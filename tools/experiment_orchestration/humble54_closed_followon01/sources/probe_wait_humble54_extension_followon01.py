"""Run only after review: inert default plus exact current Windows handles.

Does not call execute(), SetThreadExecutionState, WSL, Popen, or any tests/native work.
"""
from datetime import datetime, timezone
import ctypes
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

BASE = Path("D:/WSL/UAVHumble22-validation")
SOURCE = BASE / "wait_humble54_extension_followon01.py"
OUTPUT = BASE / "wait_humble54_extension_followon01_inert_probe01.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    if os.name != "nt":
        raise RuntimeError("Actual Windows kernel required")
    if not 0 < SOURCE.stat().st_size <= 1024 * 1024:
        raise RuntimeError("Waiter source is outside the small-file bound")
    before = SOURCE.read_bytes()
    report = {"schema_version": 1, "kind": "ACTUAL_WINDOWS_WAITER_INERT_HANDLE_PROBE",
              "started_utc": now(), "pid": os.getpid(),
              "invocation_argv": getattr(sys, "orig_argv", [sys.executable, *sys.argv]),
              "source": {"path": str(SOURCE), "size_bytes": len(before),
                         "sha256_before": hashlib.sha256(before).hexdigest()},
              "executed_waiter_execute": False, "sleep_api_called": False,
              "wsl_or_child_started": False, "handles": [], "result": "PENDING"}
    kernel = None
    result = 2
    try:
        module = runpy.run_path(str(SOURCE), run_name="inert_probe_import_only")
        for key in ["RECEIPTS", "NEW_PROGRESS"]:
            if module[key].exists():
                raise RuntimeError("Expected no existing future output: " + str(module[key]))
        code = module["main"]([])
        if code != 2:
            raise RuntimeError("Default main did not return prepared-only exit 2")
        if any(module[key].exists() for key in ["RECEIPTS", "NEW_PROGRESS"]):
            raise RuntimeError("Default main created a forbidden output")
        report["default_main"] = {"returncode": code, "future_outputs_created": False}
        kernel = module["WindowsHandles"]()
        for key in ["OLD_MONITOR", "OLD_WSL"]:
            expected = module[key]
            handle = kernel.acquire(expected)
            times = [kernel.types.FILETIME() for _ in range(4)]
            if not kernel.kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise RuntimeError("Probe GetProcessTimes failed")
            observed = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            code = kernel.exit_if_signaled(handle)
            report["handles"].append({"role": key, "pid": expected["pid"],
                                      "observed_creation_filetime": observed,
                                      "expected_creation_filetime": expected["creation_filetime"],
                                      "creation_matches": observed == expected["creation_filetime"],
                                      "exit_if_signaled": code,
                                      "observation_utc": now()})
            if observed != expected["creation_filetime"] or code is not None:
                raise RuntimeError("Current exact process is mismatched or no longer running")
        report["result"] = "PASS_INERT_ONLY_BOTH_EXACT_PROCESSES_STILL_RUNNING"
        result = 0
    except BaseException as error:
        report.update(result="REFUSED_OR_PROBE_FAILED",
                      error={"type": type(error).__name__, "message": str(error)})
    finally:
        if kernel is not None:
            report["handle_close_results"] = kernel.close()
            if not all(report["handle_close_results"]):
                result = 2
                report["result"] = "REFUSED_HANDLE_CLOSE_UNKNOWN"
        after = SOURCE.read_bytes()
        report["source"]["sha256_after"] = hashlib.sha256(after).hexdigest()
        report["source"]["unchanged"] = before == after
        if before != after:
            result = 2
            report["result"] = "REFUSED_SOURCE_CHANGED"
        report.update(finished_utc=now(), actual_probe_exit_code=result,
                      scope="Only inert default and real current-process identity/liveness; no real exit0 observed or claimed")
        with OUTPUT.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, ensure_ascii=True, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"receipt": str(OUTPUT), "result": report["result"], "actual_exit": result}))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
