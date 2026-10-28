"""Native startup evidence gates; no ROS, simulator or recorded bag needed."""
from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ros2_ws/src/uav_tracking_px4_adapter"))
from uav_tracking_px4_adapter.startup_readiness import readiness_issues


def messages():
    local = SimpleNamespace(timestamp_sample=9_900_000, timestamp=9_950_000,
        xy_valid=True, z_valid=True, v_xy_valid=True, v_z_valid=True,
        xy_global=True, z_global=True, dead_reckoning=False,
        x=0., y=0., z=-3., vx=0., vy=0., vz=0., heading=0., heading_good_for_control=False)
    flags = SimpleNamespace(timestamp_sample=9_900_000, timestamp=9_950_000,
        cs_tilt_align=True, cs_yaw_align=True, cs_gnss_pos=True, cs_gnss_vel=True,
        cs_inertial_dead_reckoning=False, cs_wind_dead_reckoning=False, cs_gnss_fault=False,
        cs_mag_fault=False, cs_mag_field_disturbed=False, cs_in_air=False, cs_mag_aligned_in_flight=False)
    return local, flags


class StartupReadinessTests(unittest.TestCase):
    def test_ground_alignment_does_not_require_impossible_inflight_final_alignment(self):
        local, flags = messages()
        self.assertEqual(readiness_issues(local, flags, 10.), [])
        self.assertIn("local_position_heading_good_for_control_not_ready",
                      readiness_issues(local, flags, 10., require_inflight_alignment=True))

    def test_handoff_requires_all_native_inflight_alignment_evidence(self):
        local, flags = messages()
        local.heading_good_for_control = True
        flags.cs_in_air = flags.cs_mag_aligned_in_flight = True
        self.assertEqual(readiness_issues(local, flags, 10., require_inflight_alignment=True), [])
        for item, field in ((local, "heading_good_for_control"), (flags, "cs_in_air"),
                            (flags, "cs_mag_aligned_in_flight")):
            setattr(item, field, False)
            self.assertTrue(readiness_issues(local, flags, 10., require_inflight_alignment=True))
            setattr(item, field, True)

    def test_sample_age_cannot_be_hidden_by_fresh_publication(self):
        local, flags = messages()
        for item, name in ((local, "local_position"), (flags, "estimator_flags")):
            original = item.timestamp_sample
            item.timestamp_sample = 9_499_999 if item is local else 8_499_999
            self.assertIn(name + "_source_stale", readiness_issues(local, flags, 10.))
            item.timestamp_sample = original

    def test_exact_freshness_and_future_boundaries_are_inclusive(self):
        local, flags = messages()
        for item in (local, flags):item.timestamp_sample = item.timestamp = 9_500_000
        self.assertEqual(readiness_issues(local, flags, 10.), [])
        for item in (local, flags):item.timestamp_sample = item.timestamp = 10_050_000
        self.assertEqual(readiness_issues(local, flags, 10.), [])
        local.timestamp_sample = local.timestamp = 10_050_001
        self.assertIn("local_position_source_future", readiness_issues(local, flags, 10.))

    def test_low_rate_estimator_flags_have_their_own_bounded_age(self):
        local, flags = messages()
        flags.timestamp_sample = flags.timestamp = 8_500_000
        self.assertEqual(readiness_issues(local, flags, 10.), [])
        flags.timestamp_sample = 8_499_999
        self.assertIn("estimator_flags_source_stale", readiness_issues(local, flags, 10.))
        # A fresh low-rate flag does not relax high-rate local-state freshness.
        flags.timestamp_sample = flags.timestamp = 9_900_000
        local.timestamp_sample = 9_499_999
        self.assertIn("local_position_source_stale", readiness_issues(local, flags, 10.))

    def test_wall_time_domain_and_inconsistent_sample_publication_are_rejected(self):
        local, flags = messages()
        local.timestamp = local.timestamp_sample = 1_793_000_000_000_000
        self.assertIn("local_position_source_future", readiness_issues(local, flags, 10.))
        local, flags = messages();flags.timestamp_sample = flags.timestamp + 1
        self.assertIn("estimator_flags_sample_after_publication", readiness_issues(local, flags, 10.))

    def test_each_position_or_gnss_validity_flag_blocks_when_false(self):
        for field in ("xy_valid", "z_valid", "v_xy_valid", "v_z_valid", "xy_global", "z_global"):
            local, flags = messages();setattr(local, field, False)
            self.assertIn("local_position_" + field + "_not_ready", readiness_issues(local, flags, 10.))
        for field in ("cs_tilt_align", "cs_yaw_align", "cs_gnss_pos", "cs_gnss_vel"):
            local, flags = messages();setattr(flags, field, False)
            self.assertIn("estimator_flags_" + field + "_not_ready", readiness_issues(local, flags, 10.))

    def test_dead_reckoning_or_declared_magnetic_gnss_fault_blocks(self):
        for field in ("cs_inertial_dead_reckoning", "cs_wind_dead_reckoning", "cs_gnss_fault",
                      "cs_mag_fault", "cs_mag_field_disturbed"):
            local, flags = messages();setattr(flags, field, True)
            self.assertIn("estimator_flags_" + field + "_active", readiness_issues(local, flags, 10.))
        local, flags = messages();local.dead_reckoning = True
        self.assertIn("local_position_dead_reckoning_active", readiness_issues(local, flags, 10.))

    def test_missing_malformed_evidence_and_nonfinite_kinematics_do_not_pass(self):
        self.assertEqual(readiness_issues(None, None, 10.), ["local_position_missing", "estimator_flags_missing"])
        for timestamp in (None, True, 9_900_000., 0, -1, 2**64):
            local, flags = messages();local.timestamp_sample = timestamp
            self.assertIn("local_position_source_timestamp_invalid", readiness_issues(local, flags, 10.))
        local, flags = messages();del flags.cs_mag_fault
        self.assertIn("estimator_flags_cs_mag_fault_unknown", readiness_issues(local, flags, 10.))
        for field in ("x", "y", "z", "vx", "vy", "vz", "heading"):
            local, flags = messages();setattr(local, field, float("nan"))
            self.assertIn("local_position_" + field + "_invalid", readiness_issues(local, flags, 10.))
        for now in (0., -1., float("nan"), float("inf"), True):
            self.assertIn("source_sim_clock_not_started_or_invalid", readiness_issues(*messages(), now))


if __name__ == "__main__":
    unittest.main()
