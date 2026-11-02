"""Independent metadata corruption fixtures; no guard, runtime or source scan."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import formal_supplementary_preflight as gate
import test_formal_supplementary_preflight as author


class IndependentProspectiveSemantics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="independent_preflight_synthetic_")
        self.addCleanup(self.temp.cleanup)
        self.case = author.Fixture(self.temp.name)
        self.case.validate()

    def history(self):
        with self.assertRaises(author.ExecObserved):
            self.case.run()
        self.case.original_start()
        self.case.validate()

    def test_all280_started_terminal_slots_still_delegate_once_with_original_denominator(self):
        self.history()
        for plan in self.case.plans.values():
            for trial in plan["trials"]:
                Path(trial["directory"]).mkdir(parents=True, exist_ok=True)
                slots = Path(plan["output"]) / "slots"
                slots.mkdir(exist_ok=True)
                self.case.save(slots / (trial["id"] + ".started.json"), {
                    "id": trial["id"], "plan_sha256": plan["plan_sha256"],
                    "started_utc": "2020-01-05T00:00:01+00:00"})
                self.case.save(slots / (trial["id"] + ".json"), {"status": "FAIL"})
        context = self.case.validate()
        self.assertEqual(len(context["starts"]), 280)
        self.assertEqual(context["protocol"]["original_planned_slots"], 280)
        before = len(self.case.calls)
        with self.assertRaises(author.ExecObserved):
            self.case.run()
        self.assertEqual(len(self.case.calls), before + 1)
        self.assertEqual(self.case.calls[-1][1], self.case.contract["adapter"]["argv_prefix"]
                         + ["run-one", "--manifest", str(self.case.admission_path)])

    def test_original_marker_id_or_internal_plan_binding_cannot_be_forged(self):
        self.history()
        trial = self.case.plans["core"]["trials"][0]
        marker = Path(self.case.plans["core"]["output"]) / "slots" / (trial["id"] + ".started.json")
        original = gate.read(gate.pin(marker))
        for field, value in (("id", "another_physical_trial"), ("plan_sha256", "a" * 64)):
            with self.subTest(field=field):
                changed = deepcopy(original)
                changed[field] = value
                self.case.save(marker, changed)
                with self.assertRaises(ValueError):
                    self.case.validate()
                self.case.save(marker, original)

    def test_internally_resealed_audit_cannot_follow_original_initial_admission(self):
        self.history()
        event = gate.decode(self.case.audit_path.read_text(encoding="utf-8"))
        event["created_utc"] = "2020-01-05T00:00:00.500000+00:00"
        event["event_sha256"] = gate.canonical({key: value for key, value in event.items()
                                               if key != "event_sha256"})
        self.case.audit_path.write_text(__import__("json").dumps(event) + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.case.validate()

    def test_original_initial_full280_count_is_required_after_a_valid_first_event(self):
        self.history()
        path = self.case.state / "initial_admission.json"
        initial = gate.read(gate.pin(path))
        initial["initial_pending_slots"] = 279
        initial["receipt_sha256"] = gate.canonical({key: value for key, value in initial.items()
                                                  if key != "receipt_sha256"})
        self.case.save(path, initial)
        with self.assertRaises(ValueError):
            self.case.validate()

    def test_unknown_internal_plan_cell_is_not_rescued_by_rehashing_every_binding(self):
        self.case.plans["extension"]["trials"][-1]["extension_condition"] = "invented_condition"
        self.case.refresh_plans()
        with self.assertRaises(ValueError):
            self.case.validate()

    def test_late_binding_without_audit_cannot_claim_an_earlier_successful_preflight(self):
        self.case.original_start()
        self.assertFalse(self.case.audit_path.exists())
        self.case.contract["created_utc"] = "2020-01-05T00:00:02+00:00"
        self.case.save_contract()
        with self.assertRaises(ValueError):
            self.case.validate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
