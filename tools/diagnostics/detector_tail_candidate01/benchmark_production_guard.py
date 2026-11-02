"""Paced PT CPU comparison invoking the real production thread guard.

The small run routine is copied from the frozen policy instrument so its
measurement path stays reviewable without replacing globals or function code.
Exactly one policy is measured per fresh process; this is not flight acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.diagnostics.detector_tail_candidate01 import benchmark_cpu_policy as instrument

common = instrument.common
configure_wait_policy = instrument.configure_wait_policy
delay_until_next = instrument.delay_until_next
thread_count = instrument.thread_count
EXPECTED_INSTRUMENT_SHA256 = "f4ec0970b0a4f7348a0c1f87f892a8d8cf2f98c8d2560c9fbae44c80a2135812"
DETECTOR_SOURCE = ROOT / "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/detector_node.py"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", choices=("baseline", "guarded"), required=True)
    parser.add_argument("--wait-policy", choices=("inherited", "passive"), default="inherited")
    parser.add_argument("--threads", type=int, choices=(1, 2, 4), default=4)
    parser.add_argument("--imgsz", type=instrument.positive, default=512)
    parser.add_argument("--warmup", type=common.at_least_three, default=3)
    parser.add_argument("--repeats", type=common.at_least_three, default=12)
    parser.add_argument("--limit-images", type=instrument.positive, default=12)
    parser.add_argument("--period", type=instrument.period, default=1.0)
    return parser.parse_args(argv)


def validate_helper_source(module, expected=DETECTOR_SOURCE):
    """Reject an installed or patched-in helper from a different source tree."""
    expected = expected.resolve(strict=True)
    module_path = Path(module.__file__).resolve(strict=True)
    helper = module.enforce_cpu_thread_count
    function_source = inspect.getsourcefile(helper)
    if (module_path != expected or function_source is None
            or Path(function_source).resolve(strict=True) != expected):
        raise ValueError("Production guard imported from a different source file")
    return helper, {"path": str(expected), "sha256": common.sha(expected),
                    "module": helper.__module__, "function": helper.__name__}


def load_production_helper():
    nodes = ROOT / "ros2_ws/src/uav_tracking_nodes"
    if str(nodes) not in sys.path:
        sys.path.insert(0, str(nodes))
    from uav_tracking_nodes import detector_node
    return validate_helper_source(detector_node)


class CountingTorch:
    """Delegate real get/set calls and count only explicit Python setters."""
    def __init__(self, torch):
        self.torch, self.setter_calls = torch, 0

    def get_num_threads(self):
        return self.torch.get_num_threads()

    def set_num_threads(self, value):
        self.setter_calls += 1
        return self.torch.set_num_threads(value)


class ProductionCpuPolicy(instrument.CpuPolicy):
    def __init__(self, torch, cv2, name, threads, *, clock=time.perf_counter):
        if name != "guarded":
            raise ValueError("ProductionCpuPolicy is only the guarded condition")
        super().__init__(torch, cv2, name, threads, clock=clock)
        self.helper, self.helper_metadata = load_production_helper()

    def __call__(self, _predictor):
        started = self.clock()
        before = self.torch.get_num_threads()
        proxy = CountingTorch(self.torch)
        after = self.helper(proxy, self.threads)
        self.callbacks.append({"before": before, "after": after,
                               "set_called": proxy.setter_calls > 0,
                               "explicit_python_setter_calls": proxy.setter_calls,
                               "wall_s": self.clock() - started,
                               "native_thread_id": threading.get_native_id(),
                               "production_helper": dict(self.helper_metadata)})


def create_policy(torch, cv2, name, threads):
    if name == "baseline":
        return instrument.CpuPolicy(torch, cv2, name, threads)
    if name == "guarded":
        return ProductionCpuPolicy(torch, cv2, name, threads)
    raise ValueError("Unknown production comparison policy")


def source_metadata():
    instrument_hash = common.sha(instrument.__file__)
    if instrument_hash != EXPECTED_INSTRUMENT_SHA256:
        raise ValueError("Frozen policy instrument changed")
    return {"derived_from": {"path": str(Path(instrument.__file__).resolve()), "sha256": instrument_hash},
            "wrapper": {"path": str(Path(__file__).resolve()), "sha256": common.sha(__file__)},
            "detector": {"path": str(DETECTOR_SOURCE.resolve(strict=True)), "sha256": common.sha(DETECTOR_SOURCE)},
            "factory": "baseline uses original CpuPolicy; guarded subclasses it and invokes imported enforce_cpu_thread_count through a counting delegate",
            "run_routine": "Copied from frozen instrument, using its common helpers; no module globals or function code are replaced",
            "setter_count_scope": "Explicit Python set_num_threads calls; excludes PyTorch internal lazy initialization"}


def run(args):
    input_dir, model_path, output, paths = common.validated_paths(args)
    sources = source_metadata()
    output.mkdir(exist_ok=False)
    common.write_new(output / "production_guard_instrument.json", sources)
    started, model_hash = common.now(), common.sha(model_path)
    rows, warmups, runner, shape_handle = [], [], None, None
    error, context = None, None
    common.write_new(output / "started.json", {
        "schema_version": 1, "started_utc": started,
        "script_sha256": common.sha(__file__), "common_script_sha256": common.sha(common.__file__),
        "production_worker_sha256": common.sha(ROOT / "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/inference_worker.py"),
        "arguments": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "model": {"path": str(model_path), "sha256": model_hash},
        "predict": common.PREDICT,
        "main_native_thread_id": threading.get_native_id(),
        "scope": "ISOLATED_PRELOADED_RGB_REAL_PRODUCTION_GUARD_DIAGNOSTIC_NOT_FLIGHT_ACCEPTANCE"})
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    def interrupted(signum, _frame):
        raise InterruptedError("Signal " + str(signum))
    for sig in handlers:
        signal.signal(sig, interrupted)
    try:
        env = configure_wait_policy(args.wait_policy)
        os.environ["YOLO_OFFLINE"] = "true"
        os.environ["YOLO_CONFIG_DIR"] = str(output / "yolo_config")
        import cv2
        import torch
        from ultralytics import YOLO
        policy = create_policy(torch, cv2, args.policy, args.threads)
        policy.initialize()
        model = YOLO(str(model_path))
        model.add_callback("on_predict_start", policy)
        shape = {"actual_model_input_shape": None}
        def attach_shape_hook(_predictor):
            nonlocal shape_handle
            if shape_handle is None:
                shape_handle = common.observe_input_shape(model, shape)
        model.add_callback("on_predict_start", attach_shape_hook)
        images = []
        for path in paths:
            digest = common.sha(path)
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None or image.ndim != 3 or image.shape[2] != 3 or common.sha(path) != digest:
                raise ValueError("Input decode failed or PNG changed: " + str(path))
            images.append({"path": str(path), "sha256": digest, "image": image,
                           "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(), "shape": list(image.shape)})
        common.write_new(output / "inputs.json", {"frames": [{k: v for k, v in item.items() if k != "image"} for item in images],
                                                  "preloaded": True})
        versions = {}
        for package in ("torch", "ultralytics", "numpy", "opencv-python"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        common.write_new(output / "environment.json", {
            "python": sys.version, "executable": sys.executable, "versions": versions,
            "wait_policy": env, "torch_threads_after_initialize": torch.get_num_threads(),
            "torch_interop_threads": torch.get_num_interop_threads(), "cv2_threads": cv2.getNumThreads(),
            "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
            "pacing": "No pace during 3+ logged warmup calls; measured starts use actual previous start, no backlog",
            "policy": args.policy, "production_helper": getattr(policy, "helper_metadata", None),
            "notes": "No Gazebo/ROS contention; baseline sequentially precedes guarded unless caller separately chooses another order"})
        previous_finish = None
        def measure(_condition, image):
            nonlocal previous_finish
            shape["actual_model_input_shape"] = None
            callback_count = len(policy.callbacks)
            psi_before, usage_before = common.psi_snapshot(), common.usage_snapshot()
            count_before = thread_count()
            cpu_before, thread_before, wall_before = time.process_time(), time.thread_time(), time.perf_counter()
            idle = None if previous_finish is None else wall_before - previous_finish
            result, = model.predict(image, imgsz=args.imgsz, **common.PREDICT)
            wall_after, thread_after, cpu_after = time.perf_counter(), time.thread_time(), time.process_time()
            previous_finish = wall_after
            usage_after, psi_after = common.usage_snapshot(), common.psi_snapshot()
            if len(policy.callbacks) != callback_count + 1:
                raise RuntimeError("Expected exactly one on_predict_start thread callback per predict")
            boxes = [{"class_id": int(box.cls[0]), "confidence": float(box.conf[0]),
                      "xyxy": [float(value) for value in box.xyxy[0].tolist()]} for box in result.boxes]
            backend = model.predictor.model
            return {"predict_wall_s": wall_after-wall_before, "process_cpu_s": cpu_after-cpu_before,
                    "calling_thread_cpu_s": thread_after-thread_before,
                    "predict_started_perf_s": wall_before, "idle_since_previous_predict_finish_s": idle,
                    "speed_ms": {name: float(result.speed[name]) if result.speed.get(name) is not None else None
                                 for name in ("preprocess", "inference", "postprocess")},
                    "callback": policy.callbacks[-1], "torch_threads_after": torch.get_num_threads(),
                    "torch_interop_threads": torch.get_num_interop_threads(), "cv2_threads": cv2.getNumThreads(),
                    "process_threads_before": count_before, "process_threads_after": thread_count(),
                    "actual_model_input_shape": shape["actual_model_input_shape"],
                    "actual_backend_format": getattr(backend, "format", None),
                    "actual_backend_device": str(getattr(backend, "device", "unknown")),
                    "actual_backend_fp16": getattr(backend, "fp16", None),
                    "effective_predictor_args": {key: vars(model.predictor.args).get(key) for key in (*common.PREDICT, "imgsz")},
                    "all_post_nms_boxes": boxes, "worker_native_thread_id": threading.get_native_id(),
                    "psi_before": psi_before, "psi_after": psi_after, "psi_delta": common.psi_delta(psi_before, psi_after),
                    "usage_delta": common.usage_delta(usage_before, usage_after)}
        runner = common.ProductionRunner(measure)
        with (output / "warmup.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for index in range(args.warmup):
                context = {"phase": "warmup", "index": index}
                row = {**context, **runner(None, images[0]["image"])}
                stream.write(json.dumps(row, allow_nan=False) + "\n"); stream.flush()
                warmups.append(row)
        previous_start = None
        with (output / "samples.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for repeat in range(args.repeats):
                for index, item in enumerate(images):
                    context = {"phase": "measurement", "repeat": repeat, "image_index": index, "path": item["path"]}
                    delay_until_next(previous_start, args.period)
                    row = {**context, "png_sha256": item["sha256"], **runner(None, item["image"])}
                    previous_start = row["predict_started_perf_s"]
                    stream.write(json.dumps(row, allow_nan=False) + "\n"); stream.flush()
                    rows.append(row)
                    if len(rows) % 12 == 0:
                        print(json.dumps({"status": "BENCHMARK_PROGRESS", "completed": len(rows),
                                          "expected": len(images)*args.repeats, "latest_wall_s": row["predict_wall_s"]}), flush=True)
        if common.sha(model_path) != model_hash or any(common.sha(item["path"]) != item["sha256"]
                or hashlib.sha256(item["image"].tobytes()).hexdigest() != item["pixel_sha256"] for item in images):
            raise ValueError("Checkpoint or input bytes changed during measurement")
        if common.sha(DETECTOR_SOURCE) != sources["detector"]["sha256"]:
            raise ValueError("Production detector helper source changed during measurement")
        if common.sha(instrument.__file__) != sources["derived_from"]["sha256"]:
            raise ValueError("Frozen policy instrument changed during measurement")
    except BaseException as caught:
        error = type(caught).__name__ + ":" + str(caught)
        raise
    finally:
        if runner is not None:
            runner.shutdown()
        if shape_handle is not None:
            shape_handle.remove()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        report = {"schema_version": 1, "started_utc": started, "finished_utc": common.now(),
                  "status": "FAILED_PARTIAL_EVIDENCE_RETAINED" if error else "OFFLINE_PRODUCTION_GUARD_COMPLETE_NOT_FLIGHT_ACCEPTANCE",
                  "policy": args.policy, "wait_policy": args.wait_policy, "error": error,
                  "failure_context": context if error else None,
                  "expected_samples": len(paths)*args.repeats, "recorded_samples": len(rows),
                  "unattempted_or_missing": len(paths)*args.repeats-len(rows), "warmup_records": len(warmups),
                  "statistics": {name: common.stats([row.get(name) for row in rows]) for name in
                                 ("predict_wall_s", "process_cpu_s", "calling_thread_cpu_s", "idle_since_previous_predict_finish_s")},
                  "callback_wall_s": common.stats([row["callback"]["wall_s"] for row in rows]),
                  "sources": sources, "root_cause_or_live_freshness_claimed": False}
        common.write_new(output / ("failed.json" if error else "summary.json"), report)
    print(json.dumps({"status": report["status"], "summary": str(output / "summary.json"), "samples": len(rows)}), flush=True)
    return report


if __name__ == "__main__":
    run(parse_args())
