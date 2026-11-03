"""Independent small-source, synthetic-only pipeline review. No native launches."""
from __future__ import annotations

import argparse
import ast
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import types
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BENCH = ROOT / "tools/diagnostics/humble54_pipeline_timing_bench01"
FROZEN = "/root/uav_tracking_fullplan_v4_humble54"
PUBLISHED = ROOT / "results/frozen_fullplan_v4_humble54"
INPUTS = []


def small(path):
    path = Path(path)
    before = path.stat()
    assert path.is_file() and before.st_size <= 2 * 1024**2, str(path)
    raw = path.read_bytes()
    after = path.stat()
    assert len(raw) == before.st_size and (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    INPUTS.append({"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return raw


def mapped(path):
    assert "?" not in path and "\ufffd" not in path and "\\" not in path, path
    if path.startswith("/mnt/d/"):
        return Path("D:/") / path[len("/mnt/d/"):]
    if path.startswith(FROZEN + "/results/"):
        return PUBLISHED / path[len(FROZEN + "/results/"):]
    if path.startswith(FROZEN + "/"):
        assert not path.endswith((".pt", ".db3", ".zstd", ".mcap")), "payload reads prohibited"
        return Path("//wsl.localhost/UAVHumble22") / path.lstrip("/")
    raise ValueError("Unapproved original small source: " + path)


def pinned(item):
    path = mapped(item["path"])
    raw = small(path)
    assert hashlib.sha256(raw).hexdigest() == item["sha256"], item["path"]
    return raw


def content_digest(obj, excluded):
    return hashlib.sha256(json.dumps({k: v for k, v in obj.items() if k != excluded},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def original_bindings(config):
    mounted_root = "/mnt/d/" + ROOT.name
    assert config["original_plan"]["path"].startswith(mounted_root + "/results/")
    assert config["recording_terminal"]["path"].startswith(mounted_root + "/results/")
    assert config["probe"]["path"].startswith(mounted_root + "/tools/")
    plan = json.loads(pinned(config["original_plan"]))
    terminal = json.loads(pinned(config["recording_terminal"]))
    assert plan["frozen_root"] == config["source_root"] == FROZEN
    assert content_digest(plan, "plan_sha256") == plan["plan_sha256"]
    assert content_digest(terminal, "record_sha256") == terminal["record_sha256"]
    assert terminal["plan_sha256"] == plan["plan_sha256"]
    assert terminal["execution_status"] == "COMPLETED" and terminal["infrastructure_stop"] is False
    assert terminal["cleanup"]["residual_processes"] == []
    trial = next(row for row in plan["trials"] if row["id"] == terminal["id"])
    assert trial["name"] == terminal["name"]
    directory = PurePosixPath(trial["directory"])
    assert config["bag_uri"] == str(directory / "rosbag")
    published = PUBLISHED / trial["name"]
    integrity_raw = small(published / "bag_integrity.json")
    assert hashlib.sha256(integrity_raw).hexdigest() == terminal["artifact_hashes"]["bag_integrity.json"]
    integrity = json.loads(integrity_raw)
    assert integrity["status"] == integrity["native_reader_validation"]["status"] == "PASS"
    closure = small(published / "recording_closure.json")
    assert hashlib.sha256(closure).hexdigest() == terminal["artifact_hashes"]["recording_closure.json"]
    assert json.loads(closure)["status"] == "PASS"
    parameter_checks = []
    seen = set()
    for role, item in config["parameters"].items():
        relative = PurePosixPath(item["path"]).relative_to(directory).as_posix()
        assert terminal["artifact_hashes"][relative] == item["sha256"]
        if item["path"] not in seen:
            pinned(item)
            seen.add(item["path"])
        parameter_checks.append({"role": role, "original_path": item["path"], "sha256": item["sha256"]})
    model_relative = PurePosixPath(config["model"]["path"]).relative_to(FROZEN).as_posix()
    assert trial["model"] == model_relative
    assert plan["model_hashes"][model_relative] == config["model"]["sha256"]
    assert {PurePosixPath(row["path"]).name: row["sha256"] for row in config["bag_files"]} == {
        **{row["path"]: row["sha256"] for row in integrity["compressed_files"]},
        "metadata.yaml": integrity["published_metadata_sha256"],
    }
    metadata = next(row for row in config["bag_files"] if row["path"].endswith("/metadata.yaml"))
    assert terminal["artifact_hashes"]["rosbag/metadata.yaml"] == metadata["sha256"]
    pinned(metadata)
    pinned(config["probe"])
    source_paths = (
        "scripts/evaluate_stage1_flight.py",
        "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/detector_node.py",
        "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/state_estimator_node.py",
        "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/controller_node.py",
        "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/inference_worker.py",
        "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py",
        "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/adapter_node.py",
        "ros2_ws/src/uav_tracking_interfaces/msg/TrackingCommand.msg",
    )
    checked_sources = []
    for relative in source_paths:
        raw = pinned({"path": FROZEN + "/" + relative, "sha256": plan["source_hashes"][relative]})
        if relative.endswith(".py"):
            ast.parse(raw.decode("utf-8-sig"), feature_version=(3, 10))
        checked_sources.append(relative)
    return {"original_id": trial["id"], "terminal_status_retained": terminal["status"],
        "mounted_paths_question_mark_count": 0, "mounted_paths_exact_project_name": True,
        "parameters": parameter_checks, "original_source_pins_checked": checked_sources,
        "model_and_archive_sha": "Compared to original plan/integrity expectations only; no payload opened or rehashed"}


def extra_reducer_cases(tests):
    cases = []
    for phase in ("detection", "state", "command"):
        for mutation in ("missing_source", "typed_mismatch", "uncaptured_take"):
            events, _, _ = tests.fixture()
            take = next(row for row in events if row["kind"] == "take" and row["phase"] == phase)
            if mutation == "missing_source":
                take["metadata"]["source_timestamp"] = 0
            elif mutation == "typed_mismatch":
                take["message_fields"]["fields"][0]["value"]["value"] = 2
            else:
                take["capture_status"] = "UNKNOWN"
            report = tests.reduced(events)
            assert report["candidate_command_count"] == 0, (phase, mutation)
            assert report["adapter_callback_count"] == 1 and report["unknown_command_count"] == 1
            assert report["received_rgb_count"] == 1
            cases.append({"phase": phase, "mutation": mutation, "result": "UNKNOWN_WITH_DENOMINATORS_RETAINED"})
    for mode in (0, 3, 4):
        events, _, _ = tests.fixture()
        command = next(row for row in events if row["kind"] == "publish" and row["phase"] == "command")
        command.update(command_valid=False, command_mode=mode)
        report = tests.reduced(events)
        assert report["candidate_command_count"] == 0 and report["unknown_command_count"] == 1
        cases.append({"mode": mode, "result": "NONFOLLOW_NOT_A_LATENCY_SAMPLE"})
    events, emit, _ = tests.fixture()
    emit("replay", "replay_input", 1450, input_kind="depth")
    emit("replay", "replay_input", 1460, input_kind="rgb")
    emit("detector", "sensor_callback", 1800, sensor="rgb", image_token="unselectedRgb", entered_ns=1800)
    report = tests.reduced(events, native_complete=False)
    assert report["candidate_command_count"] == 0 and report["unknown_command_count"] == 1
    assert report["received_rgb_count"] == 2 and report["rgb_with_candidate_count"] == 0
    assert report["replayed_input_counts_by_kind"] == {"rgb": 2, "depth": 1}
    cases.append({"mutation": "native_incomplete_and_unselected_rgb", "result": "ALL_UNKNOWN_ALL_INPUT_OPPORTUNITIES_RETAINED"})
    return cases


def fake_fmu_guard(observer_module):
    from unittest.mock import patch
    calls = []
    class FakeNode:
        def resolve_topic_name(self, topic):
            return topic.replace("/remapped/", "/bench/review/")
        def create_publisher(self, msg_type, topic, *args, **kwargs):
            calls.append(("publisher", topic))
            return types.SimpleNamespace(topic_name=self.resolve_topic_name(topic))
        def create_subscription(self, msg_type, topic, callback, *args, **kwargs):
            calls.append(("subscription", topic))
            return types.SimpleNamespace(topic_name=self.resolve_topic_name(topic), callback=callback)
        def get_name(self): return "fake_adapter"
    class FakePublisher:
        def publish(self, message): return None
    class FakeExecutor:
        def _take_subscription(self, sub): return None
        def shutdown(self): return True
    class FakeAdapter:
        def __init__(self): pass
    probe = types.SimpleNamespace(transparent_take_wrapper=lambda original, *args: original)
    trace = observer_module.Trace()
    observer = observer_module.Observer("adapter", trace, {}, probe)
    modules = {"rclpy.node": types.SimpleNamespace(Node=FakeNode),
        "rclpy.publisher": types.SimpleNamespace(Publisher=FakePublisher),
        "rclpy.executors": types.SimpleNamespace(Executor=FakeExecutor)}
    originals = (FakeNode.create_publisher, FakeNode.create_subscription, FakePublisher.publish)
    with patch.dict(sys.modules, modules):
        try:
            observer.install_ros(types.SimpleNamespace(Px4AdapterNode=FakeAdapter), {})
            node = FakeNode()
            for topic in ("/fmu", "/fmu/in/offboard_control_mode", "/fmu/out/vehicle_odometry"):
                for method, args in ((node.create_publisher, (object, topic)),
                                     (node.create_subscription, (object, topic, lambda message: None))):
                    try:
                        method(*args)
                    except ValueError as error:
                        assert "before construction" in str(error)
                    else:
                        raise AssertionError("Unisolated endpoint was constructed")
            assert calls == []
            node.create_publisher(object, "/remapped/sink")
            assert calls == [("publisher", "/remapped/sink")]
        finally:
            observer.close()
    assert (FakeNode.create_publisher, FakeNode.create_subscription, FakePublisher.publish) == originals
    return {"unisolated_endpoint_cases": 6, "native_endpoint_constructions": 0,
            "isolated_fake_endpoint_allowed": True, "hooks_restored": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-map", required=True)
    parser.add_argument("--expected-map-sha256", required=True)
    args = parser.parse_args()
    map_path = BENCH / args.source_map
    raw = small(map_path)
    assert hashlib.sha256(raw).hexdigest() == args.expected_map_sha256
    pins = json.loads(raw)
    for name, pin in pins.items():
        source = small(BENCH / name)
        assert hashlib.sha256(source).hexdigest() == pin, name
        if name.endswith(".py"):
            ast.parse(source.decode("utf-8-sig"), feature_version=(3, 10))
    config = json.loads((BENCH / "person004_short01.manifest.json").read_bytes())
    bindings = original_bindings(config)
    sys.path.insert(0, str(BENCH))
    tests = importlib.import_module("test_bench")
    tests.bench.validate_shape(config)
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
    with redirect_stdout(io.StringIO()):
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    assert result.wasSuccessful(), output.getvalue()
    additional = extra_reducer_cases(tests)
    guard = fake_fmu_guard(importlib.import_module("observer"))
    after = {name: hashlib.sha256((BENCH / name).read_bytes()).hexdigest() for name in pins}
    assert after == pins
    receipt = {
        "schema_version": 1,
        "status": "PASS_FIXED_SOURCE_AND_FAKE_REVIEW_ONLY_NOT_ACTUAL_OBSERVATION",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer": "/root/continuation06_preparation",
        "fixed_source_map": {"path": str(map_path), "sha256": args.expected_map_sha256},
        "reviewed_source_sha256": pins, "source_unchanged_after_review": True,
        "author_tests_independently_run": {"tests_run": result.testsRun, "failures": len(result.failures),
            "errors": len(result.errors), "skipped": len(result.skipped), "output": output.getvalue()},
        "independent_adversarial_reducer_cases": additional,
        "independent_before_construction_fmu_guard": guard,
        "original_small_bindings": bindings,
        "reviewed_causal_scope": {
            "t0": "max of actual RGB and Depth callback entry monotonic times, matched by bounded object tokens to the accepted actual InferenceSnapshot",
            "intermediate": "Actual worker publication, accepted navigation update, project snapshot and controller current local target; rejected update/clear cannot refresh identity",
            "t1": "actual adapter TrackingCommand subscription wrapper entry; original callback called once with unchanged message",
            "dds": "Three edges reuse fixed c7 source_timestamp/publication-clock-window/complete-typed-fields/single-polled-writer predicate; every edge remains candidate only",
            "denominators": "All adapter callbacks, edge takes/pubs/unknowns, replay counts by kind and actual received RGB opportunities retained separately; no claimed replay-to-image DDS identity",
            "follow": "Only valid VELOCITY/POSITION contributes candidate latency. HOLD/SEARCH/FAILSAFE unknowns remain. Repeated ticks disclose first per-RGB latency separately from information age",
            "retention": "Bounded image token table 8 plus snapshot job table 8 (at most 16 indirect images); total observer image references at most 24, possibly overlapping. Other token/pending/project indices capped at 64",
            "trace": "Bounded queue/event bytes, put_nowait on original callbacks; hook/trace errors invalidate candidates. Serialization/instrumentation overhead remains within measured software path",
        },
        "reviewed_execution_scope": {
            "isolation": "All fmu endpoints refused before original construction unless remapped; no replayed status/ack/setpoint/arm, no Gazebo/PX4/supervisor launched; actual original adapter status requirement retained",
            "cache": "Pinned original open_bag_reader stages temporary links. Replay ExitStack nests private native ext4 scratch and restores tempfile.tempdir; original archive paths are read only",
            "ready": "After full original role constructor and required model/topic/use_sim_time verification, then four ready roles plus stable single-writer graph required. This is construction/discovery readiness, not proof of input delivery",
            "lock": "Native CLI nonblock-acquires existing original SITL lock and holds through native() including final cleanup; no second external flock should wrap it",
            "cleanup": "Early role/replay/master errors pass nested finally; owned groups receive SIGINT, bounded wait then SIGKILL if needed; forced kill, residual group or cleanup error makes execution incomplete",
        },
        "blocking_findings": [],
        "resolved_during_review": ["master early context/trace cleanup", "owned-group cleanup and kill race", "worker hook installation cleanup", "replay teardown context attempt on node destruction error", "snapshot indirect image retention bound", "manifest Chinese paths corrupted by shell encoding", "exact-width scalar numeric buffers"],
        "execution_conclusion": "PREPARATION_REVIEW_PASS_ONLY; ROOT_MAY_CONSIDER_ONE_EXPLICIT_NATIVE_SHORT_PREFIX_AFTER_COLLECTOR_EXIT_AND_FRESH_RESOURCE_CHECKS",
        "actual_observation": "NOT_OBSERVED", "candidate_latency_samples_from_this_review": 0,
        "historical_strict": "1857/1857_UNKNOWN_UNCHANGED", "physical_e2e": "NOT_OBSERVED",
        "native_wsl_launches": 0, "real_bag_or_weight_payload_reads": 0,
        "original_or_author_source_changes": 0, "formal_admission": False,
        "remaining_actual_checks": ["Installed original ROS/px4_msgs/numpy/Ultralytics compatibility", "Actual callback and MessageInfo capture", "Actual graph discovery and input delivery", "Actual FOLLOW presence in declared prefix", "Full original source/model/archive preflight and preservation hashes", "Actual native cleanup and scratch closure"],
        "small_inputs_read": INPUTS,
    }
    target = HERE / "independent_review01.json"
    target.write_text(json.dumps(receipt, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(target), "author_tests": result.testsRun,
        "independent_reducer_cases": len(additional), "fmu_guard_cases": 6,
        "source_map_sha256": args.expected_map_sha256, "actual_observation": "NOT_OBSERVED"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
