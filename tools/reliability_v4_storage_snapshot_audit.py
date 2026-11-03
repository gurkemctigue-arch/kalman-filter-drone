"""Use saved native/safety audit evidence for size accounting, without payload reads.

This is an explicit metadata adapter for the existing storage collector. It
does not call the original helper's validate_contract/validate_snapshot: those
perform model hashing. Saved native validation is prior evidence, not a new
native, safety or model-content validation by this tool.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

AUDIT_ROOT = Path("/root/uav_tracking_snapshot_audit54_tools01")
NATIVE_SCRIPT = Path("/mnt/d/WSL/UAVHumble22-validation/snapshot_audit_native_integration01/audit_snapshot_contract_integration.py")
NATIVE_SCRIPT_SHA = "1062409c9ef2aee5c611831f5100db9ce081557570bd28859a057c7c00cec8cc"
NATIVE_RESULT = "NATIVE_CONTRACT_AND_FIRST3_SNAPSHOT_AUDIT_COMPLETE_FORMAL_DUAL_ROOT_VALIDATION_PENDING"
RECOVERY_SCRIPT = Path("/mnt/d/WSL/UAVHumble22-validation/safety54_symlink_recovery02.py")
RECOVERY_SCRIPT_SHA = "dda5af047eaa82c53e55260597c3643680c394fabab9cfc12c56dd15373a965c"
RECOVERY_DRIVER_SHA = "82c5ee395e81db0a15339149d8775cf3a8fe1c9fdce524e9e54cf2bc3d287e73"
RECOVERY_STATUS = "NATIVE_REPAIR_CONTRACT_AND_READ_ONLY_COMMAND_CONTRACT_COMPLETE_FRESH_SAFETY4_PENDING"
SCHEMA_SCRIPT = Path("/mnt/d/WSL/UAVHumble22-validation/safety54_schema_recovery03.py")
SCHEMA_SCRIPT_SHA = "a7c40c182f2101a90cd5a07b0e45b67116500ae60b4983095a6cbb86f5cb8984"
SCHEMA_DRIVER_SHA = "6f93e58d6281aa882c4b89273fcfaa1dc1897d9651174e2b947d82bd28d5c172"
SCHEMA_STATUS = "NATIVE_SCHEMA_REPAIR_CONTRACT_AND_READ_ONLY_DIAGNOSTIC_COMPLETE_FRESH_SAFETY4_PENDING"
TOOL_PINS = {
    "driver": ("run_reliability_v4_safety.py", "6d6d1b56d14866355c7d423d3eaaed420860f20190d59acdfa20b853b9f3073b"),
    "validator": ("reliability_v4_guard.py", "e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e"),
    "helper": ("reliability_v4_snapshot_audit.py", "9339fe72a67b36f987b81a20833953a50ca59302b4157a1230424e8145497ba6"),
    "registrar": ("reliability_v4_register.py", "fe2b37738ba07016dc1551abe273e5309e702b14df6e3d707b2788d3f3ef992c"),
}
SCOPE = "SAVED_NATIVE_AND_SAFETY_AUDIT_BINDINGS_CURRENT_TEXT_HASH_AND_ASSET_STAT_ONLY"
BOUNDARY = ("Original native helper validation is retained as prior saved evidence, not rerun. "
            "Current scanner-visible text is rehashed; model/other asset content is not revalidated. "
            "This is file-size accounting, not native/safety/formal admission or proof of historical imports.")


def safety_summary_bindings(plan, runner):
    """The original gate-builder bindings, using already checked pure helpers.

    Loading the builder itself would introduce its global runner import and
    sys.path mutation. These fields match its bindings(plan) dictionary.
    """
    result = {"flight_source_hashes": runner.flight_source_hashes(plan["source_hashes"]),
              "evaluation_source_hashes": runner.offline_source_hashes(plan["source_hashes"]),
              "model_hashes": plan["model_hashes"],
              "magnetic_runtime_manifest_sha256": plan["magnetic_runtime_binding"]["manifest_sha256"],
              "magnetic_library_registration_sha256": plan["magnetic_library_binding"]["registration_sha256"],
              "navigation_acceptance_sha256": runner.digest(plan["protocol"]["navigation_acceptance"])}
    for name in ("car_surface_recovery", "exclusive_navigation", "simulation_pacing"):
        if getattr(runner, name + "_declared")(plan["protocol"]):
            result[name + "_sha256"] = runner.digest(getattr(runner, name + "_summary")(plan["protocol"]))
    if runner.SUPERVISOR_STREAM_FIELD in plan["protocol"]:
        result["supervisor_stream_timing_sha256"] = runner.digest(runner.supervisor_stream_summary(plan["protocol"]))
    if runner.SPLIT_CLOCK_BRIDGE_FIELD in plan:
        result[runner.SPLIT_CLOCK_BRIDGE_FIELD] = runner.split_clock_bridge_setting(plan)
    return result


def prepare(registry_binding, native_binding, core, core_path, *, guard, bind, runner):
    """Require actual successful prior evidence; never synthesize a contract."""
    require = guard.require

    def named(path, *, data=True):
        path = Path(path)
        require(path.is_absolute() and path.is_file() and not path.is_symlink()
                and path.suffix.lower() == (".json" if data else ".py")
                and not any(part in {"rosbag", "rosbag_raw"} for part in path.parts)
                and path.stat().st_size <= 1024**2, "Named <=1 MiB audit metadata/text required")
        return path

    def bound(reference, *, data=True):
        require(isinstance(reference, dict) and set(reference) in ({"path", "sha256"}, {"path", "sha256", "bytes"})
                and isinstance(reference["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", reference["sha256"]),
                "Explicit audit path/SHA binding required")
        path = named(reference["path"], data=data)
        actual = bind(path)
        require(actual["path"] == str(path.resolve(strict=True)) and actual["sha256"] == reference["sha256"]
                and ("bytes" not in reference or type(reference["bytes"]) is int and reference["bytes"] == path.stat().st_size),
                "Saved audit binding changed")
        if not data:
            return actual, None
        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, "Duplicate audit JSON key")
                result[key] = value
            return result
        value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite audit JSON")))
        require(isinstance(value, dict), "Audit JSON object required")
        return actual, value

    registry_pin, registry = bound(registry_binding)
    native_pin, native = bound(native_binding)
    root = Path(core["frozen_root"]).resolve(strict=True)
    core_pin = bind(named(core_path))
    require(registry.get("kind") == "RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY"
            and registry.get("schema_version") == 1
            and registry.get("source_core_plan") == {**core_pin, "plan_sha256": core["plan_sha256"]},
            "Actual safety registry must bind this canonical core plan")
    contract_pin, contract = bound(registry.get("snapshot_audit_contract"))
    require(set(contract) == {"schema_version", "kind", "created_utc", "rule", "frozen_root", "audit_tool_root", "core_plan",
                              "freeze_report", "source_before", "source_after", "frozen_map", "import_isolation", "audit_tools",
                              "base_tools", "evidence_limitations"}
            and contract.get("kind") == "RELIABILITY_V4_FROZEN_SNAPSHOT_AUDIT_CONTRACT"
            and contract.get("schema_version") == 1
            and contract.get("rule") == "ORIGINAL_RUN_STAGE1_PY_SH_MSG_SCAN_PLUS_SELECTED_MODEL_AND_EXPLICIT_DDS"
            and contract.get("frozen_root") == str(root)
            and contract.get("audit_tool_root") == str(AUDIT_ROOT)
            and contract.get("core_plan") == {**core_pin, "plan_sha256": core["plan_sha256"]},
            "Original explicit native snapshot contract differs")
    require(native.get("schema_version") == 1
            and native.get("scope") == "ACTUAL_FIXED_TOOL_NATIVE_CONTRACT_AND_SNAPSHOT_AUDIT_ONLY"
            and native.get("result") == NATIVE_RESULT and type(native.get("exit_code")) is int and native["exit_code"] == 0
            and native.get("contract_creation_attempted") is True
            and native.get("mandatory_helper_hash_traversals_skipped") is False
            and native.get("helper_original_source_and_model_hashing_allowed_and_preserved") is True
            and native.get("contract") == contract_pin and native.get("contract_metadata") == contract
            and native.get("plan") == native.get("plan_after")
            and {key: native["plan"].get(key) for key in ("path", "sha256")} == core_pin,
            "Completed original native integration receipt required; preparation is insufficient")
    producer, _ = bound(native.get("self"), data=False)
    recovery = Path(native["self"]["path"]) == RECOVERY_SCRIPT and producer == {"path": str(RECOVERY_SCRIPT), "sha256": RECOVERY_SCRIPT_SHA}
    schema_recovery = Path(native["self"]["path"]) == SCHEMA_SCRIPT and producer == {"path": str(SCHEMA_SCRIPT), "sha256": SCHEMA_SCRIPT_SHA}
    require(recovery or schema_recovery or Path(native["self"]["path"]) == NATIVE_SCRIPT
            and producer == {"path": str(NATIVE_SCRIPT), "sha256": NATIVE_SCRIPT_SHA},
            "Reviewed original native integration producer differs")
    if recovery:
        require(native.get("kind") == "ACTUAL_NATIVE_SAFETY_SYMLINK_COMMAND_CONTRACT_REPAIR"
                and native.get("status") == RECOVERY_STATUS
                and native.get("physical_path_contract_diagnostic") == native.get("read_only_old_command_contract_result") == "PASS"
                and native.get("original_lexical_comparison_refusal_reproduced")
                    == "Safety command does not execute the bound frozen source/native evaluator"
                and native.get("formal_admission_created") is False and native.get("original_result_rewritten") is False
                and type(native.get("flights_started")) is int and native["flights_started"] == 0
                and all(native.get(name) is True for name in ("core_plan_unchanged", "original_failure_and_contract_unchanged",
                    "fixed_guard_helper_registrar_unchanged", "current_tool_bundle_unchanged_during_validation",
                    "frozen_metadata_unchanged_during_validation")), "Completed reviewed symlink-recovery native audit required")
    if schema_recovery:
        require(native.get("kind") == "ACTUAL_NATIVE_SAFETY_RESULT_SCHEMA_REPAIR" and native.get("status") == SCHEMA_STATUS
                and native.get("original_schema_keyerror_reproduced") == "KeyError: 'result'"
                and native.get("schema_specific_aggregation_diagnostic_result") == "PASS"
                and native.get("full_old_slot_reaudit_performed") is False
                and native.get("original_registry_not_revalidated_or_rewritten") is True
                and native.get("formal_admission_created") is False and native.get("original_result_rewritten") is False
                and type(native.get("flights_started")) is int and native["flights_started"] == 0
                and all(native.get(name) is True for name in ("core_plan_unchanged", "original_failure_and_contract_unchanged",
                    "fixed_guard_helper_registrar_unchanged", "current_tool_bundle_unchanged_during_validation",
                    "frozen_metadata_unchanged_during_validation")), "Completed reviewed schema-recovery native audit required")
        normalized, raw_keys = native.get("original_public_reader_results"), native.get("original_raw_report_keys")
        require(isinstance(normalized, dict) and set(normalized) == {"source_clock", "native_startup"}
                and isinstance(raw_keys, dict) and set(raw_keys) == {"source_clock", "native_startup", "specialized", "terminal_speed"},
                "Saved schema diagnostic report denominator differs")
        prior_directory = root / "results/reliability_v4_humble54_safety02_person_auto_unique_multi_seed004"
        for kind, filename in (("source_clock", "px4_source_clock_report.json"), ("native_startup", "native_startup_report.json")):
            item = normalized[kind]
            require(isinstance(item, dict) and item.get("kind") == kind
                    and item.get("result") == item.get("reported_verdict") == "PASS" and item.get("error") is None
                    and type(item.get("execution", {}).get("returncode")) is int and item["execution"]["returncode"] == 0
                    and item["execution"].get("error") is None, "Saved original normalized reader did not PASS")
            original_pin, original = bound({"path": item.get("report"), "sha256": item.get("report_sha256")})
            require(Path(original_pin["path"]) == (prior_directory / filename).resolve(strict=True)
                    and original.get("evaluation_status") == "PASS" and original.get(kind + "_pass") is True
                    and "result" not in original and raw_keys[kind] == sorted(original),
                    "Saved original reader schema/report binding differs")
        require(all(isinstance(raw_keys[kind], list) and "result" in raw_keys[kind] and "checks" in raw_keys[kind]
                    for kind in ("specialized", "terminal_speed")), "Saved specialist/tail raw-result schema differs")
    for flag in ("safety_registration_created", "formal_admission_or_plan_created", "formal_execution_authorized",
                 "formal_dual_root_integration_validated", "historical_flight_imports_proved", "runtime_root_edited",
                 "original_snapshots_edited", "bag_sidecar_or_telemetry_read_by_this_script"):
        require(native.get(flag) is False, "Native receipt scope/claim differs: " + flag)
    require(guard.utc(core["created_utc"]) <= guard.utc(contract["created_utc"])
            <= guard.utc(native["finished_utc"]) <= guard.utc(registry["created_utc"]) <= guard.now()
            and guard.utc(native["started_utc"]) <= guard.utc(contract["created_utc"]), "Saved audit chronology differs")
    require(native.get("bundle_before") == native.get("bundle_after"), "Original native tool bundle changed")
    tools = contract.get("audit_tools", {})
    require(set(tools) == set(TOOL_PINS), "Complete fixed original audit tool bindings required")
    for key, (name, expected) in TOOL_PINS.items():
        if schema_recovery and key == "driver":
            expected = SCHEMA_DRIVER_SHA
        elif recovery and key == "driver":
            expected = RECOVERY_DRIVER_SHA
        actual, _ = bound(tools[key], data=False)
        require(actual == {"path": str(AUDIT_ROOT / "tools" / name), "sha256": expected}, "Fixed audit tool path/bytes differ")
        prior = native["bundle_before"]["files"]["tools/" + name]
        require({name: prior.get(name) for name in ("path", "sha256")} == actual, "Prior native tool binding differs")
    require(registry.get("driver") == tools["driver"] and registry.get("validator") == tools["validator"],
            "Safety used another driver/guard")
    bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        helper = guard.import_file("storage_saved_snapshot_pure_helpers", tools["helper"]["path"])
    finally:
        sys.dont_write_bytecode = bytecode
    require(contract.get("evidence_limitations") == helper.LIMITATION, "Original import-evidence limitation changed")
    metadata, pins = {}, {}
    names = {"freeze_report": "source_integrity/source_frozen_integrity.json",
             "source_before": "source_integrity/source_before.json", "source_after": "source_integrity/source_after.json",
             "frozen_map": "source_integrity/frozen_actual.json", "import_isolation": "import_isolation.json"}
    require(native.get("freeze_metadata_before") == native.get("freeze_metadata_after"), "Prior original freeze metadata changed")
    for key, relative in names.items():
        pins[key], metadata[key] = bound(contract[key])
        require(Path(contract[key]["path"]) == (root / "results/freeze_validation" / relative).resolve(strict=True),
                "Original freeze evidence path substituted")
        prior = native["freeze_metadata_before"][relative]
        require({name: prior.get(name) for name in ("path", "sha256")} == pins[key], "Prior native freeze binding differs")
    report, entries = metadata["freeze_report"], metadata["frozen_map"].get("entries")
    require(report.get("status") == "PASS" and report.get("scope") == "RSYNC_FILTERED_SOURCE_PRE_POST_AND_COMPLETE_FROZEN_COPY_BYTES"
            and report.get("frozen") == str(root) and report.get("errors") == []
            and type(report.get("build_returncode")) is int and report["build_returncode"] == 0
            and report.get("copy_identical") is True and report.get("source_unchanged") is True
            and report.get("source_pre_post") == report.get("frozen_copy") == {"added": [], "changed": [], "missing": []}
            and isinstance(entries, dict) and bool(entries)
            and entries == metadata["source_before"].get("entries") == metadata["source_after"].get("entries")
            and metadata["frozen_map"].get("frozen") == str(root)
            and metadata["source_before"].get("source") == report.get("source") == metadata["source_after"].get("source")
            and guard.utc(report["created_utc"]) <= guard.utc(core["created_utc"]), "Original complete cold maps/report differ")
    require(pins["source_before"]["sha256"] == report["before"]["sha256"]
            and pins["source_after"]["sha256"] == report["maps"]["source_after.json"]["sha256"]
            and pins["frozen_map"]["sha256"] == report["maps"]["frozen_actual.json"]["sha256"]
            and all(report.get(name) == len(entries) for name in ("actual_frozen_entries", "actual_source_entries", "expected_entries")),
            "Original complete cold map digests/counts differ")
    for name in entries:
        helper.relative_name(name, guard)
    bases = contract["base_tools"]
    require(isinstance(bases, dict) and set(bases) == set(helper.BASE_NAMES), "Original frozen audit tool ancestry incomplete")
    for key, relative in helper.BASE_NAMES.items():
        actual, _ = bound(bases[key], data=False)
        require(actual == {"path": str(helper.source_file(root, relative, guard)), "sha256": entries[relative]["sha256"]},
                "Original frozen audit tool ancestry differs")
    # This specific pure helper only hashes the two canonical package .py
    # files and stats the generated Python import paths; it never reads models.
    helper.verify_import_receipt(metadata["import_isolation"], root, entries, guard)
    scanned = {name: row["sha256"] for name, row in entries.items() if helper.selected_source(name)}
    registered = {name: value for name, value in core["source_hashes"].items() if helper.selected_source(name)}
    require(all(scanned.get(name) == value for name, value in registered.items()), "Registered scanner sources differ from original map")
    extra = {name: value for name, value in scanned.items() if name not in core["source_hashes"]}
    context = {"helper": helper, "guard": guard, "bind": bind, "root": root, "entries": entries,
               "scanned": scanned, "extra": extra, "contract": contract_pin, "asset_stats": {},
               "summary": {"scope": SCOPE, "contract": contract_pin, "native_integration_receipt": native_pin,
                           "safety_registry": registry_pin, "original_freeze_bindings": pins,
                           "registered_scanner_count": len(registered), "original_extra_sources": extra,
                           "original_extra_count": len(extra), "model_content_revalidated": False,
                           "original_helper_validation_repeated": False, "claim_boundary": BOUNDARY}}
    verify_current(context, core)
    snapshots = native.get("snapshots", [])
    require([item.get("id") for item in snapshots] == ["person_stage1_velocity_seed004", "person_stage1_position_seed004", "person_stage2_crossing_seed004"],
            "Original native first-three denominator differs")
    first = snapshots[0]
    for item in snapshots:
        trial = next(t for t in core["trials"] if t["id"] == item["id"])
        original_pin, original = bound(item["original"])
        require(Path(original_pin["path"]) == (Path(trial["directory"]) / "configuration/source_sha256.json").resolve(strict=True)
                and original == {**scanned, **required_snapshot(context, core, trial)} and item.get("entries") == len(original),
                "Prior native original snapshot path/bytes/mapping differs")
    expected = required_snapshot(context, core, next(t for t in core["trials"] if t["id"] == first["id"]))
    require(native.get("expected_registered_snapshot_entries") == len(expected)
            and first.get("helper_validate_snapshot_called") is True
            and first.get("validation_basis") == "ACTUAL_UNMODIFIED_HELPER_VALIDATE_SNAPSHOT_CALL"
            and first.get("explicit_contract_validation") == audit_evidence(context, core, expected),
            "Actual original helper snapshot validation is missing/different")
    audit = Path(registry_pin["path"]).parent
    def saved(name):
        path = named(audit / name)
        pin = bind(path)
        return bound(pin)
    terminal_pin, terminal = saved("execution_terminal.json")
    facts_pin, facts = saved("slots_facts.json")
    validation_pin, validation = saved("development_guard_validation.json")
    owner_pin, owner = saved("owner_terminal.json")
    _, owner_state = saved("owner_state.json")
    require(terminal.get("status") == "COMPLETED" and terminal.get("returncode") == 0 and terminal.get("stop_reason") is None
            and terminal.get("planned_count") == terminal.get("attempted_count") == 4 and terminal.get("pending_count") == 0
            and terminal.get("cleanup") == {"residual_processes": []} and terminal.get("unclosed_started_ids") == []
            and terminal.get("registry") == facts.get("registry") == registry_pin
            and terminal.get("facts") == facts_pin and terminal.get("guard_validation") == validation_pin
            and facts.get("kind") == "RELIABILITY_V4_SAFETY_EXECUTION_FACTS" and facts.get("result") == "PASS"
            and facts.get("planned_count") == facts.get("attempted_count") == 4 and facts.get("pending_count") == 0
            and validation.get("result") == "PASS" and validation.get("error") is None
            and owner == owner_state and owner.get("status") == "COMPLETED" and owner.get("all_engineering_pass") is True
            and owner.get("registry") == registry_pin and owner.get("execution_terminal") == terminal_pin,
            "Actual saved four-safety lifecycle/validation did not complete")
    summary_pin, summary = bound(validation.get("summary"))
    require(Path(summary_pin["path"]) == audit / "development_validation_summary.json"
            and summary.get("kind") == "RELIABILITY_V4_FINAL_SAFETY_SUMMARY" and summary.get("result") == "PASS"
            and summary.get("evidence_scope") == "REAL_RECORDED_DEVELOPMENT_EVIDENCE"
            and summary.get("validation_scope") == "DEVELOPMENT_ONLY_NOT_FORMAL_ADMISSION"
            and summary.get("source_facts") == facts_pin and summary.get("slots") == facts["slots"]
            and summary.get("bindings") == safety_summary_bindings(core, runner)
            and guard.utc(registry["created_utc"]) <= guard.utc(facts["created_utc"])
            <= guard.utc(summary["created_utc"]) <= guard.utc(validation["finished_utc"])
            <= guard.utc(terminal["finished_utc"]) <= guard.now(), "Saved safety summary path/result/bindings/chronology differs")
    trials = registry.get("trials", [])
    require(len(trials) == len(terminal.get("slots", [])) == len(facts.get("slots", [])) == 4
            and {(t["target_class"], t["case"]) for t in trials} == {(cls, case) for cls in ("person", "car") for case in ("auto_unique_multi", "locked_ambiguity")},
            "Complete original four-safety denominator required")
    for trial, item, fact in zip(trials, terminal["slots"], facts["slots"]):
        row_pin, row = bound(item["terminal"])
        require(Path(row_pin["path"]) == audit / (trial["id"] + ".json") and row.get("trial") == trial
                and item.get("id") == fact.get("id") == trial["id"]
                and row.get("status") == item.get("status") == fact.get("result") == "PASS"
                and row.get("infrastructure_stop") is False and row.get("cleanup") == {"residual_processes": []}
                and fact == {**row["execution_facts"], "original_terminal": item["terminal"]}, "Original saved safety slot/fact differs")
        selected = {"model": core["protocol"]["resources"][trial["target_class"]]["model"]}
        expected = required_snapshot(context, core, selected)
        snapshot_pin, actual = bound(fact["evidence"]["source_snapshot"])
        require(Path(snapshot_pin["path"]) == (Path(trial["directory"]) / "configuration/source_sha256.json").resolve(strict=True)
                and actual == {**scanned, **expected} and row.get("source_snapshot_audit") == audit_evidence(context, core, expected),
                "Prior saved safety snapshot audit differs from complete original scanner")
    context["summary"].update(safety_execution_terminal=terminal_pin, safety_guard_validation=validation_pin,
                              safety_owner_terminal=owner_pin, safety_summary=summary_pin,
                              saved_four_safety_snapshots_checked=4)
    return context


def required_snapshot(context, plan, trial):
    helper, require = context["helper"], context["guard"].require
    expected = {name: value for name, value in plan["source_hashes"].items() if helper.selected_source(name)}
    for name in (trial["model"], "config/dds_runtime_humble22.json"):
        require(name in plan["source_hashes"], "Selected model/explicit DDS is not registered")
        expected[name] = plan["source_hashes"][name]
    return expected


def audit_evidence(context, plan, expected):
    helper = context["helper"]
    return {"result": "PASS", "mode": helper.KIND, "contract": context["contract"],
            "registered_count": len(expected), "original_extra_count": len(context["extra"]),
            "original_extra_sources": context["extra"],
            "historical_copy_comparisons": helper.historical_copy_comparisons(context["extra"], plan["source_hashes"]),
            "evidence_limitations": helper.LIMITATION}


def verify_current(context, core):
    """Current text hashes and asset stat only; no original full validator call."""
    root, helper, require = context["root"], context["helper"], context["guard"].require
    actual = {path.relative_to(root).as_posix() for folder in ("scripts", "uav_tracking", "ros2_ws/src")
              for path in (root / folder).rglob("*") if path.is_file() and path.suffix in {".py", ".sh", ".msg"}}
    require(actual == set(context["scanned"]), "Current original scanner name set changed")
    for name, digest in context["scanned"].items():
        path = helper.source_file(root, name, context["guard"])
        entry = context["entries"][name]
        require(entry.get("kind") == "file" and type(entry.get("bytes")) is int and path.stat().st_size == entry["bytes"]
                and context["bind"](path)["sha256"] == digest, "Current original scanner text changed: " + name)
    for name, digest in core["source_hashes"].items():
        path = helper.source_file(root, name, context["guard"])
        entry = context["entries"].get(name, {})
        stat = path.stat()
        require(entry.get("kind") == "file" and entry.get("sha256") == digest
                and type(entry.get("bytes")) is int and stat.st_size == entry["bytes"], "Registered source/asset original map/stat differs")
        if path.suffix == ".pt":
            current = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
            require(name not in context["asset_stats"] or context["asset_stats"][name] == current, "Model stat changed during size measurement")
            context["asset_stats"][name] = current


def snapshot_evidence(context, snapshot, plan, trial):
    expected = required_snapshot(context, plan, trial)
    context["guard"].require(snapshot == {**context["scanned"], **expected},
                             "Actual snapshot differs from exact original scanned sources plus registered model/DDS")
    return {**context["summary"], "snapshot_entries": len(snapshot), "registered_snapshot_entries": len(expected)}
