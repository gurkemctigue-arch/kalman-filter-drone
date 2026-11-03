"""Small Windows-safe fixtures. No WSL, compressor, ROS, source bag or model."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("prepared_lossless22", Path(__file__).with_name("benchmark.py"))
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


class PreparedBenchmarkTests(unittest.TestCase):
    def test_default_describes_without_loading_native_helper_or_executing(self):
        with patch.object(bench,"execute",side_effect=AssertionError("execute forbidden")), \
             patch.object(bench,"fixed_module",side_effect=AssertionError("helper import forbidden")), \
             patch("sys.stdout",new_callable=io.StringIO) as output:
            self.assertEqual(bench.main([]),0)
        result=json.loads(output.getvalue())
        self.assertEqual(result["proven_candidate_saving_bytes"],0)
        self.assertEqual(result["candidate_budget_s_including_all_validation"],900)
        self.assertEqual(result["profiles"]["zstd19_long27_T1"],["-T1","-19","--long=27","--check"])
        self.assertEqual(result["profiles"]["zstd22_long27_T1"],["-T1","--ultra","-22","--long=27","--check"])
        self.assertEqual(result["disk"]["unchanged_fixed_host_reserve_bytes"],22*bench.GIB)

    def test_execution_requires_explicit_reviewed_inputs_and_native_environment(self):
        with self.assertRaisesRegex(ValueError,"both exact root-reviewed"):
            bench.main(["--execute"])
        with patch.object(sys,"platform","win32"), patch.object(bench,"fixed_module",side_effect=AssertionError("no import")):
            with self.assertRaisesRegex(ValueError,"native UAVHumble22"):
                bench.execute("a"*64,"b"*64)

    def test_actual_resource_gate_rejects_unknown_low_memory_rss_and_reserve(self):
        valid={"available_memory_bytes":6*bench.GIB,"actual_group_rss_bytes":bench.GIB,
               "host":{"host_available_memory_bytes":6*bench.GIB,"D_volume":{"bytes_available":60*bench.GIB}}}
        bench.resource_gate(valid,start=True)
        for place,key,value in [("guest","available_memory_bytes",None),("guest","available_memory_bytes",True),
            ("guest","available_memory_bytes",bench.GIB),("host","host_available_memory_bytes",None),
            ("host","host_available_memory_bytes",bench.GIB),("guest","actual_group_rss_bytes",3*bench.GIB+1),
            ("disk","bytes_available",22*bench.GIB-1)]:
            changed=deepcopy(valid)
            container=changed if place=="guest" else changed["host"] if place=="host" else changed["host"]["D_volume"]
            container[key]=value
            with self.subTest(place=place,key=key,value=value),self.assertRaises(ValueError):
                bench.resource_gate(changed)
        changed=deepcopy(valid)
        changed["available_memory_bytes"]=4*bench.GIB
        bench.resource_gate(changed)
        with self.assertRaises(ValueError):
            bench.resource_gate(changed,start=True)

    def test_fixed_sources_match_original_small_plan_and_terminal_bindings(self):
        manifest=bench.load(bench.MANIFEST)
        self.assertEqual([row["id"] for row in manifest["sources"]],
                         ["car_stage1_velocity_seed004","car_extension_depth_noise_seed004"])
        for source in manifest["sources"]:
            host_dir=bench.ROOT/"results/frozen_fullplan_v4_humble54"/source["name"]
            small={Path(row["path"]).name:row for row in source["small_inputs"]}
            matrix=bench.ROOT/"results/frozen_fullplan_v4_humble54"/Path(source["plan"]).parent.name
            plan=bench.load(matrix/"plan.json")
            terminal=bench.load(matrix/"slots"/(source["id"]+".json"))
            self.assertEqual(bench.digest(plan,("plan_sha256",)),plan["plan_sha256"])
            self.assertEqual(bench.digest(terminal,("record_sha256",)),terminal["record_sha256"])
            trial=next(row for row in plan["trials"] if row["id"]==source["id"])
            self.assertEqual(source["original_run_directory"],trial["directory"])
            self.assertEqual(source["published_directory"],plan["results_root"]+"/"+trial["name"])
            self.assertEqual(bench.sha(matrix/"plan.json"),small["plan.json"]["sha256"])
            self.assertEqual(bench.sha(matrix/"slots"/(source["id"]+".json")),small[source["id"]+".json"]["sha256"])
            self.assertEqual(terminal["status"],source["original_status"])
            self.assertEqual(terminal["execution_status"],"COMPLETED")
            self.assertFalse(terminal["infrastructure_stop"])
            self.assertEqual(terminal["cleanup"]["residual_processes"],[])
            integrity=bench.load(host_dir/"bag_integrity.json")
            self.assertEqual(source["raw_validation"],integrity["raw_validation"])
            self.assertEqual(source["compressed_files"],integrity["compressed_files"])
            self.assertEqual(source["raw_validation"]["topic_counts"],integrity["native_reader_validation"]["topic_counts"])
            for relative in ("bag_integrity.json","recording_closure.json","run_config.json","rosbag/metadata.yaml"):
                self.assertEqual(bench.sha(host_dir/relative),terminal["artifact_hashes"][relative])

    def native_fixture(self, tmp, *, changed_count=False, changed_raw=False):
        root=Path(tmp);cache=root/"cache";cache.mkdir()
        payload=b"synthetic SQLite bytes, never a real ROS bag"
        expected={"message_count":3,"topic_counts":{"/a":1,"/b":2},
                  "files":[{"path":"fixture.db3","bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()}]}
        if changed_count:
            expected["topic_counts"]["/b"]=1
        if changed_raw:
            expected["files"][0]["sha256"]="0"*64
        expected_path=root/"expected.json";expected_path.write_text(json.dumps(expected),encoding="utf-8")
        class Reader:
            def __init__(self):self.rows=iter([("/a",b"1",0),("/b",b"2",1),("/b",b"3",2)]);self.left=3
            def has_next(self):return self.left>0
            def read_next(self):self.left-=1;return next(self.rows)
        @contextmanager
        def open_reader(*args):
            with tempfile.TemporaryDirectory(dir=cache,prefix="stage1_bag_read_") as decoded:
                (Path(decoded)/"fixture.db3").write_bytes(payload)
                yield Reader(),{"reader":"FAKE_ONLY"}
        evaluate=types.ModuleType("evaluate_stage1_flight");evaluate.open_bag_reader=open_reader
        rosbag=types.ModuleType("rosbag2_py");rosbag.__file__="FAKE_NO_NATIVE_LIBRARY"
        output=root/"native.json"
        with patch.dict(sys.modules,{"evaluate_stage1_flight":evaluate,"rosbag2_py":rosbag}), \
             patch.object(sys,"argv",["fake","fake_frozen",str(root/"bag"),str(expected_path),str(output),str(cache)]), \
             patch.object(sys,"path",list(sys.path)):
            exec(compile(bench.NATIVE_PROGRAM,"prepared_native_program_fixture","exec"),{})
        return json.loads(output.read_text(encoding="utf-8"))

    def test_native_program_requires_full_topics_and_exact_decoded_bytes_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=self.native_fixture(tmp)
            self.assertEqual(result["message_count"],3)
            self.assertEqual(result["topic_counts"],{"/a":1,"/b":2})
            self.assertTrue(result["full_stream_read"])
            self.assertEqual(result["status"],"PASS")
        for changed in ({"changed_count":True},{"changed_raw":True}):
            with tempfile.TemporaryDirectory() as tmp,self.subTest(changed=changed),self.assertRaises(ValueError):
                self.native_fixture(tmp,**changed)

    def candidate_fixture(self,tmp,*,fail=False):
        root=Path(tmp);published=root/"published";(published/"rosbag").mkdir(parents=True)
        metadata=published/"rosbag/metadata.yaml";metadata.write_text("synthetic metadata only",encoding="utf-8")
        output=root/"fresh";output.mkdir()
        raw={"bytes":123,"sha256":"a"*64}
        source={"id":"fixture_car","published_directory":str(published),"frozen_root":"FAKE_NOT_IMPORTED",
                "metadata_sha256":bench.sha(metadata),"compressed_files":[{"path":"fixture.db3.zstd"}],"original_status":"FAIL"}
        binding={"archive":"FAKE_NOT_READ","raw_bytes":raw["bytes"],"raw_sha256":raw["sha256"],
                 "raw_validation":{"message_count":3,"topic_counts":{"/a":1,"/b":2}}}
        calls=[]
        class Old:
            ZSTD="FAKE_ZSTD_NOT_EXECUTED"
            HASH_PROGRAM="FAKE_HASH_PROGRAM_NOT_EXECUTED"
            SAMPLES=[]
            sha=staticmethod(bench.sha)
            @staticmethod
            def write(path,value):
                with path.open("x",encoding="utf-8") as handle:json.dump(value,handle)
            @staticmethod
            def launch(argv,directory,label,**kwargs):
                calls.append((label,argv))
                if label=="compress_encode":kwargs["stdout"].write(b"synthetic archive fixture")
                elif label=="verify_hash":Old.write(Path(argv[-1]),raw)
                elif label=="native_reader":
                    Old.write(Path(argv[-2]),{"status":"PASS","native_decoded_raw":raw,
                        "message_count":3,"topic_counts":{"/a":1,"/b":2}})
                return types.SimpleNamespace(stdout=io.BytesIO())
            @staticmethod
            def await_group(children,deadline,label):
                if fail and label.endswith("_cli_test"):raise TimeoutError("fixture total candidate timeout")
                return {"wall_s":0.0,"returncodes":[0]*len(children),"groups_clean":True}
        fake_signal=types.SimpleNamespace(SIGALRM=14,ITIMER_REAL=0,
            signal=lambda *args:None,setitimer=lambda *args:(0.0,0.0))
        with patch.object(bench,"OUTPUT",output),patch.object(bench,"signal",fake_signal):
            if fail:
                with self.assertRaises(TimeoutError):
                    bench.one_candidate(Old,source,binding,*bench.PROFILES[1])
                result=bench.load(output/"fixture_car__zstd22_long27_T1/result.json")
            else:
                result=bench.one_candidate(Old,source,binding,*bench.PROFILES[1])
        return result,calls,output

    def test_candidate_uses_exact_level22_commands_and_preserves_original_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,calls,output=self.candidate_fixture(tmp)
            encoder=next(argv for label,argv in calls if label=="compress_encode")
            self.assertEqual(encoder,["FAKE_ZSTD_NOT_EXECUTED","-T1","--ultra","-22","--long=27","--check","-q","--stdout"])
            self.assertEqual(result["status"],"BYTE_AND_NATIVE_VALIDATED")
            self.assertEqual(result["original_engineering_status"],"FAIL")
            self.assertEqual(result["budget_s"],900)
            self.assertTrue((output/"fixture_car__zstd22_long27_T1/candidate.db3.zstd").is_file())

    def test_failed_candidate_retains_output_and_error_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,calls,output=self.candidate_fixture(tmp,fail=True)
            self.assertEqual(result["status"],"ERROR")
            self.assertEqual(result["error_type"],"TimeoutError")
            self.assertEqual(result["budget_s"],900)
            self.assertEqual(sum(label=="compress_encode" for label,_ in calls),1)
            self.assertTrue((output/"fixture_car__zstd22_long27_T1/candidate.db3.zstd").is_file())


if __name__ == "__main__":
    unittest.main()
