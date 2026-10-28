"""Record actual Gazebo camera frames and YOLO11n results, without truth boxes."""

import argparse
import hashlib
import json
from pathlib import Path
import time

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from ultralytics import YOLO


class AssetCapture(Node):
    def __init__(self, streams):
        super().__init__("asset_camera_validation")
        self.bridge = CvBridge()
        self.frames = {}
        self.counts = {name: 0 for name in streams}
        for name, topic in streams.items():
            self.create_subscription(Image, topic, lambda msg, category=name: self.capture(category, msg), qos_profile_sensor_data)

    def capture(self, category, message):
        self.counts[category] += 1
        # Early OGRE frames can precede async texture uploads. Keep the latest
        # frame and require multiple rendered frames before collecting proof.
        self.frames[category] = self.bridge.imgmsg_to_cv2(message, "bgr8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--stream", action="append", help="Evidence label=ROS image topic; repeatable")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    streams = dict(value.split("=", 1) for value in args.stream) if args.stream else {name: f"/asset/{name}/image" for name in ("person", "car", "hatchback", "suv")}
    node = AssetCapture(streams)
    start = time.monotonic()
    while min(node.counts.values()) < 30 and time.monotonic() - start < 50:
        rclpy.spin_once(node, timeout_sec=0.2)
    if min(node.counts.values()) < 30:
        raise RuntimeError(f"camera frames not received: {node.counts}")
    model = YOLO(str(args.weights))
    evidence = {"source": "Gazebo rendered RGB camera; no truth or injected boxes", "streams": streams, "weights_sha256": hashlib.sha256(args.weights.read_bytes()).hexdigest(), "frames_received": node.counts, "classes": {}}
    for category in node.counts:
        frame = node.frames[category]
        cv2.imwrite(str(args.output / f"{category}.png"), frame)
        records = []
        for image_size in (320, 640):
            result = model.predict(frame, imgsz=image_size, conf=0.25, device="cpu", verbose=False)[0]
            detections = [{"class_id": int(box.cls[0]), "class_name": result.names[int(box.cls[0])], "confidence": float(box.conf[0]), "bbox_xyxy": [float(v) for v in box.xyxy[0]]} for box in result.boxes]
            cv2.imwrite(str(args.output / f"{category}_yolo_{image_size}.png"), result.plot())
            records.append({"imgsz": image_size, "detections": detections})
        evidence["classes"][category] = records
    (args.output / "yolo_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
