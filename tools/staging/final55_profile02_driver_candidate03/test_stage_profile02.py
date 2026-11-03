"""Small admission-boundary checks; no native or source-tree staging."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("profile02_stage_candidate_tests", Path(__file__).with_name("stage_profile02.py"))
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)


class AdmissionTests(unittest.TestCase):
    def fixture(self):
        core = {"path": "/fixture/core/plan.json", "sha256": "a" * 64}
        extension = {"path": "/fixture/extension/plan.json", "sha256": "b" * 64}
        rows = [{"id": str(index), "original_status": ("PASS", "FAIL", "INCOMPLETE_EVIDENCE")[index % 3]} for index in range(16)]
        chain = {"status": "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION", "closed_ids": [row["id"] for row in rows],
                 "closed": rows, "pending_ids": [], "plan": extension}
        cells = [{"matrix": matrix, "target_class": target, "condition": condition}
                 for matrix, groups in (("core", s.CORE_GROUPS), ("extension", s.EXTENSION_GROUPS))
                 for target in ("person", "car") for condition in groups]
        storage = {"cells": cells}
        budget = {"schema_version": 1, "kind": "RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION", "admission_performed": False,
                  "storage": storage, "storage_sha256": hashlib.sha256(json.dumps(storage, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                  "provenance": {"development_plans": {"core": core, "extension": extension}, "assumptions": {"sha256": s.ASSUMPTIONS_SHA},
                                 "tool": {"sha256": s.BUDGET_TOOL_SHA}, "guard_tool": {"sha256": s.BUDGET_GUARD_SHA}},
                  "capacity_preview": {"scheduled_slots": 280, "fits_declared_logical_budget": True,
                                       "volumes": {"drive_D": {"fits_declared_physical_budget": True}}}}
        return chain, budget, {"core_binding": core, "extension_binding": extension}

    def test_complete_chain_keeps_failed_and_incomplete_original_results(self):
        chain, budget, kwargs = self.fixture()
        before = deepcopy((chain, budget))
        result = s.validate_admission(chain, budget, **kwargs)
        self.assertEqual(result["preserved_engineering_statuses"], chain["closed"])
        self.assertEqual((chain, budget), before)
        self.assertEqual(result["scheduled_slots"], 280)

    def test_partial_chain_cannot_enable_staging(self):
        chain, budget, kwargs = self.fixture()
        chain.update(status="BOUND_PRESERVED_PREFIX_CHAIN", pending_ids=["last"])
        with self.assertRaisesRegex(ValueError, "full original"):
            s.validate_admission(chain, budget, **kwargs)

    def test_duplicate_or_mismatched_closed_rows_reject(self):
        for field in ("closed_ids", "closed"):
            chain, budget, kwargs = self.fixture()
            chain[field][-1] = chain[field][0]
            with self.assertRaises(ValueError):
                s.validate_admission(chain, budget, **kwargs)

    def test_another_extension_plan_rejects(self):
        chain, budget, kwargs = self.fixture()
        chain["plan"] = {**chain["plan"], "sha256": "f" * 64}
        with self.assertRaisesRegex(ValueError, "another extension"):
            s.validate_admission(chain, budget, **kwargs)

    def test_negative_or_unknown_capacity_in_any_volume_rejects(self):
        for bad in (False, None, 1):
            chain, budget, kwargs = self.fixture()
            budget["capacity_preview"]["volumes"]["other"] = {"fits_declared_physical_budget": bad}
            with self.assertRaisesRegex(ValueError, "capacity"):
                s.validate_admission(chain, budget, **kwargs)
        chain, budget, kwargs = self.fixture()
        budget["capacity_preview"]["fits_declared_logical_budget"] = False
        with self.assertRaises(ValueError):
            s.validate_admission(chain, budget, **kwargs)

    def test_changed_budget_storage_or_original_assumptions_reject(self):
        for target in ("storage", "assumptions"):
            chain, budget, kwargs = self.fixture()
            if target == "storage":
                budget["storage"]["cells"].pop()
            else:
                budget["provenance"]["assumptions"]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                s.validate_admission(chain, budget, **kwargs)

    def test_twenty_eight_distinct_wrong_conditions_reject_even_if_resealed(self):
        chain, budget, kwargs = self.fixture()
        budget["storage"]["cells"][0]["condition"] = "not_a_registered_condition"
        budget["storage_sha256"] = hashlib.sha256(json.dumps(budget["storage"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "Exact core6"):
            s.validate_admission(chain, budget, **kwargs)

    def test_final_evidence_change_keeps_base_pass_and_separate_wrapper_failure(self):
        with tempfile.TemporaryDirectory(prefix="profile02_wrapper_fixture_") as temporary:
            root = Path(temporary)
            receipt = root / "receipt"
            def binding(path):
                return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            def write(path, value):
                with path.open("x", encoding="utf8") as stream:
                    json.dump(value, stream)
            def execute(prepared):
                receipt.mkdir()
                value = {"status": "PASS_STAGING_ONLY_NOT_COLD_OR_ADMISSION"}
                write(receipt / "outcome.json", value)
                return value
            def changed():
                raise ValueError("External original changed after copy")
            base = SimpleNamespace(binding=binding, write_new=write, execute=execute)
            admission = root / "stage.admission.json"
            with self.assertRaisesRegex(ValueError, "External original changed"):
                s.execute_with_outcome(base, {"paths": {"receipt": receipt}},
                                       SimpleNamespace(unchanged=changed), admission, {"checks": {}})
            original = json.loads((receipt / "outcome.json").read_bytes())
            final = json.loads((root / "stage.admission.driver_outcome.json").read_bytes())
            self.assertEqual(original["status"], "PASS_STAGING_ONLY_NOT_COLD_OR_ADMISSION")
            self.assertEqual(final["status"], "FAIL_PROFILE02_STAGING_RETAINED")
            self.assertEqual(final["base_outcome"], binding(receipt / "outcome.json"))

    def test_default_and_execute_refuse_before_reading_or_native_guard(self):
        with patch.object(s, "fixed_module", side_effect=AssertionError("Must not read")), redirect_stdout(io.StringIO()):
            self.assertEqual(s.main([]), 0)
            self.assertEqual(s.main(["--execute"]), 2)
        self.assertFalse(s.PRODUCTION_ENABLED)
        self.assertEqual(s.REGISTERED_INPUTS, {})


if __name__ == "__main__":
    unittest.main()
