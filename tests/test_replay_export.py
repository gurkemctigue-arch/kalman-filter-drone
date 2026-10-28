"""Recording export preserves causality, missingness and actual covariance."""
from copy import deepcopy
import unittest

import numpy as np

from uav_tracking.replay_export import normalize_cycles, verify_state_cycles


def cycle(sequence=1):
    return {"diagnostic_schema_version":2, "record_sequence":sequence, "received_sim_s":1.04,
        "acquisition_s":1., "measurement_processing_s":1.05, "output_s":1., "output_publication_s":1.05,
        "target_uuid":"selected-A", "track_id":1, "candidate_id":7,
        "output_target_uuid":"selected-A", "output_track_id":1, "output_surface_status":"tracking",
        "reference_valid":True, "reference_reason":"valid", "quality_scale_applied":False,
        "raw_position_world_m":[10., 0., 0.],
        "reference_covariance_geometry":(np.eye(3)*.1).tolist(),
        "reference_covariance_pose":(np.eye(3)*.01).tolist(),
        "reference_covariance_total":(np.eye(3)*.11).tolist(),
        "reference_covariance":(np.eye(3)*.11).tolist(),
        "pose_uncertainty_source":"declared_isotropic_position_std", "declared_pose_std_m":.1,
        "valid":True, "output_state":1, "output_position_world_m":[10., 0., 0.],
        "measurement_age_s":0., "output_measurement_source_s":1.,
        "output_velocity_world_mps":[0., 0., 0.], "output_covariance_world_6x6":np.eye(6).tolist()}


def native(row):
    return {"source_s":row["output_s"], "record_sequence":row["record_sequence"]-1,
        "received_sim_s":row["received_sim_s"], "target_uuid":row["output_target_uuid"],
        "frame_id":"map", "measurement_age_s":None if row["measurement_age_s"] is None else float(np.float32(row["measurement_age_s"])),
        "track_id":row["output_track_id"], "state":row["output_state"],
        "position_world_m":row["output_position_world_m"],
        "velocity_world_mps":row["output_velocity_world_mps"],
        "covariance_world_6x6":(None if row["output_covariance_world_6x6"] is None else
            np.asarray(row["output_covariance_world_6x6"], dtype=np.float32).astype(float).tolist())}


class ReplayExportTests(unittest.TestCase):
    def test_delayed_measurement_retains_all_three_output_times_and_real_sequence(self):
        exported = normalize_cycles([cycle(9)])
        self.assertEqual(exported["measurements"][0]["source_s"], 1.)
        self.assertEqual(exported["measurements"][0]["available_s"], 1.05)
        self.assertEqual(exported["output_events"][0], {
            "source_s":1.05, "state_source_s":1., "available_s":1.05, "record_sequence":9})
        self.assertEqual(exported["task_events"][0]["record_sequence"], 9)
        self.assertEqual(exported["task_events"][0]["source_s"], 1.05)

    def test_timer_repeats_do_not_create_measurements_or_backdate_lifecycle(self):
        first, projected = cycle(1), cycle(4)
        projected.update(output_s=1.1, output_publication_s=1.1, received_sim_s=1.12,
                         output_surface_status="coasting")
        exported = normalize_cycles([first, projected])
        self.assertEqual(len(exported["measurements"]), 1)
        self.assertEqual(len(exported["output_events"]), 2)
        self.assertEqual(exported["task_events"][1]["source_s"], 1.1)
        self.assertEqual(exported["output_events"][1]["available_s"], 1.12)

    def test_preselection_empty_opportunity_is_retained_without_inventing_identity(self):
        row = cycle()
        row.update(target_uuid="", track_id=0, candidate_id=None, output_target_uuid="", output_track_id=0,
                   output_surface_status="uninitialized", reference_valid=False,
                   reference_reason="no_accepted_selected_measurement")
        result = normalize_cycles([row])
        self.assertEqual(result["measurements"][0]["target_uuid"], "")
        self.assertFalse(result["measurements"][0]["reference_valid"])
        self.assertEqual(result["task_events"][0]["action"], "clear")

    def test_new_output_identity_cannot_rebind_cached_old_measurement(self):
        first, reselection = cycle(1), cycle(3)
        reselection.update(output_s=1.1, output_publication_s=1.1, received_sim_s=1.1,
                           output_target_uuid="new-B", output_track_id=2, output_surface_status="ambiguous")
        result = normalize_cycles([first, reselection])
        self.assertEqual(len(result["measurements"]), 1)
        self.assertEqual(result["task_events"][1]["target_uuid"], "new-B")
        self.assertEqual(result["task_events"][1]["state"], "ambiguous")

    def test_combined_R_and_exact_pose_source_are_both_checked(self):
        for inconsistent_sum in (True, False):
            row = cycle()
            row["reference_covariance_pose"][0][0] += .2
            if not inconsistent_sum:
                row["reference_covariance_total"][0][0] += .2
                row["reference_covariance"][0][0] += .2
            with self.subTest(inconsistent_sum=inconsistent_sum), self.assertRaises(ValueError):
                normalize_cycles([row])

    def test_missing_clock_or_wrong_time_domain_does_not_become_zero_latency(self):
        for patch in ({"received_sim_s":None}, {"received_sim_s":.8},
                      {"measurement_processing_s":1.06}, {"diagnostic_schema_version":1}):
            row = cycle(); row.update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):normalize_cycles([row])

    def test_separate_native_state_is_required_and_numeric_payload_is_verified(self):
        row = cycle(3)
        self.assertEqual(verify_state_cycles([row], [native(row)])["status"], "PASS")
        self.assertEqual(verify_state_cycles([row], [])["status"], "INCOMPLETE_EVIDENCE")
        state = deepcopy(native(row)); state["position_world_m"][0] += .5
        self.assertEqual(verify_state_cycles([row], [state])["status"], "INCOMPLETE_EVIDENCE")

    def test_empty_inputs_never_establish_native_correspondence(self):
        for diagnostics, states in (([], []), (None, None), ([], [native(cycle())])):
            with self.subTest(diagnostics=diagnostics):
                self.assertEqual(verify_state_cycles(diagnostics, states)["status"], "INCOMPLETE_EVIDENCE")

    def test_missing_nonfinite_future_or_regressed_native_delivery_is_incomplete(self):
        for defect in ({"received_sim_s":None}, {"received_sim_s":float("nan")},
                       {"received_sim_s":.90}, {"received_sim_s":-1.}, {"frame_id":"odom"}):
            row = cycle(3); state = native(row); state.update(defect)
            with self.subTest(defect=defect):
                self.assertEqual(verify_state_cycles([row], [state])["status"], "INCOMPLETE_EVIDENCE")
        first, second = cycle(3), cycle(5)
        second.update(output_s=1.01, output_publication_s=1.06, measurement_age_s=.01)
        states = [native(first), native(second)]
        states[1]["received_sim_s"] = 1.03
        self.assertEqual(verify_state_cycles([first, second], states)["status"], "INCOMPLETE_EVIDENCE")

    def test_native_age_and_last_measurement_source_must_agree(self):
        for defect in ({"measurement_age_s":None}, {"measurement_age_s":.1}, {"measurement_age_s":-1.}):
            row = cycle(3); state = native(row); state.update(defect)
            with self.subTest(defect=defect):
                self.assertEqual(verify_state_cycles([row], [state])["status"], "INCOMPLETE_EVIDENCE")
        row = cycle(3); row.update(output_s=1.8, output_publication_s=1.8, measurement_age_s=.8, output_state=2)
        state = native(row); state["received_sim_s"] = 1.8
        self.assertEqual(verify_state_cycles([row], [state])["status"], "INCOMPLETE_EVIDENCE")
        row = cycle(3); row["output_measurement_source_s"] = .9
        self.assertEqual(verify_state_cycles([row], [native(row)])["status"], "INCOMPLETE_EVIDENCE")

    def test_late_native_delivery_is_retained_with_its_actual_age(self):
        row = cycle(3); state = native(row); state["received_sim_s"] = 2.
        result = verify_state_cycles([row], [state])
        self.assertEqual(result["status"], "PASS", result)
        pair = result["pairs"][0]
        self.assertEqual(pair["native_state_availability_s"], 2.)
        self.assertEqual(pair["delivered_measurement_age_s"], 1.)
        self.assertFalse(pair["delivery_within_prediction_horizon"])

    def test_real_scale_covariance_and_age_use_declared_float32_wire_conversion(self):
        row = cycle(3)
        age = .4200000000000017
        covariance = np.diag([4.123456714, .010123456789, .123456789123, 4.76543219, .2, .3])
        row.update(output_state=2, output_s=1.+age, output_publication_s=1.5, measurement_age_s=age,
            output_covariance_world_6x6=covariance.tolist())
        state = native(row); state["received_sim_s"] = 1.5
        self.assertGreater(np.max(np.abs(np.asarray(state["covariance_world_6x6"])-covariance)), 1e-8)
        self.assertGreater(abs(state["measurement_age_s"]-age), 1e-8)
        result = verify_state_cycles([row], [state])
        self.assertEqual(result["status"], "PASS", result)
        self.assertIn("float32", result["numeric_contract"]["measurement_age_s"])
        # The high-precision diagnostic still has to agree with source time.
        row["output_measurement_source_s"] -= 2e-8
        self.assertEqual(verify_state_cycles([row], [state])["status"], "INCOMPLETE_EVIDENCE")

    def test_one_float32_ulp_after_expected_quantization_is_rejected_even_below_1e_minus_8(self):
        for field in ("age", "covariance"):
            row = cycle(3); age = .03
            row.update(output_state=2, output_s=1.+age, output_publication_s=1.1, measurement_age_s=age,
                output_covariance_world_6x6=(np.eye(6)*.01).tolist())
            state = native(row); state["received_sim_s"] = 1.1
            self.assertEqual(verify_state_cycles([row], [state])["status"], "PASS")
            if field == "age":
                original = state["measurement_age_s"]
                state["measurement_age_s"] = float(np.nextafter(np.float32(original), np.float32(np.inf)))
                change = state["measurement_age_s"]-original
            else:
                original = state["covariance_world_6x6"][0][0]
                state["covariance_world_6x6"][0][0] = float(np.nextafter(np.float32(original), np.float32(np.inf)))
                change = state["covariance_world_6x6"][0][0]-original
            self.assertGreater(change, 0.)
            self.assertLess(change, 1e-8)
            with self.subTest(field=field):
                self.assertEqual(verify_state_cycles([row], [state])["status"], "INCOMPLETE_EVIDENCE")

    def test_position_and_velocity_remain_binary64_with_absolute_1e_minus_8_tolerance(self):
        for field in ("position_world_m", "velocity_world_mps"):
            row = cycle(3); row["output_"+field] = [4.123456714, .01, 0.]
            state = native(row)
            self.assertEqual(verify_state_cycles([row], [state])["status"], "PASS")
            state[field] = np.asarray(state[field], dtype=np.float32).astype(float).tolist()
            with self.subTest(field=field):
                self.assertEqual(verify_state_cycles([row], [state])["status"], "INCOMPLETE_EVIDENCE")

    def test_invalid_ros_placeholders_and_diagnostic_nulls_are_cross_checked(self):
        row = cycle(3); row.update(valid=False, output_state=3, measurement_age_s=None,
            output_measurement_source_s=None, output_position_world_m=None,
            output_velocity_world_mps=None, output_covariance_world_6x6=None)
        state = native(row); state.update(measurement_age_s=0., position_world_m=[0.]*3,
            velocity_world_mps=[0.]*3, covariance_world_6x6=np.zeros((6, 6)).tolist())
        self.assertEqual(verify_state_cycles([row], [state])["status"], "PASS")
        state["position_world_m"][0] = 1.
        self.assertEqual(verify_state_cycles([row], [state])["status"], "INCOMPLETE_EVIDENCE")


if __name__ == "__main__":unittest.main()
