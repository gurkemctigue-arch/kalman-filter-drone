"""Independent Windows synthetic equivalence review; never open native traces."""
from copy import deepcopy
from datetime import datetime, timezone
import ast
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PERF = HERE.parent
BASE = PERF.parent / "humble54_pipeline_timing_bench01"
PROBE = PERF.parent / "humble54_timing_capability_probe01/probe.py"
sys.path[:0] = [str(PERF), str(BASE)]
import reducer as baseline
import reducer_candidate as candidate
from indexed_reduction import EventIndex, OutcomeIndex, read_events
from test_bench import fixture


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    tracked = [PERF / name for name in ("reducer_candidate.py", "indexed_reduction.py", "build_candidate.py", "test_candidate.py")]
    tracked += [BASE / "reducer.py", PROBE]
    before = [pin(path) for path in tracked]
    counts = {"event_index_queries": 0, "outcome_index_queries": 0, "navigation_predicates": 0,
              "stream_cases": 0, "whole_outputs": 0, "multifile_outputs": 0}
    missing = object()
    values = [missing, None, "", "token", "absent", 0, 1, True, False, 1.0, [], [1], {}, {"x": 1}]
    for kind, key in EventIndex.SPECS:
        rows = [{"kind": kind, **({key: deepcopy(value)} if value is not missing else {}), "ordinal": index}
                for index, value in enumerate(values)]
        rows += deepcopy(rows[:5])
        indexed = EventIndex(rows)
        for value in values[1:]:
            expected = [row for row in rows if row["kind"] == kind and row.get(key) == value]
            assert indexed.find(kind, key, value) == expected
            counts["event_index_queries"] += 1
    rows = [{"status": status, **({"rgb_token": deepcopy(value)} if value is not missing else {})}
            for status in ("UNKNOWN", "CANDIDATE_SOFTWARE_LATENCY") for value in values]
    indexed = OutcomeIndex(rows)
    for value in values[1:]:
        assert indexed.find(value) == [row for row in rows if row.get("rgb_token") == value
                                      and row["status"] == "CANDIDATE_SOFTWARE_LATENCY"]
        counts["outcome_index_queries"] += 1

    rng = random.Random(771803)
    processes = [None, "estimator", "other", 1, True, ["p"], {"p": 1}]
    for process in processes:
        events = [{"kind": kind, "process": deepcopy(owner), "recorded_monotonic_ns": stamp, "accepted": accepted}
                  for owner in processes for kind in ("noise", "navigation_clear", "navigation_update")
                  for stamp in (-1, 0, 1, 1.5, 2, 3, 4) for accepted in (True, False, 1)]
        # The reducer always supplies time-sorted data; Python's stable sort preserves ties.
        events.sort(key=lambda row: row["recorded_monotonic_ns"])
        indexed = EventIndex(events)
        for begin, end in itertools.product((-1, 0, 1, 1.5, 2, 3, 4), repeat=2):
            expected = any(row.get("process") == process and begin < row["recorded_monotonic_ns"] < end
                           and (row["kind"] == "navigation_clear" or row["kind"] == "navigation_update"
                                and row.get("accepted") is True) for row in events)
            actual = indexed.navigation_replaced({"process": process, "recorded_monotonic_ns": begin},
                                                {"recorded_monotonic_ns": end})
            assert actual == expected
            counts["navigation_predicates"] += 1

    with tempfile.TemporaryDirectory(prefix="independent_perf_small_") as temporary:
        path = Path(temporary) / "synthetic.jsonl"
        valid_rows = [{"index": i, "text": "\u884c\u4eba", "flags": [None, True, 1.0]} for i in range(5)]
        encoded = [json.dumps(row, ensure_ascii=False).encode() for row in valid_rows]
        samples = [b"", b"\r", b"\n", b"\r\n", b"\r\r\n", b"{}\r\n{}\r{}\n",
                   b"\xef\xbb\xbf{}\n", b" \n", b"{}\r\ninvalid\r", b"{\n", b"{}\x0b{}",
                   b"{}\x0c{}", b"{}\x85{}", b"{}\x1c{}"]
        for _ in range(85):
            raw = rng.choice((b"", b"\r", b"\n", b"\r\n"))
            for row in encoded:
                raw += row + rng.choice((b"\r", b"\n", b"\r\n", b"\n\r", b"\r\r\n"))
            samples.append(raw + rng.choice((b"", b"{}", b"\r", b"\n", b" \n")))
        for raw in samples:
            path.write_bytes(raw)
            try:
                expected = [json.loads(line) for line in raw.splitlines() if line]
                expected_error = None
            except Exception as error:
                expected, expected_error = None, (type(error).__name__, str(error))
            for chunk in (1, 2, 3, 4, 7, 11, 31, 1024):
                bindings = []
                try:
                    observed = list(read_events([path], bindings, chunk_bytes=chunk))
                    observed_error = None
                except Exception as error:
                    observed, observed_error = None, (type(error).__name__, str(error))
                assert observed_error == expected_error, (raw, chunk, observed_error, expected_error)
                if expected_error is None:
                    assert observed == expected
                    assert bindings == [{"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}]
                counts["stream_cases"] += 1

        for field in ("snapshot_token", "rgb_token", "depth_token", "project_token"):
            for value in (None, 1, True, ["token"], {"token": 1}):
                events = fixture()[0]
                for event in events:
                    if field in event:
                        previous = event[field]
                        event[field] = deepcopy(value)
                        if field in ("rgb_token", "depth_token"):
                            for other in events:
                                if other.get("image_token") == previous:
                                    other["image_token"] = deepcopy(value)
                settings = dict(probe_path=PROBE, begin_ns=1000, end_ns=9000)
                preserved = deepcopy(events)
                assert candidate.reduce_events(events, **settings) == baseline.reduce_events(events, **settings), (field, value)
                assert events == preserved
                counts["whole_outputs"] += 1
        events = fixture()[0]
        paths = [Path(temporary) / (str(i) + ".jsonl") for i in range(4)]
        for index, path in enumerate(paths):
            separator = (b"\r", b"\n", b"\r\n", b"\n\r")[index]
            path.write_bytes(separator.join(json.dumps(row).encode() for row in events[index::4]))
        assert candidate.reduce_files(paths, **settings) == baseline.reduce_files(paths, **settings)
        counts["multifile_outputs"] += 1

    # Reproduce the candidate in memory from its exact declared fixed07 source.
    builder = ast.parse((PERF / "build_candidate.py").read_text(encoding="utf8"))
    replacements = next(ast.literal_eval(node.value) for node in ast.walk(builder)
                        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "replacements" for target in node.targets))
    rebuilt = (BASE / "reducer.py").read_bytes().decode("utf8")
    for old, new in replacements:
        assert rebuilt.count(old) == 1
        rebuilt = rebuilt.replace(old, new)
    assert rebuilt.encode() == (PERF / "reducer_candidate.py").read_bytes()
    assert [pin(path) for path in tracked] == before
    receipt = {"verified_utc": datetime.now(timezone.utc).isoformat(), "status": "PASS_SMALL_SYNTHETIC_WINDOWS_REVIEW_ONLY",
               "scope": "NO_NATIVE_NO_REAL_TRACE_NO_BAG_NO_MODEL_NO_PERFORMANCE_CLAIM", "inputs": before,
               "independent_checks": counts, "candidate_exact_rebuild_in_memory": True, "sources_unchanged": True,
               "author_suite_observed": {"command": "python -B tools/diagnostics/humble54_pipeline_timing_perf01/test_candidate.py",
                                         "exit_code": 0, "tests": 11, "whole_output_comparisons": 131},
               "limits": ["All EventIndex navigation inputs are sorted by the reducer before indexing.",
                          "Independent stream cases use positive chunk_bytes and closed synthetic files.",
                          "Large recorded-trace equality and native performance remain unverified."]}
    (HERE / "receipt_windows01.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(receipt, ensure_ascii=True))


if __name__ == "__main__":
    main()
