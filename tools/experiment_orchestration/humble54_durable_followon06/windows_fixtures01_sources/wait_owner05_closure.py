"""Observe the bound owner05 handles, then audit the actual full owner chain.

Owner05 ended before this observer was launched. Production execution is now
disabled; these helpers and inert fixtures are preserved as preparation only.
No handle was acquired by this source. No WSL/native/capacity work is started.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EARLY = ROOT / "tools/experiment_orchestration/humble54_pending_collector05_registered/actual_start01"
PROFILE = ROOT / "tools/experiment_orchestration/humble54_pending_collector05_registered/registered_profile05.json"
CHAIN = ROOT / "tools/staging/final55_offline_overlay_profile02_20261103/validate_owner_chain.py"
SLOT = CHAIN.with_name("validate_owner_closure.py")
OUTPUT = ROOT / "results/diagnostics/humble54_probe02_durable_followon06"
ACTUAL_EXECUTION_ENABLED = False
PREPARATION_STATUS = "SUPERSEDED_BEFORE_LAUNCH_OWNER05_ALREADY_CLOSED"
CHAIN_SHA = "9cbbfbbfccccac9096a5cc122a21d8578e0fcbb3148357602dcdb834b143d97a"
SLOT_SHA = "945717313097725eba537f9078297f3e91e32bfdde89e810ed01ae7a2a3d546f"
PROFILE_SHA = "5ac96b104ac1e7ad24500657f38b329c968f9440e61f23e79d7bc27fc1df0bd0"
EARLY_MANIFEST_SHA = "ccca9ce27f115e9ec52f2662bf080c5d464502b4b990a60650fc862978ce8c55"
EXPECTED_HANDLES = {
    "monitor": {"pid": 29440, "start_token": "windows_filetime:134381580422253602"},
    "wsl": {"pid": 47940, "start_token": "windows_filetime:134381580424256581"},
    "outer": {"pid": 9872, "start_token": "windows_filetime:134381580420153869"},
}
DESCRIPTION_FIELDS = (
    "scope", "claim_boundary", "pins", "task_id", "native_owner", "owner_unc",
    "canonical_native_plan", "monitor_output", "receipt_output", "sources", "native_command",
    "monitor_command", "power_flags", "power_scope", "global_power_policy_changed", "automatic_retry",
    "registered_admission_unc",
)
CODE_PINS = {
    "launcher": (ROOT / "tools/experiment_orchestration/humble54_probe02_windows_owner05/start_owner05.py", "32479281e080e900f6eb7d5a98f2fd94865219672e59d35732ec387de53013fc"),
    "gate": (ROOT / "tools/experiment_orchestration/humble54_pending_collector05_registered/run_registered05.py", "cc22295766da78ff345f502e2f369af6527e359639a32b3d4d2f820ffc0989e3"),
    "collector": (ROOT / "tools/experiment_orchestration/humble54_pending_collector05_source/collect_humble54_pending05.py", "f6a01ac6d106ed89914745341b6faba6f1fe6dab92df6a651ae86e90adeb9ce1"),
    "monitor": (ROOT / "scripts/monitor_project_progress.py", "759136d0eda40bb3a61c9e30e0272e1f6b8810b351dbe4c75dc17db5951bfd98"),
    "chain_validator": (CHAIN, CHAIN_SHA), "slot_validator": (SLOT, SLOT_SHA),
    "registered_profile": (PROFILE, PROFILE_SHA),
}
MAX_SMALL = 2 * 1024 * 1024


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise ValueError(message)


def small_raw(path):
    path = Path(path)
    before = path.stat()
    require(path.is_file() and not path.is_symlink() and before.st_size <= MAX_SMALL, "Ordinary small metadata required: " + str(path))
    raw = path.read_bytes()
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), "Metadata changed while reading")
    return raw


def raw_sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return raw_sha(small_raw(path))


def parse(raw):
    result = json.loads(raw, parse_constant=lambda v: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    require(isinstance(result, dict), "Metadata object required")
    return result


def bound_json(path, pin):
    raw = small_raw(path)
    require(raw_sha(raw) == pin, "Fixed raw metadata/source SHA differs: " + str(path))
    return parse(raw)


def windows_local(reference):
    if reference.startswith("/root/"):
        return Path("\\\\wsl.localhost\\UAVHumble22" + reference.replace("/", "\\"))
    if reference.startswith("/mnt/") and len(reference) > 7 and reference[6] == "/":
        return Path(reference[5].upper() + ":/" + reference[7:])
    return Path(reference)


def check_code():
    for name, (path, pin) in CODE_PINS.items():
        require(sha(path) == pin, "Observed registered source changed: " + name)


def load_context():
    """Read fixed early small evidence only; never inspect current trial data."""
    check_code()
    manifest = bound_json(EARLY / "manifest.json", EARLY_MANIFEST_SHA)
    require(manifest["status"] == "ACTUAL_OWNER05_STARTED_NOT_CLOSED"
            and manifest["windows_native_prior_chain_equal"] is True, "Actual early registration differs")
    files, archived = {}, {}
    for row in manifest["files"]:
        name = row["archived_path"]
        require(Path(name).name == name and name not in archived, "Unexpected early snapshot name")
        archived[name] = bound_json(EARLY / name, row["sha256"])
        files[name] = {"path": row["original_path"], "sha256": row["sha256"]}
        if name != "windows_observation.json":
            require(sha(windows_local(row["original_path"])) == row["sha256"], "Original immutable early evidence changed")
    require(set(archived) == {"windows_started.json", "first_monitor_state.json", "first_native_state.json", "registered_admission.json", "windows_observation.json"}, "Actual early snapshot set differs")
    started, observed = archived["windows_started.json"], archived["windows_observation.json"]
    native, admission = archived["first_native_state.json"], archived["registered_admission.json"]
    identities = {"monitor": started["monitor_identity"], "wsl": observed["wsl_identity"], "outer": started["launcher_identity"]}
    for name, expected in EXPECTED_HANDLES.items():
        require({key: identities[name][key] for key in expected} == expected, "Actual creation-bound identity differs: " + name)
    require(observed["monitor_identity"] == identities["monitor"] and observed["launcher_identity"] == identities["outer"]
            and observed["first_native_owner_identity"] == native["owner_identity"] == admission["owner_identity"] == manifest["native_identity"]
            and observed["first_registered_admission_sha256"] == files["registered_admission.json"]["sha256"]
            and observed["status"] == "RUNNING" and observed["monitor_exit_code"] is None and observed["wsl_exit_code"] is None,
            "Actual early identity/admission evidence differs")
    for name, binding in started["pins"].items():
        require(sha(windows_local(binding["path"])) == binding["sha256"], "Actual invocation pin changed: " + name)
    require(started["launcher_source"]["sha256"] == CODE_PINS["launcher"][1]
            and started["pins"]["gate"]["sha256"] == CODE_PINS["gate"][1]
            and started["pins"]["chain_validator"]["sha256"] == CHAIN_SHA
            and started["pins"]["registered_profile"]["sha256"] == PROFILE_SHA,
            "Actual running registered source pins differ")
    prior = bound_json(PROFILE, PROFILE_SHA)
    return {"started": started, "observed": observed, "native_start": native, "admission": admission,
            "prior_profile": prior, "early_files": files, "identities": identities}


def atomic_json(path, value, *, new=False):
    path = Path(path)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write((json.dumps(value, indent=2, allow_nan=False) + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
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


class WindowsAPI:
    def __init__(self):
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.k.OpenProcess.restype = wintypes.HANDLE
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.k.CloseHandle.restype = wintypes.BOOL
        self.k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.k.GetProcessTimes.restype = wintypes.BOOL
        self.k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.k.WaitForSingleObject.restype = wintypes.DWORD
        self.k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.k.GetExitCodeProcess.restype = wintypes.BOOL

    def bind(self, identity):
        handle = self.k.OpenProcess(0x1000 | 0x100000, False, identity["pid"])
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        times = [wintypes.FILETIME() for _ in range(4)]
        try:
            if not self.k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise ctypes.WinError(ctypes.get_last_error())
            token = "windows_filetime:" + str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
            require(token == identity["start_token"], "PID creation identity changed before held-handle acquisition")
            return handle
        except BaseException:
            self.k.CloseHandle(handle)
            raise

    def exit(self, handle):
        state = self.k.WaitForSingleObject(handle, 0)
        if state == 258:
            return None
        if state != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = wintypes.DWORD()
        if not self.k.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(code.value)

    def close(self, handle):
        if not self.k.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def load_chain():
    check_code()
    spec = importlib.util.spec_from_file_location("fixed_followon06_owner_chain", CHAIN)
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def check_actual_close(context, exits, outer, native):
    require(set(exits) == set(EXPECTED_HANDLES) and all(type(value) is int and value == 0 for value in exits.values()), "Observed Windows handles did not all exit zero")
    started, observed = context["started"], context["observed"]
    require(outer.get("status") == "COLLECTION_ENDED" and outer.get("closure_verified") is True and outer.get("errors") == []
            and outer.get("native_collection_status") == native.get("status") == "COLLECTION_FINISHED"
            and outer.get("launcher_identity") == started["launcher_identity"]
            and outer.get("monitor_identity") == started["monitor_identity"] and outer.get("wsl_identity") == observed["wsl_identity"]
            and outer.get("first_native_owner_identity") == native.get("owner_identity") == context["native_start"]["owner_identity"]
            and native.get("returncode") == 0 and not native.get("child_may_still_be_active")
            and type(native.get("current_child", {}).get("returncode")) is int and native["current_child"]["returncode"] == 0,
            "Actual original outer/native closure is not complete and bound")
    for field in ("monitor_exit_code", "wsl_exit_code", "monitor_popen_wait_exit_code", "monitor_final_popen_wait_exit_code", "monitor_final_handle_exit_code", "wsl_final_handle_exit_code"):
        require(type(outer.get(field)) is int and outer[field] == 0, "Original held exit mismatch: " + field)
    require(outer.get("power_lease", {}).get("released_utc") and type(outer["power_lease"].get("release_return")) is int
            and outer["power_lease"]["release_return"] != 0, "Original temporary power lease was not released")


def full_profile(context, closure_files):
    """Called only with actual post-exit raw bindings, never placeholders."""
    started = context["started"]
    require(set(closure_files) == {"outer_terminal", "native_terminal", "monitor_final", "monitor_end", "events", "registered_entry_terminal"}
            and all(set(row) == {"path", "sha256"} and isinstance(row["sha256"], str) and len(row["sha256"]) == 64 for row in closure_files.values()), "Actual complete raw closure bindings required")
    result = deepcopy(context["prior_profile"])
    sources = deepcopy(started["pins"])
    sources["launcher"] = deepcopy(started["launcher_source"])
    files = context["early_files"]
    segment = {"segment_id": "owner05", "disposition": "COMPLETED", "after_slot": context["admission"]["after_slot"],
               "source_files": sources, "description": {key: deepcopy(started[key]) for key in DESCRIPTION_FIELDS},
               "launch_files": {"started": files["windows_started.json"], "first_monitor": files["first_monitor_state.json"],
                                "first_native": files["first_native_state.json"], "registered_admission": files["registered_admission.json"]},
               "closure_files": deepcopy(closure_files)}
    require(not any(row["segment_id"] == "owner05" for row in result["segments"]), "Owner05 is already present; no repeat segment")
    result["segments"].append(segment)
    return result


def close_chain(context, exits, output):
    check_code()
    chain = load_chain()
    started = context["started"]
    references = {"outer_terminal": str(Path(started["receipt_output"]) / "terminal.json"),
                  "native_terminal": started["native_owner"] + "/terminal.json",
                  "monitor_final": str(Path(started["monitor_output"]) / "monitor_state.json"),
                  "monitor_end": str(Path(started["monitor_output"]) / "end_summary.json"),
                  "events": started["native_owner"] + "/events.jsonl",
                  "registered_entry_terminal": started["native_owner"] + "/registered_entry_terminal.json"}
    raw = {key: chain.v.local_small_read(value) for key, value in references.items()}
    check_actual_close(context, exits, parse(raw["outer_terminal"]), parse(raw["native_terminal"]))
    bindings = {key: {"path": path, "sha256": raw_sha(raw[key])} for key, path in references.items()}
    profile = full_profile(context, bindings)
    audit = chain.validate_chain(profile)
    require(audit["status"] == "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION"
            and len(audit["closed_ids"]) == 16 and audit["pending_ids"] == [], "The actual owner chain did not close all original sixteen slots")
    check_code()
    atomic_json(output / "full_owner_chain_profile.json", profile, new=True)
    atomic_json(output / "owner_chain_audit.json", audit, new=True)
    return {"status": "FULL_OWNER_CHAIN_CLOSED_NOT_ENGINEERING_ADMISSION",
            "full_profile": {"path": str(output / "full_owner_chain_profile.json"), "sha256": sha(output / "full_owner_chain_profile.json")},
            "audit": {"path": str(output / "owner_chain_audit.json"), "sha256": sha(output / "owner_chain_audit.json")},
            "original_statuses": {name: sum(row["original_status"] == name for row in audit["closed"]) for name in ("PASS", "FAIL", "INCOMPLETE_EVIDENCE")},
            "pending_ids": [], "capacity_measurement": "NOT_RUN", "physical_inventory": "NOT_RUN"}


def supervise(context, output, api, *, pause=time.sleep, action=close_chain, publish=atomic_json):
    require(not output.exists(), "Fresh followon06 output required; no resume or automatic retry")
    output.mkdir(parents=True)
    state = {"scope": "DURABLE_WINDOWS_HELD_HANDLE_CLOSURE_ONLY", "status": "BINDING_ACTUAL_HANDLES", "started_utc": utc(),
             "source": {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)},
             "expected_handles": EXPECTED_HANDLES, "handles": {}, "errors": [], "automatic_retry": False,
             "future_closure": None, "capacity_measurement": "NOT_RUN", "physical_inventory": "NOT_RUN"}
    handles, exits = {}, {}
    fully_bound = False
    try:
        for name in EXPECTED_HANDLES:
            handles[name] = api.bind(context["identities"][name])
            state["handles"][name] = {"identity": context["identities"][name], "acquired_utc": utc(), "exit_code": None}
        fully_bound = True
        state["status"] = "WAITING_ACTUAL_OWNER05_CLOSURE"
        publish(output / "started.json", state, new=True)
        while len(exits) < len(handles):
            for name, handle in handles.items():
                if name not in exits:
                    code = api.exit(handle)
                    if code is not None:
                        exits[name] = code
                        state["handles"][name].update(exit_code=code, first_exit_observed_utc=utc())
            state["heartbeat_utc"] = utc()
            publish(output / "state.json", state)
            if len(exits) < len(handles):
                pause(1.0)
        require(all(type(code) is int and code == 0 for code in exits.values()), "Bound original process exited nonzero; no continuation or retry")
        require(sha(__file__) == state["source"]["sha256"], "Observer source changed while holding original handles")
        state["future_closure"] = action(context, exits, output)
        state["status"] = "CLOSURE_AUDIT_COMPLETED"
    except (Exception, KeyboardInterrupt) as error:
        state["status"] = "REFUSED_FAULT_PRESERVED_NO_RETRY"
        state["errors"].append({"utc": utc(), "error": f"{type(error).__name__}: {error}"})
    finally:
        # Once all three identities were acquired, retain each real handle even
        # after a metadata fault. Nothing else is started while their exit is unknown.
        if fully_bound:
            for name, handle in handles.items():
                while name not in exits:
                    try:
                        code = api.exit(handle)
                        if code is None:
                            pause(1.0)
                        else:
                            exits[name] = code
                            state["handles"][name].update(exit_code=code, first_exit_observed_utc=utc())
                    except KeyboardInterrupt:
                        state["errors"].append({"utc": utc(), "error": "KeyboardInterrupt while retaining original handles"})
                    except Exception as error:
                        state["status"] = "REFUSED_FAULT_PRESERVED_NO_RETRY"
                        state["errors"].append({"utc": utc(), "error": "Unknown held-handle exit: " + str(error)})
                        break
        for name, handle in handles.items():
            try:
                api.close(handle)
                state["handles"][name]["closed_utc"] = utc()
            except Exception as error:
                state["status"] = "REFUSED_FAULT_PRESERVED_NO_RETRY"
                state["errors"].append({"utc": utc(), "error": "Handle release failed: " + str(error)})
        state["finished_utc"] = utc()
        state["exit_codes"] = exits
        state["returncode"] = 0 if state["status"] == "CLOSURE_AUDIT_COMPLETED" else 2
        try:
            publish(output / "terminal.json", state, new=True)
        except Exception as error:
            state["status"] = "TERMINAL_PUBLICATION_FAILED_NO_RETRY"
            state["returncode"] = 2
            state["errors"].append({"utc": utc(), "error": "Terminal publication failed: " + str(error)})
            print(json.dumps({"status": state["status"], "state": state}), file=sys.stderr)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": PREPARATION_STATUS, "scope": "CLOSURE_ONLY", "expected_handles": EXPECTED_HANDLES,
                          "future_closure": None, "capacity_measurement": "NOT_RUN", "physical_inventory": "NOT_RUN"}))
        return 0
    if not ACTUAL_EXECUTION_ENABLED:
        print(json.dumps({"status": PREPARATION_STATUS, "execution_invoked": False,
                          "claim_boundary": "The owner ended before this observer was launched. No live-handle evidence was acquired."}))
        return 2
    require(sys.platform == "win32", "The actual durable observer requires Windows")
    context = load_context()
    result = supervise(context, OUTPUT, WindowsAPI())
    print(json.dumps({"status": result["status"], "returncode": result["returncode"], "terminal": str(OUTPUT / "terminal.json")}))
    return result["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
