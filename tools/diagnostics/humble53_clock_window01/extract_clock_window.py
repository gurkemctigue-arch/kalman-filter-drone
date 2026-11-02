"""Export closed Humble recordings without changing a trial or its verdicts.

Read five topics once with the native compression reader. Preserve its order
and the original recorder timestamp, then independently compare that order
with the staged SQLite timestamp/id order. Clock values, producer ROS source
times and recorder system timestamps remain explicitly separate domains.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gc
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile

TOPICS = ("/clock", "/fmu/out/vehicle_odometry", "/vehicle/odometry_timing",
          "/vehicle/odometry", "/tracking/flight_phase")
CLOCK, RAW, TIMING, ODOMETRY, PHASE = TOPICS
SMALL_LIMIT = 2 * 1024**2
CONTEXT = 12
SOURCE_WINDOW_NS = (76_400_000_000, 77_100_000_000)
SOURCE_CHANGE_WINDOW_NS = 50_000_000
PHASE_PATTERN = re.compile(r"; source_sim_s=([-+0-9.eE]+)\s*$")
WALL_PATTERN = re.compile(r"(?:^|; )phase_wall_monotonic_s=([-+0-9.eE]+)(?:;|$)")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def small_bytes(path):
    require(path.is_file() and not path.is_symlink(), "Ordinary input required: " + str(path))
    require(path.stat().st_size <= SMALL_LIMIT, "Small-input limit exceeded: " + str(path))
    data = path.read_bytes()
    require(len(data) <= SMALL_LIMIT, "Small input grew: " + str(path))
    return data


def small_pin(path):
    data = small_bytes(path)
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def file_stat(path):
    require(path.is_file() and not path.is_symlink(), "Ordinary archive required: " + str(path))
    stat = path.stat()
    return {"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns, "device": stat.st_dev, "inode": stat.st_ino}


def ns(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value)) * 1_000_000_000
        return int(number.to_integral_value()) if number.is_finite() else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def ros_stamp(stamp):
    sec, nanosec = int(stamp.sec), int(stamp.nanosec)
    require(0 <= nanosec < 1_000_000_000, "Malformed ROS stamp")
    return sec * 1_000_000_000 + nanosec


def optional_phase_value(text, pattern, name):
    if text.count(name + "=") != 1:
        return None
    match = pattern.search(text)
    return ns(match.group(1)) if match else None


def vector(message):
    return [float(getattr(message, key)) for key in ("x", "y", "z")]


def payload(topic, message):
    if topic == CLOCK:
        value = ros_stamp(message.clock)
        return {"clock_source_ns": value}, value
    if topic == RAW:
        value = int(message.timestamp_sample) * 1000
        return {"timestamp_sample_us": int(message.timestamp_sample),
                "timestamp_publication_us": int(message.timestamp),
                "reset_counter": int(message.reset_counter),
                "pose_frame": int(message.pose_frame), "velocity_frame": int(message.velocity_frame)}, value
    if topic == TIMING:
        text = str(message.data)
        value = json.loads(text)
        require(isinstance(value, dict), "Timing payload must be an object")
        return {"diagnostic": value, "original_text": text}, ns(value.get("source_sample_s"))
    if topic == PHASE:
        text = str(message.data)
        source = optional_phase_value(text, PHASE_PATTERN, "source_sim_s")
        return {"original_text": text, "phase": text.split(":", 1)[0].strip(),
                "phase_source_ros_ns": source,
                "phase_producer_monotonic_ns": optional_phase_value(
                    text, WALL_PATTERN, "phase_wall_monotonic_s")}, source
    stamp = ros_stamp(message.header.stamp)
    q = message.pose.pose.orientation
    return {"header_source_ns": stamp, "frame_id": message.header.frame_id,
            "child_frame_id": message.child_frame_id,
            "position_m": vector(message.pose.pose.position),
            "velocity_mps": vector(message.twist.twist.linear),
            "quaternion_xyzw": [float(getattr(q, key)) for key in ("x", "y", "z", "w")]}, stamp


@contextmanager
def staged_reader(bag, metadata, cache_parent, rosbag2_py):
    """Copy compressed inputs: do not create hardlinks or files in the source."""
    with tempfile.TemporaryDirectory(prefix="humble53_clock_read_", dir=cache_parent) as directory:
        cache = Path(directory)
        shutil.copy2(bag / "metadata.yaml", cache / "metadata.yaml")
        for relative in metadata["relative_file_paths"]:
            require(Path(relative).name == relative, "Only flat archive names are supported")
            shutil.copy2(bag / relative, cache / relative)
        compressed = bool(metadata.get("compression_format") and
                          str(metadata.get("compression_mode", "none")).lower() not in ("", "none"))
        reader_type = rosbag2_py.SequentialCompressionReader if compressed else rosbag2_py.SequentialReader
        reader = reader_type()
        try:
            reader.open(rosbag2_py.StorageOptions(uri=str(cache), storage_id="sqlite3"),
                        rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                                  output_serialization_format="cdr"))
            yield reader, cache
        finally:
            del reader
            gc.collect()


def sqlite_order_check(cache, metadata, native_rows, expected_all_counts):
    """Check bytes/order independently; never replace native-reader ordering."""
    require(len(metadata["relative_file_paths"]) == 1, "One storage file required for exact ordering check")
    relative = metadata["relative_file_paths"][0]
    filename = relative[:-5] if relative.endswith(".zstd") else relative
    path = cache / filename
    require(path.is_file() and path.suffix == ".db3", "Native reader did not create the staged SQLite database")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    mismatches, observed, digest = [], Counter(), hashlib.sha256()
    index = 0
    try:
        names = dict(connection.execute("SELECT id,name FROM topics"))
        all_counts = {names[key]: count for key, count in connection.execute(
            "SELECT topic_id,count(*) FROM messages GROUP BY topic_id")}
        require(all_counts == expected_all_counts, "Staged SQL topic counts differ from original bag_integrity")
        ids = [key for key, name in names.items() if name in TOPICS]
        query = ("SELECT id,topic_id,timestamp,data FROM messages WHERE topic_id IN (" +
                 ",".join("?" for _ in ids) + ") ORDER BY timestamp ASC,id ASC")
        for database_id, topic_id, timestamp, data in connection.execute(query, ids):
            topic = names[topic_id]
            signature = [int(timestamp), topic, hashlib.sha256(data).hexdigest()]
            digest.update(json_bytes(signature) + b"\n")
            observed[topic] += 1
            native = native_rows[index] if index < len(native_rows) else None
            if native is None or signature != [native["recorder_timestamp_ns"], native["topic"], native["cdr_sha256"]]:
                if len(mismatches) < 12:
                    mismatches.append({"filtered_sequence": index, "sqlite_message_id": database_id,
                                       "sqlite_signature": signature,
                                       "native_signature": None if native is None else [
                                           native["recorder_timestamp_ns"], native["topic"], native["cdr_sha256"]]})
            elif native is not None:
                native["sqlite_message_id"] = int(database_id)
            index += 1
    finally:
        connection.close()
    return {"compared_records": index, "all_stored_topic_counts_match_integrity": True,
            "selected_topic_counts": dict(observed), "sqlite_timestamp_id_order_sha256": digest.hexdigest(),
            "matches_native_timestamp_topic_cdr_order": not mismatches and index == len(native_rows),
            "first_mismatches": mismatches,
            "scope": "Comparison against SQLite ORDER BY recorder timestamp,id; native output is never resorted"}


def export(args):
    root = args.root.resolve(strict=True)
    trial = args.trial.resolve(strict=True)
    output = args.output.resolve()
    require(root.is_dir() and trial.is_dir(), "Existing root/trial directories required")
    results_root = (root / "results").resolve(strict=True)
    require(trial.is_relative_to(results_root), "Trial must belong to the named frozen root/results")
    require(args.output.is_absolute() and not output.exists() and output.parent.is_dir(),
            "Fresh absolute output directory with an existing parent required")
    require(not output.is_relative_to(root) and not output.is_relative_to(results_root),
            "Output must be outside frozen root and its resolved results directory")
    cache_parent = (args.cache_parent if args.cache_parent else Path(tempfile.gettempdir())).resolve(strict=True)
    require(cache_parent.is_dir() and not cache_parent.is_relative_to(root)
            and not cache_parent.is_relative_to(results_root), "Cache must be outside frozen root/results")
    bag = trial / "rosbag"
    relative_small = ("run_config.json", "summary.json", "bag_integrity.json", "recording_closure.json",
                      "px4_source_clock_report.json", "native_startup_report.json", "rosbag/metadata.yaml",
                      "configuration/runtime_parameters.yaml")
    pins_before = {name: small_pin(trial / name) for name in relative_small}
    integrity = json.loads(small_bytes(trial / "bag_integrity.json"))
    source_report = json.loads(small_bytes(trial / "px4_source_clock_report.json"))
    native_report = json.loads(small_bytes(trial / "native_startup_report.json"))
    closure = json.loads(small_bytes(trial / "recording_closure.json"))
    require(integrity.get("status") == "PASS" and integrity.get("recorder_exit_code") == 0 and
            closure.get("status") == "PASS" and closure.get("finished_utc"), "Closed, integrity-checked original trial required")
    require(integrity.get("published_metadata_sha256") == pins_before["rosbag/metadata.yaml"]["sha256"],
            "Original published metadata hash differs")
    import yaml
    metadata = yaml.safe_load(small_bytes(bag / "metadata.yaml"))["rosbag2_bagfile_information"]
    require(metadata.get("storage_identifier") == "sqlite3", "Only recorded SQLite bags are supported")
    native_integrity = integrity["native_reader_validation"]
    expected_all = native_integrity["topic_counts"]
    require(native_integrity.get("status") == "PASS" and native_integrity.get("full_stream_read") is True and
            expected_all == integrity["raw_validation"]["topic_counts"], "Original full native topic-count evidence required")
    expected = {topic: expected_all[topic] for topic in TOPICS}
    archives = {item["path"]: item for item in integrity["compressed_files"]}
    require(set(metadata["relative_file_paths"]) == set(archives), "Original archive map differs")
    stats_before = {name: file_stat(bag / name) for name in archives}
    require(all(stats_before[name]["bytes"] == item["bytes"] for name, item in archives.items()), "Archive byte sizes differ")
    required_cache = sum(item["bytes"] + item["raw_bytes"] for item in archives.values()) + 256 * 1024**2
    require(shutil.disk_usage(cache_parent).free >= required_cache, "Insufficient space for isolated copy/decompression cache")
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as error:
        raise RuntimeError("Source ROS Humble, matching px4_msgs and the frozen workspace before running") from error
    rows, counts, decode_errors, clock_rows, events = [], Counter(), [], [], []
    clock_ref, previous_wall, previous_clock, previous_timing_source = None, None, None, None
    audit_four_sequence = 0
    native_digest = hashlib.sha256()
    with staged_reader(bag, metadata, cache_parent, rosbag2_py) as (reader, cache):
        types = {item.name: item.type for item in reader.get_all_topics_and_types() if item.name in TOPICS}
        require(set(types) == set(TOPICS), "All five recorded topics must exist")
        reader.set_filter(rosbag2_py.StorageFilter(topics=list(TOPICS)))
        classes = {topic: get_message(kind) for topic, kind in types.items()}
        while reader.has_next():
            require(len(rows) < 250_000, "Bounded five-topic record limit exceeded")
            topic, data, wall_ns = reader.read_next()
            sequence = len(rows)
            before = clock_ref
            row = {"filtered_sequence": sequence, "topic": topic,
                   "recorder_timestamp_ns": int(wall_ns), "recorder_timestamp_domain": "ORIGINAL_BAG_RECORDER_SYSTEM_CLOCK",
                   "latest_recorded_clock_before": before, "cdr_sha256": hashlib.sha256(data).hexdigest()}
            if topic != PHASE:
                row["source_clock_four_topic_sequence"] = audit_four_sequence
                audit_four_sequence += 1
            if previous_wall is not None and wall_ns < previous_wall:
                events.append({"kind": "native_recorder_timestamp_regression", "sequence": sequence,
                               "previous_ns": previous_wall, "current_ns": int(wall_ns)})
            previous_wall = int(wall_ns)
            try:
                decoded, source_ns = payload(topic, deserialize_message(data, classes[topic]))
                row.update(payload=decoded, message_source_ros_ns=source_ns)
                if topic == CLOCK:
                    clock_ref = {"filtered_sequence": sequence, "source_ros_ns": source_ns,
                                 "recorder_timestamp_ns": int(wall_ns)}
                    row["clock_source_step_ns"] = None if previous_clock is None else source_ns - previous_clock
                    if previous_clock is not None and (source_ns < previous_clock or
                                                       source_ns - previous_clock > SOURCE_CHANGE_WINDOW_NS):
                        events.append({"kind": "recorded_clock_source_change_window", "sequence": sequence,
                                       "previous_source_ns": previous_clock, "source_ns": source_ns})
                    previous_clock = source_ns
                    clock_rows.append(row)
                elif topic == TIMING and source_ns is not None:
                    if previous_timing_source is not None and (source_ns < previous_timing_source or
                            source_ns - previous_timing_source > SOURCE_CHANGE_WINDOW_NS):
                        events.append({"kind": "producer_sample_source_change_window", "sequence": sequence,
                                       "previous_source_ns": previous_timing_source, "source_ns": source_ns})
                    previous_timing_source = source_ns
            except Exception as error:
                row["decode_error"] = f"{type(error).__name__}: {error}"
                decode_errors.append({"sequence": sequence, "topic": topic, "error": row["decode_error"]})
            row["latest_recorded_clock_after"] = clock_ref
            rows.append(row)
            counts[topic] += 1
            native_digest.update(json_bytes([int(wall_ns), topic, row["cdr_sha256"]]) + b"\n")
        sql_check = sqlite_order_check(cache, metadata, rows, expected_all)
    counts_match = dict(counts) == expected
    phase_rows = [row for row in rows if row["topic"] == PHASE]
    anomalies = []
    for row in rows:
        reference = row["latest_recorded_clock_before"]
        recorded_ns = reference["source_ros_ns"] if reference else None
        p = row.get("payload", {})
        anchor = None
        kind = None
        if row["topic"] == TIMING:
            anchor = ns(p.get("diagnostic", {}).get("receipt_ros_s"))
            kind = "diagnostic_delivery_outside_clock_contract"
            limits = (-50_000_001, 500_000_001)
        elif row["topic"] == ODOMETRY:
            anchor = row.get("message_source_ros_ns")
            kind = "odometry_delivery_outside_source_freshness"
            limits = (-100_000_000, 550_000_000)
        elif row["topic"] == PHASE:
            anchor = row.get("message_source_ros_ns")
            kind = "phase_source_time_stale_or_future"
            limits = (-50_000_001, 500_000_001)
        if kind and anchor is not None and recorded_ns is not None:
            difference = recorded_ns - anchor
            row["recorded_clock_minus_producer_ros_ns"] = difference
            if not limits[0] <= difference <= limits[1]:
                anomaly = {"kind": kind, "sequence": row["filtered_sequence"],
                           "recorder_timestamp_ns": row["recorder_timestamp_ns"],
                           "producer_source_or_receipt_ros_ns": anchor,
                           "latest_recorded_clock": reference,
                           "same_domain_clock_difference_ns": difference,
                           "selection_limits_ns": list(limits)}
                anomalies.append(anomaly)
    clock_sequences = [row["filtered_sequence"] for row in clock_rows]
    for event in anomalies:
        following = bisect_right(clock_sequences, event["sequence"])
        needed = event["producer_source_or_receipt_ros_ns"]
        catchup = next((row for row in clock_rows[following:] if row["message_source_ros_ns"] >= needed), None)
        event["first_later_recorded_clock_at_or_after_producer"] = None if catchup is None else {
            "filtered_sequence": catchup["filtered_sequence"], "clock_source_ros_ns": catchup["message_source_ros_ns"],
            "recorder_timestamp_ns": catchup["recorder_timestamp_ns"],
            "recorder_to_recorder_delta_ns": catchup["recorder_timestamp_ns"] - event["recorder_timestamp_ns"]}
    selected = set()
    for row in rows:
        source = row.get("message_source_ros_ns")
        if source is not None and SOURCE_WINDOW_NS[0] <= source <= SOURCE_WINDOW_NS[1]:
            selected.add(row["filtered_sequence"])
    for event in [*events, *anomalies]:
        start, end = max(0, event["sequence"] - CONTEXT), min(len(rows), event["sequence"] + CONTEXT + 1)
        selected.update(range(start, end))
    selected_counts = Counter(event["kind"] for event in anomalies)
    expected_selection_counts = {
        key: report.get("failures", {}).get(key, 0)
        for key, report in (("diagnostic_delivery_outside_clock_contract", source_report),
                            ("odometry_delivery_outside_source_freshness", source_report),
                            ("phase_source_time_stale_or_future", native_report))}
    selection_counts_match = all(selected_counts[key] == count for key, count in expected_selection_counts.items())
    pins_after = {name: small_pin(trial / name) for name in relative_small}
    stats_after = {name: file_stat(bag / name) for name in archives}
    unchanged = pins_before == pins_after and stats_before == stats_after
    require(unchanged, "Protected original input changed during extraction")
    summary = {
        "schema_version": 1, "kind": "READ_ONLY_CLOCK_ORDER_EXTRACTION_NOT_TRIAL_REEVALUATION",
        "created_utc": datetime.now(timezone.utc).isoformat(), "root": str(root), "trial": str(trial),
        "extractor": small_pin(Path(__file__).resolve()), "native_traversals": 1,
        "time_domains": {"message_source_ros_ns": "MESSAGE_SOURCE_OR_PRODUCER_ROS_CLOCK",
                         "latest_recorded_clock": "LAST_CLOCK_PAYLOAD_IN_UNCHANGED_NATIVE_READER_ORDER",
                         "recorder_timestamp_ns": "ORIGINAL_RECORDER_SYSTEM_TIMESTAMP_NOT_SIM_TIME",
                         "phase_producer_monotonic_ns": "PRODUCER_MONOTONIC_WALL_CLOCK_NOT_RECORDER_CLOCK"},
        "time_rules": "Only subtract values in the same stated domain; never subtract recorder timestamps from ROS/source stamps, interpolate, sort, fit, or backfill clocks",
        "topic_counts": dict(counts), "expected_topic_counts_from_original_integrity": expected,
        "topic_counts_match": counts_match, "decode_errors": decode_errors,
        "native_order_sha256": native_digest.hexdigest(), "sqlite_order_check": sql_check,
        "original_report_anomaly_counts_for_selection_crosscheck": expected_selection_counts,
        "selected_anomaly_counts": dict(selected_counts),
        "selected_anomaly_counts_match_original_report": selection_counts_match,
        "anomalies": anomalies, "source_or_file_order_changes": events,
        "window": {"source_range_ns": list(SOURCE_WINDOW_NS), "context_filtered_records_each_side": CONTEXT,
                   "records": len(selected), "all_clock_records": len(clock_rows), "all_phase_records": len(phase_rows)},
        "original_report_status_unchanged": {"source_clock": source_report.get("evaluation_status"),
                                             "native_startup": native_report.get("evaluation_status")},
        "protection": {"unchanged": unchanged, "small_inputs_before": pins_before, "small_inputs_after": pins_after,
                       "archive_stats_before": stats_before, "archive_stats_after": stats_after,
                       "archived_payload_sha256_provenance": {name: item["sha256"] for name, item in archives.items()},
                       "scope": "Small metadata/reports freshly hashed before and after. Archive size/mtime/ctime/device/inode checked before/after. Payload hashes are original bag_integrity provenance, not recomputed. Source compressed files are only copied to disposable cache"},
        "interpretation": "A matching SQLite/native byte order rules out an extractor reordering artifact. Negative same-domain clock differences then exist in stored recorder order; DDS callback backlog versus producer/clock scheduling still requires runtime timing evidence. This extraction creates no PASS/FAIL verdict",
    }
    output.mkdir()
    artifacts = {}
    for name, items in (("window.jsonl", (rows[index] for index in sorted(selected))),
                        ("clock_all.jsonl", iter(clock_rows)), ("phase_all.jsonl", iter(phase_rows))):
        digest, size = hashlib.sha256(), 0
        with (output / name).open("xb") as stream:
            for item in items:
                line = json_bytes(item) + b"\n"
                stream.write(line)
                digest.update(line)
                size += len(line)
        artifacts[name] = {"bytes": size, "sha256": digest.hexdigest()}
    summary["outputs"] = artifacts
    with (output / "summary.json").open("xb") as stream:
        stream.write(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n")
    print(json.dumps({"output": str(output), "counts_match": counts_match,
                      "native_sql_order_match": sql_check["matches_native_timestamp_topic_cdr_order"],
                      "selected_anomalies": dict(selected_counts), "original_inputs_unchanged": unchanged}, ensure_ascii=False))
    return 0 if (counts_match and not decode_errors and selection_counts_match
                 and sql_check["matches_native_timestamp_topic_cdr_order"]) else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Original frozen Linux source root")
    parser.add_argument("--trial", type=Path, required=True, help="Closed original trial inside root/results")
    parser.add_argument("--output", type=Path, required=True, help="Fresh external output directory")
    parser.add_argument("--cache-parent", type=Path, help="Existing external directory with at least 2.7 GiB free")
    args = parser.parse_args(argv)
    try:
        return export(args)
    except Exception as error:
        print(f"Extraction failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
