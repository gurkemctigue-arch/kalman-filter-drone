"""Paired CPU YOLO tail timing on preloaded raw PNGs; no ROS, GT or scoring.

Each measured pair contains every thread/size condition on identical pixels.
This isolates predict() and excludes IO, model initialization, warmup, thread
pool selection, box encoding, counters and JSON writes from its wall timer.
It cannot reproduce Gazebo/ROS contention or certify closed-loop freshness.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import signal
import sys
import threading
import time


PREDICT = {"device": "cpu", "conf": .25, "iou": .7, "classes": None,
           "agnostic_nms": False, "max_det": 300, "augment": False,
           "half": False, "rect": True, "verbose": False}


def at_least_three(value):
    value = int(value)
    if value < 3:
        raise argparse.ArgumentTypeError("Must be at least 3")
    return value


def positive(value):
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError("Must be positive")
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path, help="Direct raw PNG children; no annotations")
    parser.add_argument("--model", required=True, type=Path, help="Existing local .pt checkpoint")
    parser.add_argument("--output", required=True, type=Path, help="Exclusive new directory")
    parser.add_argument("--threads", nargs="+", type=int, choices=(1, 2, 4), default=[1, 2, 4])
    parser.add_argument("--include-512", action="store_true", help="Compare 512 as well as mandatory 640")
    parser.add_argument("--warmup", type=at_least_three, default=3, help="Calls per condition, excluded from samples")
    passes = parser.add_mutually_exclusive_group()
    passes.add_argument("--repeats", type=at_least_three, default=3, help="Complete paired passes over all images")
    passes.add_argument("--cycles", type=at_least_three, help="Complete input passes; N cycles produce N * image_count opportunities per condition")
    parser.add_argument("--worker-mode", choices=("main", "production"), default="main")
    parser.add_argument("--fixed-condition", action="store_true", help="One thread count and one size, no global-pool interleaving")
    parser.add_argument("--imgsz", type=int, choices=(640, 512), default=640, help="Single size for --fixed-condition")
    parser.add_argument("--limit-images", type=positive, help="First N sorted raw PNGs; disclosed in manifest")
    args = parser.parse_args(argv)
    if len(args.threads) != len(set(args.threads)):
        parser.error("--threads must not contain duplicates")
    if args.cycles is not None:
        args.repeats = args.cycles
    if args.fixed_condition and (len(args.threads) != 1 or args.include_512):
        parser.error("--fixed-condition requires exactly one --threads value and no --include-512")
    if args.worker_mode == "production" and not args.fixed_condition:
        parser.error("--worker-mode production requires --fixed-condition")
    if args.imgsz != 640 and not args.fixed_condition:
        parser.error("Use --include-512 for a grid or --fixed-condition --imgsz 512")
    return args


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def validated_paths(args):
    source, model, output = args.input_dir.absolute(), args.model.absolute(), args.output.absolute()
    if (source.is_symlink() or not source.is_dir() or source.resolve(strict=True) != source
            or model.is_symlink() or not model.is_file() or model.resolve(strict=True) != model
            or model.suffix.lower() != ".pt"):
        raise ValueError("Use canonical local raw-PNG directory and regular .pt model")
    if (output.exists() or output.is_symlink() or not output.parent.is_dir()
            or output.parent.resolve(strict=True) != output.parent
            or output == source or output.is_relative_to(source) or source.is_relative_to(output)):
        raise ValueError("Use an exclusive new output outside input with an existing canonical parent")
    images = sorted(path for path in source.iterdir() if path.suffix.lower() == ".png")
    if args.limit_images:
        images = images[:args.limit_images]
    if not images or any(path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path for path in images):
        raise ValueError("Require at least one regular direct raw PNG, without aliases")
    return source, model, output, images


def conditions(threads, include_512=False):
    return [{"id": f"pt_cpu_t{thread}_img{size}", "threads": thread, "imgsz": size}
            for size in ((640, 512) if include_512 else (640,)) for thread in threads]


def paired_order(items, pair_index):
    """Balanced deterministic rotation/reversal; all conditions in every pair."""
    shift = pair_index % len(items)
    result = items[shift:] + items[:shift]
    return list(reversed(result)) if (pair_index // len(items)) % 2 else result


def stats(values):
    known = sorted(float(value) for value in values
                   if isinstance(value, (int, float)) and not isinstance(value, bool)
                   and math.isfinite(value) and value >= 0)
    def quantile(q):
        index = (len(known) - 1) * q
        left, fraction = int(index), index - int(index)
        return known[left] * (1 - fraction) + known[min(left + 1, len(known) - 1)] * fraction
    return {"denominator": len(values), "known": len(known), "unknown": len(values) - len(known),
            "minimum": known[0] if known else None, "median": quantile(.5) if known else None,
            "p95": quantile(.95) if known else None, "p99": quantile(.99) if known else None,
            "maximum": known[-1] if known else None}


def parse_psi(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0] not in {"some", "full"}:
            continue
        row = {}
        for item in fields[1:]:
            key, raw = item.split("=", 1)
            if key in {"avg10", "avg60", "avg300", "total"}:
                value = int(raw) if key == "total" else float(raw)
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid PSI number")
                row[key] = value
        result[fields[0]] = row
    return result


def psi_snapshot():
    result = {}
    for name in ("cpu", "memory", "io"):
        try:
            result[name] = {"value": parse_psi(Path("/proc/pressure", name).read_text()), "error": None}
        except (OSError, ValueError) as error:
            result[name] = {"value": None, "error": type(error).__name__ + ":" + str(error)}
    return result


def psi_delta(before, after):
    result = {}
    for name in ("cpu", "memory", "io"):
        result[name] = {}
        a, b = before.get(name, {}).get("value"), after.get(name, {}).get("value")
        for kind in ("some", "full"):
            left = (a or {}).get(kind, {}).get("total")
            right = (b or {}).get(kind, {}).get("total")
            result[name][kind + "_stall_us"] = right - left if (isinstance(left, int)
                and isinstance(right, int) and right >= left) else None
    return result


def usage_snapshot():
    try:
        import resource
    except ImportError:
        return {"process": None, "thread": None, "error": "resource unavailable"}
    if not hasattr(resource, "getrusage") or not hasattr(resource, "RUSAGE_SELF"):
        return {"process": None, "thread": None, "error": "POSIX getrusage unavailable"}
    result = {"error": None}
    for name, selector in (("process", resource.RUSAGE_SELF), ("thread", getattr(resource, "RUSAGE_THREAD", None))):
        if selector is None:
            result[name] = None
            continue
        value = resource.getrusage(selector)
        result[name] = {"minor_faults": value.ru_minflt, "major_faults": value.ru_majflt,
                        "voluntary_switches": value.ru_nvcsw, "involuntary_switches": value.ru_nivcsw,
                        "max_rss_native_units": value.ru_maxrss}
    return result


def usage_delta(before, after):
    result = {}
    for scope in ("process", "thread"):
        a, b = before.get(scope), after.get(scope)
        result[scope] = {key: b[key] - a[key] if a and b and b[key] >= a[key] else None
                        for key in ("minor_faults", "major_faults", "voluntary_switches", "involuntary_switches")}
    return result


def new_production_model(path, threads, torch, yolo):
    """Same initialization and on_predict_start thread guard as detector_node."""
    torch.set_num_threads(threads)
    model = yolo(str(path))
    evidence = {"requested_threads": threads, "callback_count": 0, "effective_threads": None,
                "initialized_thread_ident": threading.get_ident(),
                "initialized_native_thread_id": threading.get_native_id(), "actual_model_input_shape": None}
    def enforce_cpu_threads(_predictor):
        torch.set_num_threads(threads)
        evidence["effective_threads"] = torch.get_num_threads()
        evidence["callback_count"] += 1
    model.add_callback("on_predict_start", enforce_cpu_threads)
    return model, evidence


def observe_input_shape(model, evidence):
    """A read-only PT forward pre-hook; shapes are not inferred from imgsz."""
    auto = getattr(getattr(model, "predictor", None), "model", None)
    core = getattr(getattr(auto, "backend", None), "model", None)
    if core is None or not hasattr(core, "register_forward_pre_hook"):
        return None
    def before_forward(_module, args):
        tensor = args[0] if args else None
        shape = getattr(tensor, "shape", None)
        evidence["actual_model_input_shape"] = [int(value) for value in shape] if shape is not None else None
    return core.register_forward_pre_hook(before_forward)


class ProductionRunner:
    """Use the actual production NonQueuingWorker and wait after one job."""
    def __init__(self, measure):
        nodes = Path(__file__).resolve().parents[1] / "ros2_ws/src/uav_tracking_nodes"
        if str(nodes) not in sys.path:
            sys.path.insert(0, str(nodes))
        from uav_tracking_nodes import inference_worker
        if Path(inference_worker.__file__).resolve(strict=True) != nodes / "uav_tracking_nodes/inference_worker.py":
            raise ValueError("Production worker imported from a different source tree")
        self.measure, self.result, self.error = measure, None, None
        self.worker = inference_worker.NonQueuingWorker(self._process, self._error)

    def _error(self, error):
        self.error = error

    def _process(self, job):
        try:
            self.result = self.measure(*job)
        except BaseException as error:
            self.error = error

    def __call__(self, condition, image):
        self.result = self.error = None
        if not self.worker.submit((condition, image)):
            raise RuntimeError("Production benchmark never queues a second job")
        if not self.worker.wait_idle(timeout=60.):
            raise TimeoutError("Production worker predict exceeded the 60 second per-job bound")
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise RuntimeError("Production worker returned no timing record")
        return self.result

    def shutdown(self):
        self.worker.shutdown()


def summarize(rows, all_conditions, image_count, repeats):
    result = {}
    for condition in all_conditions:
        selected = [row for row in rows if row["condition_id"] == condition["id"]]
        expected = image_count * repeats
        result[condition["id"]] = {"condition": condition, "expected": expected, "recorded": len(selected),
            "unattempted_or_missing": expected - len(selected),
            "predict_wall_s": stats([row.get("predict_wall_s") for row in selected]),
            "process_cpu_s": stats([row.get("process_cpu_s") for row in selected]),
            "calling_thread_cpu_s": stats([row.get("calling_thread_cpu_s") for row in selected]),
            "ultralytics_speed_ms": {key: stats([row.get("speed_ms", {}).get(key) for row in selected])
                                     for key in ("preprocess", "inference", "postprocess", "stage_sum")},
            "process_faults": {key: stats([row.get("usage_delta", {}).get("process", {}).get(key) for row in selected])
                               for key in ("minor_faults", "major_faults")},
            "system_psi_stall_us": {name + "." + kind: stats([
                row.get("psi_delta", {}).get(name, {}).get(kind + "_stall_us") for row in selected])
                for name in ("cpu", "memory", "io") for kind in ("some", "full")}}
    return result


def run(args):
    source, model_path, output, paths = validated_paths(args)
    output.mkdir(exist_ok=False)
    started, rows, warmups, models = now(), [], [], {}
    all_conditions = ([{"id": f"pt_cpu_t{args.threads[0]}_img{args.imgsz}", "threads": args.threads[0], "imgsz": args.imgsz}]
                      if args.fixed_condition else conditions(args.threads, args.include_512))
    model_hash = sha(model_path)
    write_new(output / "started.json", {"schema_version": 1, "started_utc": started,
        "script_sha256": sha(__file__), "model": {"path": str(model_path), "sha256": model_hash},
        "input_dir": str(source), "conditions": all_conditions, "repeats": args.repeats, "warmup": args.warmup,
        "cycles": args.repeats, "cycles_definition": "One complete pass over every selected PNG; not one individual prediction",
        "worker_mode": args.worker_mode, "fixed_condition": args.fixed_condition,
        "main_thread_ident": threading.get_ident(), "main_native_thread_id": threading.get_native_id(),
        "limit_images": args.limit_images, "predict": PREDICT,
        "scope": "ISOLATED_PRELOADED_PNG_CPU_PREDICT_ONLY_NO_ROS_NO_GT_NO_FLIGHT_ACCEPTANCE"})
    previous_signals = {item: signal.getsignal(item) for item in (signal.SIGINT, signal.SIGTERM)}
    def interrupted(signum, _frame):
        raise InterruptedError("Signal " + str(signum))
    for item in previous_signals:
        signal.signal(item, interrupted)
    error, active_context, runner, shape_handles = None, None, None, []
    try:
        # Heavy dependencies are imported only after the new output is reserved.
        os.environ["YOLO_OFFLINE"] = "true"
        os.environ["YOLO_CONFIG_DIR"] = str(output / "yolo_config")
        import cv2
        import torch
        from ultralytics import YOLO
        images = []
        for path in paths:
            before_hash = sha(path)
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None or image.ndim != 3 or image.shape[2] != 3 or sha(path) != before_hash:
                raise ValueError("PNG decode failed or input changed: " + str(path))
            images.append({"path": str(path), "file": path.name, "sha256": before_hash,
                "shape": list(image.shape), "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(), "image": image})
        write_new(output / "inputs.json", {"frames": [{key: value for key, value in item.items() if key != "image"}
                    for item in images], "preloaded": True, "total_preloaded_pixel_bytes": sum(item["image"].nbytes for item in images)})
        versions = {}
        for package in ("torch", "ultralytics", "numpy", "opencv-python"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        write_new(output / "environment.json", {"versions": versions, "python": sys.version,
            "executable": sys.executable, "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
            "torch_interop_threads": torch.get_num_interop_threads(), "cv2_threads": cv2.getNumThreads(),
            "environment": {key: os.environ.get(key) for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                "OMP_WAIT_POLICY", "KMP_BLOCKTIME", "WSL_DISTRO_NAME")},
            "method": {"models": "YOLO objects loaded on main thread exactly as production; fixed mode has only one resident model.",
                "worker": args.worker_mode,
                "thread_selection": ("Production mode does not select the pool outside predict; only the production on_predict_start callback enforces it."
                    if args.worker_mode == "production" else "Set requested pool before each timer; production callback repeats it during predict. Pool resizing excluded and timed separately."),
                "warmup": "At least three calls per condition on first preloaded raw image; logged and excluded.",
                "order": "Every image/repeat includes all conditions, with deterministic rotating/reversing order.",
                "psi": "System-wide /proc/pressure counters, not process-attributable; missing/reset remains unknown.",
                "cpu": "process_time includes native worker threads; thread_time covers calling thread only.",
                "faults": "getrusage snapshots bracket predict plus counter sampling; not exact instruction-level attribution.",
                "speed": "Ultralytics per-image preprocess/inference/postprocess milliseconds; their sum is not predict wall time."}})
        for threads in args.threads:
            models[threads] = new_production_model(model_path, threads, torch, YOLO)

        def measure(condition, image):
            model, evidence = models[condition["threads"]]
            pool_selection_wall = None
            if args.worker_mode != "production":
                pool_start = time.perf_counter()
                torch.set_num_threads(condition["threads"])
                pool_selection_wall = time.perf_counter() - pool_start
            evidence["actual_model_input_shape"] = None
            callback_before = evidence["callback_count"]
            pressure_before, usage_before = psi_snapshot(), usage_snapshot()
            cpu_before, thread_before, wall_before = time.process_time(), time.thread_time(), time.perf_counter()
            result, = model.predict(image, imgsz=condition["imgsz"], **PREDICT)
            wall_after, thread_after, cpu_after = time.perf_counter(), time.thread_time(), time.process_time()
            usage_after, pressure_after = usage_snapshot(), psi_snapshot()
            if (evidence["callback_count"] != callback_before + 1 or evidence["effective_threads"] != condition["threads"]
                    or torch.get_num_threads() != condition["threads"]):
                raise ValueError("Production on_predict_start thread guard was not applied exactly once")
            speed = {key: float(result.speed[key]) if result.speed.get(key) is not None else None
                     for key in ("preprocess", "inference", "postprocess")}
            speed["stage_sum"] = sum(speed.values()) if all(value is not None for value in speed.values()) else None
            encode_start = time.perf_counter()
            boxes = []
            for box in result.boxes:
                boxes.append({"class_id": int(box.cls[0]), "confidence": float(box.conf[0]),
                              "xyxy": [float(value) for value in box.xyxy[0].tolist()]})
            actual_args = vars(model.predictor.args)
            backend = model.predictor.model
            return {"predict_wall_s": wall_after - wall_before, "process_cpu_s": cpu_after - cpu_before,
                "calling_thread_cpu_s": thread_after - thread_before, "speed_ms": speed,
                "outside_timer_pool_selection_wall_s": pool_selection_wall,
                "outside_timer_boxes_encoding_wall_s": time.perf_counter() - encode_start,
                "all_post_nms_boxes": boxes, "post_nms_count": len(boxes),
                "car_count_at_045": sum(box["class_id"] == 2 and box["confidence"] >= .45 for box in boxes),
                "effective_threads": evidence["effective_threads"], "torch_threads_after": torch.get_num_threads(),
                "decoded_input_shape": list(image.shape), "actual_model_input_shape": evidence["actual_model_input_shape"],
                "initialized_thread_ident": evidence["initialized_thread_ident"],
                "initialized_native_thread_id": evidence["initialized_native_thread_id"],
                "predict_thread_ident": threading.get_ident(), "predict_native_thread_id": threading.get_native_id(),
                "predict_thread_name": threading.current_thread().name,
                "actual_backend_format": getattr(backend, "format", None),
                "actual_backend_type": type(getattr(backend, "backend", backend)).__module__ + "." + type(getattr(backend, "backend", backend)).__name__,
                "actual_backend_device": str(getattr(backend, "device", "unknown")),
                "actual_backend_fp16": getattr(backend, "fp16", None),
                "effective_predictor_args": {key: actual_args.get(key) for key in (*PREDICT, "imgsz", "quantize")},
                "psi_before": pressure_before, "psi_after": pressure_after,
                "psi_delta": psi_delta(pressure_before, pressure_after),
                "usage_before": usage_before, "usage_after": usage_after, "usage_delta": usage_delta(usage_before, usage_after)}

        runner = ProductionRunner(measure) if args.worker_mode == "production" else None
        execute = runner if runner is not None else measure
        with (output / "warmup.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for condition in all_conditions:
                for index in range(args.warmup):
                    active_context = {"phase": "warmup", "condition_id": condition["id"],
                                      "warmup_index": index, "file": images[0]["file"]}
                    row = {"condition_id": condition["id"], "warmup_index": index,
                           "frame": images[0]["file"], **execute(condition, images[0]["image"])}
                    stream.write(json.dumps(row, allow_nan=False) + "\n")
                    stream.flush()
                    warmups.append(row)
                model, evidence = models[condition["threads"]]
                if not any(item[0] is model for item in shape_handles):
                    handle = observe_input_shape(model, evidence)
                    if handle is not None:
                        shape_handles.append((model, handle))
        with (output / "samples.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            pair_index = 0
            for repeat in range(args.repeats):
                for image_index, item in enumerate(images):
                    order = paired_order(all_conditions, pair_index)
                    for order_index, condition in enumerate(order):
                        active_context = {"phase": "measurement", "pair_id": f"repeat{repeat:03d}_image{image_index:06d}",
                                          "condition_id": condition["id"], "file": item["file"], "order_index": order_index}
                        row = {"pair_id": f"repeat{repeat:03d}_image{image_index:06d}", "repeat": repeat,
                            "image_index": image_index, "file": item["file"], "png_sha256": item["sha256"],
                            "condition_id": condition["id"], "threads": condition["threads"], "imgsz": condition["imgsz"],
                            "order_index": order_index, **execute(condition, item["image"])}
                        stream.write(json.dumps(row, allow_nan=False) + "\n")
                        stream.flush()
                        rows.append(row)
                        if len(rows) % 100 == 0:
                            print(json.dumps({"status": "BENCHMARK_PROGRESS", "completed": len(rows),
                                "expected": len(all_conditions) * len(images) * args.repeats,
                                "latest_condition": condition["id"], "latest_predict_wall_s": row["predict_wall_s"]}), flush=True)
                    pair_index += 1
        if sha(model_path) != model_hash or any(sha(item["path"]) != item["sha256"]
                or hashlib.sha256(item["image"].tobytes()).hexdigest() != item["pixel_sha256"] for item in images):
            raise ValueError("Model/raw PNG/preloaded pixels changed during benchmark")
    except BaseException as caught:
        error = type(caught).__name__ + ":" + str(caught)
        raise
    finally:
        if runner is not None:
            runner.shutdown()
        for _, handle in shape_handles:
            handle.remove()
        for item, handler in previous_signals.items():
            signal.signal(item, handler)
        report = {"schema_version": 1, "started_utc": started, "finished_utc": now(),
            "status": "FAILED_PARTIAL_EVIDENCE_RETAINED" if error else "OFFLINE_PAIRED_TIMING_COMPLETE_NOT_FLIGHT_ACCEPTANCE",
            "error": error, "failure_context": active_context if error else None,
            "warmup_records": len(warmups), "samples": len(rows),
            "conditions": summarize(rows, all_conditions, len(paths), args.repeats),
            "raw_samples": str(output / "samples.jsonl"), "accuracy_or_identity_or_live_freshness_claimed": False}
        write_new(output / ("failed.json" if error else "summary.json"), report)
    print(json.dumps({"status": report["status"], "summary": str(output / "summary.json"), "samples": len(rows)}))
    return report


def main(argv=None):
    run(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
