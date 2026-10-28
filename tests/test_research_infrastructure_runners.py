"""Infrastructure aborts defer pending slots without censoring algorithm failures."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import run_full_plan_research as master
import run_stage1_repetitions as stage1
import run_stage23_matrix as stage23

FAILURE={"stop":True,"reasons":[{"code":"NO_CLOCK","message":"No recorded clock","source":"metadata"}],"evidence":{}}
HEALTHY={"stop":False,"reasons":[],"evidence":{}}


class InfrastructureRunnerTests(unittest.TestCase):
    def test_stage1_preserves_failed_slot_and_never_launches_next_seed(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_stage1_infra_") as temporary:
            root=Path(temporary)
            args=["repeat","--prefix","infra","--seeds","0","1","--classes","person","--modes","velocity","--estimators","adaptive_kf","--skip-online-state-evaluation"]
            with patch.object(stage1,"ROOT",root),patch.object(sys,"argv",args),patch.object(stage1.subprocess,"run",return_value=SimpleNamespace(returncode=0)) as runner,patch.object(stage1,"classify_infrastructure_failure",return_value=FAILURE):
                stage1.main()
            self.assertEqual(runner.call_count,1)
            report=json.loads((root/"results/infra_repetition_report.json").read_text())
            self.assertEqual(report["expected_trials"],2)
            self.assertFalse(report["complete"])
            self.assertEqual(report["trials"][0]["result"],"FAIL")
            self.assertTrue(report["trials"][0]["infrastructure_failure"]["stop"])

    def test_stage23_stops_before_next_flight_and_retains_pending(self):
        trials=[r for r in stage23.plan_trials("infra",[0]) if r["stage"]==3][:2]
        manifest={"plan_sha256":"test","protocol":{"wall_timeout_s":300.,"render_backend":"egl"},"slots":[{"trial":trial,"status":"PENDING"} for trial in trials]}
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_stage23_infra_") as temporary:
            root=Path(temporary)
            with patch.object(stage23,"classify_infrastructure_failure",return_value=FAILURE),patch.object(stage23.subprocess,"run",return_value=SimpleNamespace(returncode=0)) as runner:
                # Explicitly pass the patched runner: execute's default was
                # bound when its module loaded, before this patch.
                stage23.execute(manifest,root/"matrix",root=root,runner=runner)
            self.assertEqual(runner.call_count,1)
            self.assertEqual([slot["status"] for slot in manifest["slots"]],["FAIL","PENDING"])

    def test_stage1_evaluator_core_input_failure_stops_before_online_or_next_flight(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_stage1_eval_infra_") as temporary:
            root=Path(temporary)
            def run(command,**unused):
                if command[1].endswith("run_stage1_trial.sh"):
                    directory=root/"results"/command[command.index("--name")+1]/"rosbag"
                    directory.mkdir(parents=True)
                    (directory/"metadata.yaml").touch()
                return SimpleNamespace(returncode=0)
            args=["repeat","--prefix","infra","--seeds","0","1","--classes","person","--modes","velocity","--estimators","adaptive_kf"]
            with patch.object(stage1,"ROOT",root),patch.object(sys,"argv",args),patch.object(stage1.subprocess,"run",side_effect=run) as runner,patch.object(stage1,"classify_infrastructure_failure",side_effect=[HEALTHY,FAILURE]):
                stage1.main()
            self.assertEqual(runner.call_count,2) # flight + primary evaluator only
            report=json.loads((root/"results/infra_repetition_report.json").read_text())
            self.assertEqual(len(report["trials"]),1)
            self.assertEqual(report["trials"][0]["result"],"FAIL")
            self.assertTrue(report["trials"][0]["infrastructure_failure"]["stop"])

    def test_stage23_evaluator_core_input_failure_retains_pending(self):
        trials=[r for r in stage23.plan_trials("infra",[0]) if r["stage"]==2][:2]
        manifest={"plan_sha256":"test","protocol":{"wall_timeout_s":300.,"render_backend":"egl"},"slots":[{"trial":trial,"status":"PENDING"} for trial in trials]}
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_stage23_eval_infra_") as temporary:
            root=Path(temporary)
            def run(command,**unused):
                if command[1].endswith("run_stage1_trial.py"):
                    directory=root/"results"/command[command.index("--name")+1]/"rosbag"
                    directory.mkdir(parents=True)
                    (directory/"metadata.yaml").touch()
                return SimpleNamespace(returncode=0)
            with patch.object(stage23,"classify_infrastructure_failure",side_effect=[HEALTHY,FAILURE]),patch.object(stage23.subprocess,"run",side_effect=run) as runner:
                stage23.execute(manifest,root/"matrix",root=root,runner=runner)
            self.assertEqual(runner.call_count,2)
            self.assertEqual([slot["status"] for slot in manifest["slots"]],["FAIL","PENDING"])

    def test_master_defers_later_matrix_then_resume_runs_only_pending(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"results",prefix="test_master_infra_") as temporary:
            root=Path(temporary);output=root/"study"
            plan={"trials":[{"name":"first"},{"name":"second"}],"matrices":[
                {"kind":"stage1","key":"one","report":str(root/"one.json"),"trial_names":["first"]},
                {"kind":"stage1","key":"two","report":str(root/"two.json"),"trial_names":["second"]}]}
            def first_run(*unused,**kwargs):
                master.write_json(root/"one.json",{"trials":[{"name":"first","result":"FAIL","infrastructure_failure":FAILURE}]})
                return {"returncode":0}
            with patch.object(master,"matrix_command",return_value=["fake"]),patch.object(master,"run_logged",side_effect=first_run) as runner:
                self.assertEqual(master.execute_flights(plan,output,root,0),1)
                self.assertEqual(runner.call_count,1)
            self.assertEqual(master.flight_records(plan).get("second",{}).get("status","PENDING"),"PENDING")
            def second_run(*unused,**kwargs):
                master.write_json(root/"two.json",{"trials":[{"name":"second","result":"PASS"}]})
                return {"returncode":0}
            with patch.object(master,"matrix_command",return_value=["fake"]),patch.object(master,"run_logged",side_effect=second_run) as runner:
                self.assertEqual(master.execute_flights(plan,output,root,0),1)
                self.assertEqual(runner.call_count,1)
            self.assertEqual(master.flight_records(plan)["first"]["status"],"FAIL")
            self.assertEqual(len(master.load(output/"infrastructure_stops.json")),1)


if __name__=="__main__":unittest.main()
