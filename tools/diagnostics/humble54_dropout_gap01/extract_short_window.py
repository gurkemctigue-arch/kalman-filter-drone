"""Export original short-shutter RGB evidence for human review; never adjudicate it."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


RAW_RGB = "/camera/color/image_raw"
DIAGNOSTIC = "/tracking/detection_diagnostics"
TOPICS = (
    "/clock", RAW_RGB, "/camera/aligned_depth_to_color/image_raw",
    "/research/camera/color/image_raw",
    "/research/camera/aligned_depth_to_color/image_raw", DIAGNOSTIC,
)
MAX_RAW_RGB = 32
SMALL_FILE_LIMIT = 1024 * 1024


def small_bytes(path: Path) -> bytes:
    if not path.is_file() or path.stat().st_size > SMALL_FILE_LIMIT:
        raise ValueError(f"Missing or oversized small input: {path}")
    return path.read_bytes()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: dict, field: str) -> str:
    return sha(json.dumps({k: v for k, v in value.items() if k != field},
                          sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def load_small(path: Path, evidence: dict, expected: str | None = None) -> dict:
    data = small_bytes(path)
    actual = sha(data)
    if expected is not None and actual != expected:
        raise ValueError(f"Original artifact SHA mismatch: {path}")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    evidence[str(path)] = {"bytes": len(data), "sha256": actual}
    return value


def one(rows: list, predicate, label: str):
    matches = [row for row in rows if predicate(row)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {label}; got {len(matches)}")
    return matches[0]


def stamp_ns(stamp) -> int:
    sec, nano = int(stamp.sec), int(stamp.nanosec)
    if not 0 <= nano < 1_000_000_000:
        raise ValueError("Invalid integer ROS nanosecond component")
    return sec * 1_000_000_000 + nano


def decimal_time(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Nonfinite source time")
    return result


def bind_inputs(source: Path, plan_path: Path, slot_id: str) -> tuple[dict, Path, Path]:
    evidence = {}
    plan = load_small(plan_path, evidence)
    if digest(plan, "plan_sha256") != plan.get("plan_sha256"):
        raise ValueError("Original plan content digest mismatch")
    if Path(plan["frozen_root"]).resolve() != source:
        raise ValueError("--source-root differs from the original frozen root")
    if Path(plan["output"]).resolve() != plan_path.parent:
        raise ValueError("Use the original plan in its original matrix directory")
    trial = one(plan["trials"], lambda row: row["id"] == slot_id, "planned slot")
    if trial.get("condition") not in {"dropout", "combined"}:
        raise ValueError("This diagnostic is restricted to planned dropout/combined conditions")
    directory = Path(trial["directory"]).resolve(strict=True)
    if directory.name != trial["name"] or directory.parent != Path(plan["results_root"]).resolve():
        raise ValueError("Original trial name/directory/results-root binding differs")
    terminal = load_small(plan_path.parent / "slots" / f"{slot_id}.json", evidence)
    if digest(terminal, "record_sha256") != terminal.get("record_sha256"):
        raise ValueError("Original terminal content digest mismatch")
    if (terminal.get("id") != slot_id or terminal.get("name") != trial["name"]
            or terminal.get("plan_sha256") != plan["plan_sha256"]
            or terminal.get("execution_status") != "COMPLETED"
            or terminal.get("infrastructure_stop") is not False
            or type(terminal.get("flight_exit_code")) is not int
            or terminal["flight_exit_code"] != 0
            or terminal.get("cleanup", {}).get("residual_processes") != []):
        raise ValueError("Original closed non-infrastructure terminal binding failed")
    flight = one(terminal["commands"], lambda row: row["kind"] == "flight", "flight command")
    command = flight["command"]
    if (flight.get("error") is not None or flight.get("returncode") != 0
            or command != trial["flight_command"] or command.count("--name") != 1
            or command[command.index("--name") + 1] != trial["name"]):
        raise ValueError("Original successful flight command/name binding failed")
    artifacts = terminal["artifact_hashes"]
    metadata_path = directory / "rosbag/metadata.yaml"
    metadata_bytes = small_bytes(metadata_path)
    if sha(metadata_bytes) != artifacts["rosbag/metadata.yaml"]:
        raise ValueError("Original rosbag metadata SHA differs from the terminal")
    evidence[str(metadata_path)] = {"bytes": len(metadata_bytes), "sha256": sha(metadata_bytes)}
    faults = load_small(directory / "configuration/sensor_faults.json", evidence,
                        artifacts["configuration/sensor_faults.json"])
    if (type(faults.get("seed")) is not int or faults["seed"] != trial["seed"]
            or decimal_time(faults.get("drop_fraction")) != Decimal("0.10")):
        raise ValueError("Original sensor fault seed/drop fraction differs from the planned input loss")
    for name in ("recording_closure.json", "bag_integrity.json"):
        report = load_small(directory / name, evidence, artifacts[name])
        if report.get("status") != "PASS":
            raise ValueError(f"Original recording is not closed/integrity-verified: {name}")
    evaluation = one(trial["evaluations"], lambda row: row["kind"] == "surface_flight", "surface specification")
    report_path = directory / "flight_evaluation.json"
    if Path(evaluation["report"]).resolve() != report_path:
        raise ValueError("Original surface report path differs")
    old = load_small(report_path, evidence, artifacts[report_path.name])
    recorded = one(terminal["evaluations"], lambda row: row["kind"] == "surface_flight", "surface terminal entry")
    if (Path(recorded["report"]).resolve() != report_path
            or recorded["report_sha256"] != artifacts[report_path.name]
            or recorded["result"] != old["acceptance"]["result"]
            or recorded["reported_verdict"] != old["acceptance"]["result"]
            or recorded["execution"].get("returncode") != 0):
        raise ValueError("Original surface result/hash binding differs")
    short = one(old["occlusions"], lambda row: row["kind"] == "short", "original short window")
    start, end = decimal_time(short["start_s"]), decimal_time(short["end_s"])
    ack = short["shutter_execution"]
    if (not short["complete"] or not 0 < end - start <= decimal_time(old["configuration"]["max_prediction_s"])
            or ack["close_success"] is not True or ack["open_success"] is not True
            or ack["close_ack_before_open_request"] is not True
            or ack["close_request_id"] != short["close_request_id"]
            or ack["open_request_id"] != short["open_request_id"]
            or not start <= decimal_time(ack["close_response_s"]) < end
            or decimal_time(ack["open_response_s"]) < end):
        raise ValueError("Original short window/shutter ACK evidence is inconsistent")
    reader_script = source / "scripts/evaluate_stage1_flight.py"
    reader_bytes = small_bytes(reader_script)
    if sha(reader_bytes) != plan["source_hashes"]["scripts/evaluate_stage1_flight.py"]:
        raise ValueError("Original open_bag_reader source SHA differs from the plan")
    evidence[str(reader_script)] = {"bytes": len(reader_bytes), "sha256": sha(reader_bytes)}
    manifest = {
        "schema_version": 1, "status": "PENDING_VISUAL_REVIEW", "visual_review": "PENDING_VISUAL_REVIEW",
        "started_utc": datetime.now(timezone.utc).isoformat(), "source_root": str(source),
        "plan": str(plan_path), "plan_sha256": plan["plan_sha256"], "slot_id": slot_id,
        "trial_name": trial["name"], "trial_directory": str(directory), "input_small_files": evidence,
        "original_sensor_faults": faults,
        "tool_sha256": sha(small_bytes(Path(__file__).resolve())),
        "original_terminal_status": terminal["status"], "original_engineering_evidence": terminal["engineering_evidence"],
        "original_acceptance": old["acceptance"], "original_short_window": short,
        "selection": {"start_s_decimal": str(start - Decimal("0.3")),
                      "end_s_decimal": str(end + Decimal("0.3")), "inclusive": True,
                      "basis": "Every recorded acquisition stamp in the fixed original short window +/-0.3 s",
                      "raw_rgb_hard_limit": MAX_RAW_RGB, "success_or_failure_selection": False},
        "record_sequence_scope": "Zero-based rosbag reader order after filtering exactly topics_selected; not the old evaluator sequence",
        "topics_selected": list(TOPICS), "opportunities": [], "all_selected_topics_scanned": False,
        "claim_boundary": "Read-only descriptive extraction. All recorded opportunities in the acquisition window are retained, including duplicates. Absence is not an empty detection, an occlusion finding, PASS or admission. Original terminal/checks/nulls remain unchanged. No ground truth, model, inference, target fit or predicted box is consumed. Image header ns and diagnostic acquisition_ns are exact recorded integers. Diagnostic stamp_s is also preserved with its recorded decimal precision; it supplies acquisition time only when acquisition_ns is absent, never a fabricated header. Bag payload hashes are not recomputed; original metadata, sensor-fault, closure and integrity small files are bound. PNG originals receive only lossless channel reordering; contact sheet thumbnails are review aids.",
    }
    return manifest, directory / "rosbag", reader_script


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.slot_id):
        parser.error("--slot-id must be one plain slot identifier")
    source, plan = args.source_root.resolve(strict=True), args.plan.resolve(strict=True)
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("--output must be entirely new; partial attempts are never overwritten")
    manifest, bag, reader_script = bind_inputs(source, plan, args.slot_id)
    output = output.resolve()
    for original in (source, plan.parent, bag.parent):
        if output.is_relative_to(original) or original.is_relative_to(output):
            raise ValueError("--output must be external to the frozen root and original matrix/trial")

    # ROS and imaging dependencies are deliberately imported only after --help and binding checks.
    import cv2
    from cv_bridge import CvBridge
    import numpy as np
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    spec = importlib.util.spec_from_file_location("humble54_bound_stage1_reader", reader_script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # Required by the original module's dataclasses.
    spec.loader.exec_module(module)
    output.mkdir(parents=True, exist_ok=False)
    bridge, thumbnails = CvBridge(), []
    counts, matched = Counter(), Counter()
    lo, hi = map(Decimal, (manifest["selection"]["start_s_decimal"], manifest["selection"]["end_s_decimal"]))
    latest_clock, previous_clock, clock_regressions = None, None, 0
    try:
        with module.open_bag_reader(bag, rosbag2_py) as (reader, storage):
            manifest["bag_reader"] = storage
            types = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}
            absent = sorted(set(TOPICS) - types.keys())
            manifest["absent_topics"] = absent
            if absent:
                raise ValueError(f"Required extraction topics absent: {absent}")
            classes = {topic: get_message(types[topic]) for topic in TOPICS}
            reader.set_filter(rosbag2_py.StorageFilter(topics=list(TOPICS)))
            sequence = -1
            while reader.has_next():
                topic, data, recording_ns = reader.read_next()
                sequence += 1
                if topic not in classes:
                    raise ValueError("Reader filter returned an unrequested topic")
                counts[topic] += 1
                message = deserialize_message(data, classes[topic])
                if topic == "/clock":
                    latest_clock = stamp_ns(message.clock)
                    clock_regressions += int(previous_clock is not None and latest_clock < previous_clock)
                    previous_clock = latest_clock
                    continue
                row = {"topic": topic, "record_sequence": sequence,
                       "recording_timestamp_ns": int(recording_ns), "latest_read_clock_ns": latest_clock}
                if topic == DIAGNOSTIC:
                    payload = json.loads(message.data, parse_float=Decimal)
                    original_stamp = decimal_time(payload["stamp_s"])
                    if "acquisition_ns" in payload:
                        if type(payload["acquisition_ns"]) is not int:
                            raise ValueError("Diagnostic acquisition_ns exists but is not an integer")
                        exact_ns = payload["acquisition_ns"]
                        acquisition = Decimal(exact_ns) / 1_000_000_000
                        precision = "Exact recorded diagnostic acquisition_ns; not a ROS header"
                    else:
                        exact_ns = None
                        acquisition = original_stamp
                        precision = "acquisition_ns absent: recorded stamp_s decimal only; not an integer ROS header"
                    row.update(header_ns=None, acquisition_ns=exact_ns,
                               original_stamp_s_decimal=str(original_stamp),
                               acquisition_stamp_s_decimal=str(acquisition),
                               acquisition_ns_decimal=str(acquisition * 1_000_000_000),
                               stamp_precision=precision, original_diagnostic_json=message.data)
                else:
                    ns = stamp_ns(message.header.stamp)
                    acquisition = Decimal(ns) / 1_000_000_000
                    row.update(header_sec=int(message.header.stamp.sec), header_nanosec=int(message.header.stamp.nanosec),
                               header_ns=ns, acquisition_ns=ns, acquisition_stamp_s_decimal=str(acquisition),
                               stamp_precision="Exact integer ROS sec/nanosec", encoding=message.encoding,
                               width=int(message.width), height=int(message.height))
                if not lo <= acquisition <= hi:
                    continue
                matched[topic] += 1
                manifest["opportunities"].append(row)
                if topic != RAW_RGB:
                    continue
                if matched[RAW_RGB] > MAX_RAW_RGB:
                    raise ValueError("More than 32 raw RGB opportunities: incomplete extraction; no subsampling allowed")
                pixels = bridge.imgmsg_to_cv2(message, desired_encoding="passthrough")
                conversions = {"rgb8": cv2.COLOR_RGB2BGR, "rgba8": cv2.COLOR_RGBA2BGRA}
                if message.encoding in conversions:
                    pixels = cv2.cvtColor(pixels, conversions[message.encoding])
                elif message.encoding not in {"bgr8", "bgra8", "mono8", "mono16"}:
                    raise ValueError(f"Unsupported lossless original RGB encoding: {message.encoding}")
                filename = f"raw_rgb_{matched[RAW_RGB]:02d}_seq{sequence:06d}_ns{row['header_ns']}.png"
                if not cv2.imwrite(str(output / filename), pixels, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
                    raise RuntimeError("PNG write failed")
                row["original_png"] = filename
                row["png_sha256"] = sha((output / filename).read_bytes())
                preview = pixels
                if preview.ndim == 2:
                    if preview.dtype != np.uint8:
                        preview = (preview / 256).astype(np.uint8)
                    preview = cv2.cvtColor(preview, cv2.COLOR_GRAY2BGR)
                elif preview.shape[2] == 4:
                    preview = cv2.cvtColor(preview, cv2.COLOR_BGRA2BGR)
                tile = np.full((214, 280, 3), 245, dtype=np.uint8)
                scale = min(280 / preview.shape[1], 180 / preview.shape[0])
                thumb = cv2.resize(preview, (max(1, round(preview.shape[1] * scale)), max(1, round(preview.shape[0] * scale))))
                tile[:thumb.shape[0], :thumb.shape[1]] = thumb
                cv2.putText(tile, f"{matched[RAW_RGB]:02d} seq {sequence}", (4, 194), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 0, 0), 1)
                cv2.putText(tile, f"ns {row['header_ns']}", (4, 209), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 0, 0), 1)
                thumbnails.append(tile)
            manifest["all_selected_topics_scanned"] = True
        if not counts["/clock"] or not matched[RAW_RGB]:
            raise ValueError("No readable Clock or no raw RGB opportunity in the fixed window")
        canvas = np.full((((len(thumbnails) + 3) // 4) * 214, 4 * 280, 3), 245, dtype=np.uint8)
        for index, tile in enumerate(thumbnails):
            y, x = index // 4 * 214, index % 4 * 280
            canvas[y:y + 214, x:x + 280] = tile
        if not cv2.imwrite(str(output / "contact_sheet.png"), canvas):
            raise RuntimeError("Contact sheet write failed")
        manifest["contact_sheet"] = {"file": "contact_sheet.png", "sha256": sha((output / "contact_sheet.png").read_bytes()),
                                     "scope": "Every exported raw RGB, same reader order; resized thumbnails and labels only, no boxes"}
    except Exception as exc:
        manifest["status"] = "EXTRACTION_ERROR_REVIEW_INCOMPLETE"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        manifest.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                        scanned_message_counts={topic: counts[topic] for topic in TOPICS},
                        window_opportunity_counts={topic: matched[topic] for topic in TOPICS if topic != "/clock"},
                        exported_raw_rgb_count=sum("original_png" in row for row in manifest["opportunities"]),
                        clock_regression_count=clock_regressions)
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "output": str(output), "raw_rgb_count": matched[RAW_RGB]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
