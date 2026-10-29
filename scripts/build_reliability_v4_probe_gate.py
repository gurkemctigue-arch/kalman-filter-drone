"""Build a development gate from immutable PROBE evidence, without flying.

No protocol registration, bag reads, evaluator execution or formal planning.
Every supplied probe slot is retained; the existing gate validator is the
publication authority, not the generated Boolean readiness fields.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_reliability_v4 as v4

SCRIPT = "scripts/build_reliability_v4_probe_gate.py"
RUNNER = "scripts/run_reliability_v4.py"


def read_plan(path, *, extension):
    path = Path(path).resolve(strict=True)
    plan = v4.load(path)
    v4.validate_plan(plan, path)
    if plan.get("mode") != ("EXTENSION_PROBE" if extension else "PROBE"):
        raise ValueError("Only the matching development PROBE mode is allowed")
    return path, plan


def target_snapshot(path, *, extension, require_registered_navigation=True):
    path, plan = read_plan(path, extension=extension)
    if require_registered_navigation:
        v4.validate_navigation_gates(plan["protocol"].get("navigation_acceptance"))
    root = Path(plan["frozen_root"])
    if (v4.source_hashes(root) != plan["source_hashes"]
            or v4.sha(root / v4.PROTOCOL_PATH) != plan["protocol_sha256"]
            or v4.load(root / v4.PROTOCOL_PATH) != plan["protocol"]):
        raise ValueError("Target frozen source or navigation protocol changed")
    if extension:
        binding = plan["extension_protocol_binding"]
        if (v4.sha(root / v4.EXTENSION_PROTOCOL_PATH) != binding["sha256"]
                or v4.load(root / v4.EXTENSION_PROTOCOL_PATH) != binding["protocol"]):
            raise ValueError("Target frozen extension design changed")
    actual = {SCRIPT: v4.sha(__file__), RUNNER: v4.sha(v4.__file__)}
    if any(plan["source_hashes"].get(name) != value for name, value in actual.items()):
        raise ValueError("Generator and validator must match the target source snapshot")
    return path, plan, actual


def bindings(plan):
    return {
        "flight_source_hashes": v4.flight_source_hashes(plan["source_hashes"]),
        "evaluation_source_hashes": v4.offline_source_hashes(plan["source_hashes"]),
        "model_hashes": deepcopy(plan["model_hashes"]),
        "magnetic_runtime_manifest_sha256": plan["magnetic_runtime_binding"]["manifest_sha256"],
        "magnetic_library_registration_sha256": plan["magnetic_library_binding"]["registration_sha256"],
        "navigation_acceptance_sha256": v4.digest(plan["protocol"]["navigation_acceptance"]),
    }


def register_gimbal_reevaluations(target_plan, probe_plan, output):
    """Exclusively publish the six actual future commands, without bag reads."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Refusing to replace a prospective gimbal registration")
    # Diagnostic command registration is independent of prospective numeric
    # acceptance thresholds. Gate construction retains the strict default.
    _, target, _ = target_snapshot(target_plan, extension=False, require_registered_navigation=False)
    source_path, previous = read_plan(probe_plan, extension=False)
    if bindings(target)["flight_source_hashes"] != bindings(previous)["flight_source_hashes"]:
        raise ValueError("Gimbal reevaluation cannot change the flight-critical source map")
    selected = [trial for trial in previous["trials"] if trial["group"].startswith("stage3_")]
    if len(selected) != 6 or {(trial["target_class"], trial["group"]) for trial in selected} != {
            (cls, group) for cls in v4.CLASSES for group in ("stage3_midpoint", "stage3_active", "stage3_multi_active")}:
        raise ValueError("Registration requires the complete predetermined six-stage3 matrix")
    planned = []
    for trial in sorted(selected, key=lambda item:item["id"]):
        record = v4.record_path(previous, trial)
        saved = v4.load(record)
        if (saved.get("record_sha256") != v4.digest(saved, ("record_sha256",))
                or saved.get("plan_sha256") != previous["plan_sha256"] or saved.get("id") != trial["id"]
                or saved.get("execution_status") != "COMPLETED" or saved.get("infrastructure_stop") is not False
                or saved.get("flight_exit_code") != 0 or saved.get("status") not in v4.TERMINAL):
            raise ValueError("Registration requires six completed immutable original flights")
        original = next(spec for spec in trial["evaluations"] if spec["kind"] == "gimbal")
        report = Path(trial["directory"]) / "gimbal_terminal_audit_v4.json"
        if report.exists():
            raise FileExistsError("Prospective reevaluation output already exists: " + str(report))
        planned.append({"slot_id":trial["id"], "record_file_sha256":v4.sha(record),
            "original_report_sha256":v4.sha(original["report"]), "report":str(report),
            "command":v4.gimbal_reevaluation_command(target["frozen_root"], source_path, previous, trial, report)})
    registration = {"schema_version":1,"kind":"RELIABILITY_V4_SIX_STAGE3_GIMBAL_REEVALUATION_REGISTRATION",
        "created_utc":v4.utc_now(), "source_plan":{"path":str(source_path),"sha256":v4.sha(source_path),"plan_sha256":previous["plan_sha256"]},
        "predetermined_gimbal_slots":[item["slot_id"] for item in planned],
        "evaluation_source_hashes":v4.offline_source_hashes(target["source_hashes"]), "planned_evaluations":planned}
    v4.write_new(output, registration)
    return registration


def read_evaluation_overrides_manifest(path, target, probe_paths, *, extension):
    """Explicit six-slot gimbal reevaluation; original records stay immutable."""
    if path is None:
        return {}, None
    if extension:
        raise ValueError("The six-stage3 gimbal override manifest is core-only")
    path = Path(path).resolve(strict=True)
    manifest = v4.load(path)
    if (manifest.get("schema_version") != 1
            or manifest.get("kind") != "RELIABILITY_V4_SIX_STAGE3_GIMBAL_REEVALUATIONS"
            or manifest.get("evaluation_source_hashes") != v4.offline_source_hashes(target["source_hashes"])):
        raise ValueError("Invalid gimbal override manifest/evaluation-source binding")
    source = manifest.get("source_plan", {})
    source_path = Path(source["path"]).resolve(strict=True)
    if source_path not in {Path(item).resolve(strict=True) for item in probe_paths}:
        raise ValueError("Override source plan is not an explicitly supplied probe plan")
    _, previous = read_plan(source_path, extension=False)
    if source != {"path":str(source_path), "sha256":v4.sha(source_path), "plan_sha256":previous["plan_sha256"]}:
        raise ValueError("Override original plan SHA binding differs")
    expected = sorted(trial["id"] for trial in previous["trials"] if trial["group"].startswith("stage3_"))
    matrix = {(trial["target_class"], trial["group"]) for trial in previous["trials"] if trial["id"] in expected}
    if len(expected) != 6 or matrix != {(cls, group) for cls in v4.CLASSES for group in ("stage3_midpoint", "stage3_active", "stage3_multi_active")}:
        raise ValueError("Gimbal overrides require the predetermined complete six-stage3 matrix")
    if manifest.get("predetermined_gimbal_slots") != expected:
        raise ValueError("Gimbal override manifest must include all six predetermined slots")
    registered = v4.utc_timestamp(manifest.get("registered_utc"))
    created = v4.utc_timestamp(manifest.get("created_utc"))
    if created > v4.utc_timestamp(v4.utc_now()) or registered > created:
        raise ValueError("Invalid prospective gimbal reevaluation chronology")
    registration = manifest.get("prospective_registration", {})
    registration_path = Path(registration.get("path", ""))
    if (not registration_path.is_file() or v4.sha(registration_path) != registration.get("sha256")
            or registration_path.resolve() == path):
        raise ValueError("Missing separate prospective six-gimbal registration file/SHA")
    registered_evidence = v4.load(registration_path)
    if (registered_evidence.get("schema_version") != 1
            or registered_evidence.get("kind") != "RELIABILITY_V4_SIX_STAGE3_GIMBAL_REEVALUATION_REGISTRATION"
            or registered_evidence.get("created_utc") != manifest.get("registered_utc")
            or registered_evidence.get("source_plan") != source
            or registered_evidence.get("predetermined_gimbal_slots") != expected
            or registered_evidence.get("evaluation_source_hashes") != manifest["evaluation_source_hashes"]):
        raise ValueError("Prospective six-gimbal registration content/source binding differs")
    slots = manifest.get("slots")
    if not isinstance(slots, list) or sorted(item.get("slot_id", "") for item in slots) != expected:
        raise ValueError("All six gimbal slots must be reevaluated without selecting failures")
    planned = registered_evidence.get("planned_evaluations", [])
    if (not isinstance(planned, list) or sorted(item.get("slot_id", "") for item in planned) != expected):
        raise ValueError("Prospective registration must bind all six actual future commands")
    overrides = {}
    for item in slots:
        trial = next(trial for trial in previous["trials"] if trial["id"] == item["slot_id"])
        record_path = v4.record_path(previous, trial)
        if item.get("record_file_sha256") != v4.sha(record_path):
            raise ValueError("Override immutable record SHA differs")
        entries = item.get("evaluation_overrides", [])
        if len(entries) != 1 or entries[0].get("kind") != "gimbal":
            raise ValueError("Six-stage3 manifest supports exactly one gimbal reevaluation per slot")
        override = entries[0]
        spec = next(spec for spec in trial["evaluations"] if spec["kind"] == "gimbal")
        if override.get("original_report_sha256") != v4.sha(spec["report"]):
            raise ValueError("Override original report SHA differs")
        if Path(override.get("evaluation_root", "")).resolve() != Path(target["frozen_root"]).resolve():
            raise ValueError("Override evaluator must use the target frozen source")
        report = Path(override["report"])
        if (not report.is_file() or report.resolve() == Path(spec["report"]).resolve()
                or report.parent.resolve() != Path(trial["directory"]).resolve()
                or v4.sha(report) != override.get("report_sha256")):
            raise ValueError("Override must bind a new report while preserving the original")
        execution = override.get("execution", {})
        registered_slot = next(item for item in planned if item["slot_id"] == trial["id"])
        expected_registration = {"slot_id":trial["id"], "record_file_sha256":item["record_file_sha256"],
            "original_report_sha256":override["original_report_sha256"], "report":override["report"],
            "command":execution.get("command")}
        if registered_slot != expected_registration:
            raise ValueError("Actual reevaluation command/original SHA differs from prospective registration")
        start, finish = v4.utc_timestamp(execution.get("started_utc")), v4.utc_timestamp(execution.get("finished_utc"))
        log = Path(execution.get("log", ""))
        if (not registered <= start <= finish <= created or execution.get("returncode") not in {0, 2}
                or execution.get("error") is not None or not isinstance(execution.get("command"), list)
                or not log.is_file() or v4.sha(log) != execution.get("log_sha256")):
            raise ValueError("Override actual command/UTC/exit/log SHA evidence differs")
        overrides[(str(source_path), trial["id"])] = deepcopy(entries)
    return overrides, {"path":str(path), "sha256":v4.sha(path), "manifest":manifest}


def assemble(target, probe_paths, *, extension, registration_utc, overrides_manifest=None):
    """Reread every supplied terminal record; never choose passing slots."""
    if not probe_paths:
        raise ValueError("At least one explicit immutable probe plan is required")
    paths = [Path(path).resolve(strict=True) for path in probe_paths]
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate probe plan")
    overrides, manifest_binding = read_evaluation_overrides_manifest(overrides_manifest, target, paths, extension=extension)
    cutoff = None
    if extension:
        cutoff = v4.utc_timestamp(registration_utc)
        if cutoff > v4.utc_timestamp(v4.utc_now()):
            raise ValueError("Extension verification cutoff cannot be in the future")
    elif registration_utc is not None:
        raise ValueError("Core gates do not take a registration cutoff")
    slots, known_failures, statuses = [], [], Counter()
    fixture_only = target["magnetic_runtime_binding"]["manifest"].get("evidence_scope") == "ORCHESTRATION_FIXTURE_ONLY"
    for path in paths:
        path, previous = read_plan(path, extension=extension)
        fixture_only |= previous["magnetic_runtime_binding"]["manifest"].get("evidence_scope") == "ORCHESTRATION_FIXTURE_ONLY"
        records = v4.read_slots(previous)
        evaluation_plan = deepcopy(previous)
        evaluation_plan["source_hashes"] = target["source_hashes"]
        evaluation_plan["protocol"]["navigation_acceptance"] = target["protocol"]["navigation_acceptance"]
        for original in previous["trials"]:
            record = records[original["id"]]
            statuses[record["status"]] += 1
            if (record.get("status") not in v4.TERMINAL or record.get("infrastructure_stop") is not False
                    or record.get("execution_status") != "COMPLETED" or record.get("flight_exit_code") != 0):
                raise ValueError("Incomplete immutable probe slot: " + original["id"])
            if extension and v4.utc_timestamp(record.get("finished_utc")) >= cutoff:
                raise ValueError("Verification cutoff must follow every actual development record")
            trial = deepcopy(original)
            for spec in trial["evaluations"]:
                spec["evaluation_root"] = previous["frozen_root"]
            flight = next((entry for entry in record.get("commands", []) if entry.get("kind") == "flight"), {})
            entries = deepcopy(record.get("evaluations", []))
            slot_overrides = overrides.get((str(path), trial["id"]), [])
            for override in slot_overrides:
                spec = next(spec for spec in trial["evaluations"] if spec["kind"] == override["kind"])
                spec.update(report=override["report"], evaluation_root=override["evaluation_root"],
                            command=override["execution"]["command"])
                checked = v4.read_evaluation(spec, override["execution"], evaluation_plan)
                entries = [entry for entry in entries if entry.get("kind") != override["kind"]] + [checked]
            if extension:
                failures = v4.extension_algorithm_failures(evaluation_plan, trial, flight, entries)
                if failures:
                    known_failures.append({"plan_path": str(path), "slot_id": trial["id"], "failures": failures})
            else:
                verdict, evidence = v4.engineering_verdict(evaluation_plan, trial, flight, entries)
                if verdict != "PASS":
                    raise ValueError("Independent core acceptance did not PASS: " + trial["id"] + " " + str(evidence))
            slots.append({"plan_path": str(path), "plan_file_sha256": v4.sha(path), "slot_id": trial["id"],
                          "record_file_sha256": v4.sha(v4.record_path(previous, original))})
            if slot_overrides:
                slots[-1]["evaluation_overrides"] = slot_overrides
    checks = v4.EXTENSION_PROBE_CHECKS if extension else v4.PROBE_CHECKS
    flag = "ready_for_formal_condition_extensions" if extension else "ready_for_formal_reliability_v4"
    gate = {"schema_version": 2, "result": "PASS", flag: True,
            "evidence_scope": "ORCHESTRATION_FIXTURE_ONLY" if fixture_only else "IMMUTABLE_DEVELOPMENT_PROBE_EVIDENCE_NOT_FORMAL_RESULTS",
            "checks": {name: True for name in checks}, "bindings": bindings(target), "probe_slots": slots}
    if extension:
        gate["known_algorithm_failures"] = known_failures
    if manifest_binding is not None:
        gate["evaluation_overrides_manifest"] = manifest_binding
    return gate, dict(statuses)


def verification_context(target, artifact, gate, *, extension, registration_utc):
    context = deepcopy(target)
    binding = {"path": str(artifact), "sha256": v4.sha(artifact), "evidence": gate}
    if extension:
        protocol = context["extension_protocol_binding"]["protocol"]
        # A temporary validator cutoff only. No protocol or plan is written,
        # and no REGISTERED status is supplied or changed here.
        protocol["registration_utc"] = registration_utc
        protocol["development_readiness"] = binding
    else:
        context["development_probe_gate"] = binding
    return context


def run(target_plan, probe_plans, output, *, registration_utc=None, overrides_manifest=None):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Refusing to replace a development gate: " + str(output))
    target_path = Path(target_plan).resolve(strict=True)
    mode = v4.load(target_path).get("mode")
    extension = mode == "EXTENSION_PROBE"
    target_path, target, implementation = target_snapshot(target_path, extension=extension)
    source_root = Path(target["frozen_root"]).resolve()
    if (output.suffix.lower() in v4.HASH_SUFFIXES
            and any(output.is_relative_to(source_root / folder) for folder in v4.HASH_FOLDERS)):
        raise ValueError("Gate output must not change the target frozen source inputs")
    target_sha = v4.sha(target_path)
    gate, statuses = assemble(target, probe_plans, extension=extension, registration_utc=registration_utc,
                              overrides_manifest=overrides_manifest)
    gate["generation"] = {
        "generated_utc": v4.utc_now(), "target_plan_path": str(target_path),
        "target_plan_file_sha256": target_sha, "target_plan_sha256": target["plan_sha256"],
        "implementation_source_hashes": implementation, "source_terminal_status_counts": statuses,
        "publication_rule": "Existing validate_probe_gate must pass on the actual temporary artifact before exclusive publication",
        "protocol_registration": "NOT_PROTOCOL_REGISTRATION",
        "extension_verification_cutoff_utc": registration_utc if extension else None,
        "claim_boundary": "Development readiness only; no formal plan, threshold registration, flight or evaluator is run. Original failures and all supplied slots remain.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix="." + output.name + ".", suffix=".validation.json", dir=output.parent)
        temporary = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(gate, indent=2, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        context = verification_context(target, temporary, gate, extension=extension, registration_utc=registration_utc)
        v4.validate_probe_gate(context, extensions=extension)
        if v4.sha(target_path) != target_sha:
            raise ValueError("Target plan changed during gate validation")
        # Recheck live target inputs before publishing; this never rewrites
        # the original snapshot or calls the external runtime verifier.
        target_snapshot(target_path, extension=extension)
        v4.write_new(output, gate)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return gate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-plan", type=Path, required=True, help="Matching final-source PROBE or EXTENSION_PROBE snapshot with REGISTERED navigation gates")
    parser.add_argument("--probe-plan", type=Path, action="append", required=True, help="Immutable evidence plan; repeat to include every slot from multiple plans")
    parser.add_argument("--registration-utc", help="Extension only: explicit current/past UTC cutoff used solely for temporary validation, never protocol registration")
    parser.add_argument("--evaluation-overrides-manifest", type=Path, help="Explicit prospectively fixed six-stage3 offline gimbal reevaluations with actual execution and original-evidence SHA bindings")
    parser.add_argument("--register-gimbal-reevaluations", action="store_true", help="Exclusively register all six future gimbal commands before execution; writes registration only")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.register_gimbal_reevaluations:
        if len(args.probe_plan) != 1 or args.registration_utc is not None or args.evaluation_overrides_manifest is not None:
            parser.error("Gimbal registration takes exactly one source --probe-plan and no completion manifest/cutoff")
        registration = register_gimbal_reevaluations(args.target_plan, args.probe_plan[0], args.output)
        print(json.dumps({"output":str(args.output.resolve()),"registered_gimbal_slots":registration["predetermined_gimbal_slots"],
                          "executed_evaluations":0}, indent=2))
        return 0
    gate = run(args.target_plan, args.probe_plan, args.output, registration_utc=args.registration_utc,
               overrides_manifest=args.evaluation_overrides_manifest)
    print(json.dumps({"output": str(args.output.resolve()), "probe_slots": len(gate["probe_slots"]),
                      "evidence_scope": gate["evidence_scope"], "protocol_registration": "NOT_PROTOCOL_REGISTRATION"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
