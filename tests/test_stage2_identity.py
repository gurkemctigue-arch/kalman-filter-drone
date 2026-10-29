"""Independent target identity must be observable rather than guessed from GT."""

import unittest

from uav_tracking.stage2_identity import physical_identity_match, selected_identity_summary


def truth(identity, box, **kwargs):
    return {"id": identity, "bbox": box, "class_name": "person", "fully_in_frame": True, **kwargs}


def match(box, objects, **kwargs):
    return physical_identity_match(box, objects, class_name="person", fresh=True,
                                   externally_occluded=False, **kwargs)


def front_evidence(**changes):
    return {"schema_version":1,"class_name":"person","source_image_s":1.,
            "depth_coordinate":"camera_optical_z_m","mesh_geometry":"complete_static_render_mesh",
            "expected_actor_ids":["A","B","C"],"independent_camera_geometry_complete":True,
            "all_expected_actors_projected":True,"source_time_geometry_exact":True,
            "static_mesh_projection_supported":True,"closed_scene_occluders_complete":True,**changes}


def front_objects():
    return [truth("A",[0,0,10,10],depth_range_m=[4.,5.]),
            truth("B",[8,0,18,10],depth_range_m=[6.,7.]),
            truth("C",[30,0,40,10],depth_range_m=[2.,3.])]


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

    def test_whole_mesh_front_order_certifies_unique_foreground_only(self):
        result=match([0,0,10,10],front_objects(),front_visibility_evidence=front_evidence())
        self.assertEqual((result["status"],result["physical_id"]),("known","A"))
        certificate=result["foreground_visibility_certificate"]
        self.assertEqual(certificate["status"],"CERTIFIED")
        self.assertEqual(set(certificate["depth_bounds_m"]),{"A","B","C"})
        self.assertEqual([row["other_id"] for row in certificate["pairs"]],["B"])
        self.assertEqual(certificate["pairs"][0]["depth_gap_m"],1.)

    def test_overlapping_depth_behind_or_exact_margin_remains_unknown(self):
        for bounds in ([4.5,7.],[2.,3.],[5.05,7.]):
            objects=front_objects();objects[1]["depth_range_m"]=bounds
            result=match([0,0,10,10],objects,front_visibility_evidence=front_evidence())
            self.assertEqual(result["status"],"unknown")
            self.assertEqual(result["foreground_visibility_certificate"]["reason"],"whole_mesh_front_order_not_strictly_proven")

    def test_new_proof_requires_every_expected_actor_and_same_class(self):
        objects=front_objects()
        for changed in (objects[:2],objects+[truth("D",[50,0,60,10],depth_range_m=[8,9])],
                        [*objects[:2],dict(objects[2],class_name="car")]):
            result=match([0,0,10,10],changed,front_visibility_evidence=front_evidence())
            self.assertEqual(result["status"],"unknown")
            self.assertEqual(result["foreground_visibility_certificate"]["reason"],"missing_or_mismatched_expected_same_class_actors")

    def test_missing_invalid_or_near_plane_depth_is_not_a_front_proof(self):
        for bounds in (None,[],[True,7.],[float("nan"),7.],[6.,float("inf")],[7.,6.],[.1,7.],[-1.,7.]):
            # Even an unrelated actor's missing range prevents claiming the
            # explicitly required complete scene depth evidence.
            objects=front_objects();objects[2]["depth_range_m"]=bounds
            result=match([0,0,10,10],objects,front_visibility_evidence=front_evidence())
            self.assertEqual(result["status"],"unknown")
            self.assertEqual(result["foreground_visibility_certificate"]["reason"],"invalid_or_missing_whole_mesh_depth_range")

    def test_old_schema_and_incomplete_geometry_cannot_gain_front_certificate(self):
        changes=[None,{},front_evidence(schema_version=True),front_evidence(class_name="car")]
        for name in ("independent_camera_geometry_complete","all_expected_actors_projected",
                     "source_time_geometry_exact","static_mesh_projection_supported","closed_scene_occluders_complete"):
            changes.extend((front_evidence(**{name:False}),front_evidence(**{name:None})))
        for evidence in changes:
            self.assertEqual(match([0,0,10,10],front_objects(),front_visibility_evidence=evidence)["status"],"unknown")
        self.assertEqual(match([0,0,10,10],[truth("A",[0,0,10,10])])["status"],"known")

    def test_depth_never_selects_between_multiple_feasible_image_ids(self):
        objects=front_objects();objects[1]["bbox"]=[0,0,10,10]
        result=match([0,0,10,10],objects,front_visibility_evidence=front_evidence())
        self.assertEqual(result["reason"],"multiple_feasible_physical_ids")
        self.assertIsNone(result["foreground_visibility_certificate"])

    def test_front_proof_does_not_bypass_freshness_shutter_or_extent(self):
        for fresh,occluded,full in ((False,False,True),(True,True,True),(True,None,True),(True,False,False)):
            objects=front_objects();objects[0]["fully_in_frame"]=full
            result=physical_identity_match([0,0,10,10],objects,class_name="person",fresh=fresh,
                externally_occluded=occluded,front_visibility_evidence=front_evidence())
            self.assertEqual(result["status"],"unknown")

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
