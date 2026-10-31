"""Export exact raw RGB acquisitions for an offline inference timing diagnosis.

This reads a closed bag through the existing disposable decompression reader.
It never uses truth, boxes or an annotated video to choose image pixels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stamp-ns", type=int, nargs="+", required=True)
    parser.add_argument("--topic", default="/camera/color/image_raw")
    args = parser.parse_args()
    if any(stamp < 0 for stamp in args.stamp_ns) or len(set(args.stamp_ns)) != len(args.stamp_ns):
        parser.error("timestamps must be distinct nonnegative integer source nanoseconds")
    if args.output.exists():
        parser.error("output must be a new directory")

    import cv2
    from cv_bridge import CvBridge
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Image
    from evaluate_stage1_flight import open_bag_reader

    args.output.mkdir(parents=True)
    bag = args.bag.resolve(strict=True)
    originals = {str(path.relative_to(bag)): sha256(path) for path in bag.iterdir() if path.is_file()}
    pending, images = set(args.stamp_ns), []
    bridge = CvBridge()
    with open_bag_reader(bag, rosbag2_py) as (reader, storage):
        reader.set_filter(rosbag2_py.StorageFilter(topics=[args.topic]))
        while reader.has_next() and pending:
            topic, data, record_ns = reader.read_next()
            message = deserialize_message(data, Image)
            stamp_ns = int(message.header.stamp.sec) * 1_000_000_000 + int(message.header.stamp.nanosec)
            if stamp_ns not in pending:
                continue
            image = bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            output = args.output / f"rgb_{stamp_ns}.png"
            if not cv2.imwrite(str(output), image):
                raise RuntimeError("PNG export failed: " + str(output))
            images.append({"file": output.name, "source_stamp_ns": stamp_ns,
                           "record_stamp_ns": int(record_ns), "topic": topic,
                           "input_encoding": message.encoding, "output_encoding": "bgr8",
                           "shape": list(image.shape), "sha256": sha256(output)})
            pending.remove(stamp_ns)
    after = {str(path.relative_to(bag)): sha256(path) for path in bag.iterdir() if path.is_file()}
    report = {"schema_version": 1, "scope": "raw_rgb_offline_timing_inputs_only",
              "bag": str(bag), "source_files_sha256": originals,
              "source_unchanged": originals == after, "reader": storage,
              "requested_stamp_ns": args.stamp_ns, "missing_stamp_ns": sorted(pending),
              "images": sorted(images, key=lambda item: item["source_stamp_ns"]),
              "truth_read": False, "flight_acceptance_claimed": False}
    (args.output / "inputs.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"images": len(images), "missing": sorted(pending), "source_unchanged": originals == after}), flush=True)
    if pending or originals != after:
        raise RuntimeError("Raw input extraction is incomplete or original bag bytes changed")


if __name__ == "__main__":
    main()
