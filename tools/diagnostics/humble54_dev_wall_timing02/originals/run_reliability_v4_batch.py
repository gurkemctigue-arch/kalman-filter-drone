"""Own a serial v4 batch while retaining the normal runner and its evidence.

Each synchronous normal run_plan call consumes at most one original PENDING
slot. This owner only reads original records. Its policy, progress, exception
and lifecycle evidence are written to a separate, newly created directory.
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
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/run_reliability_v4.py"
OWNER_PATH = ROOT / "scripts/run_reliability_v4_batch.py"
HEARTBEAT_S = 5.0
POLICY_MODES = {"core": {"PROBE"}, "extension": {"EXTENSION_PROBE"}}
INCOMPLETE_RESULTS = {"MISSING", "INVALID", "INCOMPLETE", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_runner():
    """The CLI accepts no runner path, module name or execution replacement."""
    require(not RUNNER_PATH.is_symlink() and RUNNER_PATH.is_file(), "Ordinary same-root normal runner required")
    spec = importlib.util.spec_from_file_location("uav_tracking_same_root_v4_batch_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(Path(module.__file__).resolve() == RUNNER_PATH.resolve() and module.ROOT.resolve() == ROOT,
            "Normal runner import escaped this source root")
    return module


def process_identity():
    value = {"pid": os.getpid(), "invocation_started_utc": utc_now(),
             "invocation_started_monotonic_s": time.monotonic()}
    if os.name == "posix" and Path("/proc/self/stat").is_file():
        fields = Path("/proc/self/stat").read_text().rpartition(")")[2].split()
        value.update(ppid=int(fields[1]), pgid=int(fields[2]), session=int(fields[3]),
                     start_ticks=int(fields[19]), clock_ticks_per_s=os.sysconf("SC_CLK_TCK"),
                     boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                     creation_identity_scope="LINUX_PROC_START_TICKS_AND_BOOT_ID")
    else:
        value["creation_identity_scope"] = "UNAVAILABLE_NON_LINUX_FIXTURE_ONLY"
    return value


@contextmanager
def batch_lock(plan_sha):
    """Prevent two thin owners from interleaving the same plan between calls."""
    directory = Path("/tmp") if os.name == "posix" else Path(tempfile.gettempdir())
    path = directory / ("uav_tracking_v4_batch_" + plan_sha + ".lock")
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Owner:
    def __init__(self, output, initial):
        self.output, self.state = output, initial
        self.lock, self.stop = threading.RLock(), threading.Event()
        self.sequence, self.heartbeat_error = 0, None
        self.monitor_started, self.monitor_completed = set(), set()
        (output / "monitor_events.jsonl").open("x", encoding="utf-8").close()
        with (output / "owner_started.json").open("x", encoding="utf-8") as stream:
            json.dump(initial, stream, indent=2, allow_nan=False)
            stream.write("\n")
        self.thread = threading.Thread(target=self._heartbeat, name="v4-batch-heartbeat", daemon=True)
        self.event("owner_started")
        self.thread.start()

    def _write_state(self):
        temporary = self.output / (".owner_state." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(self.state, stream, indent=2, allow_nan=False)
                stream.write("\n")
            os.replace(temporary, self.output / "owner_state.json")
        finally:
            temporary.unlink(missing_ok=True)

    def event(self, event, **updates):
        with self.lock:
            self.sequence += 1
            now = utc_now()
            self.state.update(updates, heartbeat_utc=now, heartbeat_monotonic_s=time.monotonic(),
                              event_sequence=self.sequence)
            record = {"sequence": self.sequence, "event": event, "utc": now,
                      "monotonic_s": self.state["heartbeat_monotonic_s"],
                      "owner_pid": self.state["owner"]["pid"], **updates}
            if event == "heartbeat":
                record.update(active_slot=self.state.get("active_slot"),
                              started_this_invocation=self.state["started_this_invocation"])
            with (self.output / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, allow_nan=False) + "\n")
                stream.flush()
            self._write_state()

    def _heartbeat(self):
        while not self.stop.wait(HEARTBEAT_S):
            try:
                self.event("heartbeat")
            except Exception as error:
                self.heartbeat_error = f"{type(error).__name__}: {error}"
                return

    def monitor_event(self, event, **fields):
        """Compatibility sidecar for the existing read-only progress monitor."""
        with self.lock:
            with (self.output / "monitor_events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": event, "utc": utc_now(), **fields}, allow_nan=False) + "\n")
                stream.flush()
            if event == "START_SLOT":
                self.monitor_started.add(fields["slot"])
            elif event == "COMPLETE_SLOT":
                self.monitor_completed.add(fields["slot"])

    def monitor_original_rows(self, plan, rows):
        for trial in plan["trials"]:
            identifier, row = trial["id"], rows[trial["id"]]
            if row["status"] == "PENDING":
                continue
            if identifier not in self.monitor_started:
                self.monitor_event("START_SLOT", slot=identifier, total=len(plan["trials"]),
                                   observation="EXISTING_ORIGINAL_ATTEMPT")
            if row["status"] != "RUNNING" and identifier not in self.monitor_completed:
                self.monitor_event("COMPLETE_SLOT", slot=identifier, status=row["status"])

    def finish(self, status, **updates):
        self.stop.set()
        self.thread.join(timeout=10.)
        require(not self.thread.is_alive(), "Owner heartbeat did not finish")
        if self.heartbeat_error:
            status = "STOPPED_FAULT"
            updates.update(reason="heartbeat_evidence_failed", heartbeat_error=self.heartbeat_error)
        if status in {"STOPPED_FAULT", "INTERRUPTED"}:
            self.monitor_event("STOPPED_FAULT", slot=updates.get("stopped_slot", self.state.get("active_slot")),
                               owner_status=status, reason=updates.get("reason"))
        self.event("owner_terminal", status=status, active_slot=None, finished_utc=utc_now(), **updates)
        with (self.output / "owner_terminal.json").open("x", encoding="utf-8") as stream:
            json.dump(self.state, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return dict(self.state)


def inventory(plan, rows):
    counts = Counter(rows[trial["id"]]["status"] for trial in plan["trials"])
    complete = bool(rows) and all(rows[trial["id"]]["status"] not in {"PENDING", "RUNNING"}
                                  for trial in plan["trials"])
    return {"planned_count": len(plan["trials"]), "status_counts": dict(counts),
            "pending_ids": [trial["id"] for trial in plan["trials"] if rows[trial["id"]]["status"] == "PENDING"],
            "all_slots_terminal": complete,
            "all_engineering_pass": bool(rows) and counts["PASS"] == len(plan["trials"])}


def check_slot(runner, plan, trial, row, policy):
    """Read the original slot and reports; never upgrade or rewrite either."""
    if row.get("infrastructure_stop") is not False:
        return "infrastructure_stop_or_missing_evidence"
    if row.get("status") not in {"PASS", "FAIL"}:
        return "non_algorithm_terminal_status:" + str(row.get("status"))
    if (row.get("execution_status") != "COMPLETED" or row.get("flight_exit_code") != 0
            or row.get("runtime_configuration", {}).get("errors") != []
            or row.get("cleanup", {}).get("residual_processes") != []):
        return "normal_runtime_or_cleanup_evidence_not_complete"
    entries = row.get("evaluations")
    if not isinstance(entries, list):
        return "missing_evaluations"
    by_kind = {entry.get("kind"): entry for entry in entries if isinstance(entry, dict)}
    required = runner.required_evaluators(trial)
    if len(by_kind) != len(entries) or set(by_kind) != required:
        return "missing_or_duplicate_required_evaluators"
    for kind in ("source_clock", "native_startup"):
        entry = by_kind.get(kind, {})
        if (entry.get("result") != "PASS" or entry.get("error") is not None
                or entry.get("execution", {}).get("returncode") != 0
                or entry.get("execution", {}).get("error") is not None):
            return kind + "_not_independently_passed"
        specs = [spec for spec in trial["evaluations"] if spec.get("kind") == kind]
        if len(specs) != 1:
            return "missing_original_evaluation_spec:" + kind
        checked = runner.read_evaluation(specs[0], entry["execution"], plan)
        if (checked.get("result") != "PASS" or checked.get("report_sha256") != entry.get("report_sha256")
                or Path(entry.get("report", "")).resolve() != Path(specs[0]["report"]).resolve()):
            return kind + "_report_binding_or_contract_invalid"
    if any(entry.get("result") in INCOMPLETE_RESULTS for entry in entries):
        return "required_evaluation_evidence_incomplete"
    if policy == "core" and row["status"] != "PASS":
        return "core_slot_not_passed"
    if row["status"] == "FAIL" and row.get("engineering_result") != "FAIL":
        return "failed_slot_is_not_completed_algorithm_failure"
    return None


def run_batch(plan_path, output, policy, max_new_trials=0):
    require(policy in POLICY_MODES, "Unknown batch policy")
    require(type(max_new_trials) is int and max_new_trials >= 0, "max_new_trials must be nonnegative")
    runner = load_runner()
    require(Path(runner.__file__).resolve() == RUNNER_PATH.resolve() and runner.ROOT.resolve() == ROOT,
            "Same-root normal runner required")
    plan_path, output = Path(plan_path).resolve(strict=True), Path(output).resolve()
    plan = runner.load(plan_path)
    require(Path(plan["frozen_root"]).resolve() == ROOT, "Plan and batch owner must have the same frozen source root")
    require(plan.get("mode") in POLICY_MODES[policy], "Policy does not match the original plan mode")
    source_binding = {path.relative_to(ROOT).as_posix(): sha(path) for path in (RUNNER_PATH, OWNER_PATH)}
    require(all(plan.get("source_hashes", {}).get(name) == digest for name, digest in source_binding.items()),
            "Runner/owner source hashes differ from the registered plan")
    require(not output.exists() and output.parent.is_dir(), "New independent owner output directory required")
    protected = [Path(trial["directory"]).resolve() for trial in plan["trials"]]
    protected.extend((Path(plan["output"]).resolve() / "slots",))
    require(output != Path(plan["output"]).resolve() and
            not any(output.is_relative_to(path) or path.is_relative_to(output) for path in protected),
            "Owner output overlaps original slot/trial evidence")
    output.mkdir()
    owner = Owner(output, {"schema_version": 1, "scope": "THIN_OWNER_OF_UNCHANGED_NORMAL_V4_RUNNER",
                          "status": "RUNNING", "owner": process_identity(), "policy": policy,
                          "plan": str(plan_path), "plan_file_sha256": sha(plan_path),
                          "plan_sha256": plan["plan_sha256"], "source_hashes": source_binding,
                          "started_this_invocation": 0, "active_slot": None, "all_engineering_pass": False,
                          "claim_boundary": "COMPLETED means batch processing ended, never all slots passed; original records and unknown intervals remain authoritative"})
    rows, started = None, 0
    try:
        runner.validate_plan(plan, plan_path)
        runner.verify_sources(plan)
        with batch_lock(plan["plan_sha256"]):
            rows = runner.read_slots(plan)
            owner.monitor_original_rows(plan, rows)
            for trial in plan["trials"]:
                row = rows[trial["id"]]
                if row["status"] == "PENDING":
                    continue
                reason = check_slot(runner, plan, trial, row, policy)
                if reason:
                    return owner.finish("STOPPED_FAULT", reason=reason, stopped_slot=trial["id"], **inventory(plan, rows))
            owner.event("initial_original_inventory", **inventory(plan, rows))
            while True:
                pending = [trial for trial in plan["trials"] if rows[trial["id"]]["status"] == "PENDING"]
                if not pending:
                    return owner.finish("COMPLETED", reason="all_original_slots_terminal", **inventory(plan, rows))
                if max_new_trials and started >= max_new_trials:
                    return owner.finish("LIMIT_REACHED", reason="max_new_trials_reached", **inventory(plan, rows))
                require(not owner.heartbeat_error, "Heartbeat evidence failed: " + str(owner.heartbeat_error))
                require(sha(plan_path) == owner.state["plan_file_sha256"], "Original plan file changed")
                trial = pending[0]
                before = {key: (row["status"], row.get("record_sha256")) for key, row in rows.items()}
                owner.event("slot_invocation_started", active_slot=trial["id"],
                            invocation_number=started + 1, normal_max_new_trials=1)
                owner.monitor_event("START_SLOT", slot=trial["id"], total=len(plan["trials"]))
                result = runner.run_plan(plan, max_new_trials=1)
                rows = runner.read_slots(plan, verify_artifacts=False)
                owner.monitor_original_rows(plan, rows)
                changed = [key for key, row in rows.items() if before.get(key) != (row["status"], row.get("record_sha256"))]
                started += int(result.get("started_this_invocation", 0))
                owner.event("slot_invocation_returned", started_this_invocation=started,
                            normal_result=result, changed_original_slot_ids=changed, **inventory(plan, rows))
                require(changed == [trial["id"]] and result.get("started_this_invocation") == 1,
                        "Normal runner did not consume exactly the next original pending slot once")
                row = rows[trial["id"]]
                reason = check_slot(runner, plan, trial, row, policy)
                if result.get("stop") or reason:
                    return owner.finish("INTERRUPTED" if row.get("status") == "INTERRUPTED" else "STOPPED_FAULT",
                                        reason=reason or str(result["stop"]), stopped_slot=trial["id"], **inventory(plan, rows))
                require(sha(plan_path) == owner.state["plan_file_sha256"], "Original plan file changed")
                owner.event("slot_policy_accepted", active_slot=None, completed_slot=trial["id"],
                            original_slot_status=row["status"], **inventory(plan, rows))
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc(),
                   "original_slot_policy": "No original marker, result or evidence is deleted, retried or rewritten by this owner"}
        try:
            rows = runner.read_slots(plan, verify_artifacts=False)
            owner.monitor_original_rows(plan, rows)
        except Exception as inventory_error:
            failure["inventory_error"] = f"{type(inventory_error).__name__}: {inventory_error}"
        with (output / "exception.json").open("x", encoding="utf-8") as stream:
            json.dump(failure, stream, indent=2, allow_nan=False)
            stream.write("\n")
        extra = inventory(plan, rows) if rows is not None else {"all_engineering_pass": False}
        return owner.finish("INTERRUPTED" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "STOPPED_FAULT",
                            reason="owner_or_normal_runner_exception", exception=failure,
                            started_this_invocation=started, **extra)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", choices=tuple(POLICY_MODES), required=True)
    parser.add_argument("--max-new-trials", type=int, default=0)
    args = parser.parse_args(argv)
    if os.name != "posix":
        parser.error("Actual batch ownership requires the isolated Linux/ROS environment")
    try:
        result = run_batch(args.plan, args.output, args.policy, args.max_new_trials)
    except (ValueError, OSError) as error:
        print(f"Batch entry rejected: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] in {"COMPLETED", "LIMIT_REACHED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
