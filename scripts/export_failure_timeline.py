"""Export bounded scalar fault windows in one read-only rosbag pass.

The recorder's order and timestamp are retained without pretending that bag
receipt is an application's callback time. RGB/depth payloads are not read.
This is a diagnostic export, never an engineering verdict or bag replay.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time


TOPICS = (
    "/clock", "/tracking/status", "/tracking/command",
    "/tracking/flight_command", "/tracking/flight_phase", "/tracking/state",
    "/tracking/navigation_state", "/tracking/navigation_diagnostics",
    "/tracking/selection", "/tracking/detection_diagnostics", "/tracking/tracks",
    "/vehicle/odometry", "/vehicle/odometry_timing", "/fmu/out/vehicle_status_v1",
    "/fmu/out/vehicle_odometry", "/fmu/out/vehicle_local_position_v1",
    "/fmu/out/estimator_status_flags", "/tf", "/tf_static",
    "/tracking/supervisor_diagnostics",
)


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def stamp_s(stamp):
    if not isinstance(stamp, dict):
        return None
    sec, nsec = finite(stamp.get("sec")), finite(stamp.get("nanosec"))
    return sec + nsec * 1e-9 if sec is not None and nsec is not None else None


def source_time(payload, topic):
    """Keep acquisition/source time distinct from recorded-clock delivery."""
    if isinstance(payload.get("header"), dict):
        return stamp_s(payload["header"].get("stamp")), "header"
    if topic.startswith("/fmu/out/"):
        value = finite(payload.get("timestamp"))
        return (value * 1e-6 if value is not None else None), "px4_us_unverified_domain"
    for key in ("stamp_s", "acquisition_s", "image_stamp_s", "source_s", "time_s"):
        if finite(payload.get(key)) is not None:
            return finite(payload[key]), key
    if payload.get("transforms"):
        return stamp_s(payload["transforms"][0].get("header", {}).get("stamp")), "first_transform"
    return None, "no_source_stamp"


def parse_window(value):
    try:
        label, start, end = value.rsplit(":", 2)
        start, end = float(start), float(end)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("Use LABEL:START_S:END_S") from exc
    if not label or not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
        raise argparse.ArgumentTypeError("Windows need a label and finite 0 <= start < end")
    return {"name": label, "start_s": start, "end_s": end}


def window_names(row, windows):
    # Selecting either time keeps delayed measurements; no time is corrected.
    times = [finite(row.get(key)) for key in ("source_s", "received_clock_s")]
    return [w["name"] for w in windows
            if any(t is not None and w["start_s"] <= t <= w["end_s"] for t in times)]


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)) or hasattr(value, "tolist"):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "__iter__"):
        return [json_safe(v) for v in value]
    raise TypeError(f"Unsupported payload type: {type(value).__name__}")


def file_stats(bag):
    return {p.name: {"bytes": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns}
            for p in bag.iterdir() if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window", action="append", type=parse_window, required=True)
    args = parser.parse_args()
    if len({w["name"] for w in args.window}) != len(args.window):
        parser.error("Window names must be unique")
    bag, output = args.bag.resolve(strict=True), args.output.resolve()
    if output.exists() or output.is_relative_to(bag):
        parser.error("Output must be a new directory outside the source bag")
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.utilities import get_message
    from evaluate_stage1_flight import open_bag_reader

    before = file_stats(bag)
    metadata_sha = hashlib.sha256((bag / "metadata.yaml").read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    counts, selected_counts, errors = Counter(), Counter(), Counter()
    context, clock, clock_regressions = {}, None, 0
    final_clock = None
    last_progress = time.monotonic()
    try:
        with open_bag_reader(bag, rosbag2_py) as (reader, storage), (output / "timeline.jsonl").open("x") as stream:
            types = {t.name: t.type for t in reader.get_all_topics_and_types()}
            present = {t: types[t] for t in TOPICS if t in types}
            classes = {t: get_message(name) for t, name in present.items()}
            reader.set_filter(rosbag2_py.StorageFilter(topics=list(present)))
            sequence = -1
            while reader.has_next():
                topic, serialized, record_ns = reader.read_next()
                sequence += 1
                counts[topic] += 1
                try:
                    msg = deserialize_message(serialized, classes[topic])
                    payload = message_to_ordereddict(msg)
                    if topic == "/clock":
                        new_clock = stamp_s(payload.get("clock"))
                        if new_clock is None:
                            raise ValueError("Invalid /clock")
                        clock_regressions += int(clock is not None and new_clock < clock - 1e-9)
                        clock = final_clock = new_clock
                        continue
                    if isinstance(payload.get("data"), str):
                        try:
                            decoded = json.loads(payload["data"])
                        except (ValueError, TypeError):
                            decoded = None
                        if isinstance(decoded, dict):
                            payload = decoded
                    source, source_basis = source_time(payload, topic)
                    row = {"record_sequence": sequence, "topic": topic,
                           "storage_timestamp_ns": int(record_ns),
                           "source_s": source, "source_basis": source_basis,
                           "received_clock_s": clock, "payload": json_safe(payload)}
                    names = window_names(row, args.window)
                    for window in args.window:
                        # Recorder chronology is authoritative for baseline cache;
                        # use only delivery before the requested source window.
                        if clock is not None and clock < window["start_s"]:
                            context.setdefault(window["name"], {})[topic] = row
                    if names:
                        row["windows"] = names
                        stream.write(json.dumps(row, allow_nan=False) + "\n")
                        selected_counts[topic] += 1
                except Exception as exc:
                    errors[f"{topic}: {type(exc).__name__}: {exc}"] += 1
                if time.monotonic() - last_progress > 15:
                    print(json.dumps({"records_read": sum(counts.values()), "selected": sum(selected_counts.values()),
                                      "clock_s": clock}), flush=True)
                    last_progress = time.monotonic()
        unchanged = before == file_stats(bag) and metadata_sha == hashlib.sha256((bag / "metadata.yaml").read_bytes()).hexdigest()
        report = {"schema_version": 1, "scope": "ONE_PASS_READ_ONLY_SCALAR_DIAGNOSTIC_NOT_EVALUATION",
                  "status": "COMPLETE" if not errors and unchanged else "DIAGNOSTIC_INCOMPLETE",
                  "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
                  "source_bag": str(bag), "metadata_sha256": metadata_sha,
                  "source_stat_unchanged": unchanged, "source_files_before": before,
                  "windows": args.window, "topics": present, "missing_topics": [t for t in TOPICS if t not in present],
                  "counts_read": dict(counts), "counts_selected": dict(selected_counts),
                  "errors": dict(errors), "clock_regressions": clock_regressions,
                  "final_clock_s": final_clock, "storage": storage,
                  "context_before_windows": context,
                  "limitations": ["Recorder /clock is not application callback time.",
                      "Storage timestamp and PX4 timestamp clock domains are not assumed equivalent.",
                      "Window includes records whose source OR delivery falls inside; labels preserve this distinction.",
                      "All read/deserialize failures are reported; no RGB/depth or truth labels are extracted."]}
        (output / "manifest.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"output": str(output), "status": report["status"],
                          "selected": sum(selected_counts.values()), "errors": dict(errors)}), flush=True)
        return 0 if not errors and unchanged else 2
    except Exception as exc:
        (output / "failure.json").write_text(json.dumps({"error": f"{type(exc).__name__}: {exc}",
            "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
