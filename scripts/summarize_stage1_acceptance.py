"""Combine recorded engineering evidence; missing or failed trials never pass."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path


SETPOINT_COUNTER_KEYS = (
    "px4_setpoints", "classified_px4_setpoints", "position_only_setpoints", "velocity_only_setpoints",
    "invalid_setpoints", "simultaneous_position_velocity_setpoints", "partial_position_setpoints",
    "partial_velocity_setpoints", "malformed_partial_setpoints", "malformed_dimension_setpoints",
    "infinite_setpoint_fields", "inactive_position_velocity_setpoints", "follow_setpoints",
    "follow_position_setpoints", "follow_velocity_setpoints", "follow_invalid_setpoints",
)

POST_RESELECTION_CHECK_KEYS = (
    "minimum_recording_duration", "minimum_state_span", "minimum_control_span",
    "same_target_active_states_only", "tracking_control_only_after_grace",
    "continuous_state_evidence", "continuous_control_evidence",
    "fresh_state_at_trial_end", "tracking_control_at_trial_end",
)


def setpoint_evidence(monitor: dict) -> dict:
    """Require observed, explicitly classified samples before accepting zeros."""

    counts = monitor.get("counts", {})
    evidence = monitor.get("setpoint_evidence", {})
    missing = [name for name in SETPOINT_COUNTER_KEYS if name not in counts]
    invalid = [name for name in SETPOINT_COUNTER_KEYS if name in counts
               and (type(counts[name]) is not int or counts[name] < 0)]
    complete = (
        not missing and not invalid
        and evidence.get("counter_schema_version") == 1
        and evidence.get("topic") == "/fmu/in/trajectory_setpoint"
        and evidence.get("required_counters_present") is True
        and type(evidence.get("classified_samples")) is int
    )
    conserved = False
    if complete:
        total = counts["px4_setpoints"]
        conserved = (
            total >= 100
            and counts["classified_px4_setpoints"] == evidence["classified_samples"] == total
            and counts["position_only_setpoints"] + counts["velocity_only_setpoints"] + counts["invalid_setpoints"] == total
            and counts["follow_position_setpoints"] + counts["follow_velocity_setpoints"] + counts["follow_invalid_setpoints"] == counts["follow_setpoints"]
            and counts["follow_setpoints"] <= total
            and all(counts[name] <= total for name in SETPOINT_COUNTER_KEYS)
        )
    exclusive = bool(complete and conserved and all(counts[name] == 0 for name in (
        "invalid_setpoints", "simultaneous_position_velocity_setpoints", "partial_position_setpoints",
        "partial_velocity_setpoints", "malformed_partial_setpoints", "malformed_dimension_setpoints",
        "infinite_setpoint_fields", "inactive_position_velocity_setpoints", "follow_invalid_setpoints",
    )))
    return {"complete": complete, "counter_conservation_valid": conserved,
            "exclusive_fields": exclusive, "missing_counters": missing, "invalid_counters": invalid,
            "counts": {name: counts[name] for name in SETPOINT_COUNTER_KEYS if name in counts}}


def _finite_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def sustained_reselection_tracking(window: dict) -> bool:
    """Check recorded duration and identity, independently of a PASS label."""

    tracking = window.get("post_reselection_tracking", {})
    selection = window.get("explicit_reselection", {})
    if not isinstance(tracking, dict) or not isinstance(selection, dict):
        return False
    checks = tracking.get("checks", {})
    numeric_keys = (
        "confirmation_time_s", "minimum_duration_s", "tail_freshness_s",
        "maximum_evidence_gap_s", "maximum_measurement_age_s", "control_grace_s", "observed_duration_s",
        "state_span_s", "control_span_s", "last_state_age_to_trial_end_s",
        "last_control_age_to_trial_end_s", "last_state_measurement_age_at_trial_end_s",
    )
    if not all(_finite_number(tracking.get(key)) for key in numeric_keys):
        return False
    if not _finite_number(selection.get("confirmation_time_s")):
        return False
    confirmed = selection.get("confirmed_target_uuid")
    identity_matches = (
        selection.get("confirmed") is True
        and isinstance(confirmed, str) and bool(confirmed.strip())
        and tracking.get("confirmed_target_uuid") == confirmed
        and abs(tracking["confirmation_time_s"] - selection["confirmation_time_s"]) <= 1e-9
    )
    required_checks_pass = (
        isinstance(checks, dict)
        and all(checks.get(key) is True for key in POST_RESELECTION_CHECK_KEYS)
        and all(value is True for value in checks.values())
    )
    minimum = tracking["minimum_duration_s"]
    tail = tracking["tail_freshness_s"]
    threshold_valid = (
        minimum >= 5.0 and 0.0 < tail <= 0.5
        and 0.0 < tracking["maximum_evidence_gap_s"] <= 0.5
        and 0.0 < tracking["maximum_measurement_age_s"] <= 0.75
        and 0.0 <= tracking["control_grace_s"] <= 0.10
    )
    spans_valid = all(tracking[key] >= minimum for key in (
        "observed_duration_s", "state_span_s", "control_span_s",
    ))
    tails_valid = all(0.0 <= tracking[key] <= tail for key in (
        "last_state_age_to_trial_end_s", "last_control_age_to_trial_end_s",
    ))
    return bool(
        tracking.get("result") == "PASS" and required_checks_pass and identity_matches
        and threshold_valid and spans_valid and tails_valid
        and 0.0 <= tracking["last_state_measurement_age_at_trial_end_s"] <= tracking["maximum_measurement_age_s"]
    )


def offline_acceptance_evidence(offline: dict) -> dict:
    schema = offline.get("schema_version")
    current_schema = type(schema) is int and schema >= 3
    interval = offline.get("interval", {})
    full_recorded_trial_end = bool(
        isinstance(interval, dict)
        and interval.get("covers_recorded_trial_end") is True
        and _finite_number(interval.get("end_s"))
        and _finite_number(interval.get("recorded_end_s"))
        and interval["end_s"] >= interval["recorded_end_s"] - 1e-9
    )
    windows = offline.get("occlusions", [])
    shutter_confirmed = bool(windows) and all(
        all(window.get("shutter_execution", {}).get(name) is True for name in (
            "close_success", "open_success", "close_ack_before_open_request",
        )) for window in windows
    )
    long_windows = [window for window in windows if window.get("kind") == "long"]
    reselections = [window.get("explicit_reselection", {}) for window in long_windows]
    reselection_confirmed = bool(reselections)
    for selection in reselections:
        original = selection.get("original_target_uuid")
        confirmed = selection.get("confirmed_target_uuid")
        action = selection.get("action")
        reselection_confirmed &= bool(
            selection.get("confirmed") is True
            and isinstance(original, str) and original.strip()
            and isinstance(confirmed, str) and confirmed.strip() and confirmed != original
            and action in ("SELECT", "RESET")
            and (action != "SELECT" or confirmed == selection.get("requested_target_uuid"))
        )
    sustained_tracking = bool(current_schema and long_windows) and all(
        sustained_reselection_tracking(window) for window in long_windows
    )
    return {"current_schema": current_schema, "shutter_operations_confirmed": shutter_confirmed,
            "new_task_confirmed_from_bag": reselection_confirmed,
            "sustained_tracking_after_reselection": sustained_tracking,
            "full_recorded_trial_end": full_recorded_trial_end}


def trial_report(directory: Path) -> dict:
    missing = [name for name in ("run_config.json", "summary.json", "offline_evaluation.json",
                                "onboard.mp4", "rosbag/metadata.yaml", "configuration/source_sha256.json")
               if not (directory / name).is_file()]
    report = {"trial": directory.name, "missing_artifacts": missing, "passed": False}
    if missing:
        return report
    config = json.loads((directory / "run_config.json").read_text(encoding="utf-8"))
    monitor = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    offline = json.loads((directory / "offline_evaluation.json").read_text(encoding="utf-8"))
    selection = monitor.get("explicit_reselection", {})
    setpoints = setpoint_evidence(monitor)
    offline_evidence = offline_acceptance_evidence(offline)
    checks = {
        "real_visual_flight": monitor.get("source") == "ONBOARD_RGBD_YOLO_PX4_FLIGHT",
        "basic_flight": monitor.get("basic_flight_passed") is True,
        "offline_occlusion": offline.get("acceptance", {}).get("result") == "PASS",
        "current_offline_evidence_schema": offline_evidence["current_schema"],
        "full_recorded_trial_end": offline_evidence["full_recorded_trial_end"],
        "confirmed_shutter_operations": offline_evidence["shutter_operations_confirmed"],
        "short_and_long_occlusion": {event["kind"] for event in offline.get("occlusions", [])} >= {"short", "long"},
        "long_occlusion_braking_from_motion": all(event.get("braking_from_motion_demonstrated") is True
                                                  for event in offline.get("occlusions", []) if event["kind"] == "long"),
        "setpoint_evidence_complete": setpoints["complete"] and setpoints["counter_conservation_valid"],
        "exclusive_setpoint_fields": setpoints["exclusive_fields"],
        # FOLLOW/HOLD messages can cross in callback order. A position-mode
        # trial may include valid zero-velocity safety braking; require proof
        # of its requested mode, without forbidding that braking mode.
        "requested_mode_reaches_px4": setpoints["complete"] and monitor["counts"]["follow_" + config["command_mode"] + "_setpoints"] >= 20,
        "explicit_new_task_after_loss": bool(config.get("reselect_after_loss") and selection.get("requested_target_uuid")
                                             and selection.get("measured_confirmation")
                                             and offline_evidence["new_task_confirmed_from_bag"]),
        "sustained_tracking_after_reselection": offline_evidence["sustained_tracking_after_reselection"],
        "recorded_bag_data": any((directory / "rosbag").glob("*.db3*")),
        "nonempty_video": (directory / "onboard.mp4").stat().st_size > 1024,
    }
    report.update(class_name=config["target_class"], command_mode=config["command_mode"], checks=checks,
                  setpoint_evidence=setpoints,
                  passed=all(checks.values()),
                  horizontal_vehicle_span_m=monitor.get("horizontal_vehicle_span_m"),
                  estimated_distance_error_rmse_m=monitor.get("estimated_distance_error_rmse_m"),
                  estimated_height_error_rmse_m=monitor.get("estimated_height_error_rmse_m"),
                  median_inference_wall_s=monitor.get("median_inference_wall_s"))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path(__file__).resolve().parents[1] / "results")
    parser.add_argument("--trials", nargs="+", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    trials = [trial_report(args.results_root / name) for name in args.trials]
    required = {(category, mode) for category in ("person", "car") for mode in ("velocity", "position")}
    passed = {(row.get("class_name"), row.get("command_mode")) for row in trials if row["passed"]}
    report = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Stage-one engineering flight acceptance, not repeated research experiments or detector/estimator accuracy",
        "result": "PASS" if required <= passed and all(row["passed"] for row in trials) else "FAIL_OR_INCOMPLETE",
        "missing_passed_conditions": [dict(class_name=category, command_mode=mode) for category, mode in sorted(required - passed)],
        "trials": trials,
        "limitations": ["Portable/unit checks and environment build are recorded separately in STAGE1_ACCEPTANCE.md.",
                        "Estimated controller errors use the visual surface anchor; consult offline reports for independent model-origin metrics.",
                        "Failed historical runs remain in the results tree and are not independent successful repetitions."],
    }
    output = args.output or args.results_root / "stage1_acceptance_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
