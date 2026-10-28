"""Stage-two safety evidence must not be inferred from stable task UUIDs."""

import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_stage2_flight as evaluation


def stamp(seconds):
    value = round(seconds*1e9)
    return NS(sec=value//1_000_000_000, nanosec=value % 1_000_000_000)


def record(topic, received, *, acquired=None, **fields):
    acquired = received if acquired is None else acquired
    return evaluation.base.Record(topic, acquired, NS(header=NS(stamp=stamp(acquired)), **fields), received)


def fixture(offset=0.):
    rows = [record("/tracking/selection", 1.0+offset, action=0, target_uuid="chosen-a", class_name="person",
                   track_id=0, center_u_px=5., center_v_px=5., width_px=10., height_px=10.),
            record("/fmu/out/vehicle_status_v1", 1.1+offset, arming_state=2, nav_state=14)]
    for step in range(36):
        now = round(1.1+step*.2+offset, 9)
        rows += [record("/tracking/state", now, acquired=now-.05, state=1, target_uuid="chosen-a", track_id=1,
                        prediction_age_s=0., class_name="person"),
                 record("/tracking/status", now, lifecycle=2),
                 record("/tracking/command", now, valid=True)]
    payload = {"schema_version": 1, "acquisition_s": 1.05+offset, "output_s": 1.05+offset, "projected": False,
               "target_uuid": "chosen-a", "target_track_id": 1, "target_status": "tracking",
               "ambiguous_track_ids": [], "tracks": [
                   {"track_id": 1, "class_name": "person", "bbox_xyxy": [0,0,10,10],
                    "matched": True, "depth_valid": True},
                   {"track_id": 2, "class_name": "person", "bbox_xyxy": [30,0,40,10],
                    "matched": True, "depth_valid": True}]}
    rows += [record("/tracking/tracks", 1.1+offset, data=json.dumps(payload)),
             record("/tracking/detection_diagnostics", 1.1+offset, data=json.dumps({
                 "stamp_s": 1.05+offset, "completed_s": 1.1+offset, "detections": [{"depth_valid": True}]*2}))]
    return rows


def safe_terminal_ambiguity_fixture():
    rows = fixture()
    for row in rows:
        if row.received_sim_s < 2.5:
            continue
        if row.topic == "/tracking/state":
            row.message.state = 4 if row.received_sim_s < 3.1 else 3
        elif row.topic == "/tracking/status":
            row.message.lifecycle = 4
        elif row.topic == "/tracking/command":
            row.message.valid = False
    payload = json.loads(next(row for row in rows if row.topic == "/tracking/tracks").message.data)
    payload.update(acquisition_s=2.5, output_s=2.5, target_status="ambiguous", ambiguous_track_ids=[1,2])
    for item in payload["tracks"]:
        item["matched"] = False
    rows.append(record("/tracking/tracks", 2.5, data=json.dumps(payload)))
    return rows


def reselection_fixture(offset=0.):
    rows = fixture(offset)
    for row in rows:
        if row.topic == "/tracking/state" and row.received_sim_s >= 2.1+offset:
            row.message.target_uuid = "chosen-b"
            row.message.track_id = 2
    rows.append(record("/tracking/selection", 2.0+offset, action=0, target_uuid="chosen-b", class_name="person",
                       track_id=0, center_u_px=35., center_v_px=5., width_px=10., height_px=10.))
    return sorted(rows, key=lambda row: max(row.time_s, row.received_sim_s))


def run(rows, **kwargs):
    config = evaluation.Stage2Config(require_occlusions=False, **kwargs)
    return evaluation.evaluate(rows, [], config, {"clock_recorded": True, "clock_samples_read": 100,
                                                  "read_errors": {}, "unavailable_types": {}})


class Stage2EvaluationTests(unittest.TestCase):
    def test_operational_transform_preserves_reader_sequence_and_does_not_invent_one(self):
        source = replace(fixture()[2], record_sequence=47)
        transformed = evaluation.operational(source)
        self.assertEqual(transformed.time_s, source.received_sim_s)
        self.assertEqual(transformed.record_sequence, 47)
        self.assertIsNone(evaluation.operational(fixture()[2]).record_sequence)

    def test_reselection_tail_starts_at_exact_confirmation_sequence(self):
        rows = reselection_fixture()
        result = run(rows)
        self.assertEqual(result["result"], "PASS", result["checks"])
        confirmed = result["selections"][-1]
        actual_index = next(index for index, row in enumerate(rows)
                            if row.topic == "/tracking/state" and row.message.target_uuid == "chosen-b")
        self.assertEqual(confirmed["confirmation_record_sequence"], actual_index)
        self.assertEqual(confirmed["confirmation_state_index"], 5)
        self.assertEqual(result["sustained_tracking"]["confirmation_record_sequence"], actual_index)
        self.assertEqual(result["sustained_tracking"]["boundary_evidence"], "RECORD_SEQUENCE")
        self.assertEqual(result["sustained_tracking"]["result"], "PASS")

    def test_same_time_lost_before_confirmation_is_outside_reselection_tail(self):
        rows = reselection_fixture()
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.message.target_uuid == "chosen-b")
        rows.insert(index, record("/tracking/state", 2.1, acquired=2.05, state=3,
                                  target_uuid="chosen-a", track_id=1, prediction_age_s=.8, class_name="person"))
        result = run(rows)
        self.assertTrue(result["selections"][-1]["confirmed"])
        self.assertEqual(result["sustained_tracking"]["result"], "PASS")
        self.assertTrue(result["sustained_tracking"]["checks"]["same_target_active_states_only"])
        self.assertEqual(result["selections"][-1]["confirmation_record_sequence"], index+1)

    def test_same_time_lost_after_confirmation_cannot_be_dropped_from_tail(self):
        rows = reselection_fixture()
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.message.target_uuid == "chosen-b")
        rows.insert(index+1, record("/tracking/state", 2.1, acquired=2.05, state=3,
                                    target_uuid="chosen-b", track_id=2, prediction_age_s=.8, class_name="person"))
        result = run(rows)
        self.assertTrue(result["selections"][-1]["confirmed"])
        self.assertEqual(result["sustained_tracking"]["result"], "FAIL")
        self.assertFalse(result["sustained_tracking"]["checks"]["same_target_active_states_only"])
        self.assertEqual(result["sustained_tracking"]["first_invalid_state_s"], 2.1)

    def test_future_time_state_recorded_before_confirmation_is_outside_reselection_tail(self):
        rows = reselection_fixture()
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.message.target_uuid == "chosen-b")
        rows.insert(index, record("/tracking/state", 4.1, acquired=4.05, state=3,
                                  target_uuid="chosen-a", track_id=1, prediction_age_s=.8, class_name="person"))
        result = run(rows)
        self.assertTrue(result["selections"][-1]["confirmed"])
        self.assertEqual(result["sustained_tracking"]["result"], "PASS")
        self.assertEqual(result["sustained_tracking"]["confirmation_record_sequence"], index+1)

    def test_backdated_state_recorded_after_confirmation_remains_failure_evidence(self):
        rows = reselection_fixture()
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.message.target_uuid == "chosen-b")
        rows.insert(index+1, record("/tracking/state", 2.0, acquired=1.95, state=3,
                                    target_uuid="chosen-b", track_id=2, prediction_age_s=.8, class_name="person"))
        result = run(rows)
        self.assertTrue(result["selections"][-1]["confirmed"])
        self.assertEqual(result["sustained_tracking"]["result"], "FAIL")
        self.assertFalse(result["sustained_tracking"]["checks"]["same_target_active_states_only"])
        self.assertFalse(result["sustained_tracking"]["checks"]["chronological_state_and_control_evidence"])
        self.assertEqual(result["sustained_tracking"]["first_invalid_state_s"], 2.0)

    def test_first_old_active_after_request_cannot_be_skipped_for_later_confirmation(self):
        rows = reselection_fixture()
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.message.target_uuid == "chosen-b")
        rows.insert(index, record("/tracking/state", 2.1, acquired=2.05, state=1,
                                  target_uuid="chosen-a", track_id=1, prediction_age_s=0., class_name="person"))
        result = run(rows)
        rejected = result["selections"][-1]
        self.assertFalse(rejected["confirmed"])
        self.assertIsNone(rejected["confirmation_record_sequence"])
        self.assertIsNone(rejected["confirmation_state_index"])

    def test_backdated_first_active_after_request_cannot_be_skipped(self):
        for returned_uuid in ("chosen-a", "chosen-b"):
            with self.subTest(returned_uuid=returned_uuid):
                rows = reselection_fixture()
                index = next(index for index, row in enumerate(rows)
                             if row.topic == "/tracking/state" and row.message.target_uuid == "chosen-b")
                rows.insert(index, record("/tracking/state", 1.9, acquired=1.85, state=1,
                                          target_uuid=returned_uuid, track_id=2,
                                          prediction_age_s=0., class_name="person"))
                result = run(rows)
                rejected = result["selections"][-1]
                self.assertFalse(rejected["confirmed"])
                self.assertIsNone(rejected["confirmation_record_sequence"])
                self.assertEqual(rejected["first_active_record_sequence"], index)
                self.assertEqual(rejected["first_active_s"], 1.9)
                self.assertLess(rejected["first_active_s"], rejected["request_s"])

    def test_first_active_uses_reader_order_when_a_later_record_has_earlier_time(self):
        rows = reselection_fixture()
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.message.target_uuid == "chosen-b")
        rows.insert(index, record("/tracking/state", 2.2, acquired=2.15, state=1,
                                  target_uuid="chosen-a", track_id=1, prediction_age_s=0., class_name="person"))
        result = run(rows)
        rejected = result["selections"][-1]
        self.assertFalse(rejected["confirmed"])
        self.assertEqual(rejected["first_active_record_sequence"], index)
        self.assertEqual(rejected["first_active_s"], 2.2)

    def test_initial_terminal_window_anchors_first_state_even_when_lost(self):
        rows = fixture()
        # recorded_end=8.1, artificial terminal window begins at 2.9.
        first = next(row for row in rows if row.topic == "/tracking/state" and row.received_sim_s == 2.9)
        first.message.state = 3
        result = run(rows)
        tail = result["sustained_tracking"]
        self.assertAlmostEqual(tail["tail_window_start_s"], 2.9)
        self.assertEqual(tail["confirmation_record_sequence"], rows.index(first))
        self.assertEqual(tail["first_invalid_state_s"], 2.9)
        self.assertFalse(tail["checks"]["same_target_active_states_only"])
        self.assertEqual(tail["result"], "FAIL")

    def test_initial_terminal_window_does_not_search_past_wrong_uuid_at_same_time(self):
        rows = fixture()
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.received_sim_s == 2.9)
        rows.insert(index, record("/tracking/state", 2.9, acquired=2.85, state=1,
                                  target_uuid="other-task", track_id=2, prediction_age_s=0., class_name="person"))
        result = run(rows)
        tail = result["sustained_tracking"]
        self.assertEqual(tail["confirmation_record_sequence"], index)
        self.assertEqual(tail["first_uuid_mismatch_s"], 2.9)
        self.assertEqual(tail["result"], "FAIL")

    def test_terminal_window_anchors_earliest_reader_even_if_later_good_state_sorts_first(self):
        for state, uuid in ((4, "chosen-a"), (3, "chosen-a"), (1, "wrong-task")):
            with self.subTest(state=state, uuid=uuid):
                rows = fixture()
                index = next(index for index, row in enumerate(rows)
                             if row.topic == "/tracking/state" and row.received_sim_s == 2.9)
                # Exact independent-review regression: the bad source's
                # operational time is 2.95, followed in recording order by
                # a good operational-2.9 state and then a 3.0 recovery.
                rows.insert(index, record("/tracking/state", 2.9, acquired=2.95, state=state,
                                          target_uuid=uuid, track_id=1, prediction_age_s=0., class_name="person"))
                recovery_index = next(index for index, row in enumerate(rows)
                                      if row.topic == "/tracking/state" and row.received_sim_s == 3.1)
                rows.insert(recovery_index, record("/tracking/state", 3.0, acquired=2.95, state=1,
                                                   target_uuid="chosen-a", track_id=1,
                                                   prediction_age_s=0., class_name="person"))
                result = run(rows)
                tail = result["sustained_tracking"]
                self.assertEqual(result["result"], "FAIL")
                self.assertEqual(tail["result"], "FAIL")
                self.assertEqual(tail["confirmation_record_sequence"], index)
                self.assertEqual(tail["confirmation_time_s"], 2.95)
                self.assertEqual(tail["first_invalid_state_s"], 2.95)
                self.assertFalse(tail["checks"]["same_target_active_states_only"])
                # The shared receive-clock tick is legitimate even though
                # header/output time regresses. The bad state itself still
                # fails the complete reader-order tail unconditionally.
                self.assertTrue(tail["checks"]["chronological_state_and_control_evidence"])
                self.assertEqual(tail["state_time_regression_count"], 1)
                self.assertEqual(tail["receive_clock_regression_count"], 0)
                self.assertAlmostEqual(tail["tail_window_start_s"], 2.9)

    def test_real_prediction_then_measurement_times_pass_with_same_receive_clock(self):
        rows = reselection_fixture(offset=50.)
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.received_sim_s == 55.3)
        rows[index:index] = [
            record("/tracking/state", 55.224, acquired=55.240, state=2,
                   target_uuid="chosen-b", track_id=2, prediction_age_s=.2, class_name="person"),
            record("/tracking/state", 55.224, acquired=55.100, state=1,
                   target_uuid="chosen-b", track_id=2, prediction_age_s=0., class_name="person"),
        ]
        result = run(rows)
        tail = result["sustained_tracking"]
        self.assertEqual(result["evaluation_revision"], 3)
        self.assertEqual(result["result"], "PASS", result["checks"])
        self.assertEqual(tail["result"], "PASS", tail["checks"])
        self.assertEqual(tail["chronology_time_basis"], "received_sim_s")
        self.assertEqual(tail["state_time_regression_count"], 1)
        self.assertEqual(tail["receive_clock_regression_count"], 0)
        self.assertEqual(tail["invalid_receive_clock_count"], 0)

    def test_prediction_header_ahead_of_receive_clock_can_anchor_terminal_tail(self):
        rows = fixture(offset=52.324)
        index = next(index for index, row in enumerate(rows)
                     if row.topic == "/tracking/state" and row.received_sim_s == 55.224)
        rows[index:index+1] = [
            record("/tracking/state", 55.224, acquired=55.240, state=2,
                   target_uuid="chosen-a", track_id=1, prediction_age_s=.2, class_name="person"),
            record("/tracking/state", 55.224, acquired=55.100, state=1,
                   target_uuid="chosen-a", track_id=1, prediction_age_s=0., class_name="person"),
        ]
        result = run(rows)
        tail = result["sustained_tracking"]
        self.assertEqual(result["result"], "PASS", result["checks"])
        self.assertEqual(tail["confirmation_record_sequence"], index)
        self.assertEqual(tail["confirmation_time_s"], 55.240)
        self.assertAlmostEqual(tail["tail_window_start_s"], 55.224)
        self.assertEqual(tail["state_time_regression_count"], 1)
        self.assertEqual(tail["receive_clock_regression_count"], 0)
        self.assertTrue(tail["checks"]["chronological_state_and_control_evidence"])

    def test_actual_receive_clock_regression_fails_even_with_only_good_states(self):
        for topic in ("/tracking/state", "/tracking/status"):
            with self.subTest(regressed_topic=topic):
                rows = reselection_fixture(offset=50.)
                index = next(index for index, row in enumerate(rows)
                             if row.topic == "/tracking/state" and row.received_sim_s == 55.3)
                regressed = (record(topic, 55.200, acquired=55.100, state=1,
                                    target_uuid="chosen-b", track_id=2, prediction_age_s=0., class_name="person")
                             if topic == "/tracking/state" else record(topic, 55.200, lifecycle=2))
                rows[index:index] = [
                    record("/tracking/state", 55.224, acquired=55.240, state=2,
                           target_uuid="chosen-b", track_id=2, prediction_age_s=.2, class_name="person"),
                    regressed,
                ]
                result = run(rows)
                tail = result["sustained_tracking"]
                self.assertEqual(result["result"], "FAIL")
                self.assertEqual(tail["result"], "FAIL")
                self.assertTrue(tail["checks"]["same_target_active_states_only"])
                self.assertEqual(tail["receive_clock_regression_count"], 1)
                self.assertEqual(tail["receive_clock_order_scope"], "GLOBAL_RECORD_SEQUENCE")
                self.assertFalse(tail["checks"]["chronological_state_and_control_evidence"])

    def test_explicit_reader_sequences_survive_input_reordering_and_are_not_renumbered(self):
        source = reselection_fixture()
        rows = [replace(row, record_sequence=100+2*index) for index, row in enumerate(source)]
        expected = next(row.record_sequence for row in rows
                        if row.topic == "/tracking/state" and row.message.target_uuid == "chosen-b")
        result = run(list(reversed(rows)))
        self.assertEqual(result["selections"][-1]["confirmation_record_sequence"], expected)
        self.assertEqual(result["sustained_tracking"]["confirmation_record_sequence"], expected)
        self.assertEqual(result["sustained_tracking"]["result"], "PASS")

    def test_mixed_missing_sequences_are_rejected_without_guessing_a_boundary(self):
        rows = fixture()
        rows[0] = replace(rows[0], record_sequence=50)
        with self.assertRaises(ValueError):
            run(rows)

    def test_explicit_ambiguity_hover_contract_accepts_safe_latched_stop(self):
        result = run(safe_terminal_ambiguity_fixture(), terminal_expectation="hover")
        self.assertEqual(result["result"], "PASS", result["checks"])
        self.assertNotIn("final_sustained_tracking", result["checks"])
        self.assertIsNone(result["sustained_tracking"])
        self.assertTrue(result["checks"]["final_sustained_hover"])

    def test_normal_tracking_contract_still_rejects_terminal_loss(self):
        result = run(safe_terminal_ambiguity_fixture())
        self.assertFalse(result["checks"]["final_sustained_tracking"])

    def test_hover_contract_requires_actual_selected_ambiguity(self):
        rows = safe_terminal_ambiguity_fixture()
        for row in rows:
            if row.topic == "/tracking/state" and row.message.state == 4:
                row.message.state = 3
        result = run(rows, terminal_expectation="hover")
        self.assertFalse(result["checks"]["terminal_hover_follows_selected_ambiguity"])

    def test_hover_contract_rejects_a_single_valid_motion_command(self):
        rows = safe_terminal_ambiguity_fixture()
        next(row for row in rows if row.topic == "/tracking/command" and row.time_s > 5).message.valid = True
        result = run(rows, terminal_expectation="hover")
        self.assertFalse(result["checks"]["final_sustained_hover"])
        self.assertFalse(result["terminal_hover"]["checks"]["all_motion_commands_invalid"])

    def test_hover_contract_requires_five_seconds_not_a_stop_snapshot(self):
        rows = [row for row in safe_terminal_ambiguity_fixture() if row.received_sim_s <= 5]
        result = run(rows, terminal_expectation="hover")
        self.assertFalse(result["checks"]["final_sustained_hover"])

    def test_hover_contract_does_not_hide_missing_command_evidence(self):
        rows = [row for row in safe_terminal_ambiguity_fixture()
                if not (row.topic == "/tracking/command" and 5 <= row.time_s < 6)]
        result = run(rows, terminal_expectation="hover")
        self.assertFalse(result["terminal_hover"]["checks"]["all_streams_cover_tail_without_gaps"])

    def test_hover_contract_rejects_uuid_clear_or_automatic_change(self):
        rows = safe_terminal_ambiguity_fixture()
        for row in rows:
            if row.topic == "/tracking/state" and row.time_s > 5:
                row.message.target_uuid = ""
        result = run(rows, terminal_expectation="hover")
        self.assertFalse(result["terminal_hover"]["checks"]["same_explicit_task_retained"])

    def test_complete_no_shutter_scope_passes_but_never_claims_physical_identity(self):
        result = run(fixture())
        self.assertEqual(result["result"], "PASS", result["checks"])
        self.assertFalse(result["physical_identity"]["evaluated"])
        self.assertEqual(result["fresh_multi_track_acquisitions"], 1)
        self.assertGreaterEqual(result["sustained_tracking"]["state_span_s"], 5)

    def test_task_uuid_change_needs_recorded_explicit_selection(self):
        rows = fixture()
        for row in rows:
            if row.topic == "/tracking/state" and row.received_sim_s > 4:
                row.message.target_uuid = "silently-switched"
        result = run(rows)
        self.assertEqual(result["result"], "FAIL")
        self.assertFalse(result["checks"]["task_uuid_changes_require_explicit_selection"])

    def test_same_uuid_cannot_hide_long_loss_automatic_recovery(self):
        rows = fixture()
        for row in rows:
            if row.topic == "/tracking/state" and 3 <= row.received_sim_s < 4:
                row.message.state = 3
            if row.topic == "/tracking/status" and 3 <= row.time_s < 4:
                row.message.lifecycle = 4
            if row.topic == "/tracking/command" and 3 <= row.time_s < 4:
                row.message.valid = False
        result = run(rows)
        self.assertFalse(result["checks"]["long_loss_cannot_reactivate_without_explicit_selection"])
        self.assertFalse(result["checks"]["long_loss_cannot_control_before_explicit_selection"])

    def test_actual_ambiguity_requires_hover_and_invalid_controller_motion(self):
        rows = fixture()
        for row in rows:
            if row.topic == "/tracking/state" and 2 <= row.received_sim_s < 2.5:
                row.message.state = 4
        result = run(rows)
        self.assertFalse(result["checks"]["observed_ambiguities_suspend_control"])
        for row in rows:
            if row.topic == "/tracking/status" and 2 <= row.time_s < 2.5:
                row.message.lifecycle = 4
            if row.topic == "/tracking/command" and 2 <= row.time_s < 2.5:
                row.message.valid = False
        result = run(rows)
        self.assertTrue(result["checks"]["observed_ambiguities_suspend_control"])
        self.assertEqual(result["result"], "PASS", result["checks"])

    def test_initial_acquisition_ambiguity_cannot_certify_selected_geometric_ambiguity(self):
        result = run(fixture(), require_ambiguity=True)
        self.assertEqual(result["result"], "FAIL")
        self.assertFalse(result["checks"]["selected_geometric_ambiguity_observed_if_required"])

    def test_missing_full_track_snapshots_cannot_pass(self):
        result = run([row for row in fixture() if row.topic != "/tracking/tracks"])
        self.assertFalse(result["checks"]["all_tracks_snapshots_present_and_valid"])
        self.assertFalse(result["checks"]["multiple_same_class_fresh_tracks_observed"])

    def test_predicted_boxes_cannot_be_counted_as_fresh_same_class_candidates(self):
        rows = fixture()
        for row in rows:
            if row.topic == "/tracking/tracks":
                payload = json.loads(row.message.data)
                payload["projected"] = True
                for item in payload["tracks"]:
                    item["matched"] = False
                row.message.data = json.dumps(payload)
        result = run(rows)
        self.assertFalse(result["checks"]["multiple_same_class_fresh_tracks_observed"])

    def test_stale_active_state_fails_even_when_uuid_is_constant(self):
        rows = fixture()
        next(row for row in rows if row.topic == "/tracking/state").message.prediction_age_s = .8
        result = run(rows)
        self.assertFalse(result["checks"]["active_states_remain_fresh"])
        self.assertEqual(result["result"], "FAIL")

    def test_tail_loss_is_not_hidden_by_an_earlier_initial_confirmation(self):
        rows = fixture()
        for row in rows:
            if row.topic == "/tracking/state" and row.received_sim_s > 7.5:
                row.message.state = 3
        result = run(rows)
        self.assertFalse(result["checks"]["final_sustained_tracking"])

    def test_observed_record_end_cannot_be_truncated_to_hide_failure(self):
        rows = fixture()
        rows.append(record("/tracking/state", 10.0, state=3, target_uuid="chosen-a", track_id=1,
                           prediction_age_s=2., class_name="person"))
        result = run(rows)
        self.assertEqual(result["interval"]["recorded_end_s"], 10.)
        self.assertFalse(result["checks"]["final_sustained_tracking"])

    def test_required_shutter_coverage_cannot_be_inferred_without_events(self):
        result = evaluation.evaluate(fixture(), [], evaluation.Stage2Config(),
                                     {"clock_recorded": True, "clock_samples_read": 100})
        self.assertFalse(result["checks"]["required_short_and_long_occlusions_present"])

    def test_initial_box_must_match_the_confirmed_selected_track(self):
        rows = fixture()
        rows[0].message.center_u_px = 500
        result = run(rows)
        self.assertFalse(result["checks"]["initial_box_matches_selected_track_snapshot"])


if __name__ == "__main__":
    unittest.main()
