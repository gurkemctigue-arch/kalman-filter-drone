"""Small portable contract checks; no ROS/native imports, processes or bag reads."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import signal
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("recorder_clock_probe", Path(__file__).with_name("probe_recorder_clock.py"))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class RecorderClockContracts(unittest.TestCase):
    def test_only_clock_depth_changes_and_original_profile_is_untouched(self):
        current = {probe.CLOCK: {"history": "keep_last", "depth": 2048, "reliability": "reliable", "durability": "volatile"},
                   "/unchanged": {"history": "keep_last", "depth": 1024, "reliability": "best_effort", "durability": "transient_local"}}
        saved = copy.deepcopy(current)
        candidate = probe.candidate_profiles(current, "candidate1")
        self.assertEqual(candidate[probe.CLOCK]["depth"], 1)
        candidate[probe.CLOCK]["depth"] = 2048
        self.assertEqual(candidate, saved)
        self.assertEqual(current, saved)
        self.assertEqual(probe.candidate_profiles(current, "current2048"), saved)

    def test_describe_is_inert_and_unknown_stress_is_rejected(self):
        with patch.object(probe.sys, "argv", ["probe", "describe"]), patch.object(probe, "run", side_effect=AssertionError("native action")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(probe.main(), 0)
            self.assertFalse(json.loads(output.getvalue())["actual_execution"])
            self.assertEqual(json.loads(output.getvalue())["producer_evidence_depth"], 10)
        with patch.object(probe.sys, "argv", ["probe", "describe", "--producer-evidence-depth", "1024"]), \
                patch.object(probe, "run", side_effect=AssertionError("native action")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(probe.main(), 0)
            description = json.loads(output.getvalue())
            self.assertEqual(description["producer_evidence_depth"], 1024)
            self.assertTrue(description["diagnostic_recorder_override"])
            self.assertFalse(description["actual_execution"])
        with patch.object(probe.sys, "argv", ["probe", "describe", "--producer-evidence-depth", "512"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                probe.main()
            self.assertEqual(error.exception.code, 2)
        with patch.object(probe.sys, "argv", ["probe", "describe", "--stress-recorder-pause-wall-s", "2"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                probe.main()
            self.assertEqual(error.exception.code, 2)

    def test_large_proxy_history_changes_only_diagnostic_topics_and_clock_condition(self):
        original = {probe.CLOCK: {"history": "keep_last", "depth": 2048, "reliability": "reliable", "durability": "volatile"}}
        for topic, depth, reliability, durability in (
                ("/fmu/out/vehicle_odometry", 1024, "best_effort", "transient_local"),
                ("/vehicle/odometry_timing", 1024, "reliable", "volatile"),
                ("/vehicle/odometry", 1024, "reliable", "volatile"),
                ("/tracking/flight_phase", 256, "reliable", "volatile")):
            original[topic] = {"history": "keep_last", "depth": depth,
                               "reliability": reliability, "durability": durability}
        saved = copy.deepcopy(original)
        paired = {}
        for condition, clock_depth in (("current2048", 2048), ("candidate1", 1)):
            default = probe.candidate_profiles(original, condition)
            explicit_default = probe.candidate_profiles(original, condition, 10)
            large = probe.candidate_profiles(original, condition, 1024)
            self.assertEqual(default, explicit_default)
            self.assertEqual(set(default), set(original))
            self.assertEqual(set(large) - set(original), {probe.PRODUCER, probe.CONTROL})
            for topic in original:
                self.assertEqual(large[topic], default[topic])
                if topic != probe.CLOCK:
                    self.assertEqual(large[topic], original[topic])
            for topic in (probe.PRODUCER, probe.CONTROL):
                self.assertEqual(large[topic], {"history": "keep_last", "depth": 1024,
                                               "reliability": "reliable", "durability": "volatile"})
            self.assertEqual(large[probe.CLOCK]["depth"], clock_depth)
            paired[condition] = {topic: value for topic, value in large.items() if topic != probe.CLOCK}
        self.assertEqual(paired["current2048"], paired["candidate1"])
        self.assertEqual(original, saved)
        for invalid in (0, 11, 512, True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                probe.candidate_profiles(original, "candidate1", invalid)

    def test_archived_original_instrument_profiles_and_base_probe_keep_their_bytes(self):
        directory = Path(__file__).resolve().parent
        for path, expected in (
                (directory / "archive_v1/probe_recorder_clock.py", "868689fd2ebee216f0030f6c96eacd5e2b97bf51b454f5d79881cd492648492e"),
                (directory / "archive_v1/recording_qos.yaml", probe.QOS_SHA),
                (directory.parent / "clock_isolation_candidate01/probe_split_rgbd01.py", probe.BASE_PROBE_SHA)):
            with self.subTest(path=path):
                self.assertEqual(probe.sha(path), expected)

    @patch.object(probe.signal, "SIGCONT", 18, create=True)
    def test_cleanup_resumes_only_the_verified_owned_recorder(self):
        identity = {"pid": 123, "process_group": 123, "session": 123, "start_ticks": 45}
        row = {"child": SimpleNamespace(pid=123, poll=lambda: None), "identity": identity}
        base = SimpleNamespace(process=lambda pid: dict(identity))
        state = {}
        with patch.object(probe.os, "killpg", create=True) as kill:
            self.assertFalse(probe.resume_for_cleanup(True, row, base, state))
            kill.assert_called_once_with(123, signal.SIGCONT)
        self.assertTrue(state["resumed_during_cleanup"])
        base.process = lambda pid: {**identity, "start_ticks": 46}
        with patch.object(probe.os, "killpg", create=True) as kill, self.assertRaises(ValueError):
            probe.resume_for_cleanup(True, row, base, {})
        kill.assert_not_called()

    def test_clock_reduction_cannot_hide_missing_nonclock_or_short_coverage(self):
        rows = {topic: {"observer_count": 200, "duplicate_observer_source_stamps": 0,
                       "exact_stamp_payload_multiset_equal": True, "registered_10hz_4ms_cadence_observed": True}
                for topic in probe.IMAGES}
        equality = {probe.PRODUCER: True, probe.CONTROL: True}
        self.assertTrue(probe.nonclock_complete(0, 20_000_000_000, True, rows, equality))
        self.assertFalse(probe.nonclock_complete(0, 19_999_999_999, True, rows, equality))
        self.assertFalse(probe.nonclock_complete(0, 20_000_000_000, False, rows, equality))
        for field, value in (("observer_count", 199), ("exact_stamp_payload_multiset_equal", False),
                             ("duplicate_observer_source_stamps", 1), ("registered_10hz_4ms_cadence_observed", False)):
            changed = copy.deepcopy(rows)
            changed[probe.DEPTH][field] = value
            self.assertFalse(probe.nonclock_complete(0, 20_000_000_000, True, changed, equality))
        self.assertFalse(probe.nonclock_complete(0, 20_000_000_000, True, rows, {**equality, probe.PRODUCER: False}))


if __name__ == "__main__":
    unittest.main()
