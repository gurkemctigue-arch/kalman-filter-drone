"""Temporary tiny synthetic sources only; no real model, bag, WSL or native job."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("final55_staging_fixture", Path(__file__).with_name("stage.py"))
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@contextmanager
def inert_idle_guard():
    yield {"scope":"SYNTHETIC_FIXTURE_ONLY_NO_MACHINE_LOCK_OR_NATIVE_PROBE"}


def fixture(root):
    source, overlay, store, external = (root / name for name in ("source", "overlay", "original_results", "external"))
    for path in (source, overlay, store, external):
        path.mkdir()
    runner = b"# SYNTHETIC INERT SOURCE; never imported or executed.\nHASH_FOLDERS=('scripts','uav_tracking','config','models')\nHASH_SUFFIXES={'.py','.sh','.json','.pt'}\nOFFLINE_HELPERS={'scripts/build_reliability_v4_probe_gate.py'}\n"
    overlays = []
    for name,old_bytes,old_sha,new_bytes,new_sha in s.OVERLAYS:
        old = runner if name == s.RUNNER else ("# OLD SYNTHETIC: " + name + "\n").encode()
        new = old + b"# NEW SYNTHETIC FIXTURE ONLY\n"
        if old_sha is not None:
            put(source / name, old)
            before = (len(old), hashlib.sha256(old).hexdigest())
        else:
            before = (None,None)
        put(overlay / name, new)
        overlays.append((name,*before,len(new),hashlib.sha256(new).hexdigest()))
    for name in s.EXCLUDED17:
        put(source / name, ("# GENERATED SYNTHETIC: " + name + "\n").encode())
    put(source / "uav_tracking/flight.py", b"# SYNTHETIC FLIGHT SOURCE; no callable algorithm\n")
    put(source / "models/inert_fixture.pt", b"SYNTHETIC INERT BYTES; NOT A MODEL\n")
    public = "\n".join("rsync --exclude='" + value + "'" for value in s.FILTERS)
    put(source / "scripts/freeze_full_plan_workspace.sh", public.encode())
    for name in ("dds", "ros_gz", "clock", "magnetic", "libraries"):
        write(source / ("config/" + name + ".json"), {"scope":"SYNTHETIC_RUNTIME_FIXTURE_ONLY", "name":name})
    navigation = {"status":"REGISTERED", "scope":"SYNTHETIC_NUMERIC_GATES_ONLY"}
    for name in s.PLANNING:
        write(source / name, {"status":"DRAFT_NOT_FROZEN_NOT_EXECUTED", "registration_utc":None,
            "navigation_acceptance":navigation, "unchanged_science":"SYNTHETIC_FIXTURE"})
    emulated_link = False
    try:
        os.symlink(store, source / "results", target_is_directory=True)
    except OSError:
        # Windows has no symlink privilege here. Only the OS link boundary is
        # replaced in portable tests; production continues to reject this tree.
        emulated_link = True
        store = source / "results"
        store.mkdir()
    full = s.file_map(source)
    full.pop("results",None)
    rules = s.runner_rules(source / s.RUNNER)
    source_hashes = s.source_map(full,rules)
    plans = []
    for mode,name,groups in (("PROBE","core",("v","p","cross","mid","active","multi")),
            ("EXTENSION_PROBE","extension",("depth_noise","depth_holes","dropout","latency","combined","speed_v","speed_p","far"))):
        trials = []
        for cls in ("person","car"):
            for group in groups:
                slot = cls + "_" + group
                trials.append({"id":slot, "name":slot, "target_class":cls, "extension_condition":group,
                    "flight_command":["SYNTHETIC_NO_COMMAND_EXECUTION",slot]})
        plan = {"mode":mode, "frozen_root":str(source), "output":str(source / "results" / name),
            "selected_seeds":[4], "trials":trials, "source_hashes":source_hashes,
            "model_hashes":{key:value for key,value in source_hashes.items() if key.endswith(".pt")},
            "protocol":{"navigation_acceptance":navigation}}
        plan["plan_sha256"] = s.digest(plan)
        plan_path = store / name / "plan.json"
        write(plan_path,plan)
        for trial in trials:
            row = {"id":trial["id"], "plan_sha256":plan["plan_sha256"], "status":"PASS", "execution_status":"COMPLETED",
                "infrastructure_stop":False, "flight_exit_code":0, "cleanup":{"residual_processes":[]},
                "finished_utc":"2020-01-01T00:00:00+00:00",
                "commands":[{"kind":"flight","command":trial["flight_command"],"returncode":0,"error":None}]}
            row["record_sha256"] = s.digest(row)
            write(store / name / "slots" / (trial["id"] + ".json"),row)
        plans.append((plan,plan_path))
    full_path = store / "freeze_validation/source_integrity/source_before.json"
    write(full_path,{"entries":full,"rsync_exclusions":s.FILTERS,"source":"SYNTHETIC_PRE_FREEZE_SOURCE"})
    research = store / "recorded_estimator_research/research_report.json"
    write(research,{"scope":"SYNTHETIC_INERT_RESEARCH_REPORT_ONLY"})
    cells = [{"slot_id":row["id"], "target_class":row["target_class"], "condition":row["extension_condition"]}
        for row in plans[1][0]["trials"] if row["extension_condition"] in {"dropout","combined"}]
    contract = {"schema_version":1,"revision":"sensor_input_interruption_v1","scope":s.SCOPE,
        "source_plan":s.binding(plans[1][1]),"dev_slots":cells}
    contract_path = external / "contract.json"
    write(contract_path,contract)
    profile = deepcopy(s.PROFILE)
    profile.update(scope="SYNTHETIC_FIXTURE_ONLY",emulated_results_boundary=emulated_link,overlays=tuple(overlays),full_sha=s.sha(full_path),full_count=len(full),
        source_count=len(source_hashes),scanner_count=len(s.scanner_map({k:v for k,v in full.items() if k not in s.EXCLUDED17})),
        flight_count=len(s.flight_map(source_hashes,rules)),model_count=1,source_digest=s.digest(source_hashes),
        module_sha=s.sha(overlay / s.OVERLAYS[-2][0]),contract_sha=s.sha(contract_path),contract_digest=s.digest(contract),research_sha=s.sha(research))
    for key,(plan,path) in zip(("core","extension"),plans):
        profile[key + "_sha"] = s.sha(path)
        profile[key + "_digest"] = plan["plan_sha256"]
    expected_source = dict(source_hashes)
    for name,_,_,_,new_sha in overlays:
        if name in expected_source:
            expected_source[name] = new_sha
    expected_scanner = s.scanner_map({k:v for k,v in full.items() if k not in s.EXCLUDED17})
    for name,value in expected_source.items():
        if name in expected_scanner:
            expected_scanner[name] = value
    profile.update(overlay_source_digest=s.digest(expected_source),overlay_scanner_digest=s.digest(expected_scanner))
    paths = {"source":source,"overlay":overlay,"stage":root / "new_stage","final":root / "future_cold_root",
        "receipt":root / "new_receipts","core":plans[0][1],"extension":plans[1][1],"full":full_path,
        "module":overlay / s.OVERLAYS[-2][0],"contract":contract_path}
    return paths,profile


def invoke(paths,profile,execute=False):
    def fixture_results_boundary(source,expected_store):
        assert Path(source) / "results" == expected_store
        return s.file_map(source), {"kind":"symlink","target":str(expected_store)}
    boundary = patch.object(s,"source_snapshot",side_effect=fixture_results_boundary) if profile.get("emulated_results_boundary") else nullcontext()
    with boundary:
        return s.run(paths,execute_requested=execute,profile=profile,idle_guard=inert_idle_guard)


class StagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.paths,self.profile = fixture(self.root)

    def run_driver(self, execute=False):
        return invoke(self.paths,self.profile,execute)

    def test_default_is_read_only_and_never_imports_fixture_sources(self):
        before = s.file_map(self.root)
        result = self.run_driver()
        self.assertEqual(result["status"],"PREFLIGHT_ONLY_NO_WRITES")
        self.assertEqual(s.file_map(self.root),before)
        self.assertTrue(all(not self.paths[key].exists() for key in ("stage","final","receipt")))
        self.assertEqual(result["descriptor"]["evidence_basis"],s.BASIS)

    def test_execute_copies_only_registered_baseline_overlays_exactly_and_retains_receipts(self):
        original = s.file_map(self.paths["source"])
        put(self.paths["overlay"] / "scripts/UNREGISTERED_WORKSPACE_FILE.py",b"MUST NOT BE COPIED")
        result = self.run_driver(True)
        self.assertEqual(result["status"],"PASS_STAGING_ONLY_NOT_COLD_OR_ADMISSION")
        stage = self.paths["stage"]
        self.assertFalse((stage / "scripts/UNREGISTERED_WORKSPACE_FILE.py").exists())
        self.assertTrue((stage / "results").is_dir())
        self.assertFalse((stage / "results").is_symlink())
        self.assertFalse(self.paths["final"].exists())
        self.assertFalse(any(name.startswith(s.NESTED) for name in s.file_map(stage)))
        main = s.load(stage / s.MAIN)
        before = s.load(self.paths["source"] / s.MAIN)
        self.assertEqual({k:v for k,v in main.items() if k != s.FIELD},before)
        self.assertEqual(main[s.FIELD]["source_plan"],s.binding(self.paths["extension"]))
        self.assertEqual(s.file_map(self.paths["source"]),original)
        receipt = self.paths["receipt"]
        self.assertEqual(s.load(receipt / "actual_overlay_complete_map.json")["entries"],s.file_map(stage))
        self.assertEqual(s.load(receipt / "actual_flight_hashes.json")["entries"],s.flight_map(s.load(receipt / "actual_source_hashes.json")["entries"],s.runner_rules(stage / s.RUNNER)))
        with self.assertRaises(s.Refused):
            self.run_driver(True)

    def test_changed_small_source_terminal_or_contract_fails_before_any_output(self):
        cases = ("overlay","original","extra","nested_extra","contract","terminal","open_flight","interrupted")
        for defect in cases:
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as tmp:
                paths,profile = fixture(Path(tmp).resolve())
                if defect == "overlay":put(paths["overlay"] / s.RUNNER,b"UNREVIEWED")
                elif defect == "original":put(paths["source"] / "uav_tracking/flight.py",b"CHANGED")
                elif defect == "extra":put(paths["source"] / "scripts/extra.py",b"EXTRA")
                elif defect == "nested_extra":put(paths["source"] / (s.NESTED[0] + "unregistered.py"),b"EXTRA")
                elif defect == "contract":put(paths["contract"],b"{}")
                else:
                    plan = s.load(paths["core"])
                    record = Path(plan["output"]) / "slots" / (plan["trials"][0]["id"] + ".json")
                    row = s.load(record)
                    if defect == "terminal":row["flight_exit_code"] = False
                    elif defect == "interrupted":row["status"] = "INTERRUPTED"
                    else:row["cleanup"]["residual_processes"] = ["SYNTHETIC_RUNNING_OWNER"]
                    row["record_sha256"] = s.digest(row,("record_sha256",))
                    write(record,row)
                with self.assertRaises(s.Refused):
                    invoke(paths,profile,True)
                self.assertTrue(all(not paths[key].exists() for key in ("stage","final","receipt")))

    def test_rejects_output_overlap_and_existing_paths(self):
        for key,value in (("stage",self.paths["source"] / "new_stage"), ("receipt",self.paths["core"].parent.parent / "receipt"),
                          ("final",self.paths["overlay"] / "future")):
            paths = dict(self.paths); paths[key] = value
            with self.subTest(key=key),self.assertRaises(s.Refused):
                invoke(paths,self.profile)
        self.paths["stage"].mkdir()
        with self.assertRaises(s.Refused):self.run_driver(True)
        self.assertFalse(self.paths["receipt"].exists())

    def test_real_source_boundary_rejects_an_ordinary_results_directory(self):
        if not self.profile.get("emulated_results_boundary"):
            ordinary = self.root / "ordinary_source"
            ordinary.mkdir()
            (ordinary / "results").mkdir()
            source,store = ordinary,ordinary / "results"
        else:source,store = self.paths["source"],self.paths["core"].parent.parent
        with self.assertRaisesRegex(s.Refused,"results link/store differs"):
            s.source_snapshot(source,store)

    def test_closed_original_failure_is_preserved_and_does_not_become_engineering_pass(self):
        plan = s.load(self.paths["core"])
        record = Path(plan["output"]) / "slots" / (plan["trials"][0]["id"] + ".json")
        row = s.load(record)
        row["status"] = "INCOMPLETE_EVIDENCE"
        row["record_sha256"] = s.digest(row,("record_sha256",))
        write(record,row)
        before = s.sha(record)
        self.assertEqual(self.run_driver(True)["status"],"PASS_STAGING_ONLY_NOT_COLD_OR_ADMISSION")
        self.assertEqual(s.sha(record),before)
        self.assertEqual(s.load(record)["status"],"INCOMPLETE_EVIDENCE")

    def test_new_classifier_cannot_hide_a_flight_source_by_expanding_offline_helpers(self):
        runner = self.paths["overlay"] / s.RUNNER
        payload = runner.read_bytes() + b"OFFLINE_HELPERS.add('uav_tracking/flight.py')\n"
        runner.write_bytes(payload)
        profile = deepcopy(self.profile)
        profile["overlays"] = tuple((name,old_size,old_sha,len(payload),hashlib.sha256(payload).hexdigest())
            if name == s.RUNNER else (name,old_size,old_sha,new_size,new_sha)
            for name,old_size,old_sha,new_size,new_sha in profile["overlays"])
        with self.assertRaisesRegex(s.Refused,"classification/scanner rules"):
            invoke(self.paths,profile,True)
        self.assertFalse(self.paths["stage"].exists())
    def test_extra_file_created_during_copy_is_not_hidden_by_matching_source_counts(self):
        actual_copy = s.shutil.copy2
        inserted = False
        def inject(source,destination,**kwargs):
            nonlocal inserted
            result = actual_copy(source,destination,**kwargs)
            if not inserted:
                inserted = True
                put(self.paths["stage"] / "scripts/unregistered.py",b"SYNTHETIC_CONCURRENT_EXTRA")
            return result
        with patch.object(s.shutil,"copy2",side_effect=inject),self.assertRaises(s.Refused):
            self.run_driver(True)
        self.assertTrue(self.paths["stage"].exists())
        self.assertEqual(s.load(self.paths["receipt"] / "outcome.json")["status"],"FAIL_STAGING_ATTEMPT_RETAINED")

    def test_external_source_change_during_copy_fails_and_keeps_attempt(self):
        actual_copy = s.shutil.copy2
        changed = False
        def inject(source,destination,**kwargs):
            nonlocal changed
            result = actual_copy(source,destination,**kwargs)
            if not changed:
                changed = True
                put(self.paths["source"] / "uav_tracking/flight.py",b"SYNTHETIC_EXTERNAL_CONCURRENT_SOURCE_CHANGE")
            return result
        with patch.object(s.shutil,"copy2",side_effect=inject),self.assertRaises(s.Refused):
            self.run_driver(True)
        self.assertTrue(self.paths["stage"].exists())
        self.assertEqual(s.load(self.paths["receipt"] / "outcome.json")["status"],"FAIL_STAGING_ATTEMPT_RETAINED")


class ProcessIdentityTests(unittest.TestCase):
    def test_harmonic_nodes_collectors_and_heavy_evaluators_block(self):
        cases = (("/usr/bin/gz-sim-server",), ("/usr/bin/gz-sim-gui",), ("/usr/bin/px4",),
            ("python","/tmp/collect_remaining_slots.py"), ("python","/tmp/collector04.py"),
            ("bash","/tmp/native_owner.sh"), ("python","/tmp/evaluate_navigation_reference.py"),
            ("python","/tmp/extract_short_window.py"), ("/usr/bin/ros2","launch","fixture.launch.py"),
            ("/usr/bin/ros2","bag","record"), ("/usr/bin/colcon","build"), ("/usr/bin/gz","sim"),
            ("python","/root/fixture/install/lib/uav_tracking_nodes/controller"))
        for argv in cases:
            with self.subTest(argv=argv):self.assertTrue(s.native_blocker(list(argv),"R"))
        self.assertTrue(s.native_blocker(["/usr/bin/ruby"],"R","gz-sim-server"))
        self.assertFalse(s.native_blocker(["/usr/bin/gz-sim-server"],"Z","gz-sim-server"))
        self.assertFalse(s.native_blocker(["python","/tmp/stage.py"],"R"))
        self.assertFalse(s.native_blocker([],"S","kworker"))


if __name__ == "__main__":
    unittest.main()
