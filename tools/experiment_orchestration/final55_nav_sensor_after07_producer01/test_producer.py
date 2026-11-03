"""Windows-only synthetic fixtures; no WSL, native evaluator, bag, or image IO."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location("after07_direct_producer_fixture",Path(__file__).with_name("producer.py"))
p=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    p.write_new(path,value)
    return p.bound(path.resolve())


class ProducerTests(unittest.TestCase):
    def nav_fixture(self,tmp,*,mode="PROBE",reject_validator=False):
        root=Path(tmp).resolve()
        target={"frozen_root":str(root/"final"),"mode":mode,"source_hashes":{"builder":"b","runner":"r","evaluator":"e"}}
        target_binding=put(root/"input/target.json",target)
        sources=[];planned=[];originals={}
        for source_mode,size in (("PROBE",12),("EXTENSION_PROBE",16)):
            source=put(root/(source_mode+"/plan.json"),{"mode":source_mode})
            sources.append({"mode":source_mode,**source,"plan_sha256":"actual_fixture_plan_digest"})
            for i in range(size):
                slot=source_mode.lower()+"_%02d" % i
                trial_dir=root/"trials"/slot;trial_dir.mkdir(parents=True)
                report=trial_dir/"new_navigation.json"
                command=["bash","EXACT_BOUND_ROOT/scripts/run_research_session.sh","EXACT_BOUND_ROOT/scripts/evaluate_navigation_reference.py",
                         str(trial_dir),"--target-class","person" if i%2 else "car"]
                if i%3 == 0:
                    command.extend(["--physical-identity-report",str(trial_dir/"original_identity.json")])
                command.extend(["--output",str(report)])
                fixed={"plan_path":source["path"],"slot_id":slot,"record_file_sha256":"original_terminal_sha",
                       "original_report_sha256":"original_report_sha","report":str(report),"command":command}
                planned.append(fixed)
                originals[source["path"],slot]=({"evaluation_timeout_s":1800.0,"frozen_root":str(root/"original_frozen")},
                    {"directory":str(trial_dir)},{"finished_utc":"2020-01-01T00:00:00+00:00"})
        registration={"schema_version":1,"kind":"RELIABILITY_V4_ALL28_NAVIGATION_REEVALUATION_REGISTRATION",
            "evaluation_root":target["frozen_root"],"target_source_hashes":target["source_hashes"],
            "implementation_source_hashes":{"builder":"b","runner":"r"},"evaluation_source_hashes":{"evaluator":"e"},
            "source_plans":sources,"report_basename":"new_navigation.json","planned_evaluations":planned,
            "created_utc":"2020-01-02T00:00:00+00:00"}
        registration_binding=put(root/"input/registration.json",registration)
        calls={"invocations":[],"validator":[],"snapshots":[]}
        def inputs(actual,paths,basename,*,require_new):
            self.assertEqual(actual,target);self.assertEqual(paths,[s["path"] for s in sources])
            self.assertEqual(basename,"new_navigation.json");self.assertTrue(require_new)
            return deepcopy(sources),deepcopy(planned),deepcopy(originals)
        def validator(path,actual,selected,*,extension):
            manifest=p.load(path);calls["validator"].append(deepcopy(manifest))
            self.assertEqual(actual,target)
            self.assertEqual(selected,[s["path"] for s in sources if s["mode"] == mode])
            self.assertEqual(extension,mode == "EXTENSION_PROBE")
            self.assertEqual(manifest["kind"],"RELIABILITY_V4_ALL28_NAVIGATION_REEVALUATIONS")
            self.assertEqual(manifest["prospective_registration"],registration_binding)
            self.assertEqual(manifest["source_plans"],sources)
            self.assertEqual(len(manifest["slots"]),28)
            for fixed,slot in zip(planned,manifest["slots"]):
                self.assertEqual(slot["plan_path"],fixed["plan_path"])
                self.assertEqual(slot["slot_id"],fixed["slot_id"])
                self.assertEqual(slot["record_file_sha256"],fixed["record_file_sha256"])
                self.assertEqual(len(slot["evaluation_overrides"]),1)
                override=slot["evaluation_overrides"][0]
                self.assertEqual(override["kind"],"navigation")
                self.assertEqual(override["original_report_sha256"],fixed["original_report_sha256"])
                self.assertEqual(override["execution"]["command"],fixed["command"])
                self.assertEqual(override["report_sha256"],p.sha(fixed["report"]))
                self.assertEqual(override["execution"]["log_sha256"],p.sha(override["execution"]["log"]))
            if reject_validator:
                raise ValueError("ORIGINAL_VALIDATOR_REJECTED_FIXTURE")
            return {i:{} for i in range(16 if extension else 12)},p.bound(path)
        def snapshot(path,*,extension):
            calls["snapshots"].append((path,extension));return path,deepcopy(target),{}
        v4=types.SimpleNamespace(offline_source_hashes=lambda _: {"evaluator":"e"},utc_timestamp=datetime.fromisoformat,utc_now=p.utc)
        builder=types.SimpleNamespace(v4=v4,SCRIPT="builder",RUNNER="runner",navigation_registration_inputs=inputs,
                                      read_navigation_reevaluation_manifest=validator,target_snapshot=snapshot)
        def invoke(command,log,timeout):
            calls["invocations"].append((list(command),timeout))
            self.assertEqual(timeout,1800.0)
            # This is a fake result; FAIL/null must survive the producer unchanged.
            p.write_new(Path(command[-1]),{"engineering_status":"FAIL","identity":None})
            Path(log).write_bytes(b"synthetic evaluator log only")
            return {"command":list(command),"started_utc":p.utc(),"finished_utc":p.utc(),"returncode":0,"error":None,
                    "log":str(log),"log_sha256":p.sha(log)}
        return builder,target,registration_binding,target_binding,root/"output",invoke,calls,planned

    def test_inert_default_and_unexecuted_subcommand_read_no_inputs_or_helpers(self):
        for argv in ([],["describe"],["nav","--target-plan","NO_READ","--target-plan-sha256","NO_READ",
                     "--registration","NO_READ","--registration-sha256","NO_READ","--output-directory","NO_WRITE"]):
            with self.subTest(argv=argv),patch.object(p,"bound",side_effect=AssertionError("input read forbidden")), \
                 patch.object(p,"fixed_module",side_effect=AssertionError("native import forbidden")), \
                 patch("sys.stdout",new_callable=io.StringIO) as output:
                self.assertEqual(p.main(argv),0)
                self.assertEqual(json.loads(output.getvalue())["status"],"DESCRIBE_ONLY_NO_NATIVE_OR_INPUT_READ")

    def test_explicit_execution_rejects_windows_before_any_import_or_input(self):
        argv=["nav","--execute","--target-plan","NO_READ","--target-plan-sha256","a",
              "--registration","NO_READ","--registration-sha256","b","--output-directory","NO_WRITE"]
        with patch.object(sys,"platform","win32"),patch.object(p,"fixed_module",side_effect=AssertionError("no import")):
            with self.assertRaisesRegex(ValueError,"native UAVHumble22"):
                p.main(argv)

    def test_native_execute_also_requires_exact_reviewed_producer_sha_before_helper(self):
        argv=["nav","--execute","--reviewed-source-sha256","WRONG_SOURCE",
              "--target-plan","NO_READ","--target-plan-sha256","a",
              "--registration","NO_READ","--registration-sha256","b","--output-directory","NO_WRITE"]
        with patch.object(sys,"platform","linux"),patch.dict(p.os.environ,{"WSL_DISTRO_NAME":"UAVHumble22"}), \
             patch.object(p,"fixed_module",side_effect=AssertionError("no import")):
            with self.assertRaisesRegex(ValueError,"root-reviewed producer SHA"):
                p.main(argv)

    def test_exact_nav28_serial_execution_schema_and_original_validator_both_modes(self):
        for mode in ("PROBE","EXTENSION_PROBE"):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp,patch("sys.stdout",new_callable=io.StringIO):
                b,t,r,tb,o,invoke,calls,planned=self.nav_fixture(tmp,mode=mode)
                state=p.run_navigation(b,t,r,tb,o,invoke=invoke)
                self.assertTrue(state["status"].startswith("COMPLETED_ALL28_"))
                self.assertEqual([argv for argv,_ in calls["invocations"]],[x["command"] for x in planned])
                self.assertEqual(len(calls["validator"]),1);self.assertEqual(len(calls["snapshots"]),1)
                self.assertEqual(state["not_attempted"],[]);self.assertFalse(state["formal_admission"])
                self.assertEqual(p.load(planned[0]["report"]),{"engineering_status":"FAIL","identity":None})
                self.assertEqual(p.load(o/"terminal.json"),state)

    def test_conflicting_sidecar_stops_before_any_child_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            b,t,r,tb,o,invoke,calls,planned=self.nav_fixture(tmp)
            sidecar=p.report_paths(planned[0]["report"])[2];sidecar.write_bytes(b"preexisting evidence")
            state=p.run_navigation(b,t,r,tb,o,invoke=invoke)
            self.assertEqual(state["status"],"ERROR");self.assertEqual(calls["invocations"],[])
            self.assertEqual(sidecar.read_bytes(),b"preexisting evidence")
            self.assertFalse((o/"navigation_complete.json").exists());self.assertEqual(len(state["not_attempted"]),28)

    def test_failed_evaluator_keeps_real_exit_partial_report_and_never_retries(self):
        with tempfile.TemporaryDirectory() as tmp,patch("sys.stdout",new_callable=io.StringIO):
            b,t,r,tb,o,invoke,calls,planned=self.nav_fixture(tmp)
            def fail_second(*args):
                value=invoke(*args)
                if len(calls["invocations"]) == 2:
                    value.update(returncode=2,error="actual incomplete evaluation")
                return value
            state=p.run_navigation(b,t,r,tb,o,invoke=fail_second)
            self.assertEqual(state["status"],"ERROR");self.assertEqual(state["attempted"],2)
            self.assertEqual(state["executions"][-1]["execution"]["returncode"],2)
            self.assertEqual(len(state["not_attempted"]),26);self.assertEqual(calls["validator"],[])
            self.assertTrue(Path(planned[1]["report"]).is_file());self.assertFalse((o/"navigation_complete.json").exists())

    def test_original_validator_rejection_retains_complete_candidate_but_terminal_error(self):
        with tempfile.TemporaryDirectory() as tmp,patch("sys.stdout",new_callable=io.StringIO):
            b,t,r,tb,o,invoke,calls,planned=self.nav_fixture(tmp,reject_validator=True)
            state=p.run_navigation(b,t,r,tb,o,invoke=invoke)
            self.assertEqual(state["status"],"ERROR");self.assertEqual(state["attempted"],28)
            self.assertEqual(len(calls["validator"]),1);self.assertNotIn("completion",state)
            self.assertTrue((o/"navigation_complete.json").is_file())
            self.assertIn("ORIGINAL_VALIDATOR_REJECTED",state["error"])

    def test_input_mutation_stops_remaining_slots_and_original_source_output_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp,patch("sys.stdout",new_callable=io.StringIO):
            b,t,r,tb,o,invoke,calls,planned=self.nav_fixture(tmp)
            def mutate(*args):
                result=invoke(*args);Path(r["path"]).write_text("{}",encoding="utf-8");return result
            state=p.run_navigation(b,t,r,tb,o,invoke=mutate)
            self.assertEqual(state["status"],"ERROR");self.assertEqual(state["attempted"],1)
        with tempfile.TemporaryDirectory() as tmp:
            b,t,r,tb,o,invoke,calls,planned=self.nav_fixture(tmp)
            frozen=Path(tmp).resolve()/"original_frozen";frozen.mkdir()
            with self.assertRaisesRegex(ValueError,"external"):
                p.run_navigation(b,t,r,tb,frozen/"new_output",invoke=invoke)
            self.assertFalse((frozen/"new_output").exists())

    def sensor_fixture(self,tmp,*,incomplete=False):
        root=Path(tmp).resolve()
        source=put(root/"original_matrix/plan.json",{"frozen_root":str(root/"original_frozen"),"trials":[]})
        contract={"source_plan":source,"dev_slots":[{"slot_id":str(i)} for i in range(4)]}
        contract_binding=put(root/"input/contract.json",contract)
        module=root/"input/module.py";module.write_text("# SYNTHETIC SOURCE NEVER EXECUTED\n",encoding="utf-8")
        module_binding=p.bound(module)
        manifest_binding=put(root/"input/manifest.json",{"slots":[{"slot_id":str(i)} for i in range(4)]})
        target={"mode":"EXTENSION_PROBE","frozen_root":str(root/"final"),
                "protocol":{"sensor":{"contract":contract_binding,"module":module_binding}}}
        target_binding=put(root/"input/target.json",target)
        result={"status":"INCOMPLETE" if incomplete else "NOT_APPLICABLE","errors":["real insufficiency"] if incomplete else [],
            "missing_slot_ids":[],"per_slot":[{"slot_id":str(i),"status":"NOT_APPLICABLE","original_status":"FAIL",
                                               "identity":None} for i in range(4)],"known_algorithm_failures":["retained"]}
        calls=[]
        def evaluate(path,actual_contract):
            calls.append(("api",path,deepcopy(actual_contract)))
            self.assertEqual(path,Path(manifest_binding["path"]));self.assertEqual(actual_contract,contract)
            return deepcopy(result)
        def loader(path,digest,name):
            calls.append(("loader",path,digest));self.assertEqual((path,digest),(str(module),module_binding["sha256"]))
            return types.SimpleNamespace(evaluate_development_manifest=evaluate)
        def runner(actual,path,plans):
            calls.append(("runner",path));self.assertEqual(actual,target);self.assertEqual(plans,[source["path"]])
            return {str(i):{} for i in range(4)},{"path":manifest_binding["path"],"sha256":manifest_binding["sha256"]}
        v4=types.SimpleNamespace(SENSOR_INPUT_EVIDENCE_FIELD="sensor",read_sensor_input_evidence_manifest=runner)
        builder=types.SimpleNamespace(v4=v4,target_snapshot=lambda path,**kwargs:(path,deepcopy(target),{}))
        return builder,target,target_binding,contract_binding,manifest_binding,root/"output",loader,calls,result

    def test_sensor_uses_exact_bound_module_contract_and_original_api_preserves_fail_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            b,t,tb,c,m,o,loader,calls,result=self.sensor_fixture(tmp)
            before={str(path):p.sha(path) for path in Path(tmp).rglob("*") if path.is_file()}
            state=p.run_sensor(b,t,tb,c,m,o,module_loader=loader)
            self.assertTrue(state["status"].startswith("COMPLETED_SENSOR4_"))
            self.assertEqual([call[0] for call in calls],["loader","api","runner"])
            self.assertEqual(p.load(o/"sensor4_api_report.json"),result)
            self.assertEqual(state["original_api_status"],"NOT_APPLICABLE")
            self.assertFalse(state["formal_admission"]);self.assertFalse(state["image_review_created"])
            for path,digest in before.items():self.assertEqual(p.sha(path),digest)
            self.assertEqual(sorted(path.name for path in o.iterdir()),["sensor4_api_report.json","sensor4_runner_binding.json","terminal.json"])

    def test_incomplete_sensor_report_is_retained_and_runner_never_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            b,t,tb,c,m,o,loader,calls,result=self.sensor_fixture(tmp,incomplete=True)
            state=p.run_sensor(b,t,tb,c,m,o,module_loader=loader)
            self.assertEqual(state["status"],"ERROR");self.assertEqual(p.load(o/"sensor4_api_report.json"),result)
            self.assertEqual([x[0] for x in calls],["loader","api"])
            self.assertFalse((o/"sensor4_runner_binding.json").exists())

    def test_sensor_substitute_contract_refused_before_import_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            b,t,tb,c,m,o,loader,calls,result=self.sensor_fixture(tmp)
            substitute=put(Path(tmp).resolve()/"input/substitute.json",p.load(c["path"]))
            with self.assertRaisesRegex(ValueError,"exact contract"):
                p.run_sensor(b,t,tb,substitute,m,o,module_loader=loader)
            self.assertEqual(calls,[]);self.assertFalse(o.exists())

    def test_adopted_reaper_never_consumes_direct_popen_status(self):
        pgid=900;ours=123
        rows=[{"pid":pgid,"ppid":ours,"state":"Z"}, {"pid":901,"ppid":ours,"state":"Z"},
              {"pid":902,"ppid":999,"state":"Z"},{"pid":903,"ppid":ours,"state":"R"}]
        with patch.object(p,"process_group",return_value=rows),patch.object(p.os,"getpid",return_value=ours), \
             patch.object(p.os,"WNOHANG",1,create=True),patch.object(p.os,"waitpid",create=True) as waitpid:
            p.reap_group(pgid)
            waitpid.assert_called_once_with(901,p.os.WNOHANG)

    def test_metadata_acquisition_fault_still_cleans_and_waits_same_child_preserving_failure(self):
        class Child:
            pid=900
            returncode=None
            waits=0
            def poll(self):
                raise AssertionError("Unidentified child must remain unreaped until final owned wait")
            def wait(self,timeout):
                self.waits+=1;self.returncode=-9;return self.returncode
        child=Child();calls=0;clock=iter(range(0,500,20))
        def groups(pgid):
            nonlocal calls
            calls+=1
            if calls == 1:raise OSError("synthetic initial /proc failure")
            return [] if child.returncode is not None else [{"pid":900,"ppid":123,"state":"Z","start_ticks":12}]
        fake_signal=types.SimpleNamespace(SIGINT=2,SIGTERM=15,SIGKILL=9,SIG_IGN=1,signal=lambda *args:None)
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,"signal",fake_signal), \
             patch.object(p,"process_group",side_effect=groups),patch.object(p.subprocess,"Popen",return_value=child) as popen, \
             patch.object(p.os,"killpg",create=True) as killpg,patch.object(p.time,"monotonic",side_effect=lambda:next(clock)):
            result=p.run_command(["EXACT_FAKE_ARGV_NEVER_EXECUTED"],Path(tmp)/"child.log",1800.0)
        self.assertEqual(popen.call_count,1);self.assertEqual(child.waits,1)
        self.assertEqual(killpg.call_args_list[0].args,(900,15));self.assertEqual(killpg.call_args_list[1].args,(900,9))
        self.assertIn("synthetic initial /proc failure",result["error"])
        self.assertEqual(result["returncode"],-9);self.assertFalse(result["cleanup"]["identity_acquired"])
        self.assertEqual(result["cleanup"]["remaining_group_members"],[])

    def test_cleanup_final_scan_fault_keeps_actual_direct_exit_and_blocks_success(self):
        class Child:
            pid=900
            returncode=None
            waits=0
            def poll(self):return self.returncode
            def wait(self,timeout):
                self.waits+=1;self.returncode=0;return 0
        child=Child();calls=0
        def groups(pgid):
            nonlocal calls
            calls+=1
            if calls == 1:return [{"pid":900,"ppid":123,"state":"R","start_ticks":12}]
            if calls in {2,3}:return []
            raise OSError("synthetic final group inspection failure")
        fake_signal=types.SimpleNamespace(SIGINT=2,SIGTERM=15,SIGKILL=9,SIG_IGN=1,signal=lambda *args:None)
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,"signal",fake_signal), \
             patch.object(p,"process_group",side_effect=groups),patch.object(p.subprocess,"Popen",return_value=child):
            result=p.run_command(["EXACT_FAKE_ARGV_NEVER_EXECUTED"],Path(tmp)/"child.log",1800.0)
        self.assertEqual(child.waits,2);self.assertEqual(result["returncode"],0)
        self.assertEqual(result["error"],"Owned cleanup failed")
        self.assertIn("synthetic final group inspection failure",result["cleanup_error"])


if __name__ == "__main__":
    unittest.main()
