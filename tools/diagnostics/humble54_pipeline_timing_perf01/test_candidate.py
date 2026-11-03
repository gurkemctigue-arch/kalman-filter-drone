"""Synthetic whole-output differential checks against unchanged fixed07.

No ROS, WSL, original bag, native trace, model, or recorded schema is loaded.
The fixed07 test module is imported only for its small fake-object fixture.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "humble54_pipeline_timing_bench01"
PROBE = HERE.parent / "humble54_timing_capability_probe01/probe.py"
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(HERE))
import reducer as baseline
import reducer_candidate as candidate
from indexed_reduction import EventIndex, OutcomeIndex, read_events
from test_bench import fixture


class DifferentialTests(unittest.TestCase):
    comparisons = 0

    def compare(self, events, **kwargs):
        before = deepcopy(events)
        settings = dict(probe_path=PROBE, begin_ns=1000, end_ns=9000, **kwargs)
        original = baseline.reduce_events(events, **settings)
        optimized = candidate.reduce_events(events, **settings)
        self.assertEqual(optimized, original)
        self.assertEqual(events, before, "neither implementation may mutate caller events")
        type(self).comparisons += 1
        return original

    def test_complete_and_unclean_native_outputs(self):
        events = fixture()[0]
        self.assertEqual(self.compare(events)["candidate_command_count"], 1)
        self.assertEqual(self.compare(events, native_complete=False)["candidate_command_count"], 0)

    def test_duplicates_remain_ambiguous_for_every_lookup(self):
        for kind in ("navigation_update", "navigation_project", "snapshot", "submit", "worker_start", "sensor_callback"):
            with self.subTest(kind=kind):
                events, emit, _ = fixture()
                duplicate = deepcopy(next(row for row in events if row["kind"] == kind))
                original_id = duplicate.pop("event_id")
                duplicate.pop("local_index")
                process, when = duplicate.pop("process"), duplicate.pop("recorded_monotonic_ns")
                duplicate.pop("kind")
                added = emit(process, kind, when, **duplicate)
                if kind == "navigation_update":
                    added["event_id"] = original_id
                self.assertEqual(self.compare(events)["candidate_command_count"], 0)

    def test_navigation_strict_boundaries_and_process_scope(self):
        for kind in ("navigation_clear", "navigation_update"):
            for when in (2099, 2100, 2101, 2299, 2300, 2301):
                for process in ("estimator", "controller"):
                    for accepted in (True, False, 1):
                        with self.subTest(kind=kind, when=when, process=process, accepted=accepted):
                            events, emit, _ = fixture()
                            emit(process, kind, when, accepted=accepted, source_frame_token="unrelated")
                            result = self.compare(events)
                            changed = process == "estimator" and 2100 < when < 2300 and (kind == "navigation_clear" or accepted is True)
                            self.assertEqual(result["candidate_command_count"], int(not changed))

    def test_global_failures_and_edge_gates_stay_unknown(self):
        def mutate(events, field, value):
            next(row for row in events if row["kind"] == field[0])[field[1]] = value
        cases = [(("process_start", "boot_id"), None),
                 (("observer_final", "trace_dropped"), 1),
                 (("executor_shutdown", "returned"), False),
                 (("process_final", "trace_errors"), ["synthetic"]),
                 (("fmu_scan", "publishers"), [{}]),
                 (("take", "capture_status"), "UNKNOWN"),
                 (("publish", "success"), False),
                 (("callback", "same_object_as_original_take"), False),
                 (("callback", "complete_typed_fields_match_take"), False)]
        for field, value in cases:
            with self.subTest(field=field):
                events = fixture()[0]
                mutate(events, field, value)
                self.assertEqual(self.compare(events)["candidate_command_count"], 0)
        events = fixture()[0]
        events[0]["event_id"] = events[1]["event_id"]
        self.assertEqual(self.compare(events)["candidate_command_count"], 0)

    def test_multiple_ticks_share_rgb_but_missing_rgb_stays_unknown(self):
        events, emit, edge = fixture()
        for index in range(18):
            edge("command", "controller", "adapter", 3000 + index * 20,
                 "command-extra-" + str(index), target_token="controller:received_state",
                 command_valid=True, command_mode=1 if index % 3 else 4)
        emit("detector", "sensor_callback", 4000, sensor="rgb", image_token="never-selected", entered_ns=4000)
        result = self.compare(events)
        self.assertEqual(result["received_rgb_count"], 2)
        self.assertEqual(result["rgb_with_candidate_count"], 1)
        self.assertGreater(result["candidate_command_count"], result["rgb_with_candidate_count"])
        self.assertEqual(result["rgb_opportunities"][1]["first_candidate_latency_ns"], None)

    def test_non_string_snapshot_tokens_use_legacy_equality_fallback(self):
        for value in (["jobA"], {"job": "A"}, 7, True, None):
            with self.subTest(value=value):
                events = fixture()[0]
                for row in events:
                    if "snapshot_token" in row:
                        row["snapshot_token"] = deepcopy(value)
                self.compare(events)

    def test_missing_keys_and_none_preserve_duplicate_semantics(self):
        rows = [{"kind": "snapshot"}, {"kind": "snapshot", "rgb_token": None},
                {"kind": "snapshot", "rgb_token": []}, {"kind": "snapshot", "rgb_token": "x"}]
        lookup = EventIndex(rows)
        for token in (None, [], "x", "absent", 7, True):
            self.assertEqual(lookup.find("snapshot", "rgb_token", token),
                             [r for r in rows if r["kind"] == "snapshot" and r.get("rgb_token") == token])

    def test_streamed_jsonl_exact_records_hashes_and_chunk_boundaries(self):
        rows = [{"field": "line-" + str(i), "unicode": "目标", "value": [i, None, True]} for i in range(9)]
        encoded = [json.dumps(row, ensure_ascii=False).encode("utf-8") for row in rows]
        for ending in (b"\n", b"\r\n", b"\r"):
            for trailing in (b"", ending):
                raw = ending.join([b"", *encoded[:4], b"", *encoded[4:]]) + trailing
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "synthetic.jsonl"
                    path.write_bytes(raw)
                    for chunk_bytes in (1, 2, 3, 7, 41, 1024):
                        bindings = []
                        self.assertEqual(list(read_events([path], bindings, chunk_bytes=chunk_bytes)), rows)
                        self.assertEqual(bindings, [{"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}])

    def test_streamed_empty_whitespace_and_invalid_records(self):
        for raw in (b"", b"\r\n\r\n", b" \n", b"{}\nnot-json", b'{"missing":'):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "synthetic.jsonl"
                path.write_bytes(raw)
                try:
                    expected = [json.loads(line) for line in raw.splitlines() if line]
                except Exception as error:
                    with self.assertRaises(type(error)):
                        list(read_events([path], [], chunk_bytes=1))
                else:
                    self.assertEqual(list(read_events([path], [], chunk_bytes=1)), expected)

    def test_multifile_outputs_and_trace_bindings_are_identical(self):
        events = fixture()[0]
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / (str(i) + ".jsonl") for i in range(3)]
            for index, path in enumerate(paths):
                path.write_bytes(b"\r\n".join(json.dumps(row).encode() for row in events[index::3]))
            settings = dict(probe_path=PROBE, begin_ns=1000, end_ns=9000)
            self.assertEqual(candidate.reduce_files(paths, **settings), baseline.reduce_files(paths, **settings))

    def test_deterministic_mutation_differential(self):
        rng = random.Random(20261103)
        for iteration in range(35):
            events, emit, _ = fixture()
            for index in range(rng.randint(1, 8)):
                emit(rng.choice(("detector", "estimator", "controller")), rng.choice(("noise", "navigation_update", "navigation_clear")),
                     rng.randint(1100, 8900), accepted=rng.choice((True, False, 1)), source_frame_token="synthetic-noise")
            rng.shuffle(events)
            with self.subTest(iteration=iteration):
                self.compare(events)


def synthetic_workload(noise=3500, commands=160):
    events, emit, edge = fixture()
    for index in range(noise):
        emit("replay", "synthetic_extra", 1200 + index % 5000)
    for index in range(commands):
        edge("command", "controller", "adapter", 3000 + index * 20,
             "extra-" + str(index), target_token="controller:received_state", command_valid=True, command_mode=1)
    return events


def benchmark():
    events = synthetic_workload()
    times, outputs = {}, {}
    for name, module in (("fixed07", baseline), ("candidate", candidate)):
        before = time.perf_counter()
        outputs[name] = module.reduce_events(events, probe_path=PROBE, begin_ns=1000, end_ns=9000)
        times[name] = time.perf_counter() - before
    if outputs["fixed07"] != outputs["candidate"]:
        raise AssertionError("synthetic benchmark outputs differ")
    return {"events": len(events), "commands": outputs["candidate"]["adapter_callback_count"],
            "times_seconds": times, "speedup": times["fixed07"] / times["candidate"],
            "scope": "SMALL_SYNTHETIC_WINDOWS_ONLY_NOT_NATIVE_PERFORMANCE", "whole_output_equal": True}


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DifferentialTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print(json.dumps({"comparisons": DifferentialTests.comparisons, "benchmark": benchmark()}, ensure_ascii=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
