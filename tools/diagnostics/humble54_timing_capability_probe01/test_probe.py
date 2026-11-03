"""No ROS imports, subprocesses, large data or native execution."""
import importlib.util
from pathlib import Path
import sys
import struct
import threading
from types import SimpleNamespace
import unittest


SPEC = importlib.util.spec_from_file_location("timing_capability_probe", Path(__file__).with_name("probe.py"))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class FakeHandle:
    def __init__(self, message=None, metadata=None, error=None):
        self.message, self.metadata, self.error = message, metadata, error
        self.calls, self.arguments, self.enters, self.exits = 0, [], 0, 0

    def __enter__(self):
        self.enters += 1
        return self

    def __exit__(self, *args):
        self.exits += 1

    def take_message(self, msg_type, raw):
        self.calls += 1
        self.arguments.append((msg_type, raw))
        if self.error:
            raise self.error
        return None if self.message is None else (self.message, self.metadata)


class FakeSub:
    def __init__(self, handle):
        self.handle, self.msg_type, self.raw = handle, object(), False


namespace = {}
exec("class FakeExecutor:\n" + probe.EXPECTED_TAKE_SOURCE, namespace)
FakeExecutor = namespace["FakeExecutor"]


def fake_pose_stamped():
    return SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=42, nanosec=7),
                               frame_id="identical_header_every_publish"),
        pose=SimpleNamespace(position=SimpleNamespace(x=1.25, y=0.0, z=0.0),
                             orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)))


def at(rt, mono):
    return {"realtime_ns": rt, "monotonic_before_ns": mono,
            "monotonic_after_ns": mono + 1}


def valid_events():
    events = [
        {"kind": "controlled_writers", "phase": "one", "writers": ["own"]},
        {"kind": "graph", "phase": "one", "publishers": [{"node_name": "own", "gid_hex": "aa"}]},
        {"kind": "publish", "phase": "one", "event_index": 2, "success": True,
         "writer_token": "own", "before": at(1000, 100), "after": at(1010, 110), "payload_hex": "abcd"},
        {"kind": "publish", "phase": "one", "event_index": 3, "success": True,
         "writer_token": "own", "before": at(2000, 1100), "after": at(2010, 1110), "payload_hex": "abcd"},
        {"kind": "take", "phase": "one", "event_index": 4, "capture_status": "CAPTURED",
         "metadata": {"source_timestamp": 1005}, "payload_hex": "abcd",
         "entered_ns": 200, "exited_ns": 210},
        {"kind": "take", "phase": "one", "event_index": 5, "capture_status": "CAPTURED",
         "metadata": {"source_timestamp": 2005}, "payload_hex": "abcd",
         "entered_ns": 1200, "exited_ns": 1210},
        {"kind": "controlled_writers", "phase": "one", "writers": ["own"]},
        {"kind": "graph", "phase": "one", "publishers": [{"node_name": "own", "gid_hex": "aa"}]},
    ]
    for index, event in enumerate(events):
        event["recorded_monotonic_ns"] = index * 1000
        if event["kind"] in {"publish", "take"}:
            event["message_fields"] = probe.pose_stamped_fields(fake_pose_stamped())
    return events


class TransparencyTests(unittest.TestCase):
    def test_shutdown_false_and_non_bool_results_remain_unknown(self):
        class FakeShutdown:
            def __init__(self, result):
                self.result, self.arguments = result, []
            def shutdown(self, *, timeout_sec):
                self.arguments.append(timeout_sec)
                return self.result
        for result in (False, None, 1, True):
            with self.subTest(result=result):
                executor = FakeShutdown(result)
                record = probe.record_executor_shutdown(executor)
                self.assertEqual(executor.arguments, [2.0])
                self.assertIs(record["executor_shutdown"], result)
                summary = {"status": "CAPABILITY_OBSERVED_IN_THIS_PROBE_ONLY"}
                probe.apply_cleanup_outcome(summary, [record])
                self.assertEqual(summary["status"], "CAPABILITY_OBSERVED_IN_THIS_PROBE_ONLY"
                                 if result is True else "UNKNOWN")

    def test_shutdown_exception_is_retained_and_rejected(self):
        class BrokenShutdown:
            def shutdown(self, *, timeout_sec):
                raise RuntimeError("outstanding callbacks")
        record = probe.record_executor_shutdown(BrokenShutdown())
        self.assertFalse(record["executor_shutdown"])
        self.assertIn("outstanding callbacks", record["error"])
        summary = {"status": "CAPABILITY_OBSERVED_IN_THIS_PROBE_ONLY"}
        probe.apply_cleanup_outcome(summary, [record])
        self.assertEqual(summary["status"], "UNKNOWN")

    def test_actual_return_frame_local_metadata_and_identity(self):
        message, metadata, records, errors = object(), {"source_timestamp": 123, "received_timestamp": 456}, [], []
        handle = FakeHandle(message, metadata)
        sub = FakeSub(handle)
        original = FakeExecutor._take_subscription
        wrapped = probe.transparent_take_wrapper(original, records.append, errors)
        self.assertIs(wrapped(FakeExecutor(), sub), message)
        self.assertEqual(handle.calls, 1)
        self.assertEqual(handle.arguments, [(sub.msg_type, sub.raw)])
        self.assertEqual((handle.enters, handle.exits), (1, 1))
        self.assertIs(records[0]["metadata"], metadata)
        self.assertIs(records[0]["message"], message)
        self.assertEqual(records[0]["status"], "CAPTURED")
        self.assertIsNone(sys.getprofile())
        self.assertEqual(errors, [])

    def test_empty_and_same_native_exception_object_are_preserved(self):
        records, errors = [], []
        wrapped = probe.transparent_take_wrapper(FakeExecutor._take_subscription, records.append, errors)
        self.assertIsNone(wrapped(FakeExecutor(), FakeSub(FakeHandle())))
        self.assertEqual(records[-1]["status"], "EMPTY")
        error = RuntimeError("native take failed")
        handle = FakeHandle(error=error)
        with self.assertRaises(RuntimeError) as caught:
            wrapped(FakeExecutor(), FakeSub(handle))
        self.assertIs(caught.exception, error)
        self.assertEqual((handle.calls, handle.enters, handle.exits), (1, 1, 1))
        self.assertEqual(records[-1]["outcome"], "raised")
        self.assertIsNone(sys.getprofile())

    def test_existing_profiler_is_untouched_and_metadata_unknown(self):
        records, errors, seen = [], [], []
        def previous(frame, event, result):
            if frame.f_code is FakeExecutor._take_subscription.__code__:
                seen.append(event)
        wrapped = probe.transparent_take_wrapper(FakeExecutor._take_subscription, records.append, errors)
        sys.setprofile(previous)
        try:
            message = object()
            self.assertIs(wrapped(FakeExecutor(), FakeSub(FakeHandle(message, {}))), message)
            self.assertIs(sys.getprofile(), previous)
        finally:
            sys.setprofile(None)
        self.assertIn("call", seen)
        self.assertEqual(records[0]["reason"], "existing_thread_profiler")
        self.assertNotIn("metadata", records[0])

    def test_other_thread_profile_and_original_callback_remain_unchanged(self):
        ready, release, observations = threading.Event(), threading.Event(), []
        def other_thread():
            def other_profile(frame, event, result):
                pass
            sys.setprofile(other_profile)
            ready.set()
            release.wait(2)
            observations.append(sys.getprofile() is other_profile)
            sys.setprofile(None)
        thread = threading.Thread(target=other_thread)
        thread.start()
        self.assertTrue(ready.wait(2))
        try:
            records, errors, callback_arguments = [], [], []
            wrapped = probe.transparent_take_wrapper(FakeExecutor._take_subscription, records.append, errors)
            message = object()
            def original_handler(msg):
                callback_arguments.append(msg)
            sub = FakeSub(FakeHandle(message, {}))
            sub.callback = original_handler
            result = wrapped(FakeExecutor(), sub)
            sub.callback(result)
            self.assertIs(sub.callback, original_handler)
            self.assertEqual(callback_arguments, [message])
        finally:
            release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(observations, [True])

    def test_observer_failure_cannot_replace_original_result(self):
        errors = []
        def broken_observer(record):
            raise ValueError("observer")
        wrapped = probe.transparent_take_wrapper(FakeExecutor._take_subscription, broken_observer, errors)
        message = object()
        self.assertIs(wrapped(FakeExecutor(), FakeSub(FakeHandle(message, {}))), message)
        self.assertEqual(errors[0]["where"], "observer")
        self.assertIsNone(sys.getprofile())

    def test_publish_original_argument_return_and_exception(self):
        records, arguments = probe.Recorder(), []
        message, sentinel = object(), object()
        def original(msg):
            arguments.append(msg)
            return sentinel
        self.assertIs(probe.observed_publish(original, message, records.add, "one", "own", "aa"), sentinel)
        self.assertEqual(arguments, [message])
        self.assertTrue(records.events[0]["success"])
        error = ValueError("publish")
        def broken(msg):
            arguments.append(msg)
            raise error
        with self.assertRaises(ValueError) as caught:
            probe.observed_publish(broken, message, records.add, "one", "own", "aa")
        self.assertIs(caught.exception, error)
        self.assertEqual(arguments, [message, message])
        self.assertFalse(records.events[1]["success"])

    def test_publish_observer_error_does_not_mask_result_or_original_exception(self):
        message, sentinel, errors = object(), object(), []
        def failing_emit(*args, **kwargs):
            raise RuntimeError("observer failure")
        self.assertIs(probe.observed_publish(lambda msg: sentinel, message, failing_emit,
                                           "one", "own", "aa", errors), sentinel)
        error = ValueError("original publish failure")
        def failing_publish(msg):
            raise error
        with self.assertRaises(ValueError) as caught:
            probe.observed_publish(failing_publish, message, failing_emit, "one", "own", "aa", errors)
        self.assertIs(caught.exception, error)
        self.assertEqual([item["where"] for item in errors], ["publish_observer", "publish_observer"])


class AssociationTests(unittest.TestCase):
    def test_already_ended_take_cannot_match_future_publish(self):
        events = valid_events()
        events[4].update(entered_ns=10, exited_ns=20)
        result = probe.assess(events, "one")
        self.assertEqual(result["pairs"][0]["status"], "UNKNOWN")
        self.assertIn("publish_started_after_take_already_ended", result["pairs"][0]["reasons"])

    def test_missing_bool_and_reversed_take_clocks_are_unknown(self):
        for fields in ({"entered_ns": None}, {"exited_ns": True},
                       {"entered_ns": 220, "exited_ns": 210},
                       {"entered_ns": 200, "exited_ns": 5000}):
            with self.subTest(fields=fields):
                events = valid_events()
                events[4].update(fields)
                result = probe.assess(events, "one")
                self.assertEqual(result["pairs"][0]["status"], "UNKNOWN")
                self.assertTrue(any("take_" in reason for reason in result["pairs"][0]["reasons"]))

    def test_missing_and_reversed_publish_clocks_are_unknown(self):
        events = valid_events()
        del events[2]["before"]["monotonic_before_ns"]
        self.assertEqual(probe.assess(events, "one")["candidate_count"], 0)
        events = valid_events()
        events[2]["after"]["monotonic_before_ns"] = 50
        result = probe.assess(events, "one")
        self.assertIn("publish_monotonic_window_reversed", result["pairs"][0]["reasons"])
        self.assertEqual(result["candidate_count"], 0)

    def test_take_overlapping_synchronous_publish_is_not_falsely_rejected(self):
        events = valid_events()
        events[4].update(entered_ns=90, exited_ns=105)
        # Publish is [100,111], so take [90,105] ends before publish returns.
        result = probe.assess(events, "one")
        self.assertEqual(result["pairs"][0]["status"], "OBSERVED_CANDIDATE")

    def test_identical_payloads_remain_distinct_candidates_without_header_matching(self):
        result = probe.assess(valid_events(), "one")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual([item["publish_event_indices"] for item in result["pairs"]], [[2], [3]])
        self.assertTrue(all(item["status"] == "OBSERVED_CANDIDATE" for item in result["pairs"]))
        self.assertNotIn("KNOWN", str(result))

    def test_competing_controlled_and_graph_writer_rejects_even_disjoint_windows(self):
        events = valid_events()
        events[0]["writers"].append("competitor")
        events[1]["publishers"].append({"node_name": "competitor", "gid_hex": "bb"})
        result = probe.assess(events, "one")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["unknown_count"], 2)
        self.assertIn("controlled_writer_count_not_one", result["pairs"][0]["reasons"])
        self.assertIn("observed_competing_or_missing_writer", result["pairs"][0]["reasons"])

    def test_duplicate_timestamp_outside_window_typed_mismatch_and_missing_info(self):
        for mutate, expected in [
            (lambda e: e[5]["metadata"].update(source_timestamp=1005), "repeated_dds_source_timestamp"),
            (lambda e: e[4]["metadata"].update(source_timestamp=999999), "source_not_in_exactly_one_publish_window"),
            (lambda e: e[4]["message_fields"]["fields"][0].update(value=43), "whole_message_typed_fields_mismatch"),
            (lambda e: e[4].update(metadata={}), "missing_or_invalid_dds_source_timestamp"),
        ]:
            with self.subTest(expected=expected):
                events = valid_events()
                mutate(events)
                result = probe.assess(events, "one")
                self.assertIn(expected, result["pairs"][0]["reasons"])
                self.assertEqual(result["pairs"][0]["status"], "UNKNOWN")

    def test_overlapping_windows_and_clock_inconsistency_reject(self):
        events = valid_events()
        events[3]["before"] = at(1008, 108)
        result = probe.assess(events, "one")
        self.assertEqual(result["candidate_count"], 0)
        self.assertIn("overlapping_or_unordered_publish_windows", result["pairs"][0]["reasons"])
        events = valid_events()
        events[3]["after"] = at(999999, 1110)
        result = probe.assess(events, "one", offset_tolerance_ns=10)
        self.assertIn("realtime_monotonic_anchors_inconsistent", result["pairs"][0]["reasons"])

    def test_sparse_graph_or_lifecycle_coverage_and_unknown_publish_writer_reject(self):
        events = valid_events()
        events[-1]["recorded_monotonic_ns"] += 300000000
        result = probe.assess(events, "one")
        self.assertIn("graph_poll_gap_or_time_order_violation", result["pairs"][0]["reasons"])
        events = valid_events()
        events[-1]["recorded_monotonic_ns"] = 0
        result = probe.assess(events, "one")
        self.assertIn("graph_or_lifecycle_does_not_bracket_data", result["pairs"][0]["reasons"])
        events = valid_events()
        events[2]["writer_token"] = "uncontrolled"
        result = probe.assess(events, "one")
        self.assertIn("uncontrolled_publish_writer", result["pairs"][0]["reasons"])


class FastDDSVersionTests(unittest.TestCase):
    def setUp(self):
        self.config = (Path(__file__).parent / "version_metadata01" /
                       "listener_A01_fastrtps-config-version.cmake").read_bytes()
        self.library = "/root/uav_humble22/fastdds_listener_A01/install/lib/libfastrtps.so.2.6.12"

    def mapped(self, path=None):
        return "1000-2000 r-xp 00000000 00:01 123 " + (path or self.library)

    def test_actual_cmake_metadata_parses_exact_release_with_architecture_suffix_code(self):
        self.assertEqual(probe.parse_cmake_package_version(self.config.decode("utf-8")), "2.6.12")
        self.assertIn(b'${PACKAGE_VERSION} (${installedBits}bit)', self.config)

    def test_actual_mapped_prefix_selects_its_pinned_non_ament_config(self):
        reads = []
        def read(path):
            reads.append(path)
            return self.config
        result = probe.fastdds_binding([self.mapped(), self.mapped()], read)
        self.assertTrue(result["gate_passed"])
        self.assertEqual(reads, ["/root/uav_humble22/fastdds_listener_A01/install/share/fastrtps/cmake/fastrtps-config-version.cmake"])
        self.assertEqual(result["cmake_version_sha256"], probe.EXPECTED_FASTDDS_CMAKE_SHA256)
        self.assertEqual(result["mapped_library_version"], "2.6.12")

    def test_wrong_release_or_same_version_changed_bytes_fail_closed(self):
        for data, reason in [
            (self.config.replace(b'"2.6.12"', b'"2.14.7"'), "cmake_package_release_differs"),
            (self.config + b"\n# different metadata\n", "cmake_version_original_bytes_differ"),
        ]:
            with self.subTest(reason=reason):
                result = probe.fastdds_binding([self.mapped()], lambda path: data)
                self.assertFalse(result["gate_passed"])
                self.assertIn(reason, result["errors"])
        result = probe.fastdds_binding([self.mapped(self.library.replace("2.6.12", "2.14.7"))],
                                       lambda path: self.config)
        self.assertFalse(result["gate_passed"])
        self.assertIn("mapped_library_release_differs", result["errors"])

    def test_absent_multiple_deleted_or_unversioned_maps_cannot_use_unrelated_config(self):
        for entries in ([], [self.mapped(), self.mapped("/opt/ros/humble/lib/libfastrtps.so.2.6.12")],
                        [self.mapped() + " (deleted)"],
                        [self.mapped(self.library.removesuffix(".2.6.12"))]):
            with self.subTest(entries=entries):
                reads = []
                def forbidden_read(path):
                    reads.append(path)
                    raise AssertionError("Invalid map must not select an unrelated version config")
                result = probe.fastdds_binding(entries, forbidden_read)
                self.assertFalse(result["gate_passed"])
                self.assertEqual(reads, [])

    def test_duplicate_missing_and_unreadable_cmake_release_are_rejected(self):
        for text in ('# set(PACKAGE_VERSION "2.6.12")\n',
                     'set(PACKAGE_VERSION "2.6.12")\nset(PACKAGE_VERSION "2.14.7")\n'):
            with self.assertRaises(ValueError):
                probe.parse_cmake_package_version(text)
        def missing(path):
            raise FileNotFoundError(path)
        result = probe.fastdds_binding([self.mapped()], missing)
        self.assertFalse(result["gate_passed"])
        self.assertTrue(result["errors"][0].startswith("cmake_version_read_or_parse_failed:"))


class CompleteTypedFieldTests(unittest.TestCase):
    def test_each_of_ten_typed_fields_changes_equality_even_with_identical_raw_bytes(self):
        for path, kind in probe.POSE_FIELD_SCHEMA:
            with self.subTest(path=path):
                message = fake_pose_stamped()
                owner = message
                parts = path.split(".")
                for attribute in parts[:-1]:
                    owner = getattr(owner, attribute)
                old = getattr(owner, parts[-1])
                setattr(owner, parts[-1], old + ("x" if kind == "string" else 1))
                events = valid_events()
                events[4]["message_fields"] = probe.pose_stamped_fields(message)
                result = probe.assess(events, "one")
                self.assertEqual(result["pairs"][0]["status"], "UNKNOWN")
                self.assertIn("whole_message_typed_fields_mismatch", result["pairs"][0]["reasons"])

    def test_float64_signed_zero_nan_payload_sign_and_infinity_bits_are_preserved(self):
        for bits in ("0000000000000000", "8000000000000000", "7ff8000000000001",
                     "7ff8000000000002", "fff8000000000001", "7ff0000000000001",
                     "7ff0000000000000", "fff0000000000000"):
            with self.subTest(bits=bits):
                message = fake_pose_stamped()
                message.pose.position.y = struct.unpack(">d", bytes.fromhex(bits))[0]
                fields = probe.pose_stamped_fields(message)
                self.assertTrue(probe.valid_pose_stamped_fields(fields))
                self.assertEqual(fields["fields"][4]["bits_be_hex"], bits)
        for left, right in (("0000000000000000", "8000000000000000"),
                            ("7ff8000000000001", "7ff8000000000002")):
            events = valid_events()
            events[2]["message_fields"]["fields"][4]["bits_be_hex"] = left
            events[4]["message_fields"]["fields"][4]["bits_be_hex"] = right
            self.assertEqual(probe.assess(events, "one")["pairs"][0]["status"], "UNKNOWN")

    def test_actual_cdr_padding_difference_does_not_override_full_typed_equality(self):
        import json
        fixture = json.loads((Path(__file__).parent / "native02_cdr_padding_review.json").read_bytes())
        first = fixture["pairs"][0]
        self.assertEqual(first["different_byte_offsets"], [48, 49, 50, 51])
        self.assertTrue(first["differences_only_in_padding"])
        self.assertTrue(first["all_typed_fields_equal"])
        events = valid_events()
        events[2]["payload_hex"] = first["publish_payload_hex"]
        events[4]["payload_hex"] = first["take_payload_hex"]
        self.assertEqual(events[2]["message_fields"]["fields"], first["publish_cdr_structure"]["fields"])
        self.assertEqual(events[4]["message_fields"]["fields"], first["take_cdr_structure"]["fields"])
        self.assertNotEqual(events[2]["payload_hex"], events[4]["payload_hex"])
        self.assertEqual(probe.assess(events, "one")["pairs"][0]["status"], "OBSERVED_CANDIDATE")

    def test_missing_fields_bool_integers_and_partial_float_bits_are_unknown(self):
        for mutate in (lambda value: value["fields"].pop(),
                       lambda value: value["fields"][0].update(value=True),
                       lambda value: value["fields"][3].update(bits_be_hex="00"),
                       lambda value: value["fields"][2].update(utf8_hex="00")):
            events = valid_events()
            mutate(events[4]["message_fields"])
            self.assertEqual(probe.assess(events, "one")["pairs"][0]["status"], "UNKNOWN")

    def test_snapshot_is_of_original_publish_argument_and_observer_failure_preserves_call(self):
        recorder, errors = probe.Recorder(), []
        message, arguments, sentinel = fake_pose_stamped(), [], object()
        def original(msg):
            arguments.append(msg)
            return sentinel
        returned = probe.observed_publish(original, message, recorder.add, "one", "own", "raw",
                                          errors, message_snapshotter=probe.pose_stamped_fields)
        self.assertIs(returned, sentinel)
        self.assertEqual(arguments, [message])
        self.assertEqual(recorder.events[0]["message_fields"], probe.pose_stamped_fields(message))
        def broken_snapshot(msg):
            raise ValueError("observer only")
        self.assertIs(probe.observed_publish(original, message, recorder.add, "one", "own", "raw",
                                             errors, message_snapshotter=broken_snapshot), sentinel)
        self.assertEqual(arguments, [message, message])
        self.assertEqual(errors[0]["where"], "publish_fields_observer")


if __name__ == "__main__":
    unittest.main()
