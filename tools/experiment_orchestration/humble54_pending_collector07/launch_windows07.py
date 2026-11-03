"""One Windows owner of the existing monitor and registered remaining-five run.

Default is read-only. No observer, trigger, retry, kill, or automatic next phase.
The monitor is a new process group so this owner's console interrupt cannot
reach the monitor's interrupt handler, which would otherwise terminate WSL.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
COLLECTOR = HERE / "collect_humble54_pending07.py"
PROFILE = HERE / "registered_profile07.json"
MONITOR = ROOT / "scripts/monitor_project_progress.py"
RECEIPT = ROOT / "results/diagnostics/humble54_pending_collector07_launcher01"
PINS = {"collector": "7d2523325bca8ef520fe0e5a7bd78da355943099e3f45efee2c3ad4e870cdd9b",
        "registered_profile": "c36f17363874173ee7fed08d482a68f518fd44cffd581d757de09ccd649ded55",
        "monitor": "759136d0eda40bb3a61c9e30e0272e1f6b8810b351dbe4c75dc17db5951bfd98"}
CREATION_FLAGS = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def binding(path):
    return {"path": str(path), "sha256": sha(path)}


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def publish(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf8")
    temporary.replace(path)


class PowerLease:
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.SetThreadExecutionState.argtypes = [ctypes.c_ulong]
        self.kernel.SetThreadExecutionState.restype = ctypes.c_ulong
        self.kernel.GetCurrentThreadId.restype = ctypes.c_ulong

    def thread(self):
        return int(self.kernel.GetCurrentThreadId())

    def request(self, flags):
        return int(self.kernel.SetThreadExecutionState(flags))


def description():
    paths = {"collector": COLLECTOR, "registered_profile": PROFILE, "monitor": MONITOR}
    require(all(sha(path) == PINS[name] for name, path in paths.items()), "Registered source/profile/monitor raw pin differs")
    collector = module_at("registered_pending07_windows_check", COLLECTOR)
    checked = collector.validate_profile(PROFILE)
    profile = checked["profile"]
    require(collector.PRODUCTION_ENABLED is True and collector.PROFILE_STATUS == "REGISTERED_DEVELOPMENT_PREFIX11"
            and collector.REGISTERED_PROFILE_SHA256 == PINS["registered_profile"]
            and profile["native_output"] == "/root/uav_tracking_collection54_probe02_owner07",
            "Registered development-only collector/profile required")
    monitor = module_at("remaining07_existing_monitor", MONITOR)
    mounted = checked["library"].mounted
    monitor_output = Path(profile["windows_monitor_output"])
    require(monitor_output == ROOT / "results/monitor_humble54_probe02_owner07", "Fixed new monitor output differs")
    owner_unc = "\\\\wsl.localhost\\UAVHumble22" + profile["native_output"].replace("/", "\\")
    native = ["wsl.exe", "--distribution", "UAVHumble22", "--exec", "python3", "-B", mounted(str(COLLECTOR)),
              "--profile", mounted(str(PROFILE)), "--output", profile["native_output"], "--execute"]
    command = [sys.executable, "-B", str(MONITOR), "run", "--output", str(monitor_output),
               "--phase", "simulation", "--task-id", "humble54_probe02_remaining5_owner07",
               "--label", "humble54_probe02_remaining5_owner07", "--interval", "1", "--stale-after", "10",
               "--events", owner_unc + "\\events.jsonl", "--ledger", owner_unc + "\\state.json",
               "--plan", profile["sources"]["plan"]["path"], "--", *native]
    return {"scope": "SINGLE_WINDOWS_OWNED_MONITOR_REGISTERED_REMAINING_FIVE_ONLY", "command": command,
            "pins": {name: binding(path) for name, path in paths.items()} | {"plan": profile["sources"]["plan"]},
            "source": binding(Path(__file__).resolve()), "monitor_output": str(monitor_output), "receipt_output": str(RECEIPT),
            "native_output": profile["native_output"], "native_terminal_unc": owner_unc + "\\terminal.json",
            "closed_ids": checked["closed_ids"], "pending_ids": checked["pending_ids"], "creationflags": CREATION_FLAGS,
            "automatic_retry": False, "global_power_policy_changed": False}, monitor.process_identity


def observe_closure(state, output):
    """Read actual final small files after the real owned monitor has exited."""
    monitor_output = Path(state["monitor_output"])
    paths = {"monitor_final.json": monitor_output / "monitor_state.json",
             "monitor_end.json": monitor_output / "end_summary.json", "native_terminal.json": Path(state["native_terminal_unc"])}
    documents, hashes = {}, {}
    for name, path in paths.items():
        require(path.is_file() and path.stat().st_size <= 2 * 1024 * 1024, "Missing/oversized final small file: " + name)
        raw = path.read_bytes()
        documents[name] = json.loads(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
        with (output / name).open("xb") as handle:
            handle.write(raw)
    final, end, native = (documents[name] for name in ("monitor_final.json", "monitor_end.json", "native_terminal.json"))
    task, code = final["task"], state["owned_monitor_returncode"]
    require(final["monitor_process"]["pid"] == state["owned_monitor_identity"]["pid"]
            and final["monitor_process"]["start_token"] == state["owned_monitor_identity"]["start_token"]
            and task.get("monitor_kind") == "owned_child" and end["task"] == task
            and type(task.get("returncode")) is int and task["returncode"] == code
            and type(native.get("returncode")) is int and native["returncode"] == code
            and not native.get("child_may_still_be_active") and native.get("finished_utc")
            and native.get("automatic_retry") is False
            and native.get("status") == ("COLLECTION_FINISHED" if code == 0 else "STOPPED_FAULT"),
            "Actual owned monitor/WSL/native final identity or exit differs")
    if code == 0:
        require([row["slot_id"] for row in native["initial_closed"]] == state["closed_ids"]
                and [row["slot_id"] for row in native["collected"]] == state["pending_ids"]
                and native.get("current_slot") is None, "Completed native collector did not preserve eleven and collect exactly five")
    state.update(monitor_final={"path": str(paths["monitor_final.json"]), "sha256": hashes["monitor_final.json"]},
                 monitor_end={"path": str(paths["monitor_end.json"]), "sha256": hashes["monitor_end.json"]},
                 native_terminal={"path": state["native_output"] + "/terminal.json", "sha256": hashes["native_terminal.json"]},
                 artifacts=hashes, monitor_final_task=task, native_owner_identity=native["owner_identity"],
                 native_collection_status=native["status"], native_collection_returncode=native["returncode"], closure_verified=True)


def supervise(desc, output, power, identity, *, spawn=subprocess.Popen, pause=time.sleep, save=publish, closure=observe_closure):
    """Retain one Popen until its actual exit, including observer/interruption faults."""
    require(not output.exists(), "Fresh external receipt required; no resume/retry")
    require(not Path(desc["monitor_output"]).exists(), "Fresh monitor output required; no resume/retry")
    output.mkdir(parents=True, exist_ok=False)
    state = {**desc, "started_utc": utc(), "status": "STARTING", "launcher_identity": identity(os.getpid()),
             "owned_monitor_identity": None, "owned_monitor_returncode": None, "closure_verified": False,
             "errors": [], "interruptions": [], "returncode": 2}
    child = None
    requested = False

    def record_error(where, error):
        state["errors"].append({"utc": utc(), "where": where, "error": type(error).__name__ + ": " + str(error)})

    def checkpoint(name):
        try:
            save(output / name, state)
            return True
        except BaseException as error:
            record_error("metadata:" + name, error)
            return False

    def wait_owned():
        while True:
            try:
                code = child.poll()
                if code is not None:
                    actual = child.wait()
                    require(type(actual) is int, "Popen wait has no real integer exit")
                    if actual != code:
                        record_error("popen_exit_disagreement", ValueError("Popen poll and wait differ; original wait value retained"))
                    return actual
                state["heartbeat_utc"] = utc()
                checkpoint("state.json")
                pause(1)
            except BaseException as error:
                record_error("waiting_owned_monitor_no_kill_no_retry", error)
                # Continue with the same Popen; never terminate or replace it.

    try:
        thread = power.thread()
        requested = True
        result = power.request(0x80000003)
        state["power_lease"] = {"thread_id": thread, "flags": 0x80000003, "request_return": result,
                                "requested_utc": utc(), "global_power_policy_changed": False}
        require(type(result) is int and result != 0, "Temporary same-thread power request failed")
        require(checkpoint("started.json"), "No owned child starts without its initial durable receipt")
        with (output / "owned_monitor_stdout.log").open("xb") as log:
            child = spawn(desc["command"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=CREATION_FLAGS)
        state["monitor_started_utc"] = utc()
        state["owned_monitor_identity"] = identity(child.pid)
        require(state["owned_monitor_identity"].get("start_token"), "Owned monitor creation identity unavailable")
        state["status"] = "RUNNING"
        checkpoint("started.json")
    except BaseException as error:
        record_error("start_or_observe", error)
    finally:
        if child is not None:
            state["owned_monitor_returncode"] = wait_owned()
            state["owned_monitor_finished_utc"] = utc()
            try:
                closure(state, output)
            except BaseException as error:
                record_error("final_closure", error)
            for name, bound in desc.get("pins", {}).items():
                try:
                    require(sha(bound["path"]) == bound["sha256"], "Launched source/profile changed: " + name)
                except BaseException as error:
                    record_error("source_recheck", error)
        if requested:
            try:
                release_thread = power.thread()
                release_result = power.request(0x80000000)
                state.setdefault("power_lease", {}).update(release_thread_id=release_thread, release_return=release_result, released_utc=utc())
                require(release_thread == thread and type(release_result) is int and release_result != 0,
                        "Temporary power request was not released on its requesting thread")
            except BaseException as error:
                record_error("power_release", error)
        code = state["owned_monitor_returncode"]
        state["status"] = ("OWNED_MONITOR_ENDED" if code == 0 else "STOPPED_FAULT_NO_RETRY") if state["closure_verified"] and not state["errors"] else "SUPERVISOR_FAULT_PARTIALS_RETAINED_NO_RETRY"
        state["returncode"] = code if state["closure_verified"] and not state["errors"] else 2
        state["finished_utc"] = utc()
        if not checkpoint("terminal.json"):
            state.update(status="SUPERVISOR_FAULT_PARTIALS_RETAINED_NO_RETRY", returncode=2)
            checkpoint("terminal.json")
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        require(os.name == "nt", "Explicit Windows launcher only")
        desc, identity = description()
        require(not RECEIPT.exists() and not Path(desc["monitor_output"]).exists(), "Fresh fixed receipt and monitor output required")
        if not args.execute:
            print(json.dumps({"status": "REGISTERED_LAUNCH_CHECK_ONLY_NOT_STARTED", **desc}, ensure_ascii=True))
            return 0
        state = supervise(desc, RECEIPT, PowerLease(), identity)
        print(json.dumps({"status": state["status"], "owned_monitor_returncode": state["owned_monitor_returncode"],
                          "returncode": state["returncode"], "receipt": str(RECEIPT)}, ensure_ascii=True))
        return state["returncode"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "REFUSED_NOT_STARTED", "error": type(error).__name__ + ": " + str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
