"""Assemble three new registration artifacts; never publish protocols or fly.

Supported: validated four-safety summary, a fully bound replay configuration
candidate, and a final admission manifest checked by the existing guard.
Canonical planning files, formal plans, bags and runner state are never written.
See planning/reliability-v4-registration-tool.md for the required manual boundary.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

_guard_spec = importlib.util.spec_from_file_location(
    "reliability_v4_registration_guard", Path(__file__).with_name("reliability_v4_guard.py"))
guard = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(guard)

REPLAY_PATH = "planning/reliability-v4-estimator-replay-preregistration.json"
PARAMETERS = {"R0_sensor_world_m2_by_class", "Q_model_and_parameters",
              "P0_matrix_and_initial_velocity_policy", "ema_alpha",
              "common_gate_R_and_initialization_policy",
              "common_support_truth_coverage_requirement"}
REQUEST_FIELDS = {"schema_version", "kind", "final_root", "plans", "registrations",
                  "calibration", "safety", "state_directory", "storage"}


def read_bound(path):
    binding = guard.file_binding(path)
    actual, data = guard.bound(binding)
    guard.no_fixture(data, str(actual))
    return actual, data, binding


def canonical_development(path, runtime):
    actual, plan, binding = read_bound(path)
    guard.require(plan.get("mode") == "PROBE" and plan.get("selected_seeds") == [4]
                  and plan.get("selected_classes") == list(guard.CLASSES)
                  and plan.get("selected_groups") == list(guard.GROUPS)
                  and len(plan.get("trials", [])) == 12,
                  "Exactly the canonical seed004 two-class/six-group development plan is required")
    runtime.v4.validate_plan(plan, actual)
    return actual, plan, binding


def gate_context(target_path, gate_path):
    target_path, target, _ = read_bound(target_path)
    guard.require(target.get("mode") == "PROBE", "Safety target must be an unexecuted PROBE snapshot")
    root = Path(target["frozen_root"]).resolve(strict=True)
    runtime = guard.load_runtime(root, target)
    runtime.v4.validate_plan(target, target_path)
    runtime.v4.verify_sources(target)
    rows = runtime.v4.read_slots(target)
    guard.require(all(row["status"] == "PENDING" for row in rows.values()),
                  "Gate target snapshots must never be flown")
    gate_path, gate, gate_binding = read_bound(gate_path)
    context_plan = deepcopy(target)
    context_plan["development_probe_gate"] = {**gate_binding, "evidence": gate}
    runtime.v4.validate_probe_gate(context_plan)
    paths = {item["plan_path"] for item in gate.get("probe_slots", [])}
    guard.require(len(paths) == 1 and len(gate["probe_slots"]) == 12,
                  "Safety summary must bind the one complete canonical12 gate")
    development_path, development, _ = canonical_development(next(iter(paths)), runtime)
    return runtime, SimpleNamespace(root=root, core=context_plan,
        development_path=development_path, development=development,
        gate_bindings=gate["bindings"])


def assemble_safety(target_path, gate_path, facts_path, validation_path):
    runtime, context = gate_context(target_path, gate_path)
    _, facts, facts_binding = read_bound(facts_path)
    guard.require(facts.get("schema_version") == 1
                  and facts.get("kind") == "RELIABILITY_V4_SAFETY_EXECUTION_FACTS"
                  and facts.get("evidence_scope") == "REAL_RECORDED_DEVELOPMENT_EVIDENCE"
                  and facts.get("result") == "PASS" and facts.get("planned_count") == 4
                  and facts.get("attempted_count") == 4 and facts.get("pending_count") == 0,
                  "All four actual safety attempts must already pass; no synthetic result is permitted")
    _, registry = guard.bound(facts["registry"])
    guard.require(registry.get("schema_version") == 1
                  and registry.get("kind") == "RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY",
                  "Original prospective safety execution registry required")
    source = registry["source_core_plan"]
    dev_path, dev = guard.bound({key: source[key] for key in ("path", "sha256")})
    guard.require(dev_path == context.development_path and dev == context.development
                  and source["plan_sha256"] == dev["plan_sha256"], "Safety registry binds another canonical plan")
    guard.require(registry["flight_source_hashes"] == context.gate_bindings["flight_source_hashes"],
                  "Safety registry flight sources differ from the actual gate")
    card = guard.bound(registry["execution_card"], json_data=False)
    tail = guard.bound(registry["tail_script"], json_data=False)
    guard.bound(registry["driver"], json_data=False)
    anchor = 'tracking_tail_speed() {\n'
    source = card.read_text(encoding="utf-8")
    guard.require(source.count(anchor) == 1, "Safety card must contain the one original tail function")
    expected_tail = source.split(anchor, 1)[1].split("<<'PY'\n", 1)[1].split('\nPY\n}', 1)[0] + '\n'
    guard.require(tail.read_bytes() == expected_tail.encode("utf-8"), "Safety tail code differs from the frozen execution card")
    expected_ids = {f"{cls}_{case}_seed004" for cls in guard.CLASSES for case in guard.SAFETY_CASES}
    registered = {trial["id"]: trial for trial in registry["trials"]}
    guard.require(len(registry["trials"]) == 4 and set(registered) == expected_ids
                  and len(facts["slots"]) == 4 and {slot["id"] for slot in facts["slots"]} == expected_ids,
                  "All four original safety slots must be retained exactly once")
    required_artifacts = {"run_config", "source_snapshot", "runtime_parameters", "bag_integrity",
        "recording_closure", "process_exit_codes", "source_clock", "native_startup", "specialized",
        "terminal_speed", "rendering", "magnetic"}
    for slot in facts["slots"]:
        trial = registered[slot["id"]]
        directory = Path(slot["trial_directory"]).resolve(strict=True)
        guard.require(slot.get("result") == "PASS" and slot.get("seed") == 4
                      and slot["id"] == f'{slot["target_class"]}_{slot["case"]}_seed004'
                      and directory == Path(trial["directory"]).resolve(strict=True),
                      "Safety slot identity/result/directory differs from its registry")
        guard.require(required_artifacts <= slot["evidence"].keys(), "Safety artifact bindings are incomplete")
        artifacts = {}
        for name, binding in slot["evidence"].items():
            path = guard.bound(binding, json_data=False)
            guard.require(path.is_relative_to(directory), "Safety artifact is outside its original trial")
            if path.suffix.lower() not in {".yaml", ".yml"}:
                artifacts[name] = (path, guard.load(path))
        executions = slot["executions"]
        guard.require(set(executions) == {"flight", "source_clock", "native_startup", "specialized", "terminal_speed"},
                      "Exactly five actual safety executions are required")
        for execution in executions.values():
            guard.validate_execution(execution, after=guard.utc(registry["created_utc"]))
            guard.require(guard.utc(execution["finished_utc"]) <= guard.utc(facts["created_utc"]),
                          "Safety facts precede an actual execution finish")
        guard.require(executions["flight"]["argv"] == trial["flight_argv"], "Safety flight argv differs from its prospective registry")
        registered_rtf = context.core["protocol"]["real_time_factor"]
        parameters_path = guard.bound(slot["evidence"]["runtime_parameters"], json_data=False)
        import yaml
        parameters = yaml.safe_load(parameters_path.read_text(encoding="utf-8"))
        guard.require(artifacts["run_config"][1].get("real_time_factor") == registered_rtf
                      and float(guard.option(executions["flight"]["argv"], "--real-time-factor")) == registered_rtf
                      and artifacts["run_config"][1].get("wall_timeout") == context.core["protocol"]["flight_wall_timeout_s"]
                      and float(guard.option(executions["flight"]["argv"], "--wall-timeout")) == context.core["protocol"]["flight_wall_timeout_s"]
                      and isinstance(parameters, dict)
                      and parameters.get("uav_tracking_flight_supervisor", {}).get("ros__parameters", {}).get(
                          "requested_simulation_real_time_factor") == registered_rtf,
                      "Safety actual simulation resources differ from frozen core protocol")
        guard.require(executions["terminal_speed"]["code_script"] == registry["tail_script"],
                      "Safety terminal execution binds a different independent script")
        for kind in ("source_clock", "native_startup"):
            spec = {"kind": kind,
                "script": "scripts/evaluate_px4_source_clock.py" if kind == "source_clock" else "scripts/evaluate_native_startup.py",
                "report": str(artifacts[kind][0]), "evaluation_root": context.development["frozen_root"]}
            execution = {**executions[kind], "log": executions[kind]["log"]["path"]}
            guard.require(runtime.v4.read_evaluation(spec, execution, context.core)["result"] == "PASS",
                          "Original source/native safety report did not pass")
        specialized, speed = artifacts["specialized"][1], artifacts["terminal_speed"][1]
        guard.require(specialized.get("result") == "PASS" and speed.get("result") == "PASS"
                      and Path(specialized.get("inputs", {}).get("bag", "")).resolve() == directory / "rosbag"
                      and Path(speed.get("trial", "")).resolve() == directory,
                      "Safety specialty/tail reports do not pass for the original recording")
        guard.all_checks(specialized, guard.AUTO_CHECKS if slot["case"] == "auto_unique_multi" else guard.LOCKED_CHECKS,
                         "safety specialty")
        guard.all_checks(speed, guard.SPEED_CHECKS, "terminal speed")
        closure = artifacts["recording_closure"][1]
        guard.require(artifacts["bag_integrity"][1].get("status") == "PASS"
                      and closure.get("status") == "PASS", "Safety recording closure/archive did not pass")
        final = closure["observations"][-1]["last_clock_ns"] / 1e9
        guard.require(speed["interval"]["end_s"] - speed["interval"]["start_s"] >= 5.2 - 1e-9
                      and abs(speed["interval"]["end_s"] - final) < 1e-9,
                      "Safety physical hover tail must cover the full original 5.2 seconds through final Clock")
    stamp = guard.now().isoformat()
    guard.require(guard.utc(registry["created_utc"]) <= guard.utc(facts["created_utc"]) <= guard.utc(stamp),
                  "Safety registry/facts must actually precede this assembly")
    summary = {"schema_version": 1, "kind": "RELIABILITY_V4_FINAL_SAFETY_SUMMARY",
        "result": facts["result"], "evidence_scope": "REAL_RECORDED_DEVELOPMENT_EVIDENCE",
        "created_utc": stamp, "bindings": deepcopy(context.gate_bindings),
        "source_facts": facts_binding, "slots": deepcopy(facts["slots"])}
    guard.write_new(validation_path, summary)
    # validate_safety requires real subsequent protocol registration times.
    # Do not manufacture those times while constructing this earlier artifact.
    # seal calls the entire guard with the actual registrations; this candidate
    # alone can never replace that full semantic/time/source safety validation.
    return {"claim": "BOUND_SAFETY_SUMMARY_CANDIDATE_PENDING_COMPLETE_GUARD_SAFETY_VALIDATION",
            "protocol_registration": "NOT_PERFORMED; both actual registrations must follow this summary",
            "full_safety_validation": "PENDING_SEAL_WITH_REAL_PROTOCOL_REGISTRATIONS",
            "original_slots_unchanged": summary["slots"] == facts["slots"]}


def candidate_artifacts(candidate_path, candidate, runtime, root):
    artifacts = {}

    def pin(binding):
        path = guard.bound(binding, json_data=False)
        artifacts[str(path)] = binding["sha256"]
        return path

    pin(guard.file_binding(candidate_path))
    dev_path = pin({key: candidate["development_plan"][key] for key in ("path", "sha256")})
    _, development, _ = canonical_development(dev_path, runtime)
    guard.require(candidate["policy"]["path"] == runtime.calibration.POLICY,
                  "Calibration policy must be the frozen calibrator's actual policy")
    policy = Path(development["frozen_root"]) / runtime.calibration.POLICY
    pin({"path": str(policy.resolve(strict=True)), "sha256": candidate["policy"]["sha256"]})
    pin(guard.file_binding(root / "scripts/calibrate_estimator_replay_v4.py"))
    for cls in guard.CLASSES:
        provenance = candidate["provenance"][cls]
        guard.require(provenance["slot_id"] == f"{cls}_stage1_velocity_seed004",
                      "Calibration cannot substitute another development recording")
        pin(provenance["terminal_record"])
        arrays_path = pin(provenance["arrays"])
        for binding in provenance["recording_evidence"].values():
            pin(binding)
        receipt = provenance["verified_export_evidence"]
        for name in runtime.replay.EXPORT_SIDECARS:
            guard.require(Path(name).name == name, "Unexpected sidecar path")
            pin({"path": str(arrays_path.parent / name),
                 "sha256": receipt["sidecar_sha256"][name]})
    return artifacts


def assemble_replay(core_path, candidate_path, validation_path):
    core_path, core, core_binding = read_bound(core_path)
    guard.require(core.get("mode") == "FORMAL" and len(core.get("trials", [])) == 120,
                  "Replay configuration requires the actual complete immutable 120-slot formal definition")
    root = Path(core["frozen_root"]).resolve(strict=True)
    runtime = guard.load_runtime(root, core)
    runtime.v4.validate_plan(core, core_path)
    runtime.v4.verify_sources(core)
    rows = runtime.v4.read_slots(core)
    guard.require(len(rows) == 120 and all(row["status"] == "PENDING" for row in rows.values()),
                  "Replay registration must precede every formal attempt")
    draft_path, draft, draft_binding = read_bound(root / REPLAY_PATH)
    guard.require(draft.get("status") != "REGISTERED", "A registered replay configuration cannot be replaced")
    candidate_path, candidate, candidate_binding = read_bound(candidate_path)
    guard.require(candidate.get("kind") == "RELIABILITY_V4_DEVELOPMENT_CALIBRATION"
                  and candidate.get("status") == "CANDIDATE_NOT_REGISTERED"
                  and candidate.get("scope") == "DEVELOPMENT_ONLY"
                  and set(candidate.get("candidate_parameters", {})) == PARAMETERS,
                  "A complete real development calibration candidate is required")
    stamp = guard.now().isoformat()
    guard.require(guard.utc(core["created_utc"]) <= guard.utc(stamp)
                  and guard.utc(candidate["created_utc"]) <= guard.utc(stamp),
                  "Core definition and calibration must already exist; no future registration time is accepted")
    configuration = deepcopy(draft)
    configuration["status"] = "REGISTERED"
    configuration["calibration"].update(deepcopy(candidate["candidate_parameters"]))
    configuration["calibration"]["status"] = "REGISTERED"
    configuration["methods"]["ema"]["alpha"] = configuration["calibration"]["ema_alpha"]
    implementation = configuration["implementation_status"]
    implementation.update(registered_parameters="BOUND_TO_VERIFIED_CANONICAL_SEED004_CANDIDATE",
        formal_replay="NOT_EXECUTED", end_to_end_pipeline_complete=False,
        completion_boundary="Generated configuration candidate only. Canonical final-root publication and a complete guard check remain required; no formal result is claimed.")
    sources = {name: guard.sha(root / name) for name in set(runtime.replay.EXPORT_SOURCE_FILES) | set(runtime.replay.SOURCE_FILES)}
    guard.require(all(core["source_hashes"].get(name) == value for name, value in sources.items()),
                  "Replay/export sources must match the actual final formal plan")
    artifacts = candidate_artifacts(candidate_path, candidate, runtime, root)
    configuration["freeze_requirements"].update(
        final_engineering_plan_path=str(core_path),
        final_engineering_plan_file_sha256=core_binding["sha256"],
        final_engineering_plan_digest=core["plan_sha256"],
        flight_source_hashes=deepcopy(core["source_hashes"]),
        model_hashes=deepcopy(core["model_hashes"]),
        runtime_and_magnetic_bindings={
            "px4_runtime_manifest_sha256": core["magnetic_runtime_binding"]["manifest_sha256"],
            "magnetic_library_registration_sha256": core["magnetic_library_binding"]["registration_sha256"]},
        offline_replay_source_hashes={name: sources[name] for name in runtime.replay.SOURCE_FILES},
        evaluation_source_hashes={name: sources[name] for name in runtime.replay.EXPORT_SOURCE_FILES},
        registered_estimator_parameters={"sha256": runtime.replay.canonical_sha256(configuration["calibration"])},
        development_calibration_evidence={"scope": "DEVELOPMENT_ONLY", "artifact_hashes": artifacts},
        note="Real canonical development evidence and actual formal core definition are bound. This newly generated candidate must still be published to the canonical final-root file before guard admission.")
    configuration["registration"] = {"registered_utc": stamp}
    configuration["registration"]["configuration_sha256"] = runtime.replay.configuration_digest(configuration)
    runtime.replay.validate_registered_config(configuration)
    runtime.replay.verify_registration_artifacts(configuration, source_root=root)
    context = SimpleNamespace(root=root, core=core, replay_configuration=configuration,
                              registration_times=[guard.utc(stamp)])
    # Includes actual arrays/online/native/truth sidecars, named recording
    # bindings, recalculated geometry statistics, policy and helper provenance.
    # A hash-shaped string or candidate PASS label alone cannot satisfy it.
    guard.validate_development({"calibration": candidate_binding}, context, runtime)
    for path, expected in artifacts.items():
        guard.require(guard.sha(path) == expected, "Calibration evidence changed during assembly: " + path)
    # Preserve exact original draft bytes for root's later explicit publication.
    archive = validation_path.parent.parent / "source_draft.original.json"
    guard.bound(draft_binding, json_data=False)
    with archive.open("xb") as stream:
        stream.write(draft_path.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    guard.require(guard.sha(archive) == draft_binding["sha256"], "Replay draft changed while archiving its original bytes")
    guard.write_new(validation_path, configuration)
    return {"claim": "VERIFIED_REPLAY_CONFIGURATION_CANDIDATE_NOT_CANONICAL_REGISTRATION",
            "canonical_path_unchanged": str(draft_path), "source_draft_archive": guard.file_binding(archive),
            "registered_configuration_digest": configuration["registration"]["configuration_sha256"],
            "calibration_artifact_count": len(artifacts)}


def assemble_seal(request_path, validation_path):
    _, request, _ = read_bound(request_path)
    guard.require(set(request) == REQUEST_FIELDS and request.get("schema_version") == 1
                  and request.get("kind") == "RELIABILITY_V4_ADMISSION_ASSEMBLY_REQUEST",
                  "Explicit admission assembly request required; caller cannot supply time, tool or seal digest")
    guard.require(not Path(request["state_directory"]).is_symlink(), "Guard state cannot be a link")
    state = Path(request["state_directory"]).resolve()
    guard.require(not state.exists() and not state.is_symlink(), "A first seal requires an untouched independent guard-state directory")
    manifest = {key: deepcopy(request[key]) for key in REQUEST_FIELDS - {"schema_version", "kind"}}
    manifest.update(schema_version=1, kind="RELIABILITY_V4_FORMAL_ADMISSION",
                    created_utc=guard.now().isoformat(), tool=guard.file_binding(guard.__file__))
    manifest["manifest_sha256"] = guard.sealed(manifest, "manifest_sha256")
    guard.write_new(validation_path, manifest)
    admission = guard.check(validation_path)
    guard.require(admission.report.get("result") == "PASS"
                  and admission.report["capacity"]["pending_slots"] == 280,
                  "A first seal requires the complete real full-280 guard check")
    guard.require(not state.exists(), "Read-only guard check unexpectedly changed runner/admission state")
    return {"claim": "ADMISSION_CHECK_ONLY_NO_INITIAL_ADMISSION_OR_FLIGHT",
            "guard_check": admission.report,
            "check_location": "The guard validated these identical bytes at the recorded temporary path before exclusive publication; that temporary path is removed.",
            "guard_state_created": False}


def require_independent_output(action, inputs, output):
    """Reject a source/trial destination before even an assembly ledger exists."""
    plans, directories = [], []
    if action == "safety-summary":
        plans.append(guard.load(inputs["target_plan"]))
        facts = guard.load(inputs["facts"])
        _, registry = guard.bound(facts["registry"])
        directories.extend(Path(item["directory"]).resolve() for item in registry["trials"])
        _, development = guard.bound({key: registry["source_core_plan"][key] for key in ("path", "sha256")})
        plans.append(development)
    elif action == "replay-config":
        plans.append(guard.load(inputs["core_plan"]))
        candidate = guard.load(inputs["candidate"])
        _, development = guard.bound({key: candidate["development_plan"][key] for key in ("path", "sha256")})
        plans.append(development)
    else:
        request = guard.load(inputs["request"])
        for label in ("core", "extension"):
            _, plan = guard.bound(request["plans"][label])
            plans.append(plan)
    for plan in plans:
        root = Path(plan["frozen_root"]).resolve(strict=True)
        results = Path(plan["results_root"]).resolve(strict=True)
        guard.require(not output.is_relative_to(root) or output.is_relative_to(results),
                      "Assembly output must not modify a frozen source/build tree")
        if "output" in plan:
            guard.require(not output.is_relative_to(Path(plan["output"]).resolve()),
                          "Assembly output must be independent of every original plan matrix")
        directories.extend(Path(trial["directory"]).resolve() for trial in plan["trials"])
    tool_root = Path(__file__).resolve().parents[1]
    original_results = [Path(plan["results_root"]).resolve(strict=True) for plan in plans]
    guard.require(not output.is_relative_to(tool_root) or any(output.is_relative_to(path) for path in original_results),
                  "Assembly output must not modify the current tool source/build tree")
    guard.require(not any(output.is_relative_to(directory) for directory in directories),
                  "Assembly outputs must be independent of every original trial")


def run_action(action, inputs, output_directory):
    """One new independent directory, immutable start/outcome, no retry in place."""
    guard.require(action in {"safety-summary", "replay-config", "seal"}, "Unknown assembly action")
    requested_output = Path(output_directory).absolute()
    guard.require(not requested_output.exists() and not requested_output.is_symlink(),
                  "Refusing to reuse an assembly output directory or link")
    output = requested_output.resolve()
    guard.require(not output.exists() and not output.is_symlink(), "Refusing to reuse an assembly output directory")
    guard.require(output.parent.is_dir(), "Create the intended output parent explicitly first")
    bindings = {name: guard.file_binding(path) for name, path in inputs.items()}
    registrar = guard.file_binding(__file__)
    guard_binding = guard.file_binding(guard.__file__)
    require_independent_output(action, inputs, output)
    output.mkdir(exist_ok=False)
    validation = output / ".validation"
    validation.mkdir(exist_ok=False)
    temporary = validation / "unpublished.json"
    filename = {"safety-summary": "safety_summary_candidate.json", "replay-config": "replay_configuration_candidate.json",
                "seal": "final_admission.json"}[action]
    published = output / filename
    guard.write_new(output / "started.json", {"schema_version": 1,
        "kind": "RELIABILITY_V4_REGISTRATION_ASSEMBLY_START", "created_utc": guard.now().isoformat(),
        "action": action, "inputs": bindings, "registrar": registrar,
        "guard": guard_binding, "no_flights_or_bag_reads": True,
        "canonical_files_modified": False})
    linked = False
    try:
        if action == "safety-summary":
            detail = assemble_safety(inputs["target_plan"], inputs["core_gate"], inputs["facts"], temporary)
        elif action == "replay-config":
            detail = assemble_replay(inputs["core_plan"], inputs["candidate"], temporary)
        else:
            detail = assemble_seal(inputs["request"], temporary)
        for binding in (*bindings.values(), registrar, guard_binding):
            guard.bound(binding, json_data=False)
        validated_sha = guard.sha(temporary)
        # Atomic exclusive publication of the same validated bytes; never a
        # replace/rename over an existing artifact. Both paths share this dir.
        os.link(temporary, published)
        linked = True
        outcome = {"schema_version": 1, "kind": "RELIABILITY_V4_REGISTRATION_ASSEMBLY_OUTCOME",
            "created_utc": guard.now().isoformat(), "action": action,
            "status": "ASSEMBLED_AND_VALIDATED_NOT_EXECUTED", "registrar": registrar,
            "artifact": guard.file_binding(published), "validated_bytes_sha256": validated_sha,
            "detail": detail, "canonical_files_modified": False, "formal_attempts_started": 0}
        guard.write_new(output / "outcome.json", outcome)
        return outcome
    except BaseException as error:
        if linked:
            published.unlink()
        guard.write_new(output / "outcome.json", {"schema_version": 1,
            "kind": "RELIABILITY_V4_REGISTRATION_ASSEMBLY_OUTCOME",
            "created_utc": guard.now().isoformat(), "action": action,
            "status": "REFUSED_NO_PUBLISHED_ARTIFACT", "registrar": registrar,
            "error": type(error).__name__ + ": " + str(error),
            "canonical_files_modified": False, "formal_attempts_started": 0})
        raise
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    safety = sub.add_parser("safety-summary")
    safety.add_argument("--target-plan", type=Path, required=True)
    safety.add_argument("--core-gate", type=Path, required=True)
    safety.add_argument("--facts", type=Path, required=True)
    replay = sub.add_parser("replay-config")
    replay.add_argument("--core-plan", type=Path, required=True)
    replay.add_argument("--candidate", type=Path, required=True)
    seal = sub.add_parser("seal")
    seal.add_argument("--request", type=Path, required=True)
    for command in (safety, replay, seal):
        command.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    inputs = {key: value for key, value in vars(args).items() if key not in {"action", "output_directory"}}
    try:
        outcome = run_action(args.action, inputs, args.output_directory)
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, OSError, TypeError) as error:
        print("Registration assembly refused: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
