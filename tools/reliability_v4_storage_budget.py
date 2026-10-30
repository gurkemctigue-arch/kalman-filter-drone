"""Assemble a complete development-based storage budget, without admission.

Only named small JSON/code files are read or hashed. Original bag/VHD bytes
are never opened; files listed by an existing size receipt are only statted.
The outer guard remains responsible for every real capacity/admission check.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

_SPEC = importlib.util.spec_from_file_location(
    "storage_budget_guard", Path(__file__).with_name("reliability_v4_guard.py"))
guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guard)

KIND = "RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION"
ASSUMPTIONS_KIND = "RELIABILITY_V4_STORAGE_ASSUMPTIONS_NOT_ADMISSION"
ARCHIVE_POLICY = "ext4_sqlite_close_standard_zstd_verified_native_read"


class MissingEvidence(guard.Refusal):
    def __init__(self, missing):
        self.missing = missing
        super().__init__("Complete 28-cell evidence is required; no storage object produced")


def finite(value, name, *, minimum=0.):
    try:
        valid = type(value) in {int, float} and math.isfinite(value) and value >= minimum
    except OverflowError:
        valid = False
    guard.require(valid, "Invalid finite assumption/measurement: " + name)
    return value


def explanation(value, name):
    guard.require(isinstance(value, str) and bool(value.strip()), "Explicit basis required: " + name)
    return value


def named_json(path, bindings):
    path = Path(path)
    guard.require(path.suffix.lower() == ".json", "Named JSON evidence required")
    binding = guard.file_binding(path)  # Rejects bag/VHD paths before opening.
    actual, data = guard.bound(binding)
    bindings[str(actual)] = binding["sha256"]
    return binding, data


def read_development_plan(path, label, bindings):
    binding, plan = named_json(path, bindings)
    groups = guard.GROUPS if label == "core" else guard.CONDITIONS
    guard.require(plan.get("schema_version") == 1
                  and plan.get("study_kind") == "POST_REPAIR_ENGINEERING_VALIDATION"
                  and plan.get("mode") == ("PROBE" if label == "core" else "EXTENSION_PROBE"),
                  "Actual development plan required: " + label)
    guard.require(plan.get("plan_sha256") == guard.sealed(plan, "plan_sha256"), "Development plan digest changed")
    guard.require(plan.get("selected_seeds") == [4]
                  and plan.get("selected_classes") == list(guard.CLASSES), "Canonical seed004/two-class plan required")
    selected = "selected_groups" if label == "core" else "selected_extension_conditions"
    guard.require(plan.get(selected) == list(groups), "Incomplete development groups: " + label)
    root = Path(plan["frozen_root"])
    results = Path(plan["results_root"]).resolve(strict=True)
    guard.require(root.is_absolute() and root.resolve(strict=True) == root
                  and (root / "results").resolve(strict=True) == results, "Development results/root binding changed")
    guard.require(Path(plan["output"]).resolve(strict=True) / "plan.json" == Path(binding["path"]), "Moved development plan")
    trials, cells = plan.get("trials", []), {}
    guard.require(len(trials) == 2 * len(groups), "Complete 12/16 development denominator required")
    identifiers = set()
    for trial in trials:
        condition = trial["group"] if label == "core" else trial["extension_condition"]
        key = (label, trial["target_class"], condition)
        guard.require(key not in cells and trial.get("seed") == 4, "Duplicate/noncanonical development cell")
        guard.require(trial["id"] not in identifiers
                      and re.fullmatch(r"[A-Za-z0-9_.-]+", trial["id"])
                      and re.fullmatch(r"[A-Za-z0-9_.-]+", trial["name"]), "Unsafe/duplicate trial identity")
        identifiers.add(trial["id"])
        directory = Path(trial["directory"])
        guard.require(directory.is_absolute() and directory.resolve().is_relative_to(results)
                      and directory.name == trial["name"], "Trial outside original development results")
        expected_duration = 75.
        guard.require(finite(trial.get("duration_s"), "registered duration", minimum=1.) == expected_duration,
                      f"Expected registered {label} {expected_duration:g}-second exposure")
        cells[key] = trial
    guard.require(set(cells) == {(label, cls, group) for cls in guard.CLASSES for group in groups}, "Missing development cell")
    return binding, plan, cells


def sample_paths(plan, trial, size_directory):
    directory = Path(trial["directory"])
    return {"terminal": Path(plan["output"]) / "slots" / (trial["id"] + ".json"),
            "size": size_directory / (trial["name"] + ".json"),
            "archive": directory / "bag_integrity.json", "summary": directory / "summary.json",
            "closure": directory / "recording_closure.json"}


def read_sample(key, plan, trial, paths, bindings):
    evidence = {name: named_json(path, bindings) for name, path in paths.items()}
    record = evidence["terminal"][1]
    guard.require(record.get("record_sha256") == guard.sealed(record, "record_sha256")
                  and record.get("plan_sha256") == plan["plan_sha256"]
                  and record.get("id") == trial["id"], "Changed/foreign terminal record")
    guard.require(record.get("status") in {"PASS", "FAIL", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING"}
                  and record.get("infrastructure_stop") is False
                  and record.get("execution_status") == "COMPLETED"
                  and type(record.get("flight_exit_code")) is int and record["flight_exit_code"] == 0,
                  "Incomplete/infrastructure development exposure")
    for name, relative in (("archive", "bag_integrity.json"), ("summary", "summary.json"),
                           ("closure", "recording_closure.json")):
        guard.require(record.get("artifact_hashes", {}).get(relative) == evidence[name][0]["sha256"],
                      "Named JSON differs from original terminal binding: " + relative)
    summary, closure = evidence["summary"][1], evidence["closure"][1]
    guard.require(summary.get("termination_reason") == "follow_duration_reached"
                  and closure.get("status") == "PASS", "Short/incomplete development recording cannot budget full exposure")
    start = finite(summary.get("follow_start_s"), "actual follow start")
    end_ns = guard.integer(closure["observations"][-1]["last_clock_ns"], "recorded final Clock", minimum=1)
    guard.require(end_ns >= math.ceil((start + trial["duration_s"]) * 1e9), "Recording does not span registered follow duration")
    sample, archive = evidence["size"][1], evidence["archive"][1]
    guard.require(sample.get("scope") == "FILE_SIZE_ACCOUNTING_ONLY_NO_VERDICT_CHANGE"
                  and sample.get("trial") == trial["directory"]
                  and isinstance(sample.get("files"), dict) and bool(sample["files"]), "Foreign/incomplete size receipt")
    observed = guard.integer(sample.get("total_trial_bytes"), "total trial bytes", minimum=1)
    guard.require(observed == sum(guard.integer(n, "receipt bytes") for n in sample["files"].values()), "Size receipt sum differs")
    directory = Path(trial["directory"])
    guard.require(guard.trial_bytes(directory, sample["files"]) == observed, "Recorded sizes changed")
    guard.require(all((directory / name).is_file() for name in sample["files"]), "Receipt names a non-file")
    guard.require(archive.get("status") == "PASS" and archive.get("policy") == ARCHIVE_POLICY
                  and archive.get("raw_validation", {}).get("status") == "PASS"
                  and archive.get("native_reader_validation", {}).get("full_stream_read") is True,
                  "Original native-validated archive required")
    raw_files = archive["raw_validation"].get("files", [])
    compressed = archive.get("compressed_files", [])
    guard.require(bool(raw_files) and bool(compressed)
                  and len({x["path"] for x in raw_files}) == len(raw_files)
                  and len({x["path"] for x in compressed}) == len(compressed), "Empty/duplicate archive size list")
    raw_bytes = sum(guard.integer(x.get("raw_bytes"), "raw bytes", minimum=1) for x in compressed)
    compressed_bytes = sum(guard.integer(x.get("bytes"), "compressed bytes", minimum=1) for x in compressed)
    guard.require(raw_bytes == sum(guard.integer(x.get("bytes"), "raw file bytes", minimum=1) for x in raw_files), "Raw/compressed byte correspondence differs")
    for item in compressed:
        relative = Path(item["path"])
        guard.require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe compressed path")
        expected = "rosbag/" + relative.as_posix()
        path = directory / "rosbag" / relative
        guard.require(sample["files"].get(expected) == item["bytes"] and path.is_file()
                      and not path.is_symlink() and path.resolve(strict=True).is_relative_to((directory / "rosbag").resolve(strict=True))
                      and path.stat().st_size == item["bytes"], "Compressed size differs; no bag contents read")
    return {"key": key, "trial": trial, "total_bytes": observed, "raw_bytes": raw_bytes,
            "compressed_bytes": compressed_bytes, "original_status": record["status"],
            "size_binding": evidence["size"][0], "archive_binding": evidence["archive"][0],
            "terminal_binding": evidence["terminal"][0]}


def storage_location(inventory, plans, backend):
    guard.require(inventory.get("schema_version") == 1
                  and inventory.get("kind") == "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY"
                  and inventory.get("evidence_scope") == "METADATA_ONLY_NOT_FORMAL_ADMISSION", "Original non-admission storage-probe inventory required")
    guard.require(guard.utc(inventory["created_utc"]) <= guard.now(), "Future storage inventory")
    entries = inventory.get("volumes", [])
    guard.require(bool(entries), "Actual physical volume inventory required")
    specifications, measurements, unique = [], {}, set()
    for item in sorted(entries, key=lambda x: x["mount"]):
        mount = Path(item["mount"])
        guard.require(mount.is_absolute(), "Absolute actual volume mount required")
        identifier = "drive_" + mount.name.upper()
        guard.require(identifier not in measurements and item["windows_volume_id"] not in unique, "Duplicate/aliased physical volume")
        specification = {"id": identifier, "mount": str(mount), "windows_volume_id": item["windows_volume_id"]}
        actual = backend.volume(specification)
        guard.require(actual["mount"] == str(mount) and actual["windows_volume_id"] == item["windows_volume_id"], "Actual volume identity changed")
        guard.integer(actual["free_bytes"], "current physical free bytes")
        specifications.append(specification)
        measurements[identifier] = actual
        unique.add(item["windows_volume_id"])
    def containing(path):
        matches = [s["id"] for s in specifications if path.is_relative_to(Path(s["mount"]).resolve(strict=True))]
        guard.require(len(matches) == 1, "Actual path has missing/ambiguous host volume")
        return matches[0]
    results = Path(plans["core"]["results_root"]).resolve(strict=True)
    declared_vhd = inventory["vhd_host"]
    vhd = Path(declared_vhd["path"]).resolve(strict=True)
    guard.require(vhd == backend.vhd_path(declared_vhd["distribution"]), "Registry-backed VHD path changed")
    result_volume, vhd_volume = containing(results), containing(vhd)
    guard.require(set(measurements) == {result_volume, vhd_volume}, "Inventory must contain exactly results/VHD host volumes")
    return specifications, measurements, result_volume, {"distribution": declared_vhd["distribution"],
            "path": str(vhd), "volume": vhd_volume}


def assumptions_contract(data, volumes):
    guard.require(data.get("schema_version") == 1 and data.get("kind") == ASSUMPTIONS_KIND
                  and not ({"status", "result", "registration_utc"} & set(data)), "Explicit planning assumptions, without registration/acceptance claims, required")
    explanation(data.get("basis"), "assumptions source")
    for name in ("persistent_growth_factor", "raw_growth_factor", "compressed_growth_factor"):
        finite(data.get(name), name, minimum=1.)
    for name in ("persistent_extra_bytes_by_volume", "temporary_extra_bytes_by_volume", "additional_remaining_bytes"):
        guard.bytes_map(data[name], volumes, name)
    explanation(data.get("persistent_basis"), "persistent growth")
    explanation(data.get("temporary_basis"), "temporary bound")
    explanation(data.get("additional_remaining_basis"), "additional tasks, including an explicit zero")
    deliveries = data.get("delivery_reservations", {})
    guard.require(set(deliveries) == set(guard.DELIVERIES), "Exactly five explicit remaining delivery budgets required")
    for purpose, value in deliveries.items():
        amounts = guard.bytes_map(value["bytes_by_volume"], volumes, purpose)
        guard.require(sum(amounts.values()) > 0, "Unbudgeted remaining delivery: " + purpose)
        explanation(value.get("basis"), purpose)


def assemble(core_path, extension_path, size_directory, inventory_path, assumptions_path, *, backend=None):
    """Return a budget proposal only; does not write, admit, or invoke a runner."""
    bindings, plans, cells, plan_bindings = {}, {}, {}, {}
    for label, path in (("core", core_path), ("extension", extension_path)):
        binding, plan, entries = read_development_plan(path, label, bindings)
        plans[label], plan_bindings[label] = plan, binding
        cells.update(entries)
    for name in ("frozen_root", "results_root", "source_hashes", "model_hashes"):
        guard.require(plans["core"].get(name) == plans["extension"].get(name)
                      and plans["core"].get(name), "Core/extension source/storage identity differs: " + name)
    guard.require(len({Path(trial["directory"]).resolve() for trial in cells.values()}) == 28,
                  "A physical trial cannot substitute for multiple development cells")
    size_directory = Path(size_directory).resolve(strict=True)
    results = Path(plans["core"]["results_root"]).resolve(strict=True)
    guard.require(size_directory.is_dir() and size_directory.is_relative_to(results), "Original project size-evidence directory required")
    missing, paths = [], {}
    for key, trial in sorted(cells.items()):
        paths[key] = sample_paths(plans[key[0]], trial, size_directory)
        for purpose, path in paths[key].items():
            if not path.is_file():
                missing.append({"matrix": key[0], "target_class": key[1], "condition": key[2],
                                "missing_evidence": purpose, "path": str(path)})
    if missing:
        raise MissingEvidence(missing)
    samples = [read_sample(key, plans[key[0]], trial, paths[key], bindings) for key, trial in sorted(cells.items())]
    inventory_binding, inventory = named_json(inventory_path, bindings)
    assumptions_binding, assumptions = named_json(assumptions_path, bindings)
    backend = backend or guard.NativeStorage()
    specifications, measurements, result_volume, vhd = storage_location(inventory, plans, backend)
    volumes = set(measurements)
    assumptions_contract(assumptions, volumes)
    margins = assumptions["temporary_extra_bytes_by_volume"]
    temporary, persistent, storage_cells = {v: 0 for v in volumes}, {v: 0 for v in volumes}, []
    for sample in samples:
        values = dict(assumptions["persistent_extra_bytes_by_volume"])
        values[result_volume] += math.ceil(sample["total_bytes"] * assumptions["persistent_growth_factor"])
        derived = (3 * math.ceil(sample["raw_bytes"] * assumptions["raw_growth_factor"])
                   + 2 * math.ceil(sample["compressed_bytes"] * assumptions["compressed_growth_factor"]))
        for volume in volumes:
            temporary[volume] = max(temporary[volume], derived + margins[volume])
            persistent[volume] += 10 * values[volume]
        storage_cells.append({"matrix": sample["key"][0], "target_class": sample["key"][1],
            "condition": sample["key"][2], "persistent_bytes_by_volume": values,
            "basis": f'{assumptions["persistent_basis"]}; ceil({sample["total_bytes"]} * {assumptions["persistent_growth_factor"]}) on results volume plus explicit per-volume extras',
            "development_size_evidence": sample["size_binding"], "archive_evidence": sample["archive_binding"]})
    storage = {"volumes": specifications, "results_volume": result_volume, "vhd_host": vhd,
        "temporary_peak_bytes": temporary,
        "temporary_bound_rule": {"revision": "three_raw_two_compressed_plus_margin_v1",
            "raw_growth_factor": assumptions["raw_growth_factor"], "compressed_growth_factor": assumptions["compressed_growth_factor"],
            "extra_bytes_by_volume": dict(margins), "basis": assumptions["temporary_basis"]},
        "delivery_reservations": assumptions["delivery_reservations"],
        "additional_remaining_bytes": assumptions["additional_remaining_bytes"], "cells": storage_cells}
    preview = {}
    for volume in sorted(volumes):
        fixed = assumptions["additional_remaining_bytes"][volume] + sum(
            entry["bytes_by_volume"][volume] for entry in assumptions["delivery_reservations"].values())
        reserve = max(guard.MIN_RESERVE, temporary[volume])
        required = persistent[volume] + fixed + reserve
        preview[volume] = {**measurements[volume], "full_280_persistent_bytes": persistent[volume],
            "remaining_build_delivery_bytes": fixed, "temporary_reserve_bytes": reserve,
            "required_bytes": required, "remaining_after_budget_bytes": measurements[volume]["free_bytes"] - required,
            "fits_declared_physical_budget": measurements[volume]["free_bytes"] >= required}
    logical = guard.integer(backend.logical_free(Path(plans["core"]["frozen_root"])), "ext4 logical free")
    for path, digest in bindings.items():
        guard.require(guard.sha(path) == digest, "Small input changed during assembly: " + path)
    return {"schema_version": 1, "kind": KIND, "created_utc": guard.now().isoformat(),
        "evidence_scope": "METADATA_BUDGET_ASSEMBLY_ONLY_NOT_RUNTIME_ACCEPTANCE", "admission_performed": False,
        "storage": storage, "storage_sha256": guard.canonical(storage),
        "provenance": {"development_plans": plan_bindings, "physical_inventory": inventory_binding,
            "assumptions": assumptions_binding, "assumptions_values": assumptions, "small_inputs_sha256": bindings,
            "tool": guard.file_binding(__file__), "guard_tool": guard.file_binding(guard.__file__),
            "original_development_statuses": [{"cell": list(s["key"]), "status": s["original_status"], "terminal": s["terminal_binding"]} for s in samples]},
        "capacity_preview": {"scope": "CURRENT_SNAPSHOT_FULL280_ASSUMPTION_BUDGET_NOT_ADMISSION",
            "volumes": preview, "ext4_logical_free_bytes": logical,
            "fits_declared_logical_budget": logical >= preview[vhd["volume"]]["required_bytes"], "scheduled_slots": 280},
        "limits": "Growth factors and the three-raw/two-compressed formula are explicit assumptions, not measured future maxima. The guard must revalidate final plans/gates/evidence and current host capacity before every slot. No bag/VHD contents read or hashed; no trial or registration changed."}


def require_independent_output(output, result):
    """Do not add a JSON to source/build trees or original evidence trees."""
    output = Path(output)
    lexical, actual = output.absolute(), output.resolve()
    plan_values = [guard.bound(binding)[1] for binding in result["provenance"]["development_plans"].values()]
    results = {Path(plan["results_root"]).resolve(strict=True) for plan in plan_values}
    source_roots = {Path(plan["frozen_root"]).resolve(strict=True) for plan in plan_values}
    source_roots.add(Path(__file__).resolve().parents[1])
    for root in source_roots:
        if lexical.is_relative_to(root):
            guard.require(lexical.is_relative_to(root / "results") and any(actual.is_relative_to(r) for r in results),
                          "Budget output must not add files to a source/build/install tree")
        if actual.is_relative_to(root):
            guard.require(any(actual.is_relative_to(r) for r in results), "Budget output resolves into a source/build/install tree")
    for plan in plan_values:
        protected = [Path(plan["output"]).resolve(strict=True)]
        protected += [Path(trial["directory"]).resolve(strict=True) for trial in plan["trials"]]
        guard.require(not any(actual.is_relative_to(p) for p in protected), "Budget output must not modify an original trial/plan matrix")
    for cell in result["storage"]["cells"]:
        parent = Path(cell["development_size_evidence"]["path"]).parent.resolve(strict=True)
        guard.require(not actual.is_relative_to(parent), "Budget output must not modify the original size-evidence directory")
    guard.require(str(actual) not in result["provenance"]["small_inputs_sha256"], "Output aliases original input evidence")
    if any(actual.is_relative_to(r) for r in results):
        guard.require(not actual.parent.exists(), "Use an independent new directory under actual results")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("core-development-plan", "extension-development-plan", "size-evidence-dir", "physical-inventory", "assumptions", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        guard.require(not args.output.exists() and not args.output.is_symlink()
                      and args.output.suffix.lower() == ".json"
                      and not ({"rosbag", "rosbag_raw"} & set(args.output.parts)), "New exclusive JSON output required")
        result = assemble(args.core_development_plan, args.extension_development_plan,
                          args.size_evidence_dir, args.physical_inventory, args.assumptions)
        require_independent_output(args.output, result)
        guard.write_new(args.output, result)
        print(json.dumps({"kind": KIND, "output": str(args.output.resolve()), "cells": 28,
                          "storage_sha256": result["storage_sha256"], "admission_performed": False}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, IndexError, ArithmeticError) as error:
        refusal = {"kind": KIND, "result": "REFUSED_NOT_ADMISSION", "reason": str(error), "output_created": False}
        if isinstance(error, MissingEvidence):
            refusal["missing"] = error.missing
        print(json.dumps(refusal, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
