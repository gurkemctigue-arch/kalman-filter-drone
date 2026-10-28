"""Offline YOLO11 comparison on raw flight RGB and rendered viewpoint images.

Never opens a simulator or writes tracking observations. The source bag is read
through an isolated temporary decompression cache. PNG inputs contain no boxes,
labels or video overlays. Availability is not precision/recall without labels.
"""

import argparse
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np


def extract_frames(bag, output, step_s):
    import rosbag2_py
    from cv_bridge import CvBridge
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Image
    from evaluate_stage1_flight import open_bag_reader

    trial = bag.parent
    summary = json.loads((trial / "summary.json").read_text())
    start_s = summary["follow_start_s"]
    events = summary.get("shutter_events", [])
    manifest_path = output / "raw_frames.json"
    if manifest_path.is_file():
        cached = json.loads(manifest_path.read_text())
        if cached["bag"] != str(bag) or cached["step_s"] != step_s:
            raise ValueError("Existing raw-frame manifest uses another bag/sample step; choose a new output directory")
        return cached
    frames = []
    next_s = start_s
    bridge = CvBridge()
    with open_bag_reader(bag, rosbag2_py) as (reader, evidence):
        reader.set_filter(rosbag2_py.StorageFilter(topics=["/camera/color/image_raw"]))
        while reader.has_next():
            topic, data, received = reader.read_next()
            message = deserialize_message(data, Image)
            stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
            if stamp < next_s:
                continue
            next_s = stamp + step_s - 1e-5
            frame = bridge.imgmsg_to_cv2(message, "bgr8")
            relative = Path("raw_rgb") / f"rgb_{stamp:.3f}.png"
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), frame)
            active = False
            for event in events:
                if event["time_s"] <= stamp:
                    active = event["active"]
            frames.append({"file": str(relative), "stamp_s": stamp, "record_wall_s": received * 1e-9, "shutter_requested_active": active, "source_topic": topic})
    manifest = {"source": "raw RGB Image messages from rosbag, no video/annotation overlays", "bag": str(bag), "follow_start_s": start_s, "step_s": step_s, "shutter_events": events, "storage": evidence, "frames": frames}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def stats(values):
    return {"median": float(np.median(values)), "p95": float(np.quantile(values, .95)), "max": float(max(values))} if values else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--weights", type=Path, nargs="+", required=True)
    parser.add_argument("--views", type=Path)
    parser.add_argument("--step", type=float, default=.5)
    parser.add_argument("--imgsz", type=int, nargs="+", default=[640])
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = extract_frames(args.bag, args.output, args.step)
    inputs = [{**row, "path": args.output / row["file"], "group": "flight_raw_rgb"} for row in manifest["frames"]]
    if args.views:
        inputs.extend({"file": path.name, "path": path, "group": "static_viewpoints", "shutter_requested_active": False} for path in sorted(args.views.glob("view[0-9]*.png")) if "yolo" not in path.name)
    import torch
    from ultralytics import YOLO

    torch.set_num_threads(args.threads)
    report = {"source": "offline raw-image inference only; no runtime truth boxes", "class_id": 2, "threshold": .45, "threads": args.threads, "device": "cpu", "input_manifest": str(args.output / "raw_frames.json"), "models": []}
    for weights in args.weights:
        model = YOLO(str(weights))
        for size in args.imgsz:
            warm_start = time.perf_counter()
            model.predict(np.zeros((480, 640, 3), dtype=np.uint8), imgsz=size, device="cpu", verbose=False)
            warm_s = time.perf_counter() - warm_start
            rows = []
            for index, item in enumerate(inputs):
                frame = cv2.imread(str(item["path"]))
                started = time.perf_counter()
                # Match detector_node.predict defaults exactly: all classes,
                # default confidence/NMS, then select COCO car at score .45.
                result = model.predict(frame, imgsz=size, device="cpu", verbose=False)[0]
                elapsed = time.perf_counter() - started
                car_boxes = [box for box in result.boxes if int(box.cls[0]) == 2]
                confidences = [float(box.conf[0]) for box in car_boxes]
                best = max(confidences, default=0.)
                row = {key: value for key, value in item.items() if key != "path"}
                row.update(inference_wall_s=elapsed, best_car_confidence=best, detects_at_045=best >= .45, car_count_at_045=sum(float(box.conf[0]) >= .45 for box in car_boxes), detections=[{"class_id": int(box.cls[0]), "class_name": result.names[int(box.cls[0])], "confidence": float(box.conf[0]), "bbox_xyxy": [float(v) for v in box.xyxy[0]]} for box in result.boxes])
                rows.append(row)
                if index % 12 == 0 or item["group"] == "static_viewpoints":
                    directory = args.output / "annotations" / f"{weights.stem}_{size}"
                    directory.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(directory / item["file"].replace("/", "_")), result.plot())
            aggregate = {}
            for group in ("flight_raw_rgb", "static_viewpoints"):
                selected = [row for row in rows if row["group"] == group and not row["shutter_requested_active"]]
                if selected:
                    aggregate[group] = {"frames": len(selected), "detected_at_045": sum(row["detects_at_045"] for row in selected), "availability_at_045": sum(row["detects_at_045"] for row in selected) / len(selected), "confidence": stats([row["best_car_confidence"] for row in selected]), "inference_wall_s": stats([row["inference_wall_s"] for row in selected]), "failed_files": [row["file"] for row in selected if not row["detects_at_045"]]}
            record = {"weights": str(weights), "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(), "imgsz": size, "warmup_wall_s": warm_s, "aggregate": aggregate, "frames": rows}
            report["models"].append(record)
            (args.output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({key: value for key, value in record.items() if key != "frames"}), flush=True)


if __name__ == "__main__":
    main()
