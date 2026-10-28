"""Source timestamp alignment is part of the physical identity evidence."""
import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1]/"scripts/stage2_identity_contact_sheet.py"
SPEC = importlib.util.spec_from_file_location("stage2_identity_contact_sheet", MODULE_PATH)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class IdentityReviewTests(unittest.TestCase):
    def test_uniform_selection_retains_start_and_end(self):
        frames = [{"acquisition_s":index/5} for index in range(100)]
        chosen = review.review_frames(frames, maximum=7)
        self.assertEqual(len(chosen), 7)
        self.assertEqual(chosen[0]["acquisition_s"], 0)
        self.assertEqual(chosen[-1]["acquisition_s"], 19.8)

    def test_explicit_time_cannot_drift_to_unrelated_image(self):
        frames = [{"acquisition_s":2.}, {"acquisition_s":5.}]
        with self.assertRaises(ValueError):
            review.review_frames(frames, requested_times=[3.], requested_tolerance=.11)

    def test_source_header_tolerance_not_recording_or_video_time(self):
        self.assertEqual(list(review.source_matches(5.001, [4.8, 5., 5.2], .002)), [1])
        self.assertEqual(list(review.source_matches(5.020, [4.8, 5., 5.2], .002)), [])

    def test_duplicate_diagnostics_are_rejected(self):
        with self.assertRaises(ValueError):
            review.review_frames([{"acquisition_s":1.}, {"acquisition_s":1.}])

    def test_unknown_is_not_reported_correct_by_stable_uuid(self):
        frame = {"target_uuid":"constant", "expected_physical_id":"A",
                 "selected_physical_match":{"status":"unknown", "reason":"same_class_gt_projection_overlap"}}
        self.assertTrue(review.frame_status(frame).startswith("UNKNOWN"))
        frame["selected_physical_match"] = {"status":"known", "physical_id":"B"}
        self.assertEqual(review.frame_status(frame), "WRONG_PHYSICAL_ACTOR")


if __name__ == "__main__":
    unittest.main()
