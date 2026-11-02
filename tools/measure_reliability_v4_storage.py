"""Measure all 28 actual development cells without reading recorded payloads.

Produces the per-trial size receipts consumed by reliability_v4_storage_budget.
Only frozen text sources and named small evidence/metadata files are hashed.
Bag, telemetry, model, VHD and other payloads are statted, never opened. This
does not rerun evaluation, change a terminal verdict, or admit a formal flight.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

_SPEC = importlib.util.spec_from_file_location(
    "measurement_storage_budget", Path(__file__).with_name("reliability_v4_storage_budget.py"))
budget = importlib.util.module_from_spec(_SPEC)
_BYTECODE = sys.dont_write_bytecode
try:
    sys.dont_write_bytecode = True
    _SPEC.loader.exec_module(budget)
finally:
    sys.dont_write_bytecode = _BYTECODE
guard = budget.guard
KIND = "RELIABILITY_V4_COMPLETE28_FILE_SIZE_ACCOUNTING_NOT_ADMISSION"
TEXT_SUFFIXES = {".py", ".sh", ".msg", ".yaml", ".yml", ".json", ".sdf", ".xml",
                 ".config", ".cfg", ".txt", ".toml", ".urdf", ".patch", ".gitattributes"}
REPORTS = ("bag_integrity.json", "recording_closure.json", "summary.json",
           "process_exit_codes.json", "run_config.json", "configuration/source_sha256.json",
           "configuration/runtime_parameters.yaml")


def contained(root, relative):
    guard.require(isinstance(relative, str) and relative and "\\" not in relative
                  and ":" not in relative, "Canonical relative evidence path required")
    name = PurePosixPath(relative)
    guard.require(not name.is_absolute() and ".." not in name.parts
                  and name.as_posix() == relative, "Unsafe evidence path")
    root = Path(root).resolve(strict=True)
    path = root / relative
    guard.require(path.is_file() and not path.is_symlink()
                  and path.resolve(strict=True).is_relative_to(root), "Missing/linked/escaping evidence: " + relative)
    return path


def inventory(directory):
    """The directory tree and every file size, without opening file contents."""
    directory = Path(directory)
    guard.require(directory.is_dir() and not directory.is_symlink(), "Original unlinked trial directory required")
    root, files = directory.resolve(strict=True), {}
    for path in sorted(directory.rglob("*")):
        guard.require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root),
                      "Linked/escaping trial inventory entry")
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = path.stat().st_size
        else:
            guard.require(path.is_dir(), "Nonordinary trial inventory entry")
    guard.require(bool(files), "Empty original trial inventory")
    return files


def small_binding(path, inputs, *, bag_metadata=False):
    path = Path(path)
    if bag_metadata:
        guard.require(path.name == "metadata.yaml" and path.parent.name == "rosbag"
                      and path.is_file() and not path.is_symlink()
                      and path.stat().st_size <= 8 * 1024**2, "Named small bag metadata required")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        digest = guard.sha(path)
    actual = path.resolve(strict=True)
    inputs[str(actual)] = {"sha256": digest, "bag_metadata": bag_metadata}
    return {"path": str(actual), "sha256": digest}


def named_json(path, inputs):
    binding = small_binding(path, inputs)
    return binding, guard.load(binding["path"])


def load_checked_module(root, sources, relative, name):
    path = contained(root, relative)
    guard.require(guard.sha(path) == sources.get(relative), "Frozen helper SHA differs: " + relative)
    original = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        return guard.import_file(name, path)
    finally:
        sys.dont_write_bytecode = original


def source_context(plans, paths, inputs):
    core, extension = plans["core"], plans["extension"]
    for name in ("frozen_root", "results_root", "source_hashes", "model_hashes", "config_hashes", "protocol"):
        guard.require(core.get(name) == extension.get(name) and core.get(name) is not None,
                      "Core/extension source/storage/protocol identity differs: " + name)
    root = Path(core["frozen_root"])
    sources = core["source_hashes"]
    checked, unread_assets, source_bytes = {}, {}, 0
    for relative, expected in sources.items():
        path = contained(root, relative)
        source_bytes += path.stat().st_size
        if path.suffix.lower() in TEXT_SUFFIXES:
            binding = small_binding(path, inputs)
            guard.require(binding["sha256"] == expected, "Frozen text source SHA differs: " + relative)
            checked[relative] = expected
        else:
            unread_assets[relative] = {"declared_sha256": expected, "bytes": path.stat().st_size,
                                      "content_revalidated": False}
    runner = load_checked_module(root, sources, "scripts/run_reliability_v4.py", "storage_measurement_frozen_runner")
    failures = load_checked_module(root, sources, "uav_tracking/research_failures.py", "storage_measurement_recording_checks")
    for label, plan in plans.items():
        runner.validate_plan(plan, paths[label])
        protocol_binding, protocol = named_json(root / runner.PROTOCOL_PATH, inputs)
        guard.require(protocol_binding["sha256"] == plan["protocol_sha256"] and protocol == plan["protocol"],
                      "Actual frozen development protocol changed")
        if plan.get("extension_protocol_binding") is not None:
            binding = plan["extension_protocol_binding"]
            actual, data = named_json(root / runner.EXTENSION_PROTOCOL_PATH, inputs)
            guard.require(actual == {key: binding[key] for key in ("path", "sha256")}
                          and data == binding["protocol"], "Actual extension protocol changed")
    guard.require(runner.split_clock_bridge_setting(core) is runner.split_clock_bridge_setting(extension),
                  "Core/extension clock bridge modes differ")
    return runner, failures, {"checked_text_source_hashes": checked,
        "declared_source_files_stat_bytes": source_bytes,
        "unread_source_assets": unread_assets,
        "asset_claim_boundary": "Declared model/asset hashes are retained from the original plans and flight snapshots; their current content is not rehashed by this size-only tool."}


def completed_execution(execution, command, codes=(0,)):
    guard.require(isinstance(execution, dict) and execution.get("command") == command
                  and type(execution.get("returncode")) is int and execution["returncode"] in codes
                  and execution.get("error") is None, "Actual original execution command/exit differs")
    start, end = guard.utc(execution["started_utc"]), guard.utc(execution["finished_utc"])
    guard.require(start <= end <= guard.now(), "Invalid original execution chronology")
    return start, end


def archive_sizes(archive, directory, files, metadata):
    guard.require(archive.get("destination") and Path(archive["destination"]).resolve() == directory / "rosbag"
                  and archive.get("spool_retained") is False, "Archive destination/owned spool closure differs")
    guard.require(metadata["sha256"] == archive.get("published_metadata_sha256"), "Published bag metadata SHA changed")
    raw, compressed = archive["raw_validation"]["files"], archive["compressed_files"]
    guard.require(isinstance(raw, list) and bool(raw) and isinstance(compressed, list) and bool(compressed),
                  "Complete raw/lossless archive size mapping required")
    by_name, mapping = {}, []
    for row in raw:
        name = row["path"]
        relative = PurePosixPath(name)
        guard.require(isinstance(name, str) and relative.as_posix() == name and not relative.is_absolute()
                      and ".." not in relative.parts and "\\" not in name and ":" not in name
                      and name.endswith(".db3") and name not in by_name, "Unsafe/duplicate raw archive path")
        guard.integer(row["bytes"], "recorded raw SQLite bytes", minimum=1)
        guard.require(re.fullmatch(r"[a-f0-9]{64}", str(row.get("sha256", ""))), "Original raw digest required")
        by_name[name] = row
    seen = set()
    for row in compressed:
        name = row["path"]
        guard.require(isinstance(name, str) and name.endswith(".db3.zstd") and name not in seen,
                      "Duplicate/non-lossless compressed path")
        path = contained(directory / "rosbag", name)
        original = by_name.get(name.removesuffix(".zstd"))
        guard.require(original is not None and row.get("raw_bytes") == original["bytes"]
                      and row.get("raw_sha256") == original["sha256"] and row.get("zstd_test") == "PASS"
                      and re.fullmatch(r"[a-f0-9]{64}", str(row.get("sha256", "")))
                      and type(row.get("bytes")) is int and row["bytes"] > 0
                      and path.stat().st_size == row["bytes"] == files.get("rosbag/" + name),
                      "Original native/lossless mapping or current archive size differs")
        seen.add(name)
        mapping.append({"raw": dict(original), "compressed": dict(row), "current_compressed_stat_bytes": path.stat().st_size,
                        "compressed_payload_rehashed": False, "native_read_repeated": False})
    guard.require(len(seen) == len(by_name), "Incomplete raw/compressed archive denominator")
    return sum(row["bytes"] for row in raw), sum(row["bytes"] for row in compressed), mapping


def read_cell(key, plan, trial, runner, failures, inputs, *, snapshot_audit=None):
    original_directory = Path(trial["directory"])
    guard.require(original_directory.is_dir() and not original_directory.is_symlink(),
                  "Original unlinked trial directory required")
    directory = original_directory.resolve(strict=True)
    terminal_path = runner.record_path(plan, trial)
    terminal_binding, record = named_json(terminal_path, inputs)
    guard.require(record.get("record_sha256") == guard.sealed(record, "record_sha256")
                  and record.get("plan_sha256") == plan["plan_sha256"] and record.get("id") == trial["id"],
                  "Changed/foreign original terminal record")
    guard.require(record.get("status") in {"PASS", "FAIL", "EVALUATION_PENDING", "INCOMPLETE_EVIDENCE"}
                  and record.get("infrastructure_stop") is False and record.get("execution_status") == "COMPLETED"
                  and type(record.get("flight_exit_code")) is int and record["flight_exit_code"] == 0
                  and record.get("runtime_configuration", {}).get("errors") == []
                  and record.get("cleanup", {}).get("residual_processes") == [],
                  "Incomplete/infrastructure development exposure")
    evidence, reports = {}, {}
    for relative in REPORTS:
        path = contained(directory, relative)
        evidence[relative] = small_binding(path, inputs)
        guard.require(evidence[relative]["sha256"] == record.get("artifact_hashes", {}).get(relative),
                      "Original small artifact SHA changed: " + relative)
        if path.suffix == ".json":
            reports[relative] = guard.load(path)
    runtime = record["runtime_configuration"]
    guard.require(runtime.get("run_config_sha256") == evidence["run_config.json"]["sha256"]
                  and runtime.get("runtime_parameters_sha256") == evidence["configuration/runtime_parameters.yaml"]["sha256"],
                  "Original runtime receipt digests differ from bound current configuration")
    configuration = reports["run_config.json"]
    guard.require(configuration.get("seed") == 4 and configuration.get("target_class") == trial["target_class"]
                  and configuration.get("duration") == 75. and configuration.get("no_bag") is False
                  and configuration.get("command_mode") == trial["command_mode"]
                  and configuration.get("model_path") == str(Path(plan["frozen_root"]) / trial["model"])
                  and configuration.get("condition", "clean") == trial.get("condition", "clean"),
                  "Original recorded configuration differs from full75s registered cell")
    actual_sources = reports["configuration/source_sha256.json"]
    required_sources = {name: value for name, value in plan["source_hashes"].items()
                        if name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/"))
                        and Path(name).suffix in {".py", ".sh", ".msg"}}
    required_sources[trial["model"]] = plan["model_hashes"][trial["model"]]
    snapshot_evidence = None
    if snapshot_audit is None:
        guard.require(all(actual_sources.get(name) == value for name, value in required_sources.items())
                      and all(plan["source_hashes"].get(name) == value for name, value in actual_sources.items()),
                      "Actual flight source/model snapshot differs from its frozen plan")
    else:
        module, context = snapshot_audit
        snapshot_evidence = module.snapshot_evidence(context, actual_sources, plan, trial)
    exits = reports["process_exit_codes.json"]
    guard.require({"gazebo", "agent", "px4", "bag", "monitor", "ros"} <= exits.keys()
                  and all(type(code) is int and code in ({0, -2} if name == "agent" else {0})
                          for name, code in exits.items()), "Original child-process exits are incomplete/failed")
    flights = [entry for entry in record.get("commands", []) if entry.get("kind") == "flight"]
    guard.require(len(flights) == 1, "One original flight execution is required")
    _, flight_end = completed_execution(flights[0], trial["flight_command"])
    entries = record.get("evaluations", [])
    guard.require(len(entries) == len(trial["evaluations"])
                  and {entry.get("kind") for entry in entries} == {spec["kind"] for spec in trial["evaluations"]},
                  "Original evaluator denominator is incomplete/duplicated")
    for kind in (spec["kind"] for spec in trial["evaluations"]):
        selected = [entry for entry in entries if entry.get("kind") == kind]
        specs = [spec for spec in trial["evaluations"] if spec["kind"] == kind]
        guard.require(len(selected) == len(specs) == 1, "Original evaluator missing or duplicated")
        entry, spec = selected[0], specs[0]
        binding = small_binding(contained(directory, Path(spec["report"]).name), inputs)
        guard.require(Path(spec["report"]).resolve() == Path(binding["path"])
                      and Path(entry.get("report", "")).resolve() == Path(binding["path"])
                      and entry.get("report_sha256") == binding["sha256"]
                      == record.get("artifact_hashes", {}).get(Path(spec["report"]).name),
                      "Original evaluator report binding changed")
        start, _ = completed_execution(entry["execution"], spec["command"],
                                       codes=(0,) if kind in {"source_clock", "native_startup"} else (0, 2))
        checked = runner.read_evaluation(spec, entry["execution"], plan)
        guard.require(start >= flight_end and checked.get("result") == entry.get("result")
                      and checked.get("result") not in {"MISSING", "INVALID", "EVALUATION_PENDING"}
                      and checked.get("error") is None and entry.get("error") is None,
                      "Independent evaluator report is unreadable or differs from original record")
        if kind in {"source_clock", "native_startup"}:
            guard.require(checked["result"] == "PASS", "Independent clock/native report did not pass unchanged")
        evidence[kind] = binding
    recording = failures.classify_recording_artifacts(directory)
    guard.require(recording.get("stop") is False and all(
        recording.get("reports", {}).get(name, {}).get("status") == "PASS"
        for name in ("bag_integrity.json", "recording_closure.json")), "Original recording closure/native archive did not pass")
    summary, closure = reports["summary.json"], reports["recording_closure.json"]
    start = budget.finite(summary.get("follow_start_s"), "actual follow start")
    end = guard.integer(closure["observations"][-1]["last_clock_ns"], "original final Clock", minimum=1)
    guard.require(summary.get("termination_reason") == "follow_duration_reached"
                  and end >= math.ceil((start + 75.) * 1e9), "Short/aborted recording cannot budget full75s exposure")
    files = inventory(directory)
    metadata = small_binding(contained(directory, "rosbag/metadata.yaml"), inputs, bag_metadata=True)
    guard.require(metadata["sha256"] == record["artifact_hashes"].get("rosbag/metadata.yaml"),
                  "Original published bag metadata terminal binding differs")
    raw_bytes, compressed_bytes, mapping = archive_sizes(reports["bag_integrity.json"], directory, files, metadata)
    bag_bytes = sum(size for name, size in files.items() if name.startswith("rosbag/"))
    components = {name: 0 for name in ("recorded_bag_files", "configuration_and_source_receipts",
        "evaluation_reports", "telemetry_and_sidecars", "runtime_logs", "other_trial_files")}
    evaluator_names = {Path(spec["report"]).name for spec in trial["evaluations"]}
    for name, size in files.items():
        category = ("recorded_bag_files" if name.startswith("rosbag/") else
                    "configuration_and_source_receipts" if name.startswith("configuration/") else
                    "evaluation_reports" if name in evaluator_names else
                    "telemetry_and_sidecars" if Path(name).suffix in {".jsonl", ".bson"} else
                    "runtime_logs" if Path(name).suffix == ".log" else "other_trial_files")
        components[category] += size
    result = {"schema_version": 1, "created_utc": guard.now().isoformat(),
        "scope": "FILE_SIZE_ACCOUNTING_ONLY_NO_VERDICT_CHANGE", "trial": trial["directory"],
        "cell": list(key), "total_trial_bytes": sum(files.values()), "bag_bytes": bag_bytes,
        "auxiliary_bytes": sum(files.values()) - bag_bytes, "raw_sqlite_bytes": raw_bytes,
        "compressed_sqlite_bytes": compressed_bytes, "files": files, "component_bytes": components,
        "original_status": record["status"],
        "original_terminal": terminal_binding, "plan_sha256": plan["plan_sha256"], "duration_s": 75.,
        "original_report_bindings": evidence, "published_metadata": metadata,
        "native_lossless_archive_mapping": mapping,
        "temporary_archive_evidence": {"scope": "ACTUAL_ARCHIVE_COMPONENT_BYTES_NOT_OBSERVED_PEAK",
            "raw_sqlite_bytes": raw_bytes, "compressed_sqlite_bytes": compressed_bytes,
            "archive_processing_receipt": reports["bag_integrity.json"].get("archive_processing"),
            "observed_peak_bytes": None, "bound_is_measurement": False,
            "existing_budget_rule": "three_raw_two_compressed_plus_margin_v1",
            "archive_component_bound_without_growth_or_margin_bytes": 3 * raw_bytes + 2 * compressed_bytes},
        "inventory_payload_content_reads": False, "capacity_admission_performed": False,
        "claim_boundary": "All original persisted configuration/source, evaluation, telemetry, sidecar, log and archive files are included. Native validation/losslessness refer to the bound original recording report, not a repeated payload read. Temporary coexistence is an explicit component formula, not a sampled peak or a capacity admission."}
    if snapshot_evidence is not None:
        result["source_snapshot_validation"] = snapshot_evidence
    return result


def checked_output(output, plans):
    output = Path(output)
    guard.require(not output.exists() and not output.is_symlink() and output.parent.is_dir(), "One fresh output directory with an existing parent is required")
    actual = output.resolve()
    results = Path(plans["core"]["results_root"]).resolve(strict=True)
    guard.require(actual != results and actual.is_relative_to(results), "Size receipts must be outside source and inside actual results storage")
    for plan in plans.values():
        protected = [Path(plan["output"]).resolve(), *(Path(trial["directory"]).resolve() for trial in plan["trials"])]
        guard.require(not any(actual.is_relative_to(path) or path.is_relative_to(actual) for path in protected),
                      "Size output overlaps original plan/trial evidence")
    return actual


def measure(core_path, extension_path, output, *, physical_inventory=None,
            snapshot_audit_registry=None, snapshot_audit_registry_sha256=None,
            snapshot_audit_native_receipt=None, snapshot_audit_native_receipt_sha256=None):
    inputs, plans, paths, cells, bindings = {}, {}, {}, {}, {}
    audit_options = (snapshot_audit_registry, snapshot_audit_registry_sha256,
                     snapshot_audit_native_receipt, snapshot_audit_native_receipt_sha256)
    guard.require(all(value is None for value in audit_options) or all(value is not None for value in audit_options),
                  "Snapshot audit requires all four explicit registry/native receipt path/SHA options")
    tools = {name: small_binding(path, inputs) for name, path in (
        ("measurement", Path(__file__)), ("budget_schema", Path(budget.__file__)),
        ("guard_helpers", Path(guard.__file__)))}
    for label, path in (("core", core_path), ("extension", extension_path)):
        binding, plan, entries = budget.read_development_plan(path, label, {})
        inputs[binding["path"]] = {"sha256": binding["sha256"], "bag_metadata": False}
        plans[label], paths[label], bindings[label] = plan, Path(binding["path"]), binding
        cells.update(entries)
    output = checked_output(output, plans)
    guard.require(len(cells) == len({Path(trial["directory"]).resolve() for trial in cells.values()}) == 28,
                  "Exactly 28 distinct original physical development cells required")
    runner, failures, sources = source_context(plans, paths, inputs)
    snapshot_audit = None
    if snapshot_audit_registry is not None:
        path = Path(__file__).with_name("reliability_v4_storage_snapshot_audit.py")
        tools["snapshot_audit_metadata_adapter"] = small_binding(path, inputs)
        original = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            module = guard.import_file("measurement_saved_snapshot_audit", path)
        finally:
            sys.dont_write_bytecode = original
        context = module.prepare(
            {"path": str(snapshot_audit_registry), "sha256": snapshot_audit_registry_sha256},
            {"path": str(snapshot_audit_native_receipt), "sha256": snapshot_audit_native_receipt_sha256},
            plans["core"], paths["core"], guard=guard, bind=lambda item: small_binding(item, inputs), runner=runner)
        snapshot_audit = module, context
    receipts = {}
    for key, trial in sorted(cells.items()):
        receipts[trial["name"] + ".json"] = read_cell(key, plans[key[0]], trial, runner, failures, inputs,
                                                   snapshot_audit=snapshot_audit)
    free = [{"role": role, "path": str(path), "free_bytes": shutil.disk_usage(path).free,
             "sampled_utc": guard.now().isoformat(),
             "device_id": path.stat().st_dev, "scope": "CURRENT_FILESYSTEM_FREE_BYTES_NOT_HOST_PHYSICAL_ADMISSION"}
            for role, path in (("results", Path(plans["core"]["results_root"]).resolve()),
                               ("frozen_root", Path(plans["core"]["frozen_root"])))]
    host = None
    if physical_inventory is not None:
        binding, data = named_json(physical_inventory, inputs)
        guard.require(data.get("schema_version") == 1 and data.get("kind") == "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY"
                      and data.get("evidence_scope") == "METADATA_ONLY_NOT_FORMAL_ADMISSION"
                      and guard.utc(data["created_utc"]) <= guard.now() and bool(data.get("volumes")),
                      "Original actual host storage-probe inventory required")
        for volume in data["volumes"]:
            guard.integer(volume.get("free_bytes"), "original physical free bytes")
        host = {"binding": binding, "original_inventory": data,
                "scope": "ORIGINAL_HOST_SNAPSHOT_RETAINED_NOT_CURRENT_CAPACITY_RECHECK"}
    for item in receipts.values():
        guard.require(inventory(item["trial"]) == item["files"], "Original trial file sizes changed during measurement")
    if snapshot_audit is not None:
        module.verify_current(context, plans["core"])
    for path, original in tuple(inputs.items()):
        actual = small_binding(path, {}, bag_metadata=original["bag_metadata"])
        guard.require(actual["sha256"] == original["sha256"], "Small evidence/source changed during measurement: " + path)
    summary = {"schema_version": 1, "kind": KIND, "created_utc": guard.now().isoformat(),
        "evidence_scope": "METADATA_AND_FILE_SIZE_ACCOUNTING_ONLY_NOT_ADMISSION", "planned_count": 28,
        "measured_count": len(receipts), "original_status_counts": dict(Counter(item["original_status"] for item in receipts.values())),
        "development_plans": bindings, "source_validation": sources, "tool_bindings": tools,
        "filesystem_free_snapshots": free,
        "original_physical_inventory": host, "small_input_bindings": inputs,
        "total_original_trial_bytes": sum(item["total_trial_bytes"] for item in receipts.values()),
        "receipts": [], "payload_content_reads": False, "capacity_admission_performed": False,
        "claim_boundary": "Size evidence keeps all 28 cells and original failures. Filesystem free amounts are separate observations, never summed as independent physical volumes. WSL ext4 free space cannot replace host-volume capacity. New source freezes/builds, future evaluations/replay/video/document/log deliveries and conservative temporary-growth margins still require explicit reservations in the separate storage budget and per-slot outer guard."}
    if snapshot_audit is not None:
        summary["source_snapshot_validation"] = context["summary"]
    output.mkdir(exist_ok=False)
    for name, receipt in receipts.items():
        guard.write_new(output / name, receipt)
        summary["receipts"].append(guard.file_binding(output / name))
    guard.write_new(output / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-development-plan", type=Path, required=True)
    parser.add_argument("--extension-development-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="One independent new directory under actual results")
    parser.add_argument("--physical-inventory", type=Path, help="Optional original storage-probe snapshot, retained with its actual sample time")
    parser.add_argument("--snapshot-audit-registry", type=Path, help="Explicit completed original safety4 registry; requires all four snapshot-audit options")
    parser.add_argument("--snapshot-audit-registry-sha256")
    parser.add_argument("--snapshot-audit-native-receipt", type=Path, help="Completed original native helper audit receipt, retained as prior evidence only")
    parser.add_argument("--snapshot-audit-native-receipt-sha256")
    args = parser.parse_args(argv)
    try:
        result = measure(args.core_development_plan, args.extension_development_plan, args.output,
                         physical_inventory=args.physical_inventory,
                         snapshot_audit_registry=args.snapshot_audit_registry,
                         snapshot_audit_registry_sha256=args.snapshot_audit_registry_sha256,
                         snapshot_audit_native_receipt=args.snapshot_audit_native_receipt,
                         snapshot_audit_native_receipt_sha256=args.snapshot_audit_native_receipt_sha256)
        print(json.dumps({"kind": KIND, "output": str(args.output.resolve()), "measured_count": result["measured_count"],
                          "capacity_admission_performed": False}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, ArithmeticError) as error:
        print(json.dumps({"kind": KIND, "result": "REFUSED_NOT_ADMISSION", "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
