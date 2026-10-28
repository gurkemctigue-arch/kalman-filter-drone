"""Offline evaluator must reject fabricated/static/incorrect gimbal evidence."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_stage3_gimbal as evaluation  # noqa: E402
from uav_tracking.control.gimbal_geometry import JOINT_NAMES, MOUNT_TRANSLATION, camera_optical_quaternion  # noqa: E402


def stamp(seconds):
    value = round(seconds * 1e9)
    return NS(sec=value // 1_000_000_000, nanosec=value % 1_000_000_000)


def transform(parent, child, seconds, q=(0, 0, 0, 1), p=(0, 0, 0)):
    return NS(header=NS(stamp=stamp(seconds), frame_id=parent), child_frame_id=child,
              transform=NS(rotation=NS(x=q[0], y=q[1], z=q[2], w=q[3]), translation=NS(x=p[0], y=p[1], z=p[2])))


def fixture(mode="active"):
    records = [evaluation.stage1.Record("/tracking/flight_phase", 1.0, NS(data="FOLLOW"))]
    optical_inverse = [-0.5, 0.5, -0.5, -0.5]  # inverse of optical->FLU q, up to sign
    from uav_tracking.control.gimbal_geometry import _quaternion_product
    for step in range(251):
        time = 1 + 0.02 * step
        measured = np.array([0.1 * np.sin(time), 0.1 * np.cos(time), 0.03 * np.sin(time * 2)]) if mode == "active" else np.zeros(3)
        feedback = NS(header=NS(stamp=stamp(time)), name=list(JOINT_NAMES), position=measured.tolist())
        records.append(evaluation.stage1.Record("/gimbal/joint_states", time, feedback))
        q = camera_optical_quaternion(measured)
        tf = NS(transforms=[transform("map", "base_link", time), transform("base_link", "camera_link", time, q, MOUNT_TRANSLATION)])
        records.append(evaluation.stage1.Record("/tf", time, tf))
        model_camera_q = _quaternion_product(q, optical_inverse)
        gt = NS(transforms=[transform("stage3_flight", "stage1_uav", time),
                            transform("stage1_uav", "stage1_uav::base_link", time),
                            transform("stage1_uav", "stage1_uav::tracking_camera_mount", time, model_camera_q, MOUNT_TRANSLATION)])
        records.append(evaluation.stage1.Record("/ground_truth/vehicle_poses", time, gt))
        command = measured + 0.001 if mode == "active" else measured
        diagnostic = dict(time_s=time, active=mode == "active", feedback_angles_rad=measured.tolist(),
                          command_angles_rad=command.tolist(), joint_age_s=0,
                          desired_angles_rad=[0.0, 0.0, 0.0] if mode == "midpoint" else [0.2, 0.2, 0.2])
        records.append(evaluation.stage1.Record("/gimbal/diagnostics", time, NS(data=json.dumps(diagnostic))))
        records.append(evaluation.stage1.Record("/tracking/observations", time, NS(center_u_px=330, center_v_px=245)))
        for axis in ("yaw", "pitch", "roll"):
            records.append(evaluation.stage1.Record(f"/gimbal/{axis}/cmd_pos", time, NS(data=0.1)))
        if mode == "active":
            records.append(evaluation.stage1.Record("/gimbal/body_yaw_reference", time, NS()))
    return records


class Stage3EvaluationTests(unittest.TestCase):
    def test_complete_independent_feedback_tf_physics_evidence_passes(self):
        report = evaluation.evaluate_records(fixture(), {}, "active")
        self.assertEqual(report["result"], "PASS", report["checks"])

    def test_empty_evidence_never_passes(self):
        report = evaluation.evaluate_records([], {}, "active")
        self.assertEqual(report["result"], "FAIL_OR_INCOMPLETE")
        self.assertFalse(report["checks"]["three_encoder_joints_recorded"])

    def test_multi_target_centering_uses_only_the_selected_fresh_box(self):
        records = fixture()
        for row in list(records):
            if row.topic != "/tracking/observations":
                continue
            payload = {"schema_version": 1, "acquisition_s": row.time_s, "projected": False,
                       "target_uuid": "chosen-a", "target_status": "tracking", "target_track_id": 2,
                       "tracks": [{"track_id": 1, "matched": True, "bbox_xyxy": [0, 0, 20, 20]},
                                  {"track_id": 2, "matched": True, "bbox_xyxy": [310, 230, 330, 250]}]}
            records.append(evaluation.stage1.Record("/tracking/tracks", row.time_s, NS(data=json.dumps(payload))))
        report = evaluation.evaluate_records(records, {}, "active", selected_target=True)
        self.assertEqual(report["result"], "PASS", report["checks"])
        self.assertEqual(report["metrics"]["detected_center_normalized_error"]["rmse"], 0)
        self.assertEqual(report["centering_source"], "selected_fresh_track_box")

    def test_multi_target_missing_selected_snapshots_cannot_fall_back_to_all_boxes(self):
        report = evaluation.evaluate_records(fixture(), {}, "active", selected_target=True)
        self.assertEqual(report["metrics"]["detected_center_normalized_error"]["count"], 0)
        self.assertFalse(report["checks"]["follow_and_visual_metrics_recorded"])

    def test_actual_ros_gz_slash_scoped_link_frames_pass(self):
        records = fixture()
        for row in records:
            if row.topic == "/ground_truth/vehicle_poses":
                for tf in row.message.transforms:
                    tf.child_frame_id = tf.child_frame_id.replace("::", "/")
        report = evaluation.evaluate_records(records, {}, "active")
        self.assertEqual(report["result"], "PASS", report["checks"])

    def test_link_poses_with_different_parents_are_not_composed(self):
        records = fixture()
        for row in records:
            if row.topic == "/ground_truth/vehicle_poses":
                row.message.transforms[-1].header.frame_id = "another_model"
        report = evaluation.evaluate_records(records, {}, "active")
        self.assertFalse(report["checks"]["physical_link_pose_matches_feedback_geometry"])
        self.assertFalse(report["checks"]["no_bag_read_or_channel_errors"])

    def test_static_camera_tf_is_rejected_even_if_geometry_matches(self):
        records = fixture()
        records.append(evaluation.stage1.Record("/tf_static", 2.0, NS(transforms=[transform("base_link", "camera_link", 2.0)])))
        report = evaluation.evaluate_records(records, {}, "active")
        self.assertFalse(report["checks"]["camera_tf_is_dynamic_feedback_only"])

    def test_wrong_physical_mount_or_axis_cannot_pass_by_copying_feedback_tf(self):
        records = fixture()
        for row in records:
            if row.topic == "/ground_truth/vehicle_poses":
                row.message.transforms[-1].transform.translation.x += 0.02
        report = evaluation.evaluate_records(records, {}, "active")
        self.assertTrue(report["checks"]["tf_matches_source_feedback_geometry"])
        self.assertFalse(report["checks"]["physical_link_pose_matches_feedback_geometry"])

    def test_command_echo_as_encoder_has_no_physical_lag_evidence(self):
        records = fixture()
        for row in records:
            if row.topic == "/gimbal/diagnostics":
                payload = json.loads(row.message.data)
                payload["command_angles_rad"] = payload["feedback_angles_rad"]
                row.message.data = json.dumps(payload)
        report = evaluation.evaluate_records(records, {}, "active")
        self.assertFalse(report["checks"]["commands_and_encoders_have_physical_lag"])

    def test_camera_tf_restamped_from_publish_time_is_rejected(self):
        records = fixture()
        for row in records:
            if row.topic == "/tf":
                row.message.transforms[-1].header.stamp = stamp(row.time_s + 0.001)
        report = evaluation.evaluate_records(records, {}, "active")
        self.assertFalse(report["checks"]["camera_tf_is_dynamic_feedback_only"])

    def test_true_midpoint_uses_physical_feedback_but_does_not_need_motion(self):
        report = evaluation.evaluate_records(fixture("midpoint"), {}, "midpoint")
        self.assertEqual(report["result"], "PASS", report["checks"])

    def test_explicit_invalid_source_startup_is_audited_and_not_an_encoder_claim(self):
        records = fixture("midpoint")
        startup = dict(time_s=.02, mode="midpoint", active=False,
                       reason="invalid source timestamp", feedback_angles_rad=[0., 0., 0.],
                       desired_angles_rad=None, command_angles_rad=[0., 0., 0.],
                       commanded_rates_radps=None)
        records.append(evaluation.stage1.Record("/gimbal/diagnostics", .02, NS(data=json.dumps(startup))))
        report = evaluation.evaluate_records(records, {}, "midpoint")
        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["result"], "PASS", report["channel_errors"])
        self.assertEqual(len(report["not_ready_diagnostics"]), 1)
        self.assertEqual(report["physical_feedback"]["diagnostic_encoder_error_rad"]["count"], 251)

    def test_ready_diagnostics_missing_age_are_still_malformed(self):
        for mode in ("active", "midpoint"):
            records = fixture(mode)
            row = next(row for row in records if row.topic == "/gimbal/diagnostics")
            payload = json.loads(row.message.data)
            payload.pop("joint_age_s")
            payload["reason"] = "tracking" if mode == "active" else "midpoint"
            row.message.data = json.dumps(payload)
            report = evaluation.evaluate_records(records, {}, mode)
            self.assertFalse(report["checks"]["no_bag_read_or_channel_errors"])
            self.assertEqual(report["result"], "FAIL_OR_INCOMPLETE")

    def test_invalid_source_diagnostic_cannot_conceal_active_or_moving_command(self):
        for fields in ({"active": True}, {"command_angles_rad": [.1, 0., 0.]},
                       {"desired_angles_rad": [.1, 0., 0.]}, {"commanded_rates_radps": [.1, 0., 0.]}):
            records = fixture()
            startup = dict(time_s=.02, active=False, reason="invalid source timestamp",
                           feedback_angles_rad=[0., 0., 0.], command_angles_rad=[0., 0., 0.],
                           desired_angles_rad=None, commanded_rates_radps=None)
            startup.update(fields)
            records.append(evaluation.stage1.Record("/gimbal/diagnostics", .02, NS(data=json.dumps(startup))))
            report = evaluation.evaluate_records(records, {}, "active")
            self.assertFalse(report["checks"]["no_bag_read_or_channel_errors"])

    def test_ready_diagnostic_missing_angles_and_invalid_age_are_rejected(self):
        for fields in ({"feedback_angles_rad": None}, {"command_angles_rad": None},
                       {"joint_age_s": -1}, {"joint_age_s": float("nan")}):
            records = fixture()
            row = next(row for row in records if row.topic == "/gimbal/diagnostics")
            payload = json.loads(row.message.data)
            payload.update(fields)
            row.message.data = json.dumps(payload)
            self.assertFalse(evaluation.evaluate_records(records, {}, "active")["checks"]["no_bag_read_or_channel_errors"])

    def test_identical_initial_paused_stamp_zero_feedback_is_audited_not_counted(self):
        rows = [evaluation.stage1.Record("/gimbal/joint_states", 0.,
                NS(header=NS(stamp=stamp(0)), name=list(JOINT_NAMES), position=[0., 0., 0.]), 0.)
                for _ in range(12)] + fixture()
        report = evaluation.evaluate_records(rows, {}, "active")
        self.assertEqual(report["result"], "PASS", report["checks"])
        self.assertEqual(report["physical_feedback"]["samples"], 251)
        self.assertEqual(report["physical_feedback"]["recorded_samples"], 263)
        self.assertEqual(report["physical_feedback"]["startup_unready_samples"], 12)

    def test_initial_zero_feedback_cannot_supply_missing_physical_evidence(self):
        rows = [row for row in fixture() if row.topic != "/gimbal/joint_states"]
        rows = [evaluation.stage1.Record("/gimbal/joint_states", 0.,
                NS(header=NS(stamp=stamp(0)), name=list(JOINT_NAMES), position=[0., 0., 0.]))
                for _ in range(100)] + rows
        report = evaluation.evaluate_records(rows, {}, "active")
        self.assertFalse(report["checks"]["three_encoder_joints_recorded"])
        self.assertEqual(report["physical_feedback"]["samples"], 0)

    def test_conflicting_initial_zero_feedback_is_still_a_channel_error(self):
        zeros = [evaluation.stage1.Record("/gimbal/joint_states", 0.,
                 NS(header=NS(stamp=stamp(0)), name=list(JOINT_NAMES), position=angles))
                 for angles in ([0., 0., 0.], [.1, 0., 0.])]
        report = evaluation.evaluate_records(zeros + fixture(), {}, "active")
        self.assertFalse(report["checks"]["no_bag_read_or_channel_errors"])
        self.assertEqual(report["result"], "FAIL_OR_INCOMPLETE")

    def test_positive_duplicate_or_conflicting_feedback_remains_rejected(self):
        for conflict in (False, True):
            rows = fixture()
            original = next(row for row in rows if row.topic == "/gimbal/joint_states")
            angles = list(original.message.position)
            if conflict:
                angles[0] += .1
            duplicate = evaluation.stage1.Record("/gimbal/joint_states", original.time_s,
                        NS(header=NS(stamp=stamp(original.time_s)), name=list(JOINT_NAMES), position=angles))
            rows.insert(rows.index(original)+1, duplicate)
            report = evaluation.evaluate_records(rows, {}, "active")
            self.assertFalse(report["checks"]["three_encoder_joints_recorded"])
            self.assertEqual(report["physical_feedback"]["conflicting_duplicate_source_stamps"], int(conflict))

    def test_later_zero_or_backwards_source_cannot_be_hidden_by_timestamp_sorting(self):
        for source in (0., 1.03):
            rows = fixture()
            rows.append(evaluation.stage1.Record("/gimbal/joint_states", source,
                        NS(header=NS(stamp=stamp(source)), name=list(JOINT_NAMES), position=[0., 0., 0.])))
            report = evaluation.evaluate_records(rows, {}, "active")
            self.assertEqual(report["result"], "FAIL_OR_INCOMPLETE")
            if source == 0:
                self.assertFalse(report["checks"]["no_bag_read_or_channel_errors"])
            else:
                self.assertFalse(report["checks"]["three_encoder_joints_recorded"])

    def test_midpoint_cannot_emit_body_yaw_reference(self):
        records = fixture("midpoint")
        records.append(evaluation.stage1.Record("/gimbal/body_yaw_reference", 3, NS()))
        report = evaluation.evaluate_records(records, {}, "midpoint")
        self.assertFalse(report["checks"]["midpoint_never_publishes_active_yaw"])


if __name__ == "__main__":
    unittest.main()
