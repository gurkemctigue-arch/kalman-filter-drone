"""Online equivalence fixtures exercise real navigation code, without bags/GT."""
from copy import deepcopy
import json
import sys
from types import SimpleNamespace
import unittest

import numpy as np

from uav_tracking import navigation_reproduction as audit


PARAMETERS = {"gate_threshold":9.21, "process_acceleration_std":.4,
    "measurement_noise_std":[.05, .05, .10], "initial_velocity_covariance":4.,
    "default_dt":1. / 30., "max_age_s":.75}


class RecordedOnlineFixture:
    """Create a recorded stream using the production estimator, then corrupt it."""
    def __init__(self):
        estimator_type, _ = audit._load_estimator_type()
        self.estimator = estimator_type(**{k:v for k, v in PARAMETERS.items() if k != "max_age_s"})
        self.measurement = None
        self.rows = []

    def emit(self, output, *, acquisition=None, uuid="task-a", track=7, candidate=2,
             position=(0., 0., 0.), velocity=(1., 0., 0.), valid=True, reason="ground_contact",
             status="tracking", output_uuid=None, output_track=None, publication=None):
        publication = output + .02 if publication is None else publication
        if acquisition is not None:
            covariance = np.diag([.01, .02, .03])
            ref = SimpleNamespace(valid=valid, reason=reason,
                position_world_m=np.asarray(position) if valid else None,
                covariance=covariance if valid else None,
                reference_kind="person_ground_contact", heading_source="not_required")
            update = self.estimator.update(ref, acquisition, uuid, track, velocity)
            self.measurement = {"diagnostic_schema_version":2, "acquisition_s":acquisition,
                "measurement_processing_s":publication, "target_uuid":uuid, "track_id":track,
                "reference_valid":valid, "reference_reason":reason,
                "raw_position_world_m":list(position) if valid else None,
                "initial_velocity_world_mps":None if velocity is None else list(velocity),
                "reference_kind":"person_ground_contact", "heading_source":"not_required",
                "fusion_accepted":update.accepted, "fusion_reason":update.reason}
            if valid:
                self.measurement.update(candidate_id=candidate, reference_covariance=covariance.tolist(),
                    reference_covariance_total=covariance.tolist())
        row = deepcopy(self.measurement)
        output_uuid = uuid if output_uuid is None else output_uuid
        output_track = track if output_track is None else output_track
        snapshot = self.estimator.project(output, output_uuid, output_track, .75, status)
        row.update(record_sequence=10 + len(self.rows), received_sim_s=publication,
            output_s=output, output_publication_s=publication, output_target_uuid=output_uuid,
            output_track_id=output_track, output_surface_status=status,
            valid=snapshot.valid, state_reason=snapshot.reason,
            measurement_age_s=snapshot.measurement_age_s,
            output_measurement_source_s=snapshot.measured_timestamp_s,
            output_position_world_m=None if snapshot.position_world_m is None else snapshot.position_world_m.tolist(),
            output_velocity_world_mps=None if snapshot.velocity_world_mps is None else snapshot.velocity_world_mps.tolist(),
            output_covariance_world_6x6=None if snapshot.covariance is None else snapshot.covariance.tolist())
        self.rows.append(row)
        return row


def ordinary_fixture():
    fixture = RecordedOnlineFixture()
    fixture.emit(1., acquisition=1.)
    fixture.emit(1.1)
    fixture.emit(1.2, acquisition=1.2, position=(.2, 0, 0))
    fixture.emit(1.3, acquisition=1.3, position=(100., 0, 0))
    fixture.emit(1.4, acquisition=1.4, valid=False, reason="empty_frame")
    fixture.emit(1.5, status="ambiguous")
    fixture.emit(1.6, acquisition=1.6, position=(.6, 0, 0), status="reacquired")
    return fixture


class NavigationReproductionTests(unittest.TestCase):
    def test_real_filter_stream_reproduces_gate_outputs_and_manual_initial_state(self):
        fixture = ordinary_fixture()
        result = audit.evaluate(fixture.rows, PARAMETERS)
        self.assertEqual(result["evaluation_status"], "PASS", result)
        self.assertEqual(result["counts"]["updates_reproduced"], 5)
        self.assertEqual(result["counts"]["repeated_measurements"], 2)
        self.assertEqual(result["counts"]["outputs_reproduced"], 7)
        initial = result["records"][0]["reproduced_output"]
        self.assertEqual(initial["output_position_world_m"], [0., 0., 0.])
        self.assertEqual(initial["output_velocity_world_mps"], [1., 0., 0.])
        np.testing.assert_allclose(np.diag(initial["output_covariance_world_6x6"]), [.01, .02, .03, 4., 4., 4.])
        self.assertFalse(result["uses_ground_truth"])
        json.dumps(result, allow_nan=False)

    def test_header_publication_and_receipt_are_separate_without_extrapolation(self):
        fixture = RecordedOnlineFixture()
        fixture.emit(1., acquisition=1., publication=1.05)
        fixture.rows[0]["received_sim_s"] = 1.08
        result = audit.evaluate(fixture.rows, PARAMETERS)
        self.assertEqual(result["evaluation_status"], "PASS")
        row = result["records"][0]
        self.assertEqual(row["availability_s"], 1.08)
        self.assertEqual(row["reproduced_output"]["output_position_world_m"], [0., 0., 0.])

    def test_duplicate_after_lost_clear_and_new_identity_does_not_refuse_or_revive(self):
        fixture = RecordedOnlineFixture()
        fixture.emit(1., acquisition=1.)
        fixture.emit(1.1, status="lost")
        fixture.emit(1.2, status="tracking")
        fixture.emit(1.3, output_uuid="", output_track=0)
        fixture.emit(1.4, output_uuid="task-b", output_track=8)
        fixture.emit(1.5, acquisition=1.5, uuid="task-b", track=8, position=(5., 0., 0.), velocity=None)
        result = audit.evaluate(fixture.rows, PARAMETERS)
        self.assertEqual(result["evaluation_status"], "PASS", result)
        self.assertEqual(result["counts"]["updates_reproduced"], 2)
        self.assertFalse(result["records"][2]["reproduced_output"]["valid"])
        self.assertEqual(result["records"][3]["reproduced_output"]["state_reason"], "invalid_identity")
        self.assertEqual(result["records"][-1]["reproduced_output"]["output_velocity_world_mps"], [0., 0., 0.])

    def test_new_invalid_task_clears_old_posterior_and_stale_output_stays_invalid(self):
        fixture = RecordedOnlineFixture()
        fixture.emit(1., acquisition=1.)
        fixture.emit(1.1, acquisition=1.1, uuid="task-b", track=8, valid=False)
        fixture.emit(1.2, acquisition=1.2, uuid="task-b", track=8)
        fixture.emit(1.951, uuid="task-b", track=8)
        result = audit.evaluate(fixture.rows, PARAMETERS)
        self.assertEqual(result["evaluation_status"], "PASS", result)
        self.assertEqual(result["records"][1]["reproduced_output"]["state_reason"], "navigation_uninitialized")
        self.assertEqual(result["records"][-1]["reproduced_output"]["state_reason"], "stale_navigation_measurement")

    def test_fusion_decisions_and_each_recorded_output_component_are_independently_checked(self):
        for field in ("fusion_accepted", "fusion_reason", "valid", "state_reason", "measurement_age_s",
                      "output_measurement_source_s", "output_position_world_m", "output_velocity_world_mps",
                      "output_covariance_world_6x6"):
            with self.subTest(field=field):
                fixture = ordinary_fixture()
                value = fixture.rows[0][field]
                if isinstance(value, bool):
                    fixture.rows[0][field] = not value
                elif isinstance(value, str):
                    fixture.rows[0][field] = "wrong"
                elif isinstance(value, list):
                    if isinstance(value[0], list):
                        fixture.rows[0][field][0][0] += .1
                    else:
                        fixture.rows[0][field][0] += .1
                else:
                    fixture.rows[0][field] += .1
                result = audit.evaluate(fixture.rows, PARAMETERS)
                self.assertEqual(result["evaluation_status"], "FAIL", result)
                self.assertTrue(any(row["field"] == field for row in result["issues"]), result)

    def test_missing_evidence_is_incomplete_and_never_filled_with_zero(self):
        for field in ("initial_velocity_world_mps", "reference_covariance_total", "output_position_world_m",
                      "candidate_id", "record_sequence", "received_sim_s", "measurement_processing_s"):
            with self.subTest(field=field):
                fixture = ordinary_fixture()
                del fixture.rows[0][field]
                result = audit.evaluate(fixture.rows, PARAMETERS)
                self.assertEqual(result["evaluation_status"], "INCOMPLETE_EVIDENCE", result)
                self.assertFalse(result["online_equivalence_pass"])
        self.assertEqual(audit.evaluate([], PARAMETERS)["evaluation_status"], "INCOMPLETE_EVIDENCE")
        fixture = ordinary_fixture()
        fixture.rows[0]["received_sim_s"] = None
        self.assertEqual(audit.evaluate(fixture.rows, PARAMETERS)["evaluation_status"], "INCOMPLETE_EVIDENCE")

    def test_every_runtime_parameter_is_explicit_and_changed_runtime_fails_numeric_equivalence(self):
        fixture = ordinary_fixture()
        for name in PARAMETERS:
            with self.subTest(name=name):
                parameters = deepcopy(PARAMETERS)
                del parameters[name]
                self.assertEqual(audit.evaluate(fixture.rows, parameters)["evaluation_status"], "INCOMPLETE_EVIDENCE")
        parameters = deepcopy(PARAMETERS)
        parameters["initial_velocity_covariance"] = 8.
        self.assertEqual(audit.evaluate(fixture.rows, parameters)["evaluation_status"], "FAIL")
        parameters["max_age_s"] = 1.
        self.assertEqual(audit.evaluate(fixture.rows, parameters)["evaluation_status"], "FAIL")

    def test_clock_proxy_tolerance_is_annotated_and_not_treated_as_exact_delivery(self):
        fixture = RecordedOnlineFixture()
        fixture.emit(1., acquisition=1., publication=1.05)
        fixture.rows[0]["received_sim_s"] = 1.01
        result = audit.evaluate(fixture.rows, PARAMETERS)
        self.assertEqual(result["evaluation_status"], "PASS", result)
        self.assertAlmostEqual(result["records"][0]["clock_proxy_lag_s"], .04)
        self.assertEqual(result["records"][0]["availability_s"], 1.05)
        fixture.rows[0]["received_sim_s"] = .99
        result = audit.evaluate(fixture.rows, PARAMETERS)
        self.assertEqual(result["evaluation_status"], "INCOMPLETE_EVIDENCE")

    def test_source_processing_header_publication_and_record_order_contradictions_fail(self):
        for defect in ("processing_before_source", "publication_before_processing", "header_after_publication",
                       "duplicate_sequence", "regressed_received", "regressed_publication"):
            with self.subTest(defect=defect):
                fixture = ordinary_fixture()
                if defect == "processing_before_source":
                    fixture.rows[0]["measurement_processing_s"] = .9
                elif defect == "publication_before_processing":
                    fixture.rows[0]["output_publication_s"] = 1.01
                elif defect == "header_after_publication":
                    fixture.rows[0]["output_s"] = 1.1
                elif defect == "duplicate_sequence":
                    fixture.rows[1]["record_sequence"] = fixture.rows[0]["record_sequence"]
                elif defect == "regressed_received":
                    fixture.rows[1]["received_sim_s"] = 1.
                else:
                    fixture.rows[1]["output_publication_s"] = 1.01
                    fixture.rows[1]["output_s"] = 1.
                self.assertEqual(audit.evaluate(fixture.rows, PARAMETERS)["evaluation_status"], "FAIL")

    def test_repeated_measurement_cannot_change_recorded_inputs_or_fusion_outcome(self):
        for name in ("raw_position_world_m", "initial_velocity_world_mps", "fusion_reason", "measurement_processing_s"):
            with self.subTest(name=name):
                fixture = ordinary_fixture()
                value = fixture.rows[1][name]
                if isinstance(value, list):
                    fixture.rows[1][name][0] += .1
                elif isinstance(value, str):
                    fixture.rows[1][name] = "wrong"
                else:
                    fixture.rows[1][name] += .01
                result = audit.evaluate(fixture.rows, PARAMETERS)
                self.assertEqual(result["evaluation_status"], "FAIL", result)
                self.assertTrue(any(row["reason"] == "repeated_measurement_evidence_changed" for row in result["issues"]))

    def test_nonfinite_input_is_fail_and_report_remains_strict_json(self):
        for field in ("output_position_world_m", "initial_velocity_world_mps", "reference_covariance_total"):
            fixture = ordinary_fixture()
            if field == "reference_covariance_total":
                fixture.rows[0][field][0][0] = float("nan")
            else:
                fixture.rows[0][field][0] = float("inf")
            result = audit.evaluate(fixture.rows, PARAMETERS)
            self.assertEqual(result["evaluation_status"], "FAIL")
            json.dumps(result, allow_nan=False)

    def test_invalid_output_cannot_be_encoded_as_fake_zero_position_or_covariance(self):
        fixture = RecordedOnlineFixture()
        fixture.emit(1., acquisition=1., valid=False)
        fixture.rows[0]["output_position_world_m"] = [0., 0., 0.]
        self.assertEqual(audit.evaluate(fixture.rows, PARAMETERS)["evaluation_status"], "FAIL")

    def test_absolute_tolerance_is_fixed_and_not_relative_to_large_coordinates(self):
        fixture = RecordedOnlineFixture()
        fixture.emit(1., acquisition=1., position=(10000., 0., 0.))
        fixture.rows[0]["output_position_world_m"][0] += 5e-9
        self.assertEqual(audit.evaluate(fixture.rows, PARAMETERS)["evaluation_status"], "PASS")
        fixture.rows[0]["output_position_world_m"][0] += 2e-8
        self.assertEqual(audit.evaluate(fixture.rows, PARAMETERS)["evaluation_status"], "FAIL")

    def test_input_is_unchanged_and_ros_workspace_path_is_not_inserted(self):
        fixture = ordinary_fixture()
        rows, parameters, path = deepcopy(fixture.rows), deepcopy(PARAMETERS), list(sys.path)
        result = audit.evaluate(fixture.rows, PARAMETERS)
        self.assertEqual(result["evaluation_status"], "PASS")
        self.assertEqual(fixture.rows, rows)
        self.assertEqual(PARAMETERS, parameters)
        self.assertEqual(sys.path, path)
        self.assertNotIn("uav_tracking._navigation_reproduction_adapter", sys.modules)


if __name__ == "__main__":
    unittest.main()
