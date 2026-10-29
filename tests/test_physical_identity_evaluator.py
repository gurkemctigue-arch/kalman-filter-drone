"""Guard against circular initial labels and missing-GT false confidence."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from tests.test_stage2_identity import front_evidence, front_objects
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
    def test_front_certificate_reaches_request_current_frame_and_fixed_time_audit(self):
        evidence=front_evidence()
        truth={"gt":front_objects(),"all_fully_in_frame":True,"overlap":True,"truth_complete":True,
               "front_visibility_evidence":evidence}
        frames,tasks,rows,_=evaluation.build_identity_frames([{"stamp_s":1.01}],
            [snapshot(1.01,[0,0,10,10])],lambda _t:truth,selections=[requested()])
        self.assertEqual(tasks["task"]["physical_id"],"A")
        self.assertEqual(rows[0]["status"],"CORRECT")
        self.assertEqual(rows[0]["match"]["foreground_visibility_certificate"]["status"],"CERTIFIED")
        # Selected foreground visibility is not an all-actors-visible MOT frame.
        self.assertFalse(frames[0]["visible_geometry_eligible"])
        self.assertEqual(len(frames[0]["gt"]),3)
        audit=evaluation.task_time_identity(rows,[requested()],[{"target_uuid":"task","time_s":1.}],
            [0.,1.2],lambda _t:truth)
        self.assertEqual((audit["scheduled_samples"],audit["correct"],audit["unknown"]),(2,1,1))
        self.assertEqual(audit["tasks"]["task"]["expected_physical_id"],"A")
        self.assertEqual(audit["timeline"][0]["foreground_visibility_certificates"][0]["certificate"]["status"],"CERTIFIED")
        self.assertEqual(audit["timeline"][1]["foreground_visibility_certificates"],[])

    def test_projection_none_or_nonexact_source_does_not_create_front_proof(self):
        audit={"supported":True,"closed_scene_occluders_complete":True}
        for gt,exact in ((front_objects()[:2],True),(front_objects(),False)):
            evidence=evaluation.front_projection_evidence("person",["A","B","C"],gt,1.,
                camera_complete=True,source_exact=exact,asset_audit=audit)
            truth={"gt":gt,"all_fully_in_frame":False,"overlap":True,"truth_complete":True,
                   "front_visibility_evidence":evidence}
            _,tasks,rows,_=evaluation.build_identity_frames([{"stamp_s":1.01}],
                [snapshot(1.01,[0,0,10,10])],lambda _t:truth,selections=[requested()])
            self.assertIsNone(tasks["task"]["physical_id"])
            self.assertEqual(rows[0]["status"],"UNKNOWN_TASK_INITIAL_ID")

    def test_exact_source_pose_refuses_interpolation_conflicts_and_nonfinite_data(self):
        def row(t=1.,position=None):
            return {"time_s":t,"position_m":[0,0,0] if position is None else position,"quaternion_xyzw":[0,0,0,1]}
        self.assertIsNotNone(evaluation.exact_source_pose([row()],1.))
        self.assertIsNotNone(evaluation.exact_source_pose([row(),row()],1.))
        self.assertIsNone(evaluation.exact_source_pose([row(.99),row(1.01)],1.))
        self.assertIsNone(evaluation.exact_source_pose([row(),row(position=[.01,0,0])],1.))
        self.assertIsNone(evaluation.exact_source_pose([row(position=[float("nan"),0,0])],1.))

    def test_front_time_audit_requires_vehicle_all_actors_and_physical_camera_links(self):
        row={"time_s":1.,"position_m":[0,0,0],"quaternion_xyzw":[0,0,0,1]}
        targets={name:[row] for name in ("A","B","C")}
        links={name:[row] for name in ("base_link","tracking_camera_mount")}
        complete=evaluation.projection_exact_time_audit(1.,[row],targets,physical_links=links)
        self.assertTrue(complete["complete"])
        self.assertEqual(set(complete["exact_source_samples_s"]),{"vehicle","A","B","C","base_link","tracking_camera_mount"})
        for vehicle,actors,physical in (([],targets,links),([row],dict(targets,C=[]),links),
                                       ([row],targets,dict(links,base_link=[])),
                                       ([row],targets,dict(links,tracking_camera_mount=[]))):
            audit=evaluation.projection_exact_time_audit(1.,vehicle,actors,physical_links=physical)
            self.assertFalse(audit["complete"])
            self.assertEqual(len(audit["missing_or_invalid_exact_entities"]),1)

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


class StaticProjectionAssetTests(unittest.TestCase):
    def fixture(self,root):
        models=root/"ros2_ws/src/uav_tracking_bringup/models"
        model=models/"target_person/model.sdf";model.parent.mkdir(parents=True)
        mesh=models/"fixture/mesh.obj";mesh.parent.mkdir();mesh.write_text("v 0 0 0\nv 0 1 0\nv 0 0 1\n")
        body='<link name="link"><visual name="body"><geometry><mesh><uri>model://fixture/mesh.obj</uri></mesh></geometry></visual></link>'
        model.write_text('<sdf><model name="target_person">'+body+'</model></sdf>')
        trial=root/"trial";world=trial/"configuration/runtime_world.sdf";world.parent.mkdir(parents=True)
        scene=('<light name="sun" type="directional"/>'
               '<include><uri>model://x500_stage1</uri><name>stage1_uav</name><pose>0 0 .25 0 0 0</pose></include>'
               '<model name="ground"><static>true</static><link name="link"><visual name="ground">'
               '<geometry><plane><normal>0 0 1</normal></plane></geometry></visual></link></model>'
               '<model name="vision_shutter"><static>true</static><pose>0 0 -50 0 0 0</pose><link name="link">'
               '<visual name="shutter"><geometry><box><size>.05 3 3</size></box></geometry></visual></link></model>')
        scene+=''.join(f'<model name="stage2_person_{i}">'+body+'</model>' for i in range(3))
        world.write_text('<sdf><world name="fixture">'+scene+'</world></sdf>')
        return trial,model,world,mesh

    def test_complete_declared_rigid_scene_has_audited_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);trial,_,_,_=self.fixture(root)
            audit=evaluation.static_projection_asset_audit(root,trial,"person")
            self.assertTrue(audit["supported"],audit)
            self.assertTrue(audit["closed_scene_occluders_complete"])
            self.assertEqual(len(audit["source_sha256"]),3)

    def test_nonzero_link_unknown_relative_frame_or_scene_occluder_refuses_extra_proof(self):
        changes=(('link name="link">','link name="link"><pose>0 0 .2 0 0 0</pose>'),
                 ('link name="link">','link name="link"><pose relative_to="other">0 0 0 0 0 0</pose>'))
        for before,after in changes:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);trial,model,_,_=self.fixture(root)
                model.write_text(model.read_text().replace(before,after))
                self.assertFalse(evaluation.static_projection_asset_audit(root,trial,"person")["supported"])
        for extra in ('<model name="unexpected_wall"/>','<actor name="animated_person"/>'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);trial,_,world,_=self.fixture(root)
                world.write_text(world.read_text().replace('</world>',extra+'</world>'))
                self.assertFalse(evaluation.static_projection_asset_audit(root,trial,"person")["supported"])

    def test_actor_visual_mismatch_and_animated_mesh_refuse_extra_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);trial,model,world,mesh=self.fixture(root)
            world.write_text(world.read_text().replace('model://fixture/mesh.obj','model://other/mesh.obj',1))
            self.assertFalse(evaluation.static_projection_asset_audit(root,trial,"person")["supported"])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);trial,model,world,mesh=self.fixture(root)
            dae=mesh.with_suffix('.dae');dae.write_text('<COLLADA><library_animations/></COLLADA>')
            for path in (model,world):path.write_text(path.read_text().replace('mesh.obj','mesh.dae'))
            self.assertEqual(evaluation.static_projection_asset_audit(root,trial,"person")["reason"],"animated_or_shader_deformed_mesh")

    def test_nested_undeclared_occluders_refuse_closed_scene_certificate(self):
        wall=('<model name="nested_wall"><link name="wall"><visual name="wall">'
              '<geometry><box><size>30 30 30</size></box></geometry></visual></link></model>')
        structures=(wall,'<include><uri>model://unregistered_wall</uri></include>',
                    '<actor name="nested_animated_person"/>')
        for parent in ("stage2_person_0","ground","vision_shutter"):
            for extra in structures:
                with self.subTest(parent=parent,extra=extra),tempfile.TemporaryDirectory() as temp:
                    root=Path(temp);trial,_,world,_=self.fixture(root)
                    source=world.read_text();start=f'<model name="{parent}">'
                    world.write_text(source.replace(start,start+extra,1))
                    audit=evaluation.static_projection_asset_audit(root,trial,"person")
                    self.assertFalse(audit["supported"],audit)
                    self.assertFalse(audit["closed_scene_occluders_complete"],audit)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);trial,model,_,_=self.fixture(root)
            model.write_text(model.read_text().replace('</model>',wall+'</model>',1))
            self.assertFalse(evaluation.static_projection_asset_audit(root,trial,"person")["supported"])

    def test_ground_light_sensor_host_and_shutter_are_explicitly_limited(self):
        changes=(("<normal>0 0 1</normal>","<normal>0 1 0</normal>","unsupported_ground_occluder"),
                 ('type="directional"','type="point"',"unsupported_scene_lighting"),
                 ('model://x500_stage1','model://unregistered_drone',"unsupported_sensor_host_scene"),
                 ('<size>.05 3 3</size>','<size>.05 5 5</size>',"unsupported_external_shutter_geometry"))
        for old,new,reason in changes:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);trial,_,world,_=self.fixture(root)
                world.write_text(world.read_text().replace(old,new))
                audit=evaluation.static_projection_asset_audit(root,trial,"person")
                self.assertFalse(audit["supported"])
                self.assertEqual(audit["reason"],reason)


if __name__=="__main__":unittest.main()
