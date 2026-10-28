"""Measure real CPU YOLO latency before freezing experiment resources."""
import argparse
import json
from pathlib import Path
import statistics
import time

import cv2
import torch
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--model", default="models/yolo11s.pt")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture = cv2.VideoCapture(str(args.video))
    capture.set(cv2.CAP_PROP_POS_FRAMES, 100)
    success, frame = capture.read()
    capture.release()
    if not success:
        raise RuntimeError("No benchmark frame available")
    model = YOLO(args.model)
    selected = {"threads": 2}
    model.add_callback("on_predict_start", lambda _: torch.set_num_threads(selected["threads"]))
    measurements = []
    for threads in (2, 1, 4, 1, 2):
        selected["threads"] = threads
        values = []
        for index in range(13):
            started = time.perf_counter()
            result = model.predict(frame, imgsz=480, device="cpu", verbose=False)[0]
            elapsed = time.perf_counter() - started
            if index >= 3:
                values.append(elapsed)
        measurements.append({"threads": threads, "wall_samples_s": values,
                             "median_s": statistics.median(values), "max_s": max(values),
                             "candidates": len(result.boxes)})
    args.output.write_text(json.dumps({"scope": "Isolated real CPU inference; excludes Gazebo and ROS sensor transfer", "measurements": measurements}, indent=2))
    print(json.dumps(measurements, indent=2))


if __name__ == "__main__":
    main()
