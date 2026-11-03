"""Register a specific supervisor rollover, then signal only its bound PID.

Never signals the owned experiment command. The registered collector's existing
KeyboardInterrupt handler waits for that command's actual exit before ending.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "results/diagnostics/humble54_probe02_rollover04_to05_intent01"
NATIVE_OWNER = "/root/uav_tracking_collection54_probe02_owner04"
OWNER_UNC = Path(r"\\wsl.localhost\UAVHumble22\root\uav_tracking_collection54_probe02_owner04")
COLLECTOR = ROOT / "tools/experiment_orchestration/humble54_pending_collector04_source/collect_humble54_pending04.py"
PREPARED05 = ROOT / "tools/experiment_orchestration/humble54_pending_collector05_source/collect_humble54_pending05.py"
PLAN = ROOT / "results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/plan.json"
PINS = {"collector04": "bf9168f2b5b6dc31e43c187d894f860a4d77e780ded6a4b453c2545c5b5aee0e",
        "prepared05": "f6a01ac6d106ed89914745341b6faba6f1fe6dab92df6a651ae86e90adeb9ce1",
        "plan": "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54"}
SLOT = "person_extension_depth_holes_seed004"


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    path = Path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Small metadata required")
    return json.loads(path.read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save_new(path, value):
    with Path(path).open("xb") as handle:
        handle.write((json.dumps(value, indent=2, allow_nan=False) + "\n").encode())


def check_sources():
    for path, name in ((COLLECTOR, "collector04"), (PREPARED05, "prepared05"), (PLAN, "plan")):
        require(sha(path) == PINS[name], "Registered source changed: " + name)


def check_active(state, expected=None):
    require(state["status"] == "RUNNING" and state["current_slot"] == SLOT
            and state["owner_source"]["sha256"] == PINS["collector04"]
            and state["plan_file_sha256"] == PINS["plan"]
            and state["owner_pid"] == state["owner_identity"]["pid"]
            and len(state["collected"]) == 1
            and state["collected"][0]["slot_id"] == "person_extension_depth_noise_seed004"
            and state["current_child"]["returncode"] is None, "Specific active supervisor/slot differs")
    if expected is not None:
        require(state["owner_identity"] == expected["owner_identity"]
                and state["current_child"] == expected["current_child"]
                and state["collected"] == expected["closed_prefix"], "Owner/child/prefix changed after intent registration")


def prepare():
    require(sys.platform == "win32", "Intent registration requires Windows")
    check_sources()
    require(not OUTPUT.exists(), "Fresh intent directory required")
    native_raw = (OWNER_UNC / "state.json").read_bytes()
    native = json.loads(native_raw)
    check_active(native)
    start_path = ROOT / "results/diagnostics/humble54_probe02_windows_owner04/started.json"
    started_raw = start_path.read_bytes()
    started = json.loads(started_raw)
    require(started["pins"]["collector"]["sha256"] == PINS["collector04"]
            and started["pins"]["plan"]["sha256"] == PINS["plan"], "Actual Windows owner binding differs")
    intent = {"schema_version": 1, "status": "INTENT_REGISTERED_NOT_SIGNALLED", "registered_utc": utc(),
              "scope": "CONTROLLED_COLLECTOR_ROLLOVER_WAIT_CURRENT_ORIGINAL_COMMAND_EXIT",
              "reason": "Correct already established person/car selected-model capture binding in the supervisor; preserve flight sources, this plan and all attempts.",
              "pins": PINS, "signal_tool_sha256": sha(__file__), "native_owner": NATIVE_OWNER,
              "owner_identity": native["owner_identity"], "current_slot": SLOT,
              "current_child": native["current_child"], "closed_prefix": native["collected"],
              "native_command": started["native_command"], "monitor_identity": started["monitor_identity"],
              "signal": "SIGINT", "signal_target": "POSITIVE_COLLECTOR_PID_ONLY",
              "native_state_snapshot_sha256": hashlib.sha256(native_raw).hexdigest(),
              "windows_started_snapshot_sha256": hashlib.sha256(started_raw).hexdigest(),
              "claim_boundary": "Intent only. Current second result, parent/child exit and continuation prefix are not yet known. No child/group signal, retry, re-flight, source or original verdict changes are authorized by this record."}
    OUTPUT.mkdir(parents=True)
    (OUTPUT / "native_state_before_signal.json").write_bytes(native_raw)
    (OUTPUT / "windows_started04.json").write_bytes(started_raw)
    save_new(OUTPUT / "intent.json", intent)
    print(json.dumps({"status": intent["status"], "intent_sha256": sha(OUTPUT / "intent.json"),
                      "owner_identity": native["owner_identity"], "current_child": native["current_child"]["identity"]}))


def process(pid):
    require(type(pid) is int and pid > 0, "Positive process PID required")
    fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "start_ticks": int(fields[19])}, int(fields[1]), fields[0]


def send(expected_intent_sha):
    require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22", "Actual native control requires UAVHumble22")
    check_sources()
    intent_path = OUTPUT / "intent.json"
    require(sha(intent_path) == expected_intent_sha, "Actual intent raw SHA differs")
    intent = load(intent_path)
    require(intent["signal_tool_sha256"] == sha(__file__) and intent["pins"] == PINS
            and intent["status"] == "INTENT_REGISTERED_NOT_SIGNALLED", "Intent tool/source/scope differs")
    require(not (OUTPUT / "signal_receipt.json").exists() and not (OUTPUT / "signal_preflight.json").exists(), "No repeated control request")
    owner = Path(NATIVE_OWNER)
    require(not (owner / "terminal.json").exists(), "Owner already closed")
    state = load(owner / "state.json")
    check_active(state, intent)
    identity, _, owner_state = process(intent["owner_identity"]["pid"])
    child_identity, child_ppid, child_state = process(intent["current_child"]["pid"])
    require(identity == intent["owner_identity"] and child_identity == intent["current_child"]["identity"]
            and child_ppid == identity["pid"] and owner_state not in {"Z", "X"} and child_state not in {"Z", "X"}, "Actual owner/owned-child kernel identities differ")
    argv = (Path("/proc") / str(identity["pid"]) / "cmdline").read_bytes().decode().rstrip("\0").split("\0")
    expected_argv = intent["native_command"][4:]
    require(Path(argv[0]).name in {"python3", "python3.10"} and argv[1:] == expected_argv[1:], "Actual collector argv differs")
    require(state["owner_source"]["path"] == str(COLLECTOR), "Actual source path differs")
    preflight = {"status": "IDENTITY_CHECKED_BEFORE_SINGLE_PID_SIGNAL", "utc": utc(),
                 "intent_sha256": expected_intent_sha, "signal_tool_sha256": sha(__file__),
                 "owner_identity": identity, "child_identity": child_identity, "child_ppid": child_ppid,
                 "actual_owner_argv": argv, "signal_target_pid": identity["pid"], "signal": "SIGINT"}
    save_new(OUTPUT / "signal_preflight.json", preflight)
    os.kill(identity["pid"], signal.SIGINT)
    receipt = {"status": "SINGLE_PID_SIGINT_REQUEST_SENT", "utc": utc(), "intent_sha256": expected_intent_sha,
               "preflight_sha256": sha(OUTPUT / "signal_preflight.json"), "signal_target_pid": identity["pid"],
               "signal": "SIGINT", "os_kill_returned": True,
               "scope": "Request only; wait for original command, collector and held Windows handles to close. No completion or continuation claim."}
    save_new(OUTPUT / "signal_receipt.json", receipt)
    print(json.dumps(receipt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--prepare-intent", action="store_true")
    action.add_argument("--send-signal-after-checks", metavar="ACTUAL_INTENT_SHA256")
    args = parser.parse_args()
    if args.prepare_intent:
        prepare()
    elif args.send_signal_after_checks:
        send(args.send_signal_after_checks)
    else:
        print("PREPARED_NOT_EXECUTED")


if __name__ == "__main__":
    main()
