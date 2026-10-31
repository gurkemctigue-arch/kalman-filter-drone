"""Pure tiny fixtures only: no bags, model downloads, inference or flight."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import prospective_detection_dataset as d
import evaluate_prospective_detection as e

FIXTURE_ROOT = Path(os.environ.get("UAV_DETECTION_FIXTURE_ROOT", Path.cwd())).resolve()


def pose(t=2., p=(0,0,0), q=(0,0,0,1)):
    return {"time_s":t,"position_m":list(p),"quaternion_xyzw":list(q)}


def rgb(t=2000000000):
    return {"source_acquisition_ns":t,"record_ns":t+5,"topic_sequence":1,"width":640,"height":480,
            "step":1920,"encoding":"rgb8","frame_id":"camera_link"}


def camera(t=2000000000):
    return {"source_acquisition_ns":t,"frame_id":"camera_link","width":640,"height":480,
            "intrinsics":[100.,100.,320.,240.],"distortion":[],"distortion_model":"plumb_bob"}


def frame(t=2000000000):
    return d.sampling_schedule([0,2000000000],[{"phase":"FOLLOW","received_clock_ns":1000000000}],[rgb(t)])[0][0]


def matrix_plan(root, output, mode):
    extension = mode == "EXTENSION_FORMAL"
    trials = []
    for category in d.CLASSES:
        for group in (d.CONDITIONS if extension else d.GROUPS):
            for seed in d.SEEDS:
                group_id = "stage1_position" if extension and group == "speed_changes_position" else "stage1_velocity" if extension else group
                identity = f"{category}_{'extension_' if extension else ''}{group}_seed{seed}"
                stage = 1 if group_id.startswith("stage1_") else 2 if group_id == "stage2_crossing" else 3
                trial = {"id":identity,"name":"fixture_"+identity,"target_class":category,"group":group_id,"stage":stage,"seed":seed,
                         "directory":str(root/"results"/("fixture_"+identity))}
                if extension:
                    trial["extension_condition"] = group
                trials.append(trial)
    plan = {"mode":mode,"frozen_root":str(root),"output":str(output),"source_hashes":{k:"a"*64 for k in d.HELPERS},
            "model_hashes":{"models/fixture.pt":"b"*64},"selected_classes":list(d.CLASSES),"selected_seeds":d.SEEDS,
            "selected_groups":["stage1_velocity","stage1_position"] if extension else list(d.GROUPS),"trials":trials}
    if extension:
        plan["selected_extension_conditions"] = list(d.CONDITIONS)
    return plan


def synthetic_protocol(folder):
    root = folder/"frozen"; root.mkdir()
    (root/"models").mkdir(); (root/"models/static_fixture.obj").write_bytes(b"v 0 0 0\nv 1 0 0\nv 0 1 0\n")
    core = matrix_plan(root,root/"results/core","FORMAL"); core["plan_sha256"] = d.canonical(core)
    core["source_hashes"]["models/static_fixture.obj"] = d.sha(root/"models/static_fixture.obj")
    core["plan_sha256"] = d.canonical({k:v for k,v in core.items() if k != "plan_sha256"})
    extension = matrix_plan(root,root/"results/extension","EXTENSION_FORMAL")
    extension["source_hashes"] = deepcopy(core["source_hashes"])
    core_path = folder/"core.json"; d.write_new(core_path,core)
    extension["core_reference_binding"] = {**d.pin(core_path),"plan_sha256":core["plan_sha256"]}
    extension["plan_sha256"] = d.canonical(extension)
    extension_path = folder/"extension.json"; d.write_new(extension_path,extension)
    slots = [{"plan":name,"slot_id":t["id"],"source_trial":t["directory"],"target_class":t["target_class"],"stage":t["stage"],
              "group":t["group"],"condition":t.get("extension_condition"),"seed":t["seed"],
              "camera_mode":"DYNAMIC_PHYSICAL_NO_FIXED_FALLBACK" if t["stage"] == 3 else "PINNED_FIXED_MOUNT"}
             for name,plan in (("core",core),("extension",extension)) for t in plan["trials"]]
    protocol = {"schema_version":1,"kind":d.KIND,"sampling_rule":d.RULE,"original_planned_slots":280,"frozen_root":str(root),
                "created_utc":"2026-11-01T00:00:00+00:00","all280_unattempted_at_protocol_creation":True,
                "plans":{"core":d.pin(core_path),"extension":d.pin(extension_path)},"helper_source_hashes":{key:core["source_hashes"][key] for key in d.HELPERS},
                "producer_tools":d.tool_pins(),"slots":slots}
    path = folder/"protocol.json"; d.write_new(path,protocol)
    return protocol,d.pin(path)


class PureSampling(unittest.TestCase):
    def test_tail_after_rgb_stops_and_no_45_frame_cap(self):
        frames,audit = d.sampling_schedule([0,103000000000],[{"phase":"FOLLOW","received_clock_ns":0}],[rgb(1000000000)])
        self.assertEqual(len(frames),52); self.assertEqual(frames[-1]["scheduled_ns"],103000000000)
        self.assertEqual(frames[-1]["image_status"],"MISSING"); self.assertEqual(audit["final_recorded_clock_ns"],103000000000)

    def test_nearest_tie_earlier_and_inclusive_tolerance(self):
        frames,_ = d.sampling_schedule([0,1000000000],[{"phase":"FOLLOW","received_clock_ns":0}],[rgb(900000000),rgb(1100000000)])
        self.assertEqual(frames[0]["source_acquisition_ns"],900000000)

    def test_over_tolerance_retains_missing_opportunity(self):
        frames,_ = d.sampling_schedule([0,1000000000],[{"phase":"FOLLOW","received_clock_ns":0}],[rgb(1100000001)])
        self.assertEqual(len(frames),1); self.assertIsNone(frames[0]["source_acquisition_ns"])

    def test_duplicate_source_is_not_chosen(self):
        frames,_ = d.sampling_schedule([0,1000000000],[{"phase":"FOLLOW","received_clock_ns":0}],[rgb(1000000000),rgb(1000000000)])
        self.assertEqual(frames[0]["sampling_reason"],"ambiguous_duplicate_source_timestamp")
        self.assertEqual(frames[0]["duplicate_source_count"],2)

    def test_detection_or_visibility_cannot_select_images(self):
        images = [dict(rgb(1000000000),detections=[],tracking="LOST",visible=False,status="FAIL")]
        frames,_ = d.sampling_schedule([0,1000000000],[{"phase":"FOLLOW","received_clock_ns":0}],images)
        self.assertEqual(frames[0]["image_status"],"SELECTED")

    def test_clock_regression_is_unknown(self):
        frames,audit = d.sampling_schedule([0,2000000000,1000000000],[{"phase":"FOLLOW","received_clock_ns":0}],[])
        self.assertFalse(frames); self.assertEqual(audit["reason"],"recorded_clock_regression")

    def test_missing_follow_or_clock_does_not_start_at_takeoff(self):
        self.assertEqual(d.sampling_schedule([],[],[])[1]["status"],"UNKNOWN")
        self.assertEqual(d.sampling_schedule([0,5000000000],[],[])[1]["reason"],"missing_first_follow_with_recorded_clock")

    def test_first_follow_not_later_follow(self):
        frames,_ = d.sampling_schedule([0,7000000000],[{"phase":"FOLLOW","received_clock_ns":0},{"phase":"FOLLOW","received_clock_ns":4000000000}],[])
        self.assertEqual([f["time_s"] for f in frames],[1.,3.,5.,7.])

    def test_camera_calibration_is_nearest_acquisition_not_last(self):
        infos = [camera(2000000000),dict(camera(2050000000),intrinsics=[300.,300.,320.,240.])]
        selected,reason = d.choose_camera_info(infos,2000000000,rgb())
        self.assertIsNone(reason); self.assertEqual(selected["intrinsics"][0],100.)

    def test_camera_conflicting_same_time_is_unknown(self):
        info,reason = d.choose_camera_info([camera(),dict(camera(),width=300)],2000000000,rgb())
        self.assertIsNone(info); self.assertEqual(reason,"conflicting_source_time_camera_info")

    def test_camera_wrong_sensor_shape_or_missing_time_unknown(self):
        for modified in (dict(camera(),frame_id="other"),dict(camera(),width=200),camera(2300000000)):
            self.assertIsNone(d.choose_camera_info([modified],2000000000,rgb())[0])


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_root = FIXTURE_ROOT/"scripts/evaluate_physical_identity.py"
        if not require_root.is_file():
            raise RuntimeError("Set UAV_DETECTION_FIXTURE_ROOT to the source checkout; no bag/root search is performed")
        hashes = {p:d.sha(FIXTURE_ROOT/p) for p in d.HELPERS}
        cls.helpers = d.load_helpers(FIXTURE_ROOT,hashes)

    def setUp(self):
        self.slot = {"target_class":"car","stage":2,"group":"stage2_crossing"}
        self.points = np.asarray([[x,y,z] for x in (-.1,.1) for y in (-.1,.1) for z in (-.1,.1)])
        self.metadata = {"camera_info":[camera()],"vehicle":[pose()],"targets":{f"stage2_car_{i}":[pose(p=(i-1,0,5))] for i in range(3)},
                         "physical_links":{},"camera_tf":[],"shutters":[],"shutter_evidence_complete":True}
        self.asset = {"supported":True,"closed_scene_occluders_complete":True}
        self.fixed = (np.zeros(3),np.eye(3))

    def project(self,**kwargs):
        return d.build_geometry(kwargs.get("frame",frame()),kwargs.get("slot",self.slot),kwargs.get("metadata",self.metadata),
                                self.helpers,kwargs.get("points",self.points),kwargs.get("asset",self.asset),kwargs.get("fixed",self.fixed))

    def test_all_three_actors_are_projected(self):
        out = self.project()
        self.assertEqual({o["id"] for o in out["gt"]},set(self.metadata["targets"]))
        self.assertTrue(out["visible_label_eligible"]); self.assertTrue(out["truth_complete"])

    def test_missing_actor_keeps_other_proposals_but_not_eligible(self):
        self.metadata["targets"]["stage2_car_0"] = []
        out = self.project(); self.assertEqual(len(out["gt"]),2); self.assertFalse(out["truth_complete"])
        self.assertFalse(out["visible_label_eligible"])

    def test_missing_mesh_is_unknown_not_empty_negative(self):
        out = self.project(points=None)
        self.assertEqual(out["gt"],[]); self.assertFalse(out["truth_complete"]); self.assertFalse(out["visible_label_eligible"])

    def test_known_outside_fov_can_be_true_negative(self):
        for rows in self.metadata["targets"].values():
            rows[0]["position_m"] = [50,0,5]
        out = self.project(); self.assertEqual(out["gt"],[]); self.assertTrue(out["truth_complete"]); self.assertTrue(out["visible_label_eligible"])

    def test_near_plane_not_silently_empty_negative(self):
        self.metadata["targets"]["stage2_car_0"][0]["position_m"] = [0,0,.1]
        out = self.project(); self.assertFalse(out["truth_complete"]); self.assertFalse(out["visible_label_eligible"])

    def test_overlap_retained_amodal_but_excluded_visible(self):
        self.metadata["targets"]["stage2_car_1"] = deepcopy(self.metadata["targets"]["stage2_car_0"])
        out = self.project(); self.assertEqual(len(out["gt"]),3); self.assertTrue(out["overlap"]); self.assertFalse(out["visible_label_eligible"])

    def test_unknown_scene_never_eligible(self):
        out = self.project(asset={"supported":False,"reason":"extra_occluder"})
        self.assertEqual(len(out["gt"]),3); self.assertFalse(out["visible_label_eligible"])

    def test_shutter_guard_uses_actual_rgb_not_scheduled(self):
        actual = 2090000000
        shifted = self.project(frame=frame(actual),metadata={**self.metadata,"camera_info":[camera(actual)],
            "vehicle":[pose(t=2.09)],"targets":{name:[dict(rows[0],time_s=2.09)] for name,rows in self.metadata["targets"].items()},
            "shutters":[{"start_s":3.05,"end_s":3.5}]})
        self.assertTrue(shifted["shutter_guard"]); self.assertFalse(shifted["visible_label_eligible"])

    def test_missing_shutter_evidence_remains_unknown(self):
        out = self.project(metadata={**self.metadata,"shutter_evidence_complete":False})
        self.assertIn("incomplete_recorded_shutter_evidence",out["exclusion_reasons"])

    def dynamic_metadata(self):
        optical = self.helpers["uav_tracking.research_labels"].quaternion_matrix([-.5,.5,-.5,.5])
        metadata = deepcopy(self.metadata)
        metadata["physical_links"] = {"base_link":[pose()],"tracking_camera_mount":[pose()]}
        metadata["camera_tf"] = [pose(q=(-.5,.5,-.5,.5))]
        metadata["targets"] = {name:[pose(p=optical@np.array([i-1,0,5.]))] for i,name in enumerate(self.metadata["targets"])}
        return metadata

    def test_stage3_uses_actual_dynamic_physics_and_optical_tf(self):
        out = self.project(slot={**self.slot,"stage":3},metadata=self.dynamic_metadata(),fixed=(np.ones(3)*999,np.eye(3)))
        self.assertTrue(out["visible_label_eligible"]); self.assertEqual(len(out["gt"]),3)
        self.assertEqual(out["camera_geometry"]["status"],"KNOWN")
        np.testing.assert_allclose(out["camera_world_pose"]["position_m"],[0,0,0])

    def test_stage3_midpoint_missing_dynamic_truth_never_fixed_fallback(self):
        slot = {"target_class":"car","stage":3,"group":"stage3_midpoint"}
        out = self.project(slot=slot,metadata={**self.metadata,"targets":{"target_car":[pose(p=(0,0,5))]}})
        self.assertFalse(out["truth_complete"]); self.assertEqual(out["gt"],[])
        self.assertEqual(out["camera_geometry"]["status"],"UNKNOWN")

    def test_stage3_feedback_disagreement_is_unknown(self):
        metadata = self.dynamic_metadata(); metadata["camera_tf"][0]["position_m"] = [.1,0,0]
        out = self.project(slot={**self.slot,"stage":3},metadata=metadata)
        self.assertFalse(out["truth_complete"])
        self.assertEqual(out["camera_geometry"]["reason"],"feedback_camera_tf_disagrees_with_independent_physics")

    def test_interpolation_is_proposal_only_without_exact_source_proof(self):
        self.metadata["targets"]["stage2_car_0"] = [pose(1.98,(-1,0,5)),pose(2.02,(-1,0,5))]
        out = self.project(); self.assertTrue(out["truth_complete"]); self.assertFalse(out["visible_label_eligible"])
        self.assertIn("no_exact_independent_source_time_geometry",out["exclusion_reasons"])

    def test_conflicting_duplicate_gt_cannot_pass_exact_audit(self):
        self.metadata["targets"]["stage2_car_0"].append(pose(p=(20,0,5)))
        out = self.project(); self.assertFalse(out["visible_label_eligible"])

    def test_singleton_scene_actual_sources_and_extra_occluder(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial = Path(temporary); (trial/"configuration").mkdir()
            world = FIXTURE_ROOT/"ros2_ws/src/uav_tracking_bringup/worlds/stage1_flight_car.sdf"
            (trial/"configuration/runtime_world.sdf").write_bytes(world.read_bytes())
            audit = d.singleton_scene_audit(FIXTURE_ROOT,trial,"car",self.helpers)
            self.assertTrue(audit["supported"],audit)
            text = (trial/"configuration/runtime_world.sdf").read_text(encoding="utf-8")
            text = text.replace("</world>",'<model name="unexpected_occluder"><static>true</static></model></world>')
            (trial/"configuration/runtime_world.sdf").write_text(text,encoding="utf-8")
            self.assertFalse(d.singleton_scene_audit(FIXTURE_ROOT,trial,"car",self.helpers)["supported"])


class BindingAndReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.folder = Path(self.temp.name)
        self.protocol,self.protocol_pin = synthetic_protocol(self.folder)

    def tearDown(self):
        self.temp.cleanup()

    def source(self):
        slot = self.protocol["slots"][0]
        f = dict(frame(),image_status="PRESENT",image_file="tiny.png",image_sha256="",image_bytes=0,gt=[],actor_geometry=[{"id":"target_person","status":"KNOWN_OUT_OF_VIEW"}],
                 truth_complete=True,eligible_geometric_subset=True,visible_label_eligible=True,exclusion_reasons=[],exclusion_reason=None,
                 shutter_guard=False,overlap=False,source_time_audit={"complete":True,"source_image_s":2.,
                 "exact_source_samples_s":{"vehicle":[2.],"target_person":[2.]}},camera_info=camera())
        # Tiny bytes are sufficient for SHA/cache binding fixtures; decode tests
        # use a separately generated valid PNG below, without model inference.
        image = self.folder/"tiny.png"; image.write_bytes(b"pure-fixture-image-no-inference")
        f["image_sha256"] = d.sha(image); f["image_bytes"] = image.stat().st_size
        audit = d.sampling_schedule([0,2000000000],[{"phase":"FOLLOW","received_clock_ns":1000000000}],[rgb()])[1]
        trial = Path(slot["source_trial"]); trial.mkdir(parents=True,exist_ok=True)
        telemetry = trial/"telemetry.jsonl"
        telemetry.write_text(json.dumps({"kind":"shutter","time_s":0.,"active":False,"request_id":1})+"\n"+
                             json.dumps({"kind":"shutter_service_result","time_s":.01,"request_time_s":0.,"active":False,"request_id":1,"success":True})+"\n",encoding="utf-8")
        inputs = {"telemetry.jsonl":{"sha256":d.sha(telemetry),"bytes":telemetry.stat().st_size}}
        plan = d.checked(self.protocol["plans"][slot["plan"]])
        original = {"id":slot["slot_id"],"plan_sha256":plan["plan_sha256"],"status":"FAIL","artifact_hashes":{"telemetry.jsonl":d.sha(telemetry)}}
        original["record_sha256"] = d.canonical(original)
        terminal_path = Path(plan["output"])/"slots"/(slot["slot_id"]+".json"); terminal_path.parent.mkdir(parents=True,exist_ok=True)
        terminal_path.write_text(json.dumps(original),encoding="utf-8")
        (terminal_path.parent/(slot["slot_id"]+".started.json")).write_text(json.dumps({"id":slot["slot_id"],
            "plan_sha256":plan["plan_sha256"],"started_utc":"2026-11-01T00:00:01+00:00"}),encoding="utf-8")
        static_asset = Path(self.protocol["frozen_root"])/"models/static_fixture.obj"
        asset = {"supported":True,"closed_scene_occluders_complete":True,"source_sha256":{str(static_asset.resolve()):d.sha(static_asset)}}
        fixed = {"resolved_model_sdf_sha256":{str(static_asset.resolve()):d.sha(static_asset)}}
        windows,shutter = d.source_shutter_history(trial,inputs)
        binding = d.geometry_source_binding(self.protocol["frozen_root"],trial,plan,inputs,asset,fixed)
        return {"schema_version":1,"kind":d.KIND,"protocol":self.protocol_pin,"slot_id":slot["slot_id"],"source_trial":slot["source_trial"],
                "target_class":"person","stage":1,"camera_mode":slot["camera_mode"],"expected_actor_ids":["target_person"],"sampling_rule":d.RULE,
                "producer_tools":d.tool_pins(),"frames":[f],"sampling_audit":audit,
                "sampling_metadata":{"clock_ns":[0,2000000000],"follow_events":[{"phase":"FOLLOW","received_clock_ns":1000000000}],"image_rows":[rgb()]},
                "scene_asset_audit":asset,"fixed_mount":fixed,
                "geometry_source_binding":binding,"input_artifacts":inputs,"shutter_windows":windows,"shutter_evidence":shutter,
                "terminal":{"status":"FAIL","terminal_record":d.pin(terminal_path)},"extraction_status":"EXTRACTED_PROPOSALS_REVIEW_PENDING","coverage":d.frame_coverage([f])}

    def test_protocol_retains_all_original_280_and_model_identity(self):
        plans = d.validate_protocol(self.protocol)
        self.assertEqual(len(plans["core"]["trials"]),120); self.assertEqual(len(plans["extension"]["trials"]),160)

    def test_plan_missing_cell_and_wrong_model_refused(self):
        core = d.read(self.protocol["plans"]["core"]["path"]); extension = d.read(self.protocol["plans"]["extension"]["path"])
        core["trials"].pop(); core["plan_sha256"] = d.canonical({k:v for k,v in core.items() if k != "plan_sha256"})
        with self.assertRaises(ValueError):d.validate_matrix(core,extension)

    def test_valid_negative_frame_verify_and_failed_trial_preserved(self):
        source = self.source(); path = self.folder/"recording.json"; d.write_new(path,source)
        checked,_,_ = d.verify_recording(path,self.protocol_pin)
        self.assertEqual(checked["terminal"]["status"],"FAIL"); self.assertEqual(len(checked["frames"]),1)

    def test_wrong_or_missing_image_fails_binding(self):
        source = self.source(); path = self.folder/"recording.json"; d.write_new(path,source)
        (self.folder/"tiny.png").write_bytes(b"changed")
        with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)
        (self.folder/"tiny.png").unlink()
        with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)

    def test_terminal_result_pin_and_input_hashes_cannot_be_relabelled(self):
        for mutation in ("status","unbound","artifact"):
            source = self.source()
            if mutation == "status":source["terminal"]["status"] = "PASS"
            elif mutation == "unbound":source["terminal"]["terminal_record"] = None
            else:source["input_artifacts"]["telemetry.jsonl"]["sha256"] = "0"*64
            path = self.folder/("terminal_"+mutation+".json"); d.write_new(path,source)
            with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)

    def test_missing_inview_gt_and_invented_known_status_rejected(self):
        for mutation in ("dropped_gt","invented_status"):
            source = self.source(); source["frames"][0]["actor_geometry"][0]["status"] = "KNOWN_IN_VIEW" if mutation == "dropped_gt" else "KNOWN_BUT_UNPROVEN"
            path = self.folder/(mutation+".json"); d.write_new(path,source)
            with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)

    def test_derived_inframe_and_source_time_proof_cannot_be_forged(self):
        for mutation in ("outside","wrong_source_time"):
            source = self.source(); f = source["frames"][0]
            if mutation == "outside":
                f["actor_geometry"][0]["status"] = "KNOWN_IN_VIEW"
                f["gt"] = [{"id":"target_person","class_name":"person","bbox":[-2,2,20,30],"fully_in_frame":True}]
            else:f["source_time_audit"]["source_image_s"] = 1.9
            path = self.folder/(mutation+".json"); d.write_new(path,source)
            with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)

    def test_shutter_window_and_actual_mesh_mutation_are_rejected(self):
        source = self.source(); source["shutter_windows"] = [{"start_s":1.,"end_s":3.}]
        path = self.folder/"wrong_shutter.json"; d.write_new(path,source)
        with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)
        source = self.source(); path = self.folder/"changed_mesh.json"; d.write_new(path,source)
        (Path(self.protocol["frozen_root"])/"models/static_fixture.obj").write_bytes(b"changed mesh")
        with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)

    def test_resolved_results_junction_or_symlink_cannot_receive_outputs(self):
        root = Path(self.protocol["frozen_root"])
        outside = self.folder/"original_results"; outside.mkdir()
        alias = root/"results"
        if os.name == "nt":
            subprocess.run(["cmd","/c","mklink","/J",str(alias),str(outside)],check=True,capture_output=True)
        else:alias.symlink_to(outside,target_is_directory=True)
        source = self.source()
        self.assertFalse(Path(source["source_trial"]).resolve().is_relative_to(root))
        for path in (Path(source["source_trial"])/"report",outside/"new_pollution"):
            with self.assertRaises(ValueError):d.assert_external_output(self.protocol,path)
            with self.assertRaises(ValueError):e.fresh_directory(path,self.protocol)
        self.assertEqual(d.assert_external_output(self.protocol,self.folder/"external_report"),(self.folder/"external_report").resolve())

    def test_protocol_requires_prospective_timestamp_and_admission(self):
        for field in ("created_utc","all280_unattempted_at_protocol_creation"):
            changed = deepcopy(self.protocol); changed.pop(field)
            with self.assertRaises((ValueError,KeyError)):d.validate_protocol(changed)
        self.source()
        changed = deepcopy(self.protocol); changed["created_utc"] = "2026-11-01T00:00:02+00:00"
        with self.assertRaises(ValueError):d.validate_protocol(changed)

    def test_missing_grid_tail_refused(self):
        source = self.source(); source["sampling_audit"]["final_recorded_clock_ns"] = 6000000000
        path = self.folder/"recording.json"; d.write_new(path,source)
        with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)

    def test_relabelled_nearby_rgb_is_not_the_prospective_nearest_source(self):
        source = self.source(); source["frames"][0]["source_acquisition_ns"] = 2050000000
        source["frames"][0]["source_time_s"] = 2.05; source["frames"][0]["source_rgb"] = rgb(2050000000)
        source["frames"][0]["source_offset_ns"] = 50000000
        path = self.folder/"wrong_nearest_source.json"; d.write_new(path,source)
        with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)

    def test_derived_coverage_denominators_and_reasons_cannot_be_forged(self):
        for field,value in (("scheduled_opportunities",0),("present_images",0),("visible_geometry_eligible",0),("reason_counts",{"hidden_failure":9})):
            source = self.source(); source["coverage"][field] = value
            path = self.folder/("bad_coverage_"+field+".json"); d.write_new(path,source)
            with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)

    def test_duplicate_actor_or_unknown_eligible_refused(self):
        for mutation in ("duplicate","unknown"):
            source = self.source()
            if mutation == "duplicate":
                source["frames"][0]["gt"] = [{"id":"target_person","class_name":"person"}]*2
            else:
                source["frames"][0]["actor_geometry"][0]["status"] = "UNKNOWN_MISSING_POSE"
            path = self.folder/(mutation+".json"); d.write_new(path,source)
            with self.assertRaises(ValueError):d.verify_recording(path,self.protocol_pin)

    def label_decisions(self):
        source = self.source(); recording = self.folder/"recording.json"; d.write_new(recording,source)
        overlay = self.folder/"label.png"; overlay.write_bytes(b"all actor overlay")
        f = source["frames"][0]; key = f'{f["time_s"]:.6f}'
        manifest = {"schema_version":1,"kind":e.LABEL_KIND,"contains_predictions":False,"protocol":source["protocol"],"slot_id":source["slot_id"],
                    "producer_tools":d.tool_pins(),"source_trial":source["source_trial"],"recording":d.pin(recording),
                    "frames":[{"key":key,"source_acquisition_ns":f["source_acquisition_ns"],"image_status":f["image_status"],
                    "all_expected_actor_ids":source["expected_actor_ids"],"source_image":d.pin(self.folder/"tiny.png"),"label_overlay":d.pin(overlay)}],"contact_sheets":[]}
        decisions = {"schema_version":1,"kind":e.REVIEW_KIND,"independent_from_predictions":True,"reviewer_role":"INDEPENDENT_VISIBLE_LABEL_REVIEWER",
                     "reviewer":"independent_fixture_agent","label_manifest_sha256":d.canonical(manifest),"decisions":[{"key":key,"decision":"APPROVE_VISIBLE_LABELS",
                     "reason":"All actors and image area checked against original RGB","source_image_sha256":f["image_sha256"],"label_overlay_sha256":d.sha(overlay),
                     "all_expected_actor_ids":source["expected_actor_ids"]}]}
        provenance = {"recording":{"sha256":d.sha(recording)}}
        return decisions,manifest,source,provenance

    def test_generated_manifest_is_not_approval(self):
        decisions,manifest,source,provenance = self.label_decisions()
        self.assertEqual(e.validate_label_decisions(decisions,manifest,source,provenance),["2.000000"])
        with self.assertRaises(ValueError):e.validate_label_decisions(manifest,manifest,source,provenance)

    def test_prediction_dependent_or_ineligible_review_rejected(self):
        decisions,manifest,source,provenance = self.label_decisions()
        decisions["independent_from_predictions"] = False
        with self.assertRaises(ValueError):e.validate_label_decisions(decisions,manifest,source,provenance)
        decisions["independent_from_predictions"] = True; source["frames"][0]["visible_label_eligible"] = False
        with self.assertRaises(ValueError):e.validate_label_decisions(decisions,manifest,source,provenance)

    def test_foreign_actor_or_modified_overlay_review_rejected(self):
        decisions,manifest,source,provenance = self.label_decisions()
        decisions["decisions"][0]["all_expected_actor_ids"] = ["wrong"]
        with self.assertRaises(ValueError):e.validate_label_decisions(decisions,manifest,source,provenance)
        decisions["decisions"][0]["all_expected_actor_ids"] = source["expected_actor_ids"]
        (self.folder/"label.png").write_bytes(b"changed")
        with self.assertRaises(ValueError):e.validate_label_decisions(decisions,manifest,source,provenance)

    def test_fullframe_negative_and_missing_contact_sheets(self):
        import cv2
        source = self.source(); success,png = cv2.imencode(".png",np.zeros((480,640,3),dtype=np.uint8)); self.assertTrue(success)
        (self.folder/"tiny.png").write_bytes(png.tobytes())
        f = source["frames"][0]; f.update(image_sha256=d.sha(self.folder/"tiny.png"),image_bytes=(self.folder/"tiny.png").stat().st_size)
        missing = dict(f,opportunity_index=1,time_s=4.,scheduled_ns=4000000000,image_status="MISSING",image_file=None,visible_label_eligible=False,eligible_geometric_subset=False)
        source["frames"].append(missing)
        recording = self.folder/"recording.json"; d.write_new(recording,source)
        rows = [(recording,source,Path(source["source_trial"]).name,self.protocol)]
        pins = e.make_labels(rows,self.folder/"labels")
        manifest = d.checked(pins[0]); self.assertFalse(manifest["contains_predictions"])
        self.assertEqual(len(manifest["frames"]),2); self.assertEqual(len(manifest["contact_sheets"]),1)
        overlay = cv2.imdecode(np.frombuffer(Path(manifest["frames"][0]["label_overlay"]["path"]).read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
        self.assertEqual(overlay.shape,(480,640,3))

    def end_to_end_setup(self):
        import yaml
        helpers = d.load_helpers(FIXTURE_ROOT,{p:d.sha(FIXTURE_ROOT/p) for p in d.HELPERS})
        api,metrics = helpers["evaluate_detection_recordings"],helpers["uav_tracking.research_metrics"]
        decisions,manifest,source,_unused = self.label_decisions()
        recording = self.folder/"recording.json"
        trial = Path(source["source_trial"]); (trial/"configuration").mkdir(parents=True)
        model = Path(self.protocol["frozen_root"])/"models/fixture.pt"; model.parent.mkdir(exist_ok=True); model.write_bytes(b"TINY FIXTURE NOT A YOLO MODEL")
        parameters = {"class_name":"person","class_id":0,"model_path":str(model),"inference_image_size":128,"inference_threads":1,"inference_device":"cpu","confidence_threshold":.45}
        d.write_new(trial/"run_config.json",{"target_class":"person","model_path":str(model),"inference_image_size":128,"inference_threads":1})
        (trial/"configuration/runtime_parameters.yaml").write_text(yaml.safe_dump({"uav_tracking_detection":{"ros__parameters":parameters}}),encoding="utf-8")
        d.write_new(trial/"configuration/source_sha256.json",{"models/fixture.pt":d.sha(model)})
        args = SimpleNamespace(settings_source="recorded",person_model_path=None,person_image_size=None,person_threads=None,
                               car_model_path=None,car_image_size=None,car_threads=None,confidence_floor=.001,iou_nms=.7)
        def input_adapter(recording,source,protocol,args):
            configuration,evidence = api.inference_configuration(source,args,root=FIXTURE_ROOT)
            provenance = api.input_provenance(recording,source,configuration,evidence,root=FIXTURE_ROOT)
            return api,metrics,configuration,provenance
        _api,_metrics,_configuration,provenance = input_adapter(recording,source,self.protocol,args)
        cache = self.folder/"cache"/trial.name/"low_confidence_predictions.json"; cache.parent.mkdir(parents=True)
        # A true negative image with a false prediction must remain an FP;
        # empty GT is valid and must not crash/crop gt[0].
        predictions = {"2.000000":[{"id":"0","bbox":[1,1,10,10],"confidence":.9,"class_name":"person"}]}
        d.write_new(cache,{"schema_version":2,"provenance":provenance,"predictions":predictions})
        manifest_path = self.folder/"label_manifest.json"; d.write_new(manifest_path,manifest)
        decisions["label_manifest"] = d.pin(manifest_path)
        decisions_path = self.folder/"decisions.json"; d.write_new(decisions_path,decisions)
        rows = [(recording,source,trial.name,self.protocol)]
        return api,metrics,args,input_adapter,cache,decisions_path,rows

    def test_actual_frozen_cache_approval_metrics_and_new_report_verifier(self):
        api,metrics,args,input_adapter,cache,decisions_path,rows = self.end_to_end_setup()
        with patch.object(e,"cache_inputs",side_effect=input_adapter),patch.object(e,"frozen_api",return_value=(api,metrics)):
            review_path = self.folder/"bound_review.json"
            e.build_review(rows,cache.parent.parent,[decisions_path],review_path,args)
            result = e.evaluate(rows,cache.parent.parent,review_path,self.folder/"report",args)
            self.assertEqual(result["original_planned_slots"],280); self.assertEqual(len(result["missing_original_slot_ids"]),279)
            self.assertEqual(result["reviewed_aggregate"]["classes"]["person"]["fp"],1)
            self.assertEqual(result["recordings"][0]["review_binding_status"],"BOUND")
            receipt = e.verify_report(self.folder/"report/detection_report.json",self.protocol_pin,args)
            self.assertEqual(receipt["status"],"VERIFIED_NEW_PROSPECTIVE_REPORT")
            report_path = self.folder/"report/detection_report.json"; changed = d.read(report_path); changed["original_planned_slots"] = 1
            report_path.write_text(json.dumps(changed),encoding="utf-8")
            with self.assertRaises(ValueError):e.verify_report(report_path,self.protocol_pin,args)

    def test_old_timestamp_approval_cannot_promote_new_recording(self):
        api,metrics,args,input_adapter,cache,_decisions,rows = self.end_to_end_setup()
        legacy = self.folder/"legacy.json"; d.write_new(legacy,{"approved_frames":{rows[0][2]:["2.000000"]}})
        with patch.object(e,"cache_inputs",side_effect=input_adapter),patch.object(e,"frozen_api",return_value=(api,metrics)):
            report = e.evaluate(rows,cache.parent.parent,legacy,self.folder/"pending",args)
            self.assertIsNone(report["reviewed_aggregate"])
            self.assertEqual(report["recordings"][0]["approved_eligible"],0)
            self.assertEqual(report["recordings"][0]["review_binding_status"],"PENDING_INPUT_BINDING")

    def test_unobservable_failed_slot_requires_no_model_config_cache_or_inference(self):
        source = self.source(); f = source["frames"][0]
        f.update(image_file=None,image_status="MISSING",visible_label_eligible=False,eligible_geometric_subset=False,
                 exclusion_reasons=["no_original_rgb"],exclusion_reason="no_original_rgb")
        source["extraction_status"] = "UNOBSERVABLE_MISSING_ORIGINAL_BAG"
        source["coverage"] = d.frame_coverage(source["frames"])
        recording = self.folder/"missing_recording.json"; d.write_new(recording,source)
        rows = e.prepared([recording],self.protocol_pin)
        with patch.object(e,"cache_inputs",side_effect=AssertionError("No model/cache config may be loaded for unobservable slot")):
            inference = e.infer(rows,self.folder/"no_inference",SimpleNamespace())
            self.assertIsNone(inference[0]["prediction_cache"])
            helpers = d.load_helpers(FIXTURE_ROOT,{p:d.sha(FIXTURE_ROOT/p) for p in d.HELPERS})
            with patch.object(e,"frozen_api",return_value=(helpers["evaluate_detection_recordings"],helpers["uav_tracking.research_metrics"])):
                report = e.evaluate(rows,None,None,self.folder/"unobservable_report",SimpleNamespace())
                self.assertIsNone(report["recordings"][0]["all_eligible_proposed_metrics"])
                self.assertIsNone(report["recordings"][0]["prediction_cache"])
                self.assertEqual(report["recording_slots_supplied"],1)
                e.verify_report(self.folder/"unobservable_report/detection_report.json",self.protocol_pin,SimpleNamespace())


if __name__ == "__main__":
    unittest.main(verbosity=2)
