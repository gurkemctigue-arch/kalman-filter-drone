"""A response deadline audits held outputs; empty timestamp tails are no proof."""
from dataclasses import replace
import unittest

from tests import test_stage2_evaluation as fixtures

evaluation = fixtures.evaluation
START, END = 33.864, 34.


def fixture(*, end=END):
    rows = [fixtures.record("/tracking/state", START, acquired=33.7, state=4,
                            target_uuid="selected-car", track_id=3),
            fixtures.record("/tracking/status", 33.9, lifecycle=4),
            fixtures.record("/tracking/command", 33.9, valid=False),
            fixtures.record("/tracking/status", 33.952, lifecycle=4),
            fixtures.record("/tracking/command", 33.952, valid=False),
            fixtures.record("/tracking/status", end, lifecycle=4),
            fixtures.record("/tracking/command", end, valid=False),
            fixtures.record("/tracking/state", end, acquired=end-.2, state=1,
                            target_uuid="selected-car", track_id=3)]
    return evaluation.base.with_record_sequence(rows)


def audit(rows):
    opening = next(row for row in rows if row.topic == "/tracking/state" and row.message.state == 4)
    closing = next(row for row in rows if row.topic == "/tracking/state" and row.message.state == 1)
    return evaluation.ambiguity_control_evidence(opening, closing, rows, closing.received_sim_s,
                                                evaluation.Stage2Config())


class AmbiguityDeadlineTests(unittest.TestCase):
    def test_short_tail_uses_fresh_recorded_safe_outputs_at_the_deadline(self):
        rows = fixture()
        # The next controller tick is exactly the ambiguity-exit timestamp.
        # Its reader order precedes exit, so it also remains safety evidence.
        report = audit(rows)
        self.assertEqual(report["result"], "PASS", report)
        self.assertTrue(report["controller_hover_and_invalid_motion_commands"])
        self.assertEqual(report["streams"]["command"]["boundary_received_s"], 33.952)
        self.assertEqual(report["streams"]["command"]["samples_after_deadline"], 1)

    def test_no_post_deadline_tick_can_still_pass_with_two_real_as_of_outputs(self):
        rows = [row for row in fixture() if not (row.topic != "/tracking/state" and row.received_sim_s == END)]
        report = audit(rows)
        self.assertEqual(report["result"], "PASS", report)
        self.assertEqual(report["streams"]["command"]["samples_after_deadline"], 0)
        self.assertEqual(report["command_samples"], 1)

    def test_safe_response_does_not_hide_an_active_held_output_at_deadline(self):
        for topic, field, value in (("/tracking/command", "valid", True), ("/tracking/status", "lifecycle", 3)):
            rows = fixture()
            row = next(row for row in rows if row.topic == topic and row.received_sim_s == 33.952)
            setattr(row.message, field, value)
            with self.subTest(topic=topic):
                self.assertEqual(audit(rows)["result"], "FAIL")

    def test_valid_command_after_deadline_cannot_escape_with_a_backdated_stamp(self):
        rows = fixture()
        row = next(row for row in rows if row.topic == "/tracking/command" and row.received_sim_s == END)
        row.message.valid = True
        row.message.header.stamp = fixtures.stamp(33.953)
        rows = [replace(item, time_s=33.953) if item is row else item for item in rows]
        report = audit(rows)
        self.assertEqual(report["result"], "FAIL")
        self.assertIsNotNone(report["streams"]["command"]["first_unsafe_record_sequence"])

    def test_missing_boundary_cannot_be_filled_by_a_future_or_backdated_record(self):
        for backdated in (False, True):
            rows = [row for row in fixture() if not (row.topic == "/tracking/command" and row.received_sim_s < END)]
            if backdated:
                command = next(row for row in rows if row.topic == "/tracking/command")
                command.message.header.stamp = fixtures.stamp(33.95)
            with self.subTest(backdated=backdated):
                report = audit(rows)
                self.assertEqual(report["result"], "INCOMPLETE_EVIDENCE", report)
                self.assertFalse(report["controller_hover_and_invalid_motion_commands"])

    def test_output_recorded_before_ambiguity_does_not_establish_the_response(self):
        rows = fixture()
        rows = [row for row in rows if row.topic != "/tracking/command"]
        before = fixtures.record("/tracking/command", START, valid=False)
        before = replace(before, record_sequence=0)
        rows = [before, *[replace(row, record_sequence=row.record_sequence+1) for row in rows]]
        self.assertEqual(audit(rows)["result"], "INCOMPLETE_EVIDENCE")

    def test_missing_clock_and_receive_clock_regression_are_failures(self):
        for received in (None, 33.89):
            rows = fixture()
            rows = [replace(row, received_sim_s=received) if row.record_sequence == 4 else row for row in rows]
            with self.subTest(received=received):
                report = audit(rows)
                self.assertEqual(report["result"], "FAIL", report)
                self.assertFalse(report["chronology_valid"])

    def test_control_source_time_regression_is_not_hidden_by_receive_time_sorting(self):
        rows = fixture()
        row = next(row for row in rows if row.record_sequence == 4)
        row.message.header.stamp = fixtures.stamp(33.89)
        report = audit(rows)
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("command:source_time_regression", report["errors"])

    def test_old_safe_output_cannot_bridge_an_unobserved_long_tail(self):
        rows = fixture(end=34.8)
        rows = [row for row in rows if row.topic == "/tracking/state" or row.received_sim_s != 34.8]
        report = audit(rows)
        self.assertEqual(report["result"], "INCOMPLETE_EVIDENCE")
        self.assertIn("command:evidence_gap", report["errors"])

    def test_same_tick_exit_uses_record_order_to_keep_pre_exit_faults(self):
        before = fixture()
        next(row for row in before if row.record_sequence == 6).message.valid = True
        self.assertEqual(audit(before)["result"], "FAIL")
        after = fixture()
        bad = next(row for row in after if row.record_sequence == 6)
        bad.message.valid = True
        after = [replace(row, record_sequence=8) if row is bad else row for row in after]
        self.assertEqual(audit(after)["result"], "PASS")

    def test_duplicate_sequence_and_future_source_time_cannot_certify_suspension(self):
        rows = fixture()
        duplicate = [replace(row, record_sequence=3) if row.record_sequence == 4 else row for row in rows]
        self.assertEqual(audit(duplicate)["result"], "FAIL")
        rows[4].message.header.stamp = fixtures.stamp(34.1)
        report = audit(rows)
        self.assertEqual(report["result"], "FAIL")
        self.assertFalse(report["chronology_valid"])

    def test_full_evaluator_uses_as_of_evidence_for_the_actual_136ms_window(self):
        rows = fixtures.fixture(offset=32.)
        for row in rows:
            if row.topic == "/tracking/state" and START <= row.received_sim_s < END:
                row.message.state = 4
        rows = [row for row in rows if not (row.topic in {"/tracking/status", "/tracking/command"}
                                           and 33.85 <= row.received_sim_s <= END)]
        rows += [replace(row, record_sequence=None) for row in fixture()]
        rows.sort(key=lambda row: row.received_sim_s)
        # Restore the selected task's fixture identity for the inserted states.
        for row in rows:
            if row.topic == "/tracking/state" and getattr(row.message, "target_uuid", "") == "selected-car":
                row.message.target_uuid = "chosen-a"
        report = fixtures.run(rows)
        self.assertTrue(report["checks"]["observed_ambiguities_suspend_control"], report["ambiguity_windows"])
        self.assertAlmostEqual(report["ambiguity_windows"][0]["duration_s"], .136)


if __name__ == "__main__":
    unittest.main()
