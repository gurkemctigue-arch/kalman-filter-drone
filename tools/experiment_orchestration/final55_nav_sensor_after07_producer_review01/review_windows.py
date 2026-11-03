"""Independent Windows/source review using synthetic evaluator objects only."""
from __future__ import annotations
import ast
from contextlib import redirect_stdout
from datetime import datetime, timezone
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

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "tools/experiment_orchestration/final55_nav_sensor_after07_producer01"
PRODUCER_SHA = "e1c439d51a5ae6569ae7efe34b3eb899228977a2fbf27d9d1f3bf2aa88bd3f75"
INPUTS = []


def small(path):
    before = path.stat()
    assert path.is_file() and before.st_size <= 2 * 1024**2
    raw = path.read_bytes()
    after = path.stat()
    assert len(raw) == before.st_size and (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    INPUTS.append({"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return raw


def extra_cases(tests):
    p = tests.p
    fixture = tests.ProducerTests()
    cases = []
    for mutation in ("bool_exit", "changed_argv", "missing_report"):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            b, t, r, tb, output, original_invoke, calls, planned = fixture.nav_fixture(tmp)
            def invoke(command, log, timeout):
                execution = original_invoke(command, log, timeout)
                if mutation == "bool_exit": execution["returncode"] = False
                if mutation == "changed_argv": execution["command"] = ["SYNTHETIC_UNREGISTERED_ARGV"]
                if mutation == "missing_report": Path(command[-1]).unlink()
                return execution
            report = p.run_navigation(b, t, r, tb, output, invoke=invoke)
            assert report["status"] == "ERROR" and report["attempted"] == 1
            assert len(report["not_attempted"]) == 27 and len(calls["invocations"]) == 1
            assert calls["validator"] == [] and not (output / "navigation_complete.json").exists()
            cases.append({"case": mutation, "result": "STOPPED_WITHOUT_RETRY_OR_COMPLETION"})
    with tempfile.TemporaryDirectory() as tmp:
        b, t, tb, contract, manifest, output, loader, calls, original = fixture.sensor_fixture(tmp)
        def rejected(*args):
            raise ValueError("INDEPENDENT_SYNTHETIC_RUNNER_REJECTION")
        b.v4.read_sensor_input_evidence_manifest = rejected
        report = p.run_sensor(b, t, tb, contract, manifest, output, module_loader=loader)
        assert report["status"] == "ERROR" and "RUNNER_REJECTION" in report["error"]
        assert p.load(output / "sensor4_api_report.json") == original
        assert not (output / "sensor4_runner_binding.json").exists()
        assert original["per_slot"][0]["original_status"] == "FAIL" and original["per_slot"][0]["identity"] is None
        cases.append({"case": "sensor_runner_rejects", "result": "RAW_API_FAIL_NULL_RETAINED_NO_COMPLETION"})
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        final = root / "final"
        (final / "scripts").mkdir(parents=True)
        runner = final / "scripts/run_reliability_v4.py"
        runner.write_text("# synthetic original validator never executed\n", encoding="utf-8")
        target = {"frozen_root": str(final), "source_hashes": {"scripts/run_reliability_v4.py": p.sha(runner)}}
        target_binding = tests.put(root / "target.json", target)
        cached = types.ModuleType("run_reliability_v4")
        cached.__file__ = str(root / "wrong_root/scripts/run_reliability_v4.py")
        with patch.object(p, "FINAL", final), patch.dict(sys.modules, {"run_reliability_v4": cached}), \
             patch.object(p, "fixed_module", side_effect=AssertionError("wrong-root import forbidden")):
            try:
                p.context(Path(target_binding["path"]), target_binding["sha256"])
            except ValueError as error:
                assert "another root" in str(error)
            else:
                raise AssertionError("Cached original validator root mismatch accepted")
        cases.append({"case": "cached_validator_wrong_root", "result": "REFUSED_BEFORE_MODULE_EXECUTION"})
    class Child:
        pid, returncode, waits = 707, None, 0
        def wait(self, timeout):
            self.waits += 1
            self.returncode = 7
            return 7
    child = Child()
    scans = [0]
    def group(pgid):
        scans[0] += 1
        if scans[0] == 1:
            return [{"pid": 707, "ppid": 11, "state": "R", "start_ticks": 123}]
        return []
    fake_signal = types.SimpleNamespace(SIGINT=2, SIGTERM=15, SIGKILL=9, SIG_IGN=1, signal=lambda *args: None)
    with tempfile.TemporaryDirectory() as tmp, patch.object(p, "signal", fake_signal), \
         patch.object(p, "process_group", side_effect=group), \
         patch.object(p.subprocess, "Popen", return_value=child) as popen:
        actual = p.run_command(["SYNTHETIC_COMMAND_NOT_EXECUTED"], Path(tmp) / "closed.log", 1800.0)
    assert popen.call_count == 1 and actual["returncode"] == 7
    assert actual["error"] == "Evaluator returned 7" and child.waits == 2
    assert actual["cleanup"]["remaining_group_members"] == []
    cases.append({"case": "nonzero_direct_exit", "result": "EXACT_INTEGER_EXIT_RETAINED_SAME_HANDLE_CLEANED"})
    return cases


def main():
    prepared = json.loads(small(SOURCE / "prepared_validation01.json"))
    assert prepared["prepared_sources"]["producer.py"] == PRODUCER_SHA
    for relative, expected in prepared["prepared_sources"].items():
        raw = small(SOURCE / relative)
        assert hashlib.sha256(raw).hexdigest() == expected
        if relative.endswith(".py"):
            ast.parse(raw.decode("utf-8-sig"), feature_version=(3, 10))
    original_sources = {}
    for relative, expected in prepared["unchanged_original_source_hashes"].items():
        raw = small(ROOT / relative)
        actual = hashlib.sha256(raw).hexdigest()
        assert actual == expected, relative
        original_sources[relative] = actual
        ast.parse(raw.decode("utf-8-sig"), feature_version=(3, 10))
    spec = importlib.util.spec_from_file_location("independent_after07_producer_tests", SOURCE / "test_producer.py")
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
    stream = io.StringIO()
    with redirect_stdout(io.StringIO()):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    assert result.wasSuccessful(), stream.getvalue()
    cases = extra_cases(tests)
    assert all(hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected
        for relative, expected in prepared["prepared_sources"].items())
    receipt = {
        "schema_version": 1, "status": "PASS_WINDOWS_SOURCE_AND_SYNTHETIC_REVIEW_NOT_NATIVE_EXECUTION",
        "created_utc": datetime.now(timezone.utc).isoformat(), "reviewer": "/root/continuation06_preparation",
        "producer_sha256": PRODUCER_SHA, "prepared_sources": prepared["prepared_sources"],
        "unchanged_original_source_hashes": original_sources, "all_reviewed_source_unchanged": True,
        "author_tests_independently_run": {"tests_run": result.testsRun, "failures": len(result.failures),
            "errors": len(result.errors), "skipped": len(result.skipped), "output": stream.getvalue()},
        "independent_cases": cases,
        "source_review": {
            "actual_apis": "context loads the target's actual cold final55 builder and its runner; fixed source pins and original target_snapshot revalidate source/protocol. Function names and signatures match the original APIs inspected.",
            "navigation": "navigation_registration_inputs reconstructs all 28 original registered commands and report paths. Each exact argv is invoked once serially with its original evaluation_timeout_s; actual integer exit, UTC, closed log SHA and owned-child cleanup retained. Any failure stops remaining slots without retry.",
            "no_overwrite": "Receipt root must be new, canonical and external to final/original source and original evidence roots. Each registered new report plus all three sidecars is checked absent immediately before its one invocation; logs and receipts use exclusive creation.",
            "final_manifest": "Completion uses exact original all28 schema. Original read_navigation_reevaluation_manifest is called last and rechecks all 28 report/terminal/source/helper/physical identity/command/chronology/numeric structures before returning the core12 or extension16 subset. Validator rejection retains candidate files with ERROR.",
            "sensor": "Exact target descriptor contract/module feed evaluate_development_manifest. Its actual output is saved verbatim before original runner read_sensor_input_evidence_manifest independently recomputes and binds all four cells. Raw FAIL/null/INCOMPLETE/NOT_APPLICABLE remain; no extraction, image observation, review or PASS manufactured.",
            "process_cleanup": "Existing original SITL lock and native idle guard wrap execution. Native subreaper is required; only owned start_new_session process groups receive TERM10/KILL5. Direct Popen exit status is never consumed by adopted-descendant reaping, and the same handle is waited even after metadata acquisition failure. Cleanup faults prevent success.",
            "boundaries": "No new threshold, timeout extension, flight, owner, trigger, retry, readiness or formal admission. Future final55 target/registration/contract artifacts are not synthesized during preparation.",
        },
        "blocking_findings": [],
        "execution_conclusion": "SOURCE_PREPARATION_REVIEW_PASS_ONLY; ACTUAL_FINAL55_COLD_TARGET_AND_REGISTERED_INPUTS_AND_NATIVE_IDLE_LOCK_STILL_REQUIRED",
        "actual_navigation_evaluator_executions": 0, "actual_sensor_api_executions": 0,
        "image_reviews_created": 0, "real_bag_or_model_payload_reads": 0,
        "native_wsl_launches": 0, "author_or_original_source_changes": 0,
        "formal_admission": False,
        "remaining_actual_checks": ["Collector position and all native children must actually finish", "Positive actual measurement/budget and real final55 staging/cold build", "Actual target/prospective registration/contract/manifest canonical SHA bindings", "28 actual evaluator integer exits with original reports/sidecars preserved", "Actual original full28 and sensor4 validators, with all evidence insufficiency and algorithm failures retained", "Actual native child-group cleanup and residual inspection"],
        "small_inputs_read": INPUTS,
    }
    path = HERE / "independent_review01.json"
    path.write_text(json.dumps(receipt, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(path), "producer_sha256": PRODUCER_SHA,
        "author_tests": result.testsRun, "independent_cases": len(cases), "blocking_findings": 0,
        "native_executions": 0}, ensure_ascii=True))


if __name__ == "__main__":
    main()
