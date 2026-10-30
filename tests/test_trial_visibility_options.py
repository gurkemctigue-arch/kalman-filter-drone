"""Reject an invalid geometry mode before allocating any trial or runtime."""
import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from scripts import run_stage1_trial as trial


class TrialVisibilityOptionTests(unittest.TestCase):
    def test_invalid_class_or_reference_is_rejected_before_runtime_preparation(self):
        for cls, reference in (("person", "ground_footprint"), ("car", "visible_surface")):
            with self.subTest(cls=cls, reference=reference):
                args = ["run_stage1_trial.py", "--name", "must_not_be_created", "--class", cls,
                        "--control-reference", reference, "--correlated-two-face-bound"]
                error = io.StringIO()
                with patch.object(sys, "argv", args), contextlib.redirect_stderr(error), \
                        patch.object(trial, "prepare_ros_gz_runtime") as runtime:
                    with self.assertRaises(SystemExit) as raised:
                        trial.main()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("correlated two-face bound requires car ground_footprint", error.getvalue())
                runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
