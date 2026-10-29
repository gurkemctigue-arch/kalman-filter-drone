"""Compute candidate R0 from the two prospectively named development slots.

Array-only: no ROS, bags, metric optimization, target-truth fit or registration.
The output is candidate evidence; final prospective registration is separate.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_reliability_v4 as engineering
import run_estimator_replay_v4 as replay
from uav_tracking.replay_comparison import EXPORT_SOURCE_FILES, SOURCE_FILES

SEED = 4
POLICY = "planning/reliability-v4-calibration-policy-draft.md"


def finite(value):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError("Finite numeric acquisition time required")
    return float(value)


def geometry_statistics(trial):
    """Use every independent valid geometry opportunity, including KF rejects.

    Selection reads time, identity, reference-validity and geometry R only.
    Neither truth nor posterior acceptance influences sample membership.
    """
    start = finite(trial["interval"]["follow_start_s"])
    end = finite(trial["interval"]["recorded_clock_end_s"])
    if end <= start:
        raise ValueError("A complete positive FOLLOW interval is required")
    excluded, seen, matrices, selected = Counter(), {}, [], []
    rows = trial["measurements"]
    for row in rows:
        stamp = finite(row["source_s"])
        if not start <= stamp <= end:
            excluded["outside_follow_to_full_clock"] += 1
            continue
        if type(row.get("reference_valid")) is not bool:
            raise ValueError("Explicit geometry reference validity required")
        if not row["reference_valid"]:
            excluded["invalid_reference:" + str(row.get("reference_reason", "unspecified"))] += 1
            continue
        uuid, track = row.get("target_uuid"), row.get("track_id")
        if not isinstance(uuid, str) or not uuid or type(track) is not int or track < 0:
            raise ValueError("Valid geometry has no task/track identity")
        matrix = row.get("R_geometry_world_m2")
        # bool is not a physically meaningful covariance entry.
        if (not isinstance(matrix, list) or len(matrix) != 3
                or any(not isinstance(line, list) or len(line) != 3 for line in matrix)
                or any(type(value) not in (int, float) for line in matrix for value in line)):
            raise ValueError("Invalid geometry covariance shape/type")
        covariance = np.asarray(matrix, dtype=float)
        if (not np.isfinite(covariance).all()
                or not np.allclose(covariance, covariance.T, rtol=0., atol=1e-10)
                or np.linalg.eigvalsh(covariance).min() < -1e-10):
            raise ValueError("Invalid geometry covariance")
        key = (uuid, track, stamp)
        if key in seen:
            if not np.array_equal(seen[key], covariance):
                raise ValueError("Repeated acquisition has conflicting geometry covariance")
            excluded["duplicate_acquisition"] += 1
            continue
        identifier = row.get("acquisition_id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Missing acquisition provenance")
        seen[key] = covariance
        matrices.append(covariance)
        selected.append({"acquisition_id": identifier, "target_uuid": uuid,
                         "track_id": track, "source_s": stamp})
    if not matrices:
        raise ValueError("No independent valid geometry observations")
    mean = np.mean(matrices, axis=0)
    eigenvalues = np.linalg.eigvalsh(mean)
    if eigenvalues.min() <= 1e-12:
        raise ValueError("Mean geometry covariance is not strictly positive definite; no implicit jitter")
    return {"R0_sensor_world_m2": mean.tolist(), "eigenvalues_m2": eigenvalues.tolist(),
            "total_measurement_opportunities": len(rows), "independent_valid_geometry": len(matrices),
            "excluded_counts": dict(excluded), "selected_acquisitions": selected,
            "interval": {"follow_start_s": start, "recorded_clock_end_s": end}}


def bind_named_recording(slot, record, trial):
    """Bind small immutable recording evidence without reopening any bag."""
    directory = Path(slot["directory"]).resolve(strict=True)
    hashes = record.get("artifact_hashes", {})
    bindings = {}
    for name in ("run_config.json", "bag_integrity.json"):
        path = directory / name
        actual = replay.file_sha256(path)
        if actual != hashes.get(name):
            raise ValueError("Named calibration recording evidence changed: " + name)
        bindings[name] = {"path": str(path), "sha256": actual}
    configuration = replay.load(directory / "run_config.json")
    if (configuration.get("seed") != SEED or configuration.get("target_class") != slot["target_class"]
            or configuration.get("command_mode") != "velocity"):
        raise ValueError("Named development runtime configuration differs")
    audit = trial["export_audit"]
    if (Path(audit.get("bag_reader", {}).get("bag", "")).resolve() != directory / "rosbag"
            or audit.get("native_archive_integrity_sha256") != bindings["bag_integrity.json"]["sha256"]):
        raise ValueError("Export does not bind the named terminal recording archive")
    return bindings


def calibrate(plan_path, array_paths, output, *, source_root=ROOT):
    plan_path = Path(plan_path).resolve(strict=True)
    plan = engineering.load(plan_path)
    # Reject formal plans before opening any measurement arrays.
    if (plan.get("mode") != "PROBE" or plan.get("selected_seeds") != [SEED]
            or plan.get("selected_classes") != list(engineering.CLASSES)
            or plan.get("selected_groups") != list(engineering.GROUPS)):
        raise ValueError("Calibration requires the prospectively named complete two-class/six-group seed004 PROBE plan")
    engineering.validate_plan(plan, plan_path)
    records = engineering.read_slots(plan, verify_artifacts=False)
    sources = {relative: replay.file_sha256(Path(source_root) / relative) for relative in EXPORT_SOURCE_FILES}
    audit_configuration = {"freeze_requirements": {
        "evaluation_source_hashes": sources,
        "offline_replay_source_hashes": {name: sources[name] for name in SOURCE_FILES},
        "flight_source_hashes": plan["source_hashes"]}}
    classes, provenance = {}, {}
    for cls in engineering.CLASSES:
        slot_id = f"{cls}_stage1_velocity_seed{SEED:03d}"
        slot = next(row for row in plan["trials"] if row["id"] == slot_id)
        record = records[slot_id]
        if (record.get("status") not in engineering.TERMINAL
                or record.get("execution_status") != "COMPLETED"
                or record.get("infrastructure_stop") is not False
                or record.get("flight_exit_code") != 0):
            raise ValueError("Named calibration slot is not complete; no substitution permitted: " + slot_id)
        path = Path(array_paths[cls]).resolve(strict=True)
        trial = replay.load(path)
        if (trial.get("seed") != SEED or trial.get("target_class") != cls
                or trial.get("group") != "stage1_velocity"
                or trial.get("slot_id") != "DEVELOPMENT_ONLY_" + slot["name"]):
            raise ValueError("Calibration arrays do not belong to the predefined development slot")
        recording_bindings = bind_named_recording(slot, record, trial)
        receipt = replay.verify_export_evidence(path, trial, audit_configuration,
                                                source_root=source_root, development_only=True)
        classes[cls] = geometry_statistics(trial)
        record_path = engineering.record_path(plan, slot)
        provenance[cls] = {"slot_id": slot_id, "engineering_status": record["status"],
            "terminal_record": {"path": str(record_path), "sha256": replay.file_sha256(record_path)},
            "arrays": {"path": str(path), "sha256": replay.file_sha256(path)},
            "recording_evidence": recording_bindings,
            "verified_export_evidence": receipt}
    result = {"schema_version": 1, "kind": "RELIABILITY_V4_DEVELOPMENT_CALIBRATION",
        "status": "CANDIDATE_NOT_REGISTERED", "scope": "DEVELOPMENT_ONLY",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "policy": {"path": POLICY, "sha256": replay.file_sha256(Path(source_root) / POLICY)},
        "development_plan": {"path": str(plan_path), "sha256": replay.file_sha256(plan_path),
                             "plan_sha256": plan["plan_sha256"]},
        "provenance": provenance, "classes": classes,
        "candidate_parameters": {
            "R0_sensor_world_m2_by_class": {cls: value["R0_sensor_world_m2"] for cls, value in classes.items()},
            "Q_model_and_parameters": {"model": "piecewise_constant_acceleration", "acceleration_std_mps2": 1.},
            "P0_matrix_and_initial_velocity_policy": {"covariance_6x6": np.diag([1., 1., 1., 4., 4., 4.]).tolist(),
                "velocity_policy": "registered_constant", "initial_velocity_mps": [0., 0., 0.]},
            "ema_alpha": .35,
            "common_gate_R_and_initialization_policy": {"measurement_covariance": "geometry_plus_pose",
                "initialization": "common_P0", "threshold_squared": 9.21},
            "common_support_truth_coverage_requirement": .8},
        "source_hashes": {"scripts/calibrate_estimator_replay_v4.py": replay.file_sha256(Path(__file__))},
        "claim_boundary": "Candidate development statistics only; does not register parameters, certify full engineering acceptance or read held-out outcomes."}
    engineering.write_new(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--person-arrays", type=Path, required=True)
    parser.add_argument("--car-arrays", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = calibrate(args.plan, {"person": args.person_arrays, "car": args.car_arrays}, args.output)
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
