"""Independent adversarial fixtures only; no real bag/log/model or native ROS."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import offline_pipeline_timing as timing
import test_offline_pipeline_timing as fixture


class IndependentSourceBinding(unittest.TestCase):
    def case(self):
        case = fixture.FileBindingTests(methodName="test_source_bound_fixture_analyzes_to_exclusive_new_report")
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def save_events(self, case, events):
        case.events.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        case.context["events"] = timing.pin(case.events)
        case.save_context()

    def test_all_events_claiming_one_physical_log_line_are_unknown(self):
        result = timing.analyze_events([fixture.job(1), fixture.job(1, 2_000_000_000)], {"fixture": True})
        for name in ("completed_job_before_timing_log_wall_s", "completed_job_yolo_predict_wall_s"):
            self.assertEqual(result[name]["total"], 2)
            self.assertEqual(result[name]["known"], 0)
            self.assertEqual(result[name]["unknown"], 2)

    def test_normalized_job_without_bound_original_log_is_refused(self):
        case = self.case()
        self.save_events(case, [fixture.job()])
        self.assertEqual(case.context["job_logs"], [])
        with self.assertRaises(ValueError):
            case.run_analysis()

    def test_consistent_but_fabricated_job_duration_cannot_replace_actual_log(self):
        case = self.case()
        event = fixture.job()
        log = case.base / "original_fixture.log"
        log.write_text("INFERENCE_JOB_TIMING " + json.dumps(event["message"]) + "\n", encoding="utf-8")
        case.context["job_logs"] = [timing.pin(log)]
        self.save_events(case, [event])
        output_pin = case.run_analysis(case.base / "matching_report.json")
        report = timing.read(timing.checked(output_pin))
        self.assertEqual(report["completed_job_before_timing_log_wall_s"]["known"], 1)

        fabricated = copy.deepcopy(event)
        fabricated["message"]["production_work_before_timing_log_wall_s"] = .8
        fabricated["message"]["measured_prefix_wall_s"] = .8
        fabricated["message"]["stages"]["yolo_predict"]["wall_s"] = .6
        self.save_events(case, [fabricated])
        with self.assertRaises(ValueError):
            case.run_analysis(case.base / "fabricated_report.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
