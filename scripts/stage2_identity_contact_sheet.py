"""Render source-time-aligned stage-two identity evidence for visual review.

This offline utility reads immutable physical-identity frame JSONL and the
original ROS image headers. It never infers timestamps from video frame rate,
fills a missing image with a neighbouring second, or certifies an occluded
projected/amodal box as visible ground truth.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def review_frames(frames, maximum=24, requested_times=None, requested_tolerance=.11):
    """Choose diagnostic opportunities; explicit requests never silently drift."""
    if maximum < 1 or requested_tolerance < 0:
        raise ValueError("maximum must be positive and tolerance nonnegative")
    ordered = sorted(frames, key=lambda row: float(row["acquisition_s"]))
    if not ordered:
        return []
    timestamps = [float(row["acquisition_s"]) for row in ordered]
    if not all(math.isfinite(value) for value in timestamps):
        raise ValueError("Frame acquisition timestamps must be finite")
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("One diagnostic opportunity per acquisition timestamp is required")
    if requested_times:
        indices = set()
        for requested in requested_times:
            requested = float(requested)
            if not math.isfinite(requested):
                raise ValueError("Requested timestamps must be finite")
            insertion = bisect_left(timestamps, requested)
            choices = [index for index in (insertion-1, insertion) if 0 <= index < len(ordered)]
            nearest = min(choices, key=lambda index: (abs(timestamps[index]-requested), index))
            if abs(timestamps[nearest]-requested) > requested_tolerance+1e-12:
                raise ValueError(f"No diagnostic frame within {requested_tolerance}s of requested {requested}s")
            indices.add(nearest)
    elif len(ordered) <= maximum:
        indices = set(range(len(ordered)))
    elif maximum == 1:
        indices = {0}
    else:
        indices = {round(index*(len(ordered)-1)/(maximum-1)) for index in range(maximum)}
    return [ordered[index] for index in sorted(indices)]


def source_matches(image_stamp_s, requested_stamps, tolerance):
    """Indices of review opportunities with a sufficiently close source header."""
    if tolerance < 0 or not math.isfinite(image_stamp_s):
        raise ValueError("Invalid source timestamp or matching tolerance")
    return range(bisect_left(requested_stamps, image_stamp_s-tolerance-1e-12),
                 bisect_right(requested_stamps, image_stamp_s+tolerance+1e-12))


def frame_status(frame):
    expected = frame.get("expected_physical_id")
    matching = frame.get("selected_physical_match") or {}
    if expected is None:
        return "UNKNOWN_INITIAL_ID"
    if matching.get("status") != "known":
        return "UNKNOWN: "+str(matching.get("reason", "no_fresh_identity_evidence"))
    return "CORRECT" if str(expected) == str(matching.get("physical_id")) else "WRONG_PHYSICAL_ACTOR"


def draw_tile(frame, source, source_stamp, tile_width):
    from PIL import Image, ImageDraw
    # Draw on original pixels before resizing, preserving the GT/detection
    # coordinate convention and source aspect ratio.
    if source is None:
        canvas = Image.new("RGB", (640, 480), "#303030")
        ImageDraw.Draw(canvas).text((12, 210), "MISSING SOURCE IMAGE: no timestamp-qualified frame", fill="white")
    else:
        canvas = Image.fromarray(source).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    for collection, default_colour in ((frame.get("gt", []), "#58e665"), (frame.get("pred", []), "#60ceff")):
        for item in collection:
            selected = item.get("selected", False)
            colour = "#ff5858" if selected else default_colour
            box = [float(value) for value in item["bbox"]]
            draw.rectangle(box, outline=colour, width=4 if selected else 2)
            label = ("SELECTED " if selected else "GT " if default_colour == "#58e665" else "TRACK ")+str(item["id"])
            x, y = max(0, box[0]), max(0, box[1]-13)
            extent = draw.textbbox((x, y), label)
            draw.rectangle(extent, fill="black")
            draw.text((x, y), label, fill=colour)
    height = max(1, round(canvas.height*tile_width/canvas.width))
    canvas = canvas.resize((tile_width, height))
    tile = Image.new("RGB", (tile_width, height+104), "#111827")
    tile.paste(canvas, (0, 104))
    draw = ImageDraw.Draw(tile)
    stamp = float(frame["acquisition_s"])
    source_text = "MISSING" if source_stamp is None else f"{source_stamp:.6f} delta={source_stamp-stamp:+.6f}s"
    lines = [f"Diagnostic t={stamp:.6f}; source={source_text}",
             "Task="+str(frame.get("target_uuid", "")),
             "Expected="+str(frame.get("expected_physical_id"))+"; matched="+str((frame.get("selected_physical_match") or {}).get("physical_id")),
             frame_status(frame),
             "Green: amodal projected GT; blue: fresh track; red: selected"]
    for index, line in enumerate(lines):
        draw.text((5, 3+index*20), line, fill="#ff7777" if "WRONG" in line else "white")
    return tile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("frames", type=Path, help="evaluate_physical_identity.py .frames.jsonl sidecar")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--image-topic", default="/camera/color/image_raw")
    parser.add_argument("--maximum", type=int, default=24)
    parser.add_argument("--time", type=float, action="append", help="Explicit diagnostic/source acquisition time; repeatable")
    parser.add_argument("--requested-tolerance", type=float, default=.11)
    parser.add_argument("--source-tolerance", type=float, default=.002)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--rows", type=int, default=4)
    parser.add_argument("--tile-width", type=int, default=640)
    args = parser.parse_args()
    if args.columns < 1 or args.rows < 1 or args.tile_width < 200 or args.source_tolerance < 0:
        parser.error("Invalid layout or source tolerance")
    frames = [json.loads(line) for line in args.frames.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = review_frames(frames, args.maximum, args.time, args.requested_tolerance)
    if not selected:
        parser.error("The sidecar contains no diagnostic frames")
    timestamps = [float(frame["acquisition_s"]) for frame in selected]
    import rosbag2_py
    from cv_bridge import CvBridge
    from PIL import Image, ImageDraw
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from evaluate_stage1_flight import open_bag_reader, stamp_s
    images = {}; bridge = CvBridge()
    with open_bag_reader(args.bag, rosbag2_py) as (reader, metadata):
        types = {item.name: item.type for item in reader.get_all_topics_and_types()}
        if args.image_topic not in types:
            parser.error(f"No {args.image_topic} in bag")
        image_type = get_message(types[args.image_topic])
        reader.set_filter(rosbag2_py.StorageFilter(topics=[args.image_topic]))
        while reader.has_next():
            _topic, data, _recording_ns = reader.read_next()
            message = deserialize_message(data, image_type)
            stamp = stamp_s(message.header.stamp)
            indices = list(source_matches(stamp, timestamps, args.source_tolerance))
            if not indices:
                continue
            image = bridge.imgmsg_to_cv2(message, desired_encoding="rgb8")
            for index in indices:
                if index not in images or abs(stamp-timestamps[index]) < abs(images[index][0]-timestamps[index]):
                    images[index] = (stamp, image)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    per_page = args.columns*args.rows; pages = []; manifest = []
    for start in range(0, len(selected), per_page):
        tiles = []
        for index in range(start, min(start+per_page, len(selected))):
            source_stamp, source = images.get(index, (None, None))
            tiles.append(draw_tile(selected[index], source, source_stamp, args.tile_width))
            manifest.append({"acquisition_s":timestamps[index], "source_image_stamp_s":source_stamp,
                             "source_image_found":source is not None, "task_uuid":selected[index].get("target_uuid"),
                             "identity_status":frame_status(selected[index]), "page":len(pages)+1,
                             "expected_physical_id":selected[index].get("expected_physical_id"),
                             "matched_physical_id":(selected[index].get("selected_physical_match") or {}).get("physical_id"),
                             "physical_match_reason":(selected[index].get("selected_physical_match") or {}).get("reason"),
                             "geometry_subset_eligible":selected[index].get("visible_geometry_eligible"),
                             "tile_index":index-start})
        tile_height = max(tile.height for tile in tiles)
        page = Image.new("RGB", (args.columns*args.tile_width, args.rows*tile_height+36), "#030712")
        ImageDraw.Draw(page).text((8, 8), "Independent source-time identity review. Amodal GT / UNKNOWN intervals need visual review.", fill="white")
        for index, tile in enumerate(tiles):
            page.paste(tile, ((index % args.columns)*args.tile_width, 36+(index//args.columns)*tile_height))
        filename = f"identity_review_{len(pages)+1:02d}.jpg"
        page.save(args.output_dir/filename, quality=94)
        pages.append(filename)
    result = {"schema_version":1,"source_bag":str(args.bag.resolve()),"source_frames":str(args.frames.resolve()),
              "source_tolerance_s":args.source_tolerance,"selection":"explicit times" if args.time else "uniform diagnostic opportunities",
              "selected_frames":manifest,"missing_source_images":sum(not row["source_image_found"] for row in manifest),
              "pages":pages,"bag_storage":metadata,
              "interpretation":"Visual review artifact, not an automated identity acceptance certificate. Original image header timestamps are required; missing source images remain explicit blanks."}
    (args.output_dir/"index.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    review={"schema_version":1,"status":"PENDING_INDEPENDENT_VISUAL_REVIEW","source_frames":str(args.frames.resolve()),
            "source_bag":str(args.bag.resolve()),"reviewer":None,
            "scope":"Representative source-time screening, not a full visible-GT annotation approval or a whole-sequence identity certificate.",
            "geometry_warning":"Geometry MOT permits GT box IoU <= .01; conservative selected identity requires no positive GT box overlap. Geometry eligibility can therefore coexist with UNKNOWN physical identity.",
            "frames":[{**row,"visible_gt_boxes_approved":None,"selected_physical_actor_manually_confirmed":None,
                       "review_notes":None} for row in manifest]}
    (args.output_dir/"visual_review.json").write_text(json.dumps(review,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"pages":len(pages),"frames":len(selected),"missing_source_images":result["missing_source_images"]}))


if __name__ == "__main__":
    main()
