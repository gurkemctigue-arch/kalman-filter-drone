"""Plan/inventory or run the registered v4 array-only estimator comparison.

No bag reader or ROS imports. DRAFT is rejected before opening any trial input.
Independent export/online/native/truth sidecars must pass file and source
verification before a calculation is labelled audited. No ROS is imported.

The input manifest is {"schema_version":1,"slots":{SLOT_ID:{"path":ARRAY_JSON,
"sha256":FILE_HASH}, ...}} and must name all twenty slots; a missing entry is
explicit null. inventory reads only this manifest and file metadata.

schema2 runtime diagnostic -> normalized array mapping in the separate exporter:
  source_s = acquisition_s
  measurement.available_s = max(acquisition_s, measurement_processing_s)
  position_world_m = raw_position_world_m
  R_geometry_world_m2 = reference_covariance_geometry
  R_pose_world_m2 = reference_covariance_pose
  output.source_s = output_publication_s
  output.state_source_s = actual TargetState.header / diagnostic output_s
  output.available_s = max(output_publication_s, recorder delivery /clock)
Deduplicate measurement opportunities by acquisition+UUID/track/candidate; do
not confuse processing availability with recorder delivery. Preserve original
quality, chosen-pose/Jacobian, TF, initial-velocity and recorder-order provenance
in the export audit. This CLI verifies those serialized audits and their files;
normalization and online numerical reproduction stay in separate tools.
Task/measurement/output derived from one schema2 diagnostic may share that
diagnostic's original record_sequence. The core orders only inside a shared
cycle as task -> measurement -> output, and preserves bag sequence across cycles.
Do not synthesize sequence numbers by multiplying or replacing original order;
actual navstate bag sequence can remain separate corroboration metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from uav_tracking.replay_comparison import (  # noqa: E402
    CLASSES, METHODS, SOURCE_FILES, EXPORT_SOURCE_FILES, EXPORT_SIDECARS,
    EXPORT_EVIDENCE_KIND, DEVELOPMENT_EXPORT_EVIDENCE_KIND, PAYLOAD_EXCLUDED_FIELDS,
    ONLINE_FLIGHT_SOURCE_FILES, canonical_sha256, configuration_digest, replay_payload_sha256,
    paired_trial_summary, replay_trial, scheduled_slots, validate_registered_config,
)

DRAFT = ROOT / "planning/reliability-v4-estimator-replay-preregistration.json"


def load(path):
    result = json.loads(Path(path).read_text(encoding="utf-8-sig"),
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + token)))
    if not isinstance(result, dict):raise ValueError("Expected a JSON object: " + str(path))
    return result


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024 * 1024), b""):digest.update(block)
    return digest.hexdigest()


def verify_registration_artifacts(config, *, source_root=ROOT):
    """Bind the executable and final flight plan before reading held-out arrays."""
    freeze = config["freeze_requirements"]
    expected = freeze["offline_replay_source_hashes"]
    observed = {relative:file_sha256(Path(source_root) / relative) for relative in SOURCE_FILES}
    if any(expected.get(relative) != digest for relative,digest in observed.items()):
        raise ValueError("Current replay implementation/KF helpers differ from registration")
    plan_path = Path(freeze["final_engineering_plan_path"])
    if file_sha256(plan_path) != freeze["final_engineering_plan_file_sha256"]:
        raise ValueError("Frozen final engineering plan file differs from registration")
    plan = load(plan_path)
    if (plan.get("mode") != "FORMAL" or plan.get("plan_sha256") != freeze["final_engineering_plan_digest"]
            or canonical_sha256({k:v for k,v in plan.items() if k != "plan_sha256"}) != plan.get("plan_sha256")):
        raise ValueError("Not the registered immutable FORMAL engineering plan")
    # The replay binds the complete source manifest saved in the final plan.
    # Current files may be a separately frozen evaluation checkout.
    if plan.get("source_hashes") != freeze["flight_source_hashes"] or plan.get("model_hashes") != freeze["model_hashes"]:
        raise ValueError("Final flight source/model manifest differs from registration")
    runtime = {"px4_runtime_manifest_sha256":plan.get("magnetic_runtime_binding", {}).get("manifest_sha256"),
               "magnetic_library_registration_sha256":plan.get("magnetic_library_binding", {}).get("registration_sha256")}
    if runtime != freeze["runtime_and_magnetic_bindings"]:
        raise ValueError("Final flight runtime/library manifest differs from registration")
    plan_slots = {trial["id"]:trial for trial in plan.get("trials", [])}
    if any(slot not in plan_slots for slot in scheduled_slots()):
        raise ValueError("The final plan does not contain all twenty named recordings")
    for slot in scheduled_slots():
        trial = plan_slots[slot]
        if (trial.get("group") != "stage1_velocity" or trial.get("target_class") not in CLASSES
                or slot != f"{trial.get('target_class')}_stage1_velocity_seed{trial.get('seed')}"):
            raise ValueError("Final plan slot class/group/seed binding differs")
    return {"configuration_sha256":configuration_digest(config), "implementation_source_hashes":observed,
            "final_plan_file_sha256":file_sha256(plan_path),
            "scope":"Source/file binding and prospective registration; each recording's actual export/online/native/truth audit files are independently checked after loading its arrays"}


def input_manifest(path):
    manifest = load(path)
    slots = manifest.get("slots")
    if manifest.get("schema_version") != 1 or not isinstance(slots, dict) or set(slots) != set(scheduled_slots()):
        raise ValueError("Input manifest must name all twenty registered slots, using null for missing recordings")
    base = Path(path).resolve().parent
    resolved = {}
    for slot in scheduled_slots():
        item = slots[slot]
        if item is None:resolved[slot] = None;continue
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("Each input slot must bind an array JSON path and SHA256, or be null")
        digest = item["sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Input array SHA256 is required")
        source = Path(item["path"])
        resolved[slot] = {"path":str(source if source.is_absolute() else base / source),"sha256":digest}
    return resolved


def inventory(manifest_path):
    """Metadata only: never open a held-out trial array or bag."""
    slots = input_manifest(manifest_path)
    result = {}
    for slot,item in slots.items():
        if item is None:result[slot] = {"state":"MISSING_DECLARED"};continue
        path = Path(item["path"])
        result[slot] = {"state":"FILE_PRESENT_UNREAD" if path.is_file() else "FILE_MISSING",
                        "path":str(path),"bytes":path.stat().st_size if path.is_file() else None}
    return {"schema_version":1,"evaluation_status":"INVENTORY_ONLY_NO_HELD_OUT_OUTCOMES_READ",
            "scheduled_trials":20,"slots":result}


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def verify_export_evidence(array_path, trial, config, *, source_root=ROOT, development_only=False):
    """Open and cross-check actual source-bound audit files, never trust PASS alone.

    This verifies export provenance and numerical reproduction, independently
    of source-clock/flight acceptance. Truth coordinates never enter filtering.
    """
    def require(condition, reason):
        if not condition:raise ValueError(reason)
    def count(value, label):
        require(type(value) is int and value >= 0, "Invalid audit count: " + label)
        return value
    def number(value):
        import math
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0., "Invalid audit timestamp/age")
        return float(value)
    def equal(left, right):
        return abs(number(left)-number(right)) <= 1e-8
    def indexed(rows, key):
        require(isinstance(rows, list), "Missing audit rows")
        result = {}
        for row in rows:
            require(isinstance(row, dict), "Malformed audit row")
            sequence = row.get(key)
            count(sequence, "record sequence")
            require(sequence not in result, "Duplicate audit cycle sequence")
            result[sequence] = row
        return result

    directory = Path(array_path).resolve(strict=True).parent
    sidecars, hashes = {}, {}
    for name, field in EXPORT_SIDECARS.items():
        path = directory/name
        require(not path.is_symlink() and path.is_file(), "Missing/local audit sidecar: " + name)
        hashes[name] = file_sha256(path)
        require(hashes[name] == trial.get(field), "Audit sidecar SHA256 differs: " + name)
        sidecars[name] = load(path)
    export = trial.get("export_audit", {})
    scope = "DEVELOPMENT_ONLY" if development_only else "FORMAL"
    require(type(development_only) is bool, "Development audit mode must be an explicit boolean")
    if development_only:
        require(type(trial.get("seed")) is int and trial["seed"] not in range(1000,1010)
                and str(trial.get("slot_id", "")).startswith("DEVELOPMENT_ONLY_")
                and trial.get("engineering_status") == "DEVELOPMENT_ONLY_NO_FORMAL_VERDICT",
                "Development audit cannot accept held-out/formal trial identities")
    require(isinstance(export, dict) and export.get("scope") == scope and export.get("status") == "PASS"
            and export.get("online_equivalence") == "PASS" and export.get("native_state_audit") == "PASS",
            "A complete formal recording export audit is required")
    frozen = config["freeze_requirements"]
    sources = export.get("source_hashes")
    require(isinstance(sources, dict) and set(sources) == set(EXPORT_SOURCE_FILES), "Incomplete/unexpected export helper/message source manifest")
    for name in EXPORT_SOURCE_FILES:
        require(sources[name] == frozen["evaluation_source_hashes"].get(name), "Export source differs from registration: " + name)
        require(file_sha256(Path(source_root)/name) == sources[name], "Actual export helper/message source changed: " + name)
        if name in SOURCE_FILES:
            require(sources[name] == frozen["offline_replay_source_hashes"].get(name), "Export/replay source registrations disagree: " + name)
    require(all(sources[name] == frozen["flight_source_hashes"].get(name) for name in ONLINE_FLIGHT_SOURCE_FILES),
            "Reproduced estimator/message/KF helpers differ from the actual frozen flight revision")
    schema = (Path(source_root)/"ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg").read_text(encoding="utf-8")
    for declaration in ("float32[36] covariance", "float32 prediction_age_s", "geometry_msgs/Point position_m", "geometry_msgs/Vector3 velocity_mps"):
        require(declaration in [line.strip() for line in schema.splitlines()], "Registered TargetState wire contract changed")

    events = trial["output_events"]
    outputs = indexed(events, "record_sequence")
    measurements = indexed(trial["measurements"], "record_sequence")
    tasks = indexed(trial["task_events"], "record_sequence")
    require(bool(outputs) and set(measurements) <= set(outputs) and set(tasks) == set(outputs), "Incomplete compound output/task/measurement cycles")
    total, distinct = len(outputs), len(measurements)
    require(count(export.get("diagnostic_cycles"), "export cycles") == total
            and count(export.get("deduplicated_measurements"), "export measurements") == distinct
            and count(export.get("cached_measurement_repeats"), "export repeats") == total-distinct, "Export cycle counts disagree")
    reader = export.get("bag_reader", {})
    require(reader.get("clock_recorded") is True and reader.get("clock_records_preserved") is True
            and count(reader.get("clock_samples_read"), "clock samples") > 0
            and reader.get("source_bag_read_only") is True and reader.get("read_errors") == {}
            and reader.get("unavailable_types") in ({}, []), "Complete read-only clock-preserving bag evidence is missing")
    require(count(export.get("recorded_archive_message_count"), "archive messages") >= total, "Archive message count cannot cover recorded outputs")

    online = sidecars["online_equivalence.json"]
    payload_hash = replay_payload_sha256(trial)
    expected_payload_binding = {"schema_version":1, "canonical_payload_sha256":payload_hash,
        "excluded_circular_audit_fields":sorted(PAYLOAD_EXCLUDED_FIELDS)}
    require(all(sidecar.get("replay_payload_binding") == expected_payload_binding for sidecar in sidecars.values()),
            "Audit files do not bind the exact measurement/task/output/truth replay payload")
    require(type(online.get("schema_version")) is int and online["schema_version"] == 1
            and online.get("audit_kind") == "ONLINE_NAVIGATION_DIAGNOSTIC_REPRODUCTION"
            and online.get("evaluation_status") == "PASS" and online.get("online_equivalence_pass") is True
            and online.get("uses_ground_truth") is False and online.get("issues") == []
            and online.get("absolute_tolerance") == 1e-8 and online.get("relative_tolerance") == 0.
            and online.get("recorder_clock_future_tolerance_s") == .05, "Online audit is not complete under original numerical/time limits")
    require(online.get("navigation_estimator_source", {}).get("sha256") == sources[
        "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py"], "Actual online estimator source is unbound")
    parameters = online.get("runtime_kf_parameters")
    require(isinstance(parameters, dict) and parameters == export.get("fixed_online_constructor_parameters")
            and set(parameters) == {"gate_threshold", "process_acceleration_std", "measurement_noise_std",
                                    "initial_velocity_covariance", "default_dt", "max_age_s"}
            and parameters.get("gate_threshold") == 9.21 and parameters.get("max_age_s") == .75,
            "Online constructor parameters differ from recorded export/original limits")
    require(all(number(parameters[name]) > 0. for name in parameters if name != "measurement_noise_std")
            and isinstance(parameters["measurement_noise_std"], list) and len(parameters["measurement_noise_std"]) == 3
            and all(number(value) > 0. for value in parameters["measurement_noise_std"]), "Invalid online noise/model constructor evidence")
    records = indexed(online.get("records"), "record_sequence")
    require(set(records) == set(outputs), "Online audit does not cover every recorded output cycle")
    expected_counts = {"diagnostics":total, "distinct_measurements":distinct, "repeated_measurements":total-distinct,
                       "updates_reproduced":distinct, "outputs_reproduced":total}
    require(online.get("counts") == expected_counts and all(type(value) is int for value in online["counts"].values()), "Online audit counts disagree")
    for sequence, event in outputs.items():
        row = records[sequence]
        require(row.get("output_reproduced") is True and row.get("mismatches") == []
                and type(row.get("measurement_repeated")) is bool
                and row["measurement_repeated"] == (sequence not in measurements)
                and type(row.get("update_reproduced")) is bool and row["update_reproduced"] == (sequence in measurements), "Online per-cycle update/output evidence is incomplete")
        require(equal(row.get("output_s"), event["state_source_s"])
                and equal(row.get("output_publication_s"), event["source_s"]), "Online output header/publication disagrees with exported event")
        if sequence in measurements:
            require(equal(row.get("acquisition_s"), measurements[sequence]["source_s"]), "Online acquisition differs from exported measurement")

    native = sidecars["native_state_audit.json"]
    require(native.get("status") == "PASS" and native.get("differences") == []
            and count(native.get("diagnostic_count"), "native diagnostic count") == total
            and count(native.get("native_state_count"), "native count") == total, "Independent native-state correspondence is incomplete")
    wire = native.get("numeric_contract", {})
    require(wire == {
        "schema":"ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg",
        "covariance_world_6x6":"float32[36]; cast diagnostic to binary32, widen to binary64, exact equality",
        "measurement_age_s":"float32; check diagnostic binary64 age against source/header first, then exact binary32 wire equality",
        "position_and_velocity":"geometry_msgs Point/Vector3 binary64; rtol=0, atol=1e-8",
        "online_diagnostic_reproduction":"Separate binary64 audit retains rtol=0, atol=1e-8"}, "Native audit wire schema/precision is not the registered contract")
    pairs = indexed(native.get("pairs"), "diagnostic_record_sequence")
    require(set(pairs) == set(outputs), "Native audit does not cover every recorded output cycle")
    native_sequences = [row.get("native_state_record_sequence") for row in pairs.values()]
    require(all(type(value) is int and value >= 0 for value in native_sequences)
            and len(set(native_sequences)) == total, "Native states were reused or original sequence is missing")
    for sequence, event in outputs.items():
        pair, online_row = pairs[sequence], records[sequence]
        receipt = number(pair.get("native_state_received_sim_s"))
        availability = max(number(event["source_s"]), receipt)
        require(equal(pair.get("native_state_availability_s"), availability) and equal(event["available_s"], availability)
                and event.get("native_delivery_verified") is True, "Exported output delivery differs from separately recorded native state")
        age = number(pair.get("native_state_measurement_age_s"))
        state = online_row.get("reproduced_output", {})
        require(type(state.get("valid")) is bool, "Online audit lacks an explicit reproduced state")
        if state["valid"]:
            import struct
            precise_age = number(state.get("measurement_age_s"))
            require(precise_age <= .75+1e-8 and equal(number(event["state_source_s"])-number(state.get("output_measurement_source_s")), precise_age),
                    "Online measurement age/source/horizon is inconsistent")
            expected_age = struct.unpack("f", struct.pack("f", precise_age))[0]
            require(age == expected_age, "Native age disagrees with binary32 serialized online output")
            delivered = age + availability-number(event["state_source_s"])
            require(equal(pair.get("delivered_measurement_age_s"), delivered)
                    and pair.get("delivery_within_prediction_horizon") is (delivered <= .75+1e-8), "Native delivered-age evidence disagrees")
        else:
            require(pair.get("delivered_measurement_age_s") is None and pair.get("delivery_within_prediction_horizon") is None,
                    "Invalid native state fabricated a valid delivery age")

    truth = sidecars["truth_alignment.json"]
    alignment = truth.get("alignment", {})
    require(trial.get("truth_frame") == "map" and trial.get("truth_alignment_basis") == "declared_enu_vehicle_only_frozen"
            and alignment.get("rotation_policy") == "declared_enu"
            and alignment.get("rotation_world_from_map") == [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]], "Truth map axes are not independently declared ENU")
    start, end = number(alignment.get("calibration_start_s")), number(alignment.get("calibration_end_s"))
    require(equal(end-start, 5.) and equal(end, trial["interval"]["alignment_end_s"]), "Truth alignment was not frozen from the fixed first five seconds")
    translation = alignment.get("translation_world_from_map_m")
    import math
    require(isinstance(translation, list) and len(translation) == 3
            and all(type(value) in (int, float) and math.isfinite(value) for value in translation), "Missing independent ego translation")
    splits = alignment.get("splits", {})
    require(count(splits.get("calibration", {}).get("pairs"), "ego calibration pairs") >= 10
            and count(splits.get("ego_holdout", {}).get("pairs"), "ego holdout pairs") > 0,
            "Independent ego calibration/holdout evidence is missing")
    require(truth.get("target_reference") == "independent single actor ground-footprint/model origin"
            and truth.get("target_actor") == "target_"+trial["target_class"] and truth.get("position_anchor_m") == [0.,0.,0.]
            and truth.get("velocity_symmetric_derivative_half_window_s") == .05,
            "Truth actor/anchor/derivative differs from the frozen scoring contract")
    receipt = {"schema_version":1, "kind":DEVELOPMENT_EXPORT_EVIDENCE_KIND if development_only else EXPORT_EVIDENCE_KIND,
        "scope":scope, "trial_input_sha256":canonical_sha256(trial), "replay_payload_sha256":payload_hash,
        "configuration_sha256":configuration_digest(config), "sidecar_sha256":hashes,
        "export_source_hashes":sources, "output_sequence_sha256":canonical_sha256([row["record_sequence"] for row in events]),
        "counts":{"output_cycles":total,"measurements":distinct,"task_events":len(tasks)},
        "truth_contract":{"frame":"map","rotation_policy":"declared_enu","ego_calibration_duration_s":5.,"velocity_derivative_half_window_s":.05},
        "claim_boundary":"Verified export, online numerical reproduction and native-topic correspondence. Flight/source-clock/terminal verdicts remain independent."}
    receipt["evidence_sha256"] = canonical_sha256(receipt)
    return receipt


def run(config, manifest_path, output, *, source_root=ROOT):
    # These checks intentionally precede loading the input manifest or arrays.
    validate_registered_config(config)
    provenance = verify_registration_artifacts(config, source_root=source_root)
    slots = input_manifest(manifest_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "registered_configuration.json", config)
    reports, missing = [], []
    for slot,item in slots.items():
        if item is None:
            missing.append({"slot_id":slot,"reason":"MISSING_DECLARED"});continue
        try:
            path = Path(item["path"])
            if path.suffix.lower() != ".json":raise ValueError("Only exported array JSON is supported; no bag reader is available")
            if file_sha256(path) != item["sha256"]:raise ValueError("Input array file hash differs from manifest")
            trial = load(path)
            if trial.get("slot_id") != slot:raise ValueError("Input array is assigned to a different scheduled slot")
            export_evidence, audit_errors = None, []
            try:export_evidence = verify_export_evidence(path, trial, config, source_root=source_root)
            except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
                audit_errors.append(f"{type(error).__name__}:{error}")
            report = replay_trial(trial, config, export_evidence=export_evidence)
            report["export_evidence_issues"].extend(audit_errors)
            report["evaluation_source"] = provenance
            report["input_file_sha256"] = item["sha256"]
            write_new(output / (slot + ".json"), report)
            reports.append(report)
        except (OSError, ValueError, KeyError, TypeError) as error:
            missing.append({"slot_id":slot,"reason":f"INCOMPLETE_OR_INVALID_INPUT:{type(error).__name__}:{error}"})
    summary = paired_trial_summary(reports, config)
    summary.update(missing_or_invalid_inputs=missing, evaluation_source=provenance,
                   input_manifest_file_sha256=file_sha256(manifest_path))
    write_new(output / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan", help="Describe required registration and the 20-slot matrix; no trial reads")
    plan.add_argument("--configuration", type=Path, default=DRAFT)
    listing = sub.add_parser("inventory", help="Inspect only paths/sizes declared by a complete input manifest")
    listing.add_argument("--inputs-manifest", type=Path, required=True)
    execute = sub.add_parser("run", help="Run registered array replay; no bags, ROS or simulator")
    execute.add_argument("--configuration", type=Path, required=True)
    execute.add_argument("--inputs-manifest", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            config = load(args.configuration)
            result = {"schema_version":1,"evaluation_status":"PLAN_ONLY_NO_HELD_OUT_OUTCOMES_READ",
                "configuration_status":config.get("status"),"scheduled_trials":20,"slot_ids":scheduled_slots(),"methods":list(METHODS),
                "run_requires":"REGISTERED config with explicit R0/Q/P0/EMA/common gate, prospective digest, final plan/model/runtime and actual implementation hashes",
                "pending":["Development calibration and prospective registration", "Verified audit files for every selected formal recording", "Complete verified twenty-recording comparison"]}
        elif args.action == "inventory":result = inventory(args.inputs_manifest)
        else:result = run(load(args.configuration), args.inputs_manifest, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 2 if (result.get("missing_or_invalid_inputs") or
                 args.action == "run" and result.get("complete_verified_matrix") is not True) else 0


if __name__ == "__main__":raise SystemExit(main())
