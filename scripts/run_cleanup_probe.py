"""Prepare or observe two isolated post-study shutdown engineering probes.

Default operation only prints a plan. --execute requires explicitly bound
166-flight/166-offline/16-engineering/16-supplement ledgers, a new cleanup
checkout, idle simulation processes and both workspace locks. No bag is read
and the frozen research checkout is never modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import time
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
COMMON_NODES = {"parameter_bridge", "px4_adapter", "flight_tf", "detector",
                "state_estimator", "controller", "flight_supervisor"}
FLIGHT_TERMINAL = {"PASS", "FAIL", "INCOMPLETE", "INTERRUPTED"}
OFFLINE_TERMINAL = {"RECORDED", "INCOMPLETE_EVIDENCE", "INTERRUPTED",
                    "NOT_APPLICABLE_NO_SELECTED_TASK"}
SUPPLEMENT_TERMINAL = {"RECORDED", "INCOMPLETE_EVIDENCE", "INTERRUPTED"}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Expected a small evidence JSON, not a recording: " + str(path))

    def invalid(value):
        raise ValueError("Non-finite evidence JSON: " + value)

    value = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("Expected an evidence JSON object: " + str(path))
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def validate_completed_research(results, *, formal_plan, offline_manifest,
                                engineering_manifest, supplement_manifest):
    """Read actual small ledgers, rather than trusting completion booleans."""
    results = Path(results).resolve(strict=True)

    def bound_input(path):
        path = Path(path).resolve(strict=True)
        if not path.is_file() or not path.is_relative_to(results):
            raise ValueError("Evidence input must remain within the declared formal results: " + str(path))
        return path

    plan_path, offline_path, engineering_path, supplement_path = [bound_input(path) for path in
        (formal_plan, offline_manifest, engineering_manifest, supplement_manifest)]
    if len({plan_path, offline_path, engineering_path, supplement_path}) != 4:
        raise ValueError("The four formal evidence inputs must be distinct")
    if plan_path.parent != offline_path.parent:
        raise ValueError("The offline manifest must belong to the explicit main study directory")
    plan = load(plan_path)
    canonical = {key: value for key, value in plan.items() if key not in {"created_utc", "plan_sha256"}}
    names = {trial["name"] for trial in plan["trials"]}
    if (plan.get("schema_version") != 1 or plan.get("plan_sha256") != digest(canonical)
            or len(plan["trials"]) != 166 or len(names) != 166):
        raise ValueError("Primary plan digest or 166 distinct trial names are invalid")
    evidence = [plan_path]
    flights = {}
    declared = []
    original_results = PurePosixPath(plan["frozen_root"]) / "results"

    def declared_result_path(path):
        original = PurePosixPath(path)
        if ".." in original.parts:
            raise ValueError("Declared evidence path contains a parent traversal")
        if not original.is_absolute():
            original = PurePosixPath(plan["frozen_root"]) / original
        try:
            relative = original.relative_to(original_results)
        except ValueError:
            # Sources may have recorded the resolved data-drive path instead
            # of the frozen checkout's results symlink.
            return bound_input(path)
        return bound_input(results.joinpath(*relative.parts))

    for matrix in plan["matrices"]:
        report_path = declared_result_path(matrix["report"])
        child = load(report_path)
        evidence.append(report_path)
        if matrix["kind"] == "stage1":
            rows = [(row["name"], row.get("result")) for row in child["trials"]]
        elif matrix["kind"] == "stage23":
            rows = [(slot["trial"]["name"], slot.get("status")) for slot in child["slots"]]
        else:
            raise ValueError("Unknown primary matrix kind")
        matrix_names = matrix["trial_names"]
        if len(rows) != len(matrix_names) or {name for name, _ in rows} != set(matrix_names):
            raise ValueError("A primary child ledger is missing, duplicated or belongs to another plan")
        for name, status in rows:
            if name in flights or status not in FLIGHT_TERMINAL:
                raise ValueError(f"Primary flight not uniquely terminal: {name}: {status}")
            flights[name] = status
        declared.extend(matrix_names)
    if len(declared) != 166 or set(declared) != names or set(flights) != names:
        raise ValueError("Primary child ledgers do not cover the exact 166-flight denominator")
    offline = load(offline_path)
    evidence.append(offline_path)
    rows = offline.get("trials", {})
    if (offline.get("schema_version") != 1 or offline.get("plan_sha256") != plan["plan_sha256"] or set(rows) != names
            or any(row.get("name") != name or row.get("status") not in OFFLINE_TERMINAL
                   for name, row in rows.items())):
        raise ValueError("All 166 bound offline attempts must be terminal before cleanup probes")
    engineering = load(engineering_path)
    evidence.append(engineering_path)
    engineering_plan = engineering["plan"]
    slots = engineering["slots"]
    trials = engineering_plan["trials"]
    if (engineering.get("schema_version") != 1 or engineering.get("source") != "EXTENDED_ENGINEERING_16_FLIGHTS"
            or engineering.get("plan_sha256") != digest(engineering_plan)
            or len(trials) != 16 or len({trial["name"] for trial in trials}) != 16
            or engineering_plan.get("expected_trials") != 16
            or engineering_plan.get("primary_166_included") is not False
            or not plan.get("source_hashes")
            or engineering_plan.get("source_hashes") != plan["source_hashes"]
            or engineering_plan.get("preregistration_sha256") != plan.get("preregistration_sha256")
            or names & {trial["name"] for trial in trials}
            or [slot.get("trial") for slot in slots] != trials
            or any(slot.get("status") not in FLIGHT_TERMINAL for slot in slots)):
        raise ValueError("The independent sixteen-slot engineering ledger must be bound and terminal")
    supplement = load(supplement_path)
    evidence.append(supplement_path)
    supplement_plan = supplement.get("plan", {})
    supplement_slots = supplement.get("slots", [])
    if (supplement.get("schema_version") != 1
            or supplement.get("source") != "POST_FLIGHT_ENGINEERING_16_SUPPLEMENT"
            or supplement.get("plan_sha256") != digest(supplement_plan)
            or supplement_plan.get("frozen_root") != plan["frozen_root"]
            or supplement_plan.get("source_main_plan_sha256") != plan["plan_sha256"]
            or supplement_plan.get("source_engineering_plan_sha256") != engineering["plan_sha256"]
            or supplement_plan.get("trials") != trials
            or [slot.get("trial") for slot in supplement_slots] != trials
            or any(slot.get("status") not in SUPPLEMENT_TERMINAL for slot in supplement_slots)):
        raise ValueError("All sixteen supplementary slots must be terminal and bound to both frozen plans")
    for slot in supplement_slots:
        if slot["status"] == "RECORDED":
            tasks = slot.get("tasks", [])
            if (len(tasks) != 2 or {task.get("kind") for task in tasks}
                    != {"online_state_accuracy", "follow_dynamics"}
                    or any(task.get("status") not in {"RECORDED", "PREEXISTING_RECORDED_REPORT"}
                           or (task.get("status") == "RECORDED" and task.get("returncode") != 0)
                           for task in tasks)):
                raise ValueError("A recorded supplementary slot has incomplete analysis task bookkeeping")
    # The supplement hashes its source plan, offline manifest and independent
    # engineering manifest. Check the current input bytes as well as plan IDs;
    # otherwise an old supplement could authorize cleanup after ledger changes.
    required_sources = {plan_path, offline_path, engineering_path}
    matched = set()
    for source in supplement_plan.get("sources", []):
        try:
            source_path = declared_result_path(source["path"])
        except (OSError, ValueError):
            continue  # Frozen evaluators/anchor are outside this readiness scope.
        if source_path not in required_sources:
            continue
        if (source_path in matched or source.get("exists") is not True
                or source.get("bytes") != source_path.stat().st_size
                or source.get("sha256") != sha(source_path)):
            raise ValueError("Supplement source SHA/size binding differs from the current formal ledgers")
        matched.add(source_path)
    if matched != required_sources:
        raise ValueError("Supplement is missing exact source SHA bindings for the formal ledgers")
    return {"primary_plan_sha256": plan["plan_sha256"], "primary_flights_terminal": 166,
            "primary_offline_terminal": 166, "engineering_terminal": 16,
            "engineering_plan_sha256": engineering["plan_sha256"],
            "supplement_plan_sha256": supplement["plan_sha256"], "supplement_terminal": 16,
            "supplement_status_counts": dict(Counter(slot["status"] for slot in supplement_slots)),
            "explicit_inputs": {"formal_plan": str(plan_path), "offline_manifest": str(offline_path),
                                "engineering_manifest": str(engineering_path),
                                "supplement_manifest": str(supplement_path)},
            "completion_does_not_mean_all_pass": True,
            "protected_files_sha256": {str(path): sha(path) for path in evidence}}


def probe_plan(probe, prefix, root=ROOT):
    if not re.fullmatch(r"cleanup_[A-Za-z0-9_-]{1,60}", prefix):
        raise ValueError("A separate cleanup_ prefix is required")
    name = f"{prefix}_{probe}_person_seed00"
    args = ["--name", name, "--class", "person", "--command-mode", "velocity", "--seed", "0",
            "--duration", "45", "--wall-timeout", "300", "--real-time-factor", "0.5",
            "--inference-image-size", "320", "--inference-threads", "2",
            "--model-path", "models/yolo11n.pt", "--estimator-method", "adaptive_kf",
            "--occlusions", "--reselect-after-loss"]
    expected = COMMON_NODES | {"scenario_motion"}
    if probe == "stage3_multi":
        args.extend(["--stage", "3", "--multi-target", "--gimbal-mode", "active",
                     "--scenario-kind", "parallel", "--initial-select", "middle",
                     "--initial-min-candidates", "3", "--target-mode", "locked_target"])
        expected = COMMON_NODES | {"stage2_motion", "gimbal_adapter"}
    return {"schema_version": 1, "probe": probe, "prefix": prefix, "name": name,
            "project_root": str(root), "runner_args": args, "expected_ros_executables": sorted(expected),
            "primary_166_included": False, "engineering_16_included": False,
            "scope": "One independent shutdown engineering flight per graph; not a repetition study"}


def process_snapshot():
    rows, errors = [], []
    for directory in Path("/proc").glob("[0-9]*"):
        try:
            fields = (directory / "stat").read_text().rpartition(")")[2].split()
            command = (directory / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
            rows.append({"pid": int(directory.name), "ppid": int(fields[1]),
                         "pgid": int(fields[2]), "sid": int(fields[3]),
                         "start_ticks": int(fields[19]), "state": fields[0], "command": command})
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (OSError, ValueError, IndexError) as error:
            errors.append({"pid": directory.name, "error": str(error)})
    return {"utc": now(), "processes": rows, "errors": errors}


def simulation_process(row):
    command = row["command"]
    first = Path(command.split()[0]).name if command else ""
    return (first in {"gz", "gz-sim-server", "MicroXRCEAgent", "px4"} or first.startswith("gz-sim")
            or any(token in command for token in (
                "ros2 launch ", "ros2 bag record ", "/install/lib/uav_tracking_",
                "/scripts/stage1_flight_monitor.py", "/scripts/run_stage1_trial.py",
                "/scripts/run_full_plan_research.py", "/scripts/run_extended_engineering.py",
                "/scripts/run_full_plan_supplement.py", "/scripts/run_stage23_matrix.py",
                "/scripts/run_stage1_repetitions.py")))


@contextmanager
def workspace_locks(root, formal_results):
    import fcntl
    # Hold the existing old-study lock descriptor without writing its contents.
    with (formal_results / ".full_plan_research.lock").open("rb") as old_lock:
        with (root / "results/.full_plan_research.lock").open("a+b") as new_lock:
            fcntl.flock(old_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(new_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(new_lock, fcntl.LOCK_UN)
                fcntl.flock(old_lock, fcntl.LOCK_UN)


def crash_snapshot(root, trial_dir):
    px4 = Path(os.environ.get("STAGE1_PX4_ROOT", "/root/PX4-Autopilot"))
    paths = (root, trial_dir, px4 / "build/px4_sitl_default/rootfs", Path("/var/crash"))
    files, errors = {}, []
    for directory in paths:
        if not directory.exists():
            continue
        try:
            for path in directory.iterdir():
                if path.is_file() and (path.name.startswith("core") or path.suffix == ".crash"):
                    stat = path.stat()
                    files[str(path)] = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        except OSError as error:
            errors.append({"path": str(directory), "error": str(error)})
    try:
        core_pattern = Path("/proc/sys/kernel/core_pattern").read_text().strip()
    except OSError as error:
        core_pattern = f"UNAVAILABLE: {error}"
    return {"files": files, "errors": errors, "core_pattern": core_pattern,
            "scope": "Listed directory tops only; a piped WSL crash handler's other destinations are not audited"}


class ProcessObserver:
    def __init__(self, output):
        self.handle = output.open("x", encoding="utf-8")
        self.events, self.services, self.owned = [], {}, {}

    def emit(self, kind, **fields):
        event = {"kind": kind, "utc": now(), "monotonic_s": time.monotonic(), **fields}
        self.events.append(event)
        self.handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        self.handle.flush()

    def observe_owned(self):
        snapshot = process_snapshot()
        roots = {item["pid"]: item for item in self.services.values()}
        selected = {row["pid"] for row in snapshot["processes"]
                    if row["pid"] in roots and row["start_ticks"] == roots[row["pid"]]["start_ticks"]}
        previous = None
        while previous != selected:
            previous = selected.copy()
            selected.update(row["pid"] for row in snapshot["processes"] if row["ppid"] in selected)
        rows = [row for row in snapshot["processes"] if row["pid"] in selected]
        for row in rows:
            self.owned[(row["pid"], row["start_ticks"])] = row
        self.emit("ownership_snapshot", processes=rows, errors=snapshot["errors"])

    def popen(self, command, **kwargs):
        real = subprocess.Popen(command, **kwargs)
        name = Path(kwargs["stdout"].name).stem
        fields = Path(f"/proc/{real.pid}/stat").read_text().rpartition(")")[2].split()
        identity = {"pid": real.pid, "pgid": os.getpgid(real.pid), "sid": os.getsid(real.pid),
                    "start_ticks": int(fields[19])}
        self.services[name] = identity
        self.emit("process_start", service=name, command=command,
                  stdin_devnull=kwargs.get("stdin") == subprocess.DEVNULL, **identity)
        observer = self

        class ObservedProcess:
            def __getattr__(self, key):
                return getattr(real, key)

            def poll(self):
                return real.poll()

            def send_signal(self, signum):
                observer.observe_owned()
                observer.emit("signal_attempt", scope="PROCESS", service=name, pid=real.pid,
                              signal=signal.Signals(signum).name)
                try:
                    result = real.send_signal(signum)
                except BaseException as error:
                    observer.emit("signal_error", scope="PROCESS", service=name, error=repr(error))
                    raise
                observer.emit("signal_sent", scope="PROCESS", service=name, pid=real.pid,
                              signal=signal.Signals(signum).name)
                return result

            def wait(self, timeout=None):
                observer.emit("wait_start", service=name, timeout_s=timeout)
                try:
                    result = real.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    observer.emit("wait_timeout", service=name, timeout_s=timeout)
                    raise
                except BaseException as error:
                    observer.emit("wait_error", service=name, error=repr(error))
                    raise
                observer.emit("wait_completed", service=name, returncode=result)
                return result

        return ObservedProcess()

    def killpg(self, pgid, signum):
        self.observe_owned()
        service = next((name for name, row in self.services.items() if row["pgid"] == pgid), "UNKNOWN")
        self.emit("signal_attempt", scope="GROUP", service=service, pgid=pgid,
                  signal=signal.Signals(signum).name)
        try:
            result = os.killpg(pgid, signum)
        except BaseException as error:
            self.emit("signal_error", scope="GROUP", service=service, error=repr(error))
            raise
        self.emit("signal_sent", scope="GROUP", service=service, pgid=pgid,
                  signal=signal.Signals(signum).name)
        return result


def parse_ros_exits(text):
    rows, unmatched = {}, []
    shutdown_line = None
    for number, line in enumerate(text.splitlines(), 1):
        if shutdown_line is None and "user interrupted with ctrl-c (SIGINT)" in line:
            shutdown_line = number
        start = re.search(r"\[([^\]]+)\]: process started with pid \[(\d+)\]", line)
        if start:
            label, pid = start.group(1), int(start.group(2))
            key = (label, pid)
            if key in rows:
                unmatched.append({"line": number, "reason": "duplicate process start", "text": line})
            rows[key] = {"label": label, "executable": label.rsplit("-", 1)[0], "pid": pid,
                         "start_line": number, "outcomes": []}
        finish = re.search(r"\[([^\]]+)\]: process has (finished cleanly|died) \[pid (\d+)(?:, exit code (-?\d+))?", line)
        if finish:
            key = (finish.group(1), int(finish.group(3)))
            outcome = {"line": number, "clean": finish.group(2) == "finished cleanly",
                       "returncode": 0 if finish.group(2) == "finished cleanly" else int(finish.group(4)),
                       "after_shutdown": shutdown_line is not None and number > shutdown_line}
            if key in rows:
                rows[key]["outcomes"].append(outcome)
            else:
                unmatched.append({"line": number, "reason": "exit without process start", "text": line})
    errors = [{"line": number, "text": line} for number, line in enumerate(text.splitlines(), 1)
              if any(token in line for token in ("Traceback (most recent call last)", "KeyboardInterrupt",
                                                "rcl_shutdown already called", "failed to terminate"))]
    return {"shutdown_marker_line": shutdown_line, "nodes": list(rows.values()),
            "unmatched_records": unmatched, "cleanup_errors": errors}


def assess_cleanup(plan, ros, events, residuals, runner_error, summary, exits, snapshot_errors, new_crashes):
    expected = set(plan["expected_ros_executables"])
    starts = [event for event in events if event["kind"] == "process_start" and event["service"] == "ros"]
    signals = [event for event in events if event["kind"] == "signal_sent" and event["service"] == "ros"]
    checks = {
        "runner_completed_normally": runner_error is None,
        "monitor_completed_normally": summary.get("monitor_success") is True and exits.get("monitor") == 0,
        "outer_ros_exit_zero": exits.get("ros") == 0,
        "exact_expected_ros_graph": len(ros["nodes"]) == len(expected)
            and {row["executable"] for row in ros["nodes"]} == expected,
        "every_node_clean_after_shutdown": bool(ros["nodes"]) and all(
            len(row["outcomes"]) == 1 and row["outcomes"][0]["clean"]
            and row["outcomes"][0]["after_shutdown"] for row in ros["nodes"]),
        "no_unmatched_or_cleanup_error_records": not ros["unmatched_records"] and not ros["cleanup_errors"],
        "ros_stdin_noninteractive": len(starts) == 1 and starts[0]["stdin_devnull"],
        "one_initial_ros_process_sigint": len(signals) == 1
            and signals[0]["scope"] == "PROCESS" and signals[0]["signal"] == "SIGINT",
        "no_ros_timeout_or_signal_error": not any(event["service"] == "ros"
            and event["kind"] in {"wait_timeout", "signal_error", "wait_error"}
            for event in events if "service" in event),
        "no_observed_residual_processes_or_sessions": not residuals,
        "process_and_scoped_crash_snapshots_readable": not snapshot_errors,
        "no_new_or_changed_scoped_crash_files": not new_crashes,
    }
    return {"result": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "scope": "ROS graph shutdown and observed process cleanup only; no tracking/bag reevaluation or global core-free claim"}


def execute_probe(plan, formal_results, **formal_inputs):
    if os.name != "posix" or not re.fullmatch(r"/root/uav_tracking_fullplan_cleanup_[A-Za-z0-9_]+", str(ROOT)):
        raise ValueError("Execute only from a new /root/uav_tracking_fullplan_cleanup_NAME checkout")
    isolation_path = ROOT / "results/freeze_validation/import_isolation.json"
    isolation = load(isolation_path)
    if isolation.get("isolated") is not True or Path(isolation["root"]).resolve() != ROOT:
        raise ValueError("The new cleanup checkout has not passed its own build/import isolation")
    tests_text = (ROOT / "results/freeze_validation/unittest.log").read_text(encoding="utf-8")
    if not re.search(r"^OK(?: \(skipped=\d+\))?\s*$", tests_text, re.MULTILINE):
        raise ValueError("The new cleanup checkout has no successful frozen test-suite evidence")
    formal_results = formal_results.resolve(strict=True)
    trial_dir = ROOT / "results" / plan["name"]
    audit_dir = ROOT / "results" / f"{plan['name']}_cleanup_audit"
    if trial_dir.exists() or audit_dir.exists():
        raise FileExistsError("Refusing to replace any earlier probe, including failures")
    with workspace_locks(ROOT, formal_results):
        completion = validate_completed_research(formal_results, **formal_inputs)
        baseline = process_snapshot()
        if baseline["errors"] or any(simulation_process(row) for row in baseline["processes"]):
            raise RuntimeError("Simulation processes or unreadable process evidence remain; probe not started")
        audit_dir.mkdir()
        before_crashes = crash_snapshot(ROOT, trial_dir)
        observer = ProcessObserver(audit_dir / "process_events.jsonl")
        provenance_paths = [Path(__file__), ROOT / "scripts/run_stage1_trial.py",
                            ROOT / "scripts/run_stage1_flight.sh", isolation_path,
                            ROOT / "results/freeze_validation/source_sha256.txt",
                            ROOT / "results/freeze_validation/unittest.log"]
        provenance = {str(path): sha(path) for path in provenance_paths}
        spec = importlib.util.spec_from_file_location("cleanup_observed_trial", ROOT / "scripts/run_stage1_trial.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        # Only this module receives proxies. subprocess.run and the real global
        # subprocess/os modules keep their implementations and are not patched.
        runner.subprocess = SimpleNamespace(Popen=observer.popen, run=subprocess.run, PIPE=subprocess.PIPE,
                                            STDOUT=subprocess.STDOUT, DEVNULL=subprocess.DEVNULL,
                                            TimeoutExpired=subprocess.TimeoutExpired)
        runner.os = SimpleNamespace(environ=os.environ, killpg=observer.killpg)
        previous_argv = sys.argv
        runner_error = None
        try:
            sys.argv = [str(ROOT / "scripts/run_stage1_trial.py"), *plan["runner_args"]]
            runner.main()
        except BaseException as error:
            runner_error = {"type": type(error).__name__, "message": str(error)}
            observer.emit("runner_error", error=runner_error)
        finally:
            sys.argv = previous_argv
            observer.handle.close()
        post = process_snapshot()
        sessions = {row["sid"] for row in observer.services.values()}
        residuals = [row for row in post["processes"] if (row["pid"], row["start_ticks"]) in observer.owned
                     or row["sid"] in sessions or simulation_process(row)]
        after_crashes = crash_snapshot(ROOT, trial_dir)
        new_crashes = {path: value for path, value in after_crashes["files"].items()
                       if before_crashes["files"].get(path) != value}
        ros_path = trial_dir / "ros.log"
        ros = parse_ros_exits(ros_path.read_text(encoding="utf-8", errors="replace") if ros_path.is_file() else "")
        summary_path, exits_path = trial_dir / "summary.json", trial_dir / "process_exit_codes.json"
        snapshot_errors = baseline["errors"] + post["errors"] + before_crashes["errors"] + after_crashes["errors"]
        snapshot_errors.extend(error for event in observer.events if event["kind"] == "ownership_snapshot"
                               for error in event["errors"])
        evidence_objects = []
        for path in (summary_path, exits_path):
            try:
                value = load(path)
                if not isinstance(value, dict):
                    raise ValueError("Expected an evidence JSON object")
            except (OSError, ValueError, TypeError) as error:
                snapshot_errors.append({"path": str(path), "error": str(error)})
                value = {}
            evidence_objects.append(value)
        summary, exits = evidence_objects
        protected_after = {path: sha(path) for path in completion["protected_files_sha256"]}
        assessment = assess_cleanup(plan, ros, observer.events, residuals, runner_error, summary, exits,
                                    snapshot_errors, new_crashes)
        assessment["checks"]["formal_small_ledgers_unchanged"] = protected_after == completion["protected_files_sha256"]
        provenance_after = {path: sha(path) for path in provenance}
        assessment["checks"]["probe_source_unchanged"] = provenance == provenance_after
        assessment["result"] = "PASS" if all(assessment["checks"].values()) else "FAIL"
        report = {"schema_version": 1, "generated_utc": now(), "plan": plan, "plan_sha256": digest(plan),
                  "assessment": assessment, "completion_guard": completion,
                  "source_sha256": {"before": provenance, "after": provenance_after},
                  "formal_small_ledgers_sha256_after": protected_after, "runner_error": runner_error,
                  "outer_process_exit_codes": exits, "ros_node_exits": ros, "residual_processes": residuals,
                  "services": observer.services, "observed_owned_processes": list(observer.owned.values()),
                  "process_snapshot_errors": snapshot_errors,
                  "ros_fallback_events": [event for event in observer.events if event.get("service") == "ros"
                      and (event["kind"] == "wait_timeout" or event.get("signal") in {"SIGTERM", "SIGKILL"})],
                  "crashes_before": before_crashes, "crashes_after": after_crashes,
                  "new_or_changed_scoped_crash_files": new_crashes,
                  "evidence_sha256": {str(path): sha(path) for path in
                      [audit_dir / "process_events.jsonl", ros_path, summary_path, exits_path] if path.is_file()}}
        with (audit_dir / "cleanup_report.json").open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        print(json.dumps({"assessment": assessment, "report": str(audit_dir / "cleanup_report.json")}, indent=2))
        return 0 if assessment["result"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", choices=("stage1", "stage3_multi"), required=True)
    parser.add_argument("--prefix", default="cleanup_v1")
    parser.add_argument("--formal-results", type=Path)
    parser.add_argument("--formal-plan", type=Path)
    parser.add_argument("--offline-manifest", type=Path)
    parser.add_argument("--engineering-manifest", type=Path)
    parser.add_argument("--supplement-manifest", type=Path)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--execute", action="store_true")
    actions.add_argument("--check-ready", action="store_true")
    args = parser.parse_args()
    plan = probe_plan(args.probe, args.prefix)
    if args.execute or args.check_ready:
        formal_inputs = {key: getattr(args, key) for key in
                         ("formal_plan", "offline_manifest", "engineering_manifest", "supplement_manifest")}
        if args.formal_results is None or any(path is None for path in formal_inputs.values()):
            parser.error("--formal-results, --formal-plan, --offline-manifest, --engineering-manifest and "
                         "--supplement-manifest are required for readiness checks and execution")
        if args.execute:
            return execute_probe(plan, args.formal_results, **formal_inputs)
        print(json.dumps(validate_completed_research(args.formal_results, **formal_inputs),
                         ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({"status": "PLAN_ONLY_NO_PROCESSES_OR_OUTPUT_FILES", "plan": plan},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
