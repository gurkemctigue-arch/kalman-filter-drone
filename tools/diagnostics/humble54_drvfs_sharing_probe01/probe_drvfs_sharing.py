"""Actual Windows-handle / WSL DrvFS metadata probe; never starts ROS or a flight.

The Windows driver invokes one old and one new write_json helper. Native errors
are observed, never injected. Merely importing this script starts nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
SCOPE = "ACTUAL_DRVFS_FILE_SHARING_ONLY"
SOURCE_PINS = {
    "old": "dd4583da4f34b216bc5dd5a95aa904459ebc7f68e2bfba026a2e3e66706d9c86",
    "new": "bf9168f2b5b6dc31e43c187d894f860a4d77e780ded6a4b453c2545c5b5aee0e",
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf8")


def native(args):
    if sys.platform != "linux":
        raise ValueError("Native helper requires Linux")
    source, case = Path(args.source).resolve(strict=True), Path(args.case_dir).resolve(strict=True)
    if sha(source) != args.source_sha or args.source_sha != SOURCE_PINS[args.mode]:
        raise ValueError("Native source SHA differs from Windows registration")
    target = case / "state.json"
    spec = importlib.util.spec_from_file_location("actual_drvfs_" + args.mode, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    before = sha(target)
    result = {"scope": SCOPE, "is_fixture": False, "mode": args.mode,
              "platform": sys.platform, "uname": list(os.uname()), "pid": os.getpid(),
              "helper_source": {"path": str(source), "sha256": sha(source)},
              "probe_source_sha256": sha(__file__), "target_sha256_before": before,
              "expected_value": {"actual_drvfs_probe": True, "writer": args.mode}}
    observed = []

    def observe(frame, event, arg):
        # Observe the real OS exception as it reaches the exact pinned helper.
        # Do not replace its writer, Path.replace, sleep, clock, or exception.
        if frame.f_code is module.write_json.__code__:
            if event == "exception" and isinstance(arg[1], OSError):
                error = arg[1]
                observed.append({"utc": utc(), "line": frame.f_lineno,
                                 "type": type(error).__name__, "errno": error.errno,
                                 "message": str(error)})
            return observe
        return None

    save(case / "started.json", {"utc": utc(), "pid": os.getpid(), "about_to_call": "write_json"})
    begin = time.monotonic()
    result["writer_started_utc"] = utc()
    previous_trace = sys.gettrace()
    sys.settrace(observe)
    try:
        module.write_json(target, result["expected_value"])
        result.update(outcome="SUCCEEDED", exception=None)
    except Exception as error:
        result.update(outcome="RAISED", exception={"type": type(error).__name__,
                      "errno": getattr(error, "errno", None), "message": str(error)})
    finally:
        sys.settrace(previous_trace)
    result.update(writer_finished_utc=utc(), writer_duration_s=time.monotonic() - begin,
                  target_sha256_after=sha(target), target_value_after=json.loads(target.read_text(encoding="utf8")),
                  helper_source_sha256_after=sha(source),
                  observed_write_json_oserrors=observed,
                  temporary_files=[{"name": p.name, "sha256": sha(p)} for p in sorted(case.glob("state.json*.tmp"))])
    save(case / "native_result.json", result)
    print(json.dumps({"mode": args.mode, "outcome": result["outcome"],
                      "native_result_sha256": sha(case / "native_result.json")}))
    return 0


def mounted(path):
    path = Path(path).resolve(strict=True)
    if len(path.drive) != 2 or path.drive[1] != ":":
        raise ValueError("Probe requires a local drive path, not UNC")
    return "/mnt/" + path.drive[0].lower() + "/" + "/".join(path.parts[1:])


def lock_read_without_delete(target):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(target), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())

    def close():
        if not kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    return close


def run_case(root, mode, source, distribution):
    case = root / mode
    case.mkdir()
    target = case / "state.json"
    save(target, {"original": True, "mode": mode})
    source_sha = sha(source)
    row = {"mode": mode, "source": {"path": str(source), "sha256": source_sha},
           "started_utc": utc(), "share_mode": "FILE_SHARE_READ (1); no FILE_SHARE_DELETE",
           "desired_access": "GENERIC_READ", "release_delay_after_native_started_s": 2.0}
    close = lock_read_without_delete(target)
    row["windows_handle_acquired_utc"] = utc()
    child = None
    try:
        command = ["wsl.exe", "--distribution", distribution, "--exec", "python3", "-B", mounted(__file__),
                   "--native-helper", "--mode", mode, "--source", mounted(source), "--source-sha", source_sha,
                   "--case-dir", mounted(case)]
        row["command"] = command
        with (case / "stdout.log").open("wb") as stdout, (case / "stderr.log").open("wb") as stderr:
            child = subprocess.Popen(command, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
            row["owned_wsl_pid"] = child.pid
            deadline = time.monotonic() + 30.0
            started = case / "started.json"
            while not started.exists():
                if child.poll() is not None:
                    raise RuntimeError("Native helper exited before its write_json handshake")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Native helper did not reach write_json within 30 seconds")
                time.sleep(.02)
            # started.json can be observed before write_text closes on DrvFS.
            # Its bytes are decoded only after the owned helper has exited.
            row["windows_observed_native_start_utc"] = utc()
            time.sleep(2.0)
            close()
            close = None
            row["windows_handle_released_utc"] = utc()
            child.wait(timeout=15.0)
            row["returncode"] = child.returncode
        result = json.loads((case / "native_result.json").read_text(encoding="utf8"))
        row["native_result"] = result
        unchanged = sha(source) == source_sha == result["helper_source_sha256_after"]
        same_probe = result["probe_source_sha256"] == sha(__file__)
        actual_linux = result["platform"] == "linux" and result["is_fixture"] is False
        if mode == "old":
            expected = (result["outcome"] == "RAISED" and result["exception"]["type"] == "PermissionError"
                        and result["exception"]["errno"] == 13
                        and result["target_sha256_after"] == result["target_sha256_before"])
        else:
            expected = (result["outcome"] == "SUCCEEDED" and result["target_value_after"] == result["expected_value"]
                        and any(e["type"] == "PermissionError" and e["errno"] == 13
                                for e in result["observed_write_json_oserrors"])
                        and result["writer_duration_s"] >= 1.5 and result["temporary_files"] == [])
        row["status"] = "PASS" if unchanged and same_probe and actual_linux and expected and child.returncode == 0 else "FAIL"
    except Exception as error:
        row.update(status="FAIL", driver_error=f"{type(error).__name__}: {error}")
    finally:
        try:
            if close is not None:
                close()
                row["windows_handle_released_utc"] = utc()
        except Exception as error:
            row.update(status="FAIL", handle_release_error=f"{type(error).__name__}: {error}")
        if child is not None and child.poll() is None:
            # Only this finite Python metadata helper is owned. Keep observing it;
            # do not leave an asynchronous command alive after declaring closure.
            try:
                child.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                row["status"] = "FAIL"
                row["owned_helper_exceeded_wait_bound"] = True
                row["owned_helper_wait_started_utc"] = utc()
                child.wait()
            row["returncode"] = child.returncode
            row["owned_helper_exit_observed_utc"] = utc()
        row["finished_utc"] = utc()
        row["artifacts"] = {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)}
                            for p in sorted(case.iterdir()) if p.is_file()}
        save(case / "case_receipt.json", row)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-helper", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=("old", "new"))
    parser.add_argument("--source")
    parser.add_argument("--source-sha")
    parser.add_argument("--case-dir")
    parser.add_argument("--execute", action="store_true", help="Explicitly run two tiny WSL metadata helpers")
    parser.add_argument("--distribution", default="UAVHumble22")
    parser.add_argument("--old-source", type=Path)
    parser.add_argument("--new-source", type=Path)
    parser.add_argument("--output", type=Path, help="Entirely new project-owned directory on D:")
    args = parser.parse_args(argv)
    if args.native_helper:
        return native(args)
    if not args.execute:
        print(json.dumps({"scope": SCOPE, "status": "NOT_STARTED", "required": "Explicit --execute and source/output paths"}))
        return 0
    if sys.platform != "win32" or not all((args.old_source, args.new_source, args.output)):
        parser.error("Execution requires Windows and explicit --old-source, --new-source, --output")
    project = Path(__file__).resolve().parents[3]
    output = args.output.resolve()
    if output.drive.lower() != "d:" or not output.is_relative_to(project / "results") or output.exists():
        raise ValueError("Output must be an entirely new directory under this project's D: results")
    old, new = args.old_source.resolve(strict=True), args.new_source.resolve(strict=True)
    if sha(old) != SOURCE_PINS["old"] or sha(new) != SOURCE_PINS["new"]:
        raise ValueError("Only the registered original03 and final collector04 source SHAs are permitted")
    output.mkdir(parents=True)
    receipt = {"scope": SCOPE, "status": "RUNNING", "is_fixture": False, "started_utc": utc(),
               "claim_boundary": "Real file sharing only; no collector-loop, ROS, SITL, bags, flight, capacity or readiness claim.",
               "driver_source": {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)},
               "distribution_requested": args.distribution, "automatic_retry": False, "cases": []}
    save(output / "started.json", receipt)
    for mode, source in (("old", old), ("new", new)):
        receipt["cases"].append(run_case(output, mode, source, args.distribution))
    receipt.update(status="PASS" if all(r["status"] == "PASS" for r in receipt["cases"]) else "FAIL", finished_utc=utc())
    receipt["artifact_hashes"] = {p.relative_to(output).as_posix(): sha(p) for p in sorted(output.rglob("*")) if p.is_file()}
    save(output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(output / "receipt.json"),
                      "receipt_sha256": sha(output / "receipt.json")}))
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
