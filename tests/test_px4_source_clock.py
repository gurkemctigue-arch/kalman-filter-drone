"""Source/receipt time contract; no ROS or simulator is required."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_px4_adapter"))
from uav_tracking_px4_adapter.source_clock import OdometrySourceClock
from uav_tracking_px4_adapter import adapter_node
from uav_tracking_px4_adapter.frame_guard import VehicleFrameGuard


class SourceClockTests(unittest.TestCase):
    def test_startup_estimator_alignment_is_allowed_but_active_frame_reset_latches(self):
        guard = VehicleFrameGuard()
        self.assertTrue(guard.observe(0)[0])
        self.assertTrue(guard.observe(1)[0])
        guard.lock()
        self.assertTrue(guard.observe(1)[0])
        self.assertEqual(guard.observe(2), (False, "vehicle_frame_reset_restart_required"))
        self.assertFalse(guard.observe(1)[0], "a repeated old counter must not restore an unrelated world frame")

    def test_counter_wrap_during_flight_is_a_reset_and_missing_counter_is_invalid(self):
        guard = VehicleFrameGuard()
        self.assertTrue(guard.observe(255)[0]); guard.lock()
        self.assertFalse(guard.observe(0)[0])
        for value in (None, True, -1, 256):
            self.assertFalse(VehicleFrameGuard().observe(value)[0])

    def test_sim_source_header_preserves_acquisition_time_and_reports_receipt(self):
        clock = OdometrySourceClock("source_sim", use_sim_time=True)
        result = clock.resolve(10_000_000, 10_004_000, 10_020_000_000)
        self.assertTrue(result.accepted)
        self.assertEqual(result.header_ns, 10_000_000_000)
        self.assertAlmostEqual(result.diagnostics(clock.mode)["source_to_receipt_s"], .02)

    def test_wrong_clock_domain_does_not_fit_an_arrival_offset(self):
        clock = OdometrySourceClock("source_sim", use_sim_time=True)
        wrong = clock.resolve(1_793_219_000_000_000, 1_793_219_000_000_000, 10_000_000_000)
        self.assertFalse(wrong.accepted)
        self.assertIsNone(wrong.header_ns)
        self.assertTrue(clock.resolve(10_000_000, 10_000_000, 10_000_000_000).accepted)

    def test_real_vehicle_requires_system_time_contract(self):
        clock = OdometrySourceClock("source_system")
        result = clock.resolve(1_793_219_000_000_000, 1_793_219_000_004_000, 1_793_219_000_010_000_000)
        self.assertTrue(result.accepted)
        for mode, sim in (("source_system", True), ("source_sim", False)):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                OdometrySourceClock(mode, use_sim_time=sim)

    def test_stale_future_and_sample_after_publication_are_rejected(self):
        cases = [(9_000_000, 9_000_000, "stale"),
                 (10_100_000, 10_100_000, "future"),
                 (10_001_000, 10_000_000, "sample_after_publication")]
        for sample, publication, reason in cases:
            with self.subTest(reason=reason):
                r = OdometrySourceClock("source_sim", use_sim_time=True).resolve(sample, publication, 10_000_000_000)
                self.assertFalse(r.accepted)
                self.assertIn(reason, r.reason)

    def test_clock_rollback_is_latched_and_cannot_refresh_tf(self):
        for kind in ("source", "ros"):
            with self.subTest(kind=kind):
                clock = OdometrySourceClock("source_sim", use_sim_time=True)
                self.assertTrue(clock.resolve(10_000_000, 10_000_000, 10_000_000_000).accepted)
                r = clock.resolve(1_000_000, 1_000_000, 10_010_000_000 if kind == "source" else 1_000_000_000)
                self.assertFalse(r.accepted)
                self.assertIn("regression_restart_required", r.reason)
                self.assertFalse(clock.resolve(10_100_000, 10_100_000, 10_100_000_000).accepted)

    def test_duplicates_and_invalid_timestamps_cannot_refresh(self):
        clock = OdometrySourceClock("source_sim", use_sim_time=True)
        self.assertTrue(clock.resolve(10_000_000, 10_000_000, 10_000_000_000).accepted)
        self.assertEqual(clock.resolve(10_000_000, 10_001_000, 10_010_000_000).reason, "duplicate_source_sample")
        for bad in (0, -1, None, True, float("nan"), 1.5, 2**64):
            with self.subTest(bad=bad):
                self.assertFalse(clock.resolve(bad, 10_020_000, 10_020_000_000).accepted)

    def test_clock_not_started_and_legacy_receipt_are_explicit(self):
        clock = OdometrySourceClock("receipt", use_sim_time=True)
        self.assertFalse(clock.resolve(None, None, 0).accepted)
        result = clock.resolve(None, None, 12_000_000_000)
        self.assertTrue(result.accepted)
        self.assertEqual(result.header_ns, 12_000_000_000)
        self.assertEqual(result.reason, "legacy_receipt_stamp")

    def test_adapter_uses_source_stamp_and_rejects_wrong_domain_without_publish(self):
        odometry, timings, warnings = [], [], []
        def make_odometry():
            return NS(header=NS(), pose=NS(pose=NS(position=NS(), orientation=NS())),
                      twist=NS(twist=NS(linear=NS())))
        node = NS(
            _odometry_clock=OdometrySourceClock("source_sim", use_sim_time=True),
            get_clock=lambda: NS(now=lambda: NS(nanoseconds=10_020_000_000, to_msg=lambda: NS(sec=10, nanosec=20_000_000))),
            _vehicle_odom_pub=NS(publish=odometry.append), _odometry_timing_pub=NS(publish=timings.append),
            get_logger=lambda: NS(warning=lambda *a, **kw: warnings.append(a)),
        )
        msg = NS(timestamp_sample=10_000_000, timestamp=10_004_000,
                 pose_frame=1, velocity_frame=1, position=[0., 0., -2.], velocity=[0., 0., 0.], q=[1., 0., 0., 0.])
        with patch.object(adapter_node, "Odometry", make_odometry, create=True), patch.object(adapter_node, "String", NS, create=True):
            adapter_node.Px4AdapterNode._on_vehicle_odometry(node, msg)
            self.assertEqual((odometry[0].header.stamp.sec, odometry[0].header.stamp.nanosec), (10, 0))
            msg.timestamp_sample = msg.timestamp = 1_793_219_000_000_000
            adapter_node.Px4AdapterNode._on_vehicle_odometry(node, msg)
        self.assertEqual(len(odometry), 1)
        self.assertEqual(len(timings), 2)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
