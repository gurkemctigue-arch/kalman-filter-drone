"""Named actual small metadata only; no bags, models, images or native task."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("historical_slot03", Path(__file__).with_name("validate_owner_closure.py"))
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
ROOT = Path(__file__).resolve().parents[3]
REVIEW_PATH = ROOT / "results/diagnostics/humble54_probe02_dropout_review03/root_review.json"
REVIEW_SHA = "eac4f501a771b6acc7ecf3c88a0765165506350815c20bea94ffd3b9ef26887d"
PROFILE_PATH = ROOT / "tools/experiment_orchestration/humble54_pending_collector05_registered/registered_profile05.json"
PROFILE_SHA = "5ac96b104ac1e7ad24500657f38b329c968f9440e61f23e79d7bc27fc1df0bd0"


class ActualHistoricalUnknownTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.review_binding = {"path": str(REVIEW_PATH), "sha256": REVIEW_SHA}
        self.review = v.Inputs(v.local_small_read).json(self.review_binding)
        self.profile = v.Inputs(v.local_small_read).json({"path": str(PROFILE_PATH), "sha256": PROFILE_SHA})
        self.plan = v.Inputs(v.local_small_read).json(self.profile["plan"])
        self.row = deepcopy(self.review["frontier_record"])
        self.trial = next(row for row in self.plan["trials"] if row["id"] == self.row["slot_id"])

    def inputs_and_captures(self, read=v.local_small_read):
        inputs = v.Inputs(read)
        inputs.bind_plan_results_alias(self.plan)
        captures = v.snapshot_capture_contract(self.profile, inputs, self.plan)
        return inputs, captures

    def exception(self, review=None, binding=None):
        review = self.review if review is None else review
        return {"root_review": self.review_binding if binding is None else binding,
                "exception": deepcopy(review["historical_unknown"])}

    def test_actual_original_is_incomplete_and_requires_named_review(self):
        inputs, captures = self.inputs_and_captures()
        with self.assertRaisesRegex(v.Refused, "interrupted/pending/unknown/unsafe"):
            v.validate_slot(inputs, self.plan, self.trial, self.row, captures, self.now)
        inputs, captures = self.inputs_and_captures()
        before = v.local_small_read(self.row["original_terminal"]["path"])
        result = v.validate_slot(inputs, self.plan, self.trial, self.row, captures, self.now, reviewed_unknown=self.exception())
        self.assertEqual(result["original_status"], "INCOMPLETE_EVIDENCE")
        self.assertEqual(result["unobserved_checks"], ["surface:short:detector_interruption_observed=HISTORICAL_UNKNOWN_RETAINED"])
        self.assertEqual(v.local_small_read(self.row["original_terminal"]["path"]), before)
        self.assertEqual(result["reviewed_unknown"]["root_review"]["sha256"], REVIEW_SHA)

    def test_resigned_review_cannot_widen_terminal_field_value_status_or_time(self):
        for defect in ("terminal", "field", "value", "status", "unobserved", "plan", "early", "error"):
            with self.subTest(defect=defect):
                review = deepcopy(self.review)
                unknown = review["historical_unknown"]
                if defect == "terminal":
                    unknown["terminal"]["sha256"] = "0" * 64
                elif defect == "field":
                    unknown["field"] = "surface:long:prediction_observed"
                elif defect == "value":
                    unknown["value"] = True
                elif defect == "status":
                    unknown["original_status"] = "PASS"
                elif defect == "unobserved":
                    unknown["unobserved_checks"].append("surface:long:prediction_observed=HISTORICAL_UNKNOWN_RETAINED")
                elif defect == "plan":
                    review["plan"]["plan_sha256"] = "0" * 64
                elif defect == "early":
                    review["reviewed_utc"] = self.row["original_started_utc"]
                else:
                    review["original_error"] = "KeyboardInterrupt: "
                raw = json.dumps(review, sort_keys=True).encode()
                binding = {"path": str(REVIEW_PATH), "sha256": v.sha(raw)}

                def read(reference):
                    return raw if v.path_key(reference) == v.path_key(str(REVIEW_PATH)) else v.local_small_read(reference)

                inputs, captures = self.inputs_and_captures(read)
                with self.assertRaises(v.Refused):
                    v.validate_slot(inputs, self.plan, self.trial, self.row, captures, self.now, reviewed_unknown=self.exception(review, binding))

    def test_wrong_or_changed_root_review_raw_binding_is_refused(self):
        reviewed = self.exception()
        reviewed["root_review"]["sha256"] = "0" * 64
        inputs, captures = self.inputs_and_captures()
        with self.assertRaisesRegex(v.Refused, "Raw evidence/source SHA differs"):
            v.validate_slot(inputs, self.plan, self.trial, self.row, captures, self.now, reviewed_unknown=reviewed)

    def test_row_unknown_list_cannot_be_empty_or_include_another_null(self):
        for unknown in ([], ["another"], self.row["unobserved_checks"] + ["another"]):
            with self.subTest(unknown=unknown):
                row = deepcopy(self.row)
                row["unobserved_checks"] = unknown
                inputs, captures = self.inputs_and_captures()
                with self.assertRaisesRegex(v.Refused, "unobserved checks differ"):
                    v.validate_slot(inputs, self.plan, self.trial, row, captures, self.now, reviewed_unknown=self.exception())

    def test_additional_or_missing_behavior_is_refused_even_after_review(self):
        base = v.Inputs(v.local_small_read)
        base.bind_plan_results_alias(self.plan)
        terminal = base.json(self.row["original_terminal"])
        spec = next(item for item in self.trial["evaluations"] if item["kind"] == "surface_flight")
        surface_entry = next(item for item in terminal["evaluations"] if item["kind"] == "surface_flight")
        report = base.json({"path": spec["report"], "sha256": surface_entry["report_sha256"]})
        relative = Path(spec["report"]).name
        for defect in ("another_null", "missing_target", "unsafe_long"):
            with self.subTest(defect=defect):
                changed, term = deepcopy(report), deepcopy(terminal)
                if defect == "another_null":
                    next(row for row in changed["occlusions"] if row["kind"] == "long")["checks"]["prediction_observed"] = None
                elif defect == "missing_target":
                    next(row for row in changed["occlusions"] if row["kind"] == "short")["checks"].pop("detector_interruption_observed")
                else:
                    next(row for row in changed["occlusions"] if row["kind"] == "long")["checks"]["hover_observed_for_long_occlusion"] = False
                raw = json.dumps(changed, sort_keys=True).encode()
                next(item for item in term["evaluations"] if item["kind"] == "surface_flight")["report_sha256"] = v.sha(raw)
                term["artifact_hashes"][relative] = v.sha(raw)
                canonical_report = self.plan["results_root"] + spec["report"].split(self.plan["frozen_root"] + "/results", 1)[1] if spec["report"].startswith(self.plan["frozen_root"] + "/results/") else spec["report"]

                def read(reference):
                    return raw if v.path_key(reference) == v.path_key(canonical_report) else v.local_small_read(reference)

                inputs = v.Inputs(read)
                inputs.bind_plan_results_alias(self.plan)
                with self.assertRaises(v.Refused):
                    v.slot_evaluation_integrity(inputs, self.trial, term, self.now, reviewed_unknown=True)


if __name__ == "__main__":
    unittest.main()
