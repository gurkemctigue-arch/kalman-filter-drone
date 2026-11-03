"""Create one prepared small-evidence profile; no WSL/native/experiment calls."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def binding(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    source = HERE / "collect_humble54_pending07.py"
    spec = importlib.util.spec_from_file_location("prepared_pending07", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    plan_path = ROOT / "results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/plan.json"
    plan = json.loads(plan_path.read_bytes())
    assert binding(plan_path)["sha256"] == module.PLAN_SHA
    snapshot = ROOT / "tools/experiment_orchestration/humble54_probe02_owner06_stop_snapshot01"
    old = ROOT / "tools/experiment_orchestration"
    sources = {
        "plan": plan_path,
        "entry": Path("D:/WSL/UAVHumble22-validation/run_humble54_pending_probe02_one03.sh"),
        "old_collector06": old / "humble54_pending_collector06_source/collect_humble54_pending06.py",
        "old_gate06": old / "humble54_pending_collector06_registered/run_registered06.py",
        "old_launcher06": old / "humble54_probe02_windows_owner06/start_owner06.py",
        "old_profile06": old / "humble54_pending_collector06_registered/registered_profile06.json",
        "old_chain03": ROOT / "tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_chain.py",
        "old_slot_library03": module.SLOT_LIBRARY,
        "monitor": ROOT / "scripts/monitor_project_progress.py",
        "durable07": old / "humble54_durable_followon07/wait_owner06_closure.py",
        "durable09": old / "humble54_durable_followon09/trigger_followon08.py",
        "conditional_evaluator": ROOT / "tools/diagnostics/humble54_probe02_car_dropout_null_review01/evaluate_stage1_flight.frozen.py",
    }
    closure = {
        "events06": "native_owner06/events.jsonl",
        "native_terminal06": "native_owner06/terminal.json",
        "gate_terminal06": "native_owner06/registered_entry_terminal.json",
        "admission06": "native_owner06/admission.original.json",
        "started06": "humble54_probe02_windows_owner06/started.json",
        "first_native06": "humble54_probe02_windows_owner06/first_native_state.json",
        "first_monitor06": "humble54_probe02_windows_owner06/first_monitor_state.json",
        "final_monitor06": "humble54_probe02_windows_owner06/final_monitor_state.json",
        "outer_terminal06": "humble54_probe02_windows_owner06/terminal.json",
        "started07": "humble54_probe02_durable_followon07/started.json",
        "terminal07": "humble54_probe02_durable_followon07/terminal.json",
        "started09": "humble54_probe02_durable_followon09/started.json",
        "terminal09": "humble54_probe02_durable_followon09/terminal.json",
    }
    prefix = []
    for trial in plan["trials"][:11]:
        terminal = plan_path.parent / "slots" / (trial["id"] + ".json")
        record = json.loads(terminal.read_bytes())
        trial_directory = plan_path.parent.parent / trial["name"]
        artifacts = {name: binding(trial_directory / name) for name in module.SMALL_ARTIFACTS}
        assert all(record["artifact_hashes"][name] == row["sha256"] for name, row in artifacts.items())
        prefix.append({"id": trial["id"], "terminal": binding(terminal),
                       "marker": binding(terminal.with_name(trial["id"] + ".started.json")),
                       "record_sha256": record["record_sha256"], "original_status": record["status"],
                       "started_utc": record["started_utc"], "finished_utc": record["finished_utc"],
                       "artifacts": artifacts})
    native = json.loads((snapshot / closure["native_terminal06"]).read_bytes())
    refused = json.loads((snapshot / closure["terminal09"]).read_bytes())
    profile = {"schema_version": 1, "scope": "DEVELOPMENT_REMAINING_FIVE_AFTER_TRUE_STOPPED06",
               "status": "PREPARED_NOT_REGISTERED", "production_enabled": False, "formal_admission": False,
               "automatic_retry": False, "conditional_identity_rule": module.CONDITIONAL_IDENTITY,
               "plan_digest": plan["plan_sha256"], "runner_sha256": module.RUNNER_SHA,
               "after_slot": module.EXPECTED_AFTER_SLOT, "closed_prefix": prefix,
               "pending_ids": [row["id"] for row in plan["trials"][11:]],
               "sources": {name: binding(path) for name, path in sources.items()},
               "snapshot_manifest": binding(snapshot / "manifest.json"),
               "closure_files": {name: binding(snapshot / path) for name, path in closure.items()},
               "original_stop_error": native["error"], "original_refused09_errors": refused["errors"],
               "native_output": "/root/uav_tracking_collection54_probe02_owner07",
               "windows_monitor_output": str(ROOT / "results/monitor_humble54_probe02_owner07"),
               "claim_boundary": module.CLAIM}
    assert profile["sources"]["entry"]["sha256"] == module.ENTRY_SHA
    assert prefix[-1]["terminal"]["sha256"] == "f80a774d1af43cbb6e8525662bb13f3c2853c9c19d68ac57ccd82435b9015f17"
    output = HERE / "prepared_profile07.json"
    with output.open("x", encoding="utf8", newline="\n") as handle:
        json.dump(profile, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": "PREPARED_ONLY", "profile": binding(output), "closed": len(prefix), "pending": len(profile["pending_ids"])}))


if __name__ == "__main__":
    main()
