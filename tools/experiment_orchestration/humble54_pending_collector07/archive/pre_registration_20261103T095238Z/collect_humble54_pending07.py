"""Development-only remaining-five collector; preserve every original verdict.

The old owner06/07/08/09 sources and results are immutable inputs.  Execution is
disabled until a separate literal registration after independent review.  The
only prospective null classification is a short-window identity comparison
whose recovery prerequisite was not observed after an independently failed
short-loss check.  It never certifies identity or formal readiness.
"""
from __future__ import annotations

import argparse
import errno
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import types
import uuid

sys.dont_write_bytecode = True  # Importing the original validator must not write into its frozen tree.

SCOPE = "SUPERVISED_PENDING_COLLECTION"
PRODUCTION_ENABLED = False
REGISTERED_PROFILE_SHA256 = None
PROFILE_STATUS = "PREPARED_NOT_REGISTERED"
ROOT = Path(__file__).resolve().parents[3]
EXPECTED_PREFIX_COUNT = 11
EXPECTED_AFTER_SLOT = "car_extension_dropout_seed004"
CONDITIONAL_IDENTITY = "CONDITIONAL_UNOBSERVED_AFTER_DEMONSTRATED_SHORT_LOSS"
OLD_STOP_ERROR = "ValueError: New unknown behavior evidence; root must inspect: short:identity_preserved_on_observed_recovery"
PLAN_SHA = "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54"
ENTRY_SHA = "d9cc1f1876a5ed9a358697b29644e7aa7a3c192e0bdd2a2a7d37c208e74f06a6"
CAPTURE_PROFILES = {
    "person": {
        "model": "models/yolo11n.pt",
        "model_sha256": "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1",
        "capture_sha256": "0094a5013801e67fb6ae692cef785b190272708d71bfb0cd4a3349a0eb09ee46",
        "entries": 204,
    },
    "car": {
        "model": "models/yolo11m_car_sim_train20_04.pt",
        "model_sha256": "bf7a56de4ae1658f8101fc6089247e8b984c2965b58d6b4963b4b5977e9ca00c",
        "capture_sha256": "c003f1b86e56bc548b4a1f50d890950320d879dbf205b7c86c574c427c28009c",
        "entries": 204,
    },
}
DDS_CAPTURE_SHA = "4e517b62e823585b53dd2ac503f65eaf9bc3fd4c59d9d8fdb900d985f99d030d"
RUNNER_SHA = "069c7c519d5b0305c087f8ad2597a2c709b367cc6c62624bbb686c9a0d158e11"
NAV_PINS = {
    "scripts/evaluate_navigation_reference.py": "bbff6c746ed76d0139c194cdfc1409f38dc422d64ddbc73da2995a0838df4422",
    "uav_tracking/research_dynamics.py": "03c81478632f38ba2ca49b91b14cf5b43e0c6f8c545c6cbf037f2f62fb118cb9",
    "scripts/evaluate_follow_dynamics.py": "c9b0c54242c4860b463d2df09ab7b1fcde9079ca1aa120d75b711856cb47c72b",
    "scripts/run_reliability_v4.py": RUNNER_SHA,
}
# Root reviewed this original probe02 terminal after the actual owner05 stop.
# This preserves its UNKNOWN; no future original trial receives an exception.
HISTORY = {"person_extension_dropout_seed004": "c09f95ee3c4d5f14847bcbea82e8795b11cab6f5184fe735abac4c22decaeba8"}
OLD_SHORT_NULL = "person_extension_dropout_seed004"
SHUTTER = ("recorded_close_event", "shutter_close_service_succeeded", "shutter_open_service_succeeded", "shutter_close_ack_before_open_request")
LONG_SAFE = ("lost_observed_for_long_occlusion", "hover_observed_for_long_occlusion", "sustained_low_speed_after_hover",
             "no_automatic_recovery_after_long_loss", "no_tracking_control_before_reselection_after_long_loss")
SHORT_ALGORITHM = ("detector_interruption_observed", "prediction_observed", "no_loss_during_short_occlusion", "identity_preserved_on_observed_recovery")
LONG_ALGORITHM = ("detector_interruption_observed", "prediction_observed", "sustained_tracking_after_reselection")
CLAIM = "Collection only; original FAIL/INCOMPLETE remain unchanged. No readiness, capacity, export, final or formal execution."
SLOT_LIBRARY = ROOT / "tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_closure.py"
SLOT_LIBRARY_SHA = "b3c086db30afe243bfdac423c0302c0285ebd64c8d7e8cb24b388e40fd81d744"
SMALL_ARTIFACTS = ("recording_closure.json", "bag_integrity.json", "configuration/source_sha256.json",
                   "run_config.json", "configuration/runtime_parameters.yaml", "px4_source_clock_report.json",
                   "native_startup_report.json", "flight_evaluation.json", "navigation_reference_evaluation.json")
SOURCE_NAMES = {"plan", "entry", "old_collector06", "old_gate06", "old_launcher06", "old_profile06",
                "old_chain03", "old_slot_library03", "monitor", "durable07", "durable09", "conditional_evaluator"}


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            value.update(block)
    return value.hexdigest()


def digest(value, exclude):
    return hashlib.sha256(json.dumps({k: v for k, v in value.items() if k != exclude},
                                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load(path):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= 2 * 1024 * 1024, "Missing/oversized small JSON: " + str(path))
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda v: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    require(isinstance(value, dict), "Expected JSON object")
    return value


def fixed_module(name, path, expected):
    path = Path(path)
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "Pinned module source differs: " + str(path))
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def review_library():
    return fixed_module("humble54_pending07_small_evidence", SLOT_LIBRARY, SLOT_LIBRARY_SHA)


def one(rows, kind):
    matches = [row for row in rows if row.get("kind") == kind]
    require(len(matches) == 1, "Missing/duplicate " + kind)
    return matches[0]


def artifact(trial, record, name):
    root = Path(trial["directory"]).resolve(strict=True)
    path = (root / name).resolve(strict=True)
    require(path.is_relative_to(root) and sha(path) == record["artifact_hashes"][name], "Original artifact SHA differs: " + name)
    return path


def nav_audit(module, plan, report):
    result, evidence = module.navigation_verdict(report, plan["protocol"]["navigation_acceptance"])
    if result in {"PASS", "FAIL"}:
        return {"original_navigation_verdict": result, "original_navigation_evidence": evidence}
    reason = "Transient denominator differs from the whole interval"
    require(result == "INCOMPLETE_EVIDENCE" and evidence == {"reason": reason}, "New/unknown navigation evidence defect: " + str(evidence))
    require(all(plan["source_hashes"].get(key) == value for key, value in NAV_PINS.items()), "ULP exception source revision differs")
    require(report["evaluation_status"] == "RECORDED_WITH_CENSORED_FAILURES" and report["incomplete_reasons"] == []
            and all(type(v) is int and v == 0 for v in report["malformed_input_counts"].values()), "ULP case has additional malformed/incomplete evidence")
    interval, whole = report["interval"], report["whole_interval"]
    start, end, dt = interval["start_s"], interval["end_s"], interval["sample_period_s"]
    require(type(dt) is float and dt == .1 and all(type(v) in {int, float} and math.isfinite(v) for v in (start, end)), "ULP time grid differs")
    ratio = (end - start) / dt
    legacy, expected = math.floor(ratio) + 1, math.floor(ratio + 1e-8) + 1
    require(expected == legacy + 1 and 0 < math.ceil(ratio) - ratio <= math.ulp(ratio)
            and whole["scheduled_samples"] == expected, "Not the known single-sample ULP grid boundary")
    # Audit only: normalize the one linked count/coverage family in memory so
    # the original validator can expose any SECOND structural defect. Never
    # publish this copy or use its result as a replacement engineering verdict.
    audit = deepcopy(report)
    for dimension in ("distance", "height"):
        transient = report["whole_interval"]["transients"]["base_link"][dimension]
        n, truth = transient["scheduled_samples"], transient["valid_truth_samples"]
        require(type(n) is int and n == legacy and type(truth) is int and 0 <= truth <= n
                and whole["matched_truth_samples"] - truth in {0, 1}
                and math.isclose(transient["truth_coverage"], truth / n, rel_tol=1e-9, abs_tol=1e-9), "ULP count family has another discrepancy")
        changed = audit["whole_interval"]["transients"]["base_link"][dimension]
        changed.update(scheduled_samples=expected, valid_truth_samples=whole["matched_truth_samples"],
                       truth_coverage=whole["matched_truth_samples"] / expected)
    checked, _ = module.navigation_verdict(audit, plan["protocol"]["navigation_acceptance"])
    require(checked in {"PASS", "FAIL"}, "ULP case has a second navigation structure error")
    return {"original_navigation_verdict": result, "original_navigation_evidence": evidence,
            "collection_qualification": "KNOWN_SINGLE_SAMPLE_ULP_ORIGINAL_INCOMPLETE_RETAINED",
            "legacy_grid_samples": legacy, "original_whole_grid_samples": expected}


def check_capture(plan, trial, path, profiles):
    """Bind a saved raw capture to its exact class and selected model.

    This is separate from the unchanged full live-source-map check. Production
    profiles are fixed above; small synthetic profiles are an explicit test seam.
    """
    target_class, model = trial.get("target_class"), trial.get("model")
    require(target_class in profiles, "Unknown capture class; no fallback")
    profile = profiles[target_class]
    require(model == profile["model"]
            and plan["protocol"]["resources"][target_class]["model"] == model
            and plan["model_hashes"].get(model) == profile["model_sha256"],
            "Capture class/model/protocol/registered model SHA binding differs")
    actual_sha = sha(path)
    require(actual_sha == profile["capture_sha256"], "Class-specific capture/raw SHA differs")
    capture = load(path)
    require(len(capture) == profile["entries"]
            and {name for name in capture if name.endswith(".pt")} == {model}
            and capture[model] == profile["model_sha256"]
            and capture.get("config/dds_runtime_humble22.json") == DDS_CAPTURE_SHA,
            "Class-specific capture count/selected model/DDS differs")
    return {"target_class": target_class, "model": model, "model_sha256": profile["model_sha256"],
            "capture_sha256": actual_sha, "entries": len(capture), "path": str(Path(path).resolve(strict=True))}


def conditional_identity_nonobservation(surface, row, record):
    """Classify one conditional null without converting it into a pass.

    Other required behavior values are still checked by check_record.  Missing
    keys, missing receive-clock candidates, an observed recovery, or a null
    without the independent demonstrated loss cannot use this rule.
    """
    checks = row["checks"]
    required_nulls = ("first_measured_after_open_s", "recovery_after_open_s")
    require(row.get("kind") == "short" and row.get("complete") is True
            and row.get("result") == "FAIL"
            and "identity_preserved_on_observed_recovery" in checks
            and checks["identity_preserved_on_observed_recovery"] is None
            and checks.get("no_loss_during_short_occlusion") is False
            and all(key in row and row[key] is None for key in required_nulls)
            and record.get("status") == record.get("engineering_result") == "FAIL"
            and surface["acceptance"].get("result") == "FAIL",
            "Conditional identity null lacks its unchanged demonstrated-loss FAIL")
    missing = row.get("post_open_measured_missing_receive_time_count")
    require(type(missing) is int and missing == 0,
            "Conditional identity null has missing recovery receive-clock evidence")
    start, end, lost = row.get("start_s"), row.get("end_s"), row.get("first_lost_s")
    trial_end, recovery_window = surface["interval"].get("end_s"), surface["configuration"].get("recovery_window_s")
    values = (start, end, lost, trial_end, recovery_window, row.get("duration_s"),
              surface["configuration"].get("max_prediction_s"))
    require(all(type(value) in {int, float} and math.isfinite(value) for value in values),
            "Conditional identity null has missing/nonfinite/boolean window clocks")
    require(0 <= start <= end <= trial_end and recovery_window > 0
            and 0 <= row["duration_s"] <= surface["configuration"]["max_prediction_s"]
            and math.isclose(row["duration_s"], end - start, rel_tol=1e-9, abs_tol=1e-9)
            and start <= lost <= min(trial_end, end + recovery_window),
            "Conditional identity null contradicts the frozen short-loss time predicate")
    return {"classification": CONDITIONAL_IDENTITY,
            "field": "surface:short:identity_preserved_on_observed_recovery",
            "value": None, "original_status": "FAIL", "short_result": "FAIL",
            "first_lost_s": lost, "recovery_observation_end_s": min(trial_end, end + recovery_window),
            "identity_result": "UNOBSERVED", "identity_switch_observed_or_excluded": "NEITHER",
            "claim_boundary": "Development collection only; observed recovery comparison unavailable. Original FAIL/null retained."}


def behavior_qualification(surface, record, slot_id, terminal_sha256, history):
    """Keep failures and conditional nonobservations distinct; reject new unknowns."""
    acceptance = surface["acceptance"]
    require(acceptance.get("missing_topics") == [] and type(acceptance.get("input_read_error_count")) is int
            and acceptance["input_read_error_count"] == 0 and acceptance.get("clock_timebase_available") is True
            and all(acceptance.get(key) is True for key in ("short_occlusion_recorded", "long_occlusion_recorded", "failed_events_retained"))
            and surface["flight_evidence"].get("armed_seen") is True and surface["flight_evidence"].get("offboard_seen") is True
            and type(surface["detector"].get("invalid_diagnostic_messages")) is int
            and surface["detector"]["invalid_diagnostic_messages"] == 0,
            "Surface recording/decoder/flight evidence incomplete")
    require(len(surface["occlusions"]) == 2, "Need exactly one original short and long window")
    known, unobserved, conditional = [], [], []
    for kind, algorithm in (("short", SHORT_ALGORITHM), ("long", LONG_ALGORITHM)):
        row = one(surface["occlusions"], kind)
        checks = row["checks"]
        require(row.get("complete") is True and all(checks.get(key) is True for key in (*SHUTTER, *(LONG_SAFE if kind == "long" else ()))),
                "Original shutter/long9 safety failed")
        for key in algorithm:
            value = checks.get(key)
            historical_null = (kind == "short" and key == "detector_interruption_observed" and key in checks and value is None
                               and slot_id == OLD_SHORT_NULL and terminal_sha256 == history.get(OLD_SHORT_NULL))
            conditional_null = (kind == "short" and key == "identity_preserved_on_observed_recovery"
                                and key in checks and value is None)
            if conditional_null:
                conditional.append(conditional_identity_nonobservation(surface, row, record))
            require(type(value) is bool or historical_null or conditional_null,
                    "New unknown behavior evidence; root must inspect: " + kind + ":" + key)
            if value is False:
                known.append("surface:" + kind + ":" + key + "=FAIL")
            elif value is None:
                label = CONDITIONAL_IDENTITY if conditional_null else "HISTORICAL_UNKNOWN_RETAINED"
                unobserved.append("surface:" + kind + ":" + key + "=" + label)
    return {"known_algorithm_failures": known, "unobserved_checks": unobserved, "conditional_nonobservations": conditional}


def check_record(module, plan, trial, capture_profiles, history):
    path = Path(plan["output"]) / "slots" / (trial["id"] + ".json")
    record = load(path)
    marker_path = path.with_name(trial["id"] + ".started.json")
    marker = load(marker_path)
    require(marker.get("id") == trial["id"] and marker.get("plan_sha256") == plan["plan_sha256"]
            and marker.get("flight_command") == trial["flight_command"]
            and record.get("started_utc") == marker.get("started_utc"), "Original started marker binding differs")
    started = datetime.fromisoformat(marker["started_utc"].replace("Z", "+00:00"))
    finished = datetime.fromisoformat(record["finished_utc"].replace("Z", "+00:00"))
    require(started.tzinfo is not None and finished.tzinfo is not None
            and started.utcoffset().total_seconds() == finished.utcoffset().total_seconds() == 0
            and finished >= started, "Original marker/terminal UTC chronology differs")
    require(digest(record, "record_sha256") == record.get("record_sha256") and record.get("id") == trial["id"]
            and record.get("name") == trial["name"] and record.get("plan_sha256") == plan["plan_sha256"], "Terminal content/plan/name binding differs")
    require(record.get("execution_status") == "COMPLETED" and record.get("infrastructure_stop") is False
            and type(record.get("flight_exit_code")) is int and record["flight_exit_code"] == 0
            and record.get("cleanup", {}).get("residual_processes") == []
            and record.get("infrastructure", {}).get("stop") is False
            and record.get("runtime_configuration", {}).get("errors") == [], "Original invocation/runtime/infrastructure/cleanup is unsafe or incomplete")
    flight = one(record["commands"], "flight")
    require(flight.get("command") == trial["flight_command"] and flight.get("error") is None
            and type(flight.get("returncode")) is int and flight["returncode"] == 0, "Original flight command/exit differs")
    for name in ("recording_closure.json", "bag_integrity.json"):
        require(load(artifact(trial, record, name)).get("status") == "PASS", "Recording closure/integrity did not PASS")
    capture_binding = check_capture(plan, trial,
        artifact(trial, record, "configuration/source_sha256.json"), capture_profiles)
    runtime = record["runtime_configuration"]
    require(sha(artifact(trial, record, "run_config.json")) == runtime["run_config_sha256"]
            and sha(artifact(trial, record, "configuration/runtime_parameters.yaml")) == runtime["runtime_parameters_sha256"], "Runtime source/configuration archive changed")
    reports = {}
    require({row["kind"] for row in record["evaluations"]} == {"source_clock", "native_startup", "surface_flight", "navigation"}
            and len(record["evaluations"]) == 4, "Independent evaluator set differs")
    for spec in trial["evaluations"]:
        kind, entry = spec["kind"], one(record["evaluations"], spec["kind"])
        report_path = Path(spec["report"]).resolve(strict=True)
        relative = report_path.relative_to(Path(trial["directory"]).resolve(strict=True)).as_posix()
        require(artifact(trial, record, relative) == report_path and Path(entry["report"]).resolve(strict=True) == report_path
                and entry.get("report_sha256") == sha(report_path) and entry.get("error") is None
                and entry["execution"].get("command") == spec["command"]
                and entry["execution"].get("error") is None and type(entry["execution"].get("returncode")) is int
                and entry["execution"]["returncode"] == 0, "Evaluator report/command/exit/SHA binding differs: " + kind)
        checked = module.read_evaluation(spec, entry["execution"], plan)
        require(checked["result"] == entry["result"] and checked.get("reported_verdict") == entry.get("reported_verdict")
                and checked["result"] not in {"INVALID", "MISSING", "EVALUATION_PENDING"}, "Original evaluator entry is invalid: " + kind)
        if kind in {"source_clock", "native_startup"}:
            require(entry["result"] == "PASS", "Source-clock/native-startup did not PASS")
        reports[kind] = load(report_path)
    surface = reports["surface_flight"]
    behavior = behavior_qualification(surface, record, trial["id"], sha(path), history)
    nav = nav_audit(module, plan, reports["navigation"])
    if nav["original_navigation_verdict"] == "FAIL":
        behavior["known_algorithm_failures"].append("navigation:REGISTERED_PERFORMANCE_GATES_FAILED")
    expected, evidence = module.engineering_verdict(plan, trial, flight, record["evaluations"])
    require(expected == record["status"] == record["engineering_result"] and evidence == record["engineering_evidence"], "Original terminal verdict/evidence contradicts frozen validator")
    return {"slot_id": trial["id"], "original_status": record["status"], "terminal_sha256": sha(path),
            "original_terminal": {"path": str(path.resolve()), "sha256": sha(path)},
            "original_marker": {"path": str(marker_path.resolve()), "sha256": sha(marker_path)},
            "original_started_utc": marker["started_utc"], "original_finished_utc": record["finished_utc"],
            "record_sha256": record["record_sha256"], "capture_binding": capture_binding, **behavior, **nav}


def initial_check(plan_path, entry, after_slot, pins, module):
    require(sha(plan_path) == pins["plan"] and sha(entry) == pins["entry"], "Plan/single-slot entry source changed")
    plan = load(plan_path)
    require(digest(plan, "plan_sha256") == plan.get("plan_sha256") and plan.get("mode") == "EXTENSION_PROBE"
            and plan.get("selected_seeds") == [4], "Wrong original development plan")
    require(module.source_hashes(Path(plan["frozen_root"])) == plan["source_hashes"], "Live frozen source hashes changed")
    ids = [trial["id"] for trial in plan["trials"]]
    require(after_slot == "__before_first__" or after_slot in ids, "Unknown explicit after-slot")
    prefix = 0 if after_slot == "__before_first__" else ids.index(after_slot) + 1
    require(prefix >= pins["minimum_prefix"] and prefix < len(ids), "Closed prefix and remaining slots required")
    closed = []
    for index, trial in enumerate(plan["trials"]):
        terminal = Path(plan["output"]) / "slots" / (trial["id"] + ".json")
        if index < prefix:
            if trial["id"] in pins["history"]:
                require(sha(terminal) == pins["history"][trial["id"]], "Historical original terminal changed")
            closed.append(check_record(module, plan, trial, pins["capture_profiles"], pins["history"]))
        else:
            require(not terminal.exists() and not terminal.with_name(trial["id"] + ".started.json").exists()
                    and not Path(trial["directory"]).exists(), "Pending slot was already attempted or has an existing directory")
    return plan, closed, plan["trials"][prefix:]


def validate_stopped06(v, profile, plan, docs, raw_hashes, prefix):
    """Bind a real exit-two owner, including its uncollected closed frontier.

    No source document is edited or supplied to an exit-zero validator with a
    substituted value.  The already-held 07 handles prove the three actual
    Windows processes ended; no handle is reacquired after their exit.
    """
    now = datetime.now(timezone.utc)
    started, first, native = (docs[key] for key in ("started06", "first_native06", "native_terminal06"))
    outer, monitor, first_monitor = (docs[key] for key in ("outer_terminal06", "final_monitor06", "first_monitor06"))
    admission, gate = docs["admission06"], docs["gate_terminal06"]
    held, held_started, refused09 = docs["terminal07"], docs["started07"], docs["terminal09"]
    require(outer.get("status") == outer.get("native_collection_status") == native.get("status") == "STOPPED_FAULT"
            and outer.get("closure_verified") is True and outer.get("errors") == []
            and type(native.get("returncode")) is int and native["returncode"] == 2
            and native.get("error") == profile["original_stop_error"] == OLD_STOP_ERROR
            and native.get("metadata_fault_child_exit_observed") is True
            and not native.get("child_may_still_be_active")
            and native.get("current_slot") == EXPECTED_AFTER_SLOT,
            "Original owner06 is not the bound safely closed identity-null stop")
    for key in ("monitor_exit_code", "wsl_exit_code", "monitor_popen_wait_exit_code", "monitor_final_popen_wait_exit_code",
                "monitor_final_handle_exit_code", "wsl_final_handle_exit_code"):
        require(type(outer.get(key)) is int and outer[key] == 2, "Original nonzero held/Popen exit differs: " + key)
    require(native["owner_identity"] == first["owner_identity"] == outer["first_native_owner_identity"]
            and native["owner_source"] == first["owner_source"] == outer["first_native_owner_source"]
            and outer["launcher_identity"] == started["launcher_identity"]
            and outer["monitor_identity"] == started["monitor_identity"] == monitor["monitor_process"]
            and outer["wsl_identity"] == first_monitor["task"]["process"] == monitor["task"]["process"],
            "Actual old owner/monitor/WSL identities changed")
    for field in ("plan", "plan_sha256", "plan_file_sha256", "entry_sha256", "started_utc"):
        require(native[field] == first[field], "Old native invocation changed: " + field)
    require(native["plan_sha256"] == plan["plan_sha256"] and native["plan_file_sha256"] == PLAN_SHA
            and native["entry_sha256"] == ENTRY_SHA and native.get("automatic_retry") is False,
            "Old native source/plan registration differs")
    source_map = {"collector": "old_collector06", "gate": "old_gate06", "chain_validator": "old_chain03",
                  "registered_profile": "old_profile06", "monitor": "monitor", "entry": "entry", "plan": "plan"}
    require(started["pins"] == {key: profile["sources"][name] for key, name in source_map.items()}
            and started["launcher_source"] == profile["sources"]["old_launcher06"]
            and native["owner_source"] == {"path": v.mounted(profile["sources"]["old_collector06"]["path"]),
                                           "sha256": profile["sources"]["old_collector06"]["sha256"]},
            "Prepared profile no longer binds the exact old owner06 sources")
    v.linux_identity(native["owner_identity"])
    require(type(monitor["task"].get("returncode")) is int and monitor["task"]["returncode"] == 2
            and {key: value for key, value in monitor["task"].items() if key not in {"returncode", "finished_utc"}}
            == {key: value for key, value in first_monitor["task"].items() if key not in {"returncode", "finished_utc"}}
            and monitor.get("tasks") == [monitor["task"]], "Final original monitor task/exit changed")
    for name, document in (("monitor", started["monitor_identity"]), ("wsl", outer["wsl_identity"]), ("outer", started["launcher_identity"])):
        expected = {key: document[key] for key in ("pid", "start_token")}
        row = held["handles"][name]
        require(held["expected_handles"][name] == held_started["expected_handles"][name] == expected
                and {key: row["identity"][key] for key in expected} == expected
                and row["identity"].get("alive") is True
                and type(row.get("exit_code")) is int and row["exit_code"] == 2
                and held["exit_codes"][name] == 2
                and v.timestamp(row["acquired_utc"], now) == v.timestamp(row["alive_at_acquisition_observed_utc"], now)
                <= v.timestamp(row["first_exit_observed_utc"], now) <= v.timestamp(row["closed_utc"], now),
                "Original live-acquired held handle does not preserve its real exit-two: " + name)
    require(held.get("status") == "REFUSED_FAULT_PRESERVED_NO_RETRY" and held.get("returncode") == 2
            and held.get("future_closure") is None and held.get("automatic_retry") is False
            and held.get("source") == held_started.get("source") == profile["sources"]["durable07"]
            and len(held["errors"]) == 1
            and held["errors"][0]["error"] == "ValueError: Bound original process exited nonzero; no continuation or retry",
            "Original 07 refusal or nonzero stop was replaced")
    require(refused09.get("status") == "REFUSED_OR_STOPPED_PARTIALS_RETAINED_NO_RETRY"
            and type(refused09.get("returncode")) is int and refused09["returncode"] == 2
            and refused09.get("source") == docs["started09"].get("source") == profile["sources"]["durable09"]
            and refused09.get("child") is None and refused09.get("completion") is None
            and refused09.get("automatic_retry") is False and refused09.get("stage_build_formal") == "NOT_RUN"
            and refused09.get("errors") == profile["original_refused09_errors"],
            "Original 09 refusal/unstarted08 evidence differs")
    require(outer.get("power_lease", {}).get("released_utc")
            and type(outer["power_lease"].get("release_return")) is int and outer["power_lease"]["release_return"] != 0,
            "Original temporary power lease has no verified release")
    require(admission["owner_identity"] == native["owner_identity"] and admission["closed_ids"] == [row["id"] for row in prefix[:3]]
            and admission["pending_ids"] == [row["id"] for row in plan["trials"][3:]]
            and admission["unknown_evidence_exceptions"] == HISTORY and admission.get("automatic_retry") is False,
            "Original owner06 early prefix admission differs")
    require(gate.get("status") == "STOPPED_FAULT" and type(gate.get("returncode")) is int and gate["returncode"] == 2
            and gate["admission"]["sha256"] == raw_hashes["admission06"]
            and gate["native_terminal"]["sha256"] == raw_hashes["native_terminal06"]
            and gate["gate_source"] == admission["gate_source"] and gate["profile"] == admission["profile"]
            and outer["native_owner_terminal_sha256"] == raw_hashes["native_terminal06"]
            and outer["registered_entry_terminal_sha256"] == raw_hashes["gate_terminal06"],
            "Original gate/admission/native raw closure binding differs")
    archive_names = {"started06": "started.json", "first_native06": "first_native_state.json", "first_monitor06": "first_monitor_state.json",
                     "final_monitor06": "final_monitor_state.json", "admission06": "first_registered_admission.json",
                     "native_terminal06": "native_terminal.json", "gate_terminal06": "registered_entry_terminal.json"}
    require(all(outer["artifacts"][name] == raw_hashes[key] for key, name in archive_names.items()),
            "Original outer archived small bytes differ")
    for field, expected in (("initial_closed", prefix[:3]), ("collected", prefix[3:10])):
        rows = native[field]
        require(len(rows) == len(expected), "Old native closed-prefix shape differs")
        for row, bound in zip(rows, expected):
            require(row["slot_id"] == bound["id"] and row["original_status"] == bound["original_status"]
                    and row["terminal_sha256"] == row["original_terminal"]["sha256"] == bound["terminal"]["sha256"]
                    and row["original_marker"]["sha256"] == bound["marker"]["sha256"]
                    and row["record_sha256"] == bound["record_sha256"], "Old native closed row differs from its original record")
    require(outer.get("collected_slots") == 7, "Frontier must not be relabelled an actually collected slot")
    events = docs["events06"]
    require(len(events) == 31 and events[0].get("event") == "COLLECTION_STARTED"
            and events[0].get("pending_ids") == [row["id"] for row in plan["trials"][3:]], "Original event stream shape differs")
    cursor = 1
    for row in prefix[:3]:
        begin, end = events[cursor:cursor + 2]
        require(begin.get("event") == "START_SLOT" and end.get("event") == "COMPLETE_SLOT"
                and all(item.get("slot") == row["id"] and item.get("executed_by_this_owner") is False
                        and item.get("event_semantics") == "DERIVED_OBSERVATION_OF_ORIGINAL_CLOSED_PREFIX"
                        and item["original_terminal"]["sha256"] == row["terminal"]["sha256"]
                        and item["original_marker"]["sha256"] == row["marker"]["sha256"] for item in (begin, end)),
                "Old derived prefix event was replaced by an invocation")
        cursor += 2
    for row in prefix[3:10]:
        begin, exited, complete = events[cursor:cursor + 3]
        require(begin.get("event") == "START_SLOT" and begin.get("slot") == row["id"]
                and begin.get("executed_by_this_owner") is True and begin.get("event_semantics") == "ACTUAL_CHILD_INVOCATION"
                and begin.get("command") == ["bash", v.mounted(profile["sources"]["entry"]["path"]), row["id"]]
                and exited.get("event") == "CHILD_EXIT" and exited.get("slot") == row["id"]
                and type(exited.get("returncode")) is int and exited["returncode"] == 0
                and complete.get("event") == "COMPLETE_SLOT" and complete.get("slot") == row["id"]
                and complete.get("executed_by_this_owner") is True
                and complete.get("event_semantics") == "ACTUAL_CHILD_EXIT_AND_ORIGINAL_TERMINAL_VERIFIED"
                and complete.get("terminal_sha256") == row["terminal"]["sha256"]
                and complete.get("status") == row["original_status"], "Old completed invocation provenance differs")
        cursor += 3
    begin, exited, stopped = events[cursor:]
    child = native["current_child"]
    v.linux_identity(child["identity"])
    require(begin.get("event") == "START_SLOT" and begin.get("slot") == EXPECTED_AFTER_SLOT
            and begin.get("executed_by_this_owner") is True and begin.get("event_semantics") == "ACTUAL_CHILD_INVOCATION"
            and begin.get("command") == child["command"] == ["bash", v.mounted(profile["sources"]["entry"]["path"]), EXPECTED_AFTER_SLOT]
            and begin["pid"] == child["pid"] == child["identity"]["pid"]
            and child["identity"]["boot_id"] == native["owner_identity"]["boot_id"]
            and type(child.get("returncode")) is int and child["returncode"] == 0
            and exited.get("event") == "CHILD_EXIT" and exited.get("slot") == EXPECTED_AFTER_SLOT
            and type(exited.get("returncode")) is int and exited["returncode"] == 0
            and stopped.get("event") == "STOPPED_FAULT" and stopped.get("slot") == EXPECTED_AFTER_SLOT
            and stopped.get("error") == OLD_STOP_ERROR, "Uncollected frontier has no real successful child exit followed by the preserved stop")
    times = [v.timestamp(row["utc"], now) for row in events]
    require(times == sorted(times)
            and v.timestamp(prefix[-1]["finished_utc"], now) <= v.timestamp(exited["utc"], now)
            <= v.timestamp(child["finished_utc"], now) <= v.timestamp(native["finished_utc"], now) <= times[-1]
            and times[-1] <= v.timestamp(monitor["task"]["finished_utc"], now) <= v.timestamp(outer["finished_utc"], now),
            "Actual old frontier/process closure chronology differs")


def validate_profile(profile_path, *, native_originals=False, pending_pristine=True):
    """Read-only small evidence check; does not import ROS or launch anything."""
    profile = load(profile_path)
    v = review_library()
    inputs = v.Inputs(v.local_small_read)
    prepared = profile.get("status") == "PREPARED_NOT_REGISTERED" and profile.get("production_enabled") is False
    registered = (profile.get("status") == "REGISTERED_DEVELOPMENT_PREFIX11" and profile.get("production_enabled") is True
                  and PRODUCTION_ENABLED is True and PROFILE_STATUS == "REGISTERED_DEVELOPMENT_PREFIX11"
                  and sha(profile_path) == REGISTERED_PROFILE_SHA256)
    require((prepared or registered) and profile.get("schema_version") == 1
            and profile.get("scope") == "DEVELOPMENT_REMAINING_FIVE_AFTER_TRUE_STOPPED06" and profile.get("automatic_retry") is False
            and profile.get("conditional_identity_rule") == CONDITIONAL_IDENTITY
            and profile.get("formal_admission") is False,
            "Prepared development-only profile required")
    require(set(profile["sources"]) == SOURCE_NAMES, "Exact independently pinned source dependencies required")
    for binding in profile["sources"].values():
        inputs.bound(binding)
    require(profile["sources"]["plan"]["sha256"] == PLAN_SHA and profile["sources"]["entry"]["sha256"] == ENTRY_SHA,
            "Original plan/entry registration differs")
    plan = inputs.json(profile["sources"]["plan"])
    require(digest(plan, "plan_sha256") == plan["plan_sha256"] == profile["plan_digest"]
            and plan.get("mode") == "EXTENSION_PROBE" and plan.get("selected_seeds") == [4], "Wrong original development plan")
    require(profile.get("runner_sha256") == plan["source_hashes"]["scripts/run_reliability_v4.py"] == RUNNER_SHA
            and profile["sources"]["conditional_evaluator"]["sha256"] == plan["source_hashes"]["scripts/evaluate_stage1_flight.py"]
            and profile["sources"]["old_slot_library03"]["sha256"] == SLOT_LIBRARY_SHA,
            "Original frozen runner/evaluator/review source revision differs")
    inputs.bind_plan_results_alias(plan)
    prefix, pending = profile["closed_prefix"], profile["pending_ids"]
    ids = [row["id"] for row in plan["trials"]]
    require(len(ids) == len(set(ids)) == 16 and len(prefix) == EXPECTED_PREFIX_COUNT
            and [row["id"] for row in prefix] == ids[:11] and pending == ids[11:]
            and profile.get("after_slot") == ids[10] == EXPECTED_AFTER_SLOT,
            "Exact unchanged eleven-slot prefix and five-slot remainder required")
    if pending_pristine:
        for trial in plan["trials"][11:]:
            terminal = v.local_path(plan["output"]) / "slots" / (trial["id"] + ".json")
            alias = plan["frozen_root"] + "/results/"
            require(trial["directory"].startswith(alias), "Pending original trial does not use the authenticated results alias")
            directory = v.local_path(plan["results_root"] + "/" + trial["directory"][len(alias):])
            require(not terminal.exists() and not terminal.with_name(trial["id"] + ".started.json").exists()
                    and not directory.exists(), "No retry: a registered pending slot already has an attempt or directory")
    qualifications = []
    for trial, row in zip(plan["trials"], prefix):
        record, marker = inputs.json(row["terminal"]), inputs.json(row["marker"])
        require(record.get("id") == marker.get("id") == row["id"] == trial["id"]
                and record.get("plan_sha256") == marker.get("plan_sha256") == plan["plan_sha256"]
                and record.get("record_sha256") == row["record_sha256"] == digest(record, "record_sha256")
                and record.get("status") == row["original_status"]
                and record.get("started_utc") == marker.get("started_utc") == row["started_utc"]
                and record.get("finished_utc") == row["finished_utc"], "Original closed marker/terminal/content binding differs")
        expected_terminal = v.local_path(plan["output"]) / "slots" / (trial["id"] + ".json")
        require(v.local_path(row["terminal"]["path"]).resolve() == expected_terminal.resolve()
                and v.local_path(row["marker"]["path"]).resolve() == expected_terminal.with_name(trial["id"] + ".started.json").resolve(),
                "Profile relocated an original closed record")
        require(set(row["artifacts"]) == set(SMALL_ARTIFACTS), "Complete original small artifact family required")
        for name, binding in row["artifacts"].items():
            require(record["artifact_hashes"][name] == binding["sha256"], "Original small artifact pin differs")
            inputs.bound(binding)
        surface = inputs.json(row["artifacts"]["flight_evaluation.json"])
        behavior = behavior_qualification(surface, record, trial["id"], row["terminal"]["sha256"], HISTORY)
        qualifications.append({"id": trial["id"], "original_status": record["status"], **behavior})
        check_capture(plan, trial, v.local_path(row["artifacts"]["configuration/source_sha256.json"]["path"]), CAPTURE_PROFILES)
    manifest = inputs.json(profile["snapshot_manifest"])
    require(manifest.get("scope") == "ACTUAL_STOPPED_OWNER06_AND_REFUSED07_09_RAW_SMALL_FILES_ONLY"
            and len(manifest["files"]) == 17, "Exact original stopped-owner small snapshot required")
    snapshot_root = str(v.local_path(profile["snapshot_manifest"]["path"]).parent)
    for row in manifest["files"]:
        inputs.bound({"path": v.join(snapshot_root, row["copy"]), "sha256": row["sha256"]})
        # Only explicit native check reads native originals; Windows static
        # verification never touches UNC/WSL. Windows originals remain checked.
        if native_originals or not row["source"].startswith("\\\\"):
            inputs.bound({"path": row["source"], "sha256": row["sha256"]})
    docs, raw_hashes = {}, {}
    for key, binding in profile["closure_files"].items():
        raw = inputs.bound(binding)
        docs[key] = [v.parse(line) for line in raw.splitlines() if line.strip()] if key == "events06" else v.parse(raw)
        raw_hashes[key] = binding["sha256"]
    validate_stopped06(v, profile, plan, docs, raw_hashes, prefix)
    inputs.unchanged()
    return {"status": "BOUND_DEVELOPMENT_PREFIX11_NOT_ADMISSION", "profile": profile, "plan": plan,
            "closed_ids": ids[:11], "pending_ids": pending, "inputs": inputs, "library": v,
            "behavior_qualifications": qualifications,
            "native_originals_checked": native_originals, "original_stop_status": "STOPPED_FAULT", "original_stop_returncode": 2}


class PreservedProfileModule:
    """Recheck the admitted immutable evidence before every live-source scan."""
    def __init__(self, original, profile_path, original_chain, original_profile):
        self.original, self.profile_path = original, profile_path
        self.chain, self.old_profile = original_chain, original_profile
        self.profile_sha256 = sha(profile_path)

    def __getattr__(self, name):
        return getattr(self.original, name)

    def source_hashes(self, root):
        require(sha(self.profile_path) == self.profile_sha256, "Admitted continuation profile changed during collection")
        checked = validate_profile(self.profile_path, native_originals=True, pending_pristine=False)
        prior = self.chain.validate_continuation_profile(self.old_profile)
        require(prior["closed_ids"] == checked["closed_ids"][:3]
                and prior["after_slot"] == "person_extension_dropout_seed004",
                "Original three-slot chain no longer binds the old owner06 admission")
        return self.original.source_hashes(root)


def write_json(path, value):
    """Retry a transient sharing conflict without exposing partial JSON."""
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        deadline = time.monotonic() + 3.0
        while True:
            try:
                temporary.replace(path)
                return
            except OSError as error:
                conflict = error.errno == errno.EACCES or getattr(error, "winerror", None) in {5, 32, 33}
                if not conflict or time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
    finally:
        temporary.unlink(missing_ok=True)


def process_binding(pid):
    result = {"pid": pid, "boot_id": None, "start_ticks": None}
    if sys.platform == "linux":
        try:
            result.update(boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                          start_ticks=int((Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[19]))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return result


def wait_owned_child_after_metadata_fault(state, child):
    """Keep the WSL command alive until its real owned command exits."""
    if child is None:
        return
    if child.poll() is None:
        try:
            print(json.dumps({"event": "SUPERVISOR_METADATA_FAULT_WAITING_OWNED_CHILD",
                              "utc": utc(), "pid": child.pid,
                              "claim_boundary": "No next slot; the original command remains supervised until its actual exit."}),
                  file=sys.stderr, flush=True)
        except OSError:
            pass  # A broken diagnostic stream must not orphan the owned command.
    while child.poll() is None:
        time.sleep(.1)
    state.setdefault("current_child", {"pid": child.pid})
    state["current_child"].update(returncode=child.returncode, finished_utc=utc())
    state["metadata_fault_child_exit_observed"] = True


def collect(plan_path, entry, after_slot, output, pins, module, *, command_factory=None, poll_s=1.0, admission_binding=None):
    plan, closed, pending = initial_check(plan_path, entry, after_slot, pins, module)
    require(not output.exists(), "New owner output must not already exist; no automatic resume")
    output.mkdir(parents=True)
    state = {"scope": SCOPE, "claim_boundary": CLAIM, "started_utc": utc(), "status": "RUNNING",
             "plan": str(plan_path), "plan_sha256": plan["plan_sha256"], "plan_file_sha256": pins["plan"],
             "entry_sha256": pins["entry"], "initial_closed": closed, "collected": [], "current_slot": None,
             "owner_pid": os.getpid(), "owner_identity": process_binding(os.getpid()),
             "owner_source": {"path": str(Path(__file__).resolve()), "sha256": sha(Path(__file__))},
             "automatic_retry": False, "continuation_admission": admission_binding,
             "conditional_identity_rule": CONDITIONAL_IDENTITY, "formal_admission": False}
    original_pins = {row["slot_id"]: row["terminal_sha256"] for row in closed}
    marker_pins = {row["slot_id"]: row["original_marker"]["sha256"] for row in closed}

    def event(kind, **values):
        row = {"event": kind, "utc": utc(), "scope": SCOPE, **values}
        with (output / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, allow_nan=False) + "\n")
        state["heartbeat_utc"] = row["utc"]
        write_json(output / "state.json", state)

    def unchanged():
        require(sha(plan_path) == pins["plan"] and sha(entry) == pins["entry"], "Plan/entry changed during collection")
        require(module.source_hashes(Path(plan["frozen_root"])) == plan["source_hashes"], "Live source changed during collection")
        for slot, value in original_pins.items():
            require(sha(Path(plan["output"]) / "slots" / (slot + ".json")) == value, "Previously closed terminal changed: " + slot)
            require(sha(Path(plan["output"]) / "slots" / (slot + ".started.json")) == marker_pins[slot], "Previously closed started marker changed: " + slot)

    child = None
    try:
        event("COLLECTION_STARTED", pending_ids=[trial["id"] for trial in pending])
        for row in closed:
            observation = {"slot": row["slot_id"], "status": row["original_status"], "total": len(plan["trials"]),
                           "event_semantics": "DERIVED_OBSERVATION_OF_ORIGINAL_CLOSED_PREFIX",
                           "executed_by_this_owner": False,
                           **{key: row[key] for key in ("original_started_utc", "original_finished_utc", "original_terminal", "original_marker")}}
            event("START_SLOT", **observation)
            event("COMPLETE_SLOT", **observation)
        for trial in pending:
            unchanged()
            terminal = Path(plan["output"]) / "slots" / (trial["id"] + ".json")
            require(not terminal.exists() and not terminal.with_name(trial["id"] + ".started.json").exists()
                    and not Path(trial["directory"]).exists(), "No retry: next slot already has an attempt/directory")
            command = command_factory(trial) if command_factory is not None else ["bash", str(entry), trial["id"]]
            state["current_slot"] = trial["id"]
            started = utc()
            log = output / (trial["id"] + ".log")
            with log.open("x", encoding="utf-8") as handle:
                child = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)
                state["current_child"] = {"pid": child.pid, "command": command,
                                          "started_utc": started, "returncode": None}
                state["current_child"]["identity"] = process_binding(child.pid)
                event("START_SLOT", slot=trial["id"], pid=child.pid, command=command,
                      executed_by_this_owner=True, event_semantics="ACTUAL_CHILD_INVOCATION", total=len(plan["trials"]))
                while child.poll() is None:
                    state["heartbeat_utc"] = utc()
                    write_json(output / "state.json", state)
                    time.sleep(poll_s)
                code = child.returncode
            state["current_child"].update(returncode=code, finished_utc=utc())
            event("CHILD_EXIT", slot=trial["id"], returncode=code)
            require(code == 0, "Original single-slot CLI exited nonzero; no automatic retry")
            unchanged()
            checked = check_record(module, plan, trial, pins["capture_profiles"], pins["history"])
            original_pins[trial["id"]] = checked["terminal_sha256"]
            marker_pins[trial["id"]] = checked["original_marker"]["sha256"]
            state["collected"].append(checked)
            event("COMPLETE_SLOT", slot=trial["id"], status=checked["original_status"], terminal_sha256=checked["terminal_sha256"],
                  executed_by_this_owner=True, event_semantics="ACTUAL_CHILD_EXIT_AND_ORIGINAL_TERMINAL_VERIFIED", total=len(plan["trials"]))
        state.update(status="COLLECTION_FINISHED", current_slot=None, finished_utc=utc(), returncode=0)
        event("COLLECTION_FINISHED", collected_slots=len(state["collected"]))
    except (Exception, KeyboardInterrupt) as error:
        wait_owned_child_after_metadata_fault(state, child)
        state.update(status="STOPPED_FAULT", finished_utc=utc(), returncode=2, error=f"{type(error).__name__}: {error}")
        if child is not None and child.poll() is None:
            state["child_may_still_be_active"] = {"pid": child.pid, "note": "Supervisor stopped; no replacement task or automatic retry is launched"}
        try:
            event("STOPPED_FAULT", slot=state["current_slot"], error=state["error"])
        except OSError as persistence_error:
            print(json.dumps({"status": "STOPPED_FAULT", "error": state["error"],
                              "fault_record_write_error": str(persistence_error)}), file=sys.stderr, flush=True)
    write_json(output / "terminal.json", state)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--metadata-only", action="store_true", help="Read only Windows/local small evidence; no native source closure claim")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    execution_invoked = False
    try:
        if args.execute:
            require(PRODUCTION_ENABLED is True and PROFILE_STATUS == "REGISTERED_DEVELOPMENT_PREFIX11"
                    and isinstance(REGISTERED_PROFILE_SHA256, str) and sha(args.profile) == REGISTERED_PROFILE_SHA256,
                    "Production is disabled pending independent review and literal registration")
            require(not args.metadata_only, "Metadata-only verification cannot execute")
        if not args.metadata_only:
            require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22",
                    "Full check requires explicit native UAVHumble22; use --metadata-only on Windows")
        checked = validate_profile(args.profile, native_originals=not args.metadata_only)
        profile, plan, v = checked["profile"], checked["plan"], checked["library"]
        if args.metadata_only:
            print(json.dumps({"status": "METADATA_CHECK_ONLY_PREFIX11_NOT_NATIVE_SOURCE_CLOSURE",
                              "closed_ids": checked["closed_ids"], "pending_ids": checked["pending_ids"],
                              "original_stop_status": checked["original_stop_status"], "original_stop_returncode": 2,
                              "behavior_qualifications": checked["behavior_qualifications"],
                              "production_enabled": PRODUCTION_ENABLED, "claim_boundary": CLAIM}, allow_nan=False))
            return 0
        plan_path, entry = v.local_path(profile["sources"]["plan"]["path"]), v.local_path(profile["sources"]["entry"]["path"])
        runner = Path(plan["frozen_root"]) / "scripts/run_reliability_v4.py"
        original = fixed_module("humble54_pending07_original_runner", runner, RUNNER_SHA)
        old_chain = fixed_module("humble54_pending07_original_chain03", v.local_path(profile["sources"]["old_chain03"]["path"]),
                                 profile["sources"]["old_chain03"]["sha256"])
        old_profile = load(v.local_path(profile["sources"]["old_profile06"]["path"]))
        module = PreservedProfileModule(original, args.profile.resolve(strict=True), old_chain, old_profile)
        pins = {"plan": PLAN_SHA, "entry": ENTRY_SHA, "capture_profiles": CAPTURE_PROFILES, "history": HISTORY, "minimum_prefix": 11}
        _, closed, pending = initial_check(plan_path, entry, EXPECTED_AFTER_SLOT, pins, module)
        require([row["slot_id"] for row in closed] == checked["closed_ids"] and [row["id"] for row in pending] == checked["pending_ids"],
                "Full original validation did not bind the exact registered prefix11/remainder5")
        for row, bound in zip(closed, profile["closed_prefix"]):
            require(row["terminal_sha256"] == bound["terminal"]["sha256"] and row["original_marker"]["sha256"] == bound["marker"]["sha256"],
                    "Full validation observed different original closed bytes")
        if args.execute:
            output = Path(profile["native_output"])
            require(args.output is None or args.output.absolute() == output, "Only the registered fresh native output is permitted")
            for original in (Path(plan["frozen_root"]).resolve(), plan_path.parent.resolve(), Path(plan["results_root"]).resolve()):
                require(not output.resolve().is_relative_to(original) and not original.is_relative_to(output.resolve()), "Owner output must be external to frozen source and original results")
            require(not output.exists(), "No automatic resume: native owner output must be entirely fresh")
            admission_path = output.with_name(output.name + ".admission.json")
            admission = {"scope": "DEVELOPMENT_PREFIX11_ADMISSION_AFTER_TRUE_STOPPED06", "utc": utc(),
                         "profile": {"path": str(args.profile.resolve()), "sha256": sha(args.profile)},
                         "collector": {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)},
                         "owner_identity": process_binding(os.getpid()), "closed_ids": checked["closed_ids"],
                         "pending_ids": checked["pending_ids"], "original_stop_returncode": 2,
                         "conditional_identity_rule": CONDITIONAL_IDENTITY, "automatic_retry": False, "formal_admission": False}
            with admission_path.open("x", encoding="utf8", newline="\n") as handle:
                json.dump(admission, handle, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            execution_invoked = True
            result = collect(plan_path, entry, EXPECTED_AFTER_SLOT, output, pins, module,
                             admission_binding={"path": str(admission_path), "sha256": sha(admission_path)})
        else:
            result = {"scope": SCOPE, "status": "NATIVE_CHECK_ONLY_PREFIX11_NOT_STARTED", "closed": closed,
                      "pending_ids": [trial["id"] for trial in pending], "claim_boundary": CLAIM}
        print(json.dumps(result, allow_nan=False))
        return result.get("returncode", 0)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"scope": SCOPE,
            "status": "EXECUTION_ERROR_PARTIAL_RECORDS_RETAINED" if execution_invoked else "REFUSED_NOT_STARTED",
            "execution_invoked": execution_invoked, "error": f"{type(error).__name__}: {error}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
