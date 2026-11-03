"""Independent small Windows-only review; original data and native stay unused."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SOURCE = HERE / "stage_after_refresh.py"
TESTS = HERE / "test_stage_after_refresh.py"
EXPECTED = "c83cc666cdf8924f53033446c075d284eeccaafe5f9cbd95fb9253d8262f8e12"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert sha(SOURCE) == EXPECTED
    test_sha = sha(TESTS)
    spec = importlib.util.spec_from_file_location("independent_capacity_stage_fixtures", TESTS)
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    s = fixture_module.s
    tests = fixture_module.StageRefreshTests()
    original_pins = {str(path): sha(path) for path in (s.LEGACY, s.REFRESH, fixture_module.refresh.MEASUREMENT,
                    fixture_module.legacy.BASE, fixture_module.legacy.PRIOR)}
    result = subprocess.run([sys.executable, "-B", str(TESTS)], capture_output=True, timeout=60)
    author_output = result.stdout + result.stderr
    (HERE / "independent_author_suite02.log").write_bytes(author_output)
    assert result.returncode == 0 and b"Ran 10 tests" in author_output and b"OK" in author_output
    checks = []
    mutations = [
        ("wrong_source_path", lambda t: t["source"].update(path=str(HERE / "foreign.py"))),
        ("wrong_commit", lambda t: t.update(commit="FOREIGN")),
        ("boolean_owner_pid", lambda t: t["owner_identity"].update(pid=True)),
        ("one_child_boot_differs", lambda t: t["steps"][1].update(identity={**t["steps"][1]["identity"], "boot_id": "00000000-0000-0000-0000-000000000000"})),
        ("nonzero_terminal", lambda t: t.update(returncode=2)),
        ("boolean_terminal_exit", lambda t: t.update(returncode=False)),
        ("automatic_retry", lambda t: t.update(automatic_retry=True)),
        ("formal_admission", lambda t: t.update(formal_admission=True)),
        ("erased_original_error", lambda t: t["original_execution_window"].update(errors=[])),
        ("wrong_negative_budget_sha", lambda t: t["original_negative_budget"].update(sha256="0" * 64)),
        ("wrong_R0_sha", lambda t: t["original_R0_candidate"].update(sha256="0" * 64)),
        ("missing_derived_binding", lambda t: t["derived_input_bindings"].pop()),
        ("reordered_derived_binding", lambda t: t["derived_input_bindings"].reverse()),
        ("reordered_refresh_steps", lambda t: t["steps"].reverse()),
        ("missing_original_family_binding", lambda t: t.update(input_bindings=[r for r in t["input_bindings"] if r != t["original_failure_terminal"]])),
    ]
    with tempfile.TemporaryDirectory(prefix="independent_capacity_stage_") as temporary:
        f = tests.fixture(temporary)
        for name, mutate in mutations:
            value = deepcopy(f.term)
            mutate(value)
            try:
                tests.validate(f, value)
            except (ValueError, TypeError, KeyError) as error:
                checks.append({"name": name, "pass": True, "rejection": type(error).__name__})
            else:
                raise AssertionError("Invalid terminal accepted: " + name)
        safe = {"stage": f.root / "independent_new_stage", "receipt": f.root / "independent_new_receipt"}
        before = {str(path): sha(path) for path in f.root.rglob("*") if path.is_file()}
        s.validate_stage_outputs(safe, f.context, f.terminal_binding)
        checks.append({"name": "fresh_separate_outputs_accepted_without_writing", "pass": True})
        protected = [s.ROOT, f.p["frozen"], f.p["receipt"], f.q["receipt"], f.r["receipt"],
                     f.p["tools"], f.p["sizes"], f.p["calibration"], f.p["budget"].parent]
        for index, root in enumerate(protected):
            for role in ("stage", "receipt"):
                paths = dict(safe)
                paths[role] = root / ".__independent_stage_output_refusal01__"
                assert not paths[role].exists()
                try:
                    s.validate_stage_outputs(paths, f.context, f.terminal_binding)
                except ValueError as error:
                    assert "protected evidence" in str(error)
                    checks.append({"name": "protected_%02d_%s" % (index, role), "pass": True})
                else:
                    raise AssertionError("Protected output subtree accepted")
        assert {str(path): sha(path) for path in f.root.rglob("*") if path.is_file()} == before
        receipt = safe["receipt"]
        admission = receipt.with_name(receipt.name + ".admission.json")
        outcome = admission.with_name(admission.stem + ".driver_outcome.json")
        for name, sidecar in (("admission", admission), ("driver_outcome", outcome)):
            sidecar.write_bytes(b"independently owned synthetic preexisting sidecar\n")
            try:
                s.validate_stage_outputs(safe, f.context, f.terminal_binding)
            except ValueError as error:
                assert "Fresh explicit staging output or sidecar" in str(error)
                checks.append({"name": "preexisting_" + name + "_refused", "pass": True})
            else:
                raise AssertionError("Existing sidecar accepted")
            sidecar.unlink()
        collisions = [("stage_equals_receipt", receipt), ("stage_equals_admission", admission),
                      ("stage_equals_driver_outcome", outcome), ("stage_inside_receipt", receipt / "nested"),
                      ("stage_inside_admission", admission / "nested"), ("stage_inside_driver_outcome", outcome / "nested")]
        for name, stage in collisions:
            try:
                s.validate_stage_outputs({"stage": stage, "receipt": receipt}, f.context, f.terminal_binding)
            except ValueError as error:
                assert "mutually independent" in str(error)
                checks.append({"name": name, "pass": True})
            else:
                raise AssertionError("Conflicting output accepted: " + name)
        try:
            s.validate_stage_outputs({"stage": safe["stage"], "receipt": safe["stage"] / "nested"}, f.context, f.terminal_binding)
        except ValueError as error:
            assert "mutually independent" in str(error)
            checks.append({"name": "receipt_inside_stage_refused", "pass": True})
        else:
            raise AssertionError("Receipt inside stage accepted")

    assert sha(SOURCE) == EXPECTED and sha(TESTS) == test_sha
    assert {str(path): sha(path) for path in map(Path, original_pins)} == original_pins
    assert s.PRODUCTION_ENABLED is False and s.REGISTERED_INPUTS == {}
    receipt = {"reviewed_utc": datetime.now(timezone.utc).isoformat(),
               "status": "PASS_DISABLED_CANDIDATE_PREPARATION_ONLY_NOT_EXECUTED",
               "source": {"path": str(SOURCE), "bytes": SOURCE.stat().st_size, "sha256": EXPECTED},
               "author_tests": {"tests": 10, "exit_code": result.returncode, "sha256": test_sha,
                                "captured_output_sha256": hashlib.sha256(author_output).hexdigest()},
               "independent_checks": checks, "original_source_pins_unchanged": original_pins,
               "resolved_finding": "New candidate output isolation rejects stage, receipt and sidecars inside original7, continuation6, refresh3 and other protected evidence trees.",
               "supersedes": {"path": "independent_review01.json", "source_sha256": "c745c85530f8516eb7120954febf6d0fa20418e3ad482dc2db017f94c0b0cf88", "review_sha256": "35f97a3d97f2a318101ee24cda7c3c4d82d1120900867522799497393dd632f3"},
               "production_enabled": False, "registered_inputs": {}, "native_started": False,
               "real_bag_model_or_derived_read": False,
               "limits": ["Only Windows source and small temporary fixtures were inspected or executed.",
                          "No real positive budget exists or is registered by this review.",
                          "Positive capacity remains a historical snapshot, not current capacity or formal admission."]}
    target = HERE / "independent_review02.json"
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"status": receipt["status"], "source_sha256": EXPECTED, "author_tests": 10,
                      "independent_checks": len(checks), "receipt_sha256": sha(target)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
