"""Offline evaluator must reject fabricated/static/incorrect gimbal evidence."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

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


def paused_fixture(copies=3):
    rows = []
    for row in fixture():
        if row.topic == "/gimbal/joint_states":
            row.message.header.frame_id = "gimbal"
            row.message.velocity = []
            row.message.effort = []
            rows.append(evaluation.stage1.Record("/clock", row.time_s, NS(clock=stamp(row.time_s)), row.time_s))
        rows.append(evaluation.stage1.Record(row.topic, row.time_s, row.message, row.time_s))
    last = next(row for row in reversed(rows) if row.topic == "/gimbal/joint_states")
    rows += [deepcopy(last) for _ in range(copies)]
    count = sum(row.topic == "/clock" for row in rows)
    metadata = {"clock_records_preserved": True, "clock_samples_read": count}
    context = {"recording_closure": {"schema_version":1, "status":"PASS",
        "scope":"WORLD_PAUSE_ACK_AND_OBSERVED_FINAL_SOURCE_CORRESPONDENCE_BEFORE_RECORDER_CLOSE",
        "pause_request":{"command_pause":True,"returncode":0,"response":"data: true\n\n"},
        "observer_cleanup_completed":True, "pause_ack_elapsed_wall_s":.1,
        "observations":[{"ready":True,"failures":[],"errors":[],"last_clock_ns":6_000_000_000}]},
        "bag_integrity":{"schema_version":1,"status":"PASS","recorder_exit_code":0,
            "raw_validation":{"status":"PASS"},
            "native_reader_validation":{"status":"PASS","topic_counts":{"/clock":count}}}}
    return rows, metadata, context


def clock_boundary_fixture(copies=3):
    rows, metadata, context = paused_fixture(copies)
    final_clock_index = next(index for index, row in enumerate(rows) if row.topic == "/clock" and row.time_s == 6.)
    final_clock = rows.pop(final_clock_index)
    prior_index = next(index for index, row in enumerate(rows) if row.topic == "/gimbal/joint_states" and row.time_s == 6.)
    prior = rows[prior_index]
    rows[prior_index] = evaluation.stage1.Record(prior.topic, prior.time_s, prior.message, 5.996)
    rows.insert(prior_index, evaluation.stage1.Record("/clock", 5.996, NS(clock=stamp(5.996)), 5.996))
    rows.insert(prior_index + 2, final_clock)
    rows = [evaluation.stage1.Record(row.topic, row.time_s, row.message, row.received_sim_s, index)
            for index, row in enumerate(rows)]
    metadata["clock_samples_read"] += 1
    context["bag_integrity"]["native_reader_validation"]["topic_counts"]["/clock"] += 1
    return rows, metadata, context


class Stage3EvaluationTests(unittest.TestCase):
    def test_real_feedback_before_immediately_following_final_clock_is_retained(self):
        for copies in (1, 3):
            rows, metadata, context = clock_boundary_fixture(copies)
            prior = next(row for row in rows if row.topic == "/gimbal/joint_states" and row.time_s == 6.)
            report = evaluation.evaluate_records(rows, metadata, "active", pause_context=context)
            self.assertEqual(report["result"], "PASS", report["checks"])
            feedback = report["physical_feedback"]
            audit = feedback["terminal_redundant_message_audit"]
            self.assertEqual(feedback["samples"], 251)
            self.assertEqual(feedback["duplicate_or_nonincreasing_source_stamps"], copies)
            self.assertEqual(feedback["effective_duplicate_or_nonincreasing_source_stamps"], 0)
            self.assertEqual(audit["accepted_redundant_samples"], copies)
            self.assertEqual(audit["retention_mode"], "real_feedback_before_immediately_following_final_clock")
            self.assertEqual(audit["retained_source_s"], 6.)
            self.assertEqual(audit["retained_received_sim_s"], 5.996)
            self.assertEqual(audit["retained_record_sequence"], prior.record_sequence)
            self.assertEqual(evaluation.evaluate_records(rows, metadata, "active")["result"], "FAIL_OR_INCOMPLETE")

    def test_cross_topic_retention_rejects_conflict_clock_step_large_lead_and_multiple_early_duplicates(self):
        for defect in ("position", "velocity", "frame", "clock_step", "large_lead", "lead_limit_plus_one_ns", "two_early_duplicates", "missing_sequence", "regressing_sequence"):
            rows, metadata, context = clock_boundary_fixture()
            prior_index = next(index for index, row in enumerate(rows) if row.topic == "/gimbal/joint_states" and row.time_s == 6.)
            prior = rows[prior_index]
            if defect in {"position", "velocity"}:
                setattr(prior.message, defect, [.25, .0, .0])
            elif defect == "frame":
                prior.message.header.frame_id = "different"
            elif defect == "clock_step":
                rows.insert(prior_index + 1, evaluation.stage1.Record("/clock", 5.998, NS(clock=stamp(5.998)), 5.998))
                rows = [evaluation.stage1.Record(row.topic, row.time_s, row.message, row.received_sim_s, index)
                        for index, row in enumerate(rows)]
                metadata["clock_samples_read"] += 1
                context["bag_integrity"]["native_reader_validation"]["topic_counts"]["/clock"] += 1
            elif defect in {"large_lead", "lead_limit_plus_one_ns"}:
                receipt = 5.94 if defect == "large_lead" else 5.949999999
                rows[prior_index] = evaluation.stage1.Record(prior.topic, prior.time_s, prior.message, receipt, prior.record_sequence)
            elif defect == "two_early_duplicates":
                rows.insert(prior_index + 1, deepcopy(prior))
                rows = [evaluation.stage1.Record(row.topic, row.time_s, row.message, row.received_sim_s, index)
                        for index, row in enumerate(rows)]
            else:
                sequence = None if defect == "missing_sequence" else rows[prior_index-1].record_sequence
                rows[prior_index] = evaluation.stage1.Record(prior.topic, prior.time_s, prior.message, prior.received_sim_s, sequence)
            report = evaluation.evaluate_records(rows, metadata, "active", pause_context=context)
            self.assertEqual(report["result"], "FAIL_OR_INCOMPLETE", defect)
            self.assertGreater(report["physical_feedback"]["effective_duplicate_or_nonincreasing_source_stamps"], 0, defect)
            self.assertNotEqual(report["physical_feedback"]["terminal_redundant_message_audit"].get("retention_mode"),
                                "real_feedback_before_immediately_following_final_clock", defect)
            if defect == "lead_limit_plus_one_ns":
                self.assertIn("preceding_final_source_not_within_existing_future_tolerance",
                              report["physical_feedback"]["terminal_redundant_message_audit"]["preceding_retention_rejected_reasons"])

    def test_cross_topic_retention_accepts_the_exact_existing_fifty_ms_boundary(self):
        rows, metadata, context = clock_boundary_fixture()
        rows = [row for row in rows if not 5.95 < row.time_s < 6.]
        index = next(index for index, row in enumerate(rows) if row.topic == "/gimbal/joint_states" and row.time_s == 6.)
        prior = rows[index]
        rows[index] = evaluation.stage1.Record(prior.topic, prior.time_s, prior.message, 5.95)
        rows.insert(index, evaluation.stage1.Record("/clock", 5.95, NS(clock=stamp(5.95)), 5.95))
        rows = [evaluation.stage1.Record(row.topic, row.time_s, row.message, row.received_sim_s, index)
                for index, row in enumerate(rows)]
        count = sum(row.topic == "/clock" for row in rows)
        metadata["clock_samples_read"] = count
        context["bag_integrity"]["native_reader_validation"]["topic_counts"]["/clock"] = count
        report = evaluation.evaluate_records(rows, metadata, "active", pause_context=context)
        self.assertEqual(report["result"], "PASS", report["checks"])
        audit = report["physical_feedback"]["terminal_redundant_message_audit"]
        self.assertEqual(audit["retained_received_sim_s"], 5.95)
        self.assertEqual(audit["accepted_redundant_samples"], 3)

    def test_reader_preserves_complete_clock_and_restores_topic_filter(self):
        topics = evaluation.stage1.TOPICS
        with patch.object(evaluation.stage1, "read_rosbag", return_value=([], {})) as reader:
            evaluation.read_records(Path("fixture"))
            reader.assert_called_once_with(Path("fixture"), preserve_clock=True)
        self.assertIs(evaluation.stage1.TOPICS, topics)

    def test_cli_exclusively_publishes_provenance_bound_report_and_rejects_overwrite_before_bag_read(self):
        rows, metadata, context = paused_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            trial = Path(tmp); bag = trial / "rosbag"; bag.mkdir()
            context["bag_integrity"]["destination"] = str(bag)
            for name, content in context.items():
                (trial / (name + ".json")).write_text(json.dumps(content), encoding="utf-8")
            source = trial / "plan.json"; source.write_text("{}", encoding="utf-8")
            slot = trial / "slot.json"; slot.write_text("{}", encoding="utf-8")
            old = trial / "gimbal_evaluation.json"; old.write_text("{}", encoding="utf-8")
            output = trial / "gimbal_new.json"
            argv = [str(bag), "--mode", "active", "--source-plan", str(source), "--slot-record", str(slot),
                    "--original-report", str(old), "--output", str(output)]
            metadata["bag"] = str(bag.resolve())
            with patch.object(evaluation, "read_records", return_value=(rows, metadata)), patch("builtins.print"):
                self.assertEqual(evaluation.main(argv), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["evaluation_source"], evaluation.evaluation_source_provenance())
            self.assertEqual(report["input_bindings"]["original_report"], evaluation.small_file_binding(old))
            self.assertEqual(report["input_bindings"]["source_plan"], evaluation.small_file_binding(source))
            self.assertEqual(old.read_text(), "{}")
            with patch.object(evaluation, "read_records") as reader, self.assertRaises(FileExistsError):
                evaluation.main(argv)
            reader.assert_not_called()

    def test_only_closure_bound_complete_identical_terminal_copies_are_excluded(self):
        rows, metadata, context = paused_fixture()
        report = evaluation.evaluate_records(rows, metadata, "active", pause_context=context)
        self.assertEqual(report["result"], "PASS", report["checks"])
        feedback = report["physical_feedback"]
        self.assertEqual(feedback["samples"], 251)
        self.assertEqual(feedback["recorded_samples"], 254)
        self.assertEqual(feedback["duplicate_or_nonincreasing_source_stamps"], 3)
        self.assertEqual(len(feedback["delivery_source_order_errors"]), 3)
        self.assertEqual(feedback["effective_duplicate_or_nonincreasing_source_stamps"], 0)
        self.assertEqual(feedback["terminal_redundant_message_audit"]["accepted_redundant_samples"], 3)
        self.assertEqual(evaluation.evaluate_records(rows, metadata, "active")["result"], "FAIL_OR_INCOMPLETE")

    def test_complete_payload_conflicts_cannot_be_hidden_by_identical_three_angles(self):
        for field, value in (("velocity", [.1, 0, 0]), ("effort", [0, .1, 0]), ("position", [.1, 0, 0])):
            rows, metadata, context = paused_fixture()
            setattr(rows[-1].message, field, value)
            report = evaluation.evaluate_records(rows, metadata, "active", pause_context=context)
            self.assertEqual(report["result"], "FAIL_OR_INCOMPLETE")
            self.assertEqual(report["physical_feedback"]["terminal_redundant_message_audit"]["accepted_redundant_samples"], 0)
        rows, metadata, context = paused_fixture()
        rows[-1].message.header.frame_id = "different"
        self.assertEqual(evaluation.evaluate_records(rows, metadata, "active", pause_context=context)["result"], "FAIL_OR_INCOMPLETE")

    def test_missing_failed_closure_clock_gap_regression_and_final_mismatch_fail_closed(self):
        for defect in ("no_clock", "missing_clock", "clock_regression", "closure_fail", "no_ack", "final_mismatch", "incomplete_payload"):
            rows, metadata, context = paused_fixture()
            if defect == "no_clock":
                rows = [row for row in rows if row.topic != "/clock"]
            elif defect == "missing_clock":
                rows.pop(next(index for index, row in enumerate(rows) if row.topic == "/clock"))
            elif defect == "clock_regression":
                clocks = [row for row in rows if row.topic == "/clock"]
                clocks[10].message.clock = stamp(.01)
            elif defect == "closure_fail":
                context["recording_closure"]["status"] = "FAIL"
            elif defect == "no_ack":
                context["recording_closure"]["pause_request"]["response"] = "data: false"
            elif defect == "final_mismatch":
                context["recording_closure"]["observations"][-1]["last_clock_ns"] += 1
            else:
                del rows[-1].message.velocity
            report = evaluation.evaluate_records(rows, metadata, "active", pause_context=context)
            self.assertEqual(report["result"], "FAIL_OR_INCOMPLETE", defect)

    def test_live_middle_or_regressing_feedback_and_later_zero_stay_failures(self):
        for defect in ("middle", "resume", "regression", "later_zero", "receive_mismatch"):
            rows, metadata, context = paused_fixture()
            if defect == "middle":
                index = next(index for index, row in enumerate(rows) if row.topic == "/gimbal/joint_states")
                rows.insert(index + 1, deepcopy(rows[index]))
            elif defect == "resume":
                rows.append(evaluation.stage1.Record("/clock", 6.1, NS(clock=stamp(6.1)), 6.1))
                metadata["clock_samples_read"] += 1
                context["bag_integrity"]["native_reader_validation"]["topic_counts"]["/clock"] += 1
                context["recording_closure"]["observations"][-1]["last_clock_ns"] = 6_100_000_000
            elif defect in {"regression", "later_zero"}:
                source = 0. if defect == "later_zero" else 5.99
                message = deepcopy(rows[-1].message); message.header.stamp = stamp(source)
                rows.append(evaluation.stage1.Record("/gimbal/joint_states", source, message, 6.))
            else:
                rows[-1] = evaluation.stage1.Record(rows[-1].topic, 6., rows[-1].message, 5.99)
            self.assertEqual(evaluation.evaluate_records(rows, metadata, "active", pause_context=context)["result"], "FAIL_OR_INCOMPLETE", defect)

    def test_terminal_redundancy_never_supplies_fifty_unique_timed_samples(self):
        rows, metadata, context = paused_fixture(copies=100)
        joints = [index for index, row in enumerate(rows) if row.topic == "/gimbal/joint_states"]
        remove = set(joints[:230])
        rows = [row for index, row in enumerate(rows) if index not in remove]
        report = evaluation.evaluate_records(rows, metadata, "active", pause_context=context)
        self.assertFalse(report["checks"]["three_encoder_joints_recorded"])
        self.assertEqual(report["physical_feedback"]["samples"], 21)

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
