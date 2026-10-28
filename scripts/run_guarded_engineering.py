"""Guard the unchanged sixteen-flight runner after the full main study ends.

This main-copy tool never imports frozen algorithms, retries terminal slots,
opens bag databases, rewrites the 166-flight ledger or creates an engineering
plan. Freeze that separate manifest with the original --plan-only entry first.
Default invocation validates the existing ledgers without starting processes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

import run_guarded_full_plan as shared

MAIN_ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"PASS", "FAIL", "INTERRUPTED"}
OFFLINE_TERMINAL = {"RECORDED", "INCOMPLETE_EVIDENCE", "INTERRUPTED", "NOT_APPLICABLE_NO_SELECTED_TASK"}


def relative_output(root, value):
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "results":
        raise ValueError("Engineering output must preserve a relative results/... literal")
    return shared.bound_path(root, str(relative))


def main_readiness(root, output, expected_sha):
    """Bind all actual flight rows and all offline rows, not summary flags alone."""
    plan_path, plan = shared.read_plan(root, output, expected_sha)
    records = shared.snapshot(root, plan)
    if len(records) != 166 or any(row["status"] not in shared.TERMINAL for row in records.values()):
        raise ValueError("All original 166 flight slots must be terminal before engineering flights")
    directory = shared.bound_path(root, output)
    summary_path, offline_path = directory / "summary.json", directory / "offline_manifest.json"
    summary, offline = shared.load(summary_path), shared.load(offline_path)
    expected = set(records)
    rows = summary.get("trials", [])
    if (summary.get("schema_version") != 1 or summary.get("plan_sha256") != expected_sha
            or summary.get("planned_flights") != 166 or len(rows) != 166
            or {row.get("name") for row in rows} != expected
            or any(row.get("result") != records[row["name"]]["status"] for row in rows)
            or summary.get("all_flight_slots_terminal") is not True
            or summary.get("all_offline_slots_attempted") is not True
            or summary.get("status_counts") != dict(Counter(row["status"] for row in records.values()))):
        raise ValueError("Main summary does not bind the exact terminal 166-flight ledger")
    offline_rows = offline.get("trials", {})
    if (offline.get("schema_version") != 1 or offline.get("plan_sha256") != expected_sha
            or not isinstance(offline_rows, dict) or set(offline_rows) != expected
            or any(row.get("name") != name or row.get("status") not in OFFLINE_TERMINAL
                   for name, row in offline_rows.items())
            or summary.get("offline_status_counts") != dict(Counter(row["status"] for row in offline_rows.values()))):
        raise ValueError("All exact 166 offline slots must have valid, summary-consistent terminal records")
    paths = [plan_path, summary_path, offline_path]
    paths.extend(shared.bound_path(root, matrix["report"]) for matrix in plan["matrices"])
    protected = {str(path): shared.sha(path) for path in paths}
    return plan, protected


def read_engineering(root, output, main_plan):
    path = relative_output(root, output) / "manifest.json"
    manifest = shared.load(path)
    plan = manifest.get("plan", {})
    trials, slots = plan.get("trials", []), manifest.get("slots", [])
    prefix = plan.get("prefix", "")
    if (manifest.get("schema_version") != 1 or manifest.get("source") != "EXTENDED_ENGINEERING_16_FLIGHTS"
            or manifest.get("plan_sha256") != shared.digest(plan)
            or plan.get("expected_trials") != 16 or plan.get("primary_166_included") is not False
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}", prefix)
            or len(trials) != 16 or len({trial["name"] for trial in trials}) != 16
            or len({trial["id"] for trial in trials}) != 16 or len(slots) != 16
            or [slot.get("trial") for slot in slots] != trials
            or any(slot.get("status") not in TERMINAL | {"PENDING"} for slot in slots)):
        raise ValueError("Engineering manifest must bind its exact sixteen distinct inactive slots and plan digest")
    if (plan.get("source_hashes") != main_plan["source_hashes"]
            or plan.get("preregistration_sha256") != main_plan["preregistration_sha256"]
            or plan.get("resources") != main_plan["resources"]
            or plan.get("wall_timeout_s") != main_plan["wall_timeout_s"]
            or plan.get("render_backend") not in {"egl", "wslg"}):
        raise ValueError("Engineering sources/preregistration/resources differ from the frozen main study")
    main_names = {trial["name"] for trial in main_plan["trials"]}
    for trial, slot in zip(trials, slots):
        name = trial["name"]
        if (trial.get("stage") != 1 or trial.get("target_class") not in {"person", "car"}
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]+", name)
                or name != prefix + "_" + trial["id"] or name in main_names
                or trial.get("scope") != "single_flight_engineering_extension"
                or trial.get("independent_repeats_per_condition") != 1):
            raise ValueError("Engineering trial identity/scope is invalid or overlaps the primary denominator")
        if slot["status"] == "PENDING" and (root / "results" / name).exists():
            raise ValueError("Pending engineering trial already has artifacts; refuse adoption/overwrite: " + name)
    return path, manifest


def frozen_command(root, output, manifest):
    plan = manifest["plan"]
    return ["bash", str(root / "scripts/run_research_session.sh"),
            str(root / "scripts/run_extended_engineering.py"), "--prefix", plan["prefix"],
            "--output", str(PurePosixPath(output)), "--preregistration",
            str(root / "planning/online_estimator_preregistration.json"),
            "--wall-timeout", str(plan["wall_timeout_s"]), "--render-backend", plan["render_backend"],
            "--resume", "--stop-after", "1"]


def validate_transition(before, after, selected):
    if before["plan"] != after["plan"] or before["plan_sha256"] != after["plan_sha256"]:
        raise ValueError("Engineering plan changed during continuation")
    left = {slot["trial"]["name"]: slot for slot in before["slots"]}
    right = {slot["trial"]["name"]: slot for slot in after["slots"]}
    if (set(left) != set(right) or left[selected]["status"] != "PENDING"
            or right[selected]["status"] not in TERMINAL
            or {name for name in left if left[name] != right[name]} != {selected}):
        raise ValueError("Only the selected pending engineering slot may become terminal; historical results must stay unchanged")


def expected_outer_returncode(manifest):
    # Frozen runner reports every historical failure, even when this slot passes.
    return 2 if any(slot["status"] in {"FAIL", "INTERRUPTED"} for slot in manifest["slots"]) else 0


def runtime_errors(root, trial, plan):
    configuration = shared.load(root / "results" / trial["name"] / "run_config.json")
    expected = {key: trial[key] for key in (
        "name", "stage", "target_class", "seed", "speed_mps", "condition", "command_mode",
        "estimator_method", "target_mode", "motion_profile_kind", "desired_distance_m", "takeoff_height_m",
        "real_time_factor", "inference_image_size", "inference_threads", "occlusions", "reselect_after_loss")}
    expected.update(duration=trial["duration_s"], wall_timeout=plan["wall_timeout_s"],
                    render_backend=plan["render_backend"], no_bag=False, multi_target=False,
                    gazebo_seed=trial["seed"] + 1)
    weights = Path(trial["weights"])
    expected["model_path"] = str(weights if weights.is_absolute() else root / weights)
    return ["Runtime run_config differs from frozen engineering trial: " + key
            for key, value in expected.items() if configuration.get(key) != value]


def assess_slot(root, trial, slot, manifest, matrix_path):
    """Inspect small records and log samples only, never compressed recordings."""
    directory = root / "results" / trial["name"]
    report_path = directory / "offline_evaluation.json"
    commands, evaluations = slot.get("commands", []), slot.get("evaluations", [])
    errors, verdict, trustworthy = [], None, False
    if len(commands) != 2 or {row.get("kind") for row in commands} != {"sitl", "flight_eval"}:
        errors.append("Missing/duplicate/unexpected independent engineering command records")
    if len(evaluations) != 1 or evaluations[0].get("kind") != "schema3_flight":
        errors.append("Missing/duplicate/unexpected schema3 evaluator record")
    sitl = next((row for row in commands if row.get("kind") == "sitl"), {})
    evaluator = next((row for row in commands if row.get("kind") == "flight_eval"), {})
    evaluation = next((row for row in evaluations if row.get("kind") == "schema3_flight"), {})
    logs = {}
    for kind, record in (("sitl", sitl), ("flight_eval", evaluator)):
        try:
            log = shared.bound_path(root, record["log"])
            expected_log = matrix_path.parent / "logs" / f"{trial['id']}_{kind}.log"
            if log != expected_log.resolve() or not log.is_file():
                raise ValueError("Expected exact matrix/trial log does not exist")
            logs[kind] = log
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append("Invalid bound " + kind + " log: " + str(error))
    try:
        report = shared.load(report_path)
        verdict = report["acceptance"]["result"]
        if (report.get("schema_version") != 3 or report.get("source") != "OFFLINE_STAGE1_ROSBAG_EVALUATION"
                or verdict not in {"PASS", "FAIL", "INCOMPLETE_EVIDENCE"}):
            raise ValueError("Unexpected stage-one report schema/source/verdict")
        configuration, inputs = report.get("configuration", {}), report.get("inputs", {})
        if (any(configuration.get(key) != trial[key] for key in ("target_class", "desired_distance_m", "desired_height_m"))
                or configuration.get("start_s") is not None or configuration.get("end_s") is not None):
            errors.append("Evaluator class/distance/height/full-window configuration differs from this trial")
        for key, path in (("bag", directory / "rosbag"), ("telemetry_jsonl", directory / "telemetry.jsonl"),
                          ("monitor_summary", directory / "summary.json")):
            if not inputs.get(key) or shared.bound_path(root, inputs[key]) != path.resolve():
                errors.append("Evaluator input is not bound to this trial: " + key)
        types = inputs.get("topic_types", {})
        decoded_count = report.get("topic_message_counts", {}).get("/vehicle/odometry")
        trustworthy = (inputs.get("clock_recorded") is True and type(inputs.get("clock_samples_read")) is int
                       and inputs["clock_samples_read"] > 0 and isinstance(types, dict)
                       and {"/clock", "/vehicle/odometry"} <= set(types)
                       and not inputs.get("read_errors") and not inputs.get("unavailable_types")
                       and type(decoded_count) is int and decoded_count > 0)
        if not trustworthy:
            errors.append("Report lacks positive decoded clock/vehicle samples and readable core input evidence")
        if (evaluation.get("result") != verdict or evaluation.get("error")
                or evaluation.get("sha256") != shared.sha(report_path)
                or not evaluation.get("report")
                or shared.bound_path(root, evaluation["report"]) != report_path.resolve()):
            errors.append("Evaluator report path/SHA/verdict bookkeeping differs from the completed report")
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append("Missing or invalid completed engineering report: " + str(error))
    try:
        errors.extend(runtime_errors(root, trial, manifest["plan"]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append("Missing or invalid bound runtime configuration: " + str(error))
    code = evaluator.get("returncode")
    if type(code) is not int or code != 0 or evaluator.get("error") or evaluation.get("returncode") != code:
        errors.append("Unexpected evaluator execution status; completed negative reports normally return zero")
    ordinary_negative = False
    if sitl.get("returncode") == 1 and trustworthy and verdict in {"FAIL", "INCOMPLETE_EVIDENCE"}:
        try:
            monitor = shared.load(directory / "summary.json")
            ordinary_negative = (type(monitor.get("monitor_exit_code")) is int and monitor["monitor_exit_code"] == 1
                and monitor.get("termination_reason") in {"wall_timeout", "follow_duration_reached", "no_follow_duration_reached"})
        except (OSError, ValueError):
            pass
    if (type(sitl.get("returncode")) is not int or (sitl["returncode"] != 0 and not ordinary_negative)
            or sitl.get("error")):
        errors.append("Unexpected SITL execution status")
    expected = "PASS" if sitl.get("returncode") == 0 and len(evaluations) == 1 and all(
        row.get("returncode") == 0 and row.get("result") == "PASS" for row in evaluations) else "FAIL"
    if slot.get("status") != expected:
        errors.append("Terminal status differs from the frozen runner returncode/verdict formula")
    attempts = [{"report": str(report_path), "log": str(logs["flight_eval"]) if "flight_eval" in logs else None,
                 "returncode": code, "error": evaluator.get("error")}]
    infrastructure = shared.classify_infrastructure_failure(directory, evaluator_attempts=attempts)
    counts = infrastructure["evidence"]["bag"].get("topic_message_counts")
    if not isinstance(counts, dict) or any(type(counts.get(topic)) is not int or counts[topic] <= 0
                                           for topic in ("/clock", "/vehicle/odometry")):
        errors.append("Required bag metadata is not parseable with positive declared core message counts")
    if infrastructure["evidence"]["telemetry"]["vehicle_samples"] <= 0:
        errors.append("No independent runtime vehicle odometry samples were recorded")
    return {"stop": bool(errors) or infrastructure["stop"], "errors": errors, "infrastructure": infrastructure,
            "retained_flight_status": slot.get("status"), "ordinary_monitor_negative_result_permitted": ordinary_negative,
            "ordinary_completed_report_failure_is_not_infrastructure": True}


def verify_unchanged(protected, tools):
    for path, expected in {**protected, **tools}.items():
        if shared.sha(path) != expected:
            raise ValueError("Protected main ledger or external tool changed during engineering continuation: " + path)


def continue_slots(root, main_plan, output, manifest_sha, protected, tools, command, audit, limit):
    attempted = 0
    with (audit / "events.jsonl").open("x", encoding="utf-8") as journal:
        def emit(event):
            journal.write(json.dumps({"utc": shared.now(), **event}, ensure_ascii=False, allow_nan=False) + "\n")
            journal.flush()
        while not limit or attempted < limit:
            with shared.idle_writer_window(root):
                verify_unchanged(protected, tools)
                matrix_path, before = read_engineering(root, output, main_plan)
                if before["plan_sha256"] != manifest_sha:
                    raise ValueError("Engineering plan SHA changed during continuation")
                pending = [slot for slot in before["slots"] if slot["status"] == "PENDING"]
                if not pending:
                    emit({"event": "ALL_16_ENGINEERING_SLOTS_TERMINAL", "new_flights": attempted})
                    return 0
                trial = pending[0]["trial"]
            emit({"event": "ONE_SLOT_STARTED", "trial": trial, "argv": command})
            log = audit / f"engineering_{attempted:03d}_{trial['name']}.log"
            with log.open("x", encoding="utf-8") as handle:
                completed = subprocess.run(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT, check=False)
            attempted += 1
            with shared.idle_writer_window(root):
                verify_unchanged(protected, tools)
                _, after = read_engineering(root, output, main_plan)
                validate_transition(before, after, trial["name"])
                slot = next(row for row in after["slots"] if row["trial"]["name"] == trial["name"])
                assessment = assess_slot(root, trial, slot, after, matrix_path)
                expected_code = expected_outer_returncode(after)
            emit({"event": "ONE_SLOT_FINISHED", "trial_name": trial["name"], "runner_returncode": completed.returncode,
                  "expected_runner_returncode": expected_code, "runner_log": str(log), "assessment": assessment})
            if completed.returncode != expected_code or assessment["stop"]:
                emit({"event": "STOP_BEFORE_NEXT_SLOT", "remaining_pending": sum(row["status"] == "PENDING" for row in after["slots"])})
                return 2
        emit({"event": "REQUESTED_NEW_SLOT_LIMIT_REACHED", "new_flights": attempted})
        return 0


def execute(root, study_output, expected_sha, output, audit, limit=0):
    if os.name != "posix" or not re.fullmatch(r"/root/uav_tracking_fullplan_[A-Za-z0-9_]+", str(root)) or root == MAIN_ROOT:
        raise ValueError("Execute only from the main-copy tool against the separate frozen Linux checkout")
    audit = audit.resolve()
    if audit.is_relative_to(root) or audit.is_relative_to((root / "results").resolve()) or audit.exists():
        raise ValueError("Audit directory must be new and outside the frozen source and results")
    with shared.exclusive_guard(root):
        with shared.idle_writer_window(root):
            main_plan, protected = main_readiness(root, study_output, expected_sha)
            shared.verify_sources(root, main_plan)
            matrix_path, manifest = read_engineering(root, output, main_plan)
            tool_paths = [Path(__file__), Path(shared.__file__), MAIN_ROOT / "uav_tracking/research_failures.py",
                          MAIN_ROOT / "scripts/run_full_plan_supplement.py"]
            tools = {str(path): shared.sha(path) for path in tool_paths}
            command = frozen_command(root, output, manifest)
            audit.mkdir(parents=True)
            session = {"schema_version": 1, "created_utc": shared.now(), "frozen_root": str(root),
                       "main_plan_sha256": expected_sha, "engineering_plan_sha256": manifest["plan_sha256"],
                       "study_output_literal": study_output, "engineering_output_literal": output,
                       "engineering_manifest": str(matrix_path), "protected_main_files_sha256": protected,
                       "tool_sources_sha256": tools, "command": command,
                       "scope": "Independent sixteen conditions, one flight each; no retry or change to primary 166"}
            with (audit / "session.json").open("x", encoding="utf-8") as handle:
                json.dump(session, handle, ensure_ascii=False, indent=2, allow_nan=False)
        try:
            return continue_slots(root, main_plan, output, manifest["plan_sha256"], protected, tools, command, audit, limit)
        except BaseException as error:
            with (audit / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"utc": shared.now(), "event": "GUARD_STOPPED_EXCEPTION",
                    "exception_type": type(error).__name__, "message": str(error),
                    "action": "Retain all original results; diagnose before a fresh guard session; no next slot launched"},
                    ensure_ascii=False, allow_nan=False) + "\n")
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", required=True, type=Path)
    parser.add_argument("--study-output", required=True)
    parser.add_argument("--expected-main-plan-sha", required=True)
    parser.add_argument("--engineering-output", required=True)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--max-new-flights", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.max_new_flights < 0:
            raise ValueError("--max-new-flights must be nonnegative")
        root = args.frozen_root.resolve(strict=True)
        if args.execute:
            if args.audit_output is None:
                raise ValueError("Execution requires --audit-output")
            return execute(root, args.study_output, args.expected_main_plan_sha, args.engineering_output,
                           args.audit_output, args.max_new_flights)
        plan, protected = main_readiness(root, args.study_output, args.expected_main_plan_sha)
        shared.verify_sources(root, plan)
        _, manifest = read_engineering(root, args.engineering_output, plan)
        print(json.dumps({"status": "PLAN_ONLY_NO_PROCESSES_OR_OUTPUT_FILES", "main_terminal": 166,
              "main_offline_terminal": 166, "engineering_plan_sha256": manifest["plan_sha256"],
              "protected_main_files_sha256": protected,
              "argv": frozen_command(root, args.engineering_output, manifest)}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
