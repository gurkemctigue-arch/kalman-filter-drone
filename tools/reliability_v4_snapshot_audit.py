"""Audit an original flight snapshot against complete, pre-existing freeze maps.

This metadata adapter preserves the actual saved snapshot. It never selects,
removes or repairs a source file and never launches a runtime or a flight.
An explicit contract binds both the frozen runtime and these separate tools.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path, PurePosixPath
import sys

KIND = "RELIABILITY_V4_FROZEN_SNAPSHOT_AUDIT_CONTRACT"
RULE = "ORIGINAL_RUN_STAGE1_PY_SH_MSG_SCAN_PLUS_SELECTED_MODEL_AND_EXPLICIT_DDS"
TOOL_NAMES = {"driver": "run_reliability_v4_safety.py", "validator": "reliability_v4_guard.py",
              "helper": "reliability_v4_snapshot_audit.py", "registrar": "reliability_v4_register.py"}
BASE_NAMES = {key: "tools/" + value for key, value in TOOL_NAMES.items() if key != "helper"}
LIMITATION = ("The original import receipt records core/nodes packages and generated interfaces, "
              "plus the adapter ament prefix. It does not record every flight process module, "
              "the eight differing historical copies, or adapter_node.__file__.")


def relative_name(value, api):
    api.require(isinstance(value, str) and value and "\\" not in value and ":" not in value,
                "Snapshot source name must be a canonical relative POSIX path")
    path = PurePosixPath(value)
    api.require(not path.is_absolute() and path.as_posix() == value
                and all(part not in {".", ".."} for part in path.parts), "Snapshot source path escapes its root")
    return path


def source_file(root, name, api):
    relative_name(name, api)
    path = root / name
    api.require(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path,
                "Frozen source is missing, linked or outside its original lexical path: " + name)
    return path


def selected_source(name):
    path = PurePosixPath(name)
    return (name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/"))
            and path.suffix in {".py", ".sh", ".msg"})


def historical_copy_comparisons(extras, registered):
    comparisons = {}
    for name, digest in extras.items():
        tail = name.partition("/build/lib/")[2]
        candidates = [key for key in registered if tail and (key == tail or key.endswith("/" + tail))]
        if len(candidates) == 1:
            canonical = candidates[0]
            comparisons[name] = {"canonical_source": canonical, "historical_sha256": digest,
                                 "canonical_sha256": registered[canonical], "same_bytes": digest == registered[canonical]}
        else:
            comparisons[name] = {"canonical_candidates": candidates, "historical_sha256": digest,
                                 "interpretation": "Original retained extra; no unique canonical counterpart inferred"}
    return comparisons


def verify_import_receipt(receipt, root, entries, api):
    api.require(receipt.get("root") == str(root) and receipt.get("isolated") is True,
                "Original frozen import-isolation root/result differs")
    canonical = {"uav_tracking.core": "uav_tracking/core/__init__.py",
                 "uav_tracking_nodes": "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/__init__.py"}
    modules = receipt.get("module_files")
    api.require(isinstance(modules, dict) and set(canonical) <= modules.keys(), "Original canonical package import receipt missing")
    for name, relative in canonical.items():
        api.require(modules[name] == str(root / relative), "Original package import did not name its canonical source: " + name)
        api.require(api.sha(source_file(root, relative, api)) == entries[relative]["sha256"],
                    "Canonical imported package bytes changed: " + name)
    required = {"uav_tracking_interfaces.msg", "uav_tracking_interfaces.msg._target_observation_array",
                "uav_tracking_interfaces.msg._target_state"}
    api.require(required <= modules.keys(), "Original generated message import receipt incomplete")
    for name, value in modules.items():
        path = Path(value)
        api.require(path.is_absolute() and path.is_file() and path.resolve(strict=True).is_relative_to(root),
                    "Original imported module escaped actual frozen root: " + name)
        if name not in canonical:
            resolved = path.resolve(strict=True)
            api.require(name in required and path.is_relative_to(root / "ros2_ws/install")
                        and path.suffix == ".py" and "build/lib" not in path.as_posix()
                        and (resolved.is_relative_to(root / "ros2_ws/install")
                             or resolved.is_relative_to(root / "ros2_ws/build/uav_tracking_interfaces")),
                        "Unreviewed extra or historical-copy import in original receipt: " + name)
    prefixes = receipt.get("ros_package_prefixes")
    packages = {"uav_tracking_nodes", "uav_tracking_interfaces", "uav_tracking_bringup", "uav_tracking_px4_adapter"}
    api.require(isinstance(prefixes, dict) and set(prefixes) == packages
                and all(value == str(root / "ros2_ws/install") for value in prefixes.values())
                and (root / "ros2_ws/install").is_dir(), "Original ament prefixes do not name the actual frozen install")


def validate_contract(binding, plan, plan_path, *, api, driver_path, validator_path):
    """Verify all original bindings before admitting a distinct audit-tool root."""
    contract_path, contract = api.bound(binding)
    fields = {"schema_version", "kind", "created_utc", "rule", "frozen_root", "audit_tool_root", "core_plan",
              "freeze_report", "source_before", "source_after", "frozen_map", "import_isolation", "audit_tools",
              "base_tools", "evidence_limitations"}
    api.require(set(contract) == fields and contract.get("schema_version") == 1 and contract.get("kind") == KIND
                and contract.get("rule") == RULE and contract.get("evidence_limitations") == LIMITATION,
                "Explicit complete frozen snapshot audit contract required")
    root = Path(plan["frozen_root"]).resolve(strict=True)
    api.require(contract.get("frozen_root") == str(root), "Snapshot audit frozen root differs")
    api.require(Path(plan["results_root"]).resolve(strict=True) == (root / "results").resolve(strict=True),
                "Original frozen results link no longer names the bound results storage")
    original_validation = root / "results/freeze_validation"
    originals = {"freeze_report": "source_integrity/source_frozen_integrity.json",
                 "source_before": "source_integrity/source_before.json", "source_after": "source_integrity/source_after.json",
                 "frozen_map": "source_integrity/frozen_actual.json", "import_isolation": "import_isolation.json"}
    for key, relative in originals.items():
        api.require(api.bound(contract[key], json_data=False) == (original_validation / relative).resolve(strict=True),
                    "Snapshot audit must retain the actual original freeze evidence path: " + key)
    bound_plan_path, bound_plan = api.bound({key: contract["core_plan"][key] for key in ("path", "sha256")})
    api.require(bound_plan_path == Path(plan_path).resolve(strict=True) and bound_plan == plan
                and contract["core_plan"].get("plan_sha256") == plan["plan_sha256"], "Snapshot audit binds another core plan")
    api.require(api.utc(plan["created_utc"]) <= api.utc(contract["created_utc"]) <= api.now(),
                "Snapshot audit contract predates its actual core plan or lies in the future")
    audit_root = Path(contract["audit_tool_root"]).resolve(strict=True)
    api.require(audit_root != root, "Explicit snapshot audit and frozen runtime roots must be distinct")
    tools = contract["audit_tools"]
    api.require(isinstance(tools, dict) and set(tools) == set(TOOL_NAMES), "Actual audit tool bindings incomplete")
    for key, name in TOOL_NAMES.items():
        actual = api.bound(tools[key], json_data=False)
        api.require(actual == audit_root / "tools" / name, "Audit executable escaped its explicit tool root: " + key)
    api.require(tools["driver"] == api.file_binding(driver_path)
                and tools["validator"] == api.file_binding(validator_path)
                and tools["helper"] == api.file_binding(__file__), "Snapshot audit executable path/bytes differ")
    _, report = api.bound(contract["freeze_report"])
    maps = {name: api.bound(contract[name])[1] for name in ("source_before", "source_after", "frozen_map")}
    api.require(report.get("status") == "PASS" and report.get("scope") == "RSYNC_FILTERED_SOURCE_PRE_POST_AND_COMPLETE_FROZEN_COPY_BYTES"
                and report.get("frozen") == str(root) and report.get("errors") == []
                and type(report.get("build_returncode")) is int and report.get("build_returncode") == 0
                and report.get("copy_identical") is True and report.get("source_unchanged") is True,
                "Original full freeze report did not pass for this root")
    api.require(api.utc(report["created_utc"]) <= api.utc(plan["created_utc"]), "Full freeze evidence follows the core plan")
    for label in ("source_pre_post", "frozen_copy"):
        api.require(report.get(label) == {"added": [], "changed": [], "missing": []}, "Original freeze reported source differences")
    api.require(contract["source_before"]["sha256"] == report["before"]["sha256"]
                and contract["source_after"]["sha256"] == report["maps"]["source_after.json"]["sha256"]
                and contract["frozen_map"]["sha256"] == report["maps"]["frozen_actual.json"]["sha256"],
                "Archived maps do not match the original freeze report digests")
    entries = maps["frozen_map"].get("entries")
    api.require(isinstance(entries, dict) and entries and maps["frozen_map"].get("frozen") == str(root)
                and entries == maps["source_before"].get("entries") == maps["source_after"].get("entries")
                and maps["source_before"].get("source") == report.get("source") == maps["source_after"].get("source"),
                "Full original pre/post/frozen map entries or origins differ")
    api.require(all(report.get(name) == len(entries) for name in ("actual_frozen_entries", "actual_source_entries", "expected_entries")),
                "Original complete map entry counts differ")
    for name in entries:
        relative_name(name, api)
    sources = plan.get("source_hashes")
    api.require(isinstance(sources, dict) and sources, "Core registered source hashes missing")
    for name, digest in sources.items():
        entry = entries.get(name, {})
        path = source_file(root, name, api)
        api.require(entry.get("kind") == "file" and entry.get("sha256") == digest
                    and type(entry.get("bytes")) is int and path.stat().st_size == entry["bytes"]
                    and api.sha(path) == digest, "Registered canonical source/model differs from original freeze: " + name)
    bases = contract["base_tools"]
    api.require(isinstance(bases, dict) and set(bases) == set(BASE_NAMES), "Original frozen audit tool ancestry incomplete")
    for key, relative in BASE_NAMES.items():
        path = api.bound(bases[key], json_data=False)
        api.require(path == source_file(root, relative, api) and bases[key]["sha256"] == entries[relative]["sha256"],
                    "Original frozen audit tool ancestry differs: " + key)
    # Validate every extra according to the original scanner, never a glob ignore
    # or a caller-supplied list. Unselected original assets remain in the maps.
    scanned = {}
    for name, entry in entries.items():
        if selected_source(name):
            path = source_file(root, name, api)
            api.require(entry.get("kind") == "file" and type(entry.get("bytes")) is int
                        and path.stat().st_size == entry["bytes"] and api.sha(path) == entry.get("sha256"),
                        "Original scanner source changed or is not an ordinary file: " + name)
            scanned[name] = entry["sha256"]
    # Also detect newly introduced scanner-visible paths absent from the maps.
    actual_names = {path.relative_to(root).as_posix()
                    for directory in ("scripts", "uav_tracking", "ros2_ws/src")
                    for path in (root / directory).rglob("*")
                    if path.is_file() and path.suffix in {".py", ".sh", ".msg"}}
    api.require(actual_names == set(scanned), "Actual scanner-visible source set differs from the complete original frozen map")
    _, imports = api.bound(contract["import_isolation"])
    verify_import_receipt(imports, root, entries, api)
    return {"path": contract_path, "contract": contract, "root": root, "audit_tool_root": audit_root,
            "scanned_sources": scanned, "extra_sources": {name: value for name, value in scanned.items() if name not in sources},
            "evidence_limitations": LIMITATION}


def validate_snapshot(snapshot, expected, contract_binding, plan, plan_path, *, api, driver_path, validator_path):
    context = validate_contract(contract_binding, plan, plan_path, api=api, driver_path=driver_path, validator_path=validator_path)
    scanned = context["scanned_sources"]
    registered = {name: value for name, value in plan["source_hashes"].items() if selected_source(name)}
    api.require(all(expected.get(name) == value for name, value in registered.items())
                and all(name in plan["source_hashes"] and value == plan["source_hashes"][name]
                        for name, value in expected.items()),
                "Canonical snapshot requirements were removed or invented")
    effective = {**scanned, **expected}
    api.require(isinstance(snapshot, dict) and snapshot == effective,
                "Actual snapshot differs from exact original scanned sources plus registered model/DDS")
    return {"result": "PASS", "mode": KIND, "contract": api.file_binding(context["path"]),
            "registered_count": len(expected), "original_extra_count": len(context["extra_sources"]),
            "original_extra_sources": context["extra_sources"],
            "historical_copy_comparisons": historical_copy_comparisons(context["extra_sources"], plan["source_hashes"]),
            "evidence_limitations": LIMITATION}


def create_contract(core_plan, freeze_report, import_isolation, output, *, api):
    plan_path = Path(core_plan).resolve(strict=True)
    plan = api.load(plan_path)
    root = Path(plan["frozen_root"]).resolve(strict=True)
    report_path = Path(freeze_report).resolve(strict=True)
    directory = report_path.parent
    tool_root = Path(__file__).resolve().parents[1]
    contract = {"schema_version": 1, "kind": KIND, "created_utc": datetime.now(timezone.utc).isoformat(), "rule": RULE,
        "frozen_root": str(root), "audit_tool_root": str(tool_root),
        "core_plan": {**api.file_binding(plan_path), "plan_sha256": plan["plan_sha256"]},
        "freeze_report": api.file_binding(report_path), "import_isolation": api.file_binding(import_isolation),
        "source_before": api.file_binding(directory / "source_before.json"),
        "source_after": api.file_binding(directory / "source_after.json"),
        "frozen_map": api.file_binding(directory / "frozen_actual.json"),
        "audit_tools": {key: api.file_binding(tool_root / "tools" / name) for key, name in TOOL_NAMES.items()},
        "base_tools": {key: api.file_binding(root / relative) for key, relative in BASE_NAMES.items()},
        "evidence_limitations": LIMITATION}
    output = Path(output).resolve()
    results = Path(plan["results_root"]).resolve(strict=True)
    api.require(output.is_relative_to(results) and output != results and not output.exists()
                and not any(output.is_relative_to(Path(trial["directory"]).resolve()) for trial in plan["trials"]),
                "New independent contract in actual results storage required")
    # Exclusive creation retains a refused contract for inspection, never edits originals.
    api.write_new(output, contract)
    validate_contract(api.file_binding(output), plan, plan_path, api=api,
                      driver_path=tool_root / "tools" / TOOL_NAMES["driver"], validator_path=api.__file__)
    return api.file_binding(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-plan", type=Path, required=True)
    parser.add_argument("--freeze-report", type=Path, required=True)
    parser.add_argument("--import-isolation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    spec = importlib.util.spec_from_file_location("snapshot_audit_guard", Path(__file__).with_name(TOOL_NAMES["validator"]))
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    try:
        import json
        print(json.dumps(create_contract(args.core_plan, args.freeze_report, args.import_isolation, args.output, api=guard), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
