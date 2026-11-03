"""Independent bounded Windows source/fixture review; never run native work."""
from __future__ import annotations

import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
BENCH = ROOT / "tools/diagnostics/humble54_lossless22_bench01"
HERE = Path(__file__).resolve().parent
READS = []


def read_small(path):
    path = Path(path)
    before = path.stat()
    assert path.is_file() and before.st_size <= 2 * 1024**2, str(path)
    raw = path.read_bytes()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert len(raw) == before.st_size
    READS.append({"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return raw


def host_path(path):
    if path.startswith("/mnt/d/"):
        return Path("D:/") / path[len("/mnt/d/"):]
    if path.startswith("/root/uav_tracking_fullplan_v4_humble54/"):
        return Path("//wsl.localhost/UAVHumble22") / path.lstrip("/")
    raise ValueError("Unapproved small input path: " + path)


def extract(raw, name, namespace):
    tree = ast.parse(raw.decode("utf-8-sig"), feature_version=(3, 10))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(selected) == 1, name
    exec(compile(ast.Module(body=selected, type_ignores=[]), "independent_extracted_" + name, "exec"), namespace)
    return namespace[name]


def require(value, message):
    if not value:
        raise ValueError(message)


def review_original_reader(raw):
    """Simulate the native plugin's sibling SQLite write using the actual wrapper."""
    with tempfile.TemporaryDirectory(prefix="independent_lossless22_") as directory:
        root = Path(directory)
        source = root / "original"
        source.mkdir()
        (source / "metadata.yaml").write_text("synthetic metadata, not a ROS recording", encoding="utf-8")
        archive = source / "fixture.db3.zstd"
        archive.write_bytes(b"SYNTHETIC_ARCHIVE_NEVER_DECODED")
        original = {path.name: path.read_bytes() for path in source.iterdir()}
        cache = root / "private_cache"
        cache.mkdir()
        opened = []

        class FakeCompressionReader:
            def open(self, storage, converter):
                uri = Path(storage.uri)
                assert uri.is_relative_to(cache)
                assert (uri / "fixture.db3.zstd").read_bytes() == original[archive.name]
                (uri / "fixture.db3").write_bytes(b"SYNTHETIC_DECODED_SQLITE")
                opened.append(uri)

        def forbidden_reader():
            raise AssertionError("Compressed metadata must select compression reader")

        metadata = types.SimpleNamespace(compression_format="zstd", compression_mode="FILE",
            storage_identifier="sqlite3", relative_file_paths=[archive.name])
        rosbag = types.SimpleNamespace(Info=lambda: types.SimpleNamespace(read_metadata=lambda *args: metadata),
            SequentialCompressionReader=FakeCompressionReader, SequentialReader=forbidden_reader,
            StorageOptions=lambda **kwargs: types.SimpleNamespace(**kwargs),
            ConverterOptions=lambda **kwargs: types.SimpleNamespace(**kwargs))
        namespace = {"contextmanager": contextmanager, "Path": Path, "shutil": shutil,
            "tempfile": types.SimpleNamespace(TemporaryDirectory=lambda **kwargs:
                tempfile.TemporaryDirectory(dir=cache, **kwargs)), "Any": object}
        reader = extract(raw, "open_bag_reader", namespace)
        with reader(source, rosbag) as (_, evidence):
            assert (opened[-1] / "fixture.db3").is_file()
            assert evidence["source_bag_read_only"] is True
            assert not (source / "fixture.db3").exists()
        assert not list(cache.iterdir())
        assert {path.name: path.read_bytes() for path in source.iterdir()} == original
        metadata.relative_file_paths = ["../../escape.zstd"]
        try:
            with reader(source, rosbag):
                raise AssertionError("Escaping metadata should not yield")
        except ValueError as error:
            assert "escapes" in str(error)
        else:
            raise AssertionError("Escaping metadata accepted")
        assert not list(cache.iterdir())
    return {"sibling_write_isolated": True, "source_bytes_unchanged": True,
            "private_cache_removed": True, "escaping_filename_rejected": True,
            "real_plugin_or_archive_used": False}


def review_lock(raw):
    events = []
    busy = [False]

    class FakeHandle:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def fileno(self): return 321

    class FakePath:
        def __init__(self, value): self.value = value
        def is_file(self): return True
        def is_symlink(self): return False
        def open(self, mode):
            assert mode == "rb"
            return FakeHandle()
        def iterdir(self):
            assert self.value == "/proc"
            return iter(())
        def __str__(self): return self.value

    fcntl = types.ModuleType("fcntl")
    fcntl.LOCK_EX, fcntl.LOCK_NB, fcntl.LOCK_UN = 1, 2, 8
    def flock(fd, flags):
        events.append((fd, flags))
        if busy[0] and flags != fcntl.LOCK_UN:
            raise BlockingIOError("synthetic original SITL owner")
    fcntl.flock = flock
    namespace = {"contextmanager": contextmanager, "require": require, "Refused": ValueError,
        "Path": FakePath, "json": json, "native_blocker": lambda *args: False,
        "os": types.SimpleNamespace(name="posix", environ={"WSL_DISTRO_NAME": "UAVHumble22"}, getpid=lambda: 123)}
    guard = extract(raw, "linux_idle_guard", namespace)
    with patch.dict(sys.modules, {"fcntl": fcntl}):
        try:
            with guard() as receipt:
                assert events == [(321, 3)] and receipt["blockers"] == []
                raise RuntimeError("synthetic candidate failure")
        except RuntimeError as error:
            assert str(error) == "synthetic candidate failure"
        assert events == [(321, 3), (321, 8)]
        busy[0] = True
        try:
            with guard():
                raise AssertionError("Busy original lock must not yield")
        except ValueError as error:
            assert "owns the machine lock" in str(error)
        else:
            raise AssertionError("Busy original lock accepted")
    return {"held_through_body": True, "unlocked_after_body_exception": True,
            "existing_busy_lock_rejected": True, "real_lock_or_proc_used": False}


def review_cleanup(raw):
    ticks, killed, events, receipts = [0.0], [False], [], []
    def killpg(pid, sig):
        events.append((pid, sig))
        if sig == 9:
            killed[0] = True
    class FakeProcess:
        pid, returncode = 707, None
        def poll(self):
            if killed[0]: self.returncode = -9
            return self.returncode
    def sleep(seconds): ticks[0] += seconds
    namespace = {"os": types.SimpleNamespace(killpg=killpg),
        "signal": types.SimpleNamespace(SIGTERM=15, SIGKILL=9),
        "time": types.SimpleNamespace(monotonic=lambda: ticks[0], sleep=sleep),
        "TERM_GRACE_S": 10.0, "KILL_GRACE_S": 5.0, "CLEANUP": receipts,
        "members": lambda pgid: [] if killed[0] else [{"pid": pgid, "pgid": pgid}],
        "reap_adopted": lambda: None}
    cleanup = extract(raw, "cleanup", namespace)
    cleanup([FakeProcess()], "independent_synthetic_escalation")
    assert events == [(707, 15), (707, 9)]
    assert receipts[0]["members_after"] == [] and receipts[0]["direct_returncode"] == -9
    assert 10 <= ticks[0] < 11
    caught = []
    step = {"pid": 808}
    class WaitingProcess:
        pid = 808
        def poll(self): return None
    def failed_sample(*args): raise ValueError("synthetic resource floor rejection")
    namespace = {"time": types.SimpleNamespace(monotonic=lambda: 0), "sample": failed_sample,
        "cleanup": lambda processes, reason: caught.append((processes[0].pid, reason)), "STEPS": [step],
        "utc": lambda: "SYNTHETIC_FIXTURE_UTC"}
    waiting = extract(raw, "await_group", namespace)
    try:
        waiting([WaitingProcess()], 900, "fixture_candidate")
    except ValueError as error:
        assert "resource floor" in str(error)
    else:
        raise AssertionError("Resource gate error must escape")
    assert caught == [(808, "phase_failure_fixture_candidate")]
    return {"term_then_kill_owned_group_only": True, "bounded_original_grace": True,
            "resource_error_calls_owned_cleanup": True, "real_signal_or_sleep_used": False}


def main():
    driver = read_small(BENCH / "benchmark.py")
    manifest_raw = read_small(BENCH / "sources.json")
    manifest = json.loads(manifest_raw)
    files_before = {}
    for name in ("benchmark.py", "host_resources.py", "run.sh", "test_benchmark.py", "sources.json", "README.md"):
        raw = read_small(BENCH / name)
        files_before[name] = hashlib.sha256(raw).hexdigest()
        if name.endswith(".py"):
            ast.parse(raw.decode("utf-8-sig"), feature_version=(3, 10))
    bindings, raw_by_source = [], {}
    history = manifest["historical_complete_benchmark"]
    selected = manifest["helper_inputs"] + [{"path": history["terminal"], "sha256": history["sha256"]}]
    for source in manifest["sources"]:
        selected += source["small_inputs"]
    seen = set()
    for item in selected:
        if item["path"] in seen: continue
        seen.add(item["path"])
        raw = read_small(host_path(item["path"]))
        actual = hashlib.sha256(raw).hexdigest()
        assert actual == item["sha256"], item["path"]
        bindings.append({"original_path": item["path"], "bytes": len(raw), "sha256": actual, "matched": True})
        raw_by_source[item["path"]] = raw
    reader_raw = raw_by_source["/root/uav_tracking_fullplan_v4_humble54/scripts/evaluate_stage1_flight.py"]
    guard_path = next(item["path"] for item in manifest["helper_inputs"] if item["path"].endswith("/stage.py"))
    old_path = next(item["path"] for item in manifest["helper_inputs"] if item["path"].endswith("humble25_archive_threads_benchmark02.py"))
    fixtures = {"actual_reader_wrapper_fake_plugin": review_original_reader(reader_raw),
        "actual_sitl_guard_fake_lock": review_lock(raw_by_source[guard_path]),
        "actual_owned_cleanup_fake_processes": review_cleanup(raw_by_source[old_path])}
    files_after = {name: hashlib.sha256((BENCH / name).read_bytes()).hexdigest() for name in files_before}
    assert files_before == files_after
    receipt = {
        "schema_version": 1, "status": "PASS_SOURCE_AND_SYNTHETIC_REVIEW_ONLY_NOT_NATIVE_EXECUTED",
        "created_utc": datetime.now(timezone.utc).isoformat(), "reviewer": "/root/continuation06_preparation",
        "reviewed_files": files_before, "reviewed_files_unchanged": True,
        "author_windows_tests_independently_observed": {"command": "python -B -m unittest discover -s tools/diagnostics/humble54_lossless22_bench01 -p test_benchmark.py -v", "run": 7, "passed": 7, "failed": 0, "errors": 0, "observed_wall_s": 0.165},
        "independent_fixtures": fixtures, "original_small_bindings": bindings,
        "source_review": {
            "archive_paths": "Original archives are only read/hashed; reader receives a fresh candidate link plus copied metadata. Actual wrapper then stages temporary hardlinks before sibling SQLite decode.",
            "paired_profiles": "Same exact original source per pair, T1/long27/check common; -19 compared with --ultra -22. Fixed source/profile order limits runtime inference.",
            "validation": "CLI test, full CLI decoded byte/SHA, native unfiltered all-topic/all-message counts, native decoded exact SQLite byte/SHA, candidate compressed SHA and final source stat/SHA; one 900s candidate alarm with original owned cleanup grace.",
            "resources": "Actual host/guest memory admission 5 GiB each, sampled running floor 2 GiB each and sampled owned group RSS cap 3 GiB. D reserve remains 22 GiB; start adds 3 times exact summed raw bytes. Metadata samples do not guarantee instantaneous peaks.",
            "locking_cleanup": "Existing original SITL lock held across all work; idle guard refuses native workloads; all owned groups are cleaned before context exits. Failed results retained, no retry/next owner.",
        },
        "nonblocking_findings": [],
        "resolved_findings": [{"id": "HOST_SAMPLE_INTERVAL_WORDING", "location": "README.md host snapshots paragraph", "detail": "The author corrected the earlier maximum-two-second claim before this review completed. Reviewed README now states a query is triggered about two seconds after previous completion, with its own ten-second timeout and no guaranteed maximum sample interval. Runtime source and manifest were unchanged."}],
        "blocking_findings": [],
        "execution_conclusion": "SOURCE_EXECUTABLE_ONLY_AFTER_ROOT_REVIEWED_SHA_AND_ACTUAL_COLLECTOR_EXIT_IDLE_LOCK_RESOURCE_ADMISSION; DO_NOT_EXECUTE_WHILE_COLLECTOR07_OWNS_NATIVE_MACHINE",
        "native_wsl_compressor_invocations": 0, "real_bag_archive_model_payload_reads": 0,
        "source_changes": 0, "production_policy_changes": 0, "proven_candidate_saving_bytes": 0,
        "formal_capacity_or_admission": False,
        "remaining_actual_checks": ["Root must confirm all collector/native evaluation children exited", "Actual native idle and held original lock", "Actual host/guest memory and fixed disk reserves", "Installed zstd and ROS native plugin compatibility", "All four complete candidate outcomes or preserved diagnostic failures"],
        "review_inputs": READS,
    }
    target = HERE / "independent_review01.json"
    target.write_text(json.dumps(receipt, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(target), "source_sha256": files_before["benchmark.py"],
        "manifest_sha256": files_before["sources.json"], "matched_unique_original_small_inputs": len(bindings),
        "independent_fixture_groups": len(fixtures), "blocking_findings": 0}, ensure_ascii=True))


if __name__ == "__main__":
    main()
