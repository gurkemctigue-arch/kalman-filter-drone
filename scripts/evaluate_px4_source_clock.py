"""Audit recorded PX4 source_sim -> adapter receipt -> odometry delivery.

The pure evaluate(records, config) API needs no ROS installation. The CLI reads
only /clock, raw PX4 odometry, adapter timing and adapted odometry. No truth,
image, receipt-offset fit, or target trajectory participates in this audit.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from numbers import Integral
from pathlib import Path
import sys

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_px4_adapter"))
import evaluate_stage1_flight as bag_tools
from evaluate_stage1_flight import Record, stamp_s, summary, vector
from uav_tracking_px4_adapter.adapter_node import px4_odometry_to_enu

RAW_TOPIC = "/fmu/out/vehicle_odometry"
TIMING_TOPIC = "/vehicle/odometry_timing"
ODOMETRY_TOPIC = "/vehicle/odometry"
TOPICS = ("/clock", RAW_TOPIC, TIMING_TOPIC, ODOMETRY_TOPIC)
STAMP_TOLERANCE_S = 1e-7  # PX4 microseconds are exact; allow float serialization.
DELIVERY_QUANTIZATION_S = .05  # latest recorded /clock is a lower-bound estimate.
MIN_MATCHED_SAMPLES = 3


def _finite(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _source_ns(value):
    return int(value) * 1000 if isinstance(value, Integral) and not isinstance(value, bool) and 0 < value <= (2**63-1)//1000 else None


def _seconds_ns(value):
    number = _finite(value)
    return round(number * 1e9) if number is not None and abs(number) < 9e9 else None


def _same(a, b, tolerance=STAMP_TOLERANCE_S):
    return a is not None and b is not None and abs(a-b) <= tolerance


def _validate_configuration(config):
    if config.get("px4_time_mode") != "source_sim" or config.get("odometry_timestamp_mode") != "source_sim":
        raise ValueError("Recorded run_config and adapter parameters must both declare source_sim")
    if config.get("use_sim_time") is not True or config.get("uxrce_dds_synct") != 0 or isinstance(config.get("uxrce_dds_synct"), bool):
        raise ValueError("source_sim requires recorded use_sim_time=true and explicit UXRCE_DDS_SYNCT=0 startup evidence")
    for key, expected in (("odometry_source_max_age_s", .50), ("odometry_source_max_future_s", .05)):
        value = _finite(config.get(key))
        if value is None or not math.isclose(value, expected, abs_tol=1e-9):
            raise ValueError("Original source-clock bound must be explicitly recorded and unchanged: " + key)
    for key, expected in (("vehicle_odometry_topic", RAW_TOPIC), ("vehicle_odom_topic", ODOMETRY_TOPIC), ("odometry_timing_topic", TIMING_TOPIC)):
        if config.get(key) != expected:
            raise ValueError("Explicit recorded adapter topic is required: " + key)


def recorded_configuration(trial):
    """Historical run/settings/startup declarations only; no current defaults."""
    trial = Path(trial)
    paths = {"run_config":trial / "run_config.json", "runtime_parameters":trial / "configuration/runtime_parameters.yaml",
             "px4_parameters":trial / "configuration/px4_parameters.json"}
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("run_config.json, recorded runtime_parameters.yaml and px4_parameters.json are required")
    run = json.loads(paths["run_config"].read_text(encoding="utf-8"))
    document = yaml.safe_load(paths["runtime_parameters"].read_text(encoding="utf-8"))
    try:
        adapter = document["uav_tracking_px4_adapter"]["ros__parameters"]
        overrides = json.loads(paths["px4_parameters"].read_text(encoding="utf-8"))["explicit_environment_overrides"]
    except (KeyError, TypeError) as error:
        raise ValueError("Missing saved adapter/source-clock startup declaration") from error
    config = {"px4_time_mode":run.get("px4_time_mode"), **adapter,
              "uxrce_dds_synct":overrides.get("UXRCE_DDS_SYNCT")}
    _validate_configuration(config)
    config["recorded_configuration_evidence"] = {name:{"path":str(path), "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
                                                 for name, path in paths.items()}
    return config


def evaluation_source_provenance():
    script = Path(__file__).resolve()
    adapter_root = ROOT / "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter"
    dependencies = [script.parent / "evaluate_stage1_flight.py",
                    *[adapter_root / name for name in ("adapter_node.py", "source_clock.py", "frame_guard.py")]]
    return {"script":str(script), "script_sha256":hashlib.sha256(script.read_bytes()).hexdigest(),
            "dependencies":{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in dependencies},
            "scope":"Actual offline evaluator hashes; separate from flight-frozen code. Clock decisions are checked independently, not replayed through the online source-clock class."}


def _odom_matches(raw, odometry):
    try:
        position, velocity, quaternion = px4_odometry_to_enu(raw)
        q = odometry.pose.pose.orientation
        measured_q = np.asarray([q.x, q.y, q.z, q.w], dtype=float)
        if not np.isfinite(measured_q).all() or abs(np.linalg.norm(measured_q)-1) > 1e-5:
            return False
        return (odometry.header.frame_id == "map" and odometry.child_frame_id == "base_link"
                and np.allclose(vector(odometry.pose.pose.position), position, atol=1e-6, rtol=0)
                and np.allclose(vector(odometry.twist.twist.linear), velocity, atol=1e-6, rtol=0)
                and abs(float(measured_q @ quaternion)) >= 1-1e-8)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False


def _gaps(deliveries, start, end, limit):
    times = sorted(t for t in deliveries if start <= t <= end)
    edges = [start, *times, end]
    intervals = [{"start_s":a, "end_s":b, "duration_s":b-a} for a, b in zip(edges, edges[1:]) if b-a > limit+1e-9]
    return {"max_gap_s":max((b-a for a,b in zip(edges, edges[1:])), default=None),
            "threshold_s":limit, "violations":intervals, "tail_s":end-times[-1] if times else end-start}


def evaluate(records, config):
    """Cross-check complete recorded messages, with /clock rows retained.

    Each Record requires received_sim_s from the latest *recorded* /clock;
    record_sequence preserves delivery order. Diagnostic receipt_ros_s is the
    adapter callback clock, distinct from recorder delivery. No missing clock
    or diagnostic is reconstructed from a message header or source fit.
    """
    _validate_configuration(config)
    rows = bag_tools.with_record_sequence(list(records))
    rows.sort(key=lambda row:row.record_sequence)
    streams = defaultdict(list)
    failures, incomplete, reasons, clock_failures, frame_failures = Counter(), Counter(), Counter(), Counter(), Counter()
    clocks, previous_clock = [], None
    for row in rows:
        if row.topic == "/clock":
            try:
                value = _finite(stamp_s(row.message.clock))
            except (AttributeError, TypeError, ValueError):
                value = None
            if value is None:
                incomplete["malformed_recorded_clock"] += 1
            else:
                clocks.append(value)
                if previous_clock is not None and value < previous_clock-1e-9:
                    failures["recorded_ros_clock_regression"] += 1
                    clock_failures["recorded_ros_clock_regression"] += 1
                previous_clock = value
        elif row.topic in TOPICS:
            streams[row.topic].append(row)
    for topic in TOPICS:
        if topic == "/clock":
            if not clocks:
                incomplete["missing_recorded_clock"] += 1
        elif not streams[topic]:
            incomplete["missing_stream:"+topic] += 1

    def delivery(row):
        value = _finite(row.received_sim_s)
        if value is None:
            incomplete["missing_recorded_delivery_clock:"+row.topic] += 1
        return value

    raw_by_key, odom_by_header = defaultdict(list), defaultdict(list)
    raw_delivery, odom_delivery = {}, {}
    for index, row in enumerate(streams[RAW_TOPIC]):
        raw_by_key[(_source_ns(getattr(row.message, "timestamp_sample", None)), _source_ns(getattr(row.message, "timestamp", None)))].append(index)
        raw_delivery[index] = delivery(row)
    for index, row in enumerate(streams[ODOMETRY_TOPIC]):
        try:
            stamp = _seconds_ns(stamp_s(row.message.header.stamp))
        except (AttributeError, TypeError, ValueError, OverflowError):
            stamp = None
        if stamp is None:
            incomplete["malformed_odometry_header"] += 1
        else:
            odom_by_header[stamp].append(index)
        odom_delivery[index] = delivery(row)
    used_raw, used_odom = set(), set()
    frames, accepted_deliveries = [], []
    metrics = defaultdict(list)
    last_receipt, last_sample, last_publication, latch = None, None, None, None
    frame_counter, frame_latch, frame_lock_seen = None, False, False
    matched, accepted, rejected = 0, 0, 0
    for row in streams[TIMING_TOPIC]:
        delivered = delivery(row)
        try:
            diagnostic = json.loads(row.message.data)
            if not isinstance(diagnostic, dict):
                raise ValueError("not an object")
        except (AttributeError, TypeError, ValueError):
            incomplete["malformed_timing_diagnostic"] += 1
            continue
        receipt = _finite(diagnostic.get("receipt_ros_s"))
        sample = _seconds_ns(diagnostic.get("source_sample_s"))
        publication = _seconds_ns(diagnostic.get("source_publication_s"))
        claim = diagnostic.get("accepted")
        frame = {"record_sequence":row.record_sequence, "source_sample_s":sample/1e9 if sample is not None else None,
                 "source_publication_s":publication/1e9 if publication is not None else None,
                 "receipt_ros_s":receipt, "diagnostic_delivery_s":delivered,
                 "claimed_accepted":claim, "claimed_reason":diagnostic.get("reason"),
                 "raw_matched":False, "odometry_matched":False}
        frames.append(frame)
        if diagnostic.get("schema_version") != 1 or diagnostic.get("mode") != "source_sim" or not isinstance(claim, bool) or receipt is None:
            failures["invalid_timing_diagnostic_contract"] += 1
            clock_failures["invalid_timing_diagnostic_contract"] += 1
            continue
        if not _same(_finite(diagnostic.get("output_s")), receipt):
            failures["diagnostic_output_not_receipt_clock"] += 1
            clock_failures["diagnostic_output_not_receipt_clock"] += 1
        if delivered is not None:
            latency = delivered-receipt
            metrics["diagnostic_receipt_to_recorder_s"].append(latency)
            if latency < -DELIVERY_QUANTIZATION_S-1e-9 or latency > config["odometry_source_max_age_s"]+1e-9:
                failures["diagnostic_delivery_outside_clock_contract"] += 1
        available = [index for index in raw_by_key.get((sample, publication), []) if index not in used_raw]
        if not available:
            incomplete["diagnostic_without_matching_raw_px4"] += 1
            continue
        # Exact source timestamp pair establishes correspondence; receipt is
        # used only to distinguish repeat deliveries of the same pair.
        raw_index = min(available, key=lambda index:abs(raw_delivery[index]-receipt) if raw_delivery[index] is not None else float("inf"))
        used_raw.add(raw_index)
        raw = streams[RAW_TOPIC][raw_index]
        frame["raw_matched"] = True
        frame["raw_record_sequence"] = raw.record_sequence
        frame["raw_delivery_s"] = raw_delivery[raw_index]
        if raw_delivery[raw_index] is not None and abs(raw_delivery[raw_index]-receipt) > config["odometry_source_max_age_s"]+DELIVERY_QUANTIZATION_S:
            failures["raw_diagnostic_delivery_separation"] += 1
        # Independent source-clock checks, including the online restart latch.
        receipt_ns = round(receipt*1e9)
        if receipt_ns <= 0:
            expected = "ros_clock_not_started"
        elif latch:
            expected = latch
        elif last_receipt is not None and receipt_ns < last_receipt:
            expected = latch = "ros_clock_regression_restart_required"
        else:
            last_receipt = receipt_ns
            if sample is None or publication is None or sample <= 0 or publication <= 0:
                expected = "invalid_source_timestamp"
            elif sample > publication:
                expected = "sample_after_publication"
            elif last_sample is not None and (sample < last_sample or publication < last_publication):
                expected = latch = "source_clock_regression_restart_required"
            elif sample == last_sample:
                expected = "duplicate_source_sample"
            elif receipt_ns-sample < -round(config["odometry_source_max_future_s"]*1e9) or publication-receipt_ns > round(config["odometry_source_max_future_s"]*1e9):
                expected = "future_or_wrong_domain_source_timestamp"
            elif receipt_ns-sample > round(config["odometry_source_max_age_s"]*1e9):
                expected = "stale_or_wrong_domain_source_timestamp"
            else:
                expected = "validated_source_stamp"
                last_sample, last_publication = sample, publication
        source_valid = expected == "validated_source_stamp"
        frame["independent_reason"] = expected
        reasons[expected] += 1
        if expected not in {"validated_source_stamp", "duplicate_source_sample", "ros_clock_not_started"}:
            failures["source_rejected:"+expected] += 1
            clock_failures["source_rejected:"+expected] += 1
        if diagnostic.get("source_time_valid") is not source_valid:
            failures["diagnostic_source_validity_disagrees"] += 1
            clock_failures["diagnostic_source_validity_disagrees"] += 1
        locked = diagnostic.get("frame_locked")
        counter = getattr(raw.message, "reset_counter", None)
        if not isinstance(locked, bool) or diagnostic.get("reset_counter") != counter:
            incomplete["missing_or_inconsistent_frame_guard_evidence"] += 1
        if frame_lock_seen and locked is False:
            frame_failures["vehicle_frame_lock_was_cleared"] += 1
        frame_lock_seen = frame_lock_seen or locked is True
        frame_valid = True
        frame_reason = "vehicle_frame_valid"
        if source_valid:
            if frame_latch:
                frame_valid, frame_reason = False, "vehicle_frame_reset_restart_required"
            elif isinstance(counter, bool) or not isinstance(counter, Integral) or not 0 <= counter <= 255:
                frame_valid, frame_reason = False, "invalid_vehicle_reset_counter"
            elif frame_counter is not None and counter != frame_counter and locked is True:
                frame_valid, frame_reason, frame_latch = False, "vehicle_frame_reset_restart_required", True
            else:
                frame_counter = int(counter)
            if not frame_valid:
                frame_failures[frame_reason] += 1
            if diagnostic.get("vehicle_frame_valid") is not frame_valid or diagnostic.get("vehicle_frame_reason") != frame_reason:
                frame_failures["diagnostic_vehicle_frame_claim_disagrees"] += 1
        expected_accepted = source_valid and frame_valid
        overall_reason = frame_reason if source_valid and not frame_valid else expected
        frame.update(source_time_valid=source_valid, vehicle_frame_valid=frame_valid if source_valid else None,
                     reset_counter=counter if isinstance(counter, Integral) else None, frame_locked=locked)
        if claim != expected_accepted or diagnostic.get("reason") != overall_reason:
            failures["diagnostic_disagrees_with_independent_clock_check"] += 1
        if sample is not None:
            age = receipt-sample/1e9
            metrics["source_to_adapter_receipt_s"].append(age)
            if not _same(_finite(diagnostic.get("source_to_receipt_s")), age):
                failures["diagnostic_source_age_inconsistent"] += 1
                clock_failures["diagnostic_source_age_inconsistent"] += 1
            if raw_delivery[raw_index] is not None:
                metrics["source_to_raw_recorder_s"].append(raw_delivery[raw_index]-sample/1e9)
        if sample is not None and publication is not None:
            metrics["sample_to_publication_s"].append((publication-sample)/1e9)
        header = _seconds_ns(diagnostic.get("odometry_header_s"))
        if not claim:
            rejected += 1
            if header is not None:
                failures["rejected_diagnostic_carries_header"] += 1
            continue
        accepted += 1
        if header != sample:
            failures["accepted_header_not_px4_sample_time"] += 1
        candidates = [index for index in odom_by_header.get(sample, []) if index not in used_odom]
        candidates = [index for index in candidates if _odom_matches(raw.message, streams[ODOMETRY_TOPIC][index].message)]
        if not candidates:
            incomplete["accepted_diagnostic_without_matching_adapted_odometry"] += 1
            continue
        odom_index = min(candidates, key=lambda index:abs(odom_delivery[index]-receipt) if odom_delivery[index] is not None else float("inf"))
        used_odom.add(odom_index)
        frame["odometry_matched"] = True
        frame["odometry_record_sequence"] = streams[ODOMETRY_TOPIC][odom_index].record_sequence
        odel = odom_delivery[odom_index]
        frame["odometry_delivery_s"] = odel
        if odel is not None:
            source_age = odel-sample/1e9
            metrics["source_to_odometry_recorder_s"].append(source_age)
            metrics["adapter_receipt_to_odometry_recorder_s"].append(odel-receipt)
            if source_age < -config["odometry_source_max_future_s"]-DELIVERY_QUANTIZATION_S or source_age > config["odometry_source_max_age_s"]+DELIVERY_QUANTIZATION_S:
                failures["odometry_delivery_outside_source_freshness"] += 1
            accepted_deliveries.append(odel)
        if expected_accepted and header == sample:
            matched += 1
    if len(used_raw) != len(streams[RAW_TOPIC]):
        incomplete["raw_px4_without_timing_diagnostic"] += len(streams[RAW_TOPIC])-len(used_raw)
    if len(used_odom) != len(streams[ODOMETRY_TOPIC]):
        failures["adapted_odometry_without_valid_raw_diagnostic_correspondence"] += len(streams[ODOMETRY_TOPIC])-len(used_odom)
    if matched < MIN_MATCHED_SAMPLES:
        incomplete["insufficient_independently_matched_samples"] += 1
    timed = [value for value in raw_delivery.values() if value is not None]
    start, end = (max(min(clocks), min(timed)), max(clocks)) if clocks and timed else (None, None)
    continuity = {}
    if start is not None and end is not None and end >= start:
        for name, deliveries in (("raw_px4", timed), ("matched_adapted_odometry", accepted_deliveries)):
            continuity[name] = _gaps(deliveries, start, end, config["odometry_source_max_age_s"])
            failures["delivery_loss:"+name] += len(continuity[name]["violations"])
    else:
        incomplete["missing_valid_whole_record_interval"] += 1
    failures.update(frame_failures)
    failures = +failures
    status = "FAIL" if failures else "INCOMPLETE" if incomplete else "PASS"
    clock_complete = (bool(clocks) and len(used_raw) == len(streams[RAW_TOPIC])
                      and len(frames) == len(streams[TIMING_TOPIC])
                      and all("independent_reason" in frame for frame in frames)
                      and reasons["validated_source_stamp"] >= MIN_MATCHED_SAMPLES)
    return {"schema_version":1, "evaluation_status":status, "source_clock_pass":status == "PASS",
            "clock_domain_valid":False if clock_failures else True if clock_complete else None,
            "vehicle_frame_continuity_valid":False if frame_failures else None if incomplete["missing_or_inconsistent_frame_guard_evidence"] else True if clock_complete else None,
            "configuration":config, "interval":{"start_s":start, "end_s":end, "basis":"first raw delivery through full recorded /clock end; loss tails retained"},
            "counts":{"raw_px4":len(streams[RAW_TOPIC]), "timing_diagnostics":len(streams[TIMING_TOPIC]),
                      "adapted_odometry":len(streams[ODOMETRY_TOPIC]), "claimed_accepted":accepted, "claimed_rejected":rejected,
                      "independently_matched_triplets":matched},
            "failures":dict(failures), "clock_domain_failures":dict(clock_failures), "vehicle_frame_failures":dict(frame_failures),
            "incomplete_evidence":dict(+incomplete), "independent_reason_counts":dict(reasons),
            "metrics":{key:summary(values) for key,values in metrics.items()}, "continuity":continuity, "frames":frames,
            "claim_boundary":"PASS only establishes this recorded source_sim timestamp/correspondence/continuity contract. A correct rejection of wrong-domain or regressing source clocks is reported as a failed clock trial, not a clock pass. Startup before the first raw delivery is outside the interval; all later silence through the last recorded /clock remains. Adapter receipt and recorder delivery are distinct; delivery uses latest /clock with 50ms quantization allowance. No affine offset, lag, GT or target fit is used. A near-receipt source timestamp does not independently certify hardware acquisition latency or physical pose accuracy."}


def read_records(path):
    """Preserve clock rows; lazy ROS imports and compression-safe bag reader."""
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as error:
        raise RuntimeError("Source ROS, px4_msgs and this workspace before reading the bag") from error
    rows, errors, clock = [], Counter(), None
    with bag_tools.open_bag_reader(Path(path), rosbag2_py) as (reader, metadata):
        types = {item.name:item.type for item in reader.get_all_topics_and_types() if item.name in TOPICS}
        reader.set_filter(rosbag2_py.StorageFilter(topics=list(types)))
        classes = {name:get_message(type_name) for name,type_name in types.items()}
        sequence = 0
        while reader.has_next():
            topic, data, _ = reader.read_next()
            try:
                message = deserialize_message(data, classes[topic])
                if topic == "/clock":
                    clock = stamp_s(message.clock)
                rows.append(Record(topic, clock if clock is not None else 0., message, clock, sequence))
            except Exception as error:
                errors[f"{topic}: {type(error).__name__}: {error}"] += 1
            sequence += 1
    return rows, {**metadata, "bag":str(Path(path).resolve()), "topic_types":types, "read_errors":dict(errors),
                  "scope":"Only clock/raw PX4/timing/adapted odometry, no images or truth. Latest recorded clock supplies delivery; no wall/sim subtraction."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = recorded_configuration(args.trial)
        rows, metadata = read_records(args.trial / "rosbag")
        result = evaluate(rows, config)
        if metadata["read_errors"]:
            result["source_clock_pass"] = False
            if result["evaluation_status"] == "PASS":
                result["evaluation_status"] = "INCOMPLETE"
            result["incomplete_evidence"]["bag_read_errors"] = sum(metadata["read_errors"].values())
        result["bag"] = metadata
    except (ValueError, KeyError, TypeError, FileNotFoundError) as error:
        result = {"schema_version":1, "evaluation_status":"INCOMPLETE", "source_clock_pass":False,
                  "incomplete_evidence":{"configuration_or_input_error":str(error)}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frames = result.pop("frames", [])
    sidecar = args.output.with_suffix(".frames.jsonl")
    sidecar.write_text("".join(json.dumps(row, allow_nan=False)+"\n" for row in frames), encoding="utf-8")
    result.update(trial=str(args.trial), frames_path=str(sidecar), evaluation_source=evaluation_source_provenance())
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status":result["evaluation_status"], "source_clock_pass":result["source_clock_pass"], "output":str(args.output)}))
    return 0 if result["source_clock_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
