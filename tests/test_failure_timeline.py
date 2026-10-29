"""Time-domain and delayed-evidence boundary checks for scalar fault exports."""
import argparse
import importlib.util
from pathlib import Path
import unittest

_SPEC = importlib.util.spec_from_file_location("failure_timeline", Path(__file__).resolve().parents[1] / "scripts/export_failure_timeline.py")
timeline = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(timeline)


class FaultWindowTests(unittest.TestCase):
    def test_delayed_acquisition_and_early_delivery_are_both_retained_without_restamping(self):
        window = timeline.parse_window("reselection:50.1:52.5")
        late = {"source_s": 51., "received_clock_s": 54.}
        earlier = {"source_s": 49.9, "received_clock_s": 50.2}
        self.assertEqual(timeline.window_names(late, [window]), ["reselection"])
        self.assertEqual(timeline.window_names(earlier, [window]), ["reselection"])
        self.assertEqual(late["received_clock_s"], 54.)
        self.assertEqual(earlier["source_s"], 49.9)

    def test_missing_time_and_wall_scale_storage_do_not_invent_delivery(self):
        window = timeline.parse_window("abort:30:34")
        self.assertEqual(timeline.window_names({"storage_timestamp_ns": 1_793_275_992_000_000_000}, [window]), [])
        self.assertEqual(timeline.source_time({"timestamp": 31_384_000}, "/fmu/out/vehicle_status_v1"),
                         (31.384, "px4_us_unverified_domain"))

    def test_overlapping_windows_retain_both_labels(self):
        windows = [timeline.parse_window("a:30:32"), timeline.parse_window("b:31:34")]
        self.assertEqual(timeline.window_names({"source_s": 31.5}, windows), ["a", "b"])

    def test_source_header_keeps_nanosecond_precision_instead_of_payload_clock(self):
        value, basis = timeline.source_time({"header": {"stamp": {"sec": 50, "nanosec": 236000000}},
                                            "completed_s": 51.}, "/tracking/state")
        self.assertAlmostEqual(value, 50.236)
        self.assertEqual(basis, "header")

    def test_invalid_windows_and_nonfinite_times_are_rejected(self):
        for value in ("x:3:2", "x:nan:4", "x:0:inf", ":0:1", "x:-1:2"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                timeline.parse_window(value)
        self.assertIsNone(timeline.finite(True))
        self.assertEqual(timeline.json_safe(float("nan")), {"nonfinite": "nan"})


if __name__ == "__main__":
    unittest.main()
