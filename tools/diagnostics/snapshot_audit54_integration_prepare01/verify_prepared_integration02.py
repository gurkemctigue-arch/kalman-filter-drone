"""Windows small-file/AST verification and inert receipt-closure fixtures only."""
from __future__ import annotations

import argparse
import ast
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import traceback
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
LIMIT = 4 * 1024**2
EXPECTED_SCRIPT = "1062409c9ef2aee5c611831f5100db9ce081557570bd28859a057c7c00cec8cc"
EXPECTED_PRIOR_RECEIPT = "1c1f5cba9c068ce9ed21e5e4ab2dda9073150faeb18f36a7d83796da59ae7e3b"


def observe(path):
    path = Path(path)
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= LIMIT, str(path)
    raw = path.read_bytes()
    assert len(raw) <= LIMIT
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read_object(path):
    observe(path)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def project_modules():
    return sorted(name for name in sys.modules if name == "tools" or name.startswith(
        ("tools.", "uav_tracking", "uav_tracking_nodes", "uav_tracking_px4_adapter")))


def main():
    output = BASE / "windows_preparation_review02.json"
    with output.open("xb") as stream:
        report = {"schema_version": 1,
            "scope": "WINDOWS_AST_SMALL_PIN_CHECKS_AND_INERT_MAIN_RECEIPT_FIXTURES_ONLY",
            "started_utc": datetime.now(timezone.utc).isoformat(), "result": "INCOMPLETE",
            "native_execution_performed": False, "actual_tools_or_target_modules_imported": False,
            "actual_helper_or_adapter_called": False, "native_contract_created": False,
            "formal_or_safety_admission_created": False, "models_bags_or_large_telemetry_read": False,
            "project_modules_before": project_modules(), "verifier": observe(__file__)}
        code = 2
        try:
            prior_path = BASE / "windows_preparation_review01.json"
            report["prior_receipt_before"] = observe(prior_path)
            assert report["prior_receipt_before"]["sha256"] == EXPECTED_PRIOR_RECEIPT
            prior = read_object(prior_path)
            script = BASE / "audit_snapshot_contract_integration.py"
            report["script_before"] = observe(script)
            assert report["script_before"]["sha256"] == EXPECTED_SCRIPT
            raw = script.read_bytes()
            tree = ast.parse(raw, filename=str(script), feature_version=(3, 10))
            compile(tree, str(script), "exec")  # Syntax only; never execute the native module.
            functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
            source = raw.decode("utf-8")
            for fragment in (
                'report["plan_after"] == report["plan"]',
                'report["adapter_files_after"] == report["adapter_header"]["files"]',
                'driver.ROOT == AUDIT',
            ):
                assert fragment in source
            assert any(isinstance(handler.type, ast.Name) and handler.type.id == "BaseException"
                       for node in ast.walk(functions["main"]) if isinstance(node, ast.Try)
                       for handler in node.handlers)
            assert any(node.finalbody for node in ast.walk(functions["main"]) if isinstance(node, ast.Try))
            calls = [node.func.attr for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
            assert calls.count("create_contract") == calls.count("validate_snapshot") == 1
            assert not set(calls) & {"load_context", "load_original_guard", "load_core", "register",
                                     "execute_one", "run_one", "system", "Popen"}
            report["syntax_and_ast_gates"] = "PASSED_WITHOUT_NATIVE_MODULE_EXECUTION"

            # Re-read only the original named small files, including the fixed
            # bundle's five sources. No WSL executable or model/bag is opened.
            observations = {}
            named = {"bundle": prior["bundle"], "original_plan": prior["original_plan"]}
            for group in ("tools", "adapter_files", "freeze_metadata"):
                named.update({group + ":" + name: value for name, value in prior[group].items()})
            for row in prior["snapshots"]:
                named["snapshot:" + row["id"]] = row["original"]
            for name, expected in named.items():
                actual = observe(expected["path"])
                assert actual == expected, name
                observations[name] = actual
            report["named_small_inputs_before"] = observations
            plan = read_object(prior["original_plan"]["path"])
            canonical = hashlib.sha256(json.dumps({key: value for key, value in plan.items()
                if key != "plan_sha256"}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            assert canonical == plan["plan_sha256"] == "3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31"
            expected = {name: value for name, value in plan["source_hashes"].items()
                if name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/"))
                and PurePosixPath(name).suffix in {".py", ".sh", ".msg"}}
            for name in (plan["protocol"]["resources"]["person"]["model"], "config/dds_runtime_humble22.json"):
                expected[name] = plan["source_hashes"][name]
            snapshots = [read_object(row["original"]["path"]) for row in prior["snapshots"]]
            assert len(expected) == 187 and all(len(snapshot) == 204 and snapshot == snapshots[0]
                and len(set(snapshot) - set(expected)) == 17
                and all(snapshot.get(name) == value for name, value in expected.items()) for snapshot in snapshots)
            report["three_original_snapshot_static_mapping_checks"] = "PASSED_187_REGISTERED_PLUS_17_RETAINED_EXTRAS"

            # Execute only extracted receipt-writer functions with an inert
            # execute callback. Actual execute/load/helper/adapter functions are
            # not compiled into this namespace and cannot be called here.
            fixtures = BASE / "inert_receipt_closure02"
            fixtures.mkdir()  # Exclusive fixture namespace; preserve every output.
            selected = [functions[name] for name in ("require", "utc", "read_small", "binding", "main")]
            namespace = {"argparse": argparse, "datetime": datetime, "timezone": timezone,
                "hashlib": hashlib, "json": json, "os": os, "Path": Path, "sys": sys,
                "traceback": traceback, "LIMIT": LIMIT, "EXTERNAL": fixtures,
                "CONTRACT": fixtures / "never_created_contract.json", "__file__": str(script)}
            exec(compile(ast.Module(body=selected, type_ignores=[]), "<inert extracted receipt functions>", "exec"), namespace)
            cases = (("success", None, 0), ("ordinary_error", ValueError("inert fixture"), 2),
                     ("keyboard_interrupt", KeyboardInterrupt(), 130),
                     ("system_exit_zero", SystemExit(0), 2), ("system_exit_seven", SystemExit(7), 2))
            results = {}
            for name, error, expected_code in cases:
                destination = fixtures / (name + ".json")
                def inert_execute(record, selected_error=error):
                    record["fixture_only"] = True
                    if selected_error is not None:
                        raise selected_error
                    record["result"] = "INERT_FIXTURE_EXECUTE_RETURNED_NO_NATIVE_EXECUTION"
                namespace["execute"] = inert_execute
                arguments = [str(script), "--expected-self-sha256", EXPECTED_SCRIPT, "--output", str(destination)]
                with patch.object(sys, "argv", arguments), redirect_stdout(io.StringIO()):
                    returned = namespace["main"]()
                saved = read_object(destination)
                assert returned == saved["exit_code"] == expected_code
                assert saved["finished_utc"] and saved["fixture_only"] and not saved["formal_execution_authorized"]
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    assert saved["result"] == "INTERRUPTED_NO_FORMAL_ADMISSION"
                if isinstance(error, SystemExit):
                    assert saved["original_system_exit_code_repr"] == repr(error.code)
                results[name] = {"receipt": observe(destination), "exit_code": returned,
                    "result": saved["result"], "scope": "INERT_MAIN_CALLBACK_ONLY_NO_NATIVE_INTEGRATION"}
            original = observe(fixtures / "success.json")
            with patch.object(sys, "argv", [str(script), "--expected-self-sha256", EXPECTED_SCRIPT,
                                           "--output", str(fixtures / "success.json")]):
                try:
                    namespace["main"]()
                except FileExistsError:
                    pass
                else:
                    raise AssertionError("Existing output unexpectedly accepted")
            assert observe(fixtures / "success.json") == original
            report["inert_receipt_closure_cases"] = results
            report["existing_fixture_receipt_preserved"] = True
            report["named_small_inputs_after"] = {name: observe(value["path"]) for name, value in observations.items()}
            assert report["named_small_inputs_before"] == report["named_small_inputs_after"]
            report["script_after"] = observe(script)
            report["prior_receipt_after"] = observe(prior_path)
            assert report["script_before"] == report["script_after"]
            assert report["prior_receipt_before"] == report["prior_receipt_after"]
            report["result"] = "PREPARED_AST_SMALL_PINS_AND_INERT_RECEIPT_CLOSURE_PASSED_NATIVE_NOT_PERFORMED"
            code = 0
        except BaseException as error:
            report.update(result="WINDOWS_PREPARATION_INCOMPLETE", error=repr(error), traceback=traceback.format_exc())
        finally:
            report["project_modules_after"] = project_modules()
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            report["exit_code"] = code
            stream.write((json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
    print(json.dumps({"receipt": str(output), "result": report["result"], "exit_code": code}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
