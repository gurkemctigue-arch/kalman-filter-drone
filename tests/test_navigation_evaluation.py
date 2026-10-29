"""Independent navigation metrics must expose bias, silence and loss tails."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_navigation_reference as evaluation
from evaluate_stage1_flight import Record
from uav_tracking.research_labels import quaternion_matrix


def stamp(timestamp):
    nanoseconds = round(timestamp * 1e9)
    return NS(sec=nanoseconds // 10**9, nanosec=nanoseconds % 10**9)


def xyz(values):
    return NS(x=float(values[0]), y=float(values[1]), z=float(values[2]))


def header(timestamp, frame="map"):
    return NS(stamp=stamp(timestamp), frame_id=frame)


def fixture(*, multi=False, roll=0.):
    shift = np.array([3., -2., 1.])
    offset = np.array([0., 0., .24])
    q = [math.sin(roll / 2), 0, 0, math.cos(roll / 2)]
    rotation = quaternion_matrix(q)
    records = [Record("/tracking/flight_phase", 6., NS(data="FOLLOW"), 6.)]
    if multi:
        records.append(Record("/tracking/selection", 5.9, NS(action=0, target_uuid="task"), 5.9))
    for index in range(241):
        timestamp = index * .05
        model = np.array([timestamp, 0, 2. - (rotation @ offset)[2]])
        body = model + rotation @ offset
        target = np.array([body[0] + 9., body[1], 0.])
        transforms = []
        for name, point, quaternion in (("stage1_uav", model, q),
                                        ("actor_car_1" if multi else "target_car", target, [0, 0, 0, 1])):
            transforms.append(NS(child_frame_id=name, header=header(timestamp, "world"),
                                 transform=NS(translation=xyz(point), rotation=NS(x=quaternion[0], y=quaternion[1], z=quaternion[2], w=quaternion[3]))))
        records.append(Record("/ground_truth/poses", timestamp, NS(transforms=transforms), timestamp))
        pose = NS(position=xyz(body - shift), orientation=NS(x=q[0], y=q[1], z=q[2], w=q[3]))
        records.append(Record("/vehicle/odometry", timestamp, NS(header=header(timestamp), child_frame_id="base_link", pose=NS(pose=pose)), timestamp))
        if timestamp < 6. - 1e-9:
            continue
        state = NS(header=header(timestamp), state=1, track_id=1, target_uuid="task", prediction_age_s=0.,
                   position_m=xyz(target - shift), velocity_mps=xyz([1, 0, 0]))
        records.append(Record(evaluation.STATE_TOPIC, timestamp, state, timestamp))
        records.append(Record("/tracking/status", timestamp, NS(lifecycle=2, track_id=1), timestamp))
        if index % 4 == 0:
            payload = {"acquisition_s":timestamp, "output_s":timestamp, "target_uuid":"task", "track_id":1,
                       "reference_valid":True, "reference_reason":"ok", "reference_kind":"car_cuboid_ground_center",
                       "raw_position_world_m":(target - shift).tolist(), "fusion_accepted":True, "fusion_reason":"accepted"}
            diagnostic = Record(evaluation.DIAGNOSTIC_TOPIC, timestamp, NS(data=json.dumps(payload)), timestamp)
            records.extend([diagnostic, deepcopy(diagnostic)])
    config = {"stage":2 if multi else 1, "target_class":"car", "control_reference":"ground_footprint",
              "desired_distance_m":9., "desired_height_m":2., "navigation_frame_id":"map",
              "vehicle_control_point_offset_flu_m":offset.tolist()}
    physical = {"tasks":{"task":{"initial_mapping":{"physical_id":"actor_car_1"}}}} if multi else None
    return records, config, physical


def transform_diagnostics(records, function):
    result = []
    for record in records:
        if record.topic != evaluation.DIAGNOSTIC_TOPIC:
            result.append(record)
            continue
        payload = json.loads(record.message.data)
        function(payload)
        result.append(Record(record.topic, record.time_s, NS(data=json.dumps(payload)), record.received_sim_s))
    return result


class NavigationEvaluationTests(unittest.TestCase):
    def test_position_command_second_difference_and_mode_gaps(self):
        commands = [{"time_s": t, "valid": True, "mode": mode, "position_m": [x, 0., 0.]}
                    for t, x, mode in ((1., 0., 2), (1.1, .01, 2), (1.2, .04, 2), (1.3, 100., 0),
                                       (1.4, .16, 2), (2., 100., 2))]
        value = evaluation.position_setpoint_variation(commands)
        self.assertAlmostEqual(value["position_setpoint_second_difference_mps2"]["rmse"], 2.)
        self.assertEqual(value["position_setpoint_second_difference_mps2"]["count"], 1)
        self.assertEqual(value["position_setpoint_delta_over_dt_mps"]["count"], 2)

    def test_position_control_metrics_are_populated_from_actual_position_messages(self):
        records, config, _ = fixture()
        for timestamp, position in ((6.1, 0.), (6.2, .01), (6.3, .04)):
            command = NS(header=header(timestamp), valid=True, mode=2, position_m=xyz([position, 0., 0.]),
                         linear_mps=xyz([0., 0., 0.]), yaw_rate_radps=0.)
            records.append(Record("/tracking/command", timestamp, command, timestamp))
        result = evaluation.evaluate(records, config)
        self.assertAlmostEqual(result["position_control_jitter"]["position_setpoint_second_difference_mps2"]["rmse"], 2.)
        self.assertEqual(result["control_jitter"]["valid_velocity_commands"], 0)

    def test_command_jitter_and_end_to_end_navigation_latency_use_recorded_streams(self):
        records, config, _ = fixture()
        for timestamp, speed in ((6.1, 0.), (6.2, .2), (6.3, .4)):
            command = NS(header=header(timestamp), valid=True, mode=1,
                         linear_mps=xyz([speed, 0., 0.]), yaw_rate_radps=speed)
            records.append(Record("/tracking/command", timestamp, command, timestamp))
        result = evaluation.evaluate(records, config)
        jitter = result["control_jitter"]
        self.assertAlmostEqual(jitter["velocity_command_delta_over_dt_mps2"]["rmse"], 2.)
        self.assertEqual(jitter["valid_velocity_commands"], 3)
        self.assertGreater(result["visual_control_metrics"]["source_images_with_first_tracking_command"], 0)
        self.assertEqual(result["short_shutter_prediction"]["requested_short_windows"], 0)

    def test_short_prediction_does_not_count_ordinary_timer_predictions_or_missing_truth_as_zero(self):
        samples = [{"time_s": timestamp, "navigation_state": state, "navigation_valid": valid,
                    "kf_position_error_m": error} for timestamp, state, valid, error in
                   ((1., 2, True, 100.), (2., 2, True, .5), (2.1, 2, True, None),
                    (2.2, 3, False, None), (2.3, 1, True, .1), (4., 2, True, 200.))]
        windows = [{"start_s": 2., "end_s": 2.3}, {"start_s": 3., "end_s": 6.},
                   {"start_s": 7., "end_s": None}]
        result = evaluation.short_shutter_prediction(samples, windows)
        self.assertEqual(result["requested_short_windows"], 1)
        self.assertEqual(result["scheduled_samples"], 4)
        self.assertEqual(result["valid_prediction_samples"], 2)
        self.assertEqual(result["truth_supported_prediction_samples"], 1)
        self.assertEqual(result["position_error_m"]["rmse"], .5)
        self.assertEqual(result["valid_prediction_coverage"], .5)

    def test_clock_only_tail_extends_denominators_without_inventing_state_or_truth(self):
        records, config, _ = fixture()
        baseline = evaluation.evaluate(records,config)
        records.append(Record("/clock",15.,NS(clock=stamp(15.)),15.))
        result = evaluation.evaluate(records,config)
        self.assertEqual(baseline["interval"]["end_s"],12.)
        self.assertEqual(result["interval"]["end_s"],15.)
        self.assertEqual(result["whole_interval"]["scheduled_samples"],91)
        self.assertEqual(result["kf_navigation"]["counts"]["scheduled_samples"],91)
        self.assertEqual(result["whole_interval"]["matched_truth_samples"],61)
        self.assertEqual(result["kf_navigation"]["counts"]["valid_navigation_samples"],62)
        self.assertEqual(result["kf_navigation"]["counts"]["missing_navigation_stream"],29)
        self.assertGreater(result["whole_interval"]["inactive_control_samples"],20)
        self.assertIsNone(result["frames"][-1]["base_link_distance_error_m"])
        self.assertFalse(result["frames"][-1]["navigation_valid"])
        self.assertTrue(result["whole_interval"]["transients"]["base_link"]["distance"]["settling_right_censored"])
        self.assertLess(result["kf_navigation"]["valid_state_coverage"],baseline["kf_navigation"]["valid_state_coverage"])

    def test_cli_explicitly_requests_clock_records_and_restores_topic_filter(self):
        records, config, _ = fixture()
        previous = evaluation.bag_tools.TOPICS
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(evaluation,"recorded_configuration",return_value=config), \
                patch.object(evaluation.bag_tools,"read_rosbag",return_value=(records,{"fixture":True})) as reader, \
                patch.object(evaluation,"read_monitor_events",return_value=([],{})), \
                redirect_stdout(io.StringIO()):
            root=Path(temporary)
            self.assertEqual(evaluation.main([str(root),"--target-class","car","--output",str(root/"report.json")]),0)
            self.assertIs(reader.call_args.kwargs["preserve_clock"],True)
        self.assertEqual(evaluation.bag_tools.TOPICS,previous)

    def test_ground_center_and_control_point_are_independent_of_surface_reference(self):
        records, config, _ = fixture()
        result = evaluation.evaluate(records, config)
        self.assertEqual(result["evaluation_status"], "RECORDED_WITH_CENSORED_FAILURES")
        self.assertEqual(result["whole_interval"]["scheduled_samples"], 61)
        self.assertAlmostEqual(result["whole_interval"]["metrics"]["base_link_height_error_m"]["rmse"], 0.)
        self.assertAlmostEqual(result["whole_interval"]["metrics"]["model_origin_height_error_m"]["mean"], -.24)
        self.assertAlmostEqual(result["kf_navigation"]["metrics"]["kf_position_error_m"]["rmse"], 0., places=10)
        self.assertAlmostEqual(result["raw_navigation"]["metrics"]["position_error_m"]["rmse"], 0., places=10)
        self.assertEqual(result["whole_interval"]["transients"]["base_link"]["height"]["settling_time_s"], 0.)
        np.testing.assert_allclose(result["ego_alignment"]["translation_world_from_map_m"], [3, -2, 1])
        json.dumps(result, allow_nan=False)

    def test_body_offset_rotates_with_independent_vehicle_attitude(self):
        records, config, _ = fixture(roll=math.pi / 3)
        result = evaluation.evaluate(records, config)
        metrics = result["whole_interval"]["metrics"]
        self.assertAlmostEqual(metrics["base_link_distance_error_m"]["rmse"], 0., places=10)
        self.assertAlmostEqual(metrics["base_link_height_error_m"]["rmse"], 0., places=10)
        self.assertAlmostEqual(metrics["model_origin_height_error_m"]["mean"], -.12)
        self.assertGreater(metrics["model_origin_distance_error_m"]["mean"], 0.)

    def test_timer_repeats_do_not_inflate_raw_observation_or_velocity_counts(self):
        records, config, _ = fixture()
        result = evaluation.evaluate(records, config)["raw_navigation"]
        self.assertEqual(result["counts"]["unique_acquisition_opportunities"], 31)
        self.assertEqual(result["deduplicated_timer_repeats"], 31)
        self.assertEqual(result["metrics"]["velocity_error_mps"]["count"], 30)
        self.assertAlmostEqual(result["metrics"]["velocity_error_mps"]["rmse"], 0., places=10)
        self.assertAlmostEqual(result["metrics"]["velocity_pair_dt_s"]["mean"], .2)

    def test_unheadered_diagnostic_output_stamp_handles_prior_clock_quantization(self):
        records, config, _ = fixture()
        records = [Record(row.topic, row.time_s - .02, row.message, row.time_s - .02)
                   if row.topic == evaluation.DIAGNOSTIC_TOPIC else row for row in records]
        result = evaluation.evaluate(records, config)["raw_navigation"]
        self.assertEqual(result["valid_reference_coverage"], 1.)
        self.assertAlmostEqual(result["metrics"]["position_error_m"]["rmse"], 0., places=10)

    def test_target_bias_cannot_change_ego_only_alignment(self):
        records, config, _ = fixture()
        for record in records:
            if record.topic.startswith("/ground_truth/"):
                record.message.transforms[1].transform.translation.x += 20.
        result = evaluation.evaluate(records, config)
        np.testing.assert_allclose(result["ego_alignment"]["translation_world_from_map_m"], [3, -2, 1])
        self.assertAlmostEqual(result["raw_navigation"]["metrics"]["position_error_m"]["rmse"], 20.)
        self.assertAlmostEqual(result["kf_navigation"]["metrics"]["kf_position_error_m"]["rmse"], 20.)

    def test_silent_state_tail_keeps_grid_truth_errors_and_censors_settling(self):
        records, config, _ = fixture()
        records = [row for row in records if row.topic != evaluation.STATE_TOPIC or row.time_s < 9.]
        result = evaluation.evaluate(records, config)
        self.assertEqual(result["kf_navigation"]["counts"]["scheduled_samples"], 61)
        self.assertGreater(result["kf_navigation"]["counts"]["missing_navigation_stream"], 20)
        self.assertEqual(result["whole_interval"]["matched_truth_samples"], 61)
        self.assertGreater(result["whole_interval"]["inactive_control_samples"], 20)
        self.assertIsNone(result["whole_interval"]["transients"]["base_link"]["distance"]["settling_time_s"])
        self.assertTrue(result["whole_interval"]["transients"]["base_link"]["distance"]["settling_right_censored"])
        self.assertLess(result["kf_navigation"]["position_truth_coverage"], .6)

    def test_invalid_zero_geometry_is_never_treated_as_an_accurate_measurement(self):
        records, config, _ = fixture()
        for row in records:
            if row.topic == evaluation.STATE_TOPIC and row.time_s >= 9.:
                row.message.state = 3
                row.message.position_m = xyz([0, 0, 0])
                row.message.velocity_mps = xyz([0, 0, 0])
        result = evaluation.evaluate(records, config)
        self.assertGreater(result["kf_navigation"]["counts"]["lost"], 25)
        self.assertAlmostEqual(result["kf_navigation"]["metrics"]["kf_position_error_m"]["rmse"], 0., places=10)
        self.assertLess(result["kf_navigation"]["valid_state_coverage"], .5)

    def test_late_delivery_is_not_backdated_or_ideally_extrapolated(self):
        records, config, _ = fixture()
        records = [Record(row.topic, row.time_s, row.message, row.time_s + .1 if row.topic == evaluation.STATE_TOPIC else row.received_sim_s)
                   for row in records]
        result = evaluation.evaluate(records, config)
        self.assertFalse(result["frames"][0]["navigation_valid"])
        self.assertAlmostEqual(result["kf_navigation"]["metrics"]["kf_position_error_m"]["rmse"], .1, places=9)
        self.assertAlmostEqual(result["kf_navigation"]["message_level"]["metrics"]["position_error_m"]["rmse"], 0., places=10)
        self.assertAlmostEqual(result["kf_navigation"]["message_level"]["metrics"]["delivery_age_s"]["mean"], .1)

    def test_delivery_time_counts_toward_unchanged_prediction_age_gate(self):
        records, config, _ = fixture()
        updated = []
        for row in records:
            if row.topic == evaluation.STATE_TOPIC:
                row.message.state = 2
                row.message.prediction_age_s = .7
                row = Record(row.topic, row.time_s, row.message, row.time_s + .1)
            updated.append(row)
        result = evaluation.evaluate(updated, config)
        self.assertEqual(result["kf_navigation"]["metrics"]["kf_position_error_m"]["count"], 0)
        self.assertGreater(result["kf_navigation"]["counts"]["stale_navigation_measurement"], 50)

    def test_wrong_frame_and_nonfinite_state_remain_unavailable(self):
        records, config, _ = fixture()
        for row in records:
            if row.topic == evaluation.STATE_TOPIC:
                if row.time_s < 9.:
                    row.message.header.frame_id = "camera"
                else:
                    row.message.position_m.x = math.nan
        result = evaluation.evaluate(records, config)
        self.assertEqual(result["kf_navigation"]["position_truth_coverage"], 0.)
        self.assertGreater(result["kf_navigation"]["counts"]["unexpected_state_frame"], 20)
        self.assertGreater(result["kf_navigation"]["counts"]["nonfinite_state_vector"], 20)
        json.dumps(result, allow_nan=False)

    def test_raw_invalidity_and_stale_acquisition_stay_in_denominator(self):
        records, config, _ = fixture()
        records = transform_diagnostics(records, lambda payload: payload.update(reference_valid=False, reference_reason="clipped")
                                        if payload["acquisition_s"] < 9. else None)
        updated = []
        for row in records:
            if row.topic == evaluation.DIAGNOSTIC_TOPIC and row.time_s >= 9.:
                row = Record(row.topic, row.time_s, row.message, row.time_s + .61)
            updated.append(row)
        result = evaluation.evaluate(updated, config)["raw_navigation"]
        self.assertEqual(result["valid_reference_coverage"], 0.)
        self.assertEqual(result["counts"]["invalid_reference:clipped"], 15)
        self.assertEqual(result["counts"]["stale_raw_measurement"], 16)
        self.assertEqual(result["metrics"]["position_error_m"]["count"], 0)

    def test_raw_velocity_does_not_cross_rejected_measurements_or_track_changes(self):
        records, config, _ = fixture()
        def update(payload):
            if abs(payload["acquisition_s"] - 8.) < 1e-8:
                payload.update(reference_valid=False, reference_reason="partial")
            if payload["acquisition_s"] >= 10.:
                payload["track_id"] = 2
        records = transform_diagnostics(records, update)
        result = evaluation.evaluate(records, config)["raw_navigation"]
        self.assertEqual(result["metrics"]["position_error_m"]["count"], 30)
        self.assertEqual(result["metrics"]["velocity_error_mps"]["count"], 27)

    def test_raw_geometric_accuracy_is_separate_from_fusion_gate_acceptance(self):
        records, config, _ = fixture()
        records = transform_diagnostics(records, lambda payload: payload.update(fusion_accepted=False, fusion_reason="mahalanobis"))
        result = evaluation.evaluate(records, config)["raw_navigation"]
        self.assertEqual(result["valid_reference_coverage"], 1.)
        self.assertEqual(result["diagnostic_reason_counts"]["fusion:mahalanobis"], 31)
        self.assertEqual(result["invalid_reason_counts"], {})

    def test_real_core_ground_reference_kinds_are_accepted_for_the_correct_class(self):
        for target_class, kind in (("car", "car_cuboid_ground_center"), ("person", "person_ground_contact")):
            with self.subTest(target_class=target_class):
                records, config, _ = fixture()
                if target_class == "person":
                    config["target_class"] = "person"
                    for row in records:
                        if row.topic.startswith("/ground_truth/"):
                            row.message.transforms[1].child_frame_id = "target_person"
                records = transform_diagnostics(records, lambda payload: payload.update(reference_kind=kind))
                result = evaluation.evaluate(records, config)["raw_navigation"]
                self.assertEqual(result["valid_reference_coverage"], 1.)
                wrong = transform_diagnostics(records, lambda payload: payload.update(
                    reference_kind="person_ground_contact" if target_class == "car" else "car_cuboid_ground_center"))
                self.assertEqual(evaluation.evaluate(wrong, config)["raw_navigation"]["valid_reference_coverage"], 0.)

    def test_generic_reference_requires_an_explicit_matching_class(self):
        for class_name, expected in ((None, False), ("person", False), ("car", True)):
            payload = {"reference_kind":"ground_footprint_center"}
            if class_name is not None:
                payload["class_name"] = class_name
            self.assertEqual(evaluation._valid_reference_kind(payload, "car"), expected)

    def test_evaluation_source_hash_is_separate_from_flight_revision(self):
        provenance = evaluation.evaluation_source_provenance()
        self.assertEqual(len(provenance["script_sha256"]), 64)
        self.assertEqual(Path(provenance["script"]).name, "evaluate_navigation_reference.py")
        self.assertGreaterEqual(len(provenance["dependencies"]), 5)

    def test_multiple_actors_need_independent_request_identity_and_keep_unknown_requests(self):
        records, config, physical = fixture(multi=True)
        missing = evaluation.evaluate(records, config)
        self.assertEqual(missing["whole_interval"]["matched_truth_samples"], 0)
        self.assertEqual(missing["kf_navigation"]["position_truth_coverage"], 0.)
        known = evaluation.evaluate(records, config, physical=physical)
        self.assertEqual(known["whole_interval"]["matched_truth_samples"], 61)
        self.assertEqual(known["kf_navigation"]["position_truth_coverage"], 1.)
        records.append(Record("/tracking/selection", 9., NS(action=0, target_uuid="unknown"), 9.))
        changed = evaluation.evaluate(records, config, physical=physical)
        self.assertEqual(changed["whole_interval"]["matched_truth_samples"], 30)
        self.assertGreater(changed["kf_navigation"]["counts"]["requested_task_mismatch"], 25)
        self.assertTrue(changed["windows"][-1]["confirmation_censored"])
        self.assertIsNone(changed["windows"][-1]["base_link"]["distance"]["settling_time_s"])

    def test_missing_ego_calibration_does_not_invent_identity_alignment(self):
        records, config, _ = fixture()
        records = [row for row in records if row.topic != "/vehicle/odometry"]
        result = evaluation.evaluate(records, config)
        self.assertEqual(result["evaluation_status"], "INCOMPLETE_EVIDENCE")
        self.assertIsNone(result["ego_alignment"])
        self.assertEqual(result["kf_navigation"]["position_truth_coverage"], 0.)
        self.assertEqual(result["whole_interval"]["matched_truth_samples"], 61)

    def test_ego_alignment_requires_finite_base_link_odometry(self):
        for failure in ("frame", "nonfinite"):
            with self.subTest(failure=failure):
                records, config, _ = fixture()
                for row in records:
                    if row.topic == "/vehicle/odometry":
                        if failure == "frame":
                            row.message.child_frame_id = "camera"
                        else:
                            row.message.pose.pose.position.x = math.nan
                result = evaluation.evaluate(records, config)
                self.assertIsNone(result["ego_alignment"])
                self.assertEqual(result["evaluation_status"], "INCOMPLETE_EVIDENCE")
                json.dumps(result, allow_nan=False)

    def test_missing_truth_is_never_extrapolated_and_breaks_final_settling(self):
        records, config, _ = fixture()
        for row in records:
            if row.topic.startswith("/ground_truth/") and row.time_s >= 10.:
                row.message.transforms = row.message.transforms[:1]
        result = evaluation.evaluate(records, config)
        self.assertLess(result["whole_interval"]["matched_truth_samples"], 45)
        self.assertIsNone(result["whole_interval"]["transients"]["base_link"]["height"]["settling_time_s"])

    def test_no_follow_and_missing_explicit_reference_fail_without_assumptions(self):
        records, config, _ = fixture()
        result = evaluation.evaluate([row for row in records if row.topic != "/tracking/flight_phase"], config)
        self.assertEqual(result["evaluation_status"], "INCOMPLETE_EVIDENCE")
        for missing in ("control_reference", "vehicle_control_point_offset_flu_m", "desired_height_m"):
            altered = dict(config); altered.pop(missing)
            with self.assertRaises(ValueError):
                evaluation.evaluate(records, altered)

    def test_fixed_bands_and_whole_interval_do_not_cherry_pick_successful_initial_window(self):
        records, config, _ = fixture()
        for row in records:
            if row.topic == "/tracking/status" and row.time_s >= 10.:
                row.message.lifecycle = 4
        result = evaluation.evaluate(records, config, events=[{"kind":"shutter", "active":True, "time_s":10.}])
        initial = result["windows"][0]
        self.assertEqual(initial["end_s"], 10.)
        self.assertEqual(initial["base_link"]["distance"]["band_m"], .9)
        self.assertEqual(initial["base_link"]["height"]["band_m"], .25)
        self.assertEqual(initial["base_link"]["height"]["minimum_in_band_duration_s"], 3.)
        self.assertIsNone(result["whole_interval"]["transients"]["base_link"]["distance"]["settling_time_s"])


class RecordedNavigationConfigurationTests(unittest.TestCase):
    def saved_trial(self, root):
        trial = Path(root); directory = trial / "configuration"; directory.mkdir()
        config = {"control_reference":"ground_footprint", "target_class":"car", "stage":1,
                  "vehicle_control_point_offset_flu_m":[0, 0, .24]}
        parameters = {
            "uav_tracking_controller":{"ros__parameters":{"state_topic":evaluation.STATE_TOPIC,
                "desired_distance_m":9., "desired_height_m":2., "desired_offset_m":[0, 0, 0], "prediction_timeout_s":.75}},
            "uav_tracking_state_estimator":{"ros__parameters":{"navigation_enabled":True, "state_frame":"map",
                "max_observation_age_s":.6, "max_prediction_duration_s":.75}},
            "uav_tracking_detection":{"ros__parameters":{"navigation_enabled":True}},
        }
        (trial / "run_config.json").write_text(json.dumps(config), encoding="utf-8")
        (directory / "runtime_parameters.yaml").write_text(yaml.safe_dump(parameters), encoding="utf-8")
        (directory / "runtime_world.sdf").write_text('<sdf><world name="trial"><spherical_coordinates><world_frame_orientation>ENU</world_frame_orientation><heading_deg>0</heading_deg></spherical_coordinates></world></sdf>', encoding="utf-8")
        return trial, config, parameters

    def test_actual_runtime_reference_and_recorded_world_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial, _, _ = self.saved_trial(temporary)
            result = evaluation.recorded_configuration(trial, "car")
            self.assertEqual(result["desired_distance_m"], 9.)
            self.assertEqual(result["controller_reference_evidence"]["state_topic"], evaluation.STATE_TOPIC)
            self.assertEqual(result["declared_frame_evidence"]["world_selection"], "RECORDED_RUNTIME_WORLD")
            (trial / "configuration/runtime_parameters.yaml").rename(trial / "configuration/stage1_tracking_car.yaml")
            with self.assertRaisesRegex(ValueError, "runtime_parameters"):
                evaluation.recorded_configuration(trial, "car")

    def test_config_contradiction_missing_offset_and_nonzero_task_offset_are_rejected(self):
        for mutation in ("reference", "vehicle_offset", "task_offset"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                trial, config, parameters = self.saved_trial(temporary)
                if mutation == "reference":
                    config["desired_distance_m"] = 8.
                elif mutation == "vehicle_offset":
                    config.pop("vehicle_control_point_offset_flu_m")
                else:
                    parameters["uav_tracking_controller"]["ros__parameters"]["desired_offset_m"] = [1, 0, 0]
                (trial / "run_config.json").write_text(json.dumps(config), encoding="utf-8")
                (trial / "configuration/runtime_parameters.yaml").write_text(yaml.safe_dump(parameters), encoding="utf-8")
                with self.assertRaises(ValueError):
                    evaluation.recorded_configuration(trial, "car")

    def test_original_age_gates_and_navigation_wiring_are_verified_from_runtime(self):
        for node, key, value in (("state_estimator", "max_observation_age_s", .61),
                                 ("state_estimator", "max_prediction_duration_s", .76),
                                 ("controller", "prediction_timeout_s", .76),
                                 ("controller", "state_topic", "/tracking/state"),
                                 ("detection", "navigation_enabled", False)):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                trial, _, parameters = self.saved_trial(temporary)
                parameters["uav_tracking_" + node]["ros__parameters"][key] = value
                (trial / "configuration/runtime_parameters.yaml").write_text(yaml.safe_dump(parameters), encoding="utf-8")
                with self.assertRaises(ValueError):
                    evaluation.recorded_configuration(trial, "car")

    def test_source_world_fallback_and_non_enu_axes_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial, _, _ = self.saved_trial(temporary)
            path = trial / "configuration/runtime_world.sdf"
            original = path.read_text(encoding="utf-8")
            path.write_text(original.replace("<heading_deg>0", "<heading_deg>5"), encoding="utf-8")
            with self.assertRaises(ValueError):
                evaluation.recorded_configuration(trial, "car")
            path.unlink()
            with self.assertRaisesRegex(ValueError, "Recorded runtime world"):
                evaluation.recorded_configuration(trial, "car")


if __name__ == "__main__":
    unittest.main()
