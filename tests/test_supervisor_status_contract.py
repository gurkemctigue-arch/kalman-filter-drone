"""The runner archives separate source freshness and wall liveness contracts."""
import unittest

from scripts.run_stage1_trial import supervisor_status_timing


class SupervisorStatusContractTests(unittest.TestCase):
    def test_source_bounds_do_not_depend_on_requested_rtf(self):
        for rtf in (.1, .5, 1.):
            with self.subTest(rtf=rtf):
                self.assertEqual(supervisor_status_timing("source_sim", rtf), {
                    "status_timestamp_mode": "source_sim", "status_source_max_age_s": 1.,
                    "status_source_max_future_s": .05, "status_timeout_s": 10.,
                    "requested_simulation_real_time_factor": rtf})

    def test_legacy_receipt_setting_keeps_existing_wall_contract(self):
        self.assertEqual(supervisor_status_timing("receipt", 1.)["status_timeout_s"], 1.)
        self.assertEqual(supervisor_status_timing("receipt", .5)["status_timeout_s"], 2.)
        self.assertEqual(supervisor_status_timing("receipt", .5)["status_timestamp_mode"], "receipt_wall")

    def test_bad_modes_and_simulation_settings_fail_closed(self):
        for mode, rtf in (("system", .5), ("source_sim", 0.), ("source_sim", 1.1),
                          ("receipt", float("nan"))):
            with self.subTest(mode=mode, rtf=rtf), self.assertRaises(ValueError):
                supervisor_status_timing(mode, rtf)
