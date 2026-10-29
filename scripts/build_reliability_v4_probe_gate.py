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


def target_snapshot(path, *, extension):
    path, plan = read_plan(path, extension=extension)
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


def assemble(target, probe_paths, *, extension, registration_utc):
    """Reread every supplied terminal record; never choose passing slots."""
    if not probe_paths:
        raise ValueError("At least one explicit immutable probe plan is required")
    paths = [Path(path).resolve(strict=True) for path in probe_paths]
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate probe plan")
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
            entries = record.get("evaluations", [])
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
    checks = v4.EXTENSION_PROBE_CHECKS if extension else v4.PROBE_CHECKS
    flag = "ready_for_formal_condition_extensions" if extension else "ready_for_formal_reliability_v4"
    gate = {"schema_version": 2, "result": "PASS", flag: True,
            "evidence_scope": "ORCHESTRATION_FIXTURE_ONLY" if fixture_only else "IMMUTABLE_DEVELOPMENT_PROBE_EVIDENCE_NOT_FORMAL_RESULTS",
            "checks": {name: True for name in checks}, "bindings": bindings(target), "probe_slots": slots}
    if extension:
        gate["known_algorithm_failures"] = known_failures
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


def run(target_plan, probe_plans, output, *, registration_utc=None):
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
    gate, statuses = assemble(target, probe_plans, extension=extension, registration_utc=registration_utc)
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    gate = run(args.target_plan, args.probe_plan, args.output, registration_utc=args.registration_utc)
    print(json.dumps({"output": str(args.output.resolve()), "probe_slots": len(gate["probe_slots"]),
                      "evidence_scope": gate["evidence_scope"], "protocol_registration": "NOT_PROTOCOL_REGISTRATION"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
