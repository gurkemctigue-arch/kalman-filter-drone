"""Serial postprocessing of the independent 16 engineering bags, after all flights.

Run this MAIN-COPY tool with the frozen checkout's run_research_session.sh.
It calls only the existing frozen evaluators; never builds, flies, or retries
failed/interrupted tasks. Existing reports and partial sidecars are preserved.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from collections import Counter

TERMINAL = {"PASS", "FAIL", "INCOMPLETE", "INTERRUPTED"}
STUDY_WRITERS = {"run_full_plan_research.py", "run_extended_engineering.py",
                 "run_stage23_matrix.py", "run_stage1_trial.py", "run_stage1_repetitions.py"}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load(path):
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Expected a small JSON, not a bag or image: " + str(path))
    def invalid(value):
        raise ValueError("Non-finite JSON: " + value)
    value = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object: " + str(path))
    return value


def evidence(path):
    path = Path(path)
    item = {"path": str(path.resolve()), "exists": path.is_file()}
    if item["exists"]:
        item.update(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return item


def validate_inputs(main, extension, plan=None, offline=None):
    rows = main.get("trials", [])
    if (main.get("schema_version") != 1 or main.get("planned_flights") != 166
            or len(rows) != 166 or len({row.get("name") for row in rows}) != 166
            or any(row.get("result") not in TERMINAL for row in rows)):
        raise ValueError("All 166 distinct main flights must be terminal before supplementary postprocessing")
    if main.get("all_offline_slots_attempted") is not True:
        raise ValueError("Complete the frozen main offline phase before supplementary postprocessing")
    if plan is not None:
        plan_trials = plan.get("trials", [])
        if (plan.get("schema_version") != 1 or plan.get("plan_sha256") != main.get("plan_sha256")
                or len(plan_trials) != 166 or len({trial.get("name") for trial in plan_trials}) != 166
                or {trial.get("name") for trial in plan_trials} != {row.get("name") for row in rows}):
            raise ValueError("The main summary is not bound to the frozen 166-slot plan")
        if offline is None:
            raise ValueError("The frozen offline manifest is required for terminal bookkeeping")
        offline_rows = offline.get("trials")
        allowed = {"RECORDED", "INCOMPLETE_EVIDENCE", "INTERRUPTED", "NOT_APPLICABLE_NO_SELECTED_TASK"}
        if (offline.get("schema_version") != 1 or offline.get("plan_sha256") != plan.get("plan_sha256")
                or not isinstance(offline_rows, dict) or set(offline_rows) != {trial["name"] for trial in plan_trials}
                or any(row.get("status") not in allowed for row in offline_rows.values())):
            raise ValueError("The frozen offline manifest is missing slots or has nonterminal/foreign statuses")
        if dict(Counter(row["status"] for row in offline_rows.values())) != main.get("offline_status_counts", {}):
            raise ValueError("Summary offline status counts do not match the frozen offline manifest")
    offline = main.get("offline_status_counts", {})
    allowed_offline = {"RECORDED", "INCOMPLETE_EVIDENCE", "INTERRUPTED", "NOT_APPLICABLE_NO_SELECTED_TASK"}
    if (sum(value for value in offline.values() if type(value) is int and value >= 0) != 166
            or any(key not in allowed_offline or type(value) is not int or value < 0 for key, value in offline.items())):
        raise ValueError("All 166 main offline slots must have explicit terminal bookkeeping")
    plan = extension.get("plan") or {}
    slots = extension.get("slots", [])
    trials = plan.get("trials", [])
    if (extension.get("schema_version") != 1 or extension.get("source") != "EXTENDED_ENGINEERING_16_FLIGHTS"
            or plan.get("expected_trials") != 16 or plan.get("primary_166_included") is not False
            or len(slots) != 16 or len(trials) != 16 or extension.get("plan_sha256") != digest(plan)
            or [slot.get("trial") for slot in slots] != trials
            or len({trial.get("name") for trial in trials}) != 16
            or any(slot.get("status") not in TERMINAL for slot in slots)):
        raise ValueError("The independent 16-slot frozen manifest must be bound, distinct and entirely terminal")
    main_names = {row["name"] for row in rows}
    for trial in trials:
        name = trial.get("name", "")
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,180}", name)
                or name in main_names or trial.get("stage") != 1 or trial.get("target_class") not in {"person", "car"}
                or any(not isinstance(trial.get(key), (int, float)) or isinstance(trial[key], bool)
                       or not math.isfinite(trial[key]) or trial[key] <= 0
                       for key in ("desired_distance_m", "desired_height_m"))):
            raise ValueError("Invalid or overlapping engineering trial binding: " + str(name))
    return trials


def active_simulation_processes(proc_root=Path("/proc")):
    """Read Linux process metadata; no simulator commands or process signals."""
    if not proc_root.is_dir():
        raise ValueError("Linux /proc is required to certify an idle simulation window")
    active = []
    ancestors = {os.getpid()}
    if proc_root.resolve() == Path("/proc"):
        current = os.getpid()
        while current > 1:
            try:
                fields = (proc_root / str(current) / "stat").read_text().split()
                current = int(fields[3])
            except (FileNotFoundError, ProcessLookupError, ValueError, IndexError):
                break
            ancestors.add(current)
    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name) in ancestors:
            continue
        try:
            comm = (entry / "comm").read_text().strip()
            argv = [part.decode(errors="replace") for part in (entry / "cmdline").read_bytes().split(b"\0") if part]
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as error:
            raise ValueError("Cannot inspect a process; idle state is unverified: " + entry.name) from error
        names = {Path(arg).name.lower() for arg in argv}
        commandline = " ".join([comm, *argv]).lower()
        gz_sim = any("gz-sim" in arg for arg in argv) or ("gz" in names and "sim" in argv)
        active_markers = ("ros2 launch", "ros2 bag record", "microxrceagent", "uav_tracking_",
                          "stage1_flight_monitor.py", "sensor_fault_bridge.py")
        if (comm.lower() in {"px4", "gzserver", "gzclient", "gazebo"} or gz_sim
                or names & {name.lower() for name in STUDY_WRITERS}
                or any(marker in commandline for marker in active_markers)):
            active.append({"pid": int(entry.name), "comm": comm, "argv": argv})
    return active


@contextmanager
def exclusive_idle_window(root):
    if os.name != "posix":
        raise ValueError("Run under the frozen Linux ROS environment, not Windows Python")
    import fcntl
    with (root / "results/.full_plan_research.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("A frozen main/engineering writer is still active") from error
        try:
            active = active_simulation_processes()
            if active:
                raise ValueError("Simulation/study process still active: " + json.dumps(active, ensure_ascii=False))
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def evaluation_tasks(root, trial, python=sys.executable):
    directory = root / "results" / trial["name"]
    return [
        ("online_state_accuracy", directory / "online_state_accuracy_v2.json",
         [python, str(root / "scripts/evaluate_online_state_accuracy.py"), str(directory),
          "--target-class", trial["target_class"], "--vehicle-model", "x500_stage1",
          "--anchor-report", str(root / "results/recorded_estimator_research/research_report.json"),
          "--output", str(directory / "online_state_accuracy_v2.json")]),
        ("follow_dynamics", directory / "follow_dynamics.json",
         [python, str(root / "scripts/evaluate_follow_dynamics.py"), str(directory),
          "--target-class", trial["target_class"], "--output", str(directory / "follow_dynamics.json")]),
    ]


def resolve_bound_path(value, root):
    path = Path(value)
    return (path if path.is_absolute() else Path(root) / path).resolve()


def validate_report(path, kind, trial, directory, root):
    report = load(path)
    expected_directory = directory.resolve()
    reported_trial = report.get("trial")
    if not reported_trial or resolve_bound_path(reported_trial, root) != expected_directory:
        raise ValueError("Report trial path is absent or belongs to another engineering directory")
    reported_bag = (report.get("bag") or {}).get("bag") or (report.get("inputs") or {}).get("bag")
    if not reported_bag or resolve_bound_path(reported_bag, root) != (directory / "rosbag").resolve():
        raise ValueError("Report bag/input path is absent or belongs to another engineering directory")
    expected_sidecar = path.with_suffix(".frames.jsonl").resolve()
    if not report.get("frame_sidecar") or resolve_bound_path(report["frame_sidecar"], root) != expected_sidecar:
        raise ValueError("Report frame sidecar is absent or not bound to its report")
    if kind == "online_state_accuracy":
        if (report.get("schema_version") != 2 or report.get("target_class") != trial["target_class"]
                or not isinstance(report.get("online_state_accuracy", {}).get("metrics"), dict)):
            raise ValueError("Invalid online report/schema/class")
    else:
        ref = report.get("reference") or {}
        if (report.get("schema_version") != 1 or report.get("evaluation_status") != "RECORDED_WITH_CENSORED_FAILURES"
                or not isinstance(report.get("visual_control_metrics"), dict)
                or not math.isclose(ref.get("desired_horizontal_distance_m", math.nan), trial["desired_distance_m"], abs_tol=1e-6)
                or not math.isclose(ref.get("desired_height_above_model_origin_m", math.nan), trial["desired_height_m"], abs_tol=1e-6)):
            raise ValueError("Invalid dynamics report or recorded reference differs from frozen engineering trial")
    if not path.with_suffix(".frames.jsonl").is_file():
        raise ValueError("Report frame sidecar missing; existing evidence will not be overwritten")


def save(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def execute(root, output, manifest, *, runner=subprocess.run, idle_check=active_simulation_processes):
    """Caller holds frozen writer lock; every attempted output remains immutable."""
    for slot in manifest["slots"]:
        if slot["status"] == "RUNNING_ANALYSIS":
            slot.update(status="INTERRUPTED", reason="Prior supplementary process ended; no automatic retry")
    save(output / "manifest.json", manifest)
    for slot in manifest["slots"]:
        if slot["status"] != "PENDING":
            continue
        if idle_check():
            raise ValueError("Simulation/study became active before the next supplementary slot")
        trial = slot["trial"]
        directory = root / "results" / trial["name"]
        slot.update(status="RUNNING_ANALYSIS", started_utc=now(), tasks=[])
        save(output / "manifest.json", manifest)
        config_path = directory / "run_config.json"
        slot["configuration_sources"] = [evidence(config_path)]
        for candidate in (directory / "configuration/runtime_parameters.yaml",
                          directory / f"configuration/stage1_tracking_{trial['target_class']}.yaml"):
            if candidate.is_file():
                slot["configuration_sources"].append(evidence(candidate))
        try:
            config = load(config_path)
            if (config.get("target_class") != trial["target_class"] or config.get("stage") != 1
                    or config.get("name") != trial["name"] or config.get("command_mode") != trial["command_mode"]
                    or not math.isclose(config.get("desired_distance_m", math.nan), trial["desired_distance_m"], abs_tol=1e-6)):
                raise ValueError("Recorded run_config differs from bound engineering class/stage/name/mode/distance")
            if config.get("desired_height_m") is not None and not math.isclose(config["desired_height_m"], trial["desired_height_m"], abs_tol=1e-6):
                raise ValueError("Recorded run_config differs from bound engineering height reference")
            if not (directory / "rosbag/metadata.yaml").is_file():
                raise ValueError("Recorded bag metadata missing; failed flight retained")
        except (OSError, ValueError, TypeError) as error:
            slot.update(status="INCOMPLETE_EVIDENCE", reason=str(error), finished_utc=now())
            save(output / "manifest.json", manifest)
            continue
        for kind, report_path, argv in evaluation_tasks(root, trial):
            task = {"kind": kind, "argv": argv, "started_utc": now(), "report": str(report_path)}
            slot["tasks"].append(task)
            save(output / "manifest.json", manifest)
            try:
                if report_path.exists() or report_path.with_suffix(".frames.jsonl").exists():
                    task["status"] = "PREEXISTING_RECORDED_REPORT"
                else:
                    if idle_check():
                        raise ValueError("Simulation/study became active before an evaluator")
                    log = output / "logs" / f"{trial['name']}_{kind}.log"
                    task["log"] = str(log)
                    with log.open("x", encoding="utf-8") as handle:
                        completed = runner(argv, cwd=root, stdout=handle, stderr=subprocess.STDOUT, check=False)
                    task["returncode"] = completed.returncode
                    if completed.returncode:
                        raise ValueError("Frozen evaluator returned nonzero; partial outputs retained")
                    task["status"] = "RECORDED"
                validate_report(report_path, kind, trial, directory, root)
            except (OSError, ValueError, KeyError, TypeError) as error:
                task.update(status="INCOMPLETE_EVIDENCE", reason=str(error))
            task.update(finished_utc=now(), source=evidence(report_path))
            sidecar = report_path.with_suffix(".frames.jsonl")
            task["frame_sidecar"] = evidence(sidecar)
            save(output / "manifest.json", manifest)
        slot.update(status="RECORDED" if all(task["status"] in {"RECORDED", "PREEXISTING_RECORDED_REPORT"} for task in slot["tasks"]) else "INCOMPLETE_EVIDENCE",
                    finished_utc=now())
        save(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--engineering-manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--offline-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    try:
        root = args.frozen_root.resolve()
        with exclusive_idle_window(root):
            main_summary = load(args.summary)
            extra = load(args.engineering_manifest)
            frozen_plan = load(args.plan)
            offline_manifest = load(args.offline_manifest)
            trials = validate_inputs(main_summary, extra, frozen_plan, offline_manifest)
            protected = [args.summary, args.engineering_manifest, args.plan, args.offline_manifest,
                         root / "scripts/evaluate_online_state_accuracy.py", root / "scripts/evaluate_follow_dynamics.py",
                         root / "results/recorded_estimator_research/research_report.json",
                         root / "scripts/run_research_session.sh", root / "scripts/ros_python.sh", Path(__file__)]
            plan = {"source_main_plan_sha256": main_summary.get("plan_sha256"),
                    "source_engineering_plan_sha256": extra["plan_sha256"], "frozen_root": str(root),
                    "sources": [evidence(path) for path in protected], "trials": trials,
                    "scope": "Postprocess existing independent 16 flights; no new flights/repeats; no acceptance threshold changes"}
            if any(not source["exists"] for source in plan["sources"]):
                raise ValueError("Frozen evaluator, anchor, wrapper or input JSON is missing")
            output = args.output.resolve()
            results_root = (root / "results").resolve()
            if (output.parent != results_root
                    or output in {root, results_root}
                    or any(output == (root / "results" / trial["name"]).resolve() for trial in trials)
                    or any(path.resolve() == output or path.resolve().is_relative_to(output) for path in protected)):
                raise ValueError("Use a new dedicated supplementary manifest directory")
            path = output / "manifest.json"
            if path.exists():
                if not args.resume:
                    raise ValueError("Existing supplementary manifest requires --resume; no overwrite")
                manifest = load(path)
                if (manifest.get("schema_version") != 1 or manifest.get("source") != "POST_FLIGHT_ENGINEERING_16_SUPPLEMENT"
                        or manifest.get("plan_sha256") != digest(plan) or manifest.get("plan") != plan
                        or [slot.get("trial") for slot in manifest.get("slots", [])] != trials
                        or any(slot.get("status") not in {"PENDING", "RUNNING_ANALYSIS", "INTERRUPTED", "RECORDED", "INCOMPLETE_EVIDENCE"}
                               for slot in manifest.get("slots", []))):
                    raise ValueError("Supplementary plan/source SHA changed; preserve prior manifest and use a new output directory")
            else:
                if output.exists() and any(output.iterdir()):
                    raise ValueError("Supplementary output directory is not empty")
                output.mkdir(parents=True, exist_ok=True)
                (output / "logs").mkdir()
                manifest = {"schema_version": 1, "source": "POST_FLIGHT_ENGINEERING_16_SUPPLEMENT",
                            "created_utc": now(), "plan_sha256": digest(plan), "plan": plan,
                            "slots": [{"trial": trial, "status": "PENDING"} for trial in trials]}
                save(path, manifest)
            if not args.plan_only:
                manifest = execute(root, output, manifest)
            counts = {}
            for slot in manifest["slots"]:
                counts[slot["status"]] = counts.get(slot["status"], 0) + 1
            print(json.dumps({"manifest": str(path), "status_counts": counts}, ensure_ascii=False))
            return 0 if args.plan_only or counts.get("RECORDED", 0) == 16 else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
