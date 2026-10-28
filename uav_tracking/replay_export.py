"""Normalize recorded navigation diagnostic cycles without simulator truth.

The bag adapter supplies original filtered-reader sequence and delivery-clock
samples. A compound cycle retains that sequence for lifecycle, measurement
and output events; their causal suborder is declared by replay_comparison.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math

import numpy as np

from .core.uncertainty import pose_point_covariance


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Missing/nonfinite " + name)
    return float(value)


def _matrix(value, shape, name):
    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError("Missing/nonfinite " + name)
    return result


def _float32_wire(value, shape, name):
    """Apply TargetState.msg binary32 serialization, then widen for comparison.

    JSON diagnostics retain the filter's binary64 values. Only covariance
    and prediction_age_s are binary32 ROS fields; Point/Vector3 remain binary64.
    Quantized fields require exact equality, including a single-ULP change.
    """
    values = _matrix(value, shape, name)
    with np.errstate(over="ignore", invalid="ignore"):
        quantized = values.astype(np.float32).astype(np.float64)
    if not np.isfinite(quantized).all():
        raise ValueError("Nonfinite float32 wire value: " + name)
    return quantized


def normalize_cycles(diagnostics: list[dict]) -> dict:
    """Export every schema2 cycle and deduplicate only its cached measurement.

    Processing availability and output publication/recorder delivery remain
    distinct. The /clock proxy may lag publication by <=50 ms under the
    original future-time contract; this is recorded, never called zero latency.
    """
    measurements, tasks, outputs, provenance = [], [], [], []
    seen, identity, previous_sequence = set(), None, -1
    quality = Counter()
    for original in diagnostics:
        row = deepcopy(original)
        sequence = row.get("record_sequence")
        if type(sequence) is not int or sequence <= previous_sequence:
            raise ValueError("Diagnostic record_sequence must preserve unique increasing bag order")
        previous_sequence = sequence
        if row.get("diagnostic_schema_version") != 2:
            raise ValueError("Navigation diagnostic schema2 is required; old evidence cannot be fabricated")
        header = _finite(row.get("output_s"), "output state header")
        publication = _finite(row.get("output_publication_s"), "output publication")
        receipt = _finite(row.get("received_sim_s"), "recorded delivery clock")
        acquisition = _finite(row.get("acquisition_s"), "acquisition")
        processing = _finite(row.get("measurement_processing_s"), "measurement processing")
        if min(header, publication, receipt, acquisition, processing) < 0:
            raise ValueError("Negative source clock")
        if header > publication + 1e-8 or acquisition > processing + 1e-8 or processing > publication + 1e-8:
            raise ValueError("Recorded acquisition/processing/header/publication order is inconsistent")
        if publication - receipt > .05 + 1e-8:
            raise ValueError("Recorder clock proxy is more than 50 ms behind publication")
        uuid, track = row.get("target_uuid"), row.get("track_id")
        output_uuid, output_track = row.get("output_target_uuid"), row.get("output_track_id")
        if (not isinstance(uuid, str) or type(track) is not int or track < 0
                or not isinstance(output_uuid, str) or type(output_track) is not int or output_track < 0):
            raise ValueError("Explicit measurement and output task identities are required")
        key = (uuid, track, acquisition, row.get("candidate_id"))
        new_measurement = key not in seen
        seen.add(key)
        current = (output_uuid, output_track) if output_uuid and output_track > 0 else None
        state = row.get("output_surface_status")
        if state not in {"uninitialized", "tracking", "coasting", "reacquired", "ambiguous", "lost"}:
            raise ValueError("Missing/unsupported surface lifecycle")
        # A just-processed observation already owns its lifecycle by the end
        # of fusion. Timer-only cycles acquire their lifecycle at publication.
        task_time = processing if new_measurement and current == (uuid, track) else publication
        task = {"source_s":task_time, "available_s":task_time, "record_sequence":sequence}
        if current is None:
            task["action"] = "clear"
        else:
            if state == "uninitialized":
                raise ValueError("A bound output task cannot have an uninitialized lifecycle")
            task.update(action="bind" if current != identity else "state", target_uuid=output_uuid,
                        track_id=output_track, state=state)
        tasks.append(task)
        identity = current
        if new_measurement:
            reference_valid = row.get("reference_valid")
            if type(reference_valid) is not bool:
                raise ValueError("reference_valid must be explicit")
            measurement = {"acquisition_id":f"{uuid}:{track}:{acquisition:.9f}:{row.get('candidate_id')}",
                "source_s":acquisition, "available_s":processing, "record_sequence":sequence,
                "target_uuid":uuid, "track_id":track, "reference_valid":reference_valid,
                "reference_reason":str(row.get("reference_reason", "")),
                "position_world_m":row.get("raw_position_world_m"),
                "R_geometry_world_m2":row.get("reference_covariance_geometry"),
                "R_pose_world_m2":row.get("reference_covariance_pose")}
            if reference_valid:
                geometry = _matrix(measurement["R_geometry_world_m2"], (3, 3), "geometry R")
                pose = _matrix(measurement["R_pose_world_m2"], (3, 3), "pose R")
                total = _matrix(row.get("reference_covariance_total"), (3, 3), "total R")
                fused = _matrix(row.get("reference_covariance"), (3, 3), "actual fused R")
                _matrix(measurement["position_world_m"], (3,), "navigation position")
                if not np.allclose(geometry + pose, total, rtol=0., atol=1e-8) or not np.allclose(total, fused, rtol=0., atol=1e-8):
                    raise ValueError("Recorded R components do not reconstruct the actual fused R")
                if row.get("quality_scale_applied") is not False:
                    raise ValueError("Unexpected undeclared navigation quality scaling")
                if row.get("pose_uncertainty_source") == "measured_vehicle_odometry":
                    pose_stamp = _finite(row.get("chosen_pose_source_s"), "chosen pose source")
                    if abs(pose_stamp-acquisition) > .05 + 1e-8:
                        raise ValueError("Chosen pose violates the original 50 ms synchronization window")
                    reconstructed_pose = pose_point_covariance(measurement["position_world_m"],
                        row.get("chosen_pose_position_world_m"), row.get("chosen_pose_covariance_world_6x6"))
                elif row.get("pose_uncertainty_source") == "declared_isotropic_position_std":
                    declared = _finite(row.get("declared_pose_std_m"), "declared pose standard deviation")
                    if declared < 0:raise ValueError("Negative declared pose standard deviation")
                    reconstructed_pose = np.eye(3) * declared**2
                else:
                    raise ValueError("Missing exact pose covariance provenance")
                if not np.allclose(reconstructed_pose, pose, rtol=0., atol=1e-8):
                    raise ValueError("Pose covariance disagrees with its exact source sample")
            measurements.append(measurement)
            quality.update(row.get("missing_quality_fields", []))
            quality.update(row.get("invalid_quality_fields", []))
            provenance.append(row)
        outputs.append({"source_s":publication, "state_source_s":header,
                        "available_s":max(publication, receipt), "record_sequence":sequence})
    if not outputs:
        raise ValueError("No actual navigation output opportunities")
    return {"measurements":measurements, "task_events":tasks, "output_events":outputs,
            "measurement_provenance":provenance,
            "export_audit":{"status":"NORMALIZED_PENDING_NATIVE_STATE_AND_ONLINE_EQUIVALENCE",
                "diagnostic_cycles":len(outputs), "deduplicated_measurements":len(measurements),
                "cached_measurement_repeats":len(outputs)-len(measurements),
                "missing_or_invalid_quality_fields":dict(quality),
                "clock_proxy_policy":"max(publication, latest recorded clock), original 50 ms future tolerance; no assertion of exact transport latency",
                "record_sequence_policy":"Original diagnostic filtered-reader bag order; compound lifecycle/measurement/output share the same sequence"}}


def verify_state_cycles(diagnostics: list[dict], native_states: list[dict]) -> dict:
    """Match each diagnostic output to its separately recorded native state.

    Matching uses recorded header, identity, lifecycle and numeric payload;
    it never reads target truth or fits offsets. State delivery remains in
    this audit, rather than silently replacing the diagnostic delivery proxy.
    Covariance and age follow TargetState.msg float32 serialization exactly;
    binary64 position/velocity retain the original absolute 1e-8 comparison.
    """
    differences, pairs = [], []
    diagnostics = diagnostics if isinstance(diagnostics, list) else []
    native_states = native_states if isinstance(native_states, list) else []
    if not diagnostics:
        differences.append({"reason":"missing_navigation_diagnostics"})
    if not native_states:
        differences.append({"reason":"missing_native_navigation_states"})
    # Delivery is a quantized recorder clock, not publication or acquisition.
    # Preserve stale arrivals as evidence instead of making their age zero.
    eligible = []
    previous_sequence = previous_receipt = None
    for state in native_states:
        try:
            sequence = state.get("record_sequence")
            if type(sequence) is not int or sequence < 0 or (previous_sequence is not None and sequence <= previous_sequence):
                raise ValueError("invalid_native_record_sequence")
            previous_sequence = sequence
            source = _finite(state.get("source_s"), "native state header")
            receipt = _finite(state.get("received_sim_s"), "native delivery clock")
            age = _finite(state.get("measurement_age_s"), "native measurement age")
            if min(source, receipt, age) < 0.:
                raise ValueError("negative_native_time_or_age")
            if source - receipt > .05 + 1e-8:
                raise ValueError("native_header_exceeds_recorder_future_tolerance")
            if previous_receipt is not None and receipt < previous_receipt - 1e-8:
                raise ValueError("native_recorder_clock_regressed")
            previous_receipt = receipt
            if state.get("frame_id") != "map":
                raise ValueError("native_state_frame_is_not_map")
            if (not isinstance(state.get("target_uuid"), str) or type(state.get("track_id")) is not int
                    or state["track_id"] < 0 or type(state.get("state")) is not int or state["state"] not in range(5)):
                raise ValueError("invalid_native_identity_or_state")
            for key, shape in (("position_world_m", (3,)), ("velocity_world_mps", (3,)), ("covariance_world_6x6", (6, 6))):
                _matrix(state.get(key), shape, "native " + key)
            eligible.append(state)
        except (AttributeError, TypeError, ValueError, OverflowError) as error:
            differences.append({"record_sequence":state.get("record_sequence") if isinstance(state, dict) else None,
                                "reason":"invalid_native_state_evidence:" + str(error)})
    unmatched = list(eligible)
    previous_diagnostic_sequence = None
    for row in diagnostics:
        try:
            if not isinstance(row, dict):
                raise ValueError("invalid_navigation_diagnostic")
            sequence = row.get("record_sequence")
            if type(sequence) is not int or sequence < 0 or (previous_diagnostic_sequence is not None and sequence <= previous_diagnostic_sequence):
                raise ValueError("invalid_diagnostic_record_sequence")
            previous_diagnostic_sequence = sequence
            header = _finite(row.get("output_s"), "diagnostic output header")
            publication = _finite(row.get("output_publication_s"), "diagnostic publication")
            if min(header, publication) < 0. or header > publication + 1e-8:
                raise ValueError("invalid_diagnostic_output_time")
            if (type(row.get("valid")) is not bool or not isinstance(row.get("output_target_uuid"), str)
                    or type(row.get("output_track_id")) is not int or row["output_track_id"] < 0
                    or type(row.get("output_state")) is not int or row["output_state"] not in range(5)):
                raise ValueError("invalid_diagnostic_identity_or_validity")
            if row["valid"]:
                for key, shape in (("output_position_world_m", (3,)), ("output_velocity_world_mps", (3,)),
                                   ("output_covariance_world_6x6", (6, 6))):
                    _matrix(row.get(key), shape, key)
        except (TypeError, ValueError, OverflowError) as error:
            differences.append({"record_sequence":row.get("record_sequence") if isinstance(row, dict) else None,
                                "reason":"invalid_navigation_diagnostic:" + str(error)})
            continue
        matched = None
        for index, state in enumerate(unmatched):
            if (abs(state["source_s"]-header) <= 1e-8
                    and state["target_uuid"] == row["output_target_uuid"]
                    and state["track_id"] == row["output_track_id"]
                    and state["state"] == row["output_state"]):
                matched = unmatched.pop(index)
                break
        if matched is None:
            differences.append({"record_sequence":row["record_sequence"], "reason":"missing_separate_navigation_state"})
            continue
        try:
            valid = row.get("valid")
            if type(valid) is not bool or valid != (matched["state"] in (1, 2)):
                raise ValueError("native_validity_disagrees")
            diagnostic_age = row.get("measurement_age_s")
            if valid and diagnostic_age is None:
                raise ValueError("valid_diagnostic_requires_explicit_measurement_age")
            age = 0. if diagnostic_age is None else _finite(diagnostic_age, "diagnostic measurement age")
            if age < 0.:raise ValueError("negative_diagnostic_measurement_age")
            if valid:
                measured = _finite(row.get("output_measurement_source_s"), "last accepted measurement source")
                if age > .75 + 1e-8 or abs(matched["source_s"] - measured - age) > 1e-8:
                    raise ValueError("native_measurement_age_inconsistent_with_source_or_horizon")
            expected_wire_age = float(_float32_wire(age, (), "prediction_age_s"))
            if matched["measurement_age_s"] != expected_wire_age:
                raise ValueError("native_measurement_age_disagrees_after_float32_wire_quantization")
        except (TypeError, ValueError, OverflowError) as error:
            differences.append({"record_sequence":row.get("record_sequence"), "reason":str(error)})
        for key, diagnostic_key in (("position_world_m", "output_position_world_m"),
                                    ("velocity_world_mps", "output_velocity_world_mps"),
                                    ("covariance_world_6x6", "output_covariance_world_6x6")):
            # Invalid ROS TargetState intentionally publishes finite zero
            # placeholders; diagnostic nulls prevent treating them as estimates.
            if row.get("valid") is True:
                try:
                    same = (np.array_equal(np.asarray(matched[key]), _float32_wire(row[diagnostic_key], (6, 6), "covariance"))
                            if key == "covariance_world_6x6" else
                            np.allclose(matched[key], row[diagnostic_key], rtol=0., atol=1e-8))
                except ValueError:
                    same = False
                if not same:
                    differences.append({"record_sequence":row["record_sequence"], "reason":"native_state_payload_disagrees:"+key})
            elif row.get("valid") is False and (row.get(diagnostic_key) is not None or np.any(np.asarray(matched[key]) != 0.)):
                differences.append({"record_sequence":row["record_sequence"], "reason":"invalid_state_placeholder_disagrees:"+key})
        delivery = max(row["output_publication_s"], matched["received_sim_s"])
        delivered_age = matched["measurement_age_s"] + delivery - matched["source_s"]
        pairs.append({"diagnostic_record_sequence":row["record_sequence"],
                      "native_state_record_sequence":matched["record_sequence"],
                      "native_state_received_sim_s":matched["received_sim_s"],
                      "native_state_availability_s":delivery,
                      "native_state_measurement_age_s":matched["measurement_age_s"],
                      "delivered_measurement_age_s":delivered_age if row.get("valid") is True else None,
                      "delivery_within_prediction_horizon":delivered_age <= .75 + 1e-8 if row.get("valid") is True else None})
    if unmatched:
        differences.append({"reason":"native_states_without_matching_diagnostics", "count":len(unmatched)})
    return {"status":"PASS" if not differences else "INCOMPLETE_EVIDENCE", "pairs":pairs,
            "diagnostic_count":len(diagnostics), "native_state_count":len(native_states), "differences":differences,
            "numeric_contract":{
                "schema":"ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg",
                "covariance_world_6x6":"float32[36]; cast diagnostic to binary32, widen to binary64, exact equality",
                "measurement_age_s":"float32; check diagnostic binary64 age against source/header first, then exact binary32 wire equality",
                "position_and_velocity":"geometry_msgs Point/Vector3 binary64; rtol=0, atol=1e-8",
                "online_diagnostic_reproduction":"Separate binary64 audit retains rtol=0, atol=1e-8"}}
