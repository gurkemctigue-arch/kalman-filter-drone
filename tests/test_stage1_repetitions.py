"""Trial-level pairing retains failure evidence and missing seed partners."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("repetitions",Path(__file__).resolve().parents[1]/"scripts/run_stage1_repetitions.py")
repetitions=importlib.util.module_from_spec(spec);spec.loader.exec_module(repetitions)


class RepetitionStatisticsTests(unittest.TestCase):
    def test_first_launch_crash_is_registered_and_resume_never_relaunches(self):
        workspace=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace/"results",prefix="test_first_repeat_crash_") as temporary:
            root=Path(temporary)
            args=["repeat","--prefix","firstcrash","--seeds","0","--classes","person","--modes","velocity","--estimators","adaptive_kf","--skip-online-state-evaluation"]
            report=root/"results/firstcrash_repetition_report.json"
            def interrupted(*unused,**kwargs):
                self.assertTrue(report.is_file())
                self.assertEqual(json.loads(report.read_text())["trials"][0]["result"],"RUNNING_FLIGHT")
                raise KeyboardInterrupt()
            with patch.object(repetitions,"ROOT",root),patch.object(sys,"argv",args),patch.object(repetitions.subprocess,"run",side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):repetitions.main()
            with patch.object(repetitions,"ROOT",root),patch.object(sys,"argv",args+["--resume"]),patch.object(repetitions.subprocess,"run") as runner:
                repetitions.main()
                runner.assert_not_called()
            row=json.loads(report.read_text())["trials"][0]
            self.assertEqual(row["result"],"INTERRUPTED")
            self.assertEqual(row["interrupted_phase"],"RUNNING_FLIGHT")

    def test_failed_flight_is_measurable_but_not_a_both_pass_pair(self):
        def trial(seed,method,result,error):
            return {"target_class":"person","command_mode":"velocity","condition":"clean","motion_profile_kind":"standard",
                    "seed":seed,"estimator_method":method,"result":result,"horizontal_rmse_m":error}
        rows=[trial(0,"adaptive_kf","PASS",1.),trial(0,"raw","PASS",3.),
              trial(1,"adaptive_kf","FAIL",4.),trial(1,"raw","PASS",5.),trial(2,"adaptive_kf","PASS",1.)]
        result=repetitions.aggregate(rows,6)
        self.assertFalse(result["complete"])
        pairs=result["paired_comparisons"]["person_velocity_clean_standard_adaptive_minus_raw"]
        outcome=pairs["outcomes"]["horizontal_rmse_m"]
        self.assertEqual(outcome["all_measurable_recorded_pairs"]["pairs"],2)
        self.assertEqual(outcome["all_measurable_recorded_pairs"]["excluded_pairs"],1)
        self.assertEqual(outcome["all_measurable_recorded_pairs"]["mean_difference"],-1.5)
        self.assertEqual(outcome["conditional_both_flight_pass"]["pairs"],1)
        self.assertEqual(pairs["failure_indicator_difference"]["mean_difference"],.5)
        self.assertEqual(result["groups"]["person_velocity_adaptive_kf"]["failure_rate"]["failures"],1)


if __name__=="__main__":unittest.main()
