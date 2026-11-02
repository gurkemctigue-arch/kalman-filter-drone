"""Future native contract audit, not safety or formal admission.

This file must not be run alongside the experiment owner. It uses the actual
fixed external tools without patching them. The helper retains all original
hashing, including model hashing. Original snapshots remain untouched.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path, PurePosixPath
import sys
import traceback

RUNTIME = Path("/root/uav_tracking_fullplan_v4_humble54")
AUDIT = Path("/root/uav_tracking_snapshot_audit54_tools01")
EXTERNAL = Path("/mnt/d/WSL/UAVHumble22-validation/snapshot_audit_native_integration01")
ADAPTER_ROOT = Path("/mnt/d/WSL/UAVHumble22-validation/formal48_dds_adapter01")
CONTRACT = RUNTIME / "results/snapshot_audit54_contract01.json"
PLAN = RUNTIME / "results/reliability_v4_humble54_core12_probe01_matrix/plan.json"
PLAN_SHA = "ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b"
PLAN_DIGEST = "3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31"
BUNDLE_SHA = "fcee7f195d9822f45edc35d72cbcf0296559426e5dfadd7b2a9b8452fc9bcff3"
ADAPTER_TOOLS_SHA = "dbc9358db20d02e62c2963b868605b4e77f4d16a188f52c5e28e11e20f9f2d5a"
SNAPSHOT_SHA = "0094a5013801e67fb6ae692cef785b190272708d71bfb0cd4a3349a0eb09ee46"
SOURCE_COMMIT = "e346adfeaec91ccee60469ddc83322e112547d0b"
LIMIT = 4 * 1024**2
TOOLS = {
    "tools/reliability_v4_guard.py": (86011, "e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e"),
    "tools/run_reliability_v4_safety.py": (42661, "6d6d1b56d14866355c7d423d3eaaed420860f20190d59acdfa20b853b9f3073b"),
    "tools/reliability_v4_snapshot_audit.py": (17347, "9339fe72a67b36f987b81a20833953a50ca59302b4157a1230424e8145497ba6"),
    "tools/reliability_v4_register.py": (28714, "fe2b37738ba07016dc1551abe273e5309e702b14df6e3d707b2788d3f3ef992c"),
    "tools/__init__.py": (81, "71439d58f08b95cbc9f7998d54555ac376427bddec6cc04d959cd5427fa1b575"),
}
ADAPTER_FILES = {
    "formal48_guard_adapter01.py": (26060, "3973a0590981abf578cbd174371d13c82207c717669298b6d7769c14a242444e"),
    "formal48_guard_adapter01.sh": (2531, "b1343b56e6effe488e3554b58fbae924aba26cfdc959e113d862ad9b14f9535b"),
    "test_formal48_guard_adapter01.py": (29003, "f3ad7e63ffea568db720e91b6fb449e9ef5e9d72d5f095333178c3f8f3430042"),
}
FREEZE_PINS = {
    "source_integrity/source_frozen_integrity.json": (1762, "2d845e262201c6264b9f466b4f77eef4e30c9ec19e17a178e0a65c2db0b940f8"),
    "import_isolation.json": (1265, "a8f43e840275763b83f8f8794fd5882d2d2ec02cec397a2bf5e4ed6d570c8576"),
    "source_integrity/source_before.json": (339580, "cdb4111738f2f51c9911e3e7cebaf9f69aafd92d5cef39d8839a1e5dbb27c82f"),
    "source_integrity/source_after.json": (339282, "56523188d5613b87a4dcac6daef124ceb039736b40095a3c1526e2b11581c6a5"),
    "source_integrity/frozen_actual.json": (339262, "7c81219e94b774723e135fa0a696cab603811b298e24900de158f199a414a102"),
}
FIRST3 = ("person_stage1_velocity_seed004", "person_stage1_position_seed004", "person_stage2_crossing_seed004")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def read_small(path):
    path = Path(path)
    before = path.stat()
    require(path.is_file() and not path.is_symlink() and before.st_size <= LIMIT,
            "Missing/linked/oversized named small input: " + str(path))
    raw = path.read_bytes()
    after = path.stat()
    require(len(raw) <= LIMIT and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "Named small input changed while reading: " + str(path))
    return raw


def binding(path, raw=None):
    raw = read_small(path) if raw is None else raw
    return {"path": str(Path(path).resolve(strict=True)), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def parse(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + value)))
    require(isinstance(value, dict), "JSON object required")
    return value


def pinned(path, expected):
    raw = read_small(path)
    actual = binding(path, raw)
    require((actual["bytes"], actual["sha256"]) == expected, "Pinned source size/SHA differs: " + str(path))
    return actual


def verify_bundle():
    path = AUDIT / "bundle_manifest.json"
    raw = read_small(path)
    require(hashlib.sha256(raw).hexdigest() == BUNDLE_SHA, "Original copy manifest changed")
    manifest = parse(raw)
    require(manifest.get("native_root") == str(AUDIT) and manifest.get("frozen_runtime_root") == str(RUNTIME)
            and manifest.get("source_commit") == SOURCE_COMMIT
            and manifest.get("copy_verified") is True
            and manifest.get("native_execution_validated") is False
            and manifest.get("contract_or_safety_registration_created") is False
            and manifest.get("keep_same_guard_absolute_path_through_safety_and_formal_seal") is True,
            "Original copy-only bundle metadata differs")
    files = manifest.get("files")
    require(isinstance(files, list) and len(files) == len(TOOLS), "Bundle file count differs")
    require({item["relative"] for item in files} == set(TOOLS), "Bundle named file set differs")
    for item in files:
        require(item["native_path"] == str(AUDIT / item["relative"])
                and (item["bytes"], item["sha256"]) == TOOLS[item["relative"]], "Bundle file pin differs")
    return {"manifest": binding(path, raw), "files": {name: pinned(AUDIT / name, expected)
            for name, expected in TOOLS.items()}}


def load_actual_tools():
    require(not any(name == "tools" or name.startswith("tools.") for name in sys.modules),
            "Fresh interpreter required; a tools package was already imported")
    sys.path.insert(0, str(AUDIT))
    marker = importlib.import_module("tools")
    require(Path(marker.__file__).resolve(strict=True) == AUDIT / "tools/__init__.py",
            "Actual fixed tools package marker was not loaded")
    modules = {name: importlib.import_module("tools." + name) for name in
               ("reliability_v4_guard", "reliability_v4_snapshot_audit", "run_reliability_v4_safety", "reliability_v4_register")}
    observed = {"tools": binding(marker.__file__)}
    for name, module in modules.items():
        require(Path(module.__file__).resolve(strict=True) == AUDIT / "tools" / (name + ".py"),
                "Actual module escaped the fixed audit tool root: " + name)
        observed[name] = pinned(module.__file__, TOOLS["tools/" + name + ".py"])
    guard = modules["reliability_v4_guard"]
    driver = modules["run_reliability_v4_safety"]
    registrar = modules["reliability_v4_register"]
    require(driver.ROOT == AUDIT and driver.guard is guard
            and Path(registrar.guard.__file__).resolve(strict=True) == Path(guard.__file__),
            "Actual tool imports/root identity differs; no ROOT patch is allowed")
    return modules, observed


def adapter_header_only():
    files = {name: pinned(ADAPTER_ROOT / name, expected) for name, expected in ADAPTER_FILES.items()}
    path = ADAPTER_ROOT / "formal48_guard_adapter01.py"
    name = "snapshot_audit_actual_formal48_header_only"
    require(name not in sys.modules, "Fresh adapter import name required")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    require(Path(module.__file__).resolve(strict=True) == path,
            "Actual adapter import source path differs")
    manifest = module.tool_manifest()
    require(module.canonical(manifest) == ADAPTER_TOOLS_SHA, "Actual adapter/owner reviewed tool manifest differs")
    require(tuple(inspect.signature(module.load_context).parameters) == ("path", "expected_sha", "reviewed_tools_sha")
            and tuple(inspect.signature(module.load_original_guard).parameters) == ("context",),
            "Actual adapter load API differs")
    source = read_small(path).decode("utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    functions = {item.name: item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
    excerpts = {name: ast.get_source_segment(source, functions[name])
                for name in ("load_context", "load_original_guard")}
    # These assertions inspect the pinned actual source. They do not call the
    # formal loader with a synthetic manifest or fabricated context.
    require("tool = manifest.get('tool')" in excerpts["load_context"]
            and "guard_source = file_bytes(tool['path'])" in excerpts["load_context"]
            and "hashlib.sha256(guard_source).hexdigest() == tool['sha256']" in excerpts["load_context"]
            and "exec(compile(context.guard_source, context.tool['path'], 'exec'), module.__dict__)" in excerpts["load_original_guard"]
            and "Path(module.__file__).resolve(strict=True) == Path(context.tool['path'])" in excerpts["load_original_guard"],
            "Pinned manifest.tool path/SHA loading source did not match the reviewed interface")
    return {"result": "ACTUAL_NATIVE_IMPORT_TOOL_MANIFEST_AND_STATIC_LOADER_INTERFACE_CHECKED",
            "files": files, "module_file": module.__file__, "tools_manifest": manifest,
            "tools_canonical_sha256": module.canonical(manifest),
            "load_context_signature": str(inspect.signature(module.load_context)),
            "load_original_guard_signature": str(inspect.signature(module.load_original_guard)),
            "actual_loader_source": excerpts,
            "formal_load_context_called": False, "formal_load_original_guard_called": False,
            "formal_dual_root_integration_validated": False,
            "pending": "Real safety4 and real final formal plans/manifest must exist before the complete original adapter/guard load chain can be checked."}


def execute(report):
    require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22"
            and os.environ.get("ROS_DISTRO") == "humble" and sys.version_info[:2] == (3, 10)
            and sys.flags.dont_write_bytecode and sys.dont_write_bytecode
            and Path(sys.executable) == Path("/root/uav_humble22/venv/bin/python"),
            "Only the explicit idle UAVHumble22/Humble Python 3.10 venv with -B is supported")
    require(Path(__file__).resolve(strict=True) == EXTERNAL / "audit_snapshot_contract_integration.py",
            "Run the reviewed external file at its original path")
    require(RUNTIME.resolve(strict=True) == RUNTIME and AUDIT.resolve(strict=True) == AUDIT and AUDIT != RUNTIME,
            "The distinct original native roots must already exist without aliases")
    require(not CONTRACT.exists(), "A new contract is required; retain the existing original, including refusals")
    report["bundle_before"] = verify_bundle()
    report["freeze_metadata_before"] = {name: pinned(RUNTIME / "results/freeze_validation" / name, expected)
                                        for name, expected in FREEZE_PINS.items()}
    modules, report["native_tool_imports"] = load_actual_tools()
    guard = modules["reliability_v4_guard"]
    helper = modules["reliability_v4_snapshot_audit"]
    driver = modules["run_reliability_v4_safety"]
    report["adapter_header"] = adapter_header_only()
    raw = read_small(PLAN)
    require(hashlib.sha256(raw).hexdigest() == PLAN_SHA, "Original core plan bytes changed")
    plan = parse(raw)
    require(plan.get("plan_sha256") == PLAN_DIGEST == guard.sealed(plan, "plan_sha256")
            and plan.get("frozen_root") == str(RUNTIME), "Actual core plan canonical digest/root differs")
    report["plan"] = binding(PLAN, raw)
    expected = {name: value for name, value in plan["source_hashes"].items()
                if name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/"))
                and PurePosixPath(name).suffix in {".py", ".sh", ".msg"}}
    model = plan["protocol"]["resources"]["person"]["model"]
    for name in (model, "config/dds_runtime_humble22.json"):
        expected[name] = plan["source_hashes"][name]
    report["expected_registered_snapshot_entries"] = len(expected)
    trials = {trial["id"]: trial for trial in plan["trials"]}
    snapshots = []
    report["snapshots"] = []
    for identifier in FIRST3:
        trial = trials[identifier]
        require(trial["target_class"] == "person" and trial["model"] == model,
                "Expected original first-three person trial/model binding differs")
        path = Path(trial["directory"]) / "configuration/source_sha256.json"
        original = read_small(path)
        require(len(original) == 23847 and hashlib.sha256(original).hexdigest() == SNAPSHOT_SHA,
                "An original first-three snapshot changed: " + identifier)
        snapshot = parse(original)
        require(len(snapshot) == 204, "Original snapshot shape differs")
        row = {"id": identifier, "original": binding(path, original), "entries": len(snapshot),
               "default_strict": None, "helper_validate_snapshot_called": False}
        report["snapshots"].append(row)
        try:
            guard.source_snapshot_evidence(snapshot, expected, {}, plan, PLAN)
        except guard.Refusal as error:
            require(str(error) == "Safety actual saved source/model snapshot differs",
                    "The default strict path refused for an unexpected reason")
            row["default_strict"] = {"result": "EXPECTED_ORIGINAL_SET_DIFFERENCE_REFUSAL",
                "exception": type(error).__name__, "message": str(error),
                "extra_sources": {key: snapshot[key] for key in sorted(set(snapshot) - set(expected))},
                "missing_sources": sorted(set(expected) - set(snapshot)),
                "changed_sources": sorted(key for key in set(snapshot) & set(expected) if snapshot[key] != expected[key])}
            require(len(row["default_strict"]["extra_sources"]) == 17
                    and not row["default_strict"]["missing_sources"] and not row["default_strict"]["changed_sources"],
                    "The historical default strict set difference is no longer the expected one")
        else:
            raise ValueError("Default exact source equality unexpectedly accepted an expanded historical snapshot")
        snapshots.append((path, original, snapshot))
    require(all(original == snapshots[0][1] and snapshot == snapshots[0][2]
                for _, original, snapshot in snapshots), "The three original snapshots are no longer identical")
    # Original helper implementations are intentionally unchanged. Each of the
    # following calls retains its own full source/model validation traversal.
    report["contract_creation_attempted"] = True
    contract = helper.create_contract(PLAN,
        RUNTIME / "results/freeze_validation/source_integrity/source_frozen_integrity.json",
        RUNTIME / "results/freeze_validation/import_isolation.json", CONTRACT, api=guard)
    report["contract"] = contract
    report["contract_metadata"] = parse(read_small(contract["path"]))
    report["snapshots"][0]["helper_validate_snapshot_called"] = True
    evidence = helper.validate_snapshot(snapshots[0][2], expected, contract, plan, PLAN,
        api=guard, driver_path=driver.__file__, validator_path=guard.__file__)
    report["snapshots"][0]["explicit_contract_validation"] = evidence
    report["snapshots"][0]["validation_basis"] = "ACTUAL_UNMODIFIED_HELPER_VALIDATE_SNAPSHOT_CALL"
    for row in report["snapshots"][1:]:
        row["validation_basis"] = "ORIGINAL_BYTES_SHA_AND_COMPLETE_MAPPING_EQUAL_TO_FIRST_ACTUAL_HELPER_VALIDATED_SNAPSHOT"
        row["equivalent_to"] = report["snapshots"][0]["original"]
    report["mandatory_helper_hash_traversals_skipped"] = False
    report["bundle_after"] = verify_bundle()
    require(report["bundle_before"] == report["bundle_after"], "Audit bundle changed during the native audit")
    report["freeze_metadata_after"] = {name: pinned(RUNTIME / "results/freeze_validation" / name, expected)
                                       for name, expected in FREEZE_PINS.items()}
    require(report["freeze_metadata_before"] == report["freeze_metadata_after"],
            "Original freeze metadata changed during the native audit")
    for path, original, snapshot in snapshots:
        require(read_small(path) == original, "An original snapshot changed during the native audit: " + str(path))
    require(guard.file_binding(contract["path"]) == contract, "New contract changed during the native audit")
    report["result"] = "NATIVE_CONTRACT_AND_FIRST3_SNAPSHOT_AUDIT_COMPLETE_FORMAL_DUAL_ROOT_VALIDATION_PENDING"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-self-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    require(output.is_absolute() and output.parent.resolve(strict=True) == EXTERNAL,
            "Use a new independent receipt file in the reviewed external directory")
    report = {"schema_version": 1, "scope": "ACTUAL_FIXED_TOOL_NATIVE_CONTRACT_AND_SNAPSHOT_AUDIT_ONLY",
        "started_utc": utc(), "result": "INCOMPLETE", "contract_creation_attempted": False,
        "safety_registration_created": False, "formal_admission_or_plan_created": False,
        "formal_execution_authorized": False, "formal_dual_root_integration_validated": False,
        "historical_flight_imports_proved": False, "runtime_root_edited": False,
        "original_snapshots_edited": False, "bag_sidecar_or_telemetry_read_by_this_script": False,
        "helper_original_source_and_model_hashing_allowed_and_preserved": True}
    # Exclusive creation preserves any failed/incomplete receipt. No auto retry.
    with output.open("xb") as stream:
        try:
            report["self"] = binding(__file__)
            require(report["self"]["sha256"] == args.expected_self_sha256, "Reviewed integration script SHA differs")
            execute(report)
            require(binding(__file__) == report["self"], "Integration source changed during execution")
            code = 0
        except Exception as error:
            report["result"] = "REFUSED_OR_INCOMPLETE_NO_FORMAL_ADMISSION"
            report["error"] = type(error).__name__ + ": " + str(error)
            report["traceback"] = traceback.format_exc()
            report["contract_file_exists_at_failure"] = CONTRACT.exists()
            code = 2
        report["finished_utc"] = utc()
        stream.write((json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"result": report["result"], "receipt": str(output),
                      "formal_dual_root_integration_validated": False}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
