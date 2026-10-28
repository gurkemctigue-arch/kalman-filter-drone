"""Guard against circular initial labels and missing-GT false confidence."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np
from uav_tracking.control.gimbal_geometry import camera_optical_quaternion

scripts=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location("physical_evaluation_under_test",scripts/"evaluate_physical_identity.py")
evaluation=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluation)


def object_(identity,x1,x2):
    return {"id":identity,"bbox":[x1,0,x2,10],"class_name":"person","fully_in_frame":True}


def snapshot(t,box):
    return {"acquisition_s":t,"projected":False,"target_uuid":"task","target_track_id":1,
            "tracks":[{"track_id":1,"bbox_xyxy":box,"class_name":"person","confidence":.9,"matched":True}]}


def requested(t=1.,uuid="task",bbox=None):
    return {"target_uuid":uuid,"time_s":t,"image_stamp_s":t,
            "bbox":bbox or [0,0,10,10],"class_name":"person"}


def identity_row(t,physical="A",uuid="task"):
    return {"time_s":t,"target_uuid":uuid,"expected_physical_id":"A",
            "match":{"status":"known" if physical else "unknown","physical_id":physical}}


class PhysicalIdentityEvaluatorTests(unittest.TestCase):
    def test_dynamic_camera_uses_source_time_physics_and_no_double_body_offset(self):
        def rows(position,yaw):
            return [{"time_s":time,"position_m":position,"quaternion_xyzw":[0,0,np.sin(yaw/2),np.cos(yaw/2)]} for time in (1.,1.04)]
        vehicle=rows([3.,4.,5.],.3);base=rows([0,0,.24],0);camera=rows([.13233,0,.50078],.4)
        tf=[{"time_s":time,"position_m":[.13233,0,.26078],"quaternion_xyzw":camera_optical_quaternion([.4,-.35,0]).tolist()} for time in (1.,1.04)]
        pose,audit=evaluation.dynamic_camera_pose(1.02,vehicle,base,camera,tf)
        self.assertEqual(audit["status"],"KNOWN")
        rotation=evaluation.quaternion_matrix([0,0,np.sin(.3/2),np.cos(.3/2)])
        np.testing.assert_allclose(pose[0],np.array([3,4,5])+rotation@np.array([.13233,0,.50078]),atol=1e-12)
        np.testing.assert_allclose(pose[1],evaluation.quaternion_matrix(camera_optical_quaternion([.7,-.35,0])),atol=1e-12)
        self.assertLess(audit["tf_translation_error_m"],1e-12)
        # Later camera orientation must not be substituted for this image.
        later={"time_s":2.,"position_m":[.13233,0,.50078],"quaternion_xyzw":[0,0,np.sin(.9/2),np.cos(.9/2)]}
        pose2,_=evaluation.dynamic_camera_pose(1.02,vehicle,base,camera+[later],tf)
        np.testing.assert_array_equal(pose[1],pose2[1])

    def test_dynamic_camera_missing_stale_or_inconsistent_tf_stays_unknown(self):
        row={"time_s":1.,"position_m":[0,0,0],"quaternion_xyzw":[0,0,0,1]}
        camera=[dict(row,position_m=[.13233,0,.50078])]
        base=[dict(row,position_m=[0,0,.24])]
        for tf in ([],[dict(row,time_s=.5),dict(row,time_s=1.5)], [dict(row,position_m=[.13233,0,.26078])]):
            pose,audit=evaluation.dynamic_camera_pose(1.,[row],base,camera,tf)
            self.assertIsNone(pose)
            self.assertEqual(audit["status"],"UNKNOWN")
        self.assertIsNone(evaluation.bracketed_local_pose([row],.999))

    def test_initial_wrong_actor_cannot_define_itself_as_expected(self):
        truth={"gt":[object_("A",0,10),object_("B",20,30)],"all_fully_in_frame":True,"overlap":False,"truth_complete":True}
        frames,tasks,rows,_=evaluation.build_identity_frames([{"stamp_s":1}], [snapshot(1,[20,0,30,10])],lambda _t:truth,
            selections=[{"target_uuid":"task","time_s":1.1,"image_stamp_s":1,"bbox":[0,0,10,10],"class_name":"person"}])
        self.assertEqual(tasks["task"]["physical_id"],"A")
        self.assertEqual(rows[0]["status"],"WRONG_PHYSICAL_ACTOR")
        self.assertEqual(rows[0]["matched_physical_id"],"B")

    def test_crossing_and_missing_same_class_gt_remain_unknown(self):
        independent={"gt":[object_("A",0,10),object_("B",20,30)],"all_fully_in_frame":True,"overlap":False,"truth_complete":True}
        crossing={"gt":[object_("A",0,15),object_("B",10,25)],"all_fully_in_frame":True,"overlap":True,"truth_complete":True}
        missing={"gt":[object_("A",0,10)],"all_fully_in_frame":False,"overlap":False,"truth_complete":False}
        def gt(t):return independent if t==1 else crossing if t==2 else missing
        _,_,rows,_=evaluation.build_identity_frames([{"stamp_s":t} for t in (1,2,3)],
            [snapshot(1,[0,0,10,10]),snapshot(2,[0,0,15,10]),snapshot(3,[0,0,10,10])],gt,
            selections=[{"target_uuid":"task","time_s":1.1,"image_stamp_s":1,"bbox":[0,0,10,10],"class_name":"person"}])
        self.assertEqual(rows[0]["status"],"CORRECT")
        self.assertEqual(rows[1]["status"],"UNKNOWN_GEOMETRY")
        self.assertEqual(rows[2]["status"],"UNKNOWN_GEOMETRY")
        self.assertEqual(rows[2]["match"]["reason"],"incomplete_independent_ground_truth")

    def test_missing_request_source_image_timestamp_cannot_certify_identity(self):
        truth={"gt":[object_("A",0,10)],"all_fully_in_frame":True,"overlap":False,"truth_complete":True}
        _,tasks,rows,_=evaluation.build_identity_frames([{"stamp_s":1}],[snapshot(1,[0,0,10,10])],lambda _t:truth,
            selections=[{"target_uuid":"task","time_s":1.1,"bbox":[0,0,10,10],"class_name":"person"}])
        self.assertIsNone(tasks["task"]["physical_id"])
        self.assertEqual(rows[0]["status"],"UNKNOWN_TASK_INITIAL_ID")


class FixedTaskTimeIdentityTests(unittest.TestCase):
    def truth(self,_timestamp):
        return {"gt":[object_("A",0,10),object_("B",20,30)],"truth_complete":True}

    def audit(self,rows,requests=None,confirmations=None,clocks=None,**kwargs):
        return evaluation.task_time_identity(rows,[requested()] if requests is None else requests,
            [{"target_uuid":"task","time_s":1.}] if confirmations is None else confirmations,
            [0.,2.] if clocks is None else clocks,self.truth,**kwargs)

    def test_stopped_diagnostic_stream_leaves_entire_clock_tail_unknown(self):
        rows=[identity_row(1.01)]
        self.assertEqual(evaluation.selected_identity_summary(rows)["known_coverage"],1.)
        audit=self.audit(rows)
        self.assertEqual(audit["interval"],{"start_s":1.,"end_s":2.})
        self.assertEqual((audit["scheduled_samples"],audit["correct"],audit["unknown"]),(10,1,9))
        self.assertAlmostEqual(audit["known_coverage"],.1)
        self.assertEqual(audit["timeline"][-1]["outcome"],"unknown")

    def test_never_confirmed_request_exists_without_any_snapshot(self):
        audit=self.audit([],confirmations=[])
        self.assertEqual(audit["requested_task_count"],1)
        self.assertTrue(audit["tasks"]["task"]["initial_mapping_known"])
        self.assertEqual(audit["tasks"]["task"]["expected_physical_id"],"A")
        self.assertFalse(audit["tasks"]["task"]["confirmed"])
        self.assertEqual(audit["unconfirmed_requested_tasks"],["task"])
        self.assertEqual((audit["correct"],audit["wrong"],audit["unknown"]),(0,0,10))
        self.assertEqual(audit["known_coverage"],0.)

    def test_pending_confirmation_and_mixed_unknown_evidence_cannot_be_correct(self):
        rows=[identity_row(1.01),identity_row(1.11),identity_row(1.12,None),identity_row(1.21)]
        audit=self.audit(rows,confirmations=[{"target_uuid":"task","time_s":1.05}])
        self.assertEqual([row["outcome"] for row in audit["timeline"][:3]],["unknown","unknown","correct"])
        self.assertEqual(audit["unknown_reason_counts"]["request_not_yet_confirmed"],1)

    def test_brief_wrong_actor_is_not_hidden_by_other_frames_in_same_cell(self):
        rows=[identity_row(1.01,"B"),identity_row(1.02),identity_row(1.03,None)]
        # The new audit independently establishes A from REQUEST, even if an
        # old caller incorrectly labelled B as the expected actor.
        rows[0]["expected_physical_id"]="B"
        audit=self.audit(rows)
        self.assertEqual(audit["timeline"][0]["outcome"],"wrong")
        self.assertEqual((audit["wrong"],audit["correct"],audit["unknown"]),(1,0,9))

    def test_reselection_registers_new_request_and_independent_expected_actor(self):
        requests=[requested(),requested(1.5,"task2",[20,0,30,10])]
        confirms=[{"target_uuid":"task","time_s":1.},{"target_uuid":"task2","time_s":1.6}]
        audit=self.audit([identity_row(1.01),identity_row(1.61,"B","task2")],requests,confirms)
        self.assertEqual(audit["requested_task_count"],2)
        self.assertEqual(audit["tasks"]["task2"]["expected_physical_id"],"B")
        self.assertEqual(audit["tasks"]["task"]["scheduled_samples"],5)
        self.assertEqual(audit["tasks"]["task2"]["scheduled_samples"],5)
        self.assertEqual((audit["correct"],audit["wrong"],audit["unknown"]),(2,0,8))
        audit=self.audit([identity_row(1.01)],requests,confirms[:1])
        self.assertEqual(audit["unconfirmed_requested_tasks"],["task2"])
        self.assertEqual(audit["tasks"]["task2"]["unknown"],5)

    def test_partial_final_cell_is_counted_and_end_is_excluded(self):
        audit=self.audit([identity_row(1.01),identity_row(1.21),identity_row(1.25,"B")],clocks=[0.,1.25])
        self.assertEqual((audit["scheduled_samples"],audit["correct"],audit["wrong"],audit["unknown"]),(3,2,0,1))
        self.assertEqual(audit["timeline"][-1]["end_s"],1.25)
        self.assertEqual(self.audit([],clocks=[0.,1.3])["scheduled_samples"],3)

    def test_clear_and_mid_cell_task_boundary_do_not_inherit_correct_identity(self):
        for action in ("CLEAR","RESET"):
            audit=self.audit([identity_row(1.51)],lifecycle=[{"time_s":1.5,"action":action}])
            self.assertEqual(audit["unknown_reason_counts"]["task_cleared_or_reset"],5)
        requests=[requested(),requested(1.55,"task2",[20,0,30,10])]
        audit=self.audit([identity_row(1.51)],requests,
            [{"target_uuid":"task","time_s":1.},{"target_uuid":"task2","time_s":1.55}])
        self.assertEqual(audit["timeline"][5]["reason"],"task_boundary_within_time_cell")

    def test_unknown_initial_mapping_stays_unknown_despite_fresh_correct_boxes(self):
        request=requested();request.pop("image_stamp_s")
        audit=self.audit([identity_row(1.01)],requests=[request])
        self.assertEqual(audit["correct"],0)
        self.assertEqual(audit["unknown"],10)
        self.assertFalse(audit["tasks"]["task"]["initial_mapping_known"])

    def test_missing_clock_and_epoch_reset_are_incomplete_without_fake_zero_error(self):
        for clocks in ([],[0.,2.,1.5],[0.,1.]):
            audit=self.audit([identity_row(1.01)],clocks=clocks)
            self.assertEqual(audit["evaluation_status"],"INCOMPLETE_EVIDENCE")
            self.assertIsNone(audit["known_coverage"])
            self.assertIsNone(audit["retention_lower_bound"])
            self.assertEqual(audit["scheduled_samples"],0)


if __name__=="__main__":unittest.main()
