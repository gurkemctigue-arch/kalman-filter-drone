"""External one-slot continuation of unchanged frozen stage-two/three research.

Default operation only reads a plan and prints its exact frozen-master command.
Execution never imports/patches the frozen master, edits frozen source/plan,
retries a terminal trial or launches more than one pending slot per child.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

MAIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MAIN_ROOT))
from uav_tracking.research_failures import classify_infrastructure_failure
from run_full_plan_supplement import active_simulation_processes

TERMINAL = {"PASS", "FAIL", "INCOMPLETE", "INTERRUPTED"}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load(path):
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Expected a small ledger, not a recording: " + str(path))
    def invalid(value):
        raise ValueError("Non-finite ledger JSON: " + value)
    value = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("Expected a ledger object: " + str(path))
    return value


def bound_path(root, value, *, within_results=True):
    relative = PurePosixPath(value)
    if ".." in relative.parts:
        raise ValueError("Parent traversal is forbidden")
    path = Path(value) if relative.is_absolute() else root.joinpath(*relative.parts)
    path = path.resolve()
    boundary = (root / "results").resolve() if within_results else root.resolve()
    if not path.is_relative_to(boundary):
        raise ValueError("Frozen artifact path escaped its declared root: " + str(value))
    return path


def read_plan(root, output, expected_sha):
    root = Path(root).resolve(strict=True)
    relative = PurePosixPath(output)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "results":
        raise ValueError("--study-output must preserve the original relative results/... spelling")
    plan_path = bound_path(root, str(relative / "plan.json"))
    plan = load(plan_path)
    canonical = {key: value for key, value in plan.items() if key not in {"created_utc", "plan_sha256"}}
    trials = plan.get("trials", [])
    if (plan.get("schema_version") != 1 or plan.get("frozen_root") != str(root)
            or plan.get("plan_sha256") != expected_sha or digest(canonical) != expected_sha
            or len(trials) != 166 or len({trial["name"] for trial in trials}) != 166
            or not plan.get("source_hashes")):
        raise ValueError("Frozen plan SHA/root/source map or exact 166-trial identity set differs")
    matrix_names = [name for matrix in plan["matrices"] for name in matrix["trial_names"]]
    if len(matrix_names) != 166 or set(matrix_names) != {trial["name"] for trial in trials}:
        raise ValueError("Frozen matrices do not bind the exact 166 trials")
    if sum(trial.get("stage") == 1 for trial in trials) != 100 or sum(trial.get("stage") in {2, 3} for trial in trials) != 66:
        raise ValueError("This continuation requires the original 100+66 study")
    return plan_path, plan


def frozen_command(root, output, plan):
    return ["bash", str(root / "scripts/run_research_session.sh"),
            str(root / "scripts/run_full_plan_research.py"), "--phase", "flights",
            "--output", str(PurePosixPath(output)), "--prefix", plan["prefix"],
            "--wall-timeout", str(plan["wall_timeout_s"]), "--resume", "--stop-after", "1"]


def verify_sources(root, plan):
    for name, expected in plan["source_hashes"].items():
        path = bound_path(root, name, within_results=False)
        if not path.is_file() or sha(path) != expected:
            raise ValueError("Frozen source differs from the preregistered SHA: " + name)
    preregistration = root / "planning/online_estimator_preregistration.json"
    if sha(preregistration) != plan.get("preregistration_sha256"):
        raise ValueError("Frozen preregistration SHA differs")


def snapshot(root, plan):
    records = {}
    expected_trials = {trial["name"]: trial for trial in plan["trials"]}
    for matrix in plan["matrices"]:
        path = bound_path(root, matrix["report"])
        expected_names = set(matrix["trial_names"])
        if path.is_file():
            child = load(path)
            if matrix["kind"] == "stage1":
                rows = [(row["name"], row.get("result"), row) for row in child["trials"]]
            elif matrix["kind"] == "stage23":
                slots = child["slots"]
                raw_trials = [slot["trial"] for slot in slots]
                if child.get("plan_sha256") != digest({"protocol": child["protocol"], "trials": raw_trials}):
                    raise ValueError("Stage-two/three child protocol digest differs")
                for trial in raw_trials:
                    parent = {key: value for key, value in expected_trials[trial["name"]].items() if key != "matrix"}
                    if trial != parent:
                        raise ValueError("Stage-two/three child trial differs from the frozen parent")
                rows = [(slot["trial"]["name"], slot.get("status"), slot) for slot in slots]
                if {name for name, _, _ in rows} != expected_names:
                    raise ValueError("Stage-two/three child is missing declared slots")
            else:
                raise ValueError("Unknown frozen matrix kind")
            if len(rows) != len({name for name, _, _ in rows}) or {name for name, _, _ in rows} - expected_names:
                raise ValueError("Duplicate or foreign child trial")
            for name, status, row in rows:
                if name in records or status not in TERMINAL | {"PENDING"}:
                    raise ValueError("Duplicate or active/unresolved trial ledger: " + name)
                records[name] = {"status": status, "row": row, "matrix_kind": matrix["kind"]}
        for name in matrix["trial_names"]:
            pending_row = ({"trial": {key: value for key, value in expected_trials[name].items() if key != "matrix"},
                            "status": "PENDING"} if matrix["kind"] == "stage23" else None)
            records.setdefault(name, {"status": "PENDING", "row": pending_row, "matrix_kind": matrix["kind"]})
    for trial in plan["trials"]:
        status = records[trial["name"]]["status"]
        if trial["stage"] == 1 and status not in TERMINAL:
            raise ValueError("All original 100 stage-one flights must already be terminal")
        if status == "PENDING" and (root / "results" / trial["name"]).exists():
            raise ValueError("Pending trial already has artifacts; refuse to adopt or overwrite: " + trial["name"])
    return records


def validate_transition(before, after, selected):
    if set(before) != set(after) or before[selected]["status"] != "PENDING" or after[selected]["status"] not in TERMINAL:
        raise ValueError("Exactly the selected pending slot must become terminal")
    changed = {name for name in before if before[name] != after[name]}
    if changed != {selected}:
        raise ValueError("Frozen master changed another trial or consumed more than one slot")


def assess_slot(root, trial, record, *, matrix_report=None):
    directory = root / "results" / trial["name"]
    row = record["row"] or {}
    expected = ({"auto_unique": "auto_unique_evaluation.json"} if trial["scenario"] == "auto_unique" else
                {"stage2_safety": "stage2_evaluation.json"} if trial["stage"] == 2 else
                {"flight": "flight_evaluation.json", "gimbal": "gimbal_evaluation.json"})
    commands = row.get("commands", [])
    evaluations = row.get("evaluations", [])
    errors = []
    kinds = [item.get("kind") for item in commands]
    if len(kinds) != len(set(kinds)) or set(kinds) != {"sitl", *expected}:
        errors.append("Missing/duplicate/unexpected frozen command records")
    if len(evaluations) != len(expected) or {item.get("kind") for item in evaluations} != set(expected):
        errors.append("Missing/duplicate evaluator records")
    attempts = []
    report_verdicts = []
    decoded_vehicle_counts = {}
    core_inputs_trustworthy = True
    for kind, filename in expected.items():
        command = next((item for item in commands if item.get("kind") == kind), {})
        evaluation = next((item for item in evaluations if item.get("kind") == kind), {})
        report_path = directory / filename
        if not report_path.is_file():
            errors.append("Missing evaluator report: " + filename)
        try:
            report = load(report_path)
            verdict = report["acceptance"]["result"] if kind == "flight" else report["result"]
            allowed = ({"PASS", "FAIL", "INCOMPLETE_EVIDENCE"} if kind in {"flight", "stage2_safety"} else
                       {"PASS", "FAIL_OR_INCOMPLETE"} if kind == "gimbal" else {"PASS", "FAIL"})
            if verdict not in allowed or (kind == "flight" and report.get("schema_version") != 3):
                raise ValueError("Invalid report verdict/schema")
            if kind == "auto_unique" and (report.get("schema_version") != 2
                    or report.get("source") != "OFFLINE_AUTO_UNIQUE_MULTIPLE_CANDIDATE_SAFETY"):
                raise ValueError("Unknown auto-unique report schema/source")
            if kind == "stage2_safety" and (report.get("schema_version") != 1
                    or report.get("source") != "OFFLINE_STAGE2_SAFETY_EVALUATION"):
                raise ValueError("Unknown stage-two report schema")
            if kind == "gimbal" and (report.get("schema_version") != 3
                    or report.get("evaluator_version") != "3_audited_paused_startup_feedback"):
                raise ValueError("Unknown gimbal report schema")
            metadata = report.get("inputs", report.get("metadata", {}))
            metadata = metadata if isinstance(metadata, dict) else {}
            types = metadata.get("topic_types", {})
            readable = (metadata.get("clock_recorded") is True
                        and type(metadata.get("clock_samples_read")) is int and metadata["clock_samples_read"] > 0
                        and isinstance(types, dict) and {"/clock", "/vehicle/odometry"} <= set(types)
                        and not metadata.get("read_errors") and not metadata.get("unavailable_types"))
            if not readable:
                core_inputs_trustworthy = False
                errors.append("Evaluator lacks trustworthy decoded core inputs: " + kind)
            if not metadata.get("bag") or bound_path(root, metadata["bag"]) != (directory / "rosbag").resolve():
                errors.append("Evaluator input bag is not bound to this trial: " + kind)
            configuration = report.get("configuration", {})
            configuration = configuration if isinstance(configuration, dict) else {}
            if kind in {"flight", "stage2_safety"}:
                if not isinstance(configuration, dict) or configuration.get("target_class") != trial["target_class"]:
                    errors.append("Evaluator target class differs from frozen trial: " + kind)
            if kind == "flight" and (configuration.get("desired_distance_m") != trial["desired_distance_m"]
                    or configuration.get("desired_height_m") != 2.0
                    or configuration.get("start_s") is not None or configuration.get("end_s") is not None):
                errors.append("Flight evaluator reference/window differs from frozen trial")
            if kind == "flight":
                count = report.get("topic_message_counts", {}).get("/vehicle/odometry")
                decoded_vehicle_counts[kind] = count
                if type(count) is not int or count <= 0:
                    errors.append("Flight report has no decoded vehicle odometry samples")
                    core_inputs_trustworthy = False
            if kind == "stage2_safety" and (configuration.get("terminal_expectation") != trial["terminal_expectation"]
                    or configuration.get("require_occlusions") is not trial["occlusions"]
                    or configuration.get("require_ambiguity") is not (trial["scenario"] == "ambiguity")):
                errors.append("Stage-two evaluator safety configuration differs from frozen trial")
            if kind == "auto_unique" and report.get("target_class") != trial["target_class"]:
                errors.append("Auto-unique evaluator class differs from frozen trial")
            if kind == "auto_unique":
                decoded_vehicle_counts[kind + "_tail_window"] = report.get("actual_final_vehicle_speed_mps", {}).get("count")
            if kind == "gimbal" and report.get("mode") != trial["gimbal_mode"]:
                errors.append("Gimbal evaluator mode differs from frozen trial")
            report_verdicts.append(verdict)
            if evaluation.get("result") != verdict or evaluation.get("error"):
                errors.append("Evaluator ledger/report outcome mismatch: " + kind)
        except (OSError, ValueError, KeyError, TypeError) as error:
            verdict = None
            core_inputs_trustworthy = False
            errors.append("Invalid evaluator report " + filename + ": " + str(error))
        code = command.get("returncode")
        expected_failure_code = kind in {"stage2_safety", "auto_unique"} and code == 2 and verdict in {"FAIL", "INCOMPLETE_EVIDENCE"}
        if type(code) is not int or (code != 0 and not expected_failure_code) or command.get("error"):
            errors.append("Unexpected evaluator execution status: " + kind)
        if evaluation.get("returncode") != code:
            errors.append("Evaluator returncode bookkeeping mismatch: " + kind)
        log_path = bound_path(root, command["log"]) if command.get("log") else None
        if log_path is None or not log_path.is_file():
            errors.append("Missing evaluator execution log: " + kind)
        if not evaluation.get("report") or bound_path(root, evaluation["report"]) != report_path.resolve():
            errors.append("Evaluator report path binding mismatch: " + kind)
        if matrix_report is not None:
            expected_log = Path(matrix_report).parent / "logs" / f"{trial['id']}_{kind}.log"
            if log_path != expected_log.resolve():
                errors.append("Evaluator log path differs from its frozen matrix/trial binding: " + kind)
        attempts.append({"report": str(report_path), "log": str(log_path) if log_path else None,
                         "returncode": code, "error": command.get("error")})
    sitl = next((item for item in commands if item.get("kind") == "sitl"), {})
    sitl_log = bound_path(root, sitl["log"]) if sitl.get("log") else None
    if sitl_log is None or not sitl_log.is_file():
        errors.append("Missing SITL execution log")
    if matrix_report is not None:
        expected_sitl_log = Path(matrix_report).parent / "logs" / f"{trial['id']}_sitl.log"
        if sitl_log != expected_sitl_log.resolve():
            errors.append("SITL log path differs from its frozen matrix/trial binding")
    ordinary_monitor_negative = False
    if sitl.get("returncode") == 1 and core_inputs_trustworthy and len(report_verdicts) == len(expected):
        try:
            monitor = load(directory / "summary.json")
            ordinary_monitor_negative = (type(monitor.get("monitor_exit_code")) is int and monitor["monitor_exit_code"] == 1
                and monitor.get("termination_reason") in {"wall_timeout", "follow_duration_reached", "no_follow_duration_reached"}
                and any(verdict != "PASS" for verdict in report_verdicts))
        except (OSError, ValueError):
            pass
    if (type(sitl.get("returncode")) is not int
            or (sitl.get("returncode") != 0 and not ordinary_monitor_negative) or sitl.get("error")):
        errors.append("Unexpected SITL execution status")
    infrastructure = classify_infrastructure_failure(directory, evaluator_attempts=attempts)
    if infrastructure["evidence"]["telemetry"]["vehicle_samples"] <= 0:
        errors.append("No independent runtime vehicle odometry samples were recorded")
    expected_status = ("PASS" if sitl.get("returncode") == 0 and len(evaluations) == len(expected)
                       and all(item.get("result") == "PASS" and item.get("returncode") == 0 for item in evaluations)
                       else "FAIL")
    if record["status"] != expected_status or row.get("status") != record["status"]:
        errors.append("Terminal slot status differs from the frozen execution/verdict formula")
    return {"stop": bool(errors) or infrastructure["stop"], "errors": errors,
            "infrastructure": infrastructure, "retained_flight_status": record["status"],
            "report_decoded_vehicle_counts_when_exposed": decoded_vehicle_counts,
            "stage2_schema1_vehicle_count_limit": "No generic bag odometry decode count in this schema; positive declared bag counts, available core types, decoded clock, no decoder errors and independent runtime vehicle samples are required",
            "ordinary_monitor_negative_result_permitted": ordinary_monitor_negative,
            "ordinary_completed_report_failure_is_not_infrastructure": True}


@contextmanager
def exclusive_guard(root):
    import fcntl
    # Coordinate guard invocations outside the immutable checkout. The master
    # retains sole ownership of its own writer lock while each child runs.
    path = Path("/tmp") / ("uav_tracking_guard_" + hashlib.sha256(str(root).encode()).hexdigest()[:24] + ".lock")
    with path.open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def idle_writer_window(root):
    import fcntl
    with (root / "results/.full_plan_research.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            active = active_simulation_processes()
            if active:
                raise ValueError("Simulation/research processes remain active: " + json.dumps(active))
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def execute(root, output, expected_sha, audit_output, max_new_flights=0):
    if os.name != "posix" or not re.fullmatch(r"/root/uav_tracking_fullplan_[A-Za-z0-9_]+", str(root)) or root == MAIN_ROOT:
        raise ValueError("Execute from the separate main-copy tool against a dedicated frozen Linux checkout")
    audit_output = Path(audit_output).resolve()
    if audit_output.is_relative_to(root) or audit_output.is_relative_to((root / "results").resolve()):
        raise ValueError("Guard audit output must be outside the frozen source and results")
    if audit_output.exists():
        raise FileExistsError("Guard audit output already exists; never replace a prior attempt")
    with exclusive_guard(root):
        return execute_locked(root, output, expected_sha, audit_output, max_new_flights)


def execute_locked(root, output, expected_sha, audit_output, max_new_flights):
    with idle_writer_window(root):
        plan_path, plan = read_plan(root, output, expected_sha)
        verify_sources(root, plan)
        initial = snapshot(root, plan)
        plan_bytes_sha = sha(plan_path)
        tool_sha = {str(path): sha(path) for path in (Path(__file__), MAIN_ROOT / "uav_tracking/research_failures.py",
                                                    MAIN_ROOT / "scripts/run_full_plan_supplement.py")}
        command = frozen_command(root, output, plan)
        audit_output.mkdir(parents=True)
        session = {"schema_version": 1, "created_utc": now(), "frozen_root": str(root),
                   "study_output_literal": output, "plan_sha256": expected_sha, "plan_file_sha256": plan_bytes_sha,
                   "tool_sources_sha256": tool_sha, "command": command,
                   "initial_terminal": sum(row["status"] in TERMINAL for row in initial.values()),
                   "scope": "Unchanged frozen master, original plan, one pending stage2/3 slot per invocation; no retries"}
        with (audit_output / "session.json").open("x", encoding="utf-8") as handle:
            json.dump(session, handle, ensure_ascii=False, indent=2, allow_nan=False)
    try:
        return continue_slots(root, plan, plan_path, plan_bytes_sha, tool_sha, command, audit_output, max_new_flights)
    except BaseException as error:
        with (audit_output / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"utc": now(), "event": "GUARD_STOPPED_EXCEPTION",
                         "exception_type": type(error).__name__, "message": str(error),
                         "action": "No next slot launched; retain artifacts and diagnose before a new guard session"},
                         ensure_ascii=False, allow_nan=False) + "\n")
        raise


def continue_slots(root, plan, plan_path, plan_bytes_sha, tool_sha, command, audit_output, max_new_flights):
    attempted = 0
    with (audit_output / "events.jsonl").open("x", encoding="utf-8") as journal:
        def emit(event):
            journal.write(json.dumps({"utc": now(), **event}, ensure_ascii=False, allow_nan=False) + "\n")
            journal.flush()
        while not max_new_flights or attempted < max_new_flights:
            with idle_writer_window(root):
                if sha(plan_path) != plan_bytes_sha or any(sha(path) != expected for path, expected in tool_sha.items()):
                    raise ValueError("Plan or external guard/classifier changed during continuation")
                before = snapshot(root, plan)
                pending = [trial for trial in plan["trials"] if before[trial["name"]]["status"] == "PENDING"]
                if not pending:
                    emit({"event": "ALL_166_FLIGHT_SLOTS_TERMINAL", "new_flights": attempted})
                    return 0
                trial = pending[0]
            # Release the frozen writer lock so the unmodified master can own
            # it. A competing writer makes the master's own lock fail closed.
            emit({"event": "ONE_SLOT_STARTED", "trial": trial, "argv": command})
            log_path = audit_output / f"master_{attempted:03d}_{trial['name']}.log"
            with log_path.open("x", encoding="utf-8") as handle:
                completed = subprocess.run(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT, check=False)
            attempted += 1
            with idle_writer_window(root):
                if sha(plan_path) != plan_bytes_sha or any(sha(path) != expected for path, expected in tool_sha.items()):
                    raise ValueError("Immutable plan or external guard/classifier changed during a flight")
                after = snapshot(root, plan)
                validate_transition(before, after, trial["name"])
                matrix = next(matrix for matrix in plan["matrices"] if trial["name"] in matrix["trial_names"])
                assessment = assess_slot(root, trial, after[trial["name"]], matrix_report=bound_path(root, matrix["report"]))
            emit({"event": "ONE_SLOT_FINISHED", "trial_name": trial["name"], "master_returncode": completed.returncode,
                  "master_log": str(log_path), "assessment": assessment})
            if completed.returncode != 0 or assessment["stop"]:
                emit({"event": "STOP_BEFORE_NEXT_SLOT", "remaining_pending": sum(row["status"] == "PENDING" for row in after.values())})
                return 2
        emit({"event": "REQUESTED_NEW_SLOT_LIMIT_REACHED", "new_flights": attempted})
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--study-output", required=True)
    parser.add_argument("--expected-plan-sha", required=True)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--max-new-flights", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.max_new_flights < 0:
            raise ValueError("--max-new-flights must be nonnegative")
        root = args.frozen_root.resolve(strict=True)
        _, plan = read_plan(root, args.study_output, args.expected_plan_sha)
        if args.execute:
            if args.audit_output is None:
                raise ValueError("--audit-output is required for execution")
            return execute(root, args.study_output, args.expected_plan_sha, args.audit_output, args.max_new_flights)
        print(json.dumps({"status": "PLAN_ONLY_NO_PROCESSES_OR_OUTPUT_FILES", "argv": frozen_command(root, args.study_output, plan)}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
