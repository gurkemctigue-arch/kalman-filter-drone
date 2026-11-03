"""Small source/synthetic metadata contracts; no native, model or bag work."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("after07_stage_contracts", HERE / "stage_after07.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class PreparedStageContracts(unittest.TestCase):
    def test_disabled_entry_does_not_read_or_prepare(self):
        with patch.object(s, "fixed_module", side_effect=AssertionError("No file read")), redirect_stdout(io.StringIO()):
            self.assertEqual(s.main([]), 0)
            self.assertEqual(s.main(["--execute"]), 2)
            with self.assertRaisesRegex(ValueError, "Production disabled"):
                s.run_registered(execute_requested=True)
        self.assertFalse(s.PRODUCTION_ENABLED)
        self.assertEqual(s.REGISTERED_INPUTS, {})

    def test_actual_profile_contract_and_ten_candidate_payloads_match_pins(self):
        base, prior = s.fixed_module(s.BASE, s.BASE_SHA), s.fixed_module(s.PRIOR, s.PRIOR_SHA)
        profile, bundle = s.candidate_inputs(base, prior)
        self.assertEqual(len(profile["overlays"]), 10)
        changed = {row[0] for row, old in zip(profile["overlays"], base.OVERLAYS) if tuple(row[3:]) != old[3:]}
        self.assertEqual(changed, {row["path"] for row in bundle["after_pins_requiring_update"]})
        self.assertEqual(len(changed), 4)
        self.assertEqual([row[:3] for row in profile["overlays"]], [list(row[:3]) for row in base.OVERLAYS])
        self.assertEqual((profile["source_count"], profile["scanner_count"], profile["flight_count"]), (308,185,277))
        self.assertEqual(profile["module_sha"], "aca8932895eb44361265347164f5cd62fe427ccb61907c5844309162b33a7ffc")
        self.assertEqual(s.production_paths(prior)["final"], Path("/root/uav_tracking_fullplan_v4_final55"))
        self.assertIn("after07_01", str(s.production_paths(prior)["stage"]))

    def test_only_actual_audit_creation_time_may_differ(self):
        original = {"created_utc":"2020-01-01T00:00:00+00:00", "status":"SYNTHETIC", "closed_ids":["slot"], "original_status":"FAIL"}
        fresh = deepcopy(original); fresh["created_utc"] = "2020-01-01T00:00:01+00:00"
        self.assertEqual(s.stable_audit(original),s.stable_audit(fresh))
        fresh["original_status"] = "PASS"
        self.assertNotEqual(s.stable_audit(original),s.stable_audit(fresh))

    def fixture(self, root):
        root = Path(root); receipt = root / "receipt"; receipt.mkdir()
        for name in ("measurement.py","budget.json","closure.json"):
            (root / name).write_text("SYNTHETIC INERT METADATA",encoding="utf8")
        source={"path":str(root/"measurement.py"),"sha256":"a"*64}
        budget={"path":str(root/"budget.json"),"sha256":"b"*64}
        closure={"path":str(root/"closure.json"),"sha256":"c"*64}
        measurement=SimpleNamespace(SCOPE="SYNTHETIC",ROOT=root,REGISTERED_INPUTS={"only":"SYNTHETIC"})
        old=SimpleNamespace(COMMIT="fixture",TOOL_PINS={"tools/tool.py":"f"*64},
                            workflow_commands=lambda p:[(label,["NO_EXECUTION",label]) for label in ("measure_actual28","physical_inventory","person_velocity_export","car_velocity_export","R0_candidate","full280_budget")])
        old.TOOL_PINS={"tools/tool"+str(index)+".py":"f"*64 for index in range(5)}
        p={"receipt":receipt,"idle":root/"idle.sh"}
        expected=[("native_idle",["bash",p["idle"]])]+[("tool_"+str(index),["git","-C",root,"show","fixture:"+relative]) for index,relative in enumerate(old.TOOL_PINS)]+old.workflow_commands(p)
        begin=datetime(2020,1,1,tzinfo=timezone.utc)
        guard={"machine_lock":"/fixture/lock","blockers":[]}
        terminal={"scope":"SYNTHETIC","status":"COMPLETED_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION","returncode":0,
                  "errors":[],"interruptions":[],"automatic_retry":False,"formal_admission":False,"commit":"fixture","guard":guard,
                  "source":source,"actual_original_bindings":measurement.REGISTERED_INPUTS,"owner_identity":{"pid":1},
                  "started_utc":begin.isoformat(),"finished_utc":(begin+timedelta(seconds=40)).isoformat(),
                  "input_bindings":[source,budget,closure],"closure_audit":closure,"steps":[]}
        for index,(label,argv) in enumerate(expected):
            row={"id":label,"command":list(map(str,argv)),"returncode":0,"pid":index+2,"identity":{"pid":index+2},
                 "started_utc":(begin+timedelta(seconds=index*2+1)).isoformat(),"finished_utc":(begin+timedelta(seconds=index*2+2)).isoformat()}
            for channel in ("stdout","stderr"):
                path=receipt/(label+"."+channel+".log");path.write_text("SYNTHETIC",encoding="utf8");row[channel]=str(path)
            terminal["steps"].append(row)
        inputs=SimpleNamespace(bound=Mock())
        v=SimpleNamespace(local_path=lambda path:Path(path),linux_identity=lambda identity:None,
                          timestamp=lambda value,now:datetime.fromisoformat(value))
        return terminal,measurement,old,p,source,budget,inputs,v,guard,begin+timedelta(seconds=50)

    def test_completed_terminal_requires_every_original_step_and_budget_binding(self):
        with tempfile.TemporaryDirectory() as root:
            args=self.fixture(root)
            result=s.validate_terminal(*args)
            self.assertEqual(result["closed_steps"],12)
            self.assertEqual(len(result["workflow_steps"]),6)
            self.assertEqual(args[6].bound.call_count,3)

    def test_zero_exit_cannot_hide_missing_command_nonzero_step_guard_or_budget(self):
        mutations=[lambda t:t["steps"].pop(),
                   lambda t:t["steps"][6].update(command=["WRONG"]),
                   lambda t:t["steps"][6].update(returncode=2),
                   lambda t:t.update(guard={}),
                   lambda t:t.update(input_bindings=[t["source"],t["closure_audit"]]),
                   lambda t:t.update(status="STOPPED_DIRECT_MEASUREMENT_PARTIAL_OUTPUTS_RETAINED"),
                   lambda t:t["steps"][6].update(started_utc=t["started_utc"])]
        for mutation in mutations:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as root:
                args=self.fixture(root);mutation(args[0])
                with self.assertRaises(ValueError):s.validate_terminal(*args)


if __name__=="__main__":
    unittest.main(verbosity=2)
