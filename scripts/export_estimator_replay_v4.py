"""Export schema2 navigation recordings and independently audit online replay.

Development recordings may be inspected before registration. Held-out seeds
1000..1009 require the registered final plan and immutable terminal slot.
Truth is read only to form the separately mapped scoring grid, never gating.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import evaluate_stage1_flight as bag_tools
from evaluate_online_state_accuracy import PoseSeries, anchor_truth, freeze_ego_alignment
from evaluate_navigation_reference import recorded_configuration
from extract_research_recording import pose_dict
from run_estimator_replay_v4 import load, file_sha256, verify_registration_artifacts
from uav_tracking.navigation_reproduction import evaluate_navigation_reproduction
from uav_tracking.replay_comparison import (canonical_sha256, validate_registered_config,
                                           PAYLOAD_EXCLUDED_FIELDS, replay_payload_sha256)
from uav_tracking.replay_export import normalize_cycles, verify_state_cycles

DIAGNOSTIC = "/tracking/navigation_diagnostics"
NATIVE = "/tracking/navigation_state"
SOURCE_FILES = ("scripts/export_estimator_replay_v4.py", "scripts/evaluate_stage1_flight.py",
    "scripts/run_estimator_replay_v4.py", "uav_tracking/replay_comparison.py",
    "scripts/evaluate_navigation_reference.py", "scripts/evaluate_online_state_accuracy.py",
    "scripts/extract_research_recording.py", "uav_tracking/replay_export.py",
    "uav_tracking/navigation_reproduction.py", "uav_tracking/core/uncertainty.py",
    "uav_tracking/research_labels.py",
    "ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg",
    "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py",
    "uav_tracking/core/kalman.py", "uav_tracking/core/models.py")
TERMINAL = {"PASS", "FAIL", "INTERRUPTED", "INCOMPLETE_EVIDENCE", "INFRASTRUCTURE_ERROR", "EVALUATION_PENDING"}


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0.:
        raise ValueError("Missing/nonfinite/nonnegative " + name)
    return float(value)


def _utc(value):
    if not isinstance(value, str):raise ValueError("Missing explicit UTC flight start")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("Flight start must explicitly use UTC")
    return stamp.astimezone(timezone.utc)


def _contained(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Expected a relative artifact path")
    path = (root/relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Recorded artifact escaped its trial directory")
    return path


def formal_slot(trial, raw_config, registration, slot_id, sources):
    """Verify metadata, immutable artifacts and prospective bindings before ROS reads."""
    parameters = validate_registered_config(registration)
    verify_registration_artifacts(registration)
    freeze = registration["freeze_requirements"]
    if any(freeze["evaluation_source_hashes"].get(name) != value for name, value in sources.items()):
        raise ValueError("Current recording exporter/audit sources differ from registration")
    plan = load(freeze["final_engineering_plan_path"])
    selected = next((row for row in plan["trials"] if row["id"] == slot_id), None)
    if (selected is None or Path(selected["directory"]).resolve() != trial
            or selected.get("group") != "stage1_velocity"
            or selected.get("seed") != raw_config["seed"] or selected.get("target_class") != raw_config["target_class"]
            or slot_id != f"{raw_config['target_class']}_stage1_velocity_seed{raw_config['seed']}"):
        raise ValueError("Trial class/seed/policy differs from the registered immutable slot")
    terminal_path = Path(plan["output"])/"slots"/(slot_id+".json")
    terminal = load(terminal_path)
    if (terminal.get("record_sha256") != canonical_sha256({key:value for key,value in terminal.items() if key != "record_sha256"})
            or terminal.get("plan_sha256") != plan["plan_sha256"] or terminal.get("id") != slot_id
            or terminal.get("status") not in TERMINAL):
        raise ValueError("Immutable terminal record is invalid")
    started = terminal.get("started_utc", terminal.get("started", {}).get("started_utc"))
    if _utc(started) <= parameters["registered_utc"]:
        raise ValueError("Estimator registration must precede every selected held-out flight")
    # Registration after another selected slot had already started is also late.
    for candidate in plan["trials"]:
        if candidate.get("group") != "stage1_velocity":continue
        for suffix in (".json", ".started.json"):
            path = Path(plan["output"])/"slots"/(candidate["id"]+suffix)
            if not path.is_file():continue
            record = load(path)
            stamp = record.get("started_utc", record.get("started", {}).get("started_utc"))
            if stamp is not None and _utc(stamp) <= parameters["registered_utc"]:
                raise ValueError("Registration followed the first selected formal flight")
    artifacts = terminal.get("artifact_hashes")
    required = {"run_config.json", "configuration/runtime_parameters.yaml", "bag_integrity.json", "rosbag/metadata.yaml"}
    if not isinstance(artifacts, dict) or not required.issubset(artifacts):
        raise ValueError("Terminal record does not bind all required recording/configuration artifacts")
    for relative, expected in artifacts.items():
        if file_sha256(_contained(trial, relative)) != expected:
            raise ValueError("Immutable terminal trial artifact changed: " + relative)
    terminal = {**terminal, "started_utc":started}
    return plan, terminal_path, terminal


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def recorded_inputs(records):
    diagnostics, states, clocks, phases = [], [], [], []
    for row in records:
        if row.topic == "/clock":
            clocks.append(_number(bag_tools.stamp_s(row.message.clock), "recorded clock"))
        elif row.topic == DIAGNOSTIC:
            data = json.loads(row.message.data)
            data.update(record_sequence=row.record_sequence, received_sim_s=row.received_sim_s)
            diagnostics.append(data)
        elif row.topic == NATIVE:
            message = row.message
            states.append({"source_s":bag_tools.stamp_s(message.header.stamp),
                "record_sequence":row.record_sequence, "received_sim_s":row.received_sim_s,
                "target_uuid":str(message.target_uuid), "track_id":int(message.track_id),
                "state":int(message.state), "position_world_m":list(bag_tools.vector(message.position_m)),
                "frame_id":str(message.header.frame_id),
                "velocity_world_mps":list(bag_tools.vector(message.velocity_mps)),
                "measurement_age_s":float(message.prediction_age_s),
                "covariance_world_6x6":np.asarray(message.covariance).reshape(6, 6).tolist()})
        elif row.topic == "/tracking/flight_phase" and row.message.data.startswith("FOLLOW:"):
            match = re.search(r"source_sim_s=([0-9.]+)$", row.message.data)
            if match is None or row.received_sim_s is None:
                raise ValueError("FOLLOW phase requires explicit source time and recorded clock")
            source = _number(float(match[1]), "FOLLOW source")
            received = _number(row.received_sim_s, "FOLLOW delivery")
            if source - received > .05 + 1e-8:raise ValueError("FOLLOW source exceeds original future tolerance")
            phases.append(max(source, received))
    if not clocks or not phases:
        raise ValueError("Full recorded clock and an actual FOLLOW phase are required")
    if any(b < a for a, b in zip(clocks, clocks[1:])):
        raise ValueError("Recorded clock regressed")
    if min(phases) >= clocks[-1]:raise ValueError("FOLLOW has no later recorded clock interval")
    return diagnostics, states, {"follow_start_s":min(phases), "recorded_clock_end_s":clocks[-1]}


def independent_truth(records, config, interval, task_events):
    """Map only scoring truth using an ego-only fixed five-second alignment."""
    trajectories, odometry = defaultdict(dict), []
    for row in records:
        message = row.message
        if row.topic.startswith("/ground_truth/"):
            for transform in message.transforms:
                pose = pose_dict(transform)
                trajectories[transform.child_frame_id.strip("/")][pose["time_s"]] = pose
        elif row.topic == "/vehicle/odometry":
            if message.header.frame_id != "map" or message.child_frame_id != "base_link":
                raise ValueError("Unexpected vehicle odometry frames")
            q = message.pose.pose.orientation
            odometry.append({"time_s":bag_tools.stamp_s(message.header.stamp),
                "position_m":list(bag_tools.vector(message.pose.pose.position)),
                "quaternion_xyzw":[q.x, q.y, q.z, q.w]})
    def series(name):
        keys = [key for key in trajectories if key == name or key.endswith("::"+name) or key.rsplit("/", 1)[-1] == name]
        if len(keys) != 1:raise ValueError("Missing/ambiguous independently named truth actor: "+name)
        return PoseSeries(list(trajectories[keys[0]].values()))
    vehicle = series("stage1_uav")
    target = series("target_"+config["target_class"])
    alignment = freeze_ego_alignment(sorted(odometry, key=lambda row:row["time_s"]), vehicle,
        config["vehicle_control_point_offset_flu_m"], np.eye(3), calibration_duration_s=5.)
    interval = {**interval, "alignment_end_s":alignment["calibration_end_s"]}
    start = max(interval["follow_start_s"], interval["alignment_end_s"])
    end = interval["recorded_clock_end_s"]
    if not math.isfinite(start) or end <= start:raise ValueError("No positive post-alignment FOLLOW interval")
    rotation = np.asarray(alignment["rotation_world_from_map"])
    translation = np.asarray(alignment["translation_world_from_map_m"])
    events = sorted(task_events, key=lambda row:(row["available_s"], row["record_sequence"]))
    times = [row["available_s"] for row in events]
    samples = []
    for index in range(int(math.floor((end-start)/.1+1e-8))+1):
        stamp = start+index*.1
        preceding = bisect_right(times, stamp+1e-9)-1
        task = events[preceding] if preceding >= 0 else None
        uuid = str(task.get("target_uuid", "")) if task is not None and task["action"] != "clear" else ""
        truth = anchor_truth(target, stamp, np.zeros(3), derivative_half_window_s=.05)
        samples.append({"time_s":stamp, "target_uuid":uuid,
            "position_world_m":(rotation.T @ (truth[0]-translation)).tolist() if truth is not None else None,
            "velocity_world_mps":(rotation.T @ truth[1]).tolist() if truth is not None and truth[1] is not None else None})
    return interval, samples, {"alignment":alignment, "target_reference":"independent single actor ground-footprint/model origin",
        "target_actor":"target_"+config["target_class"], "position_anchor_m":[0.,0.,0.],
        "velocity_symmetric_derivative_half_window_s":.05,
        "truth_boundary":"Offline scoring only. No target fit, nearest-actor mapping, extrapolation or update/gate input."}


def validate_recording_archive(trial):
    report = load(trial/"bag_integrity.json")
    if report.get("status") != "PASS" or report.get("policy") != "ext4_sqlite_close_standard_zstd_verified_native_read":
        raise ValueError("Recorded native archive integrity gate did not pass")
    files = report.get("compressed_files")
    if not isinstance(files, list) or not files or len({item.get("path") for item in files}) != len(files):
        raise ValueError("Recording integrity report has no unique compressed artifacts")
    for item in files:
        path = _contained(trial/"rosbag", item["path"])
        if file_sha256(path) != item["sha256"]:
            raise ValueError("Recorded compressed artifact changed")
    if file_sha256(trial/"rosbag/metadata.yaml") != report["published_metadata_sha256"]:
        raise ValueError("Recorded archive metadata changed")
    raw, native = report.get("raw_validation", {}), report.get("native_reader_validation", {})
    if (raw.get("status") != "PASS" or native.get("status") != "PASS" or native.get("full_stream_read") is not True
            or type(raw.get("message_count")) is not int or raw["message_count"] <= 0
            or raw["message_count"] != native.get("message_count") or raw.get("topic_counts") != native.get("topic_counts")):
        raise ValueError("Recording lacks complete native stream/count correspondence")
    metadata = yaml.safe_load((trial/"rosbag/metadata.yaml").read_text(encoding="utf-8"))["rosbag2_bagfile_information"]
    if metadata.get("relative_file_paths") != [item["path"] for item in files]:
        raise ValueError("Recording metadata differs from hashed compressed file set")
    return report


def export(trial, output, *, registration=None, slot_id=None):
    trial, output = Path(trial).resolve(strict=True), Path(output)
    if output.exists():raise ValueError("Export destination already exists; refusing overwrite")
    raw_config = load(trial/"run_config.json")
    seed = raw_config["seed"]
    if type(seed) is not int or seed < 0 or raw_config.get("target_class") not in {"person", "car"}:
        raise ValueError("Explicit integer seed and supported target class are required")
    formal = seed in range(1000, 1010)
    sources = {relative:file_sha256(ROOT/relative) for relative in SOURCE_FILES}
    config = None
    if formal:
        if registration is None or slot_id is None:raise ValueError("Held-out export requires prospective registration and terminal slot")
        registration = load(registration)
        plan, terminal_path, terminal = formal_slot(trial, raw_config, registration, slot_id, sources)
    elif registration is not None or slot_id is not None:
        raise ValueError("Development exports do not masquerade as registered formal slots")
    if type(raw_config.get("stage")) is not int or raw_config["stage"] != 1 or raw_config.get("command_mode") != "velocity" or raw_config.get("multi_target") is not False:
        raise ValueError("This exporter supports only the prospectively chosen single-target stage1_velocity recording policy")
    archive = validate_recording_archive(trial)
    config = recorded_configuration(trial, raw_config["target_class"])
    saved = yaml.safe_load((trial/"configuration/runtime_parameters.yaml").read_text(encoding="utf-8"))
    estimator = saved["uav_tracking_state_estimator"]["ros__parameters"]
    previous_topics = bag_tools.TOPICS
    try:
        bag_tools.TOPICS = tuple(dict.fromkeys(previous_topics+(DIAGNOSTIC,NATIVE)))
        records, metadata = bag_tools.read_rosbag(trial/"rosbag", preserve_clock=True)
    finally:bag_tools.TOPICS = previous_topics
    if metadata.get("read_errors") or metadata.get("unavailable_types") or metadata.get("clock_records_preserved") is not True:
        raise ValueError("Bag has unreadable required records")
    diagnostics, states, interval = recorded_inputs(records)
    normalized = normalize_cycles(diagnostics)
    native_audit = verify_state_cycles(diagnostics, states)
    by_sequence = {row["diagnostic_record_sequence"]:row for row in native_audit["pairs"]}
    for event in normalized["output_events"]:
        event["diagnostic_proxy_available_s"] = event["available_s"]
        pair = by_sequence.get(event["record_sequence"])
        event["native_delivery_verified"] = pair is not None and native_audit["status"] == "PASS"
        if pair is not None:event["available_s"] = pair["native_state_availability_s"]
    parameters = {"gate_threshold":estimator["mahalanobis_gate"],
        "process_acceleration_std":estimator["process_noise_accel_mps2"],
        "measurement_noise_std":[.05,.05,.10], "initial_velocity_covariance":4., "default_dt":1./30., "max_age_s":.75}
    online_audit = evaluate_navigation_reproduction(diagnostics, parameters)
    interval, truth, truth_evidence = independent_truth(records, config, interval, normalized["task_events"])
    audit = {**normalized.pop("export_audit"), "online_equivalence":online_audit.get("evaluation_status"),
        "native_state_audit":native_audit["status"], "source_hashes":sources, "bag_reader":metadata,
        "native_archive_integrity_sha256":file_sha256(trial/"bag_integrity.json"), "scope":"FORMAL" if formal else "DEVELOPMENT_ONLY",
        "fixed_online_constructor_parameters":parameters, "recorded_archive_message_count":archive["raw_validation"]["message_count"],
        "availability_basis":"Native navigation-state recorder clock matched by source/identity/state/payload, max with publication; diagnostic proxy retained separately. Missing native correspondence remains unverified.",
        "claim_boundary":"Export, diagnostic numerical reproduction and separate state-topic correspondence only. Independent source-clock/flight acceptance and formal real-bag validation remain required."}
    # The pure online audit and separate recorded state check both must pass;
    # normalization alone never certifies reproduction.
    online_status = online_audit.get("evaluation_status", online_audit.get("status"))
    audit["status"] = ("FAIL" if online_status == "FAIL" else
        "PASS" if native_audit["status"] == "PASS" and online_status == "PASS" else "INCOMPLETE_EVIDENCE")
    result = {"schema_version":1, "target_class":raw_config["target_class"], "seed":seed,
        "group":"stage1_velocity", "interval":interval, **normalized, "truth_samples":truth,
        "truth_frame":"map", "truth_alignment_basis":"declared_enu_vehicle_only_frozen", "export_audit":audit}
    if formal:
        freeze = registration["freeze_requirements"]
        result.update(slot_id=slot_id, flight_started_utc=terminal["started_utc"], engineering_status=terminal["status"],
            bindings={key:freeze[key] for key in ("final_engineering_plan_digest", "flight_source_hashes", "model_hashes", "runtime_and_magnetic_bindings")})
        result["bindings"].update(immutable_slot_record_sha256=file_sha256(terminal_path),
            recording_artifact_hashes={path.relative_to(trial).as_posix():file_sha256(path)
                for path in sorted((trial/"rosbag").rglob("*")) if path.is_file()})
    else:result.update(slot_id="DEVELOPMENT_ONLY_"+trial.name, engineering_status="DEVELOPMENT_ONLY_NO_FORMAL_VERDICT")
    # Hash the actual normalized/scoring inputs before adding sidecar hashes.
    # All three independently checked audits retain this same non-circular
    # binding, so resealing arrays alone cannot substitute measurement or truth.
    payload_binding = {"schema_version":1, "canonical_payload_sha256":replay_payload_sha256(result),
        "excluded_circular_audit_fields":sorted(PAYLOAD_EXCLUDED_FIELDS)}
    output.mkdir(parents=True, exist_ok=False)
    for filename, evidence in (("online_equivalence.json",online_audit), ("native_state_audit.json",native_audit),
                               ("truth_alignment.json",truth_evidence)):
        evidence["replay_payload_binding"] = payload_binding
        write_new(output/filename, evidence)
    for filename, field in (("online_equivalence.json","online_equivalence_audit_sha256"),
                            ("native_state_audit.json","native_state_audit_sha256"),
                            ("truth_alignment.json","truth_alignment_evidence_sha256")):
        result[field] = file_sha256(output/filename)
    write_new(output/"arrays.json", result)
    return {"status":audit["status"], "scope":audit["scope"], "output":str(output),
            "measurements":len(result["measurements"]), "output_events":len(result["output_events"]),
            "online_equivalence_status":online_status, "native_state_audit_status":native_audit["status"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--registration", type=Path)
    parser.add_argument("--slot-id")
    args = parser.parse_args(argv)
    result = export(args.trial, args.output, registration=args.registration, slot_id=args.slot_id)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":raise SystemExit(main())
