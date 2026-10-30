#!/usr/bin/env python3
"""Supplement existing v4 JSON evidence; never run flight code or read a bag."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import platform
import sys


SCOPE = "OFFLINE_JSON_TASK_PHASE_APPENDIX_V4_NOT_A_PRIMARY_GATE"
BANDS = ("pre_follow", "follow_0_45", "follow_45_75", "after_75_recording_tail")
METRICS = ("base_link_distance_error_m", "base_link_height_error_m",
           "model_origin_distance_error_m", "model_origin_height_error_m",
           "kf_position_error_m", "kf_velocity_error_mps")
EVENT_KINDS = {"phase", "shutter", "shutter_service_result", "shutter_hold_started",
               "shutter_hold_finished", "shutter_schedule_failure",
               "initial_selection_requested", "initial_selection_confirmed",
               "explicit_reselection_requested", "explicit_reselection_confirmed"}
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_LINE_BYTES = 4 * 1024 * 1024
MAX_RETAINED_ROWS = 200000


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def require_number(value, name):
    if not number(value):
        raise ValueError("Non-finite or nonnumeric " + name)
    return float(value)


def strict_json(data):
    def reject(value):
        raise ValueError("Non-finite JSON constant: " + value)
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("Non-finite JSON number: " + value)
        return parsed
    return json.loads(data, parse_constant=reject, parse_float=finite_float)


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


class Inputs:
    """Bind complete files; JSONL is scanned without retaining unused payloads."""
    def __init__(self):
        self.bindings = {}
        self.errors = []

    def read(self, role, path, *, lines=False, select=None, required=True):
        if path is None:
            self.bindings[role] = {"path": None, "status": "MISSING" if required else "NOT_PROVIDED"}
            if required:
                self.errors.append(role + ": missing input")
            return None
        path = Path(path).resolve()
        binding = {"path": str(path), "status": "INCOMPLETE"}
        self.bindings[role] = binding
        try:
            if path.suffix.lower() != (".jsonl" if lines else ".json"):
                raise ValueError("Only explicit JSON/JSONL inputs are accepted")
            if not path.is_file():
                raise ValueError("Input file is missing")
            before = path.stat()
            digest = hashlib.sha256()
            if lines:
                result = []
                line_count = 0
                with path.open("rb") as stream:
                    while True:
                        line = stream.readline(MAX_LINE_BYTES + 1)
                        if not line:
                            break
                        digest.update(line)
                        line_count += 1
                        if len(line) > MAX_LINE_BYTES:
                            raise ValueError("JSONL line exceeds bounded record size")
                        if not line.strip():
                            continue
                        row = strict_json(line)
                        if not isinstance(row, dict):
                            raise ValueError("JSONL record is not an object")
                        chosen = select(row) if select else row
                        if chosen is not None:
                            result.append(chosen)
                            if len(result) > MAX_RETAINED_ROWS:
                                raise ValueError("Too many retained rows; analysis incomplete, no truncation")
                binding["line_count"] = line_count
                binding["retained_rows"] = len(result)
            else:
                if before.st_size > MAX_JSON_BYTES:
                    raise ValueError("JSON exceeds bounded document size")
                data = path.read_bytes()
                digest.update(data)
                result = strict_json(data)
                if not isinstance(result, dict):
                    raise ValueError("JSON document is not an object")
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Input changed during complete read")
            binding.update(status="COMPLETE", bytes=before.st_size, sha256=digest.hexdigest())
            return result
        except (OSError, ValueError, UnicodeError) as error:
            binding["error"] = str(error)
            # Retain the identity of invalid-but-existing bytes too. Hashing a
            # file to EOF does not turn an incomplete parse into valid evidence.
            try:
                if path.is_file():
                    binding.update(bytes=path.stat().st_size, sha256=file_sha(path))
            except OSError:
                pass
            self.errors.append(role + ": " + str(error))
            return None


def metrics(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {"count": 0, "rmse": None, "mean": None, "p95_absolute": None, "squared_error_sum": 0.}
    absolute = sorted(abs(value) for value in values)
    point = (len(values) - 1) * .95
    lo, hi = math.floor(point), math.ceil(point)
    energy = math.fsum(v * v for v in values)
    require_number(energy, "squared error sum")
    return {"count": len(values), "rmse": math.sqrt(energy / len(values)), "squared_error_sum": energy,
            "mean": math.fsum(values) / len(values),
            "p95_absolute": absolute[lo] + (absolute[hi] - absolute[lo]) * (point - lo)}


def band_at(timestamp, follow):
    relative = timestamp - follow
    if relative < -1e-9:
        return BANDS[0]
    if relative < 45. - 1e-9:
        return BANDS[1]
    if relative <= 75. + 1e-9:
        return BANDS[2]
    return BANDS[3]


def navigation_contract(report, rows):
    if report.get("schema_version") != 1:
        raise ValueError("Unsupported navigation report schema")
    interval = report["interval"]
    follow, end, cutoff, step = (require_number(interval[key], "navigation interval " + key)
        for key in ("start_s", "end_s", "navigation_evaluation_start_s", "sample_period_s"))
    if step != .1 or not follow <= cutoff <= end:
        raise ValueError("Invalid original navigation grid/calibration interval")
    expected = int(math.floor((end - follow) / step + 1e-8)) + 1
    if len(rows) != expected or report["whole_interval"]["scheduled_samples"] != expected:
        raise ValueError("Navigation sidecar does not conserve the original physical grid")
    for index, row in enumerate(rows):
        required = {"time_s", "navigation_valid", "navigation_state", "navigation_reason", "active", *METRICS[:4]}
        if not required.issubset(row):
            raise ValueError("Navigation sidecar is missing original fields")
        stamp = require_number(row.get("time_s"), "navigation time")
        if abs(stamp - (follow + index * step)) > 1e-7:
            raise ValueError("Navigation sidecar grid is missing, duplicated or reordered")
        if type(row.get("navigation_valid")) is not bool or type(row.get("active")) is not bool:
            raise ValueError("Missing original navigation/control validity")
        if type(row.get("navigation_state")) is not int and row.get("navigation_state") is not None:
            raise ValueError("Invalid navigation state code")
        if not isinstance(row.get("navigation_reason"), str):
            raise ValueError("Missing original navigation reason")
        for key in METRICS:
            if row.get(key) is not None:
                require_number(row[key], key)
        if row.get("kf_position_error_m") is not None and (stamp < cutoff - 1e-9 or not row["navigation_valid"]):
            raise ValueError("KF error contradicts original calibration/validity interval")
    scoped = [row for row in rows if row["time_s"] >= cutoff - 1e-9]
    counts = report["kf_navigation"]["counts"]
    if (counts["scheduled_samples"] != len(scoped)
            or counts.get("valid_navigation_samples", 0) != sum(row["navigation_valid"] for row in scoped)):
        raise ValueError("Navigation sidecar disagrees with original navigation denominator")
    matched = sum(row.get("base_link_distance_error_m") is not None for row in rows)
    if report["whole_interval"]["matched_truth_samples"] != matched:
        raise ValueError("Navigation sidecar disagrees with original physical truth coverage")
    for key in METRICS:
        primary = (report["kf_navigation"]["metrics"] if key.startswith("kf_")
                   else report["whole_interval"]["metrics"])[key]
        actual = metrics(row.get(key) for row in rows)
        if type(primary.get("count")) is not int or primary["count"] != actual["count"]:
            raise ValueError("Navigation sidecar metric count differs from primary report: " + key)
        original_rmse = primary.get("rmse")
        if ((original_rmse is None) != (actual["rmse"] is None)
                or original_rmse is not None and (not number(original_rmse)
                    or not math.isclose(original_rmse, actual["rmse"], rel_tol=1e-9, abs_tol=1e-10))):
            raise ValueError("Navigation sidecar RMSE differs from primary report: " + key)
    return follow, end, cutoff


def identity_contract(report):
    audit = report["conservative_task_time_identity"]
    if (audit.get("schema_version") != 1 or audit.get("sample_period_s") != .1
            or audit.get("coverage_basis") != "fixed_10hz_request_to_recorded_clock_end"):
        raise ValueError("Unsupported original identity cell contract")
    start = require_number(audit["interval"]["start_s"], "identity start")
    end = require_number(audit["interval"]["end_s"], "identity end")
    if end <= start:
        raise ValueError("No original identity duration")
    rows = audit["timeline"]
    expected = max(1, int(math.ceil((end - start) / .1 - 1e-9)))
    if len(rows) != expected or audit["scheduled_samples"] != expected:
        raise ValueError("Identity timeline does not conserve original cell denominator")
    for index, row in enumerate(rows):
        left = require_number(row.get("time_s"), "identity cell left")
        right = require_number(row.get("end_s"), "identity cell right")
        if abs(left - (start + index * .1)) > 1e-7 or abs(right - min(end, start + (index + 1) * .1)) > 1e-7:
            raise ValueError("Missing, overlapping or reordered original identity cell")
        if row.get("outcome") not in {"correct", "wrong", "unknown"} or not isinstance(row.get("reason"), str):
            raise ValueError("Missing original identity outcome/reason")
        if not isinstance(row.get("target_uuid"), str) or not row["target_uuid"]:
            raise ValueError("Missing original identity task membership")
    counts = Counter(row["outcome"] for row in rows)
    if any(audit[key] != counts[key] for key in ("correct", "wrong", "unknown")):
        raise ValueError("Identity outcomes disagree with original audit")
    return audit


def select_event(row):
    if row.get("kind") not in EVENT_KINDS:
        return None
    require_number(row.get("time_s"), "monitor event time")
    return {key: value for key, value in row.items() if key not in {"bbox", "position_m", "orientation_xyzw"}}


def event_partition(follow, end, summary, events, nav_rows, identity, mode, occlusions, *, navigation_end=None):
    """Fail closed to an explicit unresolved partition when events are absent."""
    lower = min(follow, identity["interval"]["start_s"]) if identity else follow
    reasons = []
    details = {"short_recovery_definition": "First original 10 Hz valid MEASURED and active navigation sample after short open request; grid resolution, not a new primary gate"}

    def unresolved(reason):
        return {"status": "UNRESOLVED_EVENTS", "reasons": [reason], "details": details,
                "intervals": [{"name": "UNRESOLVED_EVENTS", "start_s": lower, "end_s": end}]}

    if summary is None or events is None:
        return unresolved("Missing complete monitor summary or telemetry")
    try:
        monitor_end = require_number(summary.get("end_sim_s"), "monitor end")
        if abs(require_number(summary.get("follow_start_s"), "monitor FOLLOW") - follow) > .2:
            return unresolved("Monitor FOLLOW and original navigation FOLLOW disagree")
        if not follow <= monitor_end <= end + .2:
            return unresolved("Monitor endpoint is outside recorded interval")
        if any(b["time_s"] < a["time_s"] - 1e-9 for a, b in zip(events, events[1:])):
            return unresolved("Monitor event timestamps regress")
        failures = [row for row in events if row["kind"] == "shutter_schedule_failure"
                    or row["kind"] == "shutter_service_result" and row.get("success") is False]
        details["recorded_failure_events"] = failures
        if failures:
            return unresolved("Original failed shutter event retained; no successful event substitution")
        initial_confirm = lower
        if mode == "specified":
            tasks = sorted(identity["tasks"].values(), key=lambda row: row["request_time_s"]) if identity else []
            if not tasks or tasks[0].get("confirmation_time_s") is None:
                return unresolved("Missing initial task confirmation")
            initial_confirm = require_number(tasks[0]["confirmation_time_s"], "initial confirmation")
            if not lower <= initial_confirm <= monitor_end:
                return unresolved("Initial task confirmation is outside the recorded task interval")
        boundaries = [(lower, "initial_confirmation"), (initial_confirm, "normal_follow")]
        if occlusions == "unknown":
            return unresolved("Occlusion profile must be declared expected or none")
        if occlusions == "expected":
            holds = {name: [row for row in events if row["kind"] == "shutter_hold_finished" and row.get("name") == name]
                     for name in ("short", "long")}
            if any(len(rows) != 1 for rows in holds.values()):
                return unresolved("Missing or repeated original short/long shutter completion event")
            shutter_rows = [row for row in events if row["kind"] == "shutter"
                            and not row.get("refresh") and not row.get("cleanup")]
            shutters = {row.get("request_id"): row for row in shutter_rows}
            if len(shutters) != len(shutter_rows):
                return unresolved("Duplicate shutter request identifiers")
            points = {}
            for name, rows in holds.items():
                hold = rows[0]
                close = shutters.get(hold.get("close_request_id"))
                opened = shutters.get(hold.get("open_request_id"))
                if close is None or opened is None or close.get("active") is not True or opened.get("active") is not False:
                    return unresolved("Shutter completion lacks matching close/open request identities")
                points[name] = (close["time_s"], opened["time_s"])
            short_close, short_open = points["short"]
            long_close, long_open = points["long"]
            recovered = next((row["time_s"] for row in nav_rows if short_open <= row["time_s"] < long_close
                              and row["navigation_valid"] and row["navigation_state"] == 1 and row["active"]), None)
            requests = [row for row in events if row["kind"] == "explicit_reselection_requested"]
            if recovered is None or len(requests) != 1:
                return unresolved("Short recovery or unique explicit reselection event is missing")
            request = requests[0]
            uuid = request.get("target_uuid")
            if identity:
                confirmation = identity["tasks"].get(uuid, {}).get("confirmation_time_s")
            else:
                confirms = [row["time_s"] for row in events if row["kind"] == "explicit_reselection_confirmed"
                            and row.get("target_uuid") == uuid]
                confirmation = min(confirms) if confirms else None
            if confirmation is None:
                return unresolved("New task lacks its original confirmation")
            confirmation = require_number(confirmation, "new task confirmation")
            if confirmation + 5. > min(end, navigation_end if navigation_end is not None else end) + 1e-9:
                return unresolved("Original recording does not cover the complete confirmed five-second interval")
            sequence = [initial_confirm, short_close, short_open, recovered, long_close, long_open,
                        request["time_s"], confirmation, confirmation + 5., monitor_end]
            if any(b < a - 1e-9 for a, b in zip(sequence, sequence[1:])):
                return unresolved("Events are out of order or recording ended before confirmed five-second window")
            boundaries.extend(((short_close, "short_request_and_recovery"), (recovered, "normal_follow"),
                (long_close, "long_request_to_open"), (long_open, "open_to_explicit_request"),
                (request["time_s"], "request_to_new_confirmation"),
                (confirmation, "confirmed_first_5s"), (confirmation + 5., "later_run")))
            details.update(short_open_s=short_open, short_recovery_s=recovered,
                new_confirmation_s=confirmation, new_target_uuid=uuid,
                explicit_wait_after_open_s=request["time_s"] - long_open,
                confirmation_delay_s=confirmation - request["time_s"],
                confirmation_source="original_identity_task" if identity else "monitor_surface_measured_confirmation")
        elif any(row["kind"] == "shutter" and not row.get("cleanup") for row in events):
            return unresolved("Declared no occlusions conflicts with recorded shutter requests")
        boundaries.extend(((min(monitor_end, end), "recording_tail"), (end, None)))
        intervals = []
        for (start, name), (stop, _) in zip(boundaries, boundaries[1:]):
            if stop > start + 1e-9:
                intervals.append({"name": name, "start_s": start, "end_s": stop})
        return {"status": "RESOLVED_RECORDED_EVENTS", "reasons": reasons, "details": details, "intervals": intervals}
    except (KeyError, TypeError, ValueError) as error:
        return unresolved(str(error))


def phase_at(timestamp, partition):
    for interval in partition["intervals"]:
        if interval["start_s"] - 1e-9 <= timestamp < interval["end_s"] - 1e-9:
            return interval
    if partition["intervals"] and abs(timestamp - partition["intervals"][-1]["end_s"]) <= 1e-7:
        return partition["intervals"][-1]
    raise ValueError("Original sample lies outside event partition")


def navigation_summary(rows, cutoff):
    scoped = [row for row in rows if row["time_s"] >= cutoff - 1e-9]
    n = len(scoped)
    matched = sum(row.get("base_link_distance_error_m") is not None for row in rows)
    valid = sum(row["navigation_valid"] for row in scoped)
    return {"physical_scheduled_samples": len(rows), "physical_matched_truth_samples": matched,
            "physical_truth_coverage": matched / len(rows) if rows else None,
            "navigation_scheduled_samples": n, "valid_navigation_samples": valid,
            "navigation_valid_coverage": valid / n if n else None,
            "metrics": {key: metrics(row.get(key) for row in rows) for key in METRICS},
            "overlap_flags": {"lost": sum(row["navigation_reason"] == "lost" for row in rows),
                "ambiguous": sum(row["navigation_reason"] == "ambiguous" for row in rows),
                "invalid_navigation": sum(not row["navigation_valid"] for row in rows),
                "inactive_control": sum(not row["active"] for row in rows),
                "truth_missing": len(rows) - matched},
            "navigation_reason_counts": dict(Counter(row["navigation_reason"] for row in scoped))}


def grid_interruption_runs(rows, end):
    """Describe observed grid interruptions; no continuous-state interpolation."""
    runs = []
    start = None
    members = []
    for row in rows:
        if not row["navigation_valid"]:
            if start is None:
                start = row["time_s"]
            members.append(row)
        elif start is not None:
            runs.append({"start_s": start, "first_valid_grid_s": row["time_s"],
                "grid_bracket_duration_s": row["time_s"] - start, "end_censored": False,
                "invalid_grid_points": len(members), "reason_counts": dict(Counter(item["navigation_reason"] for item in members))})
            start, members = None, []
    if start is not None:
        runs.append({"start_s": start, "first_valid_grid_s": None, "recording_end_s": end,
            "grid_bracket_duration_s": end - start, "end_censored": True,
            "invalid_grid_points": len(members), "reason_counts": dict(Counter(item["navigation_reason"] for item in members))})
    return {"runs": runs, "definition": "Original consecutive invalid navigation grid points, bracketed by next valid point or censored recording end. These grid brackets do not certify continuous physical availability between samples."}


def confirmation_grid_continuity(rows, partition):
    details = partition["details"]
    if partition["status"] != "RESOLVED_RECORDED_EVENTS" or "new_confirmation_s" not in details:
        return {"status": "UNAVAILABLE", "reason": "No resolved original new-task confirmation"}
    confirmation, uuid = details["new_confirmation_s"], details["new_target_uuid"]
    remaining = [row for row in rows if row["time_s"] >= confirmation - 1e-9]
    window = [row for row in remaining if row["time_s"] < confirmation + 5. - 1e-9]
    def active(row):
        return row["navigation_valid"] and row["active"] and row.get("target_uuid") == uuid
    prefix = []
    for row in remaining:
        if not active(row):
            break
        prefix.append(row)
    return {"status": "ORIGINAL_GRID_DESCRIPTION", "target_uuid": uuid, "confirmation_s": confirmation,
        "first_5s_scheduled_points": len(window), "first_5s_valid_active_same_task_points": sum(active(row) for row in window),
        "continuous_prefix_points": len(prefix),
        "observed_prefix_span_s": prefix[-1]["time_s"] - prefix[0]["time_s"] if prefix else None,
        "first_prefix_interruption_s": remaining[len(prefix)]["time_s"] if len(prefix) < len(remaining) else None,
        "definition": "Original received grid only; confirmation need not align with the grid. No cross-sample continuous tracking or new acceptance claim."}


def identity_summary(rows, boundaries, extra_flags):
    counts = Counter(row["outcome"] for row in rows)
    crossed = sum(any(row["time_s"] < boundary - 1e-9 and row["end_s"] > boundary + 1e-9
                      for boundary in boundaries) for row in rows)
    flags = Counter()
    unknown_flags = Counter()
    for row in rows:
        flags.update(extra_flags.get(row["time_s"], set()))
        if row["outcome"] == "unknown":
            unknown_flags.update(extra_flags.get(row["time_s"], set()))
    return {"scheduled_cells": len(rows), **{key: counts[key] for key in ("correct", "wrong", "unknown")},
            "cell_duration_s": math.fsum(row["end_s"] - row["time_s"] for row in rows),
            "unknown_duration_s": math.fsum(row["end_s"] - row["time_s"] for row in rows if row["outcome"] == "unknown"),
            "known_coverage": (counts["correct"] + counts["wrong"]) / len(rows) if rows else None,
            "crosses_boundary_cells": crossed, "unknown_reason_counts": dict(Counter(
                row["reason"] for row in rows if row["outcome"] == "unknown")),
            "overlap_flags_all_cells": dict(flags), "overlap_flags_unknown_cells": dict(unknown_flags)}


def identity_flags(audit, report, frame_rows):
    """Map acquisition evidence to original cells, without filling other cells."""
    flags = {}
    cells = audit["timeline"]
    start = audit["interval"]["start_s"]

    def add(stamp, uuid, names):
        require_number(stamp, "identity flag source time")
        index = int(math.floor((stamp - start) / .1 + 1e-9))
        if 0 <= index < len(cells) and cells[index]["time_s"] - 1e-9 <= stamp < cells[index]["end_s"]:
            if uuid == cells[index].get("target_uuid"):
                flags.setdefault(cells[index]["time_s"], set()).update(names)
    for row in report.get("selected_identity_timeline", []):
        reason = row.get("matching", row.get("match", {})).get("reason")
        names = {"no_fresh_selected"} if reason == "no_fresh_selected_detection" else set()
        if row.get("status") in {"UNKNOWN_GEOMETRY", "UNKNOWN_TASK_INITIAL_ID"}:
            names.add("unknown_identity_geometry_or_task")
        add(row["time_s"], row.get("target_uuid"), names)
    for row in frame_rows or []:
        names = set()
        if row.get("shutter_guard") is True:
            names.add("shutter_guard")
        if row.get("truth_complete") is False:
            names.add("identity_truth_missing")
        expected = row.get("expected_physical_id")
        actor = next((gt for gt in row.get("gt", []) if gt.get("id") == expected), None)
        if actor is not None and actor.get("fully_in_frame") is False:
            names.add("expected_truth_projection_clipped")
        add(row["time_s"], row.get("target_uuid"), names)
    return flags


def analyze(inputs, mode, navigation, nav_rows, identity_report, summary, events,
            raw_rows=None, identity_frame_rows=None, occlusions="unknown"):
    result = {"schema_version": 1, "scope": SCOPE, "mode": mode,
        "primary_conclusions": {"navigation": navigation.get("evaluation_status") if navigation else None,
                                "identity": identity_report.get("evaluation_status") if identity_report else None},
        "navigation": None, "identity": {"status": "NOT_APPLICABLE", "reason": "Unique instance mode has no full-task REQUEST identity audit"}
            if mode == "auto_unique" else None,
        "errors": inputs.errors, "limitations": ["Supplementary descriptions only; no primary outcome or safety gate changes",
            "Identity cells retain original outcomes including wrong evidence and boundary uncertainty",
            "Overlapping flags are observations, not exclusive or causal UNKNOWN explanations",
            "Snapshot missing per original identity cell: UNAVAILABLE (no explicit per-frame presence field)",
            "Detailed physical truth-missing cause per navigation point: UNAVAILABLE"],
        "event_partition": None, "bands": {}, "phases": {}, "conservation": None}
    if navigation is None or nav_rows is None:
        result["status"] = "INCOMPLETE_EVIDENCE"
        return result
    try:
        follow, nav_end, cutoff = navigation_contract(navigation, nav_rows)
        audit = identity_contract(identity_report) if mode == "specified" and identity_report is not None else None
        if mode == "specified" and audit is None:
            inputs.errors.append("Missing specified-individual identity audit")
        if audit:
            actual_sha = inputs.bindings.get("identity_report", {}).get("sha256")
            if not actual_sha or navigation.get("physical_identity_sha256") != actual_sha:
                raise ValueError("Navigation report is not bound to the supplied original identity report SHA")
        id_rows = audit["timeline"] if audit else []
        end = max(nav_end, audit["interval"]["end_s"]) if audit else nav_end
        partition = event_partition(follow, end, summary, events, nav_rows, audit, mode, occlusions, navigation_end=nav_end)
        result["event_partition"] = partition
        if partition["status"] == "UNRESOLVED_EVENTS":
            inputs.errors.append("UNRESOLVED_EVENTS: " + "; ".join(partition["reasons"]))
        flags = identity_flags(audit, identity_report, identity_frame_rows) if audit else {}
        boundaries = [follow, follow + 45., follow + 75.] + [row["start_s"] for row in partition["intervals"]]
        result["navigation"] = {"interval": navigation["interval"], "whole": navigation_summary(nav_rows, cutoff)}
        result["navigation"]["grid_interruptions"] = grid_interruption_runs(nav_rows, nav_end)
        result["navigation"]["post_confirmation_continuity"] = confirmation_grid_continuity(nav_rows, partition)
        if audit:
            result["identity"] = {"status": "APPLICABLE_ORIGINAL_CELLS", "interval": audit["interval"],
                "whole": identity_summary(id_rows, boundaries, flags)}
        for name in BANDS:
            selected_nav = [row for row in nav_rows if band_at(row["time_s"], follow) == name]
            selected_id = [row for row in id_rows if band_at(row["time_s"], follow) == name]
            result["bands"][name] = {"navigation": navigation_summary(selected_nav, cutoff),
                "identity": identity_summary(selected_id, boundaries, flags) if audit else None}
        for interval in partition["intervals"]:
            name = interval["name"]
            # Repeated normal-follow intervals share one named bucket.
            result["phases"].setdefault(name, {"intervals": [], "_nav": [], "_id": []})
            result["phases"][name]["intervals"].append(interval)
        for row in nav_rows:
            result["phases"][phase_at(row["time_s"], partition)["name"]]["_nav"].append(row)
        for row in id_rows:
            result["phases"][phase_at(row["time_s"], partition)["name"]]["_id"].append(row)
        for group in result["phases"].values():
            group["navigation"] = navigation_summary(group.pop("_nav"), cutoff)
            group["identity"] = identity_summary(group.pop("_id"), boundaries, flags) if audit else None
        checks = {}
        for view in ("bands", "phases"):
            groups = list(result[view].values())
            for key in ("physical_scheduled_samples", "physical_matched_truth_samples", "navigation_scheduled_samples", "valid_navigation_samples"):
                checks[view + ":" + key] = sum(group["navigation"][key] for group in groups) == result["navigation"]["whole"][key]
            for key in METRICS:
                checks[view + ":metric_count:" + key] = sum(group["navigation"]["metrics"][key]["count"] for group in groups) == result["navigation"]["whole"]["metrics"][key]["count"]
                checks[view + ":metric_energy:" + key] = math.isclose(math.fsum(
                    group["navigation"]["metrics"][key]["squared_error_sum"] for group in groups),
                    result["navigation"]["whole"]["metrics"][key]["squared_error_sum"], rel_tol=1e-12, abs_tol=1e-12)
            if audit:
                for key in ("scheduled_cells", "correct", "wrong", "unknown"):
                    checks[view + ":identity:" + key] = sum(group["identity"][key] for group in groups) == result["identity"]["whole"][key]
        result["conservation"] = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
        if not all(checks.values()):
            inputs.errors.append("Original denominator/outcome conservation failed")
        if raw_rows is not None:
            raw_groups = {}
            for row in raw_rows:
                stamp = require_number(row.get("time_s"), "raw acquisition time")
                if type(row.get("fusion_accepted")) is not bool:
                    raise ValueError("Missing raw fusion acceptance evidence")
                raw_groups.setdefault(band_at(stamp, follow), []).append(row)
            result["raw_acquisition_overlap"] = {name: {"acquisition_opportunities": len(rows),
                "fusion_not_accepted": sum(not row["fusion_accepted"] for row in rows),
                "fusion_reason_counts": dict(Counter(str(row.get("fusion_reason")) for row in rows))}
                for name, rows in raw_groups.items()}
        else:
            result["raw_acquisition_overlap"] = {"status": "UNAVAILABLE", "reason": "No original raw sidecar provided"}
        if identity_frame_rows is None:
            result["limitations"].append("Identity shutter guard, clipping and truth flags: UNAVAILABLE without original identity frame sidecar")
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        inputs.errors.append("Evidence contract: " + str(error))
    result["status"] = "INCOMPLETE_EVIDENCE" if inputs.errors else "COMPLETE_AUXILIARY_ANALYSIS"
    return result


def write_outputs(directory, report, manifest):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    manifest["manifest_sha256"] = canonical(manifest)
    report["input_manifest_sha256"] = manifest["manifest_sha256"]
    report["input_manifest_file"] = "input_manifest.json"
    for name, value in (("analysis.json", report), ("input_manifest.json", manifest)):
        with (directory / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    fields = ("view", "segment", "physical_samples", "navigation_samples", "valid_navigation_samples",
              "distance_rmse_m", "height_rmse_m", "identity_cells", "identity_wrong", "identity_unknown")
    table = []
    for view in ("bands", "phases"):
        for name, group in report[view].items():
            nav, identity = group["navigation"], group["identity"]
            table.append((view, name, nav["physical_scheduled_samples"], nav["navigation_scheduled_samples"],
                nav["valid_navigation_samples"], nav["metrics"]["base_link_distance_error_m"]["rmse"],
                nav["metrics"]["base_link_height_error_m"]["rmse"],
                identity["scheduled_cells"] if identity else None,
                identity["wrong"] if identity else None, identity["unknown"] if identity else None))
    with (directory / "segments.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(table)
    escape = lambda value: html.escape("N/A" if value is None else str(value))
    cells = "".join("<tr>" + "".join("<td>" + escape(value) + "</td>" for value in row) + "</tr>" for row in table)
    body = "<!doctype html><html lang='en'><meta charset='utf-8'><title>v4 task phase appendix</title>"
    body += "<style>body{font:16px system-ui;margin:2em;color:#172230}table{border-collapse:collapse}th,td{padding:.5em;border:1px solid #ccd3db}th{background:#edf2f7}code{overflow-wrap:anywhere}</style>"
    body += "<h1>v4 task phase appendix</h1><p>" + escape(report["status"]) + "</p>"
    body += "<p>Supplementary evidence; original primary outcomes and complete denominators remain in force. N/A is not zero. Duration changes do not establish algorithm improvement.</p>"
    body += "<p>Events: " + escape((report.get("event_partition") or {}).get("status")) + "; conservation: " + escape((report.get("conservation") or {}).get("status")) + "</p>"
    body += "<p>Manifest: <code>" + manifest["manifest_sha256"] + "</code></p>"
    body += "<table><thead><tr>" + "".join("<th>" + name + "</th>" for name in fields) + "</tr></thead><tbody>" + cells + "</tbody></table>"
    body += "<h2>Missing evidence and limitations</h2><ul>" + "".join("<li>" + escape(value) + "</li>" for value in report["errors"] + report["limitations"]) + "</ul>"
    body += "<p><a href='analysis.json'>Full JSON</a> · <a href='segments.csv'>CSV</a> · <a href='input_manifest.json'>Input manifest</a></p></html>"
    (directory / "index.html").write_text(body, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("auto_unique", "specified"), required=True)
    parser.add_argument("--navigation-report", type=Path, required=True)
    parser.add_argument("--navigation-frames", type=Path, required=True)
    parser.add_argument("--identity-report", type=Path)
    parser.add_argument("--identity-frames", type=Path)
    parser.add_argument("--raw-frames", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--telemetry", type=Path)
    parser.add_argument("--occlusions", choices=("expected", "none", "unknown"), default="unknown")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("Output directory already exists; no overwrite or resume")
    if args.mode == "auto_unique" and (args.identity_report or args.identity_frames):
        parser.error("Unique-instance identity must remain N/A; no REQUEST-only identity report may be supplied")
    inputs = Inputs()
    navigation = inputs.read("navigation_report", args.navigation_report)
    rows = inputs.read("navigation_frames", args.navigation_frames, lines=True)
    identity = inputs.read("identity_report", args.identity_report, required=args.mode == "specified")
    frames = inputs.read("identity_frames", args.identity_frames, lines=True, required=False)
    raw = inputs.read("raw_frames", args.raw_frames, lines=True, required=False)
    summary = inputs.read("monitor_summary", args.summary)
    events = inputs.read("monitor_telemetry", args.telemetry, lines=True, select=select_event)
    report = analyze(inputs, args.mode, navigation, rows, identity, summary, events,
                     raw, frames, args.occlusions)
    script = Path(__file__).resolve()
    manifest = {"schema_version": 1, "scope": SCOPE, "created_utc": datetime.now(timezone.utc).isoformat(),
        "analyzer_source": {"path": str(script), "sha256": file_sha(script), "local_dependencies_sha256": {}},
        "python_version": platform.python_version(), "inputs": inputs.bindings,
        "parameters": {"mode": args.mode, "occlusions": args.occlusions},
        "declared_navigation_source": navigation.get("evaluation_source") if navigation else None,
        "declared_identity_source": identity.get("evaluation_source") if identity else None,
        "source_scope": "Actual input bytes and analyzer SHA; declared evaluator provenance retained, not re-certified or replaced",
        "read_scope": "Complete explicit JSON/JSONL inputs only; no bag, nodes, model or simulation"}
    write_outputs(args.output_dir, report, manifest)
    print(json.dumps({"status": report["status"], "output": str(args.output_dir), "manifest_sha256": manifest["manifest_sha256"]}))
    return 0 if report["status"] == "COMPLETE_AUXILIARY_ANALYSIS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
