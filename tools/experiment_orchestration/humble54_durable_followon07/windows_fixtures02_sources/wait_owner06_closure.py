"""Observe the bound owner06 handles, then audit the actual full owner chain.

Default is inert. Explicit --execute retains three creation-bound Windows
handles and only audits closure after their actual zero exits. No native
command, experiment, capacity measurement or inventory process is started.
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
EARLY = ROOT / "tools/experiment_orchestration/humble54_probe02_windows_owner06/actual_start01"
PROFILE = ROOT / "tools/experiment_orchestration/humble54_pending_collector06_registered/registered_profile06.json"
CHAIN = ROOT / "tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_chain.py"
SLOT = CHAIN.with_name("validate_owner_closure.py")
OUTPUT = ROOT / "results/diagnostics/humble54_probe02_durable_followon07"
ACTUAL_EXECUTION_ENABLED = True
PREPARATION_STATUS = "PREPARED_NOT_EXECUTED"
CHAIN_SHA = "b5aae1e007b009848555bbe3a9d9dfc4e6974f8afe4452c8b94e0aa31c547705"
SLOT_SHA = "b3c086db30afe243bfdac423c0302c0285ebd64c8d7e8cb24b388e40fd81d744"
PROFILE_SHA = "cf176db9ef9fd0ee70cd2e7631dc1d518c0c9289940c83eabd89497d10161678"
EARLY_MANIFEST_SHA = "07ad158f45d0e082cfb9a02823dbf85afdff2c4384907bb9ba2cdb18a6e69353"
REGISTERED_UNKNOWN_EVIDENCE = {"person_extension_dropout_seed004": "c09f95ee3c4d5f14847bcbea82e8795b11cab6f5184fe735abac4c22decaeba8"}
EXPECTED_HANDLES = {
    "monitor": {"pid": 22632, "start_token": "windows_filetime:134381603781453202"},
    "wsl": {"pid": 12812, "start_token": "windows_filetime:134381603784377166"},
    "outer": {"pid": 47044, "start_token": "windows_filetime:134381603778483580"},
}
DESCRIPTION_FIELDS = (
    "scope", "claim_boundary", "pins", "task_id", "native_owner", "owner_unc",
    "canonical_native_plan", "monitor_output", "receipt_output", "sources", "native_command",
    "monitor_command", "power_flags", "power_scope", "global_power_policy_changed", "automatic_retry",
    "registered_admission_unc",
)
CODE_PINS = {
    "launcher": (ROOT / "tools/experiment_orchestration/humble54_probe02_windows_owner06/start_owner06.py", "24df3a49a0b235dd3a1a3dbf5a6506bb4e26371eb650709f3bb267471ea65d0c"),
    "gate": (ROOT / "tools/experiment_orchestration/humble54_pending_collector06_registered/run_registered06.py", "1bd31770ccd35c93f36d10068995c5d96c28a35c25ed6c3c35b04ce9555c1922"),
    "collector": (ROOT / "tools/experiment_orchestration/humble54_pending_collector06_source/collect_humble54_pending06.py", "cd325e39a0d49a2c890813217af8e97d8ee8efb290f645ffa3ff9b1a7d1293cf"),
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
    manifest = bound_json(EARLY / "snapshot_receipt.json", EARLY_MANIFEST_SHA)
    require(manifest["kind"] == "ACTUAL_OWNER06_START_ONLY_NOT_CLOSURE"
            and manifest["windows_native_stable_admission_equal"] is True, "Actual early registration differs")
    files, archived = {}, {}
    for row in manifest["files"]:
        name = row["copy"]
        require(Path(name).name == name and name not in archived, "Unexpected early snapshot name")
        archived[name] = bound_json(EARLY / name, row["sha256"])
        files[name] = {"path": row["source"], "sha256": row["sha256"]}
        require(sha(windows_local(row["source"])) == row["sha256"], "Original immutable early evidence changed")
    require(set(archived) == {"started.json", "first_monitor_state.json", "first_native_state.json", "first_registered_admission.json"}, "Actual early snapshot set differs")
    started, first_monitor = archived["started.json"], archived["first_monitor_state.json"]
    native, admission = archived["first_native_state.json"], archived["first_registered_admission.json"]
    identities = {"monitor": started["monitor_identity"], "wsl": first_monitor["task"]["process"], "outer": started["launcher_identity"]}
    for name, expected in EXPECTED_HANDLES.items():
        require({key: identities[name][key] for key in expected} == expected, "Actual creation-bound identity differs: " + name)
    require(first_monitor["monitor_process"] == identities["monitor"]
            and first_monitor["task"]["id"] == started["task_id"]
            and first_monitor["task"]["monitor_kind"] == "owned_child"
            and first_monitor["task"]["returncode"] is None and first_monitor["task"]["finished_utc"] is None
            and native["owner_identity"] == admission["owner_identity"] and native["status"] == "RUNNING"
            and admission["scope"] == "REGISTERED_PREFIX_ADMISSION_BEFORE_NEW_OWNER06_CHILDREN"
            and admission["unknown_evidence_exceptions"] == REGISTERED_UNKNOWN_EVIDENCE
            and admission["automatic_retry"] is False,
            "Actual early identity/admission evidence differs")
    for name, binding in started["pins"].items():
        require(sha(windows_local(binding["path"])) == binding["sha256"], "Actual invocation pin changed: " + name)
    require(started["launcher_source"]["sha256"] == CODE_PINS["launcher"][1]
            and started["pins"]["gate"]["sha256"] == CODE_PINS["gate"][1]
            and started["pins"]["chain_validator"]["sha256"] == CHAIN_SHA
            and started["pins"]["registered_profile"]["sha256"] == PROFILE_SHA,
            "Actual running registered source pins differ")
    admission_pin = files["first_registered_admission.json"]["sha256"]
    require(sha(windows_local(started["registered_admission_unc"])) == admission_pin,
            "Original external admission differs from the actual early raw copy")
    files["windows_started.json"] = files.pop("started.json")
    files["registered_admission.json"] = {"path": started["registered_admission_unc"], "sha256": admission_pin}
    files.pop("first_registered_admission.json")
    prior = bound_json(PROFILE, PROFILE_SHA)
    return {"started": started, "observed": {"wsl_identity": identities["wsl"]}, "native_start": native, "admission": admission,
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
    spec = importlib.util.spec_from_file_location("fixed_followon07_owner_chain", CHAIN)
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
    segment = {"segment_id": "owner06", "disposition": "COMPLETED", "after_slot": context["admission"]["after_slot"],
               "source_files": sources, "description": {key: deepcopy(started[key]) for key in DESCRIPTION_FIELDS},
               "launch_files": {"started": files["windows_started.json"], "first_monitor": files["first_monitor_state.json"],
                                "first_native": files["first_native_state.json"], "registered_admission": files["registered_admission.json"]},
               "closure_files": deepcopy(closure_files)}
    require(not any(row["segment_id"] == "owner06" for row in result["segments"]), "Owner05 is already present; no repeat segment")
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
    require(not output.exists(), "Fresh followon07 output required; no resume or automatic retry")
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
            require(api.exit(handles[name]) is None, "Original process already exited before live held-handle acquisition: " + name)
            state["handles"][name]["alive_at_acquisition_observed_utc"] = utc()
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
        print(json.dumps({"status": "DISABLED_NOT_STARTED", "execution_invoked": False,
                          "claim_boundary": "The observer execution gate is disabled; no handle is acquired."}))
        return 2
    require(sys.platform == "win32", "The actual durable observer requires Windows")
    context = load_context()
    result = supervise(context, OUTPUT, WindowsAPI())
    print(json.dumps({"status": result["status"], "returncode": result["returncode"], "terminal": str(OUTPUT / "terminal.json")}))
    return result["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
