"""The review index must not invent acceptance or hide missing opportunities."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC=importlib.util.spec_from_file_location("build_acceptance_dashboard",Path(__file__).resolve().parents[1]/"scripts/build_acceptance_dashboard.py")
dashboard=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


class AcceptanceDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/"results"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def json(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data),encoding="utf-8")

    def trial(self,name="stage2_person & review"):
        trial=self.root/name
        self.json(trial/"run_config.json",{"target_class":"person","command_mode":"velocity"})
        self.json(trial/"summary.json",{"source":"ONBOARD_RGBD_YOLO_PX4_FLIGHT","basic_flight_passed":True,"armed_seen":True,"offboard_seen":True})
        return trial

    def complete_safety_artifacts(self,trial):
        self.json(trial/"stage2_evaluation.json",{"result":"PASS","checks":{"recorded":True}})
        self.json(trial/"configuration/source_sha256.json",{})
        (trial/"onboard.mp4").write_bytes(b"x"*1025)
        (trial/"rosbag").mkdir()
        (trial/"rosbag/metadata.yaml").write_text("fixture",encoding="utf-8")
        (trial/"rosbag/fixture.db3").write_bytes(b"fixture")

    def full_plan(self,root=None):
        root=root or self.root
        trials=[{"name":f"fullplan_v1_trial_{index:03d}","stage":2} for index in range(166)]
        plan={"schema_version":1,"frozen_root":"/root/uav_tracking_fullplan_v1","trials":trials,
              "matrices":[{"kind":"stage1","report":"/root/uav_tracking_fullplan_v1/results/primary_repetition_report.json"}],
              "protocol":"166 preregistered independent flight slots"}
        plan["plan_sha256"]=hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        path=root/"full_plan_research_v1/plan.json"
        self.json(path,plan)
        return path,plan

    def test_independent_wrong_identity_fails_overall_without_rewriting_safety(self):
        trial=self.trial()
        self.complete_safety_artifacts(trial)
        self.json(trial/"physical_identity.json",{"selected_physical_identity_all":{"frames":10,"counts":{"CORRECT":2,"WRONG_PHYSICAL_ACTOR":1,"NOT_OBSERVED":5,"UNKNOWN_GEOMETRY":2,"UNKNOWN_TASK_INITIAL_ID":0}}})
        record=dashboard.collect_trial(trial)
        self.assertEqual(record["status"],"FAIL")
        self.assertEqual(record["dimensions"][0]["status"],"PASS")
        self.assertEqual(record["identity"]["status"],"WRONG_PHYSICAL_ACTOR")

    def test_unknown_identity_is_explicit_and_not_misclassified_as_wrong(self):
        trial=self.trial()
        self.complete_safety_artifacts(trial)
        self.json(trial/"physical_identity.json",{"selected_physical_identity_all":{"frames":10,"counts":{"CORRECT":3,"WRONG_PHYSICAL_ACTOR":0,"NOT_OBSERVED":5,"UNKNOWN_GEOMETRY":2,"UNKNOWN_TASK_INITIAL_ID":0}}})
        record=dashboard.collect_trial(trial)
        self.assertEqual(record["status"],"PASS")
        self.assertEqual(record["identity"]["status"],"NO_OBSERVED_WRONG_MATCH")
        self.assertEqual(record["identity"]["correct_lower_bound"],"3/10 (30.0%)")
        rendered=dashboard.trial_html(record,self.root/"review.html",0)
        self.assertIn("已知帧未见错配（未知仍保留）",rendered)
        self.assertIn("5/10 (50.0%)",rendered)

    def test_zero_known_identity_remains_incomplete_evidence(self):
        identity=dashboard.identity_coverage({"selected_physical_identity_all":{"frames":10,"counts":{"CORRECT":0,"WRONG_PHYSICAL_ACTOR":0,"NOT_OBSERVED":5,"UNKNOWN_GEOMETRY":5,"UNKNOWN_TASK_INITIAL_ID":0}}})
        self.assertEqual(identity["status"],"INCOMPLETE_EVIDENCE")

    def test_partial_identity_with_null_report_or_counts_remains_incomplete(self):
        for data in ({"selected_physical_identity_all":None},
                     {"selected_physical_identity_all":{"counts":None}}):
            self.assertEqual(dashboard.identity_coverage(data)["status"],"INCOMPLETE_EVIDENCE")

    def test_stage_two_common_gimbal_default_is_not_displayed_as_active_mode(self):
        trial=self.trial()
        self.json(trial/"run_config.json",{"target_class":"person","gimbal_mode":"active","command_mode":"velocity"})
        rendered=dashboard.trial_html(dashboard.collect_trial(trial),self.root/"review.html",0)
        self.assertNotIn(" · active",rendered)

    def test_matrix_prefix_is_discovered_from_explicit_run_stage(self):
        trial=self.trial("stage23_engineering_v1_s2_car_ambiguity_locked_seed000")
        self.json(trial/"run_config.json",{"target_class":"car","stage":2})
        trials=dashboard.discover_trials([self.root])
        self.assertEqual(len(trials),1)
        self.assertEqual(trials[0]["stage"],2)
        self.assertEqual(trials[0]["status"],"INCOMPLETE_EVIDENCE")

    def test_escaping_and_relative_paths_without_external_assets(self):
        trial=self.trial()
        self.json(trial/"stage2_evaluation.json",{"result":"FAIL","checks":{"<script>alert(1)</script>":False}})
        output=self.root/"验收总览.html"
        dashboard.build_dashboard([self.root],output)
        result=output.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",result)
        self.assertNotIn("<script>alert(1)</script>",result)
        self.assertIn("stage2_person%20%26%20review/run_config.json",result)
        self.assertNotIn("file://",result)
        self.assertNotIn("https://",result)

    def test_pass_label_with_missing_artifacts_cannot_pass_engineering(self):
        trial=self.trial()
        self.json(trial/"stage2_evaluation.json",{"result":"PASS","checks":{"recorded":True}})
        record=dashboard.collect_trial(trial)
        self.assertEqual(record["status"],"INCOMPLETE_EVIDENCE")
        self.assertIn("onboard.mp4",record["missing"])

    def test_missing_dimension_report_has_no_dead_link_but_failure_logs_remain_available(self):
        trial=self.trial()
        for name in ("process_exit_codes.json","monitor.log","bag.log","offline_evaluation.log"):
            (trial/name).write_text("failed fixture",encoding="utf-8")
        rendered=dashboard.trial_html(dashboard.collect_trial(trial),self.root/"review.html",0)
        self.assertIn("报告未生成（stage2_evaluation.json）",rendered)
        self.assertNotIn('/stage2_evaluation.json"',rendered)
        for name in ("process_exit_codes.json","monitor.log","bag.log","offline_evaluation.log"):
            self.assertIn('/'+name+'"',rendered)

    def test_cloud_gimbal_pass_does_not_supply_missing_flight_acceptance(self):
        trial=self.trial("stage3_person_active")
        self.json(trial/"gimbal_evaluation.json",{"result":"PASS","checks":{"geometry":True}})
        record=dashboard.collect_trial(trial)
        independent=next(item for item in record["dimensions"] if item["name"]=="独立跟随/遮挡验收")
        self.assertEqual(independent["status"],"INCOMPLETE_EVIDENCE")

    def test_matrix_stage_three_flight_report_filename_is_read(self):
        trial=self.trial("stage3_person_active")
        self.json(trial/"flight_evaluation.json",{"acceptance":{"result":"PASS"}})
        module=SimpleNamespace(offline_acceptance_evidence=lambda report:{"strict_evidence":True})
        with patch.dict(sys.modules,{"summarize_stage1_acceptance":module}):
            record=dashboard.collect_trial(trial)
        independent=next(item for item in record["dimensions"] if item["name"]=="独立跟随/遮挡验收")
        self.assertEqual(independent["status"],"PASS")
        self.assertEqual(independent["file"],"flight_evaluation.json")
        self.assertEqual(record["status"],"INCOMPLETE_EVIDENCE", "other missing evidence still cannot pass")

    def test_auto_unique_uses_its_actual_evaluator_without_identity_claim(self):
        trial=self.trial("stage2_car_auto_unique")
        self.json(trial/"auto_unique_evaluation.json",{"result":"PASS","checks":{"stopped_on_ambiguity":True}})
        record=dashboard.collect_trial(trial)
        self.assertEqual(record["dimensions"][0]["status"],"PASS")
        self.assertEqual(record["dimensions"][0]["file"],"auto_unique_evaluation.json")
        rendered=dashboard.trial_html(record,self.root/"review.html",0)
        self.assertIn("指定目标身份评价不适用",rendered)
        self.assertNotIn("任务 UUID 保持不证明物理身份",rendered)

    def test_new_supported_failure_cannot_be_hidden_by_old_passing_report(self):
        trial=self.trial("stage3_car_active")
        self.json(trial/"gimbal_evaluation.json",{"schema_version":1,"result":"PASS","checks":{"old":True}})
        self.json(trial/"gimbal_evaluation_v3.json",{"schema_version":3,"result":"FAIL","checks":{"new":False}})
        record=dashboard.collect_trial(trial)
        self.assertEqual(record["status"],"FAIL")
        self.assertEqual(record["dimensions"][0]["file"],"gimbal_evaluation_v3.json")
        self.assertEqual(len(record["evaluation_history"]),2)
        rendered=dashboard.trial_html(record,self.root/"review.html",0)
        self.assertIn("评价器版本历史",rendered)
        self.assertIn("gimbal_evaluation.json",rendered)

    def test_new_supported_decoder_report_is_selected_with_old_failure_retained(self):
        trial=self.trial("stage2_car_auto_unique")
        self.json(trial/"auto_unique_evaluation.json",{"schema_version":1,"result":"FAIL","checks":{"decoder":False}})
        self.json(trial/"auto_unique_evaluation_v2.json",{"schema_version":2,"result":"PASS","checks":{"decoder":True}})
        record=dashboard.collect_trial(trial)
        self.assertEqual(record["dimensions"][0]["status"],"PASS")
        self.assertEqual(record["dimensions"][0]["file"],"auto_unique_evaluation_v2.json")
        self.assertEqual(record["status"],"INCOMPLETE_EVIDENCE")
        # History preserves every report but does not promise a display/time
        # order; Path.glob enumeration differs between Windows and Linux.
        self.assertCountEqual([(row["file"],row["schema"],row["status"])
                               for row in record["evaluation_history"]],
                              [("auto_unique_evaluation.json",1,"FAIL"),
                               ("auto_unique_evaluation_v2.json",2,"PASS")])

    def test_unsupported_gimbal_schema_cannot_supply_a_pass(self):
        trial=self.trial("stage3_car_active")
        self.json(trial/"gimbal_evaluation.json",{"schema_version":999,"result":"PASS","checks":{"unknown":True}})
        record=dashboard.collect_trial(trial)
        self.assertEqual(record["dimensions"][0]["status"],"INCOMPLETE_EVIDENCE")

    def test_no_fresh_and_unknown_remain_in_identity_denominator(self):
        data={"selected_physical_identity_all":{"frames":10,"counts":{"CORRECT":3,"WRONG_PHYSICAL_ACTOR":0,"NOT_OBSERVED":5,"UNKNOWN_GEOMETRY":2,"UNKNOWN_TASK_INITIAL_ID":0}}}
        identity=dashboard.identity_coverage(data)
        self.assertEqual(identity["correct_lower_bound"],"3/10 (30.0%)")
        self.assertEqual(identity["conditional_agreement"],"3/3 (100.0%)")
        self.assertEqual(identity["no_fresh_fraction"],"5/10 (50.0%)")
        self.assertEqual(identity["unknown_fraction"],"2/10 (20.0%)")

    def test_partial_matrix_keeps_unstarted_plan(self):
        progress=dashboard.research_progress({"expected_trials":40,"recorded_trials":2,"complete":False,"trials":[{"result":"PASS"},{"result":"FAIL"}]})
        self.assertFalse(progress["complete"])
        self.assertEqual(progress["counts"]["planned"],38)
        self.assertEqual(progress["counts"]["complete"],2)
        self.assertEqual(progress["counts"]["failed"],1)

    def test_declared_complete_without_terminal_rows_is_not_complete(self):
        progress=dashboard.research_progress({"expected_trials":2,"complete":True,"trials":[{"status":"complete"},{"status":"started"}]})
        self.assertFalse(progress["complete"])
        self.assertEqual(progress["counts"]["started"],1)

    def test_proposed_detection_metrics_remain_pending(self):
        progress=dashboard.research_progress({"recordings":[{"sampled_opportunities":45,"geometric_eligible":26,"approved_eligible":0,"publication_status":"PENDING_VISUAL_REVIEW"}],"reviewed_aggregate":None})
        self.assertEqual(progress["state"],"PENDING_VISUAL_REVIEW")
        self.assertFalse(progress["complete"])
        self.assertEqual(progress["reviewed"],0)

    def test_empty_results_remain_unfinished(self):
        output=self.root/"验收总览.html"
        report=dashboard.build_dashboard([self.root],output)
        self.assertEqual(report["trials"],0)
        self.assertIn("研究工作保持未完成",output.read_text(encoding="utf-8"))

    def test_exported_figures_are_visible_and_missing_files_remain_explicit(self):
        figure_dir=self.root/"research_figures"
        self.json(figure_dir/"manifest.json",{"figures":["audit.png","missing.png","../escape.png"],"claim_boundary":"offline only"})
        (figure_dir/"audit.png").write_bytes(b"fixture")
        (figure_dir/"audit.svg").write_text("<svg/>",encoding="utf-8")
        output=self.root/"review.html"
        report=dashboard.build_dashboard([self.root],output)
        self.assertEqual(report["research_figure_files"],1)
        self.assertEqual(report["research_reports"],0)
        rendered=output.read_text(encoding="utf-8")
        self.assertIn('src="research_figures/audit.png"',rendered)
        self.assertIn('href="research_figures/audit.svg"',rendered)
        self.assertIn("missing.png, ../escape.png",rendered)
        self.assertNotIn('src="escape.png"',rendered)

    def test_reviewed_detection_reports_operating_misses_alongside_ap(self):
        self.json(self.root/"detection_research/detection_report.json",{
            "recordings":[{"sampled_opportunities":100,"geometric_eligible":80,"approved_eligible":80}],
            "reviewed_aggregate":{"map50_95":.98,"classes":{"car":{"precision":1,"recall":.75,"fn":19,"confidence_threshold":.45}}}})
        output=self.root/"review.html"
        dashboard.build_dashboard([self.root],output)
        rendered=output.read_text(encoding="utf-8")
        self.assertIn("已复核子集 mAP50:95：0.98",rendered)
        self.assertIn("漏检 FN",rendered)
        self.assertIn("<td>19</td>",rendered)
        self.assertIn("AP 使用置信度扫描",rendered)

    def test_full_plan_without_executed_or_offline_rows_preserves_both_166_denominators(self):
        self.full_plan()
        entries=dashboard.discover_research([self.root])
        study=next(item for item in entries if item["progress"]["kind"]=="full_plan")
        progress=study["progress"]
        self.assertEqual(study["errors"],[])
        self.assertEqual(progress["flight_counts"]["pending"],166)
        self.assertEqual(progress["offline_counts"]["pending"],166)
        self.assertFalse(progress["complete"])
        self.assertFalse(progress["all_flights_pass"])

    def test_current_child_manifest_overrides_stale_summary_and_retains_failures(self):
        path,plan=self.full_plan()
        names=[row["name"] for row in plan["trials"]]
        self.json(path.parent/"summary.json",{"plan_sha256":plan["plan_sha256"],"planned_flights":166,
                  "all_flights_pass":True,"trials":[{"name":name,"result":"PASS"} for name in names]})
        child=self.root/"primary_repetition_report.json"
        self.json(child,{"trials":[{"name":names[0],"result":"FAIL"},
                                    {"name":names[1],"result":"RUNNING_FLIGHT"},
                                    {"name":names[2],"result":"RUNNING_EVALUATION"},
                                    {"name":names[3],"result":"INTERRUPTED"}]})
        before=child.read_bytes()
        progress=dashboard.collect_full_plan(path,plan)["progress"]
        self.assertEqual(progress["flight_counts"]["running"],2)
        self.assertEqual(progress["flight_counts"]["failed"],2)
        self.assertEqual(progress["flight_counts"]["raw"]["PASS"],162)
        self.assertFalse(progress["all_flights_pass"])
        self.assertFalse(progress["complete"])
        self.assertEqual(before,child.read_bytes())

    def test_relative_stage23_report_binds_to_frozen_results(self):
        path,plan=self.full_plan()
        names=[row["name"] for row in plan["trials"]]
        plan["matrices"]=[{"kind":"stage23","report":"results/full_plan_research_v1/stage23_matrix/manifest.json"}]
        plan["plan_sha256"]=hashlib.sha256(json.dumps({key:value for key,value in plan.items() if key!="plan_sha256"},sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        self.json(path,plan)
        self.json(path.parent/"stage23_matrix/manifest.json",{"slots":[
            {"trial":{"name":names[0]},"status":"FAIL"},{"trial":{"name":names[1]},"status":"PASS"}]})
        study=dashboard.collect_full_plan(path,plan)
        self.assertEqual(study["errors"],[])
        self.assertEqual(study["progress"]["flight_counts"]["terminal"],2)
        self.assertEqual(study["progress"]["flight_counts"]["pending"],164)
        self.assertEqual(study["progress"]["flight_counts"]["failed"],1)

    def test_relative_matrix_report_cannot_escape_selected_results_root(self):
        path,plan=self.full_plan()
        outside=self.root.parent/"outside.json"
        self.json(outside,{"slots":[{"trial":{"name":row["name"]},"status":"PASS"} for row in plan["trials"]]})
        plan["matrices"]=[{"kind":"stage23","report":"results/../outside.json"}]
        plan["plan_sha256"]=hashlib.sha256(json.dumps({key:value for key,value in plan.items() if key!="plan_sha256"},sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        with patch.object(dashboard,"read_json",wraps=dashboard.read_json) as reader:
            study=dashboard.collect_full_plan(path,plan)
        self.assertTrue(study["errors"])
        self.assertEqual(study["progress"]["flight_counts"]["pending"],166)
        self.assertFalse(any(call.args[0].resolve()==outside.resolve() for call in reader.call_args_list))

    def test_checkpoint_separates116_formal_slots_from117_recording_cards(self):
        path,plan=self.full_plan()
        names=[row["name"] for row in plan["trials"]]
        plan["matrices"]=[{"kind":"stage23","report":"results/full_plan_research_v1/stage23_matrix/manifest.json"}]
        plan["plan_sha256"]=hashlib.sha256(json.dumps({key:value for key,value in plan.items() if key!="plan_sha256"},sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        self.json(path,plan)
        self.json(path.parent/"stage23_matrix/manifest.json",{"slots":[
            {"trial":{"name":name},"status":"PASS" if index<76 else "FAIL" if index<116 else "PENDING"}
            for index,name in enumerate(names)]})
        cards=[{"directory":self.root/name,"stage":2,"status":"PASS" if index<76 else "FAIL"}
               for index,name in enumerate(names[:116])]
        cards.append({"directory":self.root/"diagnostic_probe","stage":1,"status":"INCOMPLETE_EVIDENCE"})
        frame=self.root/names[0]/"selected target.jpg"
        frame.parent.mkdir()
        frame.write_bytes(b"existing-image-fixture")
        output=self.root/"checkpoint.html"
        with patch.object(dashboard,"discover_trials",return_value=cards),patch.object(dashboard,"trial_html",return_value="<article></article>"):
            report=dashboard.build_dashboard([self.root],output,checkpoint_title="检查点116 · 未完成",highlight_frames=[frame])
        rendered=output.read_text(encoding="utf-8")
        self.assertIn("正式飞行已终止：116 / 166",rendered)
        self.assertIn("PASS 76 / FAIL 40 / PENDING 50 / RUNNING 0",rendered)
        self.assertIn("离线分析：0 / 166；PENDING 166",rendered)
        self.assertIn("页面录制卡片 117，其中正式计划内 116、计划外 1",rendered)
        self.assertEqual(rendered.count("<td>PENDING</td>"),50)
        self.assertIn(names[-1],rendered)
        self.assertIn(names[0]+"/selected%20target.jpg",rendered)
        self.assertEqual(report["formal_plan_counts"][0]["flight"]["terminal"],116)
        self.assertEqual(report["trials"],117)

    def test_full_execution_with_failed_flight_and_not_applicable_offline_is_not_all_pass(self):
        path,plan=self.full_plan()
        names=[row["name"] for row in plan["trials"]]
        self.json(self.root/"primary_repetition_report.json",{"trials":[
            {"name":name,"result":"FAIL" if index==0 else "PASS"} for index,name in enumerate(names)]})
        self.json(path.parent/"offline_manifest.json",{"plan_sha256":plan["plan_sha256"],"trials":{
            name:{"name":name,"status":"NOT_APPLICABLE_NO_SELECTED_TASK" if index==0 else "RECORDED"}
            for index,name in enumerate(names)}})
        progress=dashboard.collect_full_plan(path,plan)["progress"]
        self.assertTrue(progress["complete"])
        self.assertFalse(progress["all_flights_pass"])
        self.assertEqual(progress["flight_counts"]["failed"],1)
        self.assertEqual(progress["offline_counts"]["terminal"],166)
        self.assertEqual(progress["offline_counts"]["raw"]["NOT_APPLICABLE_NO_SELECTED_TASK"],1)

    def test_wrong_plan_offline_and_unknown_flight_status_do_not_complete(self):
        path,plan=self.full_plan()
        name=plan["trials"][0]["name"]
        self.json(self.root/"primary_repetition_report.json",{"trials":[{"name":name,"result":"ALIEN_STATUS"}]})
        self.json(path.parent/"offline_manifest.json",{"plan_sha256":"other-study","trials":{
            row["name"]:{"name":row["name"],"status":"RECORDED"} for row in plan["trials"]}})
        study=dashboard.collect_full_plan(path,plan)
        self.assertEqual(study["progress"]["flight_counts"]["unknown"],1)
        self.assertEqual(study["progress"]["flight_counts"]["pending"],165)
        self.assertEqual(study["progress"]["offline_counts"]["pending"],166)
        self.assertFalse(study["progress"]["complete"])
        self.assertTrue(study["errors"])

    def test_superseded_history_retains_original_counts_without_promoting_completion(self):
        path,plan=self.full_plan()
        names=[row["name"] for row in plan["trials"]]
        self.json(self.root/"primary_repetition_report.json",{"trials":[
            {"name":name,"result":"FAIL" if index==0 else "PASS"}
            for index,name in enumerate(names[:8])]})
        self.json(path.parent/"superseded.json",{"plan_sha256":plan["plan_sha256"],
            "replacement_prefix":"fullplan_v2","reason":"reader ordering correction"})
        study=dashboard.collect_full_plan(path,plan)
        self.assertEqual(study["progress"]["flight_counts"]["pending"],158)
        self.assertEqual(study["progress"]["flight_counts"]["failed"],1)
        self.assertFalse(study["progress"]["complete"])
        rendered=dashboard.study_progress_html(study,self.root/"review.html")
        self.assertIn("历史研究，已由 fullplan_v2 替代",rendered)
        self.assertIn("已有飞行不计入替代研究分母",rendered)
        self.assertIn("superseded.json",rendered)

    def test_superseded_annotation_for_different_plan_is_rejected(self):
        path,plan=self.full_plan()
        self.json(path.parent/"superseded.json",{"plan_sha256":"wrong","replacement_prefix":"other"})
        study=dashboard.collect_full_plan(path,plan)
        self.assertIsNone(study["progress"]["superseded"])
        self.assertTrue(study["errors"])

    def test_extended_nested_sixteen_slots_keep_running_failure_and_pending_separate(self):
        trials=[{"name":f"extended_{index}"} for index in range(16)]
        plan={"expected_trials":16,"primary_166_included":False,"trials":trials}
        statuses=["PASS","FAIL","RUNNING_EVALUATION","INTERRUPTED"]+["PENDING"]*12
        manifest={"source":"EXTENDED_ENGINEERING_16_FLIGHTS","plan":plan,
                  "plan_sha256":hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(",", ":")).encode()).hexdigest(),
                  "slots":[{"trial":trial,"status":status} for trial,status in zip(trials,statuses)]}
        self.json(self.root/"extended_engineering_v1_matrix/manifest.json",manifest)
        study=dashboard.discover_research([self.root])[0]
        self.assertEqual(study["errors"],[])
        self.assertEqual(study["progress"]["expected"],16)
        self.assertEqual(study["progress"]["flight_counts"]["pending"],12)
        self.assertEqual(study["progress"]["flight_counts"]["running"],1)
        self.assertEqual(study["progress"]["flight_counts"]["failed"],2)
        rendered=dashboard.study_progress_html(study,self.root/"review.html")
        self.assertIn("扩展16次单列于主166次之外",rendered)
        self.assertIn("FAIL",rendered)
        self.assertIn("未完成",rendered)

    def test_new_six_group_artifact_manifest_links_png_svg_pdf_and_csv_from_additional_root(self):
        extra=self.root.parent/"additional frozen results"
        path,plan=self.full_plan(extra)
        trial=extra/plan["trials"][0]["name"]
        self.json(trial/"run_config.json",{"target_class":"person","stage":2})
        self.json(trial/"summary.json",{"basic_flight_passed":False})
        self.complete_safety_artifacts(trial)
        figure_dir=extra/"full_plan_figures"
        artifacts={}
        for index in range(6):
            for extension in ("png","pdf","svg"):
                name=f"group_{index}.{extension}"
                figure_dir.mkdir(parents=True,exist_ok=True)
                (figure_dir/name).write_bytes(b"fixture")
                artifacts[name]="fixture-hash"
        (figure_dir/"flight_units.csv").write_text("trial,status\n",encoding="utf-8")
        artifacts["flight_units.csv"]="fixture-hash"
        self.json(figure_dir/"manifest.json",{"source_summary_sha256":"source", "artifacts_sha256":artifacts})
        output=self.root/"review.html"
        report=dashboard.build_dashboard([self.root,extra,extra/"full_plan_figures"],output)
        self.assertEqual(report["research_figure_files"],6)
        self.assertEqual(report["trials"],1)
        rendered=output.read_text(encoding="utf-8")
        self.assertIn("主研究166次飞行",rendered)
        self.assertIn("离线分析分母 166",rendered)
        self.assertIn("additional%20frozen%20results/full_plan_figures/group_0.png",rendered)
        self.assertIn("group_0.pdf",rendered)
        self.assertIn("group_0.svg",rendered)
        self.assertIn("flight_units.csv",rendered)
        self.assertIn("rosbag/fixture.db3",rendered)
        self.assertIn("onboard.mp4",rendered)
        self.assertIn(plan["trials"][-1]["name"],rendered)


if __name__=="__main__":
    unittest.main()
