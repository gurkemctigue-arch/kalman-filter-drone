"""One-shot Windows continuation after the exact Humble54 extension processes exit.

Preparation only until an operator invokes --execute after independent review.
No retries, process termination, experiment launches, or formal admission are added.
The follow-on shell independently rechecks native idleness and its prerequisites.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

PROJECT = Path("D:/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2")
EXTERNAL = Path("D:/WSL/UAVHumble22-validation")
RECEIPTS = EXTERNAL / "wait_humble54_extension_followon01"
FOLLOWON_SHELL = EXTERNAL / "run_humble54_closed_followon01.sh"
# Final shell bytes independently reviewed before this source pin was fixed.
FOLLOWON_SHELL_SHA256 = "124c6d4e0474ce9d1047e56208352e983bf9a21b1f2c4215461d60d6a4e3570b"
MONITOR = PROJECT / "scripts/monitor_project_progress.py"
MONITOR_SHA256 = "759136d0eda40bb3a61c9e30e0272e1f6b8810b351dbe4c75dc17db5951bfd98"
EXTENSION_PROGRESS = PROJECT / "results/project_progress/humble54_extension16_run01"
FROZEN_RESULTS = PROJECT / "results/frozen_fullplan_v4_humble54"
MATRIX = FROZEN_RESULTS / "reliability_v4_humble54_extension16_probe01_matrix"
OWNER_DIRECTORY = FROZEN_RESULTS / "humble54_extension16_owner01"
NEW_PROGRESS = PROJECT / "results/project_progress/humble54_closed_followon01"
PLAN_SHA256 = "f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055"
PLAN_DIGEST = "ded5ab19b72f53c932cbea2044561a4e2fe937445cb07eb9525e9e0be5fc9761"
OLD_TASK = "humble54-extension16-run01"
OLD_TASK_STARTED_UTC = "2026-11-03T01:14:20.481862+00:00"
OLD_MONITOR = {"pid": 19256, "creation_filetime": 134381420603083387}
OLD_WSL = {"pid": 4888, "creation_filetime": 134381420604764583}
OLD_OWNER = {"pid": 134468, "start_ticks": 7830987,
             "boot_id": "f79204a4-99cd-42cf-b886-aa905b1cac6a"}
UNIFIED_EXEC_SESSION_CONTEXT = 29911  # Operator/tool context; not an end_summary field.
NEW_TASK = "humble54-closed-followon01"
MAX_BYTES = 1024 * 1024


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def reject_constant(value):
    raise ValueError("Non-finite JSON constant: " + value)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def small_bytes(path):
    path = Path(path)
    before = path.stat()
    require(path.is_file() and 0 < before.st_size <= MAX_BYTES,
            "Not a bounded small file: " + str(path))
    content = path.read_bytes()
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
            and len(content) == before.st_size, "File changed while reading: " + str(path))
    return content


def small_json(path):
    return json.loads(small_bytes(path).decode("utf-8-sig"),
                      object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def pin(path, expected):
    require(len(expected) == 64 and set(expected) <= set("0123456789abcdef"),
            "Final reviewed SHA256 has not been registered: " + str(path))
    actual = digest_bytes(small_bytes(path))
    require(actual == expected, "Pinned source changed: " + str(path))
    return {"path": str(path), "sha256": actual}


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        deadline = time.monotonic() + 0.5
        while True:
            try:
                os.replace(temporary, path)
                return
            except OSError as error:
                if (getattr(error, "winerror", None) not in {5, 32, 33}
                        or time.monotonic() >= deadline):
                    raise
                time.sleep(0.02)
    finally:
        temporary.unlink(missing_ok=True)


def timestamp(value):
    require(isinstance(value, str), "Missing UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Timestamp lacks timezone")
    return parsed.timestamp()


def expected_token(identity):
    return "windows_filetime:" + str(identity["creation_filetime"])


def check_saved_identity(value, expected):
    require(isinstance(value, dict) and value.get("pid") == expected["pid"]
            and value.get("start_token") == expected_token(expected),
            "Saved process creation identity does not match exact extension invocation")


def original_record_digest(record):
    content = {key: value for key, value in record.items() if key != "record_sha256"}
    return digest_bytes(json.dumps(content, sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode())


def validate_closed_inputs():
    """Small saved records only. The native shell still runs original checks."""
    plan_bytes = small_bytes(MATRIX / "plan.json")
    require(digest_bytes(plan_bytes) == PLAN_SHA256, "Original extension plan bytes changed")
    plan = json.loads(plan_bytes.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)
    require(plan.get("plan_sha256") == PLAN_DIGEST and plan.get("mode") == "EXTENSION_PROBE"
            and plan.get("selected_seeds") == [4], "Wrong extension plan or seed partition")
    trials = plan.get("trials")
    require(isinstance(trials, list) and len(trials) == 16, "Need all 16 planned trials")
    ids = [trial["id"] for trial in trials]
    require(len(set(ids)) == 16 and all(Path(item).name == item for item in ids),
            "Invalid or duplicate original slot IDs")

    terminal_bytes = small_bytes(OWNER_DIRECTORY / "owner_terminal.json")
    require(terminal_bytes == small_bytes(OWNER_DIRECTORY / "owner_state.json"),
            "Owner state and terminal differ")
    owner = json.loads(terminal_bytes.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
                       parse_constant=reject_constant)
    require(owner.get("status") == "COMPLETED" and owner.get("policy") == "extension"
            and owner.get("plan_file_sha256") == PLAN_SHA256
            and owner.get("plan_sha256") == PLAN_DIGEST
            and "active_slot" in owner and owner["active_slot"] is None and owner.get("pending_ids") == []
            and owner.get("planned_count") == 16 and owner.get("all_slots_terminal") is True,
            "Extension owner did not close the complete original plan")
    require(all(owner.get("owner", {}).get(key) == value for key, value in OLD_OWNER.items()),
            "Original Linux owner creation identity changed")
    normal = owner.get("normal_result", {})
    require("stop" in normal and normal["stop"] is None and normal.get("terminal_count") == 16
            and normal.get("mode") == "EXTENSION_PROBE" and normal.get("planned_count") == 16
            and normal.get("pending_ids") == [] and normal.get("plan_sha256") == PLAN_DIGEST,
            "Normal runner did not close without orchestration stop")

    rows = []
    for trial in trials:
        slot_id = trial["id"]
        marker = small_json(MATRIX / "slots" / (slot_id + ".started.json"))
        row_bytes = small_bytes(MATRIX / "slots" / (slot_id + ".json"))
        row = json.loads(row_bytes.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
                         parse_constant=reject_constant)
        require(marker.get("id") == row.get("id") == slot_id
                and marker.get("plan_sha256") == row.get("plan_sha256") == PLAN_DIGEST
                and row.get("name") == trial["name"], "Original START/terminal/plan mismatch")
        require(row.get("record_sha256") == original_record_digest(row),
                "Original terminal content digest changed: " + slot_id)
        require(row.get("status") in {"PASS", "FAIL"}
                and row.get("execution_status") == "COMPLETED"
                and row.get("infrastructure_stop") is False and row.get("flight_exit_code") == 0
                and row.get("runtime_configuration", {}).get("errors") == []
                and row.get("cleanup", {}).get("residual_processes") == [],
                "Infrastructure/unknown/incomplete original slot: " + slot_id)
        require(row.get("engineering_result") == row["status"],
                "Original engineering result disagrees with terminal status: " + slot_id)
        evaluations = row.get("evaluations")
        require(isinstance(evaluations, list), "Missing evaluation list: " + slot_id)
        by_kind = {entry["kind"]: entry for entry in evaluations}
        expected_kinds = {entry["kind"] for entry in trial["evaluations"]}
        require(len(by_kind) == len(evaluations) and set(by_kind) == expected_kinds,
                "Missing/duplicate original evaluations: " + slot_id)
        for kind, entry in by_kind.items():
            result = entry.get("result")
            require(isinstance(result, str) and result and result not in {
                "MISSING", "INVALID", "INCOMPLETE", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING"},
                "Incomplete evaluation result: " + slot_id + ":" + kind)
            require(entry.get("error") is None and entry.get("execution", {}).get("returncode") == 0
                    and entry.get("execution", {}).get("error") is None,
                    "Evaluation execution failed: " + slot_id + ":" + kind)
            if kind in {"source_clock", "native_startup"}:
                require(result == "PASS", "Original source/native safety gate did not PASS")
        require(timestamp(marker["started_utc"]) <= timestamp(row["finished_utc"]),
                "Original terminal precedes START")
        rows.append({"id": slot_id, "status": row["status"],
                     "original_file_sha256": digest_bytes(row_bytes),
                     "finished_utc": row["finished_utc"]})
    marker_ids = {path.name[:-len(".started.json")]
                  for path in (MATRIX / "slots").glob("*.started.json")}
    require(marker_ids == set(ids), "Extra/missing or unclosed original START markers")
    counts = dict(Counter(row["status"] for row in rows))
    require(owner.get("status_counts") == normal.get("status_counts") == counts,
            "Owner counts differ from the 16 original terminals")

    end = small_json(EXTENSION_PROGRESS / "end_summary.json")
    state = small_json(EXTENSION_PROGRESS / "monitor_state.json")
    task = end.get("task", {})
    require(end.get("status") == "COMPLETED" and end.get("completion_scope") == "monitored_command"
            and end.get("phase") == "batch" and task.get("phase") == "batch"
            and task.get("id") == OLD_TASK and task.get("monitor_kind") == "owned_child"
            and task.get("started_utc") == OLD_TASK_STARTED_UTC and task.get("returncode") == 0
            and state.get("task") == task, "Wrong/stale/incomplete Windows end summary")
    check_saved_identity(task.get("process"), OLD_WSL)
    check_saved_identity(state.get("monitor_process"), OLD_MONITOR)
    check_saved_identity(end.get("process_check", {}).get("observation"), OLD_WSL)
    check_saved_identity(end.get("monitor_check", {}).get("observation"), OLD_MONITOR)
    require(end.get("process_check", {}).get("verified_alive") is False
            and end.get("process_check", {}).get("identity_matches") is True
            and end.get("process_check", {}).get("observation", {}).get("alive") is False
            and end.get("monitor_check", {}).get("identity_matches") is True,
            "Final command identity/exit observation is not explicit")
    evidence = end.get("evidence", {})
    require(evidence.get("state") == "COMPLETED" and evidence.get("planned_slots") == 16
            and evidence.get("attempted_slots") == 16 and evidence.get("recorded_terminal_slots") == 16
            and evidence.get("unattempted_slots") == 0 and evidence.get("attempted_without_terminal") == []
            and "current_slot" in evidence and evidence["current_slot"] is None and evidence.get("errors") == []
            and evidence.get("status_counts") == counts, "Windows evidence is incomplete or disagrees")
    require(timestamp(end["generated_utc"]) >= timestamp(task["finished_utc"])
            >= timestamp(owner["finished_utc"])
            >= max(timestamp(row["finished_utc"]) for row in rows), "Closure timestamps do not bind")
    return {"result": "CLOSED_ORIGINAL_EXTENSION_PRECONDITIONS",
            "plan_file_sha256": PLAN_SHA256, "plan_digest": PLAN_DIGEST,
            "owner_terminal_sha256": digest_bytes(terminal_bytes),
            "end_summary_sha256": digest_bytes(small_bytes(EXTENSION_PROGRESS / "end_summary.json")),
            "original_status_counts": counts, "original_slots": rows,
            "unknown_identity_and_algorithm_failures_retained": True,
            "scope": "Small original records only; artifact payloads are not rehashed here. Native follow-on rechecks prerequisites."}


class WindowsHandles:
    """Retain exact process objects; never infer exit from a reused or absent PID."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.types = ctypes, wintypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        k = self.kernel
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        k.GetProcessTimes.restype = wintypes.BOOL
        k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.GetExitCodeProcess.restype = wintypes.BOOL
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.SetThreadExecutionState.argtypes = [wintypes.DWORD]
        k.SetThreadExecutionState.restype = wintypes.DWORD
        self.handles = []

    def acquire_identity(self, pid):
        handle = self.kernel.OpenProcess(0x00101000, False, pid)
        require(bool(handle), "OpenProcess failed: " + str(self.ctypes.get_last_error()))
        self.handles.append(handle)
        times = [self.types.FILETIME() for _ in range(4)]
        require(bool(self.kernel.GetProcessTimes(handle, *(self.ctypes.byref(t) for t in times))),
                "GetProcessTimes failed")
        creation = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return handle, {"pid": pid, "creation_filetime": creation,
                        "start_token": "windows_filetime:" + str(creation)}

    def acquire(self, expected):
        handle, identity = self.acquire_identity(expected["pid"])
        require(identity["creation_filetime"] == expected["creation_filetime"],
                "Kernel process creation FILETIME mismatch")
        return handle

    def exit_if_signaled(self, handle):
        result = self.kernel.WaitForSingleObject(handle, 0)
        require(result in {0, 258}, "WaitForSingleObject failed or returned unknown state")
        if result == 258:
            return None
        code = self.types.DWORD()
        require(bool(self.kernel.GetExitCodeProcess(handle, self.ctypes.byref(code))),
                "GetExitCodeProcess failed after process was signaled")
        return code.value

    def close(self):
        results = []
        for handle in reversed(self.handles):
            results.append(bool(self.kernel.CloseHandle(handle)))
        self.handles.clear()
        return results


def execute():
    require(os.name == "nt", "This waiter requires actual Windows kernel handles")
    require(not NEW_PROGRESS.exists(), "Follow-on monitor output already exists; no reuse or retry")
    RECEIPTS.mkdir(exist_ok=False)
    report = {"schema_version": 1, "started_utc": utc_now(), "pid": os.getpid(),
              "status": "ACQUIRING_EXACT_EXTENSION_HANDLES", "followon_launched": False,
              "extension_handles": {"monitor": OLD_MONITOR, "wsl": OLD_WSL},
              "unified_exec_session_context": UNIFIED_EXEC_SESSION_CONTEXT,
              "session_context_source": "Operator/tool handoff; absent from original monitor schema",
              "global_power_policy_changed": False, "automatic_retry": False,
              "formal_admission_created": False, "new_flight_started": False}
    handles = None
    sleep_request = False
    child = None
    outcome = 2
    try:
        handles = WindowsHandles()
        monitor_handle = handles.acquire(OLD_MONITOR)
        wsl_handle = handles.acquire(OLD_WSL)
        report["exact_kernel_handles_acquired_utc"] = utc_now()
        report["pins"] = {"waiter": {"path": str(Path(__file__).resolve()),
                          "sha256": digest_bytes(small_bytes(Path(__file__)))},
                          "monitor": pin(MONITOR, MONITOR_SHA256),
                          "shell": pin(FOLLOWON_SHELL, FOLLOWON_SHELL_SHA256)}
        accepted = handles.kernel.SetThreadExecutionState(0x80000001)
        require(bool(accepted), "Temporary SetThreadExecutionState request was rejected")
        sleep_request = True
        report["sleep_request"] = {"accepted_utc": utc_now(), "return_value": int(accepted),
                                   "scope": "TEMPORARY_SYSTEM_SLEEP_REQUEST_ONLY"}
        report["status"] = "WAITING_FOR_EXTENSION"
        while True:
            codes = {"monitor": handles.exit_if_signaled(monitor_handle),
                     "wsl": handles.exit_if_signaled(wsl_handle)}
            report.update(heartbeat_utc=utc_now(), original_handle_exit_codes=codes)
            atomic_json(RECEIPTS / "state.json", report)
            if all(code is not None for code in codes.values()):
                break
            time.sleep(5)
        require(codes == {"monitor": 0, "wsl": 0}, "Exact original processes did not both exit 0")
        report["closed_preconditions"] = validate_closed_inputs()
        require(not NEW_PROGRESS.exists(), "Follow-on output appeared while waiting")
        pin(MONITOR, MONITOR_SHA256)
        pin(FOLLOWON_SHELL, FOLLOWON_SHELL_SHA256)
        require(digest_bytes(small_bytes(Path(__file__))) == report["pins"]["waiter"]["sha256"],
                "Waiter changed while waiting")
        command = [sys.executable, "-B", str(MONITOR), "run", "--output", str(NEW_PROGRESS),
                   "--phase", "batch", "--task-id", NEW_TASK,
                   "--label", "Humble54 closed development follow-on; no new flights or formal admission", "--",
                   "wsl.exe", "--distribution", "UAVHumble22", "--user", "root", "--",
                   "bash", "/mnt/d/WSL/UAVHumble22-validation/run_humble54_closed_followon01.sh"]
        commitment = {"committed_utc": utc_now(), "command": command,
                      "scope": "At most one launch; a crash after commitment never authorizes retry"}
        with (RECEIPTS / "launch_committed.json").open("x", encoding="utf-8") as stream:
            json.dump(commitment, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        report.update(status="FOLLOWON_LAUNCH_COMMITTED", launch=commitment)
        atomic_json(RECEIPTS / "state.json", report)
        with (RECEIPTS / "followon_monitor.stdout.log").open("x", encoding="utf-8") as stream:
            child = subprocess.Popen(command, cwd=PROJECT, stdin=subprocess.DEVNULL,
                                     stdout=stream, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
            report.update(status="FOLLOWON_RUNNING", followon_launched=True,
                          followon_monitor_pid=child.pid, followon_started_utc=utc_now())
            new_handle, new_identity = handles.acquire_identity(child.pid)
            report["followon_monitor_creation_identity"] = new_identity
            while child.poll() is None:
                report["heartbeat_utc"] = utc_now()
                atomic_json(RECEIPTS / "state.json", report)
                time.sleep(5)
            report["followon_monitor_exit_code"] = child.returncode
            report["followon_monitor_handle_exit_code"] = handles.exit_if_signaled(new_handle)
        followon_end = small_json(NEW_PROGRESS / "end_summary.json")
        followon_state = small_json(NEW_PROGRESS / "monitor_state.json")
        require(followon_end.get("task", {}).get("id") == NEW_TASK
                and followon_end.get("task", {}).get("monitor_kind") == "owned_child"
                and followon_end.get("task") == followon_state.get("task"),
                "Follow-on monitor did not save its actual owned child")
        check_saved_identity(followon_state.get("monitor_process"), new_identity)
        check_saved_identity(followon_end.get("monitor_check", {}).get("observation"), new_identity)
        require(followon_end.get("monitor_check", {}).get("identity_matches") is True,
                "Follow-on saved monitor identity differs from the retained real process handle")
        owned = followon_end["task"].get("process", {})
        observed = followon_end.get("process_check", {}).get("observation", {})
        require(owned.get("pid") == observed.get("pid") and isinstance(owned.get("pid"), int)
                and isinstance(owned.get("start_token"), str)
                and owned["start_token"].startswith("windows_filetime:")
                and owned["start_token"] == observed.get("start_token")
                and followon_end.get("process_check", {}).get("identity_matches") is True
                and followon_end.get("process_check", {}).get("verified_alive") is False
                and observed.get("alive") is False,
                "Follow-on owned WSL creation identity/exit observation is unknown")
        report["followon_owned_child"] = followon_end["task"]
        require(child.returncode == 0 and report["followon_monitor_handle_exit_code"] == 0
                and followon_end.get("status") == "COMPLETED"
                and followon_end["task"].get("returncode") == 0,
                "Follow-on command failed or has an unknown outcome; no retry")
        report.update(status="COMPLETED_FOLLOWON_COMMAND_ONLY", finished_utc=utc_now())
        outcome = 0
    except BaseException as error:
        report.update(status="STOPPED_REFUSED_NO_RETRY", finished_utc=utc_now(),
                      error={"type": type(error).__name__, "message": str(error)},
                      child_may_continue=bool(child is not None and child.poll() is None))
    finally:
        if sleep_request:
            released = handles.kernel.SetThreadExecutionState(0x80000000)
            report["sleep_request"]["release_return_value"] = int(released)
            report["sleep_request"]["released_utc"] = utc_now()
            if not released:
                outcome = 2
                report["status"] = "STOPPED_SLEEP_REQUEST_RELEASE_UNVERIFIED"
        if handles is not None:
            report["handle_close_results"] = handles.close()
            report["handles_close_attempted_utc"] = utc_now()
            if not all(report["handle_close_results"]):
                outcome = 2
                report["status"] = "STOPPED_HANDLE_CLOSE_UNVERIFIED"
        atomic_json(RECEIPTS / "state.json", report)
        atomic_json(RECEIPTS / "end_summary.json", report)
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Only after independent review and pinning")
    args = parser.parse_args(argv)
    if not args.execute:
        print("PREPARED_ONLY: no handles opened, no receipt or output created, no command started")
        return 2
    return execute()


if __name__ == "__main__":
    raise SystemExit(main())
