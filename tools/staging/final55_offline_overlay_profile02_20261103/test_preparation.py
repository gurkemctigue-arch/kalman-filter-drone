"""Small metadata checks only; never native sources, models, bags or staging."""
from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("profile02_preparation_tests", HERE / "check_preparation.py")
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)
INPUTS = (
    "tools/staging/final55_offline_overlay_20261103/stage.py",
    "results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/plan.json",
    "tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical_probe02_20261103.json",
    "tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical02.json",
    "tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical_probe02_20261103.creation.json",
)


class PreparationTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name in INPUTS:
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p.PROJECT / name, destination)
        return root

    def test_named_metadata_check_is_read_only_and_constructs_exactly_four_overrides(self):
        root = self.fixture()
        before = {name: (root / name).read_bytes() for name in INPUTS}
        result = p.check(root)
        self.assertEqual(result["status"], "PREPARATION_METADATA_VALID_NOT_EXECUTABLE")
        self.assertEqual(set(result["profile_overrides"]), {"extension_sha", "extension_digest", "contract_sha", "contract_digest"})
        self.assertFalse(result["owner_closure_bound"])
        self.assertFalse(result["collector_production_pins_bound"])
        self.assertEqual({path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}, set(INPUTS))
        self.assertEqual({name: (root / name).read_bytes() for name in INPUTS}, before)

    def test_execute_refuses_before_any_input_read_or_staging(self):
        output = io.StringIO()
        with patch.object(p, "check", side_effect=AssertionError("Must not read inputs")), redirect_stdout(output):
            self.assertEqual(p.main(["--execute"]), 2)
        self.assertIn("REFUSED_NO_STAGING_OR_NATIVE_TASK", output.getvalue())
        self.assertIn("owner/WSL exit closure", output.getvalue())

    def test_changed_base_plan_contract_and_provenance_pins_reject(self):
        for name in INPUTS:
            with self.subTest(name=name):
                root = self.fixture()
                with (root / name).open("ab") as stream:
                    stream.write(b"\nUNREVIEWED_CHANGE\n")
                with self.assertRaises(p.Refused):
                    p.check(root)

    def test_changed_base_source_is_rejected_before_it_can_execute(self):
        root = self.fixture()
        marker = root / "MUST_NOT_BE_CREATED"
        base = root / INPUTS[0]
        # This would create an output if unpinned source were ever evaluated.
        base.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n", encoding="utf-8")
        with self.assertRaises(p.Refused):
            p.check(root)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
