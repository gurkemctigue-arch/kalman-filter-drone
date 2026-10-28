"""Plot data must keep the full identity denominator and missing outcomes."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import plot_stage23_acceptance as plots


class Stage23PlotTests(unittest.TestCase):
    def test_identity_unknown_and_no_fresh_keep_all_task_opportunities(self):
        report = {"opportunities": 100, "selected_physical_identity_all": {"frames": 10,
                  "counts": {"CORRECT": 3, "WRONG_PHYSICAL_ACTOR": 1, "NOT_OBSERVED": 2,
                             "UNKNOWN_GEOMETRY": 3, "UNKNOWN_TASK_INITIAL_ID": 1}}}
        data = plots.identity_bar_data(report, "test")
        self.assertTrue(data["available"])
        self.assertEqual(data["denominator"], 10)
        self.assertEqual(data["fractions"], {"correct": .3, "wrong": .1, "unknown": .4, "no_fresh": .2})
        self.assertEqual(sum(data["counts"].values()), data["denominator"])

    def test_incomplete_or_inconsistent_identity_is_never_a_zero_error_bar(self):
        cases = [None, {"evaluation_status": "INCOMPLETE_EVIDENCE", "selected_physical_identity_all": None},
                 {"selected_physical_identity_all": {"frames": 10, "counts": {"CORRECT": 1,
                     "WRONG_PHYSICAL_ACTOR": 0, "NOT_OBSERVED": 0, "UNKNOWN_GEOMETRY": 0, "UNKNOWN_TASK_INITIAL_ID": 0}}}]
        for report in cases:
            data = plots.identity_bar_data(report, "test")
            self.assertFalse(data["available"])
            self.assertIsNone(data["fractions"])

    def test_pending_points_remain_null_while_incompatible_measured_points_keep_flag(self):
        report = {"trial_measurements": [], "seed_pairs": [
            {"pair_id": "p", "target_class": "person", "seed": 0, "compatible": False,
             "slot_ids": [], "issues": ["different resource protocol"],
             "differences": {"image_center_rmse": {"midpoint": None, "active": .2}}}]}
        data = plots.pair_plot_data(report)
        midpoint = next(row for row in data if row["mode"] == "midpoint" and row["metric"] == "image_center_rmse")
        active = next(row for row in data if row["mode"] == "active" and row["metric"] == "image_center_rmse")
        self.assertIsNone(midpoint["value"])
        self.assertEqual(active["value"], .2)
        self.assertFalse(active["compatible"])
        self.assertFalse(active["verified_pass"])

    def test_pending_render_exports_real_standalone_png_and_pdf(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            paths = plots.plot_pairs([], directory)
            self.assertEqual(len(paths), 2)
            self.assertTrue((directory / "paired_seed_rmse.png").read_bytes().startswith(b"\x89PNG"))
            self.assertTrue((directory / "paired_seed_rmse.pdf").read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
