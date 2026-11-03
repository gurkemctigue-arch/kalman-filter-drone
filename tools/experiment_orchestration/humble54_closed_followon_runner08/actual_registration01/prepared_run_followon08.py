"""Prepare one serial actual28/export/R0/budget run after durable07 closure.

Default is a description. Execution remains disabled until root arms this
reviewed source. This program never invokes WSL, stages final55, builds, flies,
retries, substitutes recordings, or changes original frozen54 source files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import uuid

ROOT = Path(__file__).resolve().parents[3]
EXECUTION_ENABLED = False
COMMIT = "eedd8d9abcd6890b0bd5d0155f76ac08253426b9"
BASE = ROOT / "tools/staging/final55_offline_overlay_20261103/stage.py"
BASE_SHA = "25a88f5ba369c918c5d891828b5e2434c61f75f33eb5485749f1ec0fda632268"
CHAIN = ROOT / "tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_chain.py"
CHAIN_SHA = "b5aae1e007b009848555bbe3a9d9dfc4e6974f8afe4452c8b94e0aa31c547705"
DURABLE = ROOT / "tools/experiment_orchestration/humble54_durable_followon07/wait_owner06_closure.py"
DURABLE_SHA = "ed38a4469169f96364ee9bc79c52c892a3106954ee77c20efa35480eea5861a2"
TOOL_PINS = {
    "tools/measure_reliability_v4_storage.py": "bea4c4ba80fe99991c5f13f91c2b00f375c94954af53ffbfa19e47d19f69bb6c",
    "tools/reliability_v4_storage_snapshot_audit.py": "b6bb0f5a402ba1093d1c5d5061c5b2ac0d99b9153e7af73257ae5fdc873b2323",
    "tools/reliability_v4_storage_budget.py": "e02424cc5df2e103c8994afca8fdeee7fba02c777e0bb50fd7e54576d3e6b4aa",
    "tools/reliability_v4_guard.py": "e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e",
    "tools/reliability_v4_snapshot_audit.py": "9339fe72a67b36f987b81a20833953a50ca59302b4157a1230424e8145497ba6",
}
FROZEN_PINS = {
    "scripts/run_reliability_v4.py": "069c7c519d5b0305c087f8ad2597a2c709b367cc6c62624bbb686c9a0d158e11",
    "scripts/export_estimator_replay_v4.py": "08edc1f57a5f1d8de4e93d3a00f8aefdc6b7fb72aab52f815c756d017d1a72ac",
    "scripts/calibrate_estimator_replay_v4.py": "0a6f3982e395024d7abf3da43e2e685dc0d88157686496dd2cd3e0296f462fe9",
    "scripts/humble22_env.sh": "f4e5d0db8f4a4d46debafdfe52ffdb69aa6970ad3d79e77bd23b81afa795cf1a",
    "scripts/run_research_session.sh": "31cab510fc713a7e9e5dd3b349e92acce97d8fe958480abec924ad3a88a39610",
    "scripts/ros_python.sh": "17a7029b6622946a6eaac25534732be4ff521b8cdf099f1e9214ae4906670f41",
}
CORE_SHA = "ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b"
EXTENSION_SHA = "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54"
REGISTRY_SHA = "ee72b0151a924f7aad0b27459ad2784f7ad1d3d24af6a156d97fec80044332cf"
NATIVE_SHA = "155275816b1acb09c499b88075e83ffa9bb23195c844d1dbe595efe95a0d50bf"
ASSUMPTIONS_SHA = "bc0ef3a6549bb7421b1b6de64c17951c4d71af32114c94a8e4234ad42360b049"
IDLE_SHA = "87c0d015a92eafc3211bd9d2fdb5cf9231332a761d5b656c78419cb002ca1e2b"
CORE_GROUPS = ("stage1_velocity", "stage1_position", "stage2_crossing", "stage3_midpoint", "stage3_active", "stage3_multi_active")
EXTENSION_GROUPS = ("depth_noise", "depth_holes", "dropout", "latency", "combined", "speed_changes_velocity", "speed_changes_position", "far_distance")


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def linux_identity(pid):
    require(type(pid) is int and pid > 0, "Positive native process PID required")
    fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(), "start_ticks": int(fields[19])}


def paths():
    frozen = Path("/root/uav_tracking_fullplan_v4_humble54")
    results = frozen / "results"
    base = Path("/mnt/d/WSL/UAVHumble22-validation")
    receipt = base / "humble54_probe02_closed_followon08"
    return {"frozen": frozen, "receipt": receipt,
            "tools": Path("/root/uav_tracking_storage_measure54_probe02_tools08"),
            "core": results / "reliability_v4_humble54_core12_probe01_matrix/plan.json",
            "extension": results / "reliability_v4_humble54_extension16_probe02_matrix/plan.json",
            "registry": results / "reliability_v4_humble54_safety03_audit/registry.json",
            "native": base / "safety54_schema_recovery03/native_recovery03.json",
            "idle": base / "check_humble54_native_idle02.sh",
            "sizes": results / "full28_storage_measurement_probe02_followon08",
            "inventory": receipt / "physical_inventory08.json",
            "calibration": results / "reliability_v4_humble54_development_calibration_probe02_08",
            "budget": results / "full280_storage_budget_probe02_followon08/budget.json",
            "assumptions": ROOT / "planning/reliability-v4-humble54-storage-assumptions01.json",
            "audit_guard": Path("/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py"),
            "durable_output": ROOT / "results/diagnostics/humble54_probe02_durable_followon07"}


def fixed_module(path, pin):
    raw = path.read_bytes()
    require(len(raw) <= 2 * 1024 * 1024 and sha(raw) == pin, "Reviewed source differs: " + str(path))
    module = types.ModuleType("fixed_runner08_" + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def same_actual(chain, left, right):
    return chain.v.local_path(str(left)).resolve(strict=True) == chain.v.local_path(str(right)).resolve(strict=True)


def validate_closure(chain, inputs, profile_binding, closure_binding, p):
    require(same_actual(chain, profile_binding["path"], p["durable_output"] / "full_owner_chain_profile.json")
            and same_actual(chain, closure_binding["path"], p["durable_output"] / "terminal.json"),
            "The actual durable07 originals are required")
    profile, closure = inputs.json(profile_binding), inputs.json(closure_binding)
    require(closure.get("status") == "CLOSURE_AUDIT_COMPLETED" and closure.get("scope") == "DURABLE_WINDOWS_HELD_HANDLE_CLOSURE_ONLY"
            and closure.get("errors") == [] and type(closure.get("returncode")) is int and closure["returncode"] == 0
            and set(closure.get("exit_codes", {})) == {"outer", "monitor", "wsl"}
            and all(type(code) is int and code == 0 for code in closure["exit_codes"].values()),
            "Durable07 did not observe complete actual zero exits")
    require(closure.get("source", {}).get("sha256") == DURABLE_SHA and same_actual(chain, closure["source"]["path"], DURABLE),
            "The actual durable07 observer source differs")
    inputs.bound(closure["source"])
    for name in ("outer", "monitor", "wsl"):
        held = closure["handles"][name]
        require(type(held.get("exit_code")) is int and held["exit_code"] == 0 and held.get("closed_utc"), "Durable handle release is incomplete")
        now = datetime.now(timezone.utc)
        require(chain.v.timestamp(held["acquired_utc"], now) <= chain.v.timestamp(held["first_exit_observed_utc"], now)
                <= chain.v.timestamp(held["closed_utc"], now) <= chain.v.timestamp(closure["finished_utc"], now), "Durable handle chronology differs")
    saved = closure["future_closure"]
    require(saved.get("status") == "FULL_OWNER_CHAIN_CLOSED_NOT_ENGINEERING_ADMISSION"
            and saved.get("pending_ids") == [] and saved["full_profile"]["sha256"] == profile_binding["sha256"]
            and same_actual(chain, saved["full_profile"]["path"], profile_binding["path"])
            and same_actual(chain, saved["audit"]["path"], p["durable_output"] / "owner_chain_audit.json"),
            "Durable07 closure does not bind this actual full profile")
    inputs.bound(saved["full_profile"])
    saved_audit = inputs.json(saved["audit"])
    audit = chain.validate_chain(profile)
    require(audit["status"] == "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION" and len(audit["closed_ids"]) == 16
            and len(set(audit["closed_ids"])) == 16 and audit["pending_ids"] == [] and audit == saved_audit,
            "The full original sixteen-slot chain no longer matches durable07")
    original_plan = {key: audit["plan"][key] for key in ("path", "sha256")}
    inputs.bind_plan_results_alias(inputs.json(original_plan))
    for binding in audit["input_bindings"]:
        inputs.bound(binding)
    return audit


def fresh_outputs(p):
    outputs = [p[name] for name in ("receipt", "tools", "sizes", "calibration")] + [p["budget"].parent]
    for path in outputs:
        require(not path.exists() and not path.is_symlink(), "Existing or reserved followon output conflicts; no resume: " + str(path))
        require(path.parent.is_dir(), "Existing output parent required: " + str(path))
    actual = [path.resolve() for path in outputs]
    require(len(set(actual)) == len(actual) and all(not a.is_relative_to(b) and not b.is_relative_to(a)
            for index, a in enumerate(actual) for b in actual[index + 1:]), "Followon outputs overlap")


def write_new(path, value):
    with Path(path).open("x", encoding="utf8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def publish_state(path, value):
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        write_new(temporary, value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def child_step(p, state, label, argv, inputs, *, environment):
    """Own one child until actual exit, including after a parent interrupt."""
    inputs.unchanged()
    row = {"id": label, "command": [str(value) for value in argv], "started_utc": utc(), "returncode": None}
    state["steps"].append(row)
    stdout = p["receipt"] / (label + ".stdout.log")
    stderr = p["receipt"] / (label + ".stderr.log")
    row.update(stdout=str(stdout), stderr=str(stderr))
    publish_state(p["receipt"] / "state.json", state)
    failure, child = None, None
    try:
        with stdout.open("xb") as out, stderr.open("xb") as err:
            try:
                child = subprocess.Popen(row["command"], stdout=out, stderr=err, env=environment, start_new_session=True)
                row["pid"] = child.pid
                row["identity"] = linux_identity(child.pid)
                publish_state(p["receipt"] / "state.json", state)
                row["returncode"] = child.wait()
            except BaseException as error:
                failure = error
                if isinstance(error, KeyboardInterrupt):
                    state["interruptions"].append({"utc": utc(), "step": label, "action": "WAIT_ORIGINAL_CHILD_NO_SIGNAL_RETRY_OR_DETACH"})
            finally:
                if child is not None:
                    while row["returncode"] is None:
                        try:
                            row["returncode"] = child.wait()
                        except KeyboardInterrupt as error:
                            failure = failure if failure is not None else error
                            state["interruptions"].append({"utc": utc(), "step": label, "action": "WAIT_ORIGINAL_CHILD_NO_SIGNAL_RETRY_OR_DETACH"})
    finally:
        row["finished_utc"] = utc()
        try:
            publish_state(p["receipt"] / "state.json", state)
        except BaseException as error:
            failure = failure if failure is not None else error
    if failure is not None:
        raise failure
    require(type(row["returncode"]) is int and row["returncode"] == 0, "Original step failed; partial output retained: " + label)
    inputs.unchanged()
    return stdout


def ros_command(p, script, *arguments):
    return ["bash", "-c", 'set -eo pipefail; source "$1/scripts/humble22_env.sh"; shift; exec bash "$@"',
            "_", str(p["frozen"]), str(p["frozen"] / "scripts/run_research_session.sh"), str(script), *map(str, arguments)]


def workflow_commands(p):
    common = ["--core-development-plan", p["core"], "--extension-development-plan", p["extension"]]
    return [
        ("measure_actual28", ros_command(p, p["tools"] / "tools/measure_reliability_v4_storage.py", *common,
          "--output", p["sizes"], "--snapshot-audit-registry", p["registry"], "--snapshot-audit-registry-sha256", REGISTRY_SHA,
          "--snapshot-audit-native-receipt", p["native"], "--snapshot-audit-native-receipt-sha256", NATIVE_SHA)),
        ("physical_inventory", ros_command(p, p["audit_guard"], "storage-probe", "--distribution", "UAVHumble22", "--mount", "/mnt/d", "--output", p["inventory"])),
        *[(target + "_velocity_export", ros_command(p, p["frozen"] / "scripts/export_estimator_replay_v4.py",
            p["frozen"] / ("results/reliability_v4_humble54_core12_probe01_" + target + "_stage1_velocity_seed004"),
            "--output", p["calibration"] / (target + "_export"))) for target in ("person", "car")],
        ("R0_candidate", ros_command(p, p["frozen"] / "scripts/calibrate_estimator_replay_v4.py", "--plan", p["core"],
          "--person-arrays", p["calibration"] / "person_export/arrays.json", "--car-arrays", p["calibration"] / "car_export/arrays.json",
          "--output", p["calibration"] / "R0_candidate.json")),
        ("full280_budget", ros_command(p, p["tools"] / "tools/reliability_v4_storage_budget.py", *common,
          "--size-evidence-dir", p["sizes"], "--physical-inventory", p["inventory"], "--assumptions", p["assumptions"], "--output", p["budget"]))]


def bound_generated(inputs, path):
    raw = inputs.read_reference(str(path))
    return inputs.json({"path": str(path), "sha256": sha(raw)})


def positive_budget(budget, core_binding, extension_binding):
    require(budget.get("kind") == "RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION" and budget.get("admission_performed") is False,
            "Actual original budget output required")
    storage = budget["storage"]
    require(sha(json.dumps(storage, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()) == budget["storage_sha256"], "Budget storage digest differs")
    expected = {(matrix, target, condition) for matrix, conditions in (("core", CORE_GROUPS), ("extension", EXTENSION_GROUPS))
                for target in ("person", "car") for condition in conditions}
    keys = [(row["matrix"], row["target_class"], row["condition"]) for row in storage["cells"]]
    require(len(keys) == len(set(keys)) == 28 and set(keys) == expected, "Complete exact measured28 budget required")
    provenance = budget["provenance"]
    require(provenance["development_plans"] == {"core": core_binding, "extension": extension_binding}
            and provenance["assumptions"]["sha256"] == ASSUMPTIONS_SHA, "Budget belongs to other original inputs")
    preview = budget["capacity_preview"]
    require(preview.get("scheduled_slots") == 280 and preview.get("fits_declared_logical_budget") is True
            and isinstance(preview.get("volumes"), dict) and bool(preview["volumes"])
            and all(row.get("fits_declared_physical_budget") is True for row in preview["volumes"].values()),
            "Unknown or negative physical/logical full280 budget; stop without staging")


def run(profile_binding, closure_binding):
    require(EXECUTION_ENABLED, "Runner08 is not armed; no native command or output is started")
    require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22", "Run explicitly inside existing native UAVHumble22; no WSL launcher exists")
    base, chain = fixed_module(BASE, BASE_SHA), fixed_module(CHAIN, CHAIN_SHA)
    p = paths()
    with base.linux_idle_guard() as guard:
        inputs = chain.v.Inputs(chain.v.local_small_read)
        audit = validate_closure(chain, inputs, profile_binding, closure_binding, p)
        for path, pin in ((BASE, BASE_SHA), (CHAIN, CHAIN_SHA), (DURABLE, DURABLE_SHA),
                          (p["core"], CORE_SHA), (p["extension"], EXTENSION_SHA), (p["registry"], REGISTRY_SHA),
                          (p["native"], NATIVE_SHA), (p["assumptions"], ASSUMPTIONS_SHA), (p["idle"], IDLE_SHA),
                          (p["audit_guard"], TOOL_PINS["tools/reliability_v4_guard.py"]),
                          (p["frozen"] / "results/humble54_core12_owner01/owner_terminal.json", "966b51475b492b4975d13fddd7b36e54fb1ecfce78580be1ba13bcda063c731c")):
            inputs.bound({"path": str(path), "sha256": pin})
        for name, pin in FROZEN_PINS.items():
            inputs.bound({"path": str(p["frozen"] / name), "sha256": pin})
        self_binding = {"path": str(Path(__file__).resolve()), "sha256": sha(Path(__file__).read_bytes())}
        inputs.bound(self_binding)
        fresh_outputs(p)
        inputs.unchanged()
        p["receipt"].mkdir(exist_ok=False)
        state = {"schema_version": 1, "scope": "NATIVE_SERIAL_FOLLOWON08_ACTUAL28_R0_BUDGET_ONLY", "status": "STARTED_FOLLOWON08", "started_utc": utc(), "source": self_binding,
                 "owner_identity": linux_identity(os.getpid()),
                 "full_chain_profile": profile_binding, "durable07_closure": closure_binding, "closed_ids": audit["closed_ids"],
                 "guard": guard, "commit": COMMIT, "steps": [], "interruptions": [], "errors": [], "automatic_retry": False,
                 "claim_boundary": "Original actual28 measurement, two named development exports, R0 candidate and budget only. No staging/build/formal admission."}
        environment = {**os.environ, "HUMBLE22_PROJECT_ROOT": str(p["frozen"]), "HUMBLE22_ROS_GZ_WS": "/root/uav_humble22/ros_gz_shutdown_A01_ws",
                       "HUMBLE22_PX4_ROOT": "/root/uav_humble22/PX4-Autopilot-v4mag", "TMPDIR": "/tmp", "STAGE1_TRANSIENT_DIR": "/tmp",
                       "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        try:
            write_new(p["receipt"] / "started.json", state)
            idle = child_step(p, state, "native_idle", ["bash", p["idle"]], inputs, environment=environment)
            query = bound_generated(inputs, idle)
            require(query.get("kind") == "ACTUAL_CURRENT_NATIVE_PROCESS_QUERY_ONLY" and query.get("matching_processes") == [], "Actual native idle query did not pass")
            p["tools"].mkdir(exist_ok=False)
            (p["tools"] / "tools").mkdir()
            for index, (relative, pin) in enumerate(TOOL_PINS.items()):
                stdout = child_step(p, state, "tool_" + str(index), ["git", "-C", ROOT, "show", COMMIT + ":" + relative], inputs, environment=environment)
                raw = inputs.read_reference(str(stdout))
                require(sha(raw) == pin, "Fixed commit storage source differs: " + relative)
                with (p["tools"] / relative).open("xb") as handle:
                    handle.write(raw)
                inputs.bound({"path": str(p["tools"] / relative), "sha256": pin})
            for label, argv in workflow_commands(p):
                stdout = child_step(p, state, label, argv, inputs, environment=environment)
                if label == "measure_actual28":
                    measured = bound_generated(inputs, p["sizes"] / "summary.json")
                    require(measured.get("planned_count") == measured.get("measured_count") == 28 and len(measured["receipts"]) == 28
                            and measured.get("payload_content_reads") is False and measured.get("capacity_admission_performed") is False,
                            "Original complete actual28 measurement required")
                    for binding in measured["receipts"]:
                        inputs.bound(binding)
                    for path, item in measured["small_input_bindings"].items():
                        inputs.bound({"path": path, "sha256": item["sha256"]})
                elif label == "physical_inventory":
                    inventory = bound_generated(inputs, p["inventory"])
                    require(inventory.get("kind") == "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY"
                            and inventory.get("evidence_scope") == "METADATA_ONLY_NOT_FORMAL_ADMISSION" and inventory.get("volumes"), "Actual physical inventory required")
                elif label.endswith("_velocity_export"):
                    require(bound_generated(inputs, stdout).get("status") == "PASS", "Original export evidence failed")
                elif label == "R0_candidate":
                    calibration = bound_generated(inputs, p["calibration"] / "R0_candidate.json")
                    require(calibration.get("status") == "CANDIDATE_NOT_REGISTERED" and calibration.get("scope") == "DEVELOPMENT_ONLY"
                            and set(calibration["classes"]) == {"person", "car"}, "Original development R0 candidate required")
                elif label == "full280_budget":
                    budget = bound_generated(inputs, p["budget"])
                    positive_budget(budget, base.binding(p["core"]), base.binding(p["extension"]))
                    for path, pin in budget["provenance"]["small_inputs_sha256"].items():
                        inputs.bound({"path": path, "sha256": pin})
            inputs.unchanged()
            state["status"] = "COMPLETED_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION"
        except BaseException as error:
            state["status"] = "STOPPED_FOLLOWON08_PARTIAL_OUTPUTS_RETAINED"
            state["errors"].append({"utc": utc(), "error": f"{type(error).__name__}: {error}"})
        finally:
            state["finished_utc"] = utc()
            state["returncode"] = 0 if state["status"] == "COMPLETED_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION" else 2
            state["input_bindings"] = sorted(inputs.seen.values(), key=lambda row: chain.v.path_key(row["path"]))
            write_new(p["receipt"] / "terminal.json", state)
        return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--full-chain-profile")
    parser.add_argument("--full-chain-profile-sha256")
    parser.add_argument("--durable07-closure")
    parser.add_argument("--durable07-closure-sha256")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "DESCRIPTION_ONLY_NOT_STARTED", "execution_enabled": EXECUTION_ENABLED,
                          "commit": COMMIT, "sequence": ["actual full16 durable07 closure", "locked native idle", "fixed tools", *[name for name, _ in workflow_commands(paths())]],
                          "outputs": {name: paths()[name].as_posix() for name in ("receipt", "tools", "sizes", "inventory", "calibration", "budget")},
                          "automatic_retry": False, "stage_build_formal": "NOT_AVAILABLE"}))
        return 0
    try:
        require(EXECUTION_ENABLED, "Runner08 is not armed; no native command or output is started")
        require(all((args.full_chain_profile, args.full_chain_profile_sha256, args.durable07_closure, args.durable07_closure_sha256)),
                "Explicit actual full-chain and durable07 closure path/raw SHA bindings required")
        state = run({"path": args.full_chain_profile, "sha256": args.full_chain_profile_sha256},
                    {"path": args.durable07_closure, "sha256": args.durable07_closure_sha256})
        print(json.dumps({"status": state["status"], "returncode": state["returncode"]}))
        return state["returncode"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "REFUSED_OR_STOPPED_NO_RETRY", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
