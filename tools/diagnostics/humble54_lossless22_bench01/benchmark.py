"""Prepared fixed T1 level19/22 benchmark; default describe performs no work.

Reuse the completed humble25 benchmark's child/time/RSS/wait/cleanup primitives.
Only an explicit reviewed --execute in an idle native UAVHumble22 may read the
two immutable source archives. No production policy, owner, trigger or admission.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import subprocess
import sys
import time
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "sources.json"
OUTPUT = Path("/mnt/d/WSL/UAVHumble22-validation/humble54_lossless22_bench01")
OLD = Path("/mnt/d/WSL/UAVHumble22-validation/humble25_archive_threads_benchmark02.py")
OLD_SHA = "baca7d2447907a84a9c1cc38f19c7588177db0ff6af5c8c4b31185c16a0fdfb0"
GUARD = ROOT / "tools/staging/final55_offline_overlay_20261103/stage.py"
GUARD_SHA = "25a88f5ba369c918c5d891828b5e2434c61f75f33eb5485749f1ec0fda632268"
HOST_PYTHON = Path("/mnt/c/Program Files/Python312/python.exe")
GIB = 1024**3
BUDGET_S = 900.0
PROFILES = (("zstd19_long27_T1", ("-T1", "-19", "--long=27", "--check")),
            ("zstd22_long27_T1", ("-T1", "--ultra", "-22", "--long=27", "--check")))
MEMORY_START_BYTES = 5 * GIB
MEMORY_FLOOR_BYTES = 2 * GIB
GROUP_RSS_LIMIT_BYTES = 3 * GIB
HOST_DISK_RESERVE_BYTES = 22 * GIB


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(value, excluded=()):
    return hashlib.sha256(json.dumps({k:v for k,v in value.items() if k not in excluded},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def fixed_module(path, expected):
    raw = Path(path).read_bytes()
    require(len(raw) < 2 * 1024**2 and hashlib.sha256(raw).hexdigest() == expected,
            "Reviewed helper source differs: " + str(path))
    module = types.ModuleType("lossless22_" + Path(path).stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def specification():
    return {"status": "PREPARED_NOT_EXECUTED_NO_COMPRESSOR_OR_BAG_READ",
        "sources_manifest": str(MANIFEST), "sources_manifest_sha256": sha(MANIFEST),
        "profiles": {name:list(args) for name,args in PROFILES},
        "fixed_source_order": ["car_stage1_velocity_seed004", "car_extension_depth_noise_seed004"],
        "candidate_budget_s_including_all_validation": BUDGET_S,
        "original_owned_cleanup_grace_s": {"TERM":10,"KILL":5},
        "fresh_external_output": str(OUTPUT),
        "source_method": "Original compressed archive decode stdout then encode; not direct ext4 production timing.",
        "memory": {"start_host_and_guest_bytes_each": MEMORY_START_BYTES,
                   "running_host_and_guest_floor_bytes_each": MEMORY_FLOOR_BYTES,
                   "actual_sampled_owned_group_rss_limit_bytes": GROUP_RSS_LIMIT_BYTES,
                   "host_query_interval_s": 2, "group_sampling_interval_s": 0.2},
        "disk": {"unchanged_fixed_host_reserve_bytes": HOST_DISK_RESERVE_BYTES,
                 "additional_start_reservation": "3 * sum(exact original raw byte counts); assumes no compression saving"},
        "requires": ["explicit --execute and reviewed driver/manifest SHA", "original held SITL lock and native idle guard",
                     "actual host/guest resource preflight", "fresh output", "exact original small and archive bindings"],
        "automatic_retry": False, "automatic_owner_or_next_job": False,
        "policy_or_old_archive_changed": False, "full280_and_original_reserves_changed": False,
        "proven_candidate_saving_bytes": 0, "formal_admission": False}


def resource_gate(sample, *, start=False):
    minimum = MEMORY_START_BYTES if start else MEMORY_FLOOR_BYTES
    for label,value in (("guest",sample.get("available_memory_bytes")),
                        ("host",sample.get("host",{}).get("host_available_memory_bytes"))):
        require(type(value) is int and value >= minimum, label + " memory absent/below fixed actual admission floor")
    require(type(sample.get("actual_group_rss_bytes")) is int
            and sample["actual_group_rss_bytes"] <= GROUP_RSS_LIMIT_BYTES,
            "Observed simultaneous owned group RSS exceeds fixed cap")
    free = sample["host"].get("D_volume", {}).get("bytes_available")
    require(type(free) is int and free >= HOST_DISK_RESERVE_BYTES,
            "Host D free absent/below unchanged 22 GiB fixed reserve")


def own_tree_bytes(root):
    # Only the fresh benchmark tree. Native cache hardlinks are counted once.
    seen, logical, allocated = set(), 0, 0
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        stat = path.stat()
        identity = stat.st_dev, stat.st_ino
        if identity not in seen:
            logical += stat.st_size
            allocated += getattr(stat, "st_blocks", 0) * 512
            seen.add(identity)
    return {"logical_unique_inode_bytes":logical, "allocated_unique_inode_bytes":allocated}


class Resources:
    def __init__(self, old, output):
        self.old, self.output = old, output
        self.original_sample = old.sample
        self.host = None
        self.host_time = -float("inf")
        self.querying = False
        self.number = 0
        self.tree = {"logical_unique_inode_bytes":0,"allocated_unique_inode_bytes":0}
        self.tree_time = time.monotonic()

    def __call__(self, label, processes):
        self.original_sample(label, processes)
        row = self.old.SAMPLES[-1]
        row["benchmark_tree"] = self.tree
        row["guest_root_available_bytes"] = shutil.disk_usage("/root").free
        if self.querying:
            return
        if time.monotonic() - self.host_time >= 2:
            self.querying = True
            self.number += 1
            destination = self.output / ("host_snapshot_%05d.json" % self.number)
            try:
                helper = str(HERE / "host_resources.py")
                require(helper.startswith("/mnt/d/"), "Host helper must stay in the reviewed D workspace")
                windows_helper = "D:\\" + helper[len("/mnt/d/"):].replace("/", "\\")
                with destination.open("xb") as handle:
                    child = self.old.launch([str(HOST_PYTHON), "-B", windows_helper, "--query"],
                        self.output, "host_query_%05d" % self.number, stdout=handle)
                    self.old.await_group([child], time.monotonic() + 10, "host_metadata_query")
                self.host = load(destination)
                self.host_time = time.monotonic()
                self.tree = own_tree_bytes(self.output)
                self.tree_time = time.monotonic()
            finally:
                self.querying = False
        row["host"] = self.host
        row["benchmark_tree"] = self.tree
        row["benchmark_tree_sample_age_s"] = time.monotonic() - self.tree_time
        row["host_sample_age_s"] = time.monotonic() - self.host_time
        resource_gate(row)


def source_binding(source, old):
    for binding in source["small_inputs"]:
        old.check(binding["path"], binding["sha256"])
    plan, terminal = load(source["plan"]), load(source["terminal"])
    require(digest(plan, ("plan_sha256",)) == plan["plan_sha256"]
            and digest(terminal, ("record_sha256",)) == terminal["record_sha256"]
            and terminal["plan_sha256"] == plan["plan_sha256"], "Original plan/terminal canonical digest differs")
    trial = [row for row in plan["trials"] if row["id"] == source["id"]]
    require(len(trial) == 1 and trial[0]["directory"] == source["original_run_directory"]
            and trial[0]["name"] == source["name"]
            and str(PurePosixPath(plan["results_root"]) / trial[0]["name"]) == source["published_directory"],
            "Source ID and publication path must come from the exact original plan")
    require(terminal["id"] == source["id"] and terminal["name"] == source["name"]
            and terminal["status"] == source["original_status"]
            and terminal["engineering_result"] == source["original_status"]
            and terminal["execution_status"] == "COMPLETED" and terminal["infrastructure_stop"] is False
            and terminal["flight_exit_code"] == 0 and terminal["cleanup"]["residual_processes"] == [],
            "Original source must be independently closed; its verdict is retained")
    directory = Path(source["published_directory"])
    archive = load(directory / "bag_integrity.json")
    require(archive["status"] == "PASS" and load(directory / "recording_closure.json")["status"] == "PASS"
            and archive["raw_validation"] == source["raw_validation"]
            and archive["compressed_files"] == source["compressed_files"]
            and archive["native_reader_validation"]["full_stream_read"] is True
            and archive["native_reader_validation"]["topic_counts"] == archive["raw_validation"]["topic_counts"]
            and archive["native_reader_validation"]["message_count"] == archive["raw_validation"]["message_count"],
            "Exact original full recording/native denominator differs")
    for relative in ("bag_integrity.json", "recording_closure.json", "run_config.json", "rosbag/metadata.yaml"):
        require(terminal["artifact_hashes"][relative] == old.sha(directory / relative),
                "Published source differs from original terminal artifact binding")
    require(len(archive["compressed_files"]) == len(archive["raw_validation"]["files"]) == 1,
            "This fixed minimal benchmark requires each complete source to have one storage file")
    item, raw = archive["compressed_files"][0], archive["raw_validation"]["files"][0]
    require(PurePosixPath(item["path"]).name == item["path"] and item["raw_sha256"] == raw["sha256"]
            and item["raw_bytes"] == raw["bytes"] and item["zstd_test"] == "PASS", "Raw/archive receipt mismatch")
    path = directory / "rosbag" / item["path"]
    require(not path.is_symlink() and path.stat().st_size == item["bytes"], "Original archive size/path differs")
    old.check(path, item["sha256"])
    return {"archive":str(path), "archive_sha256":item["sha256"], "archive_stat":old.stat(path),
            "raw_sha256":raw["sha256"], "raw_bytes":raw["bytes"], "raw_validation":source["raw_validation"]}


NATIVE_PROGRAM = r'''
from collections import Counter
import hashlib,json,sys
from pathlib import Path
sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'scripts')]
from evaluate_stage1_flight import open_bag_reader
import rosbag2_py
bag,expected_path,result_path,cache=map(Path,sys.argv[2:6])
expected=json.loads(expected_path.read_text());counts=Counter()
with open_bag_reader(bag,rosbag2_py) as (reader,evidence):
    while reader.has_next():
        topic,_,_=reader.read_next();counts[topic]+=1
    if dict(counts)!=expected['topic_counts'] or sum(counts.values())!=expected['message_count']:
        raise ValueError('Complete native per-topic/message denominator differs')
    files=list(cache.glob('stage1_bag_read_*/*.db3'))
    if len(files)!=1 or len(expected['files'])!=1:
        raise ValueError('Exactly one complete native decoded SQLite is required')
    decoded=files[0];wanted=expected['files'][0];h=hashlib.sha256();size=0
    with decoded.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block);size+=len(block)
    if decoded.name!=wanted['path'] or size!=wanted['bytes'] or h.hexdigest()!=wanted['sha256']:
        raise ValueError('Native decoded exact raw byte count/SHA differs')
    native_raw={'bytes':size,'sha256':h.hexdigest()}
if list(cache.iterdir()):raise ValueError('Native private cache was not cleaned')
with result_path.open('x') as stream:
    json.dump({'status':'PASS','full_stream_read':True,'message_count':sum(counts.values()),
        'topic_counts':dict(counts),'native_decoded_raw':native_raw,'reader_evidence':evidence,
        'rosbag2_py_path':str(rosbag2_py.__file__)},stream,indent=2)
'''


def one_candidate(old, source, binding, profile, arguments):
    name = source["id"] + "__" + profile
    directory = OUTPUT / name
    directory.mkdir()
    began = time.monotonic()
    deadline = began + BUDGET_S
    result = {"status":"ERROR", "source_id":source["id"], "profile":profile,
              "encoder_arguments":list(arguments), "budget_s":BUDGET_S, "started_utc":utc(),
              "original_source":binding, "original_engineering_status":source["original_status"]}
    old.write(directory / "started.json", result)
    def timeout(_number, _frame):
        raise TimeoutError("Unchanged 900s total candidate budget exhausted: " + name)
    handler = signal.signal(signal.SIGALRM, timeout)
    timer = signal.setitimer(signal.ITIMER_REAL, BUDGET_S)
    if timer != (0.0, 0.0):
        signal.setitimer(signal.ITIMER_REAL,*timer)
        signal.signal(signal.SIGALRM,handler)
        raise RuntimeError("An existing real timer may not be replaced")
    try:
        candidate = directory / "candidate.db3.zstd"
        with candidate.open("xb") as output:
            decoder = old.launch([old.ZSTD,"--decompress","--long=27","--stdout","-q",binding["archive"]], directory,
                                 "compress_decode", stdout=subprocess.PIPE)
            try:
                encoder = old.launch([old.ZSTD,*arguments,"-q","--stdout"], directory, "compress_encode",
                                     stdin=decoder.stdout, stdout=output)
            finally:
                decoder.stdout.close()
            compression = old.await_group([decoder,encoder], deadline, name + "_compression")
        checker = old.launch([old.ZSTD,"--test","--long=27","-q",str(candidate)],directory,"cli_test",stdout=subprocess.DEVNULL)
        cli = old.await_group([checker], deadline, name + "_cli_test")
        decoded = directory / "decoded_sha.json"
        decoder = old.launch([old.ZSTD,"--decompress","--long=27","--stdout","-q",str(candidate)],directory,"verify_decode",stdout=subprocess.PIPE)
        try:
            hasher = old.launch([sys.executable,"-B","-c",old.HASH_PROGRAM,str(decoded)],directory,"verify_hash",stdin=decoder.stdout,stdout=subprocess.DEVNULL)
        finally:
            decoder.stdout.close()
        roundtrip = old.await_group([decoder,hasher], deadline, name + "_raw_roundtrip")
        expected_raw = {"bytes":binding["raw_bytes"],"sha256":binding["raw_sha256"]}
        require(load(decoded) == expected_raw, "Exact CLI decoded raw SHA/bytes differ")
        bag = directory / "native_bag"
        bag.mkdir()
        shutil.copy2(Path(source["published_directory"]) / "rosbag/metadata.yaml", bag / "metadata.yaml")
        require(old.sha(bag / "metadata.yaml") == source["metadata_sha256"], "Copied native metadata differs")
        os.link(candidate, bag / source["compressed_files"][0]["path"])
        expected = directory / "expected_raw_validation.json"
        old.write(expected, binding["raw_validation"])
        cache = directory / "native_cache"
        cache.mkdir()
        native_result = directory / "native_full_reader.json"
        child = old.launch([sys.executable,"-B","-c",NATIVE_PROGRAM,source["frozen_root"],str(bag),str(expected),str(native_result),str(cache)],
            directory,"native_reader",stdout=subprocess.DEVNULL,env={"TMPDIR":str(cache)})
        native = old.await_group([child], deadline, name + "_native_full_reader")
        proof = load(native_result)
        require(proof["status"] == "PASS" and proof["native_decoded_raw"] == expected_raw
                and proof["message_count"] == binding["raw_validation"]["message_count"]
                and proof["topic_counts"] == binding["raw_validation"]["topic_counts"] and not list(cache.iterdir()),
                "Native full stream/raw/cache proof differs")
        result.update(status="BYTE_AND_NATIVE_VALIDATED",candidate_path=str(candidate),candidate_bytes=candidate.stat().st_size,
            candidate_sha256=old.sha(candidate),compression=compression,cli_test=cli,raw_roundtrip=roundtrip,
            decoded_raw_proof=load(decoded),native=native,native_proof=proof)
    except BaseException as error:
        result.update(error_type=type(error).__name__,error=repr(error))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,handler)
        result.update(finished_utc=utc(),total_wall_s=time.monotonic()-began,
            actual_group_sample_peak_rss_bytes=max((row["actual_group_rss_bytes"] for row in old.SAMPLES if row["phase"].startswith(name)),default=0))
        old.write(directory / "result.json",result)
    return result


def execute(reviewed_source_sha, reviewed_manifest_sha):
    require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22",
            "Explicit native UAVHumble22 only; this tool never launches WSL")
    require(sha(__file__) == reviewed_source_sha and sha(MANIFEST) == reviewed_manifest_sha,
            "Exact reviewed driver and source manifest are required")
    require(not OUTPUT.exists() and not OUTPUT.is_symlink() and OUTPUT.parent.is_dir(),
            "Single fresh external output required; no overwrite or retry")
    manifest = load(MANIFEST)
    require(manifest["proven_candidate_saving_bytes"] == 0 and len(manifest["sources"]) == 2,
            "Prepared evidence cannot claim unmeasured savings")
    old = fixed_module(OLD,OLD_SHA)
    guard = fixed_module(GUARD,GUARD_SHA)
    with guard.linux_idle_guard() as idle:
        OUTPUT.mkdir()
        old.OUTPUT = OUTPUT
        old.sample = Resources(old,OUTPUT)
        state = {"status":"ERROR", "started_utc":utc(), "idle_guard":idle,
                 "reports":[], "formal_capacity_gate_passed":False,
                 "source_sha256":reviewed_source_sha,"sources_manifest_sha256":reviewed_manifest_sha,
                 "production_policy_changed":False,"proven_candidate_saving_bytes":0}
        old.write(OUTPUT / "started.json", {**state,"specification":specification()})
        handlers = {}
        def interrupted(number, _frame):
            raise InterruptedError("Signal " + str(number))
        try:
            for number in (signal.SIGINT,signal.SIGTERM):
                handlers[number] = signal.signal(number,interrupted)
            import ctypes
            require(ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0) == 0,
                    "Original child subreaper requirement failed")
            for item in manifest["helper_inputs"]:
                old.check(item["path"],item["sha256"])
            require(old.CANDIDATE_BUDGET_S == BUDGET_S, "Original 900s candidate budget changed")
            require(HOST_PYTHON.is_file() and Path(old.ZSTD).is_file() and Path(old.TIME).is_file(),
                    "Fixed actual native/host tools are unavailable")
            state["tool_bindings"] = {str(p):old.sha(p) for p in (HOST_PYTHON,Path(old.ZSTD),Path(old.TIME))}
            state["zstd_version"] = subprocess.check_output([old.ZSTD,"--version"],text=True,timeout=5).strip()
            old.sample("preflight",[])
            preflight = next(row for row in old.SAMPLES if row["phase"] == "preflight")
            resource_gate(preflight,start=True)
            raw_total = sum(source["raw_validation"]["files"][0]["bytes"] for source in manifest["sources"])
            require(preflight["host"]["D_volume"]["bytes_available"] >= HOST_DISK_RESERVE_BYTES + 3 * raw_total,
                    "Actual host free cannot hold conservative raw-size-based outputs/cache plus unchanged reserve")
            bindings = []
            state["source_bindings"] = bindings
            for source in manifest["sources"]:
                bindings.append(source_binding(source,old))
            for source,binding in zip(manifest["sources"],bindings):
                for profile,arguments in PROFILES:
                    old.sample("candidate_preflight",[])
                    resource_gate(next(row for row in reversed(old.SAMPLES) if row["phase"] == "candidate_preflight"),start=True)
                    state["reports"].append(one_candidate(old,source,binding,profile,arguments))
            for source,binding in zip(manifest["sources"],bindings):
                after = source_binding(source,old)
                require(after == binding,"Original source stat/SHA/denominators changed during benchmark")
            require(sha(__file__) == reviewed_source_sha and sha(MANIFEST) == reviewed_manifest_sha,
                    "Benchmark reviewed source changed")
            for item in manifest["helper_inputs"]:
                old.check(item["path"],item["sha256"])
            state["paired_observed_bytes"] = [{"source_id":source["id"],
                "baseline_bytes":state["reports"][2*i]["candidate_bytes"],
                "candidate_bytes":state["reports"][2*i+1]["candidate_bytes"],
                "difference_bytes":state["reports"][2*i]["candidate_bytes"]-state["reports"][2*i+1]["candidate_bytes"]}
                for i,source in enumerate(manifest["sources"])]
            state.update(status="COMPLETED_TWO_SOURCES_TWO_FIXED_LEVELS_NO_POLICY_CHANGE",original_preserved=True)
        except BaseException as error:
            state.update(error_type=type(error).__name__,error=repr(error))
            raise
        finally:
            active_error = sys.exc_info()[1]
            for number in handlers:
                signal.signal(number,signal.SIG_IGN)
            try:
                cleanup_errors=[]
                for child in old.OWNED:
                    try:
                        old.cleanup([child],"final_owned_group_confirmation")
                    except BaseException as error:
                        cleanup_errors.append(repr(error))
                if cleanup_errors:
                    state.update(status="ERROR",cleanup_errors=cleanup_errors)
                preservation=[]
                for source,binding in zip(manifest["sources"],state.get("source_bindings",[])):
                    try:
                        path=Path(binding["archive"])
                        observed={"stat":old.stat(path),"sha256":old.sha(path)}
                        unchanged=(observed["stat"]==binding["archive_stat"]
                                   and observed["sha256"]==binding["archive_sha256"])
                        for item in source["small_inputs"]:
                            old.check(item["path"],item["sha256"])
                        preservation.append({"source_id":source["id"],"unchanged":unchanged,"observed":observed})
                    except BaseException as error:
                        preservation.append({"source_id":source["id"],"unchanged":False,"error":repr(error)})
                state["source_preservation_after"]=preservation
                preservation_failed=any(row["unchanged"] is not True for row in preservation)
                if preservation_failed:
                    state.update(status="ERROR",original_preserved=False)
                state["candidate_outcomes"] = {source["id"] + "__" + profile:
                    load(OUTPUT/(source["id"]+"__"+profile)/"result.json")
                    if (OUTPUT/(source["id"]+"__"+profile)/"result.json").is_file() else {"status":"NOT_ATTEMPTED"}
                    for source in manifest["sources"] for profile,_ in PROFILES}
                state.update(finished_utc=utc(),steps=old.STEPS,cleanup=old.CLEANUP,
                    residual_processes=[row for child in old.OWNED for row in old.members(child.pid)])
                host_rows=[row for row in old.SAMPLES if "host" in row]
                state["sampled_resource_summary"]={
                    "actual_group_rss_peak_bytes":max((row["actual_group_rss_bytes"] for row in old.SAMPLES),default=0),
                    "fresh_benchmark_tree_peak_logical_bytes":max((row.get("benchmark_tree",{}).get("logical_unique_inode_bytes",0) for row in old.SAMPLES),default=0),
                    "host_available_memory_min_bytes":min((row["host"]["host_available_memory_bytes"] for row in host_rows),default=None),
                    "guest_available_memory_min_bytes":min((row["available_memory_bytes"] for row in old.SAMPLES),default=None),
                    "vhd_peak_logical_bytes":max((row["host"]["vhd"]["logical_bytes"] for row in host_rows),default=None),
                    "vhd_peak_allocated_bytes":max((row["host"]["vhd"]["allocated_bytes"] for row in host_rows),default=None),
                    "scope":"Periodic observations, not a guarantee of unobserved instantaneous peaks; no production spool is created."}
                old.write(OUTPUT / "resources.json",old.SAMPLES)
                state["resources_sha256"]=old.sha(OUTPUT / "resources.json")
                old.write(OUTPUT / "terminal.json",state)
                if (cleanup_errors or preservation_failed) and active_error is None:
                    raise RuntimeError("Owned cleanup/source preservation failure retained in terminal")
            finally:
                for number,handler in handlers.items():
                    signal.signal(number,handler)
    return state


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--reviewed-source-sha256")
    parser.add_argument("--reviewed-manifest-sha256")
    args=parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(specification(),indent=2))
        return 0
    require(args.reviewed_source_sha256 and args.reviewed_manifest_sha256,
            "--execute requires both exact root-reviewed SHA bindings")
    execute(args.reviewed_source_sha256,args.reviewed_manifest_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
