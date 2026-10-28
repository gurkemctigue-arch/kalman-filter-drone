"""Frozen denominators, failure retention and the postflight result join."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location("full_plan",ROOT/"scripts/run_full_plan_research.py")
full=importlib.util.module_from_spec(spec);spec.loader.exec_module(full)


class FullPlanResearchTests(unittest.TestCase):
    def test_visual_reports_require_new_fields_and_keep_flights_as_statistics_units(self):
        def report(opportunities,observed,error,latency):
            def metric(count,value):return {"count":count,"mean":value,"rmse":value,"p95":value}
            return {"schema_version":1,"evaluation_status":"RECORDED_WITH_CENSORED_FAILURES","windows":[],
                    "visual_control_metrics":{"detection_opportunities":opportunities,"center_observed_samples":observed,
                        "observed_center_coverage":observed/opportunities,"source_images_with_first_tracking_command":observed,
                        "detected_center_error_px":metric(observed,error*100),"detected_center_normalized_error":metric(observed,error),
                        "image_to_first_tracking_command_sim_s":metric(observed,latency)}}
        first=report(100,100,.1,.2);second=report(10,1,.9,.6)
        self.assertTrue(full.valid_follow_dynamics_report(first))
        old={"schema_version":1,"evaluation_status":"RECORDED_WITH_CENSORED_FAILURES","windows":[]}
        self.assertFalse(full.valid_follow_dynamics_report(old))
        partial=report(100,100,.1,.2);del partial["visual_control_metrics"]["image_to_first_tracking_command_sim_s"]
        self.assertFalse(full.valid_follow_dynamics_report(partial))
        contract={"stage":1,"target_class":"person","command_mode":"velocity","estimator_method":"adaptive_kf"}
        rows=[{**contract,"result":"PASS",**full.dynamics_trial_fields(first)},
              {**contract,"result":"FAIL",**full.dynamics_trial_fields(second)},
              {**contract,"result":"FAIL",**full.dynamics_trial_fields(old)}]
        self.assertEqual(rows[0]["follow_visual_center_observed_samples"],100)
        data=full.dynamics_statistics(rows)["s1_person_velocity_adaptive_kf"]["visual_control_statistics"]
        self.assertEqual(data["reports_available"],2)
        self.assertEqual(data["reports_missing"],1)
        self.assertEqual(data["detection_opportunities_total"],110)
        self.assertAlmostEqual(data["pooled_observed_center_coverage"],101/110)
        stats=data["whole_flight_statistics"]
        self.assertAlmostEqual(stats["follow_visual_detected_center_normalized_error_rmse"]["mean"],.5)
        self.assertAlmostEqual(stats["follow_visual_image_to_first_tracking_command_sim_s_mean"]["mean"],.4)
        self.assertEqual(stats["follow_visual_image_to_first_tracking_command_sim_s_mean"]["valid_count"],2)

    def test_dynamics_censoring_is_counted_and_never_imputed_as_zero(self):
        report={"evaluation_status":"RECORDED_WITH_CENSORED_FAILURES","windows":[
            {"kind":"initial_follow_before_first_shutter","distance":{"settling_time_s":None,"settling_right_censored":True,"opposite_side_overshoot_m":.3,"truth_coverage":.9},
             "height":{"settling_time_s":2.5,"settling_right_censored":False,"opposite_side_overshoot_m":.1,"truth_coverage":1.}},
            {"kind":"explicit_selection","first_measured_confirmation_after_request_s":1.2,"confirmation_censored":False},
            {"kind":"explicit_selection","first_measured_confirmation_after_request_s":None,"confirmation_censored":True}]}
        row={"stage":1,"target_class":"person","command_mode":"velocity","estimator_method":"adaptive_kf","result":"FAIL",**full.dynamics_trial_fields(report)}
        self.assertIsNone(row["initial_distance_settling_time_s"])
        self.assertEqual(row["initial_distance_unsettled_indicator"],1.)
        data=full.dynamics_statistics([row])["s1_person_velocity_adaptive_kf"]
        self.assertEqual(data["initial_distance_settling"]["right_censored"],1)
        self.assertEqual(data["initial_distance_settling"]["observed_settling_time_s"]["valid_count"],0)
        self.assertEqual(data["initial_height_settling"]["observed_settling_time_s"]["mean"],2.5)
        self.assertEqual(data["explicit_selection_confirmation_censored"],1)
        self.assertEqual(data["flight_mean_observed_confirmation_latency_s"]["mean"],1.2)

    def test_second_writer_cannot_reconcile_live_slots_and_lock_releases(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_full_plan_lock_") as temporary:
            root=Path(temporary)
            with full.process_lock(root):
                with self.assertRaisesRegex(RuntimeError,"Another full-plan writer"):
                    with full.process_lock(root):self.fail("Second writer acquired active root lock")
            with full.process_lock(root):
                self.assertTrue((root/"results/.full_plan_research.lock").is_file())

    def test_exact_existing_166_slots_and_resource_matched_commands(self):
        with patch.object(full,"source_hashes",return_value={"example.py":"frozen"}):
            plan=full.make_plan(ROOT,"teststudy",ROOT/"results/teststudy")
        self.assertEqual(len(plan["trials"]),166)
        self.assertEqual(sum(t["stage"]==1 for t in plan["trials"]),100)
        self.assertEqual(sum(t["stage"]==2 for t in plan["trials"]),26)
        self.assertEqual(sum(t["stage"]==3 for t in plan["trials"]),40)
        self.assertEqual(len({t["name"] for t in plan["trials"]}),166)
        command=full.matrix_command(plan["matrices"][0],plan,ROOT,3)
        self.assertIn("--skip-online-state-evaluation",command)
        self.assertEqual(command[command.index("--car-image-size")+1],"640")
        self.assertEqual(command[command.index("--real-time-factor")+1],str(plan["resources"]["real_time_factor"]))
        original=full.plan_digest(plan);plan["resources"]["real_time_factor"]=.8
        self.assertNotEqual(full.plan_digest(plan),original)

    def test_final_running_child_slot_is_interrupted_without_launch_or_retry(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_full_plan_resume_") as temporary:
            root=Path(temporary);output=root/"matrix";report=output/"manifest.json"
            trial={"id":"last","name":"last_trial","stage":3,"target_class":"car"}
            full.write_json(report,{"plan_sha256":"child_hash","slots":[{"trial":trial,"status":"RUNNING_EVALUATION","commands":[{"returncode":None}]}]})
            plan={"trials":[trial],"matrices":[{"kind":"stage23","report":str(report),"output":str(output),"trial_names":[trial["name"]]}]}
            with patch.object(full,"run_logged") as runner:
                self.assertEqual(full.execute_flights(plan,root/"master",root,0),0)
                runner.assert_not_called()
            child=full.load(report)
            self.assertEqual(child["slots"][0]["status"],"INTERRUPTED")
            self.assertEqual(child["slots"][0]["commands"],[{"returncode":None}])
            self.assertEqual(full.load(output/"summary.json")["status_counts"],{"INTERRUPTED":1})

    def test_stored_plan_and_offline_trial_bindings_reject_tampering(self):
        with patch.object(full,"source_hashes",return_value={"example.py":"frozen"}):
            plan=full.make_plan(ROOT,"teststudy",ROOT/"results/teststudy")
        plan["plan_sha256"]=full.plan_digest(plan)
        full.validate_plan(plan)
        first=plan["trials"][0]["name"]
        manifest={"schema_version":1,"plan_sha256":plan["plan_sha256"],"trials":{first:{"name":first,"status":"RECORDED"}}}
        full.validate_offline_manifest(manifest,plan)
        manifest["plan_sha256"]="other_plan"
        with self.assertRaises(ValueError):full.validate_offline_manifest(manifest,plan)
        manifest["plan_sha256"]=plan["plan_sha256"]
        manifest["trials"]["foreign_trial"]={"name":"foreign_trial"}
        with self.assertRaises(ValueError):full.validate_offline_manifest(manifest,plan)
        plan["trials"][0]["seed"]=999
        with self.assertRaises(ValueError):full.validate_plan(plan)

    def test_final_running_stage1_slot_is_reconciled_without_child_execution(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_full_plan_stage1_resume_") as temporary:
            root=Path(temporary);report=root/"child.json"
            trial={"name":"last_trial","stage":1,"target_class":"person","command_mode":"velocity","seed":0,"condition":"clean"}
            full.write_json(report,{"trials":[{**trial,"result":"RUNNING_FLIGHT"}]})
            plan={"trials":[trial],"matrices":[{"kind":"stage1","report":str(report),"trial_names":[trial["name"]]}]}
            with patch.object(full,"run_logged") as runner:
                self.assertEqual(full.execute_flights(plan,root/"master",root,0),0)
                runner.assert_not_called()
            self.assertEqual(full.load(report)["trials"][0]["result"],"INTERRUPTED")

    def test_runtime_hashes_include_root_config_and_actual_render_mesh(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_full_plan_hash_") as temporary:
            root=Path(temporary)
            config=root/"config/tracking.yaml";config.parent.mkdir(parents=True);config.write_text("gain: 1\n")
            mesh=root/"ros2_ws/src/pkg/models/target/mesh.obj";mesh.parent.mkdir(parents=True);mesh.write_text("v 0 0 0\n")
            before=full.source_hashes(root)
            self.assertIn("config/tracking.yaml",before)
            self.assertIn("ros2_ws/src/pkg/models/target/mesh.obj",before)
            mesh.write_text("v 1 0 0\n")
            self.assertNotEqual(full.source_hashes(root)["ros2_ws/src/pkg/models/target/mesh.obj"],before["ros2_ws/src/pkg/models/target/mesh.obj"])

    def test_last_interrupted_offline_slot_is_persisted_without_rerun(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_full_plan_offline_resume_") as temporary:
            root=Path(temporary);output=root/"study";child=root/"child.json"
            trial={"name":"last_trial","stage":1,"target_class":"person"}
            full.write_json(child,{"trials":[{**trial,"result":"FAIL"}]})
            plan={"plan_sha256":"frozen","trials":[trial],"matrices":[{"kind":"stage1","report":str(child)}]}
            manifest_path=output/"offline_manifest.json"
            full.write_json(manifest_path,{"schema_version":1,"plan_sha256":"frozen","trials":{"last_trial":{"name":"last_trial","status":"RUNNING_ANALYSIS"}}})
            with patch.object(full,"run_logged") as runner:
                full.execute_offline(plan,output,root)
                runner.assert_not_called()
            self.assertEqual(full.load(manifest_path)["trials"]["last_trial"]["status"],"INTERRUPTED")

    def test_join_offline_online_metrics_without_rewriting_flight_history(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_full_plan_") as temporary:
            root=Path(temporary);directory=root/"results/trial";directory.mkdir(parents=True)
            report=root/"child.json"
            trial={"name":"trial","stage":1,"target_class":"person","command_mode":"velocity","seed":0,
                   "condition":"clean","estimator_method":"adaptive_kf","matrix":"primary_matrix"}
            source={**trial,"result":"FAIL","online_state_evaluation_status":"EXPLICITLY_SKIPPED","horizontal_rmse_m":2.,"height_rmse_m":.1}
            full.write_json(report,{"trials":[source]})
            full.write_json(directory/"online_state_accuracy_v2.json",{"schema_version":2,
                "online_state_accuracy":{"active_coverage":.8,"position_reference_coverage":.7,"metrics":{"state_stamp_position_error_m":{"rmse":.2}}},
                "control_jitter":{"velocity_command_delta_over_dt_mps2":{"rmse":.3}}})
            plan={"plan_sha256":"fixed","trials":[trial],"matrices":[{"kind":"stage1","report":str(report)}]}
            result=full.consolidated_summary(plan,root/"summary",root)
            row=result["trials"][0]
            self.assertEqual(row["online_state_anchor_position_rmse_m"],.2)
            self.assertEqual(row["result"],"FAIL")
            self.assertEqual(row["flight_phase_evidence"]["online_state_evaluation_status"],"EXPLICITLY_SKIPPED")
            self.assertEqual(full.load(report)["trials"][0],source)
            with patch.object(full,"run_logged") as runner:
                plan["matrices"][0]["trial_names"]=["trial"]
                self.assertEqual(full.execute_flights(plan,root/"summary",root,0),0)
                runner.assert_not_called()


if __name__=="__main__":unittest.main()
