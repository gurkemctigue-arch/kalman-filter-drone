"""Wait for actual durable07 proof, then own exactly one native runner08.

Default is inert and execution is disabled until root pins and arms reviewed
runner08. No global power policy, retries, staging, build or formal run exists.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
EXECUTION_ENABLED = False
RUNNER08_SHA256 = None  # Root must pin the actual reviewed, armed source.
RUNNER08 = ROOT / "tools/experiment_orchestration/humble54_closed_followon_runner08/run_followon08.py"
DURABLE07 = ROOT / "tools/experiment_orchestration/humble54_durable_followon07/wait_owner06_closure.py"
DURABLE07_SHA256 = "ed38a4469169f96364ee9bc79c52c892a3106954ee77c20efa35480eea5861a2"
CHAIN = ROOT / "tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_chain.py"
CHAIN_SHA256 = "b5aae1e007b009848555bbe3a9d9dfc4e6974f8afe4452c8b94e0aa31c547705"
SLOT = CHAIN.with_name("validate_owner_closure.py")
SLOT_SHA256 = "b3c086db30afe243bfdac423c0302c0285ebd64c8d7e8cb24b388e40fd81d744"
ORIGINAL07 = ROOT / "results/diagnostics/humble54_probe02_durable_followon07"
NATIVE08 = ROOT.drive + "/WSL/UAVHumble22-validation/humble54_probe02_closed_followon08"
OUTPUT = ROOT / "results/diagnostics/humble54_probe02_durable_followon09"
MAX_SMALL = 2 * 1024 * 1024
STEP_IDS = ["native_idle", *["tool_" + str(i) for i in range(5)], "measure_actual28", "physical_inventory",
            "person_velocity_export", "car_velocity_export", "R0_candidate", "full280_budget"]


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def small_raw(path):
    path = Path(path)
    before = path.stat()
    require(path.is_file() and not path.is_symlink() and before.st_size <= MAX_SMALL, "Ordinary small metadata required: " + str(path))
    raw = path.read_bytes()
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), "Small file changed while reading")
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def binding(path):
    return {"path": str(path), "sha256": sha(small_raw(path))}


def parse(raw):
    value = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    require(isinstance(value, dict), "JSON metadata object required")
    return value


def fixed_module(path, pin):
    require(isinstance(pin, str) and len(pin) == 64, "Root has not pinned the actual armed runner08")
    raw = small_raw(path)
    require(sha(raw) == pin, "Reviewed source differs: " + str(path))
    module = types.ModuleType("fixed_trigger09_" + path.stem)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def check_sources():
    for path, pin in ((RUNNER08, RUNNER08_SHA256), (DURABLE07, DURABLE07_SHA256), (CHAIN, CHAIN_SHA256), (SLOT, SLOT_SHA256)):
        require(isinstance(pin, str) and len(pin) == 64 and sha(small_raw(path)) == pin, "Actual reviewed source pin differs: " + str(path))


def atomic_json(path, value, *, new=False):
    path = Path(path)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write((json.dumps(value, indent=2, allow_nan=False) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        if new:
            os.link(temporary, path)
        else:
            deadline = time.monotonic() + 3.0
            while True:
                try:
                    os.replace(temporary, path)
                    break
                except OSError as error:
                    if getattr(error, "winerror", None) not in {5, 32, 33} or time.monotonic() >= deadline:
                        raise
                    time.sleep(.02)
    finally:
        temporary.unlink(missing_ok=True)


def mounted(path):
    path = Path(path).resolve()
    require(len(path.drive) == 2 and path.drive[1] == ":", "A local drive path is required")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def load_context():
    check_sources()
    runner = fixed_module(RUNNER08, RUNNER08_SHA256)
    require(runner.EXECUTION_ENABLED is True, "Actual runner08 remains disabled")
    observer = fixed_module(DURABLE07, DURABLE07_SHA256)
    original = observer.load_context()  # Immutable original06 early evidence only.
    started_binding = binding(ORIGINAL07 / "started.json")
    started = parse(small_raw(ORIGINAL07 / "started.json"))
    require(started.get("status") == "WAITING_ACTUAL_OWNER06_CLOSURE"
            and started.get("scope") == "DURABLE_WINDOWS_HELD_HANDLE_CLOSURE_ONLY"
            and started.get("errors") == [] and started.get("automatic_retry") is False
            and started.get("expected_handles") == observer.EXPECTED_HANDLES
            and started.get("source") == {"path": str(DURABLE07), "sha256": DURABLE07_SHA256}, "Actual durable07 start differs")
    require(set(started.get("handles", {})) == set(observer.EXPECTED_HANDLES), "Durable07 did not acquire all three original handles")
    for name, row in started["handles"].items():
        require(row.get("identity") == original["identities"][name] and row.get("alive_at_acquisition_observed_utc")
                and row.get("exit_code") is None, "Durable07 actual live acquisition evidence differs")
    return {"runner": runner, "observer": observer, "chain": observer.load_chain(), "original": original,
            "started07": started, "started07_binding": started_binding}


def validate_ready(context):
    """Only called after the original07 terminal has actually appeared."""
    check_sources()
    chain, runner, observer = context["chain"], context["runner"], context["observer"]
    inputs = chain.v.Inputs(chain.v.local_small_read)
    inputs.bound(context["started07_binding"])
    profile_binding = binding(ORIGINAL07 / "full_owner_chain_profile.json")
    closure_binding = binding(ORIGINAL07 / "terminal.json")
    audit = runner.validate_closure(chain, inputs, profile_binding, closure_binding, runner.paths())
    profile, closure = inputs.json(profile_binding), inputs.json(closure_binding)
    started = context["started07"]
    require(closure.get("started_utc") == started["started_utc"] and closure.get("expected_handles") == started["expected_handles"]
            and closure.get("automatic_retry") is False, "Durable07 terminal belongs to another start")
    now = datetime.now(timezone.utc)
    for name, early in started["handles"].items():
        row = closure["handles"][name]
        require(all(row.get(key) == early.get(key) for key in ("identity", "acquired_utc", "alive_at_acquisition_observed_utc")),
                "Actual original07 held identity/acquisition changed")
        require(chain.v.timestamp(row["acquired_utc"], now) <= chain.v.timestamp(row["alive_at_acquisition_observed_utc"], now)
                <= chain.v.timestamp(row["first_exit_observed_utc"], now), "Original07 live acquisition chronology differs")
    segment = profile["segments"][-1]
    require(segment.get("segment_id") == "owner06" and profile == observer.full_profile(context["original"], segment["closure_files"]),
            "Actual prior chain plus exactly original06 is required")
    files = segment["closure_files"]
    observer.check_actual_close(context["original"], closure["exit_codes"], inputs.json(files["outer_terminal"]), inputs.json(files["native_terminal"]))
    inputs.unchanged()
    return {"profile": profile_binding, "closure": closure_binding, "audit": audit, "inputs": inputs}


def child_command(proof):
    return ["wsl.exe", "--distribution", "UAVHumble22", "--exec", "python3", "-B", mounted(RUNNER08), "--execute",
            "--full-chain-profile", mounted(proof["profile"]["path"]), "--full-chain-profile-sha256", proof["profile"]["sha256"],
            "--durable07-closure", mounted(proof["closure"]["path"]), "--durable07-closure-sha256", proof["closure"]["sha256"]]


def validate_completion(context, proof, state):
    terminal_binding = binding(Path(NATIVE08) / "terminal.json")
    terminal = parse(small_raw(terminal_binding["path"]))
    chain = context["chain"]
    require(terminal.get("scope") == "NATIVE_SERIAL_FOLLOWON08_ACTUAL28_R0_BUDGET_ONLY"
            and terminal.get("status") == "COMPLETED_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION"
            and type(terminal.get("returncode")) is int and terminal["returncode"] == 0
            and terminal.get("errors") == [] and terminal.get("interruptions") == [] and terminal.get("automatic_retry") is False,
            "Actual original08 successful terminal is absent or incomplete")
    require(terminal.get("source", {}).get("sha256") == RUNNER08_SHA256
            and chain.v.local_path(terminal["source"]["path"]).resolve() == RUNNER08.resolve(), "Original08 source differs")
    for field, expected in (("full_chain_profile", proof["profile"]), ("durable07_closure", proof["closure"])):
        actual = terminal[field]
        require(actual["sha256"] == expected["sha256"] and chain.v.local_path(actual["path"]).resolve() == Path(expected["path"]).resolve(),
                "Original08 used different closure inputs")
    require(terminal.get("closed_ids") == proof["audit"]["closed_ids"] and len(set(terminal["closed_ids"])) == 16,
            "Original08 did not use the complete original16")
    require([row["id"] for row in terminal.get("steps", [])] == STEP_IDS
            and all(type(row.get("returncode")) is int and row["returncode"] == 0 for row in terminal["steps"]),
            "Original08 full exact serial steps did not all exit zero")
    now = datetime.now(timezone.utc)
    require(chain.v.timestamp(state["child"]["started_utc"], now) <= chain.v.timestamp(terminal["started_utc"], now)
            <= chain.v.timestamp(terminal["finished_utc"], now) <= chain.v.timestamp(state["child"]["finished_utc"], now),
            "Original08 completion chronology differs")
    proof["inputs"].unchanged()
    check_sources()
    require(binding(terminal_binding["path"]) == terminal_binding, "Original08 terminal changed while checking")
    return {"terminal": terminal_binding, "status": terminal["status"], "stage_build_formal": "NOT_RUN"}


class WindowsAPI:
    def __init__(self):
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.GetCurrentProcess.restype = wintypes.HANDLE
        self.k.GetCurrentThreadId.restype = wintypes.DWORD
        self.k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.k.GetProcessTimes.restype = wintypes.BOOL
        self.k.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.k.DuplicateHandle.restype = wintypes.BOOL
        self.k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.k.WaitForSingleObject.restype = wintypes.DWORD
        self.k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.k.GetExitCodeProcess.restype = wintypes.BOOL
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.k.CloseHandle.restype = wintypes.BOOL
        self.k.SetThreadExecutionState.argtypes = [wintypes.DWORD]
        self.k.SetThreadExecutionState.restype = wintypes.DWORD

    def thread_id(self):
        return int(self.k.GetCurrentThreadId())

    def power(self, flags):
        return int(self.k.SetThreadExecutionState(flags))

    def creation(self, handle):
        times = [wintypes.FILETIME() for _ in range(4)]
        if not self.k.GetProcessTimes(handle, *(ctypes.byref(row) for row in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        return "windows_filetime:" + str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)

    def bind_child(self, child):
        # Duplicate the retained Popen creation handle: no PID-name lookup or reuse race.
        original = wintypes.HANDLE(int(child._handle))
        identity = {"pid": child.pid, "start_token": self.creation(original)}
        process, duplicate = self.k.GetCurrentProcess(), wintypes.HANDLE()
        if not self.k.DuplicateHandle(process, original, process, ctypes.byref(duplicate), 0, False, 2):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            require(self.creation(duplicate) == identity["start_token"], "Owned Popen/duplicate creation identity differs")
            return duplicate, identity
        except BaseException:
            self.close(duplicate)
            raise

    def exit(self, handle):
        result = self.k.WaitForSingleObject(handle, 0)
        if result == 258:
            return None
        if result != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = wintypes.DWORD()
        if not self.k.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(code.value)

    def close(self, handle):
        if not self.k.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def supervise(context, output, api, *, pause=time.sleep, ready=validate_ready, complete=validate_completion,
              publish=atomic_json, launch=subprocess.Popen, check=check_sources):
    output = Path(output)
    require(not output.exists() and not output.is_symlink() and output.parent.is_dir(), "Fresh09 output required; no resume/retry")
    output.mkdir()
    state = {"scope": "WINDOWS_DURABLE07_TO_NATIVE08_SINGLE_OWNED_TRIGGER", "status": "STARTING", "started_utc": utc(),
             "source": binding(__file__), "durable07_started": context["started07_binding"], "errors": [], "interruptions": [],
             "automatic_retry": False, "global_power_policy_changed": False, "child": None, "completion": None,
             "stage_build_formal": "NOT_RUN"}
    child, held, power_attempted, proof = None, None, False, None

    def fault(error):
        state["status"] = "REFUSED_OR_STOPPED_PARTIALS_RETAINED_NO_RETRY"
        state["errors"].append({"utc": utc(), "error": f"{type(error).__name__}: {error}"})

    try:
        check()
        lease = state["power_lease"] = {"thread_id": api.thread_id(), "scope": "CURRENT_THREAD_SYSTEM_AND_DISPLAY", "flags": 0x80000003}
        power_attempted = True
        lease.update(request_return=api.power(0x80000003), requested_utc=utc())
        require(type(lease["request_return"]) is int and lease["request_return"] != 0, "Current-thread power request was not accepted")
        state["status"] = "WAITING_ACTUAL_DURABLE07_TERMINAL"
        publish(output / "started.json", state, new=True)
        while not (ORIGINAL07 / "terminal.json").exists():
            state["heartbeat_utc"] = utc()
            publish(output / "state.json", state)
            pause(1.0)
        proof = ready(context)
        state["actual_inputs"] = {"full_chain_profile": proof["profile"], "durable07_closure": proof["closure"],
                                  "closed_ids": proof["audit"]["closed_ids"]}
        require(not Path(NATIVE08).exists() and not Path(NATIVE08).is_symlink(), "Original08 output already exists; no resume/retry")
        state["status"] = "STARTING_ONE_OWNED_NATIVE08"
        state["child"] = {"command": child_command(proof), "started_utc": utc(), "popen_wait_exit_code": None}
        publish(output / "state.json", state)
        check()
        require(binding(__file__) == state["source"], "Trigger09 source changed")
        proof["inputs"].unchanged()
        with (output / "runner08.stdout.log").open("xb") as stdout, (output / "runner08.stderr.log").open("xb") as stderr:
            try:
                child = launch(state["child"]["command"], cwd=ROOT, stdout=stdout, stderr=stderr,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                state["child"]["pid"] = child.pid
                held, identity = api.bind_child(child)
                state["child"].update(identity=identity, handle_acquired_utc=utc())
                state["status"] = "WAITING_OWNED_NATIVE08_ACTUAL_EXIT"
                publish(output / "state.json", state)
                while state["child"]["popen_wait_exit_code"] is None:
                    try:
                        state["child"]["popen_wait_exit_code"] = child.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        state["heartbeat_utc"] = utc()
                        publish(output / "state.json", state)
            finally:
                # Even a failed metadata write cannot detach the actual Popen child.
                if child is not None:
                    while state["child"]["popen_wait_exit_code"] is None:
                        try:
                            state["child"]["popen_wait_exit_code"] = child.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            pass
                        except BaseException as error:
                            fault(error)
                            state["interruptions"].append({"utc": utc(), "action": "WAIT_ORIGINAL_CHILD_NO_SIGNAL_RETRY_OR_DETACH"})
                            pause(1.0)
                    state["child"]["finished_utc"] = utc()
        require(held is not None, "Owned child creation handle was not retained")
        state["child"]["held_handle_exit_code"] = api.exit(held)
        require(type(state["child"]["popen_wait_exit_code"]) is int and state["child"]["popen_wait_exit_code"] == 0
                and type(state["child"]["held_handle_exit_code"]) is int and state["child"]["held_handle_exit_code"] == 0,
                "Original08 Popen/held-handle exits were not both zero")
        require(state["errors"] == [], "Child supervision had an interruption/fault")
        state["completion"] = complete(context, proof, state)
        state["status"] = "COMPLETED_OWNED08_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION"
    except BaseException as error:
        fault(error)
    finally:
        if held is not None:
            try:
                state["child"]["final_held_handle_exit_code"] = api.exit(held)
                require(type(state["child"]["final_held_handle_exit_code"]) is int
                        and state["child"]["final_held_handle_exit_code"] == state["child"]["popen_wait_exit_code"],
                        "Final held-handle/Popen exit differs")
            except BaseException as error:
                fault(error)
            try:
                api.close(held)
                state["child"]["handle_closed_utc"] = utc()
            except BaseException as error:
                fault(error)
        if power_attempted:
            try:
                state["power_lease"].update(release_return=api.power(0x80000000), released_utc=utc())
                require(type(state["power_lease"]["release_return"]) is int and state["power_lease"]["release_return"] != 0,
                        "Current-thread power release failed")
            except BaseException as error:
                fault(error)
        state["finished_utc"] = utc()
        state["returncode"] = 0 if state["status"] == "COMPLETED_OWNED08_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION" else 2
        try:
            publish(output / "terminal.json", state, new=True)
        except BaseException as error:
            fault(error)
            state["returncode"] = 2
            print(json.dumps({"status": "TERMINAL_PUBLICATION_FAILED_NO_RETRY", "state": state}), file=sys.stderr)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "PREPARED_DISABLED_NOT_STARTED", "execution_enabled": EXECUTION_ENABLED,
                          "runner08_armed_source_sha256": RUNNER08_SHA256, "automatic_retry": False, "stage_build_formal": "NOT_AVAILABLE"}))
        return 0
    if not EXECUTION_ENABLED:
        print(json.dumps({"status": "DISABLED_NOT_STARTED", "execution_invoked": False}))
        return 2
    require(sys.platform == "win32", "Trigger09 must own its Windows child and current-thread lease")
    result = supervise(load_context(), OUTPUT, WindowsAPI())
    print(json.dumps({"status": result["status"], "returncode": result["returncode"]}))
    return result["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
