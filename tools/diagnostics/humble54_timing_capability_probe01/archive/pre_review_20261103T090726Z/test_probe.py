"""No ROS imports, subprocesses, large data or native execution."""
import importlib.util
from pathlib import Path
import sys
import threading
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
         "metadata": {"source_timestamp": 1005}, "payload_hex": "abcd"},
        {"kind": "take", "phase": "one", "event_index": 5, "capture_status": "CAPTURED",
         "metadata": {"source_timestamp": 2005}, "payload_hex": "abcd"},
        {"kind": "controlled_writers", "phase": "one", "writers": ["own"]},
        {"kind": "graph", "phase": "one", "publishers": [{"node_name": "own", "gid_hex": "aa"}]},
    ]
    for index, event in enumerate(events):
        event["recorded_monotonic_ns"] = index * 1000
    return events


class TransparencyTests(unittest.TestCase):
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

    def test_duplicate_timestamp_outside_window_byte_mismatch_and_missing_info(self):
        for mutate, expected in [
            (lambda e: e[5]["metadata"].update(source_timestamp=1005), "repeated_dds_source_timestamp"),
            (lambda e: e[4]["metadata"].update(source_timestamp=999999), "source_not_in_exactly_one_publish_window"),
            (lambda e: e[4].update(payload_hex="different"), "whole_message_bytes_mismatch"),
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


if __name__ == "__main__":
    unittest.main()
