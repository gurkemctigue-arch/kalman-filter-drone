"""Diagnose scalar source/arrival events; telemetry needs no ROS or bag packages.

Original BAG --output ... --window-s ... remains supported. Telemetry sequence
is zero-based physical JSONL line order, independent of bag record_sequence.
Explicit time/sequence bounds are inclusive and intersect in original order.
"""

import argparse
from bisect import bisect_left
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from typing import Any


TIME_FIELDS = ("time_s", "stamp_s", "acquisition_s", "output_s", "completed_s", "measurement_processing_s",
               "output_publication_s", "image_stamp_s", "output_measurement_source_s")
STATE_FIELDS = ("state", "track_id", "target_uuid", "prediction_age_s", "position_m", "velocity_mps")
REFERENCE_FIELDS = ("reference_valid", "reference_reason", "reference_kind", "support_count", "heading_source",
                    "candidate_id", "raw_position_world_m", "reference_covariance", "geometry")
FUSION_FIELDS = ("fusion_accepted", "fusion_reason", "fusion")
OUTPUT_FIELDS = ("output_s", "output_publication_s", "valid", "output_surface_status", "output_target_uuid",
                 "output_track_id", "output_measurement_source_s", "output_state", "output_position_world_m",
                 "output_velocity_world_mps", "measurement_age_s", "state_reason")


def picked(value, names):
    return {name: value[name] for name in names if name in value}


def finite_number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite JSON number")
    return float(value)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + token)))


class Window:
    def __init__(self, start=None, end=None, sequence_start=None, sequence_end=None, window_s=5.):
        for name, value in (("source start", start), ("source end", end), ("window-s", window_s)):
            if value is not None:
                finite_number(value, name)
        if window_s <= 0 or start is not None and end is not None and start > end:
            raise ValueError("Require positive window-s and source start <= end")
        for value in (sequence_start, sequence_end):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("Sequence bounds must be nonnegative integers")
        if sequence_start is not None and sequence_end is not None and sequence_start > sequence_end:
            raise ValueError("Require sequence start <= end")
        self.start, self.end = start, end
        self.sequence_start, self.sequence_end, self.window_s = sequence_start, sequence_end, window_s
        self.default_follow = all(value is None for value in (start, end, sequence_start, sequence_end))
        self.follow = None

    def note_follow(self, event):
        if self.follow is None and event["kind"] in {"phase", "telemetry"} and event.get("phase") == "FOLLOW":
            self.follow = event["time_s"]
            if self.default_follow:
                self.start, self.end = self.follow - 1., self.follow + self.window_s

    def contains(self, row):
        sequence, time_s = row["record_sequence"], row["window_time_s"]
        return ((self.sequence_start is None or sequence >= self.sequence_start)
                and (self.sequence_end is None or sequence <= self.sequence_end)
                and (self.start is None or time_s is not None and time_s >= self.start)
                and (self.end is None or time_s is not None and time_s <= self.end))

    def description(self):
        return {"source_time_window_s": [self.start, self.end],
                "sequence_window_inclusive": [self.sequence_start, self.sequence_end],
                "selection": "INCLUSIVE_INTERSECTION_IN_ORIGINAL_RECORD_ORDER",
                "unstamped_event_policy": "Arrival ROS clock only, explicitly marked; never invented acquisition time",
                "default_first_follow_window": self.default_follow}


class CausalRows:
    def __init__(self, window, sequence_kind):
        self.window, self.sequence_kind = window, sequence_kind
        self.measurements = {}
        self.selected, self.before_follow = [], []
        self.latest = {}
        self.context_before_window = None
        self.counts = Counter()

    def append(self, event, sequence, *, bag_receive=False):
        kind, arrival = event["kind"], event.get("time_s")
        self.window.note_follow(event)
        source_field = ("output_s" if kind in {"navigation_diagnostics", "tracks"} else
                        "image_stamp_s" if kind.endswith("selection_requested") else "stamp_s")
        source = event.get(source_field)
        # acquisition_s is a retained measurement stamp in timer diagnostics;
        # it must not replace the source timestamp of the new output event.
        row = {"record_sequence": sequence, "sequence_kind": self.sequence_kind, "kind": kind,
               "source_s": source, "source_field": source_field if source is not None else None,
               "received_s": arrival,
               "received_time_kind": "LATEST_RECORDED_BAG_CLOCK_APPROXIMATION" if bag_receive else "MONITOR_CALLBACK_ROS_CLOCK",
               "window_time_s": source if source is not None else arrival,
               "window_time_basis": "MESSAGE_SOURCE_OR_OUTPUT" if source is not None else "ARRIVAL_ONLY_NO_MESSAGE_SOURCE",
               "source_to_receive_s": arrival - source if arrival is not None and source is not None else None,
               "identity": picked(event, ("target_uuid", "track_id", "target_track_id", "output_target_uuid", "output_track_id")),
               "latest_arrived_records": dict(self.latest)}
        if kind == "navigation_diagnostics":
            fields = ("acquisition_s", "measurement_processing_s", "target_uuid", "track_id", "candidate_id")
            key_fields = {name: event.get(name) for name in fields}
            key = tuple(key_fields.values())
            known = key[0] is not None and key[1] is not None
            first = self.measurements.get(key) if known else None
            if known and first is None:
                self.measurements[key] = sequence
            row["navigation"] = {"reference": picked(event, REFERENCE_FIELDS), "fusion": picked(event, FUSION_FIELDS),
                                 "state": picked(event, OUTPUT_FIELDS), "measurement_key": key_fields,
                                 "measurement_key_complete": known, "first_seen_record_sequence": first if first is not None else sequence if known else None,
                                 "cached_measurement_diagnostics": first is not None,
                                 "new_reference_evaluation": known and first is None,
                                 "new_accepted_measurement": known and first is None and event.get("reference_valid") is True
                                     and event.get("fusion_accepted") is True}
        elif kind in {"target_state", "navigation_state"}:
            row["state"] = picked(event, STATE_FIELDS)
            row["source_time_note"] = "State header/output stamp; not independently asserted to be a fresh measurement"
        elif kind == "detection":
            row["detector"] = picked(event, ("stamp_s", "completed_s", "submitted_s", "worker_started_s", "rgb_received_s",
                "depth_received_s", "depth_stamp_s", "tracking_active", "image_size", "class_name", "navigation_enabled",
                "navigation_ground_sample_count", "navigation_overlap_pair_count", "navigation_incomplete_overlap_pair_count", "detections"))
        elif kind == "control_status":
            row["controller"] = picked(event, ("lifecycle", "reason", "track_id", "measurement_age_s"))
        elif "selection" in kind:
            row["selection"] = picked(event, ("target_uuid", "track_id", "source", "rule", "image_stamp_s", "bbox", "action"))
        elif kind == "tracks":
            row["tracks"] = picked(event, ("acquisition_s", "output_s", "target_uuid", "target_track_id", "target_status",
                "projected", "associations", "ambiguous_track_ids", "ambiguous_detection_indices", "tracks"))
        else:
            row["event"] = picked(event, ("phase", "detail", "reason", "state", "position", "velocity", "age_s"))
        self.counts[kind] += 1
        previous = dict(self.latest)
        self.latest[kind] = {"record_sequence": sequence, "source_s": source, "received_s": arrival,
                             **row["identity"], **picked(event, ("reason", "phase", "state", "state_reason"))}
        if self.window.default_follow and self.window.follow is None:
            # Compact scalar rows only; the input is still read exactly once.
            self.before_follow.append((row, previous))
        else:
            if self.before_follow:
                for item, context in self.before_follow:
                    self._select(item, context)
                self.before_follow.clear()
            self._select(row, previous)

    def _select(self, row, previous):
        if self.window.contains(row):
            if self.context_before_window is None:
                self.context_before_window = previous
            self.selected.append(row)

    def report(self):
        if self.window.default_follow and self.window.follow is None:
            raise ValueError("No FOLLOW event; supply an explicit source-time or sequence window")
        nav = [row["navigation"] for row in self.selected if "navigation" in row]
        return {"follow_start_s": self.window.follow, "window": [self.window.start, self.window.end],
                "window_selection": self.window.description(), "causal_table": self.selected,
                "context_before_first_selected_record": self.context_before_window or {},
                "input_kind_counts": dict(self.counts),
                "window_counts": {"records": len(self.selected), "navigation_publications": len(nav),
                    "distinct_navigation_reference_evaluations": sum(item["new_reference_evaluation"] for item in nav),
                    "new_accepted_navigation_measurements": sum(item["new_accepted_measurement"] for item in nav),
                    "cached_navigation_publications": sum(item["cached_measurement_diagnostics"] for item in nav)},
                "notes": ["Original record order is retained; this table does not infer callback order from source stamps.",
                    "A cached navigation reference/fusion diagnosis is not a new measurement; every timer output remains a separate state event.",
                    "Context links mean previously arrived records, not proven causal or same-frame associations."]}


def diagnose_telemetry(path, window):
    """Read one JSONL pass, with independent zero-based physical line sequence."""
    table = CausalRows(window, "TELEMETRY_JSONL_ZERO_BASED_PHYSICAL_LINE_NOT_BAG_SEQUENCE")
    before = path.stat()
    hasher, byte_count, count = hashlib.sha256(), 0, 0
    with path.open("rb") as stream:
        for sequence, raw in enumerate(stream):
            count += 1
            byte_count += len(raw)
            hasher.update(raw)
            try:
                value = strict_json(raw.decode("utf-8-sig" if sequence == 0 else "utf-8"))
                if not isinstance(value, dict) or not isinstance(value.get("kind"), str) or not value["kind"]:
                    raise ValueError("Each telemetry line needs an object with a nonempty kind")
                finite_number(value.get("time_s"), "time_s")
                for name in TIME_FIELDS:
                    if value.get(name) is not None:
                        finite_number(value[name], name)
                if value["kind"] == "navigation_diagnostics":
                    for name in ("target_uuid", "track_id", "candidate_id"):
                        if isinstance(value.get(name), (dict, list)):
                            raise ValueError("Invalid navigation measurement key: " + name)
                if value["kind"] == "detection" and not isinstance(value.get("detections", []), list):
                    raise ValueError("Detector detections must be an array")
                table.append(value, sequence)
            except (UnicodeError, ValueError, TypeError) as error:
                raise ValueError(f"{path}: telemetry line {sequence + 1}: {error}") from error
    after = path.stat()
    if not count:
        raise ValueError("Telemetry input is empty")
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Telemetry input changed during its single read; use a completed recording")
    report = table.report()
    report.update(input_mode="telemetry", inputs={"telemetry": str(path.resolve()), "sha256": hasher.hexdigest(),
        "bytes_read": byte_count, "records_read": count, "read_passes": 1,
        "sequence_note": "Zero-based physical JSONL line order, independent of bag record_sequence; blank/malformed lines fail"})
    return report


def diagnose_bag(bag, window):
    # ROS packages are imported only inside read_rosbag, never in telemetry mode.
    import evaluate_stage1_flight as evaluation
    evaluation.TOPICS = ("/clock", "/tracking/state", "/tracking/observations", "/tracking/status",
                         "/tracking/detection_diagnostics", "/tracking/flight_phase", "/tf", "/tf_static",
                         "/tracking/navigation_state", "/tracking/navigation_diagnostics", "/tracking/tracks", "/tracking/selection")
    records, metadata = evaluation.read_rosbag(bag)
    records = evaluation.with_record_sequence(records)
    follow = next((row.time_s for row in records if row.topic == "/tracking/flight_phase"
                   and row.message.data.split(":", 1)[0] == "FOLLOW"), None)
    window.follow = follow
    if window.default_follow:
        if follow is None:
            raise ValueError("No FOLLOW event; supply an explicit source-time or sequence window")
        window.start, window.end = follow - 1., follow + window.window_s
    table = CausalRows(window, "BAG_FILTERED_READER_RECORD_SEQUENCE")
    states, observations, diagnostics, tf_rows = [], [], [], []
    last_state, last_rejected = None, None
    for row in records:
        message = row.message
        receive = row.received_sim_s
        sequence_ok = ((window.sequence_start is None or row.record_sequence >= window.sequence_start)
                       and (window.sequence_end is None or row.record_sequence <= window.sequence_end))
        selected = lambda time_s: sequence_ok and (window.start is None or time_s >= window.start) and (window.end is None or time_s <= window.end)
        event = {"time_s": receive, "kind": "other"}
        if row.topic in {"/tracking/state", "/tracking/navigation_state"}:
            event.update(kind="target_state" if row.topic == "/tracking/state" else "navigation_state", stamp_s=row.time_s,
                         **{name: getattr(message, name, None) for name in ("state", "track_id", "target_uuid", "prediction_age_s")},
                         position_m=evaluation.vector(message.position_m), velocity_mps=evaluation.vector(message.velocity_mps))
        elif row.topic in {"/tracking/detection_diagnostics", "/tracking/navigation_diagnostics", "/tracking/tracks"}:
            event.update(strict_json(message.data))
            event["kind"] = {"/tracking/detection_diagnostics": "detection", "/tracking/navigation_diagnostics": "navigation_diagnostics",
                             "/tracking/tracks": "tracks"}[row.topic]
        elif row.topic == "/tracking/flight_phase":
            event.update(kind="phase", phase=message.data.split(":", 1)[0], detail=message.data)
        elif row.topic == "/tracking/status":
            event.update(kind="control_status", **{name: getattr(message, name, None) for name in ("lifecycle", "reason", "track_id")},
                         measurement_age_s=getattr(message, "time_since_measurement_s", None))
        elif row.topic == "/tracking/selection":
            event.update(kind="selection", stamp_s=row.time_s,
                         **{name: getattr(message, name, None) for name in ("target_uuid", "track_id", "source", "action")})
        elif row.topic == "/tracking/observations":
            event.update(kind="observation", stamp_s=row.time_s, depth_m=float(message.depth_m), valid=bool(message.depth_valid))
        if event["kind"] != "other":
            table.append(event, row.record_sequence, bag_receive=True)
        if row.topic in {"/tf", "/tf_static"}:
            for transform in message.transforms:
                tf_rows.append({"topic": row.topic, "stamp_s": evaluation.stamp_s(transform.header.stamp),
                                "received_s": receive, "parent": transform.header.frame_id,
                                "child": transform.child_frame_id,
                                "translation": evaluation.vector(transform.transform.translation),
                                "rotation_xyzw": [getattr(transform.transform.rotation, axis) for axis in "xyzw"]})
        if row.topic == "/tracking/state":
            operational = max(row.time_s, receive) if receive is not None else row.time_s
            if selected(operational if window.default_follow else row.time_s):
                rejected = int(message.rejected_measurements)
                if message.state != last_state or message.state == 1 or rejected != last_rejected:
                    states.append({"acquisition_or_output_s": row.time_s, "received_s": receive,
                                   "state": int(message.state), "track_id": int(message.track_id),
                                   "prediction_age_s": float(message.prediction_age_s), "rejected": rejected,
                                   "position_map": evaluation.vector(message.position_m),
                                   "velocity_map": evaluation.vector(message.velocity_mps)})
                last_state, last_rejected = message.state, rejected
        elif row.topic == "/tracking/observations" and selected(row.time_s):
            observations.append({"acquired_s": row.time_s, "received_s": receive,
                                 "receive_lag_s": receive - row.time_s if receive is not None else None,
                                 "depth_valid": bool(message.depth_valid), "depth_m": float(message.depth_m),
                                 "depth_std_m": float(message.depth_std_m), "valid_ratio": float(message.depth_valid_ratio),
                                 "confidence": float(message.confidence),
                                 "position_camera": evaluation.vector(message.position_camera_m),
                                 "bbox": [float(message.bbox_x_min_px), float(message.bbox_y_min_px),
                                          float(message.bbox_x_max_px), float(message.bbox_y_max_px)]})
        elif row.topic == "/tracking/detection_diagnostics":
            payload = json.loads(message.data)
            if selected(payload["stamp_s"]):
                diagnostics.append({**payload, "received_s": receive})
    base_tf = sorted([row for row in tf_rows if row["child"] == "base_link"], key=lambda row: row["stamp_s"])
    base_times = [row["stamp_s"] for row in base_tf]
    for observation in observations:
        index = bisect_left(base_times, observation["acquired_s"])
        observation["tf_source_bracket_s"] = base_times[max(index - 1, 0):index + 1]
        delivered = [row for row in base_tf if row["received_s"] is not None
                     and observation["received_s"] is not None and row["received_s"] <= observation["received_s"]]
        observation["latest_tf_stamp_at_recorded_observation_receive_s"] = delivered[-1]["stamp_s"] if delivered else None
    report = {**table.report(), "input_mode": "bag", "follow_start_s": follow, "window": [window.start, window.end], "inputs": metadata,
              "topic_counts": dict(Counter(row.topic for row in records)), "states": states,
              "observations": observations, "diagnostics": diagnostics,
              "tf_summary": {"frames": dict(Counter(row["parent"] + "->" + row["child"] for row in tf_rows)),
                             "static": [row for row in tf_rows if row["topic"] == "/tf_static"],
                             "max_base_tf_gap_s": max((right - left for left, right in zip(base_times, base_times[1:])), default=None)},
              "notes": ["Message receive time is the latest bag /clock and has clock-sample uncertainty; no wall/sim time substitution.",
                        "TF availability at bag receipt approximates recorder ordering, not the estimator's callback receipt ordering."]}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path, nargs="?", help="Original bag mode; mutually exclusive with --telemetry")
    parser.add_argument("--telemetry", type=Path, help="Read telemetry.jsonl once using only Python standard library")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-s", type=float, default=5.)
    parser.add_argument("--source-start-s", "--start-s", type=float)
    parser.add_argument("--source-end-s", "--end-s", type=float)
    parser.add_argument("--sequence-start", "--record-sequence-start", type=int)
    parser.add_argument("--sequence-end", "--record-sequence-end", type=int)
    args = parser.parse_args(argv)
    if (args.bag is None) == (args.telemetry is None):
        parser.error("Provide exactly one BAG or --telemetry input")
    try:
        window = Window(args.source_start_s, args.source_end_s, args.sequence_start, args.sequence_end, args.window_s)
        source = args.telemetry or args.bag
        if source.resolve() == args.output.resolve():
            raise ValueError("Output must not overwrite the input")
        report = diagnose_telemetry(source, window) if args.telemetry else diagnose_bag(source, window)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({"report": str(args.output), "input_mode": report["input_mode"],
                      "follow_start_s": report["follow_start_s"], "window": report["window_selection"],
                      "window_counts": report["window_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    main()
