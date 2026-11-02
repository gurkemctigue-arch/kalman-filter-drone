"""Windows preparation audit: parse source only; never import target modules."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROJECT = Path("D:/基于yolo和卡尔曼滤波")
NATIVE = Path(r"\\wsl.localhost\UAVHumble22\root\uav_tracking_snapshot_audit54_tools01")
LIMIT = 4 * 1024**2


def read(path):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= LIMIT, str(path)
    raw = path.read_bytes()
    assert len(raw) <= LIMIT
    return raw


def observe(path, expected=None):
    raw = read(path)
    value = {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if expected is not None:
        assert (value["bytes"], value["sha256"]) == expected, str(path)
    return value


def main():
    script = BASE / "audit_snapshot_contract_integration.py"
    raw = read(script)
    tree = ast.parse(raw.decode("utf-8"), filename=str(script))
    compile(tree, str(script), "exec")  # Syntax only; the resulting code is never executed.
    names = {"TOOLS", "ADAPTER_FILES", "FREEZE_PINS", "PLAN_SHA", "PLAN_DIGEST", "SNAPSHOT_SHA", "BUNDLE_SHA", "FIRST3"}
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and len(node.targets) == 1
                 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names}
    assert set(constants) == names
    tools = {name: observe(NATIVE / name, pin) for name, pin in constants["TOOLS"].items()}
    adapter = Path("D:/WSL/UAVHumble22-validation/formal48_dds_adapter01")
    adapters = {name: observe(adapter / name, pin) for name, pin in constants["ADAPTER_FILES"].items()}
    frozen = PROJECT / "results/frozen_fullplan_v4_humble54"
    metadata = {name: observe(frozen / "freeze_validation" / name, pin)
                for name, pin in constants["FREEZE_PINS"].items()}
    bundle = observe(NATIVE / "bundle_manifest.json")
    assert bundle["sha256"] == constants["BUNDLE_SHA"]
    plan_path = frozen / "reliability_v4_humble54_core12_probe01_matrix/plan.json"
    plan_observed = observe(plan_path)
    assert plan_observed["sha256"] == constants["PLAN_SHA"]
    plan = json.loads(read(plan_path))
    canonical = hashlib.sha256(json.dumps({key: value for key, value in plan.items() if key != "plan_sha256"},
                             sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert plan["plan_sha256"] == canonical == constants["PLAN_DIGEST"]
    expected = {name: value for name, value in plan["source_hashes"].items()
                if name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/"))
                and Path(name).suffix in {".py", ".sh", ".msg"}}
    for name in (plan["protocol"]["resources"]["person"]["model"], "config/dds_runtime_humble22.json"):
        expected[name] = plan["source_hashes"][name]
    snapshots = []
    first_raw = first_map = None
    for identifier in constants["FIRST3"]:
        trial = next(item for item in plan["trials"] if item["id"] == identifier)
        path = frozen / Path(trial["directory"]).name / "configuration/source_sha256.json"
        snapshot_raw = read(path)
        snapshot = json.loads(snapshot_raw)
        observed = observe(path, (23847, constants["SNAPSHOT_SHA"]))
        if first_raw is None:
            first_raw, first_map = snapshot_raw, snapshot
        assert first_raw == snapshot_raw and first_map == snapshot and len(snapshot) == 204
        extras = {key: snapshot[key] for key in sorted(set(snapshot) - set(expected))}
        missing = sorted(set(expected) - set(snapshot))
        changed = sorted(key for key in set(snapshot) & set(expected) if snapshot[key] != expected[key])
        assert len(extras) == 17 and not missing and not changed
        snapshots.append({"id": identifier, "original": observed, "bytes_and_full_mapping_equal": True,
                          "static_expected_set_difference": {"extras": len(extras), "missing": missing, "changed": changed},
                          "default_strict_guard_executed": False, "helper_executed": False})
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    attrs = [node.func.attr for node in calls if isinstance(node.func, ast.Attribute)]
    assert attrs.count("create_contract") == 1 and attrs.count("validate_snapshot") == 1
    assert attrs.count("source_snapshot_evidence") == 1
    assert not set(attrs) & {"load_context", "load_original_guard", "load_core", "register", "execute_one", "run_one", "system", "Popen"}
    source = raw.decode("utf-8")
    assert "sys.modules[name] = module" in source and "driver.ROOT == AUDIT" in source
    assert not any(isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
                   and node.attr == "ROOT" for node in ast.walk(tree))
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PREPARED_SOURCE_SYNTAX_AND_SMALL_PIN_CHECKS_PASSED_NATIVE_EXECUTION_NOT_PERFORMED",
        "script": observe(script), "verifier": observe(Path(__file__)), "bundle": bundle,
        "tools": tools, "adapter_files": adapters, "freeze_metadata": metadata,
        "original_plan": plan_observed, "snapshots": snapshots, "expected_registered_entries": len(expected),
        "syntax_compiled_without_execution": True, "target_modules_imported": False,
        "wsl_or_native_commands_run": False, "contract_or_safety_registration_created": False,
        "formal_plan_or_admission_created": False, "models_bags_sidecars_large_telemetry_read": False,
        "frozen_runtime_source_changed": False,
        "not_validated_here": ["Actual native imports", "Real helper contract and snapshot calls",
                              "Real default strict refusals", "Real adapter tool_manifest",
                              "Safety4", "Real final-manifest formal dual-root load chain"]}
    output = BASE / "windows_preparation_review01.json"
    with output.open("xb") as stream:
        stream.write((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"result": report["result"], "script": report["script"], "receipt": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
