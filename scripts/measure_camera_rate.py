"""Measure real ROS RGB/depth arrivals and acquisition intervals, without YOLO."""

import argparse
import json
from pathlib import Path
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class CameraRate(Node):
    def __init__(self):
        super().__init__("render_camera_rate_measurement")
        self.first_arrival = None
        self.records = {"rgb": [], "depth": []}
        for label, topic in (("rgb", "/camera/rgbd/image"), ("depth", "/camera/rgbd/depth_image")):
            self.create_subscription(Image, topic, lambda message, name=label: self.capture(name, message), qos_profile_sensor_data)

    def capture(self, name, message):
        arrival = time.monotonic()
        if self.first_arrival is None:
            self.first_arrival = arrival
        stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
        self.records[name].append((arrival, stamp, message.width, message.height, message.encoding))


def describe(records, start, end):
    selected = [row for row in records if start <= row[0] <= end]
    if len(selected) < 2:
        return {"frames": len(selected), "window_duration_s": end - start, "passes_10_hz_and_gap_under_0_25_s": False}
    values = np.asarray([(row[0], row[1]) for row in selected])
    intervals = np.diff(values, axis=0)
    arrival_intervals = intervals[:, 0]
    stamp_intervals = intervals[:, 1]
    elapsed = values[-1, 0] - values[0, 0]
    stamp_elapsed = values[-1, 1] - values[0, 1]
    rate = (len(selected) - 1) / elapsed
    return {
        "frames": len(selected), "window_duration_s": end - start,
        "arrival_hz": rate, "window_hz": len(selected) / (end - start),
        "acquisition_hz_sim_time": (len(selected) - 1) / stamp_elapsed if stamp_elapsed > 0 else None,
        "simulation_time_per_wall_time": stamp_elapsed / elapsed,
        "arrival_gap_s": {"p50": float(np.quantile(arrival_intervals, .50)), "p95": float(np.quantile(arrival_intervals, .95)), "p99": float(np.quantile(arrival_intervals, .99)), "max": float(np.max(arrival_intervals))},
        "stamp_gap_s": {"p50": float(np.quantile(stamp_intervals, .50)), "p95": float(np.quantile(stamp_intervals, .95)), "max": float(np.max(stamp_intervals))},
        "width": selected[-1][2], "height": selected[-1][3], "encoding": selected[-1][4],
        "passes_10_hz_and_gap_under_0_25_s": bool(rate >= 10 and np.max(arrival_intervals) < .25),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--warmup", type=float, default=5)
    parser.add_argument("--startup-timeout", type=float, default=20)
    args = parser.parse_args()
    rclpy.init()
    node = CameraRate()
    process_start = time.monotonic()
    while node.first_arrival is None and time.monotonic() - process_start < args.startup_timeout:
        rclpy.spin_once(node, timeout_sec=.1)
    window_start = (node.first_arrival or time.monotonic()) + args.warmup
    window_end = window_start + args.seconds
    if node.first_arrival is not None:
        while time.monotonic() < window_end:
            rclpy.spin_once(node, timeout_sec=.1)
    report = {"source": "real ROS bridged Gazebo RGB-D Image callbacks; monotonic wall clock", "startup_to_first_frame_s": node.first_arrival - process_start if node.first_arrival else None, "warmup_s": args.warmup, "seconds": args.seconds, "streams": {name: describe(rows, window_start, window_end) for name, rows in node.records.items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
