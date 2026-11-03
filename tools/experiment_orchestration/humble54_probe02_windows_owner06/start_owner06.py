"""Prepared Windows supervisor for a registered preserved-prefix owner06.

Production is disabled until root registers actual closure/profile/source pins.
No WSL command is called by the prepared default or by a refused --execute.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
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
ROOT = Path(__file__).resolve().parents[3]
MONITOR = ROOT / "scripts/monitor_project_progress.py"
COLLECTOR = ROOT / "tools/experiment_orchestration/humble54_pending_collector06_source/collect_humble54_pending06.py"
GATE = ROOT / "tools/experiment_orchestration/humble54_pending_collector06_registered/run_registered06.py"
CHAIN = ROOT / "tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_chain.py"
PROFILE = ROOT / "tools/experiment_orchestration/humble54_pending_collector06_registered/registered_profile06.json"
PROFILE_STATUS = "REGISTERED_ACTUAL_CLOSED_PREFIX_CHAIN"
ENTRY = Path("D:/WSL/UAVHumble22-validation/run_humble54_pending_probe02_one03.sh")
PLAN = ROOT / "results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/plan.json"
PINS = {
    "monitor": "759136d0eda40bb3a61c9e30e0272e1f6b8810b351dbe4c75dc17db5951bfd98",
    "collector": "cd325e39a0d49a2c890813217af8e97d8ee8efb290f645ffa3ff9b1a7d1293cf",
    "gate": "1bd31770ccd35c93f36d10068995c5d96c28a35c25ed6c3c35b04ce9555c1922",
    "chain_validator": "b5aae1e007b009848555bbe3a9d9dfc4e6974f8afe4452c8b94e0aa31c547705",
    "registered_profile": "cf176db9ef9fd0ee70cd2e7631dc1d518c0c9289940c83eabd89497d10161678",
    "entry": "d9cc1f1876a5ed9a358697b29644e7aa7a3c192e0bdd2a2a7d37c208e74f06a6",
    "plan": "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54",
}
REGISTERED_UNKNOWN_EVIDENCE = {"person_extension_dropout_seed004": "c09f95ee3c4d5f14847bcbea82e8795b11cab6f5184fe735abac4c22decaeba8"}
TASK = "humble54_probe02_preserved_pending_owner06"
NATIVE_OWNER = "/root/uav_tracking_collection54_probe02_owner06"
OWNER_UNC = Path(r"\\wsl.localhost\UAVHumble22\root\uav_tracking_collection54_probe02_owner06")
ADMISSION_UNC = OWNER_UNC.with_name(OWNER_UNC.name + ".admission.json")
MONITOR_OUT = ROOT / "results/monitor_humble54_probe02_owner06"
OUTPUT = ROOT / "results/diagnostics/humble54_probe02_windows_owner06"


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf8")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def mounted(path):
    path = Path(path).resolve()
    return "/mnt/" + path.drive[0].lower() + "/" + "/".join(path.parts[1:])


CANONICAL_NATIVE_PLAN = mounted(PLAN)


def check_admission(admission):
    if (admission["gate_source"] != {"path": mounted(GATE), "sha256": PINS["gate"]}
            or admission["profile"] != {"path": mounted(PROFILE), "sha256": PINS["registered_profile"]}
            or admission["chain_validator"] != {"path": mounted(CHAIN), "sha256": PINS["chain_validator"]}
            or admission["collector"] != {"path": mounted(COLLECTOR), "sha256": PINS["collector"]}
            or admission["plan"]["sha256"] != PINS["plan"]
            or admission["chain_admission"]["status"] != "BOUND_PRESERVED_PREFIX_CHAIN"
            or admission["unknown_evidence_exceptions"] != REGISTERED_UNKNOWN_EVIDENCE or admission["automatic_retry"] is not False):
        raise ValueError("Early registered gate/profile/closed-prefix admission differs")


def check_gate_terminal(gate_terminal, row, native, native_raw):
    if (row.get("first_registered_admission_owner_identity") != native["owner_identity"]
            or gate_terminal["gate_source"] != {"path": mounted(GATE), "sha256": PINS["gate"]}
            or gate_terminal["profile"] != {"path": mounted(PROFILE), "sha256": PINS["registered_profile"]}
            or gate_terminal["admission"] != {"path": NATIVE_OWNER + ".admission.json", "sha256": row.get("first_registered_admission_sha256")}
            or sha(ADMISSION_UNC) != row.get("first_registered_admission_sha256")
            or gate_terminal["native_terminal"] != {"path": NATIVE_OWNER + "/terminal.json", "sha256": hashlib.sha256(native_raw).hexdigest()}
            or gate_terminal["returncode"] != native["returncode"] or gate_terminal["status"] != native["status"]):
        raise ValueError("Registered entry terminal/admission/native closure differs")


def description():
    if PROFILE_STATUS != "REGISTERED_ACTUAL_CLOSED_PREFIX_CHAIN":
        raise ValueError("Actual closed-prefix profile and registered source pins are not registered")
    paths = {"monitor": MONITOR, "collector": COLLECTOR, "gate": GATE, "chain_validator": CHAIN,
             "registered_profile": PROFILE, "entry": ENTRY, "plan": PLAN}
    for name, path in paths.items():
        if not isinstance(PINS[name], str) or len(PINS[name]) != 64 or sha(path) != PINS[name]:
            raise ValueError("Pinned source differs: " + name)
    native = ["wsl.exe", "--distribution", "UAVHumble22", "--exec", "python3", "-B", mounted(GATE),
              "--profile", mounted(PROFILE),
              "--output", NATIVE_OWNER, "--execute"]
    sources = {"events": str(OWNER_UNC / "events.jsonl"), "ledger": str(OWNER_UNC / "state.json"), "plan": str(PLAN)}
    command = [sys.executable, "-B", str(MONITOR), "run", "--output", str(MONITOR_OUT),
               "--phase", "simulation", "--task-id", TASK, "--label", TASK,
               "--interval", "1", "--stale-after", "10"]
    for name, path in sources.items():
        command.extend(["--" + name, path])
    return {"scope": "WINDOWS_OWNER_OF_REGISTERED_PRESERVED_PREFIX_CONTINUATION",
            "claim_boundary": "Execution closure only; original engineering FAIL/INCOMPLETE remain unchanged. No formal readiness claim.",
            "pins": {name: {"path": str(path), "sha256": PINS[name]} for name, path in paths.items()},
            "task_id": TASK, "native_owner": NATIVE_OWNER, "owner_unc": str(OWNER_UNC),
            "registered_admission_unc": str(ADMISSION_UNC),
            "canonical_native_plan": CANONICAL_NATIVE_PLAN,
            "monitor_output": str(MONITOR_OUT), "receipt_output": str(OUTPUT), "sources": sources,
            "native_command": native, "monitor_command": command + ["--"] + native,
            "power_flags": 0x80000003, "power_scope": "TEMPORARY_SYSTEM_AND_DISPLAY_REQUEST_ON_THIS_OWNER_THREAD",
            "global_power_policy_changed": False, "automatic_retry": False}


class WindowsAPI:
    def __init__(self):
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.k.OpenProcess.restype = wintypes.HANDLE
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.k.CloseHandle.restype = wintypes.BOOL
        self.k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.k.GetProcessTimes.restype = wintypes.BOOL
        self.k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.k.GetExitCodeProcess.restype = wintypes.BOOL
        self.k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.k.WaitForSingleObject.restype = wintypes.DWORD
        self.k.SetThreadExecutionState.argtypes = [wintypes.DWORD]
        self.k.SetThreadExecutionState.restype = wintypes.DWORD

    def bind(self, identity):
        handle = self.k.OpenProcess(0x1000 | 0x100000, False, identity["pid"])
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        times = [wintypes.FILETIME() for _ in range(4)]
        if not self.k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            self.k.CloseHandle(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        token = "windows_filetime:" + str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        if token != identity["start_token"]:
            self.k.CloseHandle(handle)
            raise ValueError("PID creation identity changed before handle acquisition")
        return handle

    def exit(self, handle):
        wait = self.k.WaitForSingleObject(handle, 0)
        if wait == 258:
            return None
        if wait != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = wintypes.DWORD()
        if not self.k.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(code.value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if PROFILE_STATUS != "REGISTERED_ACTUAL_CLOSED_PREFIX_CHAIN":
        print(json.dumps({"status": "PREPARED_NOT_REGISTERED_NOT_STARTED", "profile_status": PROFILE_STATUS,
                          "actual_prefix": None, "registered_profile_sha256": None,
                          "claim_boundary": "No actual closure profile or launch is configured."}))
        return 2 if args.execute else 0
    desc = description()
    if not args.execute:
        print(json.dumps({"status": "NOT_STARTED", **desc}))
        return 0
    if sys.platform != "win32":
        raise ValueError("Actual supervision requires Windows")
    if OUTPUT.exists() or MONITOR_OUT.exists() or OWNER_UNC.exists() or ADMISSION_UNC.exists():
        raise ValueError("Fresh Windows receipt, monitor and native owner directories required; no resume")
    OUTPUT.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("pinned_generic_windows_monitor", MONITOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    api = WindowsAPI()
    row = {**desc, "status": "STARTING", "started_utc": utc(),
           "launcher_source": {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)},
           "launcher_identity": module.process_identity(os.getpid()), "errors": []}
    monitor = None
    monitor_handle = None
    wsl_handle = None
    power = False
    try:
        with (OUTPUT / "monitor_stdout.log").open("wb") as stdout, (OUTPUT / "monitor_stderr.log").open("wb") as stderr:
            monitor = subprocess.Popen(desc["monitor_command"], cwd=ROOT, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        identity = module.process_identity(monitor.pid)
        monitor_handle = api.bind(identity)
        row["monitor_identity"] = identity
        row["monitor_handle_acquired_utc"] = utc()
        accepted = api.k.SetThreadExecutionState(desc["power_flags"])
        if accepted == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        power = True
        row["power_lease"] = {"monitor_identity": identity, "accepted_utc": utc(), "request_return": int(accepted),
                              "flags": desc["power_flags"], "global_power_policy_changed": False}
        save(OUTPUT / "started.json", row)
        while True:
            try:
                if wsl_handle is None and (MONITOR_OUT / "monitor_state.json").exists():
                    raw = (MONITOR_OUT / "monitor_state.json").read_bytes()
                    state = json.loads(raw.decode("utf-8-sig"))
                    if state["monitor_process"]["pid"] != identity["pid"] or state["monitor_process"]["start_token"] != identity["start_token"]:
                        raise ValueError("Monitor state belongs to a different creation identity")
                    if state["task"]["id"] != TASK or state["task"]["monitor_kind"] != "owned_child" or state["sources"] != desc["sources"]:
                        raise ValueError("Monitor task/source binding differs from this invocation")
                    wsl_handle = api.bind(state["task"]["process"])
                    row["wsl_identity"] = state["task"]["process"]
                    row["wsl_handle_acquired_utc"] = utc()
                    (OUTPUT / "first_monitor_state.json").write_bytes(raw)
                if "first_native_owner_identity" not in row and (OWNER_UNC / "state.json").exists():
                    raw = (OWNER_UNC / "state.json").read_bytes()
                    native_start = json.loads(raw.decode("utf8"))
                    if (native_start["owner_source"]["sha256"] != PINS["collector"]
                            or native_start["owner_source"]["path"] != mounted(COLLECTOR)
                            or native_start["plan_file_sha256"] != PINS["plan"]
                            or native_start["entry_sha256"] != PINS["entry"]
                            or native_start["plan"] != CANONICAL_NATIVE_PLAN or native_start["status"] != "RUNNING"):
                        raise ValueError("Early native owner source/plan/start binding differs")
                    row["first_native_owner_identity"] = native_start["owner_identity"]
                    row["first_native_owner_source"] = native_start["owner_source"]
                    row["first_native_started_utc"] = native_start["started_utc"]
                    row["first_native_state_observed_utc"] = utc()
                    (OUTPUT / "first_native_state.json").write_bytes(raw)
                if "first_registered_admission_sha256" not in row and ADMISSION_UNC.exists():
                    raw = ADMISSION_UNC.read_bytes()
                    admission = json.loads(raw.decode("utf8"))
                    check_admission(admission)
                    row["first_registered_admission_sha256"] = hashlib.sha256(raw).hexdigest()
                    row["first_registered_admission_owner_identity"] = admission["owner_identity"]
                    row["first_registered_admission_observed_utc"] = utc()
                    (OUTPUT / "first_registered_admission.json").write_bytes(raw)
                wsl_code = api.exit(wsl_handle) if wsl_handle is not None else None
                if wsl_code is not None:
                    row.setdefault("wsl_first_exit_observed_utc", utc())
                monitor_code = api.exit(monitor_handle)
                if monitor_code is not None:
                    row.setdefault("monitor_first_exit_observed_utc", utc())
                row.update(status="RUNNING", heartbeat_utc=utc(), monitor_exit_code=monitor_code, wsl_exit_code=wsl_code)
                save(OUTPUT / "state.json", row)
                if monitor_code is not None and (wsl_handle is None or wsl_code is not None):
                    break
                time.sleep(.1)
            except KeyboardInterrupt:
                row["errors"].append({"utc": utc(), "error": "KeyboardInterrupt; owned commands remain supervised, no detach/retry"})
        row["monitor_popen_wait_exit_code"] = monitor.wait()
        row["windows_handles_closed_observation_utc"] = utc()
        if wsl_handle is None:
            raise ValueError("No actual WSL creation-bound handle was acquired; closure is not established")
        if row["monitor_popen_wait_exit_code"] != monitor_code:
            raise ValueError("Monitor kernel handle exit differs from Popen.wait")
        final = load(MONITOR_OUT / "monitor_state.json")
        if (final["monitor_process"] != identity or final["task"]["process"] != row["wsl_identity"]
                or final["task"]["id"] != TASK or final["sources"] != desc["sources"]
                or final["task"]["returncode"] != wsl_code or not final["task"]["finished_utc"]):
            raise ValueError("Final monitor identity/source/exit receipt differs")
        terminal_path = OWNER_UNC / "terminal.json"
        raw = terminal_path.read_bytes()
        native = json.loads(raw.decode("utf8"))
        if (native["owner_source"]["sha256"] != PINS["collector"] or native["plan_file_sha256"] != PINS["plan"]
                or native["entry_sha256"] != PINS["entry"] or native["plan"] != CANONICAL_NATIVE_PLAN
                or native["owner_identity"] != row.get("first_native_owner_identity")
                or native["owner_source"] != row.get("first_native_owner_source")
                or native["started_utc"] != row.get("first_native_started_utc")
                or native["returncode"] != wsl_code or native["current_child"]["returncode"] is None
                or native.get("child_may_still_be_active") or native["status"] not in {"COLLECTION_FINISHED", "STOPPED_FAULT"}):
            raise ValueError("Native terminal source/plan/child/exit closure differs")
        (OUTPUT / "native_terminal.json").write_bytes(raw)
        gate_terminal_path = OWNER_UNC / "registered_entry_terminal.json"
        gate_raw = gate_terminal_path.read_bytes()
        gate_terminal = json.loads(gate_raw.decode("utf8"))
        check_gate_terminal(gate_terminal, row, native, raw)
        (OUTPUT / "registered_entry_terminal.json").write_bytes(gate_raw)
        row["registered_entry_terminal_sha256"] = hashlib.sha256(gate_raw).hexdigest()
        (OUTPUT / "final_monitor_state.json").write_bytes((MONITOR_OUT / "monitor_state.json").read_bytes())
        row["native_owner_identity"] = native["owner_identity"]
        row["native_owner_terminal_sha256"] = sha(terminal_path)
        row["native_collection_status"] = native["status"]
        row["collected_slots"] = len(native["collected"])
        row["closure_verified"] = True
        row["status"] = "COLLECTION_ENDED" if monitor_code == wsl_code == 0 else "STOPPED_FAULT"
        description()  # Recheck all pinned sources after actual command closure.
    except Exception as error:
        row["status"] = "STOPPED_FAULT"
        row["errors"].append({"utc": utc(), "error": f"{type(error).__name__}: {error}"})
    finally:
        # Even a publication/validation fault must not abandon either owned
        # Windows command. Preserve the power request until real command exit.
        for name, handle in (("wsl", wsl_handle), ("monitor", monitor_handle)):
            if handle is not None:
                while True:
                    exit_code = api.exit(handle)
                    if exit_code is not None:
                        row.setdefault(name + "_first_exit_observed_utc", utc())
                        break
                    time.sleep(.2)
                row[name + "_final_handle_exit_code"] = exit_code
                row[name + "_final_exit_observed_utc"] = utc()
        if monitor is not None:
            row["monitor_final_popen_wait_exit_code"] = monitor.wait()
        if power:
            row["power_lease"]["release_return"] = int(api.k.SetThreadExecutionState(0x80000000))
            row["power_lease"]["released_utc"] = utc()
        for handle in (wsl_handle, monitor_handle):
            if handle is not None:
                api.k.CloseHandle(handle)
        row["finished_utc"] = utc()
        row["artifacts"] = {p.name: sha(p) for p in sorted(OUTPUT.iterdir()) if p.is_file()}
        save(OUTPUT / "terminal.json", row)
    print(json.dumps({"status": row["status"], "terminal": str(OUTPUT / "terminal.json"),
                      "terminal_sha256": sha(OUTPUT / "terminal.json")}))
    return 0 if row.get("closure_verified") and row["status"] == "COLLECTION_ENDED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
