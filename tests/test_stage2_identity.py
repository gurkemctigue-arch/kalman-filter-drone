"""Independent target identity must be observable rather than guessed from GT."""

import unittest

from uav_tracking.stage2_identity import physical_identity_match, selected_identity_summary


def truth(identity, box, **kwargs):
    return {"id": identity, "bbox": box, "class_name": "person", "fully_in_frame": True, **kwargs}


def match(box, objects, **kwargs):
    return physical_identity_match(box, objects, class_name="person", fresh=True,
                                   externally_occluded=False, **kwargs)


class Stage2PhysicalIdentityTests(unittest.TestCase):
    def test_unique_isolated_projection_identifies_physical_actor(self):
        result = match([0,0,10,10], [truth("A", [0,0,10,10]), truth("B", [30,0,40,10])])
        self.assertEqual(result["status"], "known")
        self.assertEqual(result["physical_id"], "A")

    def test_equal_overlap_with_two_actors_cannot_be_resolved_by_first_or_nearest(self):
        result = match([0,0,10,10], [truth("A", [0,0,10,10]), truth("B", [0,0,10,10])])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "multiple_feasible_physical_ids")

    def test_even_a_higher_iou_does_not_certify_visibility_during_projection_overlap(self):
        result = match([0,0,10,10], [truth("A", [0,0,10,10]), truth("B", [8,0,18,10])])
        self.assertEqual(result["candidate_ids"], ["A"])
        self.assertEqual(result["reason"], "same_class_gt_projection_overlap")

    def test_partial_gt_or_missing_new_detection_is_unknown(self):
        self.assertEqual(match([0,0,10,10], [truth("A", [0,0,10,10], fully_in_frame=False)])["status"], "unknown")
        result = physical_identity_match([0,0,10,10], [truth("A", [0,0,10,10])],
                                         class_name="person", fresh=False, externally_occluded=False)
        self.assertEqual(result["reason"], "no_fresh_selected_detection")

    def test_unknown_shutter_state_cannot_certify_correct_identity(self):
        result = physical_identity_match([0,0,10,10], [truth("A", [0,0,10,10])],
                                         class_name="person", fresh=True, externally_occluded=None)
        self.assertEqual(result["status"], "unknown")

    def test_wrong_physical_actor_is_detected_even_if_task_uuid_never_changes(self):
        a = {"status": "known", "physical_id": "A"}
        b = {"status": "known", "physical_id": "B"}
        unknown = {"status": "unknown", "physical_id": None, "reason": "crossing_occlusion"}
        result = selected_identity_summary([
            {"target_uuid": "constant-task", "expected_physical_id": "A", "match": item}
            for item in (a, unknown, b, a)])
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["wrong"], 1)
        self.assertEqual(result["unknown"], 1)
        self.assertEqual(result["retention_lower_bound"], .5)
        self.assertEqual(result["known_coverage"], .75)
        self.assertEqual(result["observed_physical_identity_switches_within_task"], 2)

    def test_new_explicit_task_does_not_count_as_identity_switch(self):
        result = selected_identity_summary([
            {"target_uuid": "task-a", "expected_physical_id": "A", "match": {"status": "known", "physical_id": "A"}},
            {"target_uuid": "task-b", "expected_physical_id": "B", "match": {"status": "known", "physical_id": "B"}},
        ])
        self.assertEqual(result["observed_physical_identity_switches_within_task"], 0)
        self.assertEqual(result["correct"], 2)

    def test_expected_actor_cannot_be_redefined_to_hide_a_wrong_follow(self):
        with self.assertRaises(ValueError):
            selected_identity_summary([
                {"target_uuid": "task", "expected_physical_id": identity,
                 "match": {"status": "known", "physical_id": identity}}
                for identity in ("A", "B")])


if __name__ == "__main__":
    unittest.main()
