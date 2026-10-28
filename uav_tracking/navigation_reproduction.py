"""Reproduce schema-2 online navigation diagnostics without ROS or truth.

``evaluate_navigation_reproduction`` accepts flat diagnostic payloads augmented
with the original ``record_sequence`` and the recorder's latest observed
``received_sim_s``. Measurement processing, output header, publication and
recorder delivery remain separate. The latter clock is a quantized proxy: a
publication at most 50 ms ahead is annotated, using the existing future-clock
tolerance, and availability is max(publication, proxy). This never proves zero
transport delay or replaces the separate source-clock/export audits.

All constructor parameters are explicit. The real ROS-free NavigationEstimator
source is loaded without changing sys.path, and is called once per distinct
measurement and once per recorded output. No GT, alignment fitting, replacement
measurements, synthetic zeros or comparison-estimator parameters are used.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import math
from numbers import Real
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import numpy as np

ABSOLUTE_TOLERANCE = 1e-8
RECORDER_CLOCK_FUTURE_TOLERANCE_S = .05
PARAMETERS = ("gate_threshold", "process_acceleration_std", "measurement_noise_std",
              "initial_velocity_covariance", "default_dt", "max_age_s")
MEASUREMENT_FIELDS = ("acquisition_s", "target_uuid", "track_id", "reference_valid",
    "reference_reason", "raw_position_world_m", "initial_velocity_world_mps",
    "measurement_processing_s", "fusion_accepted", "fusion_reason")
OUTPUT_FIELDS = ("output_s", "output_publication_s", "output_target_uuid", "output_track_id",
    "output_surface_status", "valid", "state_reason", "measurement_age_s",
    "output_measurement_source_s", "output_position_world_m", "output_velocity_world_mps",
    "output_covariance_world_6x6")


class _EvidenceError(ValueError):
    def __init__(self, field: str, reason: str, *, incomplete: bool = False):
        super().__init__(reason)
        self.field, self.reason, self.incomplete = field, reason, incomplete


def _finite(value: Any, field: str, *, nonnegative: bool = True) -> float:
    if (not isinstance(value, Real) or isinstance(value, (bool, np.bool_))
            or not math.isfinite(float(value)) or nonnegative and value < 0):
        raise _EvidenceError(field, "expected_finite_nonnegative_number" if nonnegative else "expected_finite_number")
    return float(value)


def _integer(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise _EvidenceError(field, "expected_nonnegative_integer")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise _EvidenceError(field, "expected_explicit_string")
    return value


def _boolean(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise _EvidenceError(field, "expected_explicit_boolean")
    return value


def _array(value: Any, shape: tuple[int, ...], field: str, *, covariance: bool = False) -> np.ndarray:
    def has_boolean(item):
        if isinstance(item, (bool, np.bool_)):
            return True
        return isinstance(item, (list, tuple, np.ndarray)) and any(has_boolean(x) for x in item)
    try:
        matrix = np.asarray(value)
        valid = (matrix.shape == shape and matrix.dtype.kind in "iuf"
                 and not has_boolean(value) and np.isfinite(matrix).all())
    except (TypeError, ValueError, OverflowError):
        valid = False
    if not valid:
        raise _EvidenceError(field, "expected_finite_array_with_shape_" + str(shape))
    matrix = matrix.astype(float)
    if covariance and (not np.allclose(matrix, matrix.T, rtol=0., atol=1e-10)
                       or np.linalg.eigvalsh(matrix).min() < -1e-10):
        raise _EvidenceError(field, "expected_symmetric_positive_semidefinite_covariance")
    return matrix


def _required(row: dict, names: tuple[str, ...]) -> None:
    absent = [name for name in names if name not in row]
    if absent:
        raise _EvidenceError(",".join(absent), "missing_required_fields", incomplete=True)


def _equivalent(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, (bool, np.bool_)) or isinstance(right, (bool, np.bool_)):
        return type(left) is bool and type(right) is bool and left == right
    if isinstance(left, Real) and isinstance(right, Real):
        return (math.isfinite(float(left)) and math.isfinite(float(right))
                and abs(float(left) - float(right)) <= ABSOLUTE_TOLERANCE)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_equivalent(left[k], right[k]) for k in left)
    if isinstance(left, (list, tuple, np.ndarray)) and isinstance(right, (list, tuple, np.ndarray)):
        return len(left) == len(right) and all(_equivalent(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def _load_estimator_type():
    """Load the actual adapter source without adding a ROS workspace to sys.path."""
    path = Path(__file__).resolve().parents[1] / "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py"
    if not path.is_file():
        from uav_tracking_nodes.navigation_estimator import NavigationEstimator
        module = sys.modules[NavigationEstimator.__module__]
        path = Path(module.__file__).resolve()
        return NavigationEstimator, {"path":str(path), "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    source = path.read_bytes()
    name = "uav_tracking._navigation_reproduction_adapter"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    sys.modules[name] = module  # dataclass resolves annotations during definition.
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module.NavigationEstimator, {"path":str(path), "sha256":hashlib.sha256(source).hexdigest()}


def evaluate_navigation_reproduction(diagnostics: list[dict], runtime_kf_parameters: dict) -> dict:
    """Return PASS, FAIL or INCOMPLETE_EVIDENCE for online numerical equivalence.

    Runtime keys are all NavigationEstimator constructor arguments plus
    ``max_age_s``; the latter must retain the registered 0.75 s horizon.
    Invalid/missing state inputs taint subsequent reconstruction rather than
    inventing a posterior. Repeated old measurement diagnostics never reapply
    an update, including after LOST, a clear identity or a new task.
    """
    report = {"schema_version":1, "audit_kind":"ONLINE_NAVIGATION_DIAGNOSTIC_REPRODUCTION",
        "evaluation_status":"INCOMPLETE_EVIDENCE", "online_equivalence_pass":False,
        "absolute_tolerance":ABSOLUTE_TOLERANCE, "relative_tolerance":0., "uses_ground_truth":False,
        "recorder_clock_future_tolerance_s":RECORDER_CLOCK_FUTURE_TOLERANCE_S,
        "availability_basis":"max(output_publication_s, received_sim_s); latest clock proxy is quantized",
        "claim_boundary":"Numerical diagnostic reproduction only; independent source-clock, actual-state-topic and export audits remain required",
        "runtime_kf_parameters":None, "issues":[], "records":[],
        "counts":{"diagnostics":0, "distinct_measurements":0, "repeated_measurements":0,
                  "updates_reproduced":0, "outputs_reproduced":0}}

    def issue(field, reason, sequence=None, *, incomplete=False):
        report["issues"].append({"record_sequence":sequence, "field":field,
                                 "reason":reason, "severity":"INCOMPLETE" if incomplete else "FAIL"})

    def finalize():
        severities = {row["severity"] for row in report["issues"]}
        status = "FAIL" if "FAIL" in severities else "INCOMPLETE_EVIDENCE" if "INCOMPLETE" in severities else "PASS"
        report.update(evaluation_status=status, online_equivalence_pass=status == "PASS")
        return report

    try:
        if not isinstance(runtime_kf_parameters, dict):
            raise _EvidenceError("runtime_kf_parameters", "missing_explicit_parameter_map", incomplete=True)
        _required(runtime_kf_parameters, PARAMETERS)
        parameters = {}
        for name in PARAMETERS:
            if name == "measurement_noise_std":
                noise = _array(runtime_kf_parameters[name], (3,), name)
                if np.any(noise <= 0.):
                    raise _EvidenceError(name, "expected_positive_noise_standard_deviations")
                parameters[name] = noise.tolist()
            else:
                parameters[name] = _finite(runtime_kf_parameters[name], name)
                if parameters[name] <= 0.:
                    raise _EvidenceError(name, "expected_positive_parameter")
        if not _equivalent(parameters["max_age_s"], .75):
            raise _EvidenceError("max_age_s", "registered_prediction_horizon_must_equal_0.75")
        estimator_type, provenance = _load_estimator_type()
        estimator = estimator_type(**{name:value for name, value in parameters.items() if name != "max_age_s"})
        report["runtime_kf_parameters"] = parameters
        report["navigation_estimator_source"] = provenance
    except _EvidenceError as error:
        issue(error.field, error.reason, incomplete=error.incomplete)
        return finalize()
    except (ImportError, OSError, TypeError, ValueError) as error:
        issue("navigation_estimator", "cannot_construct_actual_estimator:" + str(error), incomplete=True)
        return finalize()
    if not isinstance(diagnostics, list) or not diagnostics:
        issue("diagnostics", "no_recorded_diagnostics", incomplete=True)
        return finalize()

    cache = {}
    last_sequence = last_publication = last_received = None
    tainted = False
    for row in diagnostics:
        report["counts"]["diagnostics"] += 1
        entry = {"record_sequence":None, "measurement_repeated":None,
                 "update_reproduced":False, "output_reproduced":False, "mismatches":[]}
        report["records"].append(entry)
        sequence = None
        try:
            if not isinstance(row, dict):
                raise _EvidenceError("diagnostic", "expected_flat_diagnostic_object", incomplete=True)
            _required(row, ("record_sequence", "received_sim_s", "diagnostic_schema_version") + MEASUREMENT_FIELDS + OUTPUT_FIELDS)
            sequence = _integer(row["record_sequence"], "record_sequence")
            entry["record_sequence"] = sequence
            if type(row["diagnostic_schema_version"]) is not int or row["diagnostic_schema_version"] != 2:
                raise _EvidenceError("diagnostic_schema_version", "schema_2_required", incomplete=True)
            if last_sequence is not None and sequence <= last_sequence:
                raise _EvidenceError("record_sequence", "record_order_not_strictly_increasing")
            last_sequence = sequence
            acquisition = _finite(row["acquisition_s"], "acquisition_s")
            processing = _finite(row["measurement_processing_s"], "measurement_processing_s")
            output = _finite(row["output_s"], "output_s")
            publication = _finite(row["output_publication_s"], "output_publication_s")
            if row["received_sim_s"] is None:
                raise _EvidenceError("received_sim_s", "no_observed_recorder_clock", incomplete=True)
            received = _finite(row["received_sim_s"], "received_sim_s")
            entry.update(acquisition_s=acquisition, output_s=output,
                         output_publication_s=publication, received_sim_s=received,
                         availability_s=max(publication, received))
            if acquisition > processing + ABSOLUTE_TOLERANCE:
                raise _EvidenceError("measurement_processing_s", "processing_precedes_acquisition")
            if processing > publication + ABSOLUTE_TOLERANCE or output > publication + ABSOLUTE_TOLERANCE:
                raise _EvidenceError("output_publication_s", "publication_precedes_processing_or_output_header")
            if last_publication is not None and publication < last_publication - ABSOLUTE_TOLERANCE:
                raise _EvidenceError("output_publication_s", "publication_clock_regressed")
            if last_received is not None and received < last_received - ABSOLUTE_TOLERANCE:
                raise _EvidenceError("received_sim_s", "recorder_clock_regressed")
            last_publication, last_received = publication, received
            lag = max(0., publication - received)
            entry["clock_proxy_lag_s"] = lag
            if lag > RECORDER_CLOCK_FUTURE_TOLERANCE_S + ABSOLUTE_TOLERANCE:
                issue("received_sim_s", "recorder_clock_proxy_lag_exceeds_original_future_tolerance", sequence, incomplete=True)
            uuid, track = _text(row["target_uuid"], "target_uuid"), _integer(row["track_id"], "track_id")
            candidate = row.get("candidate_id")
            if candidate is not None:
                candidate = _integer(candidate, "candidate_id")
            valid = _boolean(row["reference_valid"], "reference_valid")
            reason = _text(row["reference_reason"], "reference_reason")
            initial_velocity = row["initial_velocity_world_mps"]
            if initial_velocity is not None:
                initial_velocity = _array(initial_velocity, (3,), "initial_velocity_world_mps").tolist()
            position, covariance = row["raw_position_world_m"], row.get("reference_covariance_total")
            if valid:
                _required(row, ("candidate_id", "reference_covariance_total", "reference_kind", "heading_source"))
                if candidate is None:
                    raise _EvidenceError("candidate_id", "valid_reference_requires_selected_candidate", incomplete=True)
                position = _array(position, (3,), "raw_position_world_m")
                covariance = _array(covariance, (3, 3), "reference_covariance_total", covariance=True)
                if "reference_covariance" in row and not _equivalent(row["reference_covariance"], covariance):
                    issue("reference_covariance", "combined_covariance_alias_disagrees_with_total", sequence)
            accepted = _boolean(row["fusion_accepted"], "fusion_accepted")
            fusion_reason = _text(row["fusion_reason"], "fusion_reason")
            output_uuid = _text(row["output_target_uuid"], "output_target_uuid")
            output_track = _integer(row["output_track_id"], "output_track_id")
            status = _text(row["output_surface_status"], "output_surface_status")
            expected_valid = _boolean(row["valid"], "valid")
            expected_reason = _text(row["state_reason"], "state_reason")
            for name in ("measurement_age_s", "output_measurement_source_s"):
                if row[name] is not None:
                    _finite(row[name], name)
            for name, shape in (("output_position_world_m", (3,)), ("output_velocity_world_mps", (3,)),
                                ("output_covariance_world_6x6", (6, 6))):
                # A corrupt recorded output does not alter the actual filter
                # inputs. Continue reconstruction and compare validity too.
                try:
                    if expected_valid:
                        _array(row[name], shape, name, covariance=name.endswith("6x6"))
                    elif row[name] is not None:
                        raise _EvidenceError(name, "invalid_output_must_record_null_not_fabricated_zero")
                except _EvidenceError as error:
                    issue(error.field, error.reason, sequence)

            key = (acquisition, uuid, track, candidate)
            signature = {name:deepcopy(row.get(name)) for name in MEASUREMENT_FIELDS
                         + ("candidate_id", "reference_covariance_total", "reference_covariance", "reference_kind", "heading_source")}
            repeated = key in cache
            entry["measurement_repeated"] = repeated
            report["counts"]["repeated_measurements" if repeated else "distinct_measurements"] += 1
            if tainted:
                issue("posterior", "unverifiable_after_missing_or_invalid_state_input", sequence, incomplete=True)
                continue
            if repeated:
                prior_signature, update = cache[key]
                if not _equivalent(signature, prior_signature):
                    raise _EvidenceError("measurement", "repeated_measurement_evidence_changed")
            else:
                reference = SimpleNamespace(valid=valid, reason=reason, position_world_m=position,
                    covariance=covariance, reference_kind=row.get("reference_kind", "unknown"),
                    heading_source=row.get("heading_source", "unknown"))
                update = estimator.update(reference, timestamp=acquisition, target_uuid=uuid,
                                          track_id=track, initial_velocity=initial_velocity)
                cache[key] = (signature, update)
                entry["update_reproduced"] = True
                report["counts"]["updates_reproduced"] += 1
            for name, actual, expected in (("fusion_accepted", update.accepted, accepted),
                                          ("fusion_reason", update.reason, fusion_reason)):
                if not _equivalent(actual, expected):
                    entry["mismatches"].append(name)
                    issue(name, "recorded_value_differs_from_actual_estimator", sequence)
            snapshot = estimator.project(output, target_uuid=output_uuid, track_id=output_track,
                                         max_age=parameters["max_age_s"], surface_status=status)
            reproduced = {"valid":snapshot.valid, "state_reason":snapshot.reason,
                "measurement_age_s":snapshot.measurement_age_s,
                "output_measurement_source_s":snapshot.measured_timestamp_s,
                "output_position_world_m":None if snapshot.position_world_m is None else snapshot.position_world_m.tolist(),
                "output_velocity_world_mps":None if snapshot.velocity_world_mps is None else snapshot.velocity_world_mps.tolist(),
                "output_covariance_world_6x6":None if snapshot.covariance is None else snapshot.covariance.tolist()}
            entry["reproduced_output"] = reproduced
            entry["output_reproduced"] = True
            report["counts"]["outputs_reproduced"] += 1
            for name, actual in reproduced.items():
                if not _equivalent(actual, row[name]):
                    entry["mismatches"].append(name)
                    issue(name, "recorded_value_differs_from_actual_estimator", sequence)
        except _EvidenceError as error:
            issue(error.field, error.reason, sequence, incomplete=error.incomplete)
            tainted = True
        except (TypeError, ValueError, OverflowError, np.linalg.LinAlgError) as error:
            issue("reproduction", "cannot_reproduce:" + str(error), sequence)
            tainted = True
    return finalize()


evaluate = evaluate_navigation_reproduction
