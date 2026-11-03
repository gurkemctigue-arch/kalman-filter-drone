"""Compose the reviewed source stage with complete probe02 execution evidence.

Production stays disabled until the actual full owner chain and storage budget
exist and their raw bindings are registered. This never launches WSL or builds.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "tools/staging/final55_offline_overlay_20261103/stage.py"
BASE_SHA = "25a88f5ba369c918c5d891828b5e2434c61f75f33eb5485749f1ec0fda632268"
CHAIN = ROOT / "tools/staging/final55_offline_overlay_profile02_20261103/validate_owner_chain.py"
CHAIN_SHA = "9cbbfbbfccccac9096a5cc122a21d8578e0fcbb3148357602dcdb834b143d97a"
PRODUCTION_ENABLED = False
REGISTERED_INPUTS = {}
OVERRIDES = {
    "extension_sha": "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54",
    "extension_digest": "837e533b75800c4c3fdd19f4937d55d92e50fe833da5c6b8801494dfbc77d15b",
    "contract_sha": "11bcebbe460eecc24c9c5bc920f977b421013c9df862f60e667e5ee07f3625e3",
    "contract_digest": "7c689e742d0a5451ac995b1a1bd2efa14ad6f74c14e2056359877f18cafd868e",
}
ASSUMPTIONS_SHA = "bc0ef3a6549bb7421b1b6de64c17951c4d71af32114c94a8e4234ad42360b049"
BUDGET_TOOL_SHA = "e02424cc5df2e103c8994afca8fdeee7fba02c777e0bb50fd7e54576d3e6b4aa"
BUDGET_GUARD_SHA = "e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e"
CORE_GROUPS = ("stage1_velocity", "stage1_position", "stage2_crossing", "stage3_midpoint", "stage3_active", "stage3_multi_active")
EXTENSION_GROUPS = ("depth_noise", "depth_holes", "dropout", "latency", "combined", "speed_changes_velocity", "speed_changes_position", "far_distance")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixed_module(path, expected):
    raw = path.read_bytes()
    require(sha(raw) == expected, "Reviewed source changed: " + str(path))
    module = types.ModuleType("fixed_" + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def validate_admission(chain_result, budget, *, core_binding, extension_binding):
    """Check the registered producer output; no independent fresh-capacity claim."""
    require(chain_result.get("status") == "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION"
            and len(chain_result.get("closed_ids", [])) == 16
            and len(set(chain_result["closed_ids"])) == 16
            and chain_result.get("pending_ids") == []
            and [row["id"] for row in chain_result.get("closed", [])] == chain_result["closed_ids"],
            "A full original sixteen-slot owner chain is required")
    require({key: chain_result["plan"][key] for key in ("path", "sha256")} == extension_binding,
            "Owner chain belongs to another extension plan")
    require(budget.get("schema_version") == 1
            and budget.get("kind") == "RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION"
            and budget.get("admission_performed") is False,
            "Actual development-based budget assembly required")
    storage = budget["storage"]
    canonical = json.dumps(storage, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(sha(canonical) == budget["storage_sha256"], "Budget storage digest differs")
    provenance = budget["provenance"]
    require(provenance.get("development_plans") == {"core": core_binding, "extension": extension_binding}
            and provenance.get("assumptions", {}).get("sha256") == ASSUMPTIONS_SHA
            and provenance.get("tool", {}).get("sha256") == BUDGET_TOOL_SHA
            and provenance.get("guard_tool", {}).get("sha256") == BUDGET_GUARD_SHA,
            "Budget plans or original assumptions differ")
    cells = storage["cells"]
    keys = [(row["matrix"], row["target_class"], row["condition"]) for row in cells]
    expected = {(matrix, target, condition)
                for matrix, groups in (("core", CORE_GROUPS), ("extension", EXTENSION_GROUPS))
                for target in ("person", "car") for condition in groups}
    require(len(keys) == len(set(keys)) == 28 and set(keys) == expected,
            "Exact core6/extension8 across both classes required")
    preview = budget["capacity_preview"]
    volumes = preview.get("volumes")
    require(preview.get("scheduled_slots") == 280 and preview.get("fits_declared_logical_budget") is True
            and isinstance(volumes, dict) and bool(volumes)
            and all(row.get("fits_declared_physical_budget") is True for row in volumes.values()),
            "Declared logical or physical capacity does not fit all 280 slots")
    return {"original_slot_count": 16, "measured_cell_count": 28, "scheduled_slots": 280,
            "preserved_engineering_statuses": [{"id": row["id"], "original_status": row["original_status"]}
                                              for row in chain_result["closed"]]}


def execute_with_outcome(base, prepared, inputs, admission_path, admission):
    """Keep the base outcome and a separate final wrapper outcome on failure."""
    outcome_path = admission_path.with_name(admission_path.stem + ".driver_outcome.json")
    require(not admission_path.exists() and not outcome_path.exists(), "Fresh wrapper evidence paths required")
    base.write_new(admission_path, admission)
    report = {"status": "STARTED_PROFILE02_STAGING", "admission": base.binding(admission_path)}
    try:
        outcome = base.execute(prepared)
        inputs.unchanged()
        report["status"] = "PASS_PROFILE02_STAGING_ONLY_NOT_COLD_OR_ADMISSION"
    except BaseException as error:
        report.update(status="FAIL_PROFILE02_STAGING_RETAINED", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        base_outcome = prepared["paths"]["receipt"] / "outcome.json"
        report["base_outcome"] = base.binding(base_outcome) if base_outcome.is_file() else None
        base.write_new(outcome_path, report)
    return {**outcome, "profile02_admission": base.binding(admission_path),
            "profile02_driver_outcome": base.binding(outcome_path)}


def production_paths():
    source = Path("/root/uav_tracking_fullplan_v4_humble54")
    results = source / "results"
    return {
        "source": source, "overlay": ROOT,
        "stage": Path("/root/uav_tracking_final55_stage_probe02_05"),
        "final": Path("/root/uav_tracking_fullplan_v4_final55"),
        "receipt": Path("/mnt/d/WSL/UAVHumble22-validation/final55_stage_probe02_05"),
        "core": results / "reliability_v4_humble54_core12_probe01_matrix/plan.json",
        "extension": results / "reliability_v4_humble54_extension16_probe02_matrix/plan.json",
        "full": results / "freeze_validation/source_integrity/source_before.json",
        "module": ROOT / "tools/offline_evaluation/sensor_input_interruption_v1/evidence.py",
        "contract": ROOT / "tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical_probe02_20261103.json",
    }


def run_registered(*, execute_requested=False):
    require(PRODUCTION_ENABLED and set(REGISTERED_INPUTS) == {"full_chain_profile", "budget"},
            "Actual full chain and budget have not been registered; production staging disabled")
    base = fixed_module(BASE, BASE_SHA)
    chain = fixed_module(CHAIN, CHAIN_SHA)
    profile = deepcopy(base.PROFILE)
    profile.update(OVERRIDES)
    require({key for key in profile if profile[key] != base.PROFILE[key]} == set(OVERRIDES),
            "Unexpected base profile override")
    paths = production_paths()
    with base.linux_idle_guard():
        inputs = chain.v.Inputs(chain.v.local_small_read)
        registered_profile = inputs.json(REGISTERED_INPUTS["full_chain_profile"])
        budget = inputs.json(REGISTERED_INPUTS["budget"])
        original = chain.validate_chain(registered_profile)
        original_plan_binding = {key: original["plan"][key] for key in ("path", "sha256")}
        inputs.bind_plan_results_alias(inputs.json(original_plan_binding))
        for binding in original["input_bindings"]:
            inputs.bound(binding)
        for path, pin in budget["provenance"]["small_inputs_sha256"].items():
            inputs.bound({"path": path, "sha256": pin})
        for role in ("assumptions", "physical_inventory", "tool", "guard_tool"):
            inputs.bound(budget["provenance"][role])
        for cell in budget["storage"]["cells"]:
            for role in ("development_size_evidence", "archive_evidence"):
                inputs.bound(cell[role])
        for path, pin in ((BASE, BASE_SHA), (CHAIN, CHAIN_SHA)):
            inputs.bound({"path": str(path), "sha256": pin})
        chain.v.timestamp(budget["created_utc"], datetime.now(timezone.utc))
        core = base.binding(paths["core"].resolve(strict=True))
        extension = base.binding(paths["extension"].resolve(strict=True))
        # The owner profile preserves its Windows reference string. Compare
        # the actual path here without altering any original serialized file.
        require(chain.v.local_path(original["plan"]["path"]).resolve(strict=True) == paths["extension"].resolve(strict=True),
                "Original chain plan path resolves elsewhere")
        budget_chain = {**original, "plan": {**original["plan"], "path": extension["path"]}}
        admission = validate_admission(budget_chain, budget, core_binding=core, extension_binding=extension)
        prepared = base.prepare(paths, profile)
        inputs.unchanged()
        if not execute_requested:
            return {"status": "PREFLIGHT_ONLY_NO_STAGING", "admission": admission, **base.summary(prepared)}
        admission_path = paths["receipt"].with_name(paths["receipt"].name + ".admission.json")
        admission_record = {
            "status": "ACTUAL_FULL_CHAIN_AND_BUDGET_BEFORE_STAGING_NOT_FORMAL_ADMISSION",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "driver": base.binding(Path(__file__).resolve()),
            "base_driver": {"path": str(BASE), "sha256": BASE_SHA},
            "chain_validator": {"path": str(CHAIN), "sha256": CHAIN_SHA},
            "registered_inputs": REGISTERED_INPUTS, "checks": admission,
        }
        return execute_with_outcome(base, prepared, inputs, admission_path, admission_record)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not PRODUCTION_ENABLED:
        print(json.dumps({"status": "DISABLED_WAITING_ACTUAL_FULL_CHAIN_AND_BUDGET",
                          "outputs_created": False, "native_command_started": False}))
        return 2 if args.execute else 0
    print(json.dumps(run_registered(execute_requested=args.execute), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
