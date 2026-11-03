"""Prepared owner06 collector for the original pending slots; never change old verdicts.

The production CLI refuses until the actual closed prefix and owner chain are
reviewed and registered. Synthetic fixtures call the internal test seam only.
Uses the unchanged original single-slot entry and its original frozen validator.
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
import uuid

sys.dont_write_bytecode = True  # Importing the original validator must not write into its frozen tree.

SCOPE = "SUPERVISED_PENDING_COLLECTION"
PROFILE_STATUS = "PREPARED_NOT_AUTHORIZED_FOR_CONTINUATION"
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
    acceptance = surface["acceptance"]
    require(acceptance.get("missing_topics") == [] and type(acceptance.get("input_read_error_count")) is int
            and acceptance["input_read_error_count"] == 0 and acceptance.get("clock_timebase_available") is True
            and all(acceptance.get(key) is True for key in ("short_occlusion_recorded", "long_occlusion_recorded", "failed_events_retained"))
            and surface["flight_evidence"].get("armed_seen") is True and surface["flight_evidence"].get("offboard_seen") is True
            and type(surface["detector"].get("invalid_diagnostic_messages")) is int
            and surface["detector"]["invalid_diagnostic_messages"] == 0, "Surface recording/decoder/flight evidence incomplete")
    require(len(surface["occlusions"]) == 2, "Need exactly one original short and long window")
    known, unobserved = [], []
    for kind, algorithm in (("short", SHORT_ALGORITHM), ("long", LONG_ALGORITHM)):
        row = one(surface["occlusions"], kind)
        checks = row["checks"]
        require(row.get("complete") is True and all(checks.get(key) is True for key in (*SHUTTER, *(LONG_SAFE if kind == "long" else ()))), "Original shutter/long9 safety failed")
        for key in algorithm:
            value = checks.get(key)
            historical_null = (kind == "short" and key == "detector_interruption_observed" and value is None
                               and trial["id"] == OLD_SHORT_NULL and sha(path) == history.get(OLD_SHORT_NULL))
            require(type(value) is bool or historical_null, "New unknown behavior evidence; root must inspect: " + kind + ":" + key)
            if value is False:
                known.append("surface:" + kind + ":" + key + "=FAIL")
            elif value is None:
                unobserved.append("surface:" + kind + ":" + key + "=HISTORICAL_UNKNOWN_RETAINED")
    nav = nav_audit(module, plan, reports["navigation"])
    if nav["original_navigation_verdict"] == "FAIL":
        known.append("navigation:REGISTERED_PERFORMANCE_GATES_FAILED")
    expected, evidence = module.engineering_verdict(plan, trial, flight, record["evaluations"])
    require(expected == record["status"] == record["engineering_result"] and evidence == record["engineering_evidence"], "Original terminal verdict/evidence contradicts frozen validator")
    return {"slot_id": trial["id"], "original_status": record["status"], "terminal_sha256": sha(path),
            "original_terminal": {"path": str(path.resolve()), "sha256": sha(path)},
            "original_marker": {"path": str(marker_path.resolve()), "sha256": sha(marker_path)},
            "original_started_utc": marker["started_utc"], "original_finished_utc": record["finished_utc"],
            "record_sha256": record["record_sha256"], "known_algorithm_failures": known,
            "unobserved_checks": unobserved, "capture_binding": capture_binding, **nav}


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


def collect(plan_path, entry, after_slot, output, pins, module, *, command_factory=None, poll_s=1.0):
    plan, closed, pending = initial_check(plan_path, entry, after_slot, pins, module)
    require(not output.exists(), "New owner output must not already exist; no automatic resume")
    output.mkdir(parents=True)
    state = {"scope": SCOPE, "claim_boundary": CLAIM, "started_utc": utc(), "status": "RUNNING",
             "plan": str(plan_path), "plan_sha256": plan["plan_sha256"], "plan_file_sha256": pins["plan"],
             "entry_sha256": pins["entry"], "initial_closed": closed, "collected": [], "current_slot": None,
             "owner_pid": os.getpid(), "owner_identity": process_binding(os.getpid()),
             "owner_source": {"path": str(Path(__file__).resolve()), "sha256": sha(Path(__file__))},
             "automatic_retry": False}
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
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--entry", type=Path, required=True)
    parser.add_argument("--after-slot", required=True)
    parser.add_argument("--output", type=Path, help="Required only for explicit execution; must be entirely new")
    parser.add_argument("--execute", action="store_true", help="Explicitly start the sequential original pending commands")
    args = parser.parse_args(argv)
    execution_invoked = False
    try:
        require(PROFILE_STATUS == "REGISTERED_ACTUAL_CLOSED_PREFIX_CHAIN", "Continuation profile awaits actual previous-owner closure and prefix-chain review")
        plan_path, entry = args.plan.resolve(strict=True), args.entry.resolve(strict=True)
        require(sha(plan_path) == PLAN_SHA and sha(entry) == ENTRY_SHA, "Original plan/entry pin differs")
        plan = load(plan_path)
        runner = Path(plan["frozen_root"]) / "scripts/run_reliability_v4.py"
        require(sha(runner) == RUNNER_SHA, "Original runner pin differs")
        spec = importlib.util.spec_from_file_location("humble54_original_pending_collection_validator", runner)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        pins = {"plan": PLAN_SHA, "entry": ENTRY_SHA, "capture_profiles": CAPTURE_PROFILES, "history": HISTORY, "minimum_prefix": 0}
        if args.execute:
            require(sys.platform == "linux" and args.output is not None, "Execution requires native Linux and an explicit new output")
            output = args.output.absolute()
            for original in (Path(plan["frozen_root"]).resolve(), plan_path.parent.resolve(), Path(plan["results_root"]).resolve()):
                require(not output.resolve().is_relative_to(original) and not original.is_relative_to(output.resolve()), "Owner output must be external to frozen source and original results")
            execution_invoked = True
            result = collect(plan_path, entry, args.after_slot, output, pins, module)
        else:
            _, closed, pending = initial_check(plan_path, entry, args.after_slot, pins, module)
            result = {"scope": SCOPE, "status": "CHECK_ONLY_NOT_STARTED", "closed": closed,
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
