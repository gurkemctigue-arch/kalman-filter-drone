"""Isolated FP32 CPU backend comparison; never starts ROS/Gazebo or changes config."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import time

import cv2
import numpy as np
import openvino as ov
import torch
from ultralytics import YOLO
from ultralytics.data.augment import LetterBox
from ultralytics.utils import ops
from ultralytics.utils.nms import non_max_suppression


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stats(values):
    return {"count": len(values), "median": float(np.median(values)),
            "p95": float(np.quantile(values, .95)), "max": float(max(values))} if values else None


def box_iou(left, right):
    a, b = np.asarray(left), np.asarray(right)
    wh = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2]))
    intersection = float(np.prod(wh))
    union = float(np.prod(a[2:] - a[:2]) + np.prod(b[2:] - b[:2]) - intersection)
    return intersection / union if union else 0.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--limit-flight", type=int, default=80)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    cv2.setNumThreads(1)
    source = args.source_root
    weights = source / "models/yolo11s.pt"
    manifest_path = source / "results/car_detector_comparison/raw_frames.json"
    manifest = json.loads(manifest_path.read_text())
    flight = [dict(row, path=manifest_path.parent / row["file"], group="flight_raw_rgb")
              for row in manifest["frames"] if not row["shutter_requested_active"]][:args.limit_flight]
    views = [dict(file=path.name, path=path, group="static_viewpoints") for path in
             sorted((source / "results/asset_validation/flight_viewpoints").glob("view[0-9]*.png"))
             if "yolo" not in path.name]
    inputs = flight + views
    for item in inputs:
        item["image"] = cv2.imread(str(item["path"]))
        if item["image"] is None:
            raise ValueError(f"Unreadable raw image: {item['path']}")
        item["sha256"] = digest(item["path"])
    report = {
        "scope": "Offline paired common preprocessing/inference/NMS latency, not live ROS flight acceptance",
        "weights_source": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt",
        "weights_sha256": digest(weights), "weights_license": "Ultralytics AGPL-3.0 / enterprise terms upstream",
        "openvino_license": "Apache-2.0", "versions": {
            package: importlib.metadata.version(package) for package in ("openvino", "ultralytics", "numpy", "torch")},
        "input_manifest_sha256": digest(manifest_path), "flight_frames": len(flight), "view_frames": len(views),
        "torch_threads": torch.get_num_threads(), "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "nms": {"confidence": .25, "iou": .7, "all_classes": True, "max_det": 300},
        "car_selection": {"class_id": 2, "minimum_confidence": .45},
        "measurement": "preloaded image -> identical LetterBox/RGB/CHW/FP32 -> backend -> same Ultralytics NMS/box scaling; no image IO, plotting, export, compile or warmup",
        "models": [],
    }
    for size, shape in ((480, (384, 480)), (640, (480, 640))):
        export_root = args.output / f"export_{size}"
        export_root.mkdir(exist_ok=True)
        copied_weights = export_root / "yolo11s.pt"
        shutil.copy2(weights, copied_weights)
        export_start = time.perf_counter()
        model_dir = export_root / "yolo11s_openvino_model"
        export_reused = (model_dir / "yolo11s.xml").is_file()
        if not export_reused:
            model_dir = Path(YOLO(str(copied_weights)).export(format="openvino", imgsz=list(shape),
                             dynamic=False, batch=1, device="cpu", half=False))
        export_s = time.perf_counter() - export_start
        xml = model_dir / "yolo11s.xml"
        core = ov.Core()
        compiled = core.compile_model(core.read_model(xml), "CPU", {
            "PERFORMANCE_HINT": "LATENCY", "INFERENCE_NUM_THREADS": args.threads,
            "NUM_STREAMS": 1, "INFERENCE_PRECISION_HINT": ov.Type.f32,
        })
        properties = {name: str(compiled.get_property(name)) for name in
                      ("EXECUTION_DEVICES", "INFERENCE_NUM_THREADS", "NUM_STREAMS", "INFERENCE_PRECISION_HINT")}
        pt = YOLO(str(weights))
        for _ in range(3):
            pt.predict(inputs[0]["image"], imgsz=size, device="cpu", verbose=False)
        backend = pt.predictor.model
        # Ultralytics select_device('cpu') resets this to NUM_THREADS during
        # setup; enforce the experimental limit after that initialization.
        torch.set_num_threads(args.threads)
        letterbox = LetterBox(shape, auto=False, stride=32)

        def infer(image, kind):
            started = time.perf_counter()
            rgb = letterbox(image=image)[..., ::-1].transpose(2, 0, 1)
            batch = np.ascontiguousarray(rgb[None], dtype=np.float32) / 255.
            tensor = torch.from_numpy(batch)
            core_start = time.perf_counter()
            if kind == "pytorch":
                raw = backend(tensor)
                raw = raw[0] if isinstance(raw, (tuple, list)) else raw
            else:
                raw = torch.from_numpy(compiled(batch)[compiled.output(0)])
            core_s = time.perf_counter() - core_start
            prediction = non_max_suppression(raw, conf_thres=.25, iou_thres=.7,
                                             classes=None, agnostic=False, max_det=300)[0]
            prediction[:, :4] = ops.scale_boxes(shape, prediction[:, :4], image.shape)
            total_s = time.perf_counter() - started
            selected = prediction[(prediction[:, 5] == 2) & (prediction[:, 4] >= .45)]
            return {"total_wall_s": total_s, "inference_wall_s": core_s,
                    "car_boxes": selected.tolist(), "detects": bool(len(selected))}

        with torch.inference_mode():
            for _ in range(3):
                infer(inputs[0]["image"], "pytorch")
                infer(inputs[0]["image"], "openvino")
            rows = []
            for index, item in enumerate(inputs):
                row = {key: item[key] for key in ("file", "group", "sha256")}
                for kind in (("pytorch", "openvino") if index % 2 == 0 else ("openvino", "pytorch")):
                    row[kind] = infer(item["image"], kind)
                if row["pytorch"]["detects"] and row["openvino"]["detects"]:
                    a = max(row["pytorch"]["car_boxes"], key=lambda box: box[4])
                    b = max(row["openvino"]["car_boxes"], key=lambda box: box[4])
                    row["best_car_box_iou"] = box_iou(a[:4], b[:4])
                    row["best_car_confidence_abs_delta"] = abs(a[4] - b[4])
                rows.append(row)
        aggregate = {}
        for group in ("flight_raw_rgb", "static_viewpoints"):
            selected = [row for row in rows if row["group"] == group]
            aggregate[group] = {"frames": len(selected), "presence_disagreements": [row["file"] for row in selected
                if row["pytorch"]["detects"] != row["openvino"]["detects"]],
                "best_car_box_iou": stats([row["best_car_box_iou"] for row in selected if "best_car_box_iou" in row]),
                "best_car_confidence_abs_delta": stats([row["best_car_confidence_abs_delta"] for row in selected if "best_car_box_iou" in row])}
            for kind in ("pytorch", "openvino"):
                aggregate[group][kind] = {"detected": sum(row[kind]["detects"] for row in selected),
                    "failed_files": [row["file"] for row in selected if not row[kind]["detects"]],
                    "total_wall_s": stats([row[kind]["total_wall_s"] for row in selected]),
                    "inference_wall_s": stats([row[kind]["inference_wall_s"] for row in selected])}
        record = {"requested_imgsz": size, "actual_input_shape": [1, 3, *shape], "export_s": export_s,
                  "export_reused": export_reused, "actual_torch_threads_during_timing": torch.get_num_threads(),
                  "openvino_properties": properties, "exported_files_sha256": {str(path.relative_to(args.output)): digest(path)
                      for path in sorted(model_dir.iterdir()) if path.is_file()}, "aggregate": aggregate, "frames": rows}
        report["models"].append(record)
        (args.output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({key: value for key, value in record.items() if key != "frames"}), flush=True)


if __name__ == "__main__":
    main()
