"""Offline evaluation must preserve losses and distinguish estimates from truth."""

from __future__ import annotations

import importlib.util
import base64
from contextlib import nullcontext
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_stage1_flight.py"
SPEC = importlib.util.spec_from_file_location("stage1_offline_evaluation", SOURCE)
evaluation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = evaluation
SPEC.loader.exec_module(evaluation)


def stamp(seconds: float):
    value = round(seconds * 1e9)
    return NS(sec=value // 1_000_000_000, nanosec=value % 1_000_000_000)


def record(topic: str, timestamp: float, received=None, **fields):
    return evaluation.Record(topic, timestamp, NS(header=NS(stamp=stamp(timestamp)), **fields), received)


DEFAULT_RECEIVE = object()


def state(timestamp: float, value=1, received=DEFAULT_RECEIVE, uuid="selected-person", class_name="person", track_id=1):
    if received is DEFAULT_RECEIVE:
        received = timestamp
    return record("/tracking/state", timestamp, received, state=value, prediction_age_s=0.0,
                  track_id=track_id, target_uuid=uuid, class_name=class_name)


def selection(timestamp: float, uuid="new-person", action=0, received=DEFAULT_RECEIVE, **fields):
    if received is DEFAULT_RECEIVE:
        received = timestamp
    values = dict(action=action, target_uuid=uuid, track_id=0, class_name="person",
                  center_u_px=5.0, center_v_px=5.0, width_px=10.0, height_px=10.0)
    values.update(fields)
    return record("/tracking/selection", timestamp, received, **values)


def shutter_events(start=1.0, end=4.0):
    return [
        {"kind": "shutter", "time_s": start, "active": True, "request_id": 1, "request_time_s": start},
        {"kind": "shutter_service_result", "time_s": start + .05, "active": True,
         "request_id": 1, "request_time_s": start, "success": True},
        {"kind": "shutter", "time_s": end, "active": False, "request_id": 2, "request_time_s": end},
        {"kind": "shutter_service_result", "time_s": end + .05, "active": False,
         "request_id": 2, "request_time_s": end, "success": True},
    ]


def evaluate_window(window, *args, **kwargs):
    """Use fully acknowledged fixture actions unless a test explicitly bypasses this helper."""
    window = {**window, "close_request_id": 1, "open_request_id": 2}
    kwargs.setdefault("shutter_service_results", [row for row in shutter_events(window["start_s"], window["end_s"])
                                                 if row["kind"] == "shutter_service_result"])
    return evaluation.evaluate_occlusion(window, *args, **kwargs)


def status(timestamp: float, lifecycle=2, error=1.0):
    return record("/tracking/status", timestamp, timestamp, lifecycle=lifecycle, distance_error_m=error,
                  height_error_m=error / 2, reason="tracking" if lifecycle == 2 else "hover")


def sustained_tracking(start=4.2, steps=30, uuid="new-person"):
    times = [round(start + index * .2, 9) for index in range(steps + 1)]
    return [state(timestamp, uuid=uuid) for timestamp in times], [status(timestamp) for timestamp in times]


def tied_reselection_records(*, bad_before_confirmation=True, bad_state=3, bad_uuid="selected-person"):
    """Reader order differs from header order at one operational clock tick."""
    states, statuses = sustained_tracking()
    confirmation = state(4.1, received=4.2, uuid="new-person", track_id=2)
    bad = state(4.2, bad_state, uuid=bad_uuid)
    tied = [bad, confirmation] if bad_before_confirmation else [confirmation, bad]
    rows = [state(.9), state(1.2, 2), state(1.8, 3), status(1.8, 4),
            odometry(1.8, 1), odometry(2, .1), odometry(2.2, .1), odometry(2.41, .1),
            diagnostic(1.2, False), selection(4.1)] + tied
    rows += [statuses[0]]
    for next_state, next_status in zip(states[1:], statuses[1:]):
        rows.extend([next_state, next_status])
    return rows, confirmation, bad


def odometry(timestamp: float, speed=1.0):
    return record("/vehicle/odometry", timestamp, twist=NS(twist=NS(linear=NS(x=speed, y=0.0, z=0.0))))


def diagnostic(timestamp: float, candidate=True):
    return record("/tracking/detection_diagnostics", timestamp + 0.1, data=json.dumps({
        "stamp_s": timestamp, "completed_s": timestamp + 0.1, "inference_wall_s": 0.2,
        "rgb_depth_sync_error_s": 0.01, "class_name": "person",
        "detections": [{"depth_valid": True}] if candidate else [],
    }))


def truth(timestamp: float, entity: str, position, parent="world"):
    transform = NS(header=NS(stamp=stamp(timestamp), frame_id=parent), child_frame_id=entity,
                   transform=NS(translation=NS(x=position[0], y=position[1], z=position[2])))
    return record("/ground_truth/poses", timestamp, transforms=[transform])


class FlightEvaluationTests(unittest.TestCase):
    def test_messages_before_first_clock_are_retained_separately_from_decode_errors(self):
        serialized = [("/tracking/flight_phase", b"phase0", 100),
                      ("/clock", b"clock", 110),
                      ("/tracking/flight_phase", b"phase1", 120),
                      ("/tracking/flight_phase", b"corrupt", 130)]
        messages = {b"phase0": NS(data="WAITING: startup"), b"clock": NS(clock=stamp(2.0)),
                    b"phase1": NS(data="FOLLOW: tracking")}

        class Reader:
            def __init__(self):
                self.index = 0

            def get_all_topics_and_types(self):
                return [NS(name=topic, type="fake/" + topic) for topic in ("/clock", "/tracking/flight_phase")]

            def set_filter(self, _filter):
                pass

            def has_next(self):
                return self.index < len(serialized)

            def read_next(self):
                row = serialized[self.index]
                self.index += 1
                return row

        rows, metadata = evaluation._deserialize_bag(
            Reader(), NS(StorageFilter=lambda **_fields: None), lambda blob, _type: messages[blob], lambda name: name)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].time_s, 2.0)
        self.assertEqual(rows[0].record_sequence, 2)
        self.assertEqual(metadata["startup_unclocked_messages"], {"/tracking/flight_phase": 1})
        untimed = metadata["startup_unclocked_records"][0]
        self.assertEqual(untimed["record_timestamp_ns"], 100)
        self.assertEqual(base64.b64decode(untimed["serialized_cdr_base64"]), b"phase0")
        self.assertEqual(metadata["clock_samples_read"], 1)
        self.assertFalse(metadata["clock_records_preserved"])
        self.assertEqual(sum(metadata["read_errors"].values()), 1)
        self.assertTrue(all("KeyError" in error for error in metadata["read_errors"]))

    def test_clock_record_preservation_is_opt_in_and_keeps_tail_and_original_order(self):
        serialized = [("/clock",b"clock0",0),("/tracking/flight_phase",b"phase",1),("/clock",b"clock_tail",2)]
        messages = {b"clock0":NS(clock=stamp(6.)),b"phase":NS(data="FOLLOW: fixture"),b"clock_tail":NS(clock=stamp(15.))}

        class Reader:
            def __init__(self):self.index=0
            def get_all_topics_and_types(self):return [NS(name=t,type="fixture") for t in ("/clock","/tracking/flight_phase")]
            def set_filter(self,_filter):pass
            def has_next(self):return self.index<len(serialized)
            def read_next(self):
                row=serialized[self.index];self.index+=1;return row

        api=NS(StorageFilter=lambda **fields:None)
        decode=lambda blob,_type:messages[blob]
        old,old_meta=evaluation._deserialize_bag(Reader(),api,decode,lambda name:name)
        kept,kept_meta=evaluation._deserialize_bag(Reader(),api,decode,lambda name:name,preserve_clock=True)
        self.assertEqual([row.topic for row in old],["/tracking/flight_phase"])
        self.assertEqual(max(row.time_s for row in old),6.)
        self.assertEqual([row.record_sequence for row in kept],[0,1,2])
        self.assertEqual([row.topic for row in kept],["/clock","/tracking/flight_phase","/clock"])
        self.assertEqual(kept[-1].time_s,15.)
        self.assertEqual(kept[-1].received_sim_s,15.)
        self.assertEqual(old_meta["clock_samples_read"],kept_meta["clock_samples_read"])
        self.assertFalse(old_meta["clock_records_preserved"])
        self.assertTrue(kept_meta["clock_records_preserved"])

    def test_public_reader_forwards_clock_option_without_changing_default(self):
        modules={"rosbag2_py":NS(),"rclpy.serialization":NS(deserialize_message=lambda *_args:None),
                 "rosidl_runtime_py.utilities":NS(get_message=lambda name:name)}
        with patch.dict(sys.modules,modules), patch.object(evaluation,"open_bag_reader",side_effect=lambda *_args:nullcontext((None,{}))), \
                patch.object(evaluation,"_deserialize_bag",return_value=([],{})) as deserialize:
            evaluation.read_rosbag(Path("fixture_no_bag_read"))
            self.assertIs(deserialize.call_args.kwargs["preserve_clock"],False)
            evaluation.read_rosbag(Path("fixture_no_bag_read"),preserve_clock=True)
            self.assertIs(deserialize.call_args.kwargs["preserve_clock"],True)

    def test_absent_clock_prevents_pass_even_when_other_evidence_would_pass(self):
        rows = [state(1), state(4), status(1), odometry(1), diagnostic(1),
                record("/fmu/out/vehicle_status_v1", 1, arming_state=2, nav_state=14)]
        windows = [{"kind": "short", "result": "PASS"}, {"kind": "long", "result": "PASS"}]
        with patch.object(evaluation, "shutter_windows", return_value=[{"start_s": 1, "end_s": 2}, {"start_s": 2, "end_s": 4}]), \
                patch.object(evaluation, "evaluate_occlusion", side_effect=windows):
            normal = evaluation.evaluate(rows, [], evaluation.EvaluationConfig(), {"clock_recorded": True, "clock_samples_read": 1})
        self.assertEqual(normal["acceptance"]["result"], "PASS")
        with patch.object(evaluation, "shutter_windows", return_value=[{"start_s": 1, "end_s": 2}, {"start_s": 2, "end_s": 4}]), \
                patch.object(evaluation, "evaluate_occlusion", side_effect=windows):
            missing = evaluation.evaluate(rows, [], evaluation.EvaluationConfig(), {"clock_recorded": False, "clock_samples_read": 0,
                "startup_unclocked_messages": {"/tracking/flight_phase": 1}})
        self.assertEqual(missing["acceptance"]["result"], "INCOMPLETE_EVIDENCE")
        self.assertFalse(missing["acceptance"]["clock_timebase_available"])
        self.assertTrue(any("preceding the first /clock" in note for note in missing["limitations"]))

    def test_active_truth_subset_keeps_hover_errors_in_whole_interval(self):
        rows = [state(1), state(4), status(1, 2), status(2, 3), status(3, 4)]
        for timestamp, distance in ((1.0, 5.0), (2.0, 6.0), (3.0, 15.0)):
            rows.extend([truth(timestamp, "target_person", (distance, 0, 0)),
                         truth(timestamp, "stage1_uav", (0, 0, 3))])
        result = evaluation.evaluate(rows, [], evaluation.EvaluationConfig())["ground_truth"]
        self.assertEqual(result["matched_samples"], 3)
        self.assertAlmostEqual(result["horizontal_distance_error_m"]["rmse"], math.sqrt(101 / 3))
        active = result["active_tracking"]
        self.assertEqual(active["matched_samples"], 2)
        self.assertEqual(active["active_duration_s"], 2.0)
        self.assertAlmostEqual(active["horizontal_distance_error_m"]["rmse"], math.sqrt(0.5))
        self.assertEqual(active["height_above_target_origin_error_m"]["rmse"], 1.0)
        self.assertAlmostEqual(active["matched_fraction_of_whole_interval"], 2 / 3)
        self.assertIsNone(result["position_estimation_rmse_m"])

    def test_compressed_bag_uses_temporary_reader_cache_and_preserves_original(self):
        class FakeReader:
            def open(self, storage, _converter):
                self.uri = Path(storage.uri)
                # Model the compression reader's on-disk derived SQLite file.
                (self.uri / "trial.db3").write_text("decompressed temporary data")

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "metadata.yaml").write_text("source metadata")
            (source / "trial.db3.zstd").write_bytes(b"compressed source")
            metadata = NS(compression_format="zstd", compression_mode="FILE", storage_identifier="sqlite3",
                          relative_file_paths=["trial.db3.zstd"])
            api = NS(Info=lambda: NS(read_metadata=lambda *_args: metadata),
                     SequentialCompressionReader=FakeReader, SequentialReader=lambda: self.fail("wrong reader"),
                     StorageOptions=lambda **values: NS(**values), ConverterOptions=lambda **values: NS(**values))
            with evaluation.open_bag_reader(source, api) as (reader, info):
                temporary = reader.uri
                self.assertNotEqual(temporary, source)
                self.assertEqual((temporary / "trial.db3.zstd").read_bytes(), b"compressed source")
                self.assertEqual(info["compression_mode"], "file")
                self.assertTrue(info["source_bag_read_only"])
                self.assertFalse((source / "trial.db3").exists())
            self.assertFalse(temporary.exists())
            self.assertEqual((source / "trial.db3.zstd").read_bytes(), b"compressed source")

    def test_no_truth_never_produces_fabricated_position_rmse(self):
        rows = [state(1), status(1, error=2), status(1.2, lifecycle=4, error=0),
                odometry(1), state(2, 3)]
        result = evaluation.evaluate(rows, [], evaluation.EvaluationConfig())
        self.assertIsNone(result["estimator"]["position_rmse_m"])
        self.assertFalse(result["ground_truth"]["available"])
        self.assertEqual(result["controller"]["estimated_horizontal_distance_error_m"]["rmse"], 2.0)
        self.assertEqual(result["controller"]["lifecycle_counts"]["HOVER"], 1)
        self.assertEqual(result["estimator"]["state_counts"]["LOST"], 1)
        self.assertEqual(result["acceptance"]["result"], "INCOMPLETE_EVIDENCE")
        json.dumps(result, allow_nan=False)

    def test_empty_detector_frames_reduce_availability_and_keep_sim_and_wall_latency_distinct(self):
        rows = [state(1), state(2), diagnostic(1, True), diagnostic(1.5, False)]
        result = evaluation.evaluate(rows, [], evaluation.EvaluationConfig())
        detector = result["detector"]
        self.assertEqual(detector["completed_inference_frames"], 2)
        self.assertEqual(detector["valid_depth_frame_fraction"], 0.5)
        self.assertAlmostEqual(detector["acquisition_to_completed_sim_latency_s"]["median"], 0.1)
        self.assertAlmostEqual(detector["inference_wall_s"]["median"], 0.2)
        self.assertIsNone(detector["recall"])

    def test_truth_requires_uav_truth_and_does_not_fit_px4_world_offset(self):
        rows = [state(1), state(2), odometry(1), truth(1, "target_person", (5, 0, 0))]
        result = evaluation.evaluate(rows, [], evaluation.EvaluationConfig())
        self.assertFalse(result["ground_truth"]["available"])
        rows += [truth(1, "stage1_uav", (0, 0, 3))]
        result = evaluation.evaluate(rows, [], evaluation.EvaluationConfig())
        metrics = result["ground_truth"]
        self.assertTrue(metrics["available"])
        self.assertEqual(metrics["horizontal_distance_error_m"]["rmse"], 0.0)
        self.assertEqual(metrics["height_above_target_origin_error_m"]["rmse"], 1.0)
        self.assertIsNone(metrics["position_estimation_rmse_m"])
        different_frame = rows[:-1] + [truth(1, "stage1_uav", (0, 0, 3), parent="other_world")]
        self.assertFalse(evaluation.evaluate(different_frame, [], evaluation.EvaluationConfig())["ground_truth"]["available"])

    def test_requested_occlusion_without_detection_interruption_is_retained_as_failure(self):
        rows = [state(1), state(1.1, 2), state(1.5), state(2), diagnostic(1.2, True)]
        events = shutter_events(1.0, 1.4)
        result = evaluation.evaluate(rows, events, evaluation.EvaluationConfig())
        self.assertEqual(len(result["occlusions"]), 1)
        self.assertEqual(result["occlusions"][0]["result"], "FAIL")
        self.assertEqual(result["acceptance"]["result"], "FAIL")

    def test_long_occlusion_measures_actual_braking_and_requires_sustained_low_speed(self):
        after_states, after_statuses = sustained_tracking()
        states = [state(0.9), state(1.2, 2), state(1.8, 3)] + after_states
        statuses = [status(0.9), status(1.8, 4)] + after_statuses
        odom = [odometry(0.9, 1), odometry(1.8, 1), odometry(2.0, 0.2),
                odometry(2.2, 0.1), odometry(2.41, 0.1)]
        diagnostics = [{"stamp_s": 1.2, "valid_depth": False, "has_candidate": False}]
        result = evaluate_window({"start_s": 1.0, "end_s": 4.0, "complete": True},
                                               states, statuses, odom, diagnostics, evaluation.EvaluationConfig(), 10.2,
                                               selections=[selection(4.1)])
        self.assertEqual(result["result"], "PASS")
        self.assertAlmostEqual(result["time_to_sustained_low_speed_after_hover_s"], 0.2)
        self.assertTrue(result["braking_from_motion_demonstrated"])
        isolated = evaluate_window({"start_s": 1.0, "end_s": 4.0, "complete": True},
                                                 states, statuses, odom[:3], diagnostics, evaluation.EvaluationConfig(), 5.0)
        self.assertEqual(isolated["result"], "FAIL")
        self.assertFalse(isolated["checks"]["sustained_low_speed_after_hover"])

    def test_recovery_time_uses_receive_clock_not_delayed_image_stamp(self):
        rows = [state(0.9), state(1.1, 2), state(1.5, received=1.8), state(2),
                diagnostic(1.2, False)]
        events = shutter_events(1.0, 1.4)
        result = evaluation.evaluate(rows, events, evaluation.EvaluationConfig())
        self.assertAlmostEqual(result["occlusions"][0]["recovery_after_open_s"], 0.4)
        self.assertAlmostEqual(result["estimator"]["measured_message_receive_lag_s"]["max"], 0.3)

    def test_long_loss_cannot_resume_without_recorded_explicit_selection(self):
        states = [state(0.9), state(1.1, 2), state(1.8, 3), state(4.2, uuid="new-person")]
        statuses = [status(1), status(1.8, 4)]
        odom = [odometry(1.8, 1), odometry(2.0, .1), odometry(2.2, .1), odometry(2.41, .1)]
        diagnostics = [{"stamp_s": 1.2, "valid_depth": False, "has_candidate": False}]
        args = ({"start_s": 1, "end_s": 4, "complete": True}, states, statuses,
                odom, diagnostics, evaluation.EvaluationConfig(), 5)
        unauthorized = evaluate_window(*args)
        self.assertEqual(unauthorized["result"], "FAIL")
        self.assertEqual(unauthorized["first_unrequested_measured_after_loss_s"], 4.2)
        authorized = evaluate_window(*args, selections=[selection(4.1)])
        self.assertTrue(authorized["explicit_reselection"]["confirmed"])
        self.assertTrue(authorized["checks"]["no_automatic_recovery_after_long_loss"])
        self.assertEqual(authorized["result"], "FAIL")  # Too brief to demonstrate sustained restart.
        # A later explicit operation cannot retrospectively authorize recovery.
        late = evaluate_window(*args, selections=[selection(4.3)])
        self.assertEqual(late["result"], "FAIL")

    def test_late_pre_shutter_frame_cannot_certify_short_occlusion_recovery(self):
        rows = [state(.9), state(1.1, 2), state(.95, received=1.5), state(1.7, 3),
                state(2, 3), diagnostic(1.2, False)]
        events = shutter_events(1.0, 1.4)
        event = evaluation.evaluate(rows, events, evaluation.EvaluationConfig())["occlusions"][0]
        self.assertEqual(event["result"], "FAIL")
        self.assertIsNone(event["first_measured_after_open_s"])
        self.assertFalse(event["checks"]["no_loss_during_short_occlusion"])

    def test_short_recovery_requires_receive_and_acquisition_after_open(self):
        events = shutter_events(1.0, 1.4)
        # A future source stamp cannot make a sample received before opening
        # into recovery evidence. Missing receive time is also insufficient.
        for received in (1.3, None):
            with self.subTest(received=received):
                rows = [state(.9), state(1.1, 2), state(1.5, received=received),
                        status(2.0), diagnostic(1.2, False)]
                event = evaluation.evaluate(rows, events, evaluation.EvaluationConfig())["occlusions"][0]
                self.assertEqual(event["result"], "INCOMPLETE_EVIDENCE")
                self.assertIsNone(event["first_measured_after_open_s"])
                self.assertIsNone(event["checks"]["identity_preserved_on_observed_recovery"])
                self.assertEqual(event["post_open_measured_missing_receive_time_count"], int(received is None))
        # Exact opening-time evidence on both clocks is valid.
        rows = [state(.9), state(1.1, 2), state(1.4, received=1.4), status(2.0), diagnostic(1.2, False)]
        event = evaluation.evaluate(rows, events, evaluation.EvaluationConfig())["occlusions"][0]
        self.assertEqual(event["result"], "PASS")
        self.assertEqual(event["first_measured_after_open_s"], 1.4)

    def test_long_loss_rejects_predicted_reactivation_before_selection(self):
        states = [state(.9), state(1.1, 2), state(1.8, 3), state(4.2, 2)]
        statuses = [status(1.8, 4)]
        odom = [odometry(1.8, 1), odometry(2, .1), odometry(2.2, .1), odometry(2.41, .1)]
        diagnostics = [{"stamp_s": 1.2, "valid_depth": False, "has_candidate": False}]
        args = ({"start_s": 1, "end_s": 4, "complete": True}, states, statuses,
                odom, diagnostics, evaluation.EvaluationConfig(), 5)
        for selections in (None, [selection(4.3)]):
            with self.subTest(selections=selections):
                event = evaluate_window(*args, selections=selections)
                self.assertEqual(event["result"], "FAIL")
                self.assertIsNone(event["first_unrequested_measured_after_loss_s"])
                self.assertEqual(event["first_unrequested_predicted_after_loss_s"], 4.2)
                self.assertEqual(event["first_unrequested_active_state_after_loss_s"], 4.2)
                self.assertFalse(event["checks"]["no_automatic_recovery_after_long_loss"])
                self.assertTrue(event["checks"]["no_tracking_control_before_reselection_after_long_loss"])
        states.insert(-1, state(4.15, uuid="new-person"))
        for action in (0, 2):
            event = evaluate_window(*args, selections=[selection(4.1, action=action)])
            self.assertTrue(event["explicit_reselection"]["confirmed"])
            self.assertTrue(event["checks"]["no_automatic_recovery_after_long_loss"])
            self.assertEqual(event["result"], "FAIL")  # The later original UUID is still forbidden.
            self.assertFalse(event["post_reselection_tracking"]["checks"]["same_target_active_states_only"])

    def test_long_loss_independently_rejects_tracking_control_after_grace(self):
        states = [state(.9), state(1.1, 2), state(1.8, 3), state(4.5, 3)]
        odom = [odometry(1.8, 1), odometry(2, .1), odometry(2.2, .1), odometry(2.41, .1)]
        diagnostics = [{"stamp_s": 1.2, "valid_depth": False, "has_candidate": False}]
        for lifecycle in (2, 3):
            with self.subTest(lifecycle=lifecycle):
                statuses = [status(1.8, 4), status(4.2, lifecycle)]
                args = ({"start_s": 1, "end_s": 4, "complete": True}, states, statuses,
                        odom, diagnostics, evaluation.EvaluationConfig(), 5)
                event = evaluate_window(*args)
                self.assertEqual(event["result"], "FAIL")
                self.assertIsNone(event["first_unrequested_active_state_after_loss_s"])
                self.assertEqual(event["first_unrequested_tracking_control_after_loss_s"], 4.2)
                self.assertTrue(event["checks"]["no_automatic_recovery_after_long_loss"])
                self.assertFalse(event["checks"]["no_tracking_control_before_reselection_after_long_loss"])
                with_confirmation = sorted(states + [state(4.15, uuid="new-person")], key=lambda row: row.time_s)
                allowed = evaluate_window(args[0], with_confirmation, *args[2:], selections=[selection(4.1)])
                self.assertTrue(allowed["checks"]["no_tracking_control_before_reselection_after_long_loss"])
                self.assertEqual(allowed["result"], "FAIL")  # Subsequent LOST still invalidates restart.
        # A queued FOLLOW/PREDICT status in the two-tick grace interval does
        # not establish an automatic restart when HOVER immediately resumes.
        statuses = [status(1.8, 4), status(1.89, 2), status(1.90, 4)]
        event = evaluate_window({"start_s": 1, "end_s": 4, "complete": True},
            states, statuses, odom, diagnostics, evaluation.EvaluationConfig(), 5)
        self.assertIsNone(event["first_unrequested_tracking_control_after_loss_s"])
        self.assertTrue(event["checks"]["no_tracking_control_before_reselection_after_long_loss"])

    def test_shutter_execution_requires_each_correlated_successful_response(self):
        rows = [state(.9), state(1.1, 2), state(1.5), status(2.0), diagnostic(1.2, False)]
        good = shutter_events(1.0, 1.4)
        event = evaluation.evaluate(rows, good, evaluation.EvaluationConfig())["occlusions"][0]
        self.assertEqual(event["result"], "PASS")
        self.assertTrue(event["shutter_execution"]["close_success"])
        self.assertTrue(event["shutter_execution"]["open_success"])
        self.assertTrue(event["shutter_execution"]["close_ack_before_open_request"])
        for index in (1, 3):
            with self.subTest(failed_response=index):
                failed = [dict(row) for row in good]
                failed[index]["success"] = False
                event = evaluation.evaluate(rows, failed, evaluation.EvaluationConfig())["occlusions"][0]
                self.assertEqual(event["result"], "FAIL")
        for mutation in (dict(active=False), dict(request_time_s=1.01)):
            with self.subTest(mutation=mutation):
                mismatched = [dict(row) for row in good]
                mismatched[1].update(mutation)
                event = evaluation.evaluate(rows, mismatched, evaluation.EvaluationConfig())["occlusions"][0]
                self.assertEqual(event["result"], "FAIL")
        duplicated = good + [dict(good[1])]
        event = evaluation.evaluate(rows, duplicated, evaluation.EvaluationConfig())["occlusions"][0]
        self.assertEqual(event["result"], "FAIL")
        late = [dict(row) for row in good]
        late[1]["time_s"] = 1.45
        event = evaluation.evaluate(rows, late, evaluation.EvaluationConfig())["occlusions"][0]
        self.assertEqual(event["result"], "FAIL")
        self.assertFalse(event["shutter_execution"]["close_ack_before_open_request"])

    def test_legacy_or_missing_shutter_response_cannot_pass_new_contract(self):
        rows = [state(.9), state(1.1, 2), state(1.5), status(2.0), diagnostic(1.2, False)]
        old = [{"kind": "shutter", "time_s": 1.0, "active": True},
               {"kind": "shutter_service_result", "time_s": 1.05, "success": True},
               {"kind": "shutter", "time_s": 1.4, "active": False},
               {"kind": "shutter_service_result", "time_s": 1.45, "success": True}]
        for events in (old, shutter_events(1, 1.4)[:-1]):
            with self.subTest(events=events):
                report = evaluation.evaluate(rows, events, evaluation.EvaluationConfig())
                self.assertEqual(report["schema_version"], 3)
                self.assertEqual(report["occlusions"][0]["result"], "INCOMPLETE_EVIDENCE")

    def test_invalid_box_selection_or_uuid_cannot_authorize_long_loss_return(self):
        states = [state(.9), state(1.1, 2), state(1.8, 3), state(4.2, uuid="new-person")]
        statuses = [status(1.8, 4)]
        odom = [odometry(1.8, 1), odometry(2, .1), odometry(2.2, .1), odometry(2.41, .1)]
        diagnostics = [{"stamp_s": 1.2, "valid_depth": False, "has_candidate": False}]
        args = ({"start_s": 1, "end_s": 4, "complete": True}, states, statuses,
                odom, diagnostics, evaluation.EvaluationConfig(), 5)
        invalid = [selection(4.1, uuid=""), selection(4.1, uuid="selected-person"),
                   selection(4.1, width_px=0.0, height_px=0.0), selection(4.1, class_name="car"),
                   selection(4.1, received=None), selection(4.1, uuid="different-new-person"),
                   selection(4.1, action=1), selection(4.1, track_id=99)]
        for request in invalid:
            with self.subTest(request=vars(request.message)):
                event = evaluate_window(*args, selections=[request])
                self.assertEqual(event["result"], "FAIL")
                self.assertFalse(event["explicit_reselection"]["confirmed"])
                self.assertIsNone(event["first_explicit_reselection_s"])
                self.assertEqual(event["first_unrequested_measured_after_loss_s"], 4.2)
        for action in (0, 2):
            event = evaluate_window(*args, selections=[selection(4.1, action=action)])
            confirmation = event["explicit_reselection"]
            self.assertEqual(event["result"], "FAIL")  # Confirmation alone does not prove five seconds.
            self.assertFalse(event["post_reselection_tracking"]["checks"]["minimum_recording_duration"])
            self.assertTrue(confirmation["confirmed"])
            self.assertEqual(confirmation["original_target_uuid"], "selected-person")
            self.assertEqual(confirmation["confirmed_target_uuid"], "new-person")
            self.assertEqual(confirmation["action"], "SELECT" if action == 0 else "RESET")
            self.assertEqual(confirmation["selection_time_s"], 4.1)
            self.assertEqual(confirmation["confirmation_time_s"], 4.2)

    def test_reselection_needs_fresh_first_measurement_of_the_new_task(self):
        base = [state(.9), state(1.1, 2), state(1.8, 3)]
        statuses = [status(1.8, 4)]
        odom = [odometry(1.8, 1), odometry(2, .1), odometry(2.2, .1), odometry(2.41, .1)]
        diagnostics = [{"stamp_s": 1.2, "valid_depth": False, "has_candidate": False}]
        # A delayed, pre-open image is not fresh confirmation even with the
        # requested new UUID. The operational row time is its delivery time.
        delayed = state(3.9, received=4.2, uuid="new-person")
        delayed = evaluation.Record(delayed.topic, 4.2, delayed.message, delayed.received_sim_s)
        for after in (
            [state(4.2, 3)],  # no measurement
            [state(4.2, uuid="selected-person")],
            [state(4.2, 2, uuid="new-person")],
            [state(4.2, uuid="new-person", received=None)],
            [delayed],
            [state(4.15), state(4.2, uuid="new-person")],
        ):
            with self.subTest(after=after):
                event = evaluate_window({"start_s": 1, "end_s": 4, "complete": True},
                    base + after, statuses, odom, diagnostics, evaluation.EvaluationConfig(), 5,
                    selections=[selection(4.1)])
                self.assertFalse(event["explicit_reselection"]["confirmed"])
                self.assertIsNone(event["first_explicit_reselection_s"])
                if after[0].message.state in {1, 2}:
                    self.assertEqual(event["result"], "FAIL")
        # A real track-ID selection must also confirm that same track.
        event = evaluate_window({"start_s": 1, "end_s": 4, "complete": True},
            base + [state(4.2, uuid="new-person", track_id=2)], statuses, odom, diagnostics,
            evaluation.EvaluationConfig(), 5, selections=[selection(4.1, track_id=2)])
        self.assertTrue(event["explicit_reselection"]["confirmed"])

    @staticmethod
    def confirmed_selection():
        return {"confirmed": True, "confirmed_target_uuid": "new-person", "confirmation_time_s": 4.2,
                "confirmation_state_index": 0}

    def test_equal_clock_lost_before_confirmation_does_not_pollute_sustained_interval(self):
        rows, confirmation, bad = tied_reselection_records()
        report = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())
        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["evaluation_revision"], 3)
        event = report["occlusions"][0]
        confirmed = event["explicit_reselection"]
        sustained = event["post_reselection_tracking"]
        self.assertTrue(confirmed["confirmed"])
        self.assertEqual(confirmed["confirmation_time_s"], 4.2)
        self.assertEqual(confirmed["confirmation_record_sequence"], rows.index(confirmation))
        self.assertEqual(sustained["result"], "PASS", sustained["checks"])
        self.assertEqual(sustained["boundary_evidence"], "RECORD_SEQUENCE")
        self.assertNotIn("LOST", sustained["state_counts"])
        # Original failures remain in the full-trial metrics.
        self.assertEqual(report["estimator"]["state_counts"]["LOST"], 2)

    def test_equal_clock_fault_after_confirmation_is_never_removed(self):
        for code, uuid in ((3, "selected-person"), (3, "new-person"),
                           (4, "new-person"), (1, "selected-person")):
            with self.subTest(code=code, uuid=uuid):
                rows, confirmation, bad = tied_reselection_records(
                    bad_before_confirmation=False, bad_state=code, bad_uuid=uuid)
                event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
                self.assertTrue(event["explicit_reselection"]["confirmed"])
                result = event["post_reselection_tracking"]
                self.assertEqual(result["result"], "FAIL")
                self.assertFalse(result["checks"]["same_target_active_states_only"])
                self.assertEqual(result["first_invalid_state_s"], 4.2)

    def test_equal_clock_old_active_before_confirmation_cannot_be_skipped(self):
        for code in (1, 2):
            with self.subTest(code=code):
                rows, _, _ = tied_reselection_records(bad_state=code)
                event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
                self.assertFalse(event["explicit_reselection"]["confirmed"])
                self.assertEqual(event["result"], "FAIL")
                self.assertIn("first_active_state_does_not_confirm_fresh_new_task",
                              event["explicit_reselection"]["invalid_candidates"][0]["reasons"])

    def test_preconfirmation_future_time_lost_is_excluded_by_record_sequence(self):
        rows, confirmation, bad = tied_reselection_records()
        bad_index = rows.index(bad)
        rows[bad_index] = state(4.25, 3, received=4.2)
        event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
        result = event["post_reselection_tracking"]
        self.assertEqual(result["result"], "PASS", result["checks"])
        self.assertNotIn("LOST", result["state_counts"])

    def test_first_active_after_request_cannot_be_skipped_when_its_time_regresses(self):
        for uuid in ("selected-person", "new-person"):
            with self.subTest(uuid=uuid):
                rows, confirmation, bad = tied_reselection_records()
                request_index = next(index for index, row in enumerate(rows) if row.topic == "/tracking/selection")
                rows.insert(request_index+1, state(4.05, uuid=uuid))
                event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
                self.assertFalse(event["explicit_reselection"]["confirmed"])
                self.assertEqual(event["result"], "FAIL")

    def test_first_active_after_request_uses_reader_order_even_with_future_stamp(self):
        rows, confirmation, bad = tied_reselection_records()
        bad_index = rows.index(bad)
        rows[bad_index] = state(4.25, 1, received=4.2)
        event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
        self.assertFalse(event["explicit_reselection"]["confirmed"])
        self.assertEqual(event["result"], "FAIL")

    def test_postconfirmation_backdated_lost_is_retained_and_fails_chronology(self):
        rows, confirmation, bad = tied_reselection_records(bad_before_confirmation=False)
        bad_index = rows.index(bad)
        rows[bad_index] = state(4.15, 3, received=4.15)
        event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
        self.assertTrue(event["explicit_reselection"]["confirmed"])
        result = event["post_reselection_tracking"]
        self.assertEqual(result["result"], "FAIL")
        self.assertFalse(result["checks"]["same_target_active_states_only"])
        self.assertFalse(result["checks"]["chronological_state_and_control_evidence"])
        self.assertEqual(result["first_invalid_state_s"], 4.15)
        self.assertEqual(result["state_time_regression_count"], 1)

    def test_postconfirmation_old_image_is_not_sorted_before_the_confirmation_record(self):
        rows, confirmation, bad = tied_reselection_records(bad_before_confirmation=False, bad_state=1)
        bad_index = rows.index(bad)
        rows[bad_index] = state(4.05, received=4.2)
        event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
        self.assertTrue(event["explicit_reselection"]["confirmed"])
        self.assertEqual(event["post_reselection_tracking"]["result"], "FAIL")
        self.assertEqual(event["post_reselection_tracking"]["first_uuid_mismatch_s"], 4.2)

    def test_real_sixteen_ms_prediction_to_measurement_operational_regressions_are_diagnostic(self):
        for start, predicted_source, received, image_source in (
            (54.2, 55.240, 55.224, 55.100), (59.6, 60.640, 60.624, 60.500),
        ):
            with self.subTest(predicted_source=predicted_source):
                states, statuses = sustained_tracking(start=start)
                predicted = state(predicted_source, 2, received=received, uuid="new-person")
                predicted.message.prediction_age_s = .34
                measured = state(image_source, received=received, uuid="new-person")
                records = evaluation.with_record_sequence(sorted(
                    states + statuses + [predicted, measured], key=lambda row: row.received_sim_s))
                operational_states = [evaluation.replace(row, time_s=max(row.time_s, row.received_sim_s))
                                      for row in records if row.topic == "/tracking/state"]
                controls = [row for row in records if row.topic == "/tracking/status"]
                request = {"confirmed": True, "confirmed_target_uuid": "new-person",
                           "confirmation_time_s": start,
                           "confirmation_record_sequence": operational_states[0].record_sequence}
                result = evaluation.post_reselection_tracking(
                    operational_states, controls, request, start+6, evaluation.EvaluationConfig())
                self.assertEqual(result["result"], "PASS", result["checks"])
                self.assertEqual(result["state_time_regression_count"], 1)
                self.assertEqual(result["receive_clock_regression_count"], 0)
                self.assertTrue(result["operational_time_regressions_are_diagnostic_only"])

    def test_real_receive_clock_regression_fails_even_with_monotonic_headers(self):
        rows, _, _ = tied_reselection_records()
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.time_s == 4.4)
        rows[index] = evaluation.replace(rows[index], received_sim_s=4.15)
        event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
        result = event["post_reselection_tracking"]
        self.assertTrue(result["checks"]["same_target_active_states_only"])
        self.assertEqual(result["state_time_regression_count"], 0)
        self.assertEqual(result["receive_clock_regression_count"], 1)
        self.assertFalse(result["checks"]["chronological_state_and_control_evidence"])
        self.assertEqual(result["result"], "FAIL")

    def test_receive_clock_regression_between_streams_cannot_be_hidden_by_per_stream_checks(self):
        rows, _, _ = tied_reselection_records()
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/status" and row.time_s == 4.4)
        rows[index] = evaluation.replace(rows[index], received_sim_s=4.35)
        event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
        result = event["post_reselection_tracking"]
        self.assertEqual(result["receive_clock_order_scope"], "GLOBAL_RECORD_SEQUENCE")
        self.assertEqual(result["receive_clock_regression_count"], 1)
        self.assertEqual(result["result"], "FAIL")

    def test_invalid_or_missing_receive_clock_never_passes(self):
        for received in (None, math.nan, math.inf, -1.0):
            with self.subTest(received=received):
                states, statuses = sustained_tracking()
                states[10] = evaluation.replace(states[10], received_sim_s=received)
                result = evaluation.post_reselection_tracking(
                    states, statuses, self.confirmed_selection(), 10.2, evaluation.EvaluationConfig())
                self.assertEqual(result["invalid_receive_clock_count"], 1)
                self.assertIsNone(result["checks"]["chronological_state_and_control_evidence"])
                self.assertEqual(result["result"], "INCOMPLETE_EVIDENCE")

    def test_prediction_tail_anchor_uses_its_receive_clock_as_chronology_origin(self):
        states, statuses = sustained_tracking(start=55.240)
        states[0] = state(55.240, 2, received=55.224, uuid="new-person")
        statuses[0] = evaluation.replace(statuses[0], received_sim_s=55.224)
        request = {"confirmed": True, "confirmed_target_uuid": "new-person",
                   "confirmation_time_s": 55.240, "confirmation_state_index": 0}
        result = evaluation.post_reselection_tracking(
            states, statuses, request, 61.240, evaluation.EvaluationConfig())
        self.assertEqual(result["result"], "PASS", result["checks"])
        self.assertEqual(result["receive_clock_regression_count"], 0)

    def test_preconfirmation_control_cannot_satisfy_postconfirmation_grace(self):
        rows, confirmation, bad = tied_reselection_records()
        rows = [row for row in rows if not (row.topic == "/tracking/status" and row.time_s == 4.2)]
        rows.insert(rows.index(confirmation), status(4.2))
        event = evaluation.evaluate(rows, shutter_events(), evaluation.EvaluationConfig())["occlusions"][0]
        result = event["post_reselection_tracking"]
        self.assertFalse(result["checks"]["tracking_control_only_after_grace"])
        self.assertEqual(result["result"], "FAIL")

    def test_explicit_reader_sequence_survives_pre_sorted_input(self):
        rows, confirmation, _ = tied_reselection_records()
        numbered = evaluation.with_record_sequence(rows)
        source_sorted = sorted(numbered, key=lambda row: row.time_s)
        report = evaluation.evaluate(source_sorted, shutter_events(), evaluation.EvaluationConfig())
        event = report["occlusions"][0]
        self.assertEqual(event["post_reselection_tracking"]["result"], "PASS")
        self.assertEqual(event["explicit_reselection"]["confirmation_record_sequence"], rows.index(confirmation))

    def test_post_reselection_requires_exact_boundary_evidence(self):
        states, statuses = sustained_tracking()
        request = {"confirmed": True, "confirmed_target_uuid": "new-person", "confirmation_time_s": 4.2}
        result = evaluation.post_reselection_tracking(states, statuses, request, 10.2, evaluation.EvaluationConfig())
        self.assertEqual(result["result"], "INCOMPLETE_EVIDENCE")
        self.assertEqual(result["boundary_evidence"], "UNAVAILABLE")
        request["confirmation_state_index"] = 1
        result = evaluation.post_reselection_tracking(states, statuses, request, 10.2, evaluation.EvaluationConfig())
        self.assertEqual(result["result"], "INCOMPLETE_EVIDENCE")
        self.assertEqual(result["boundary_evidence"], "INVALID_BOUNDARY_TIME")

    def test_reselection_sustained_tracking_needs_five_seconds_and_fresh_trial_tail(self):
        states, statuses = sustained_tracking()
        result = evaluation.post_reselection_tracking(
            states, statuses, self.confirmed_selection(), 10.25, evaluation.EvaluationConfig())
        self.assertEqual(result["result"], "PASS")
        self.assertTrue(all(value is True for value in result["checks"].values()))
        self.assertAlmostEqual(result["state_span_s"], 6.0)
        self.assertAlmostEqual(result["last_state_age_to_trial_end_s"], .05)
        self.assertAlmostEqual(result["last_state_measurement_age_at_trial_end_s"], .05)
        no_request = evaluation.post_reselection_tracking(
            states, statuses, None, 10.25, evaluation.EvaluationConfig())
        self.assertEqual(no_request["result"], "INCOMPLETE_EVIDENCE")

    def test_reselection_brief_follow_then_lost_is_an_explicit_failure(self):
        states, statuses = sustained_tracking(steps=5)  # One second of FOLLOW.
        states += [state(5.25, 3, uuid="new-person"), state(10.2, 3, uuid="new-person")]
        statuses += [status(5.25, 4), status(10.2, 4)]
        result = evaluation.post_reselection_tracking(
            states, statuses, self.confirmed_selection(), 10.2, evaluation.EvaluationConfig())
        self.assertEqual(result["result"], "FAIL")
        self.assertFalse(result["checks"]["minimum_control_span"])
        self.assertFalse(result["checks"]["same_target_active_states_only"])
        self.assertFalse(result["checks"]["tracking_control_at_trial_end"])
        self.assertEqual(result["first_invalid_state_s"], 5.25)
        self.assertEqual(result["first_nontracking_control_after_grace_s"], 5.25)

    def test_reselection_rejects_any_later_loss_ambiguity_or_identity_change(self):
        for code, uuid in ((0, "new-person"), (3, "new-person"), (4, "new-person"), (1, "other-person")):
            with self.subTest(code=code, uuid=uuid):
                states, statuses = sustained_tracking()
                states[10] = state(6.2, code, uuid=uuid)
                result = evaluation.post_reselection_tracking(
                    states, statuses, self.confirmed_selection(), 10.2, evaluation.EvaluationConfig())
                self.assertEqual(result["result"], "FAIL")
                self.assertFalse(result["checks"]["same_target_active_states_only"])
                self.assertEqual(result["first_invalid_state_s"], 6.2)
                if uuid == "other-person":
                    self.assertEqual(result["first_uuid_mismatch_s"], 6.2)
        states, statuses = sustained_tracking()
        statuses[10] = status(6.2, 4)
        result = evaluation.post_reselection_tracking(
            states, statuses, self.confirmed_selection(), 10.2, evaluation.EvaluationConfig())
        self.assertFalse(result["checks"]["tracking_control_only_after_grace"])

    def test_reselection_sparse_samples_or_missing_trial_tail_cannot_pass(self):
        states, statuses = sustained_tracking()
        for state_rows, control_rows, failed_check in (
            ([states[0], states[-1]], statuses, "continuous_state_evidence"),
            (states, [statuses[0], statuses[-1]], "continuous_control_evidence"),
            (states[:-5], statuses, "fresh_state_at_trial_end"),
            (states, statuses[:-5], "tracking_control_at_trial_end"),
        ):
            with self.subTest(check=failed_check):
                result = evaluation.post_reselection_tracking(
                    state_rows, control_rows, self.confirmed_selection(), 10.2, evaluation.EvaluationConfig())
                self.assertEqual(result["result"], "FAIL")
                self.assertFalse(result["checks"][failed_check])

    def test_reselection_recent_prediction_must_still_have_fresh_measurement(self):
        states, statuses = sustained_tracking()
        states[-1] = state(10.2, 2, uuid="new-person")
        states[-1].message.prediction_age_s = .8
        result = evaluation.post_reselection_tracking(
            states, statuses, self.confirmed_selection(), 10.2, evaluation.EvaluationConfig())
        self.assertEqual(result["result"], "FAIL")
        self.assertFalse(result["checks"]["fresh_state_at_trial_end"])
        states[-1] = state(10.2, uuid="new-person", received=None)
        result = evaluation.post_reselection_tracking(
            states, statuses, self.confirmed_selection(), 10.2, evaluation.EvaluationConfig())
        self.assertEqual(result["result"], "INCOMPLETE_EVIDENCE")
        self.assertIsNone(result["checks"]["fresh_state_at_trial_end"])

    def test_reselection_control_transition_grace_is_bounded(self):
        states, statuses = sustained_tracking()
        statuses = [status(4.2, 4), status(4.25)] + statuses[1:]
        allowed = evaluation.post_reselection_tracking(
            states, statuses, self.confirmed_selection(), 10.2, evaluation.EvaluationConfig())
        self.assertEqual(allowed["result"], "PASS")
        statuses.insert(2, status(4.31, 4))
        failed = evaluation.post_reselection_tracking(
            states, statuses, self.confirmed_selection(), 10.2, evaluation.EvaluationConfig())
        self.assertEqual(failed["result"], "FAIL")
        self.assertFalse(failed["checks"]["tracking_control_only_after_grace"])

    def test_partial_time_slice_does_not_claim_to_cover_the_recorded_trial_tail(self):
        states, statuses = sustained_tracking()
        # A later loss cannot be hidden by making an earlier local tail look fresh.
        rows = states + statuses + [state(11.0, 3, uuid="new-person")]
        clipped = evaluation.evaluate(rows, [], evaluation.EvaluationConfig(start_s=4.2, end_s=10.2))
        self.assertFalse(clipped["interval"]["covers_recorded_trial_end"])
        self.assertEqual(clipped["interval"]["recorded_end_s"], 11.0)
        full = evaluation.evaluate(rows, [], evaluation.EvaluationConfig(start_s=4.2))
        self.assertTrue(full["interval"]["covers_recorded_trial_end"])
        self.assertEqual(full["interval"]["end_s"], 11.0)

    def test_unclosed_shutter_event_is_incomplete_and_not_silently_dropped(self):
        events = [{"kind": "shutter", "time_s": 1.0, "active": True}]
        windows = evaluation.shutter_windows(events)
        self.assertEqual(len(windows), 1)
        self.assertFalse(windows[0]["complete"])
        self.assertIsNone(windows[0]["end_s"])

    def test_stats_drop_nonfinite_values_and_serialize_strict_json(self):
        stats = evaluation.summary([0.0, 2.0, math.inf, math.nan])
        self.assertEqual(stats["count"], 2)
        self.assertEqual(stats["rmse"], math.sqrt(2))
        json.dumps(stats, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
