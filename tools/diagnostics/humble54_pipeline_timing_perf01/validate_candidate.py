"""Bounded Windows synthetic validation, writing only this isolated directory."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import unittest

import test_candidate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def bindings():
    paths = [HERE / name for name in ("build_candidate.py", "indexed_reduction.py",
                                      "reducer_candidate.py", "test_candidate.py", "validate_candidate.py")]
    paths += [test_candidate.BASE / "reducer.py", test_candidate.PROBE,
              test_candidate.BASE / "test_bench.py"]
    return [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]


def main():
    started = datetime.now(timezone.utc).isoformat()
    before = bindings()
    stream = io.StringIO()
    test_candidate.DifferentialTests.comparisons = 0
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_candidate.DifferentialTests)
    result = unittest.TextTestRunner(verbosity=2, stream=stream).run(suite)
    benchmark = test_candidate.benchmark() if result.wasSuccessful() else None
    after = bindings()
    log = stream.getvalue()
    (HERE / "validation_windows01.log").write_text(log, encoding="utf-8", newline="\n")
    receipt = {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
               "scope": "ISOLATED_SYNTHETIC_DIFFERENTIAL_ONLY_NOT_REAL_TRACE_EQUIVALENCE",
               "native_started": False, "real_trace_or_bag_or_model_read": False,
               "fixed07_modified": False, "c7_assess_unchanged": True,
               "passed": result.wasSuccessful() and before == after,
               "test_count": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "whole_output_differential_comparisons": test_candidate.DifferentialTests.comparisons,
               "all_bound_sources_unchanged_during_test": before == after,
               "source_bindings": after, "synthetic_benchmark": benchmark,
               "test_log_sha256": hashlib.sha256(log.encode("utf-8")).hexdigest(),
               "real_trace_equivalence": "NOT_TESTED_WAIT_FOR_ORIGINAL_FULLPERSON_CLOSURE_AND_SERIAL_REDUCTION",
               "physical_e2e": "NOT_OBSERVED", "formal_progress": "0/280_UNCHANGED"}
    path = HERE / "validation_windows01.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, ensure_ascii=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
