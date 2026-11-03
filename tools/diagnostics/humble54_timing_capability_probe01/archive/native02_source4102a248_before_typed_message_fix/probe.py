#!/usr/bin/env python3
"""Small, independent Humble timing capability experiment; never a flight/E2E test.

Importing this module does not import ROS or start a process. Native execution is
explicit, bounded, and requires an unused localhost ROS domain and output path.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import inspect
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import time
import traceback
import uuid
import xml.etree.ElementTree as ET


EXPECTED_EXECUTORS_SHA256 = "cfd24d4952d061299d395820bfffae3afb95a87ac186ca131194be349846e7fd"
EXPECTED_TAKE_SOURCE = (
    "    def _take_subscription(self, sub):\n"
    "        with sub.handle:\n"
    "            msg_info = sub.handle.take_message(sub.msg_type, sub.raw)\n"
    "            if msg_info is not None:\n"
    "                return msg_info[0]\n"
    "        return None\n"
)
EXPECTED_TAKE_SHA256 = "a4a44c7de81c0de9e031b7bfbb839508e6d4d77aec015b52a29689afa82eb03a"
EXPECTED_FASTDDS_VERSION = "2.6.12"
EXPECTED_FASTDDS_CMAKE_SHA256 = "8edb8f6935ce6eb8e383c40d785156fcca62f3834852e5a0cb8f5377d3bd5001"
SCOPE = "INDEPENDENT_SOFTWARE_TIMING_CAPABILITY_ONLY_NOT_E2E_NOT_ACCEPTANCE"


def anchor():
    """Bound one CLOCK_REALTIME reading with two CLOCK_MONOTONIC readings."""
    before = time.monotonic_ns()
    realtime = time.time_ns()
    after = time.monotonic_ns()
    return {"monotonic_before_ns": before, "realtime_ns": realtime,
            "monotonic_after_ns": after}


def json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return {"unsupported_type": type(value).__qualname__, "repr": repr(value)}


class Recorder:
    def __init__(self):
        self.events = []
        self.errors = []

    def add(self, kind, **fields):
        event = {"event_index": len(self.events), "kind": kind,
                 "recorded_monotonic_ns": time.monotonic_ns(), **fields}
        self.events.append(json_value(event))


def transparent_take_wrapper(original, observer, instrumentation_errors):
    """Observe the original Python return frame; never replace its native take.

    Existing profilers retain their original behavior, with no metadata captured.
    Observer execution happens after restoring the prior per-thread profiler.
    The short-lived profiler adds overhead to all calls in that thread during
    original(), so this is capability instrumentation, not a low-overhead claim.
    """
    original_code = original.__code__

    def report(record):
        try:
            observer(record)
        except Exception as error:
            instrumentation_errors.append({"where": "observer", "error": repr(error)})

    @functools.wraps(original)
    def observed(executor, sub):
        entry = time.monotonic_ns()
        previous = sys.getprofile()
        if previous is not None:
            try:
                return original(executor, sub)
            finally:
                report({"status": "UNKNOWN", "reason": "existing_thread_profiler",
                        "sub": sub, "entered_ns": entry})
        capture = []

        def profiler(frame, event, result):
            if event == "return" and frame.f_code is original_code:
                try:
                    if frame.f_locals.get("sub") is sub:
                        capture.append((frame.f_locals.get("msg_info"), result))
                except Exception as error:
                    instrumentation_errors.append({"where": "return_profile", "error": repr(error)})

        outcome = "returned"
        returned = None
        original_error = None
        installed = False
        try:
            try:
                sys.setprofile(profiler)
                installed = True
            except Exception as error:
                instrumentation_errors.append({"where": "install_profile", "error": repr(error)})
            try:
                returned = original(executor, sub)
                return returned
            except BaseException as error:
                outcome, original_error = "raised", type(error).__qualname__
                raise
        finally:
            if installed:
                try:
                    sys.setprofile(previous)
                except Exception as error:
                    instrumentation_errors.append({"where": "restore_profile", "error": repr(error)})
            record = {"status": "UNKNOWN", "reason": "missing_original_return_frame",
                      "sub": sub, "entered_ns": entry, "exited_ns": time.monotonic_ns(),
                      "outcome": outcome, "original_exception_type": original_error,
                      "return_value": returned}
            if outcome == "returned" and len(capture) == 1:
                msg_info, profile_return = capture[0]
                if msg_info is None and returned is None:
                    record.update(status="EMPTY", reason="native_take_no_message")
                elif (isinstance(msg_info, tuple) and len(msg_info) == 2
                      and msg_info[0] is returned and profile_return is returned
                      and isinstance(msg_info[1], dict)):
                    record.update(status="CAPTURED", reason=None, message=returned,
                                  metadata=msg_info[1])
            report(record)

    return observed


def observed_publish(original, message, emit, phase, writer_token, payload_hex,
                     instrumentation_errors=None):
    """Call the original bound publish exactly once with the original message."""
    before = anchor()
    success = False
    error_type = None
    try:
        result = original(message)
        success = True
        return result
    except BaseException as error:
        error_type = type(error).__qualname__
        raise
    finally:
        after = anchor()
        try:
            emit("publish", phase=phase, writer_token=writer_token,
                 before=before, after=after, success=success,
                 exception_type=error_type, payload_hex=payload_hex)
        except Exception as error:
            if instrumentation_errors is not None:
                instrumentation_errors.append({"where": "publish_observer", "error": repr(error)})


def valid_ns(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def valid_publish_clock_fields(event):
    return all(isinstance(event.get(name), dict) and
               all(valid_ns(event[name].get(key)) for key in
                   ("monotonic_before_ns", "realtime_ns", "monotonic_after_ns"))
               for name in ("before", "after"))


def record_executor_shutdown(executor):
    """Humble returns False when outstanding callbacks do not finish in time."""
    try:
        result = executor.shutdown(timeout_sec=2.0)
        return {"executor_shutdown": json_value(result), "timeout_sec": 2.0,
                "returned_true": result is True}
    except Exception as error:
        return {"executor_shutdown": False, "timeout_sec": 2.0, "error": repr(error)}


def apply_cleanup_outcome(summary, cleanup):
    if any(any(key.endswith("error") for key in item) or
           ("executor_shutdown" in item and item.get("returned_true") is not True)
           for item in cleanup):
        summary.update(status="UNKNOWN", stop_reason="native_cleanup_error")


def assess(events, phase, timestamp_uncertainty_ns=2, offset_tolerance_ns=100000,
           graph_gap_limit_ns=200000000):
    """Conservative candidate pairing. It deliberately never returns KNOWN."""
    selected = [event for event in events if event.get("phase") == phase]
    publishes = [event for event in selected if event["kind"] == "publish"]
    takes = [event for event in selected if event["kind"] == "take"]
    graphs = [event for event in selected if event["kind"] == "graph"]
    lifecycle = [event for event in selected if event["kind"] == "controlled_writers"]
    reasons = []
    if len(lifecycle) < 2 or any(len(event["writers"]) != 1 for event in lifecycle):
        reasons.append("controlled_writer_count_not_one")
    if len(graphs) < 2:
        reasons.append("insufficient_graph_samples")
    endpoint_sets = [tuple(sorted(item["gid_hex"] for item in event["publishers"]))
                     for event in graphs]
    if any(len(items) != 1 for items in endpoint_sets):
        reasons.append("observed_competing_or_missing_writer")
    if endpoint_sets and len(set(endpoint_sets)) != 1:
        reasons.append("observed_graph_changed")
    expected_names = {name for event in lifecycle for name in event["writers"]}
    if any(item["node_name"] not in expected_names
           for event in graphs for item in event["publishers"]):
        reasons.append("unexpected_graph_writer")
    if any(event["writer_token"] not in expected_names for event in publishes):
        reasons.append("uncontrolled_publish_writer")
    data_times = [event.get("recorded_monotonic_ns") for event in publishes + takes]
    graph_times = [event.get("recorded_monotonic_ns") for event in graphs]
    lifecycle_times = [event.get("recorded_monotonic_ns") for event in lifecycle]
    graph_max_gap_ns = None
    if (not data_times or not graph_times or not lifecycle_times
            or any(not isinstance(value, int) for value in data_times + graph_times + lifecycle_times)):
        reasons.append("missing_graph_or_lifecycle_time_coverage")
    else:
        if (min(graph_times) > min(data_times) or max(graph_times) < max(data_times)
                or min(lifecycle_times) > min(data_times) or max(lifecycle_times) < max(data_times)):
            reasons.append("graph_or_lifecycle_does_not_bracket_data")
        gaps = [right - left for left, right in zip(graph_times, graph_times[1:])]
        graph_max_gap_ns = max(gaps, default=0)
        if any(gap < 0 or gap > graph_gap_limit_ns for gap in gaps):
            reasons.append("graph_poll_gap_or_time_order_violation")
    if any(not event["success"] for event in publishes):
        reasons.append("publish_exception")
    clock_valid_publishes = [event for event in publishes if valid_publish_clock_fields(event)]
    if len(clock_valid_publishes) != len(publishes):
        reasons.append("missing_or_invalid_publish_clock_fields")
    ordered = sorted(clock_valid_publishes,
                     key=lambda event: event["before"]["monotonic_before_ns"])
    if any(event["before"]["monotonic_after_ns"] > event["after"]["monotonic_before_ns"]
           for event in ordered):
        reasons.append("publish_monotonic_window_reversed")
    for left, right in zip(ordered, ordered[1:]):
        if (left["after"]["realtime_ns"] + timestamp_uncertainty_ns
                >= right["before"]["realtime_ns"] - timestamp_uncertainty_ns):
            reasons.append("overlapping_or_unordered_publish_windows")
            break
    if any(left["after"]["monotonic_after_ns"] >= right["before"]["monotonic_before_ns"]
           for left, right in zip(ordered, ordered[1:])):
        reasons.append("overlapping_or_unordered_publish_monotonic_windows")
    anchors = [item for event in ordered for item in (event["before"], event["after"])]
    if any(item["monotonic_before_ns"] > item["monotonic_after_ns"] for item in anchors):
        reasons.append("monotonic_anchor_reversed")
    if any(right["realtime_ns"] < left["realtime_ns"] for left, right in zip(anchors, anchors[1:])):
        reasons.append("realtime_reversed")
    if anchors:
        lower = max(item["realtime_ns"] - item["monotonic_after_ns"] for item in anchors)
        upper = min(item["realtime_ns"] - item["monotonic_before_ns"] for item in anchors)
        if lower > upper + offset_tolerance_ns:
            reasons.append("realtime_monotonic_anchors_inconsistent")
    source_counts = {}
    for event in takes:
        stamp = event.get("metadata", {}).get("source_timestamp")
        if isinstance(stamp, int) and not isinstance(stamp, bool):
            source_counts[stamp] = source_counts.get(stamp, 0) + 1
    pairs = []
    used_publishes = {}
    for event in takes:
        local_reasons = list(dict.fromkeys(reasons))
        entered, exited, recorded = (event.get(key) for key in
                                     ("entered_ns", "exited_ns", "recorded_monotonic_ns"))
        valid_take_fields = all(valid_ns(value) for value in (entered, exited, recorded))
        if not valid_take_fields:
            local_reasons.append("missing_or_invalid_take_clock_fields")
        elif not entered <= exited <= recorded:
            local_reasons.append("take_monotonic_window_reversed_or_after_record")
        stamp = event.get("metadata", {}).get("source_timestamp")
        candidates = []
        if not isinstance(stamp, int) or isinstance(stamp, bool) or stamp <= 0:
            local_reasons.append("missing_or_invalid_dds_source_timestamp")
        else:
            if source_counts[stamp] != 1:
                local_reasons.append("repeated_dds_source_timestamp")
            candidates = [pub for pub in clock_valid_publishes if pub["success"] and
                          pub["before"]["realtime_ns"] - timestamp_uncertainty_ns <= stamp <=
                          pub["after"]["realtime_ns"] + timestamp_uncertainty_ns]
            if len(candidates) != 1:
                local_reasons.append("source_not_in_exactly_one_publish_window")
        if len(candidates) == 1:
            pub = candidates[0]
            used_publishes[pub["event_index"]] = used_publishes.get(pub["event_index"], 0) + 1
            if valid_take_fields and pub["before"]["monotonic_before_ns"] > exited:
                local_reasons.append("publish_started_after_take_already_ended")
            if pub["payload_hex"] != event.get("payload_hex"):
                local_reasons.append("whole_message_bytes_mismatch")
        if event.get("capture_status") != "CAPTURED":
            local_reasons.append("take_metadata_not_captured")
        pairs.append({"take_event_index": event["event_index"],
                      "publish_event_indices": [pub["event_index"] for pub in candidates],
                      "source_timestamp": stamp,
                      "status": "UNKNOWN" if local_reasons else "OBSERVED_CANDIDATE",
                      "reasons": local_reasons})
    for pair in pairs:
        if any(used_publishes.get(index, 0) != 1 for index in pair["publish_event_indices"]):
            pair["status"] = "UNKNOWN"
            pair["reasons"].append("publish_window_used_by_multiple_takes")
    unmatched = [pub["event_index"] for pub in publishes if not used_publishes.get(pub["event_index"])]
    return {"scope": SCOPE, "phase": phase, "pairs": pairs,
            "publish_count": len(publishes), "take_count": len(takes),
            "unmatched_publish_event_indices": unmatched,
            "graph_sample_count": len(graphs),
            "graph_max_observed_gap_ns": graph_max_gap_ns,
            "graph_gap_limit_ns": graph_gap_limit_ns,
            "graph_observation": "POLLED_NOT_CONTINUOUS_EXTERNAL_WRITER_ABSENCE_NOT_PROVEN",
            "timestamp_uncertainty_ns": timestamp_uncertainty_ns,
            "offset_tolerance_ns": offset_tolerance_ns,
            "candidate_count": sum(pair["status"] == "OBSERVED_CANDIDATE" for pair in pairs),
            "unknown_count": sum(pair["status"] == "UNKNOWN" for pair in pairs)}


def dump_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def parse_cmake_package_version(text):
    """Read a single literal release assignment, never execute CMake code."""
    matches = re.findall(
        r'^\s*set\(\s*PACKAGE_VERSION\s+(?:"([0-9]+\.[0-9]+\.[0-9]+)"|'
        r'([0-9]+\.[0-9]+\.[0-9]+))\s*\)\s*(?:#.*)?$', text, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError("Need exactly one literal CMake PACKAGE_VERSION release")
    return matches[0][0] or matches[0][1]


def read_small_config(path):
    source = Path(path)
    if not source.is_file() or source.stat().st_size > 65536:
        raise ValueError("Missing or oversized fixed CMake version config")
    return source.read_bytes()


def fastdds_binding(map_entries, read_config=read_small_config):
    """Bind non-ament FastDDS to its actual mapped library's install prefix.

    No fallback to a different installed prefix: absent/multiple/deleted maps,
    unexpected library version, config version or known config hash fail closed.
    Full library payload hashing remains outside this small capability probe.
    """
    result = {"expected_version": EXPECTED_FASTDDS_VERSION, "gate_passed": False,
              "source_kind": "ACTUAL_MAPPED_LIBRARY_PREFIX_AND_PINNED_CMAKE_VERSION_FILE",
              "mapped_library_paths": [], "errors": []}
    paths = set()
    for line in map_entries:
        fields = line.split(None, 5)
        if len(fields) != 6:
            continue
        raw_path = fields[5]
        if raw_path.endswith(" (deleted)"):
            if "libfastrtps.so" in raw_path:
                result["errors"].append("deleted_mapped_fastdds_library")
            continue
        path = PurePosixPath(raw_path)
        if path.name == "libfastrtps.so" or path.name.startswith("libfastrtps.so."):
            paths.add(str(path))
    result["mapped_library_paths"] = sorted(paths)
    if len(paths) != 1 or result["errors"]:
        result["errors"].append("need_exactly_one_live_mapped_fastdds_library")
        return result
    library = PurePosixPath(next(iter(paths)))
    matched = re.fullmatch(r"libfastrtps\.so\.([0-9]+\.[0-9]+\.[0-9]+)", library.name)
    if (not library.is_absolute() or library.parent.name not in {"lib", "lib64"}
            or matched is None):
        result["errors"].append("mapped_fastdds_path_or_release_name_not_supported")
        return result
    result["mapped_library_version"] = matched.group(1)
    config = library.parent.parent / "share/fastrtps/cmake/fastrtps-config-version.cmake"
    result["cmake_version_path"] = str(config)
    try:
        data = read_config(str(config))
        if not isinstance(data, bytes) or len(data) > 65536:
            raise ValueError("Version config reader must return bounded original bytes")
        result["cmake_version_bytes"] = len(data)
        result["cmake_version_sha256"] = hashlib.sha256(data).hexdigest()
        result["cmake_package_version"] = parse_cmake_package_version(data.decode("utf-8"))
    except Exception as error:
        result["errors"].append("cmake_version_read_or_parse_failed:" + repr(error))
        return result
    if result["mapped_library_version"] != EXPECTED_FASTDDS_VERSION:
        result["errors"].append("mapped_library_release_differs")
    if result["cmake_package_version"] != EXPECTED_FASTDDS_VERSION:
        result["errors"].append("cmake_package_release_differs")
    if result["cmake_version_sha256"] != EXPECTED_FASTDDS_CMAKE_SHA256:
        result["errors"].append("cmake_version_original_bytes_differ")
    result["gate_passed"] = not result["errors"]
    return result


def runtime_binding():
    import rclpy.executors
    from ament_index_python.packages import get_package_share_directory
    from rclpy.utilities import get_rmw_implementation_identifier
    path = Path(inspect.getfile(rclpy.executors.Executor))
    data = path.read_bytes()
    source = inspect.getsource(rclpy.executors.Executor._take_subscription)
    method = rclpy.executors.Executor._take_subscription
    method_is_original_shape = (not hasattr(method, "__wrapped__")
                               and method.__code__.co_name == "_take_subscription"
                               and method.__code__.co_firstlineno == 398
                               and Path(method.__code__.co_filename).resolve() == path.resolve())
    binding = {"executor_path": str(path), "executor_sha256": hashlib.sha256(data).hexdigest(),
               "take_source": source, "take_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
               "rmw_identifier": get_rmw_implementation_identifier(), "packages": {}}
    binding["method_is_original_shape"] = method_is_original_shape
    maps = Path("/proc/self/maps")
    binding["loaded_library_map_entries"] = [line for line in maps.read_text(encoding="utf-8").splitlines()
        if any(name in line for name in ("libfastrtps", "librmw_fastrtps", "_rclpy_pybind11"))] if maps.exists() else []
    binding["loaded_library_binary_hashes"] = "NOT_OBSERVED_BY_THIS_SMALL_PROBE"
    for package in ("rclpy", "rmw_fastrtps_cpp", "rmw_fastrtps_shared_cpp"):
        xml = Path(get_package_share_directory(package)) / "package.xml"
        binding["packages"][package] = ET.fromstring(xml.read_bytes()).findtext("version")
    expected_versions = {"rclpy": "3.3.22", "rmw_fastrtps_cpp": "6.2.10",
                         "rmw_fastrtps_shared_cpp": "6.2.10"}
    binding["fastdds"] = fastdds_binding(binding["loaded_library_map_entries"])
    binding["gate_passed"] = (
        method_is_original_shape and binding["executor_sha256"] == EXPECTED_EXECUTORS_SHA256 and
        binding["take_sha256"] == EXPECTED_TAKE_SHA256 and
        binding["packages"] == expected_versions and
        binding["fastdds"]["gate_passed"] and
        binding["rmw_identifier"] == "rmw_fastrtps_cpp")
    return binding


def native(args):
    """Run only this small message experiment; no subprocesses or flight stack."""
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    recorder = Recorder()
    summary = {"scope": SCOPE, "status": "UNKNOWN", "native_experiment": True,
               "physical_e2e": "NOT_OBSERVED", "historical_strict_changed": False,
               "probe_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "python": sys.version, "platform": platform.platform(), "pid": os.getpid(),
               "configured_domain_id": args.domain_id,
               "started_at": anchor(),
               "profile_overhead": "TEMPORARY_PER_THREAD_ALL_CALLS_DURING_ORIGINAL_TAKE_NOT_QUANTIFIED",
               "limits": ["No flight, detector, inference, original pipeline or physical latency measured",
                          "Graph is polled throughout; transient external writers cannot be excluded",
                          "Observed source clock/window behavior does not prove every future sample",
                          "Any candidate remains supplementary; no KNOWN/strict promotion"]}
    previous_env = {key: os.environ.get(key) for key in
                    ("ROS_DOMAIN_ID", "ROS_LOCALHOST_ONLY", "RMW_IMPLEMENTATION")}
    os.environ.update(ROS_DOMAIN_ID=str(args.domain_id), ROS_LOCALHOST_ONLY="1",
                      RMW_IMPLEMENTATION="rmw_fastrtps_cpp")
    summary["previous_process_environment"] = previous_env
    nodes, executor, patched_class, original_take = [], None, None, None
    initialized = False
    state = {"phase": "initialization"}
    pending = {}
    callback_records = []
    try:
        import rclpy
        from geometry_msgs.msg import PoseStamped
        from rclpy.executors import Executor, SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.serialization import serialize_message

        summary["runtime_binding"] = runtime_binding()
        if not summary["runtime_binding"]["gate_passed"]:
            summary["stop_reason"] = "fixed_runtime_source_or_version_gate_failed"
            raise RuntimeError(summary["stop_reason"])
        token = uuid.uuid4().hex[:12]
        topic = "/timing_capability_probe_" + token
        summary.update(topic=topic, monotonic_clock=vars(time.get_clock_info("monotonic")),
                       realtime_clock=vars(time.get_clock_info("time")))
        boot = Path("/proc/sys/kernel/random/boot_id")
        summary["boot_id"] = boot.read_text(encoding="utf-8").strip() if boot.exists() else None
        rclpy.init(args=[])
        initialized = True
        reader = Node("timing_probe_reader_" + token)
        writer_a = Node("timing_probe_writer_a_" + token)
        writer_b = Node("timing_probe_writer_b_" + token)
        nodes.extend((reader, writer_a, writer_b))
        executor = SingleThreadedExecutor()
        for node in nodes:
            executor.add_node(node)

        def on_take(record):
            if record["sub"].topic_name != topic:
                return
            if record["status"] == "EMPTY":
                recorder.add("take_empty", phase=state["phase"],
                             entered_ns=record["entered_ns"], exited_ns=record.get("exited_ns"))
                return
            message = record.get("message")
            take_token = len(recorder.events)
            recorder.add("take", phase=state["phase"], take_token=take_token,
                         capture_status=record["status"], capture_reason=record["reason"],
                         entered_ns=record["entered_ns"], exited_ns=record.get("exited_ns"),
                         metadata=record.get("metadata", {}),
                         payload_hex=bytes(serialize_message(message)).hex() if message is not None else None)
            if message is not None:
                pending[id(message)] = (message, take_token)

        original_take = Executor._take_subscription
        Executor._take_subscription = transparent_take_wrapper(original_take, on_take, recorder.errors)
        patched_class = Executor

        def original_callback(message):
            entered = time.monotonic_ns()
            observed = pending.pop(id(message), None)
            exact = observed is not None and observed[0] is message
            record = {"phase": state["phase"], "entered_ns": entered,
                      "take_token": observed[1] if exact else None,
                      "same_object_as_original_take": exact,
                      "payload_hex": bytes(serialize_message(message)).hex()}
            callback_records.append(record)
            recorder.add("callback", **record)

        subscription = reader.create_subscription(PoseStamped, topic, original_callback, 10)
        if subscription.callback is not original_callback:
            raise RuntimeError("original registered handler identity changed")
        pub_a = writer_a.create_publisher(PoseStamped, topic, 10)
        controlled = [writer_a.get_name()]
        recorder.add("writer_created", writer=controlled[0], topic=topic, at=anchor())
        deadline = time.monotonic() + args.timeout_s

        def graph():
            endpoints = reader.get_publishers_info_by_topic(topic)
            items = [{"node_name": item.node_name, "node_namespace": item.node_namespace,
                      "gid_hex": bytes(item.endpoint_gid).hex(), "topic_type": item.topic_type,
                      "qos_repr": repr(item.qos_profile)} for item in endpoints]
            recorder.add("graph", phase=state["phase"], at=anchor(), publishers=items)
            return items

        def spin():
            if time.monotonic() >= deadline:
                raise TimeoutError("bounded capability experiment deadline")
            executor.spin_once(timeout_sec=0.01)
            graph()

        def wait_graph(expected):
            stable_since = None
            while True:
                items = graph()
                names = sorted(item["node_name"] for item in items)
                if names == sorted(expected) and len(items) == len(expected):
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= 0.15:
                        return
                else:
                    stable_since = None
                spin()

        def drain(duration):
            until = time.monotonic() + duration
            while time.monotonic() < until:
                spin()

        def publish(pub, writer_token):
            message = PoseStamped()
            message.header.stamp.sec, message.header.stamp.nanosec = 42, 7
            message.header.frame_id = "identical_header_every_publish"
            message.pose.position.x = 1.25
            message.pose.orientation.w = 1.0
            payload = bytes(serialize_message(message)).hex()
            observed_publish(pub.publish, message, recorder.add, state["phase"], writer_token,
                             payload, recorder.errors)

        state["phase"] = "discover_single"
        wait_graph(controlled)
        state["phase"] = "single_writer_identical_payload"
        recorder.add("controlled_writers", phase=state["phase"], writers=list(controlled), at=anchor())
        graph()
        for _ in range(args.messages):
            publish(pub_a, writer_a.get_name())
            drain(0.025)
        drain(0.2)
        recorder.add("controlled_writers", phase=state["phase"], writers=list(controlled), at=anchor())
        graph()

        state["phase"] = "discover_competitor"
        pub_b = writer_b.create_publisher(PoseStamped, topic, 10)
        controlled.append(writer_b.get_name())
        recorder.add("writer_created", writer=writer_b.get_name(), topic=topic, at=anchor())
        wait_graph(controlled)
        state["phase"] = "competing_writer_identical_payload"
        recorder.add("controlled_writers", phase=state["phase"], writers=list(controlled), at=anchor())
        graph()
        for _ in range(args.messages):
            publish(pub_a, writer_a.get_name())
            publish(pub_b, writer_b.get_name())
            drain(0.025)
        drain(0.2)
        recorder.add("controlled_writers", phase=state["phase"], writers=list(controlled), at=anchor())
        graph()
        summary["phases"] = [assess(recorder.events, phase) for phase in
                             ("single_writer_identical_payload", "competing_writer_identical_payload")]
        first, second = summary["phases"]
        consistent = (len(callback_records) == first["take_count"] + second["take_count"]
                      and all(item["same_object_as_original_take"] for item in callback_records))
        capability_observed = (first["publish_count"] == args.messages == first["candidate_count"]
                               and first["unknown_count"] == 0 and not first["unmatched_publish_event_indices"]
                               and second["take_count"] == 2 * args.messages == second["unknown_count"]
                               and second["candidate_count"] == 0 and consistent
                               and not pending and not recorder.errors)
        summary.update(status="CAPABILITY_OBSERVED_IN_THIS_PROBE_ONLY" if capability_observed else "UNKNOWN",
                       original_handler_identity_preserved=subscription.callback is original_callback,
                       callback_object_consistency=consistent, pending_take_objects=len(pending))
    except Exception as error:
        summary.update(status="UNKNOWN", exception_type=type(error).__qualname__,
                       error=str(error), traceback=traceback.format_exc())
    finally:
        if patched_class is not None:
            patched_class._take_subscription = original_take
        # Preserve the observed messages before DDS teardown, which itself can fail.
        try:
            checkpoint = output / "raw_events_before_cleanup.json"
            dump_json(checkpoint, {"scope": SCOPE, "events": recorder.events})
            dump_json(output / "summary_before_cleanup.json", {
                **summary, "status": "UNKNOWN", "cleanup_completed": False,
                "proposed_status_before_cleanup": summary["status"],
                "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest()})
        except Exception as error:
            recorder.errors.append({"where": "pre_cleanup_checkpoint", "error": repr(error)})
        cleanup = []
        if executor is not None:
            cleanup.append(record_executor_shutdown(executor))
        for node in reversed(nodes):
            try:
                name = node.get_name()
                node.destroy_node()
                recorder.add("node_destroyed", node_name=name, at=anchor())
            except Exception as error:
                cleanup.append({"node_destroy_error": repr(error)})
        if initialized:
            try:
                import rclpy
                rclpy.shutdown()
            except Exception as error:
                cleanup.append({"context_shutdown_error": repr(error)})
        apply_cleanup_outcome(summary, cleanup)
        binding = summary.get("runtime_binding")
        if binding is not None:
            try:
                after_sha = hashlib.sha256(Path(binding["executor_path"]).read_bytes()).hexdigest()
                binding["executor_sha256_after"] = after_sha
                binding["executor_source_unchanged"] = after_sha == binding["executor_sha256"]
                if not binding["executor_source_unchanged"]:
                    summary.update(status="UNKNOWN", stop_reason="executor_source_changed")
            except Exception as error:
                summary.update(status="UNKNOWN", stop_reason="executor_source_recheck_failed", error=repr(error))
        if recorder.errors:
            summary.update(status="UNKNOWN", stop_reason="instrumentation_error")
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        summary.update(instrumentation_errors=recorder.errors, cleanup=cleanup,
                       cleanup_completed=True, raw_event_count=len(recorder.events), finished_at=anchor())
        raw = output / "raw_events.json"
        dump_json(raw, {"scope": SCOPE, "events": recorder.events})
        summary["raw_events_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
        dump_json(output / "summary.json", summary)
    return 0 if summary["status"] == "CAPABILITY_OBSERVED_IN_THIS_PROBE_ONLY" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    native_parser = commands.add_parser("native", help="explicit small ROS-only capability experiment")
    native_parser.add_argument("--output", required=True, help="new, unused directory; never overwrites")
    native_parser.add_argument("--domain-id", required=True, type=int, help="exclusive unused domain, 1..232")
    native_parser.add_argument("--messages", type=int, default=8)
    native_parser.add_argument("--timeout-s", type=float, default=20.0)
    args = parser.parse_args()
    if not 1 <= args.domain_id <= 232 or not 2 <= args.messages <= 30 or not 2 <= args.timeout_s <= 45:
        parser.error("domain-id 1..232, messages 2..30 and timeout-s 2..45 required")
    return native(args)


if __name__ == "__main__":
    raise SystemExit(main())
