"""Measure transparent NTFS compression of exactly two historical text files.

Default only prints the fixed sample. Actual execution requires a fresh native
idle receipt after owner05 closes. Never deletes, moves, rewrites payloads,
recurses, touches a VHD, or estimates unmeasured whole-project savings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import types

ROOT = Path(__file__).resolve().parents[3]
SURVEY = ROOT / "tools/diagnostics/text_storage_metadata_survey01/survey.py"
SURVEY_SHA = "a4a88958d2f5075dc2cc13db01e35ea2a595f7513a3f8be39c1247da47f91a6b"
SURVEY_DATA = SURVEY.with_name("survey01.json")
SURVEY_DATA_SHA = "778eb6116ee55140f2ea7f48c64b4ec46d872b3051c439b6b8a52d9710817db9"
SAMPLES = (
    ("frozen_fullplan_v4_humble35/reliability_v4_humble35_surface01_car_stage2_crossing_seed004/telemetry.jsonl", 195924034),
    ("frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_car_stage1_velocity_seed004/telemetry.jsonl", 82657557),
)
OWNER = ROOT / "results/diagnostics/humble54_probe02_windows_owner05/terminal.json"


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def small(path):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= 2 * 1024 * 1024, "Small metadata file required")
    return path.read_bytes()


def save_new(path, value):
    with Path(path).open("xb") as handle:
        handle.write((json.dumps(value, indent=2, allow_nan=False) + "\n").encode())


def load_api():
    raw = small(SURVEY)
    require(digest(raw) == SURVEY_SHA, "Original read-only API source differs")
    module = types.ModuleType("fixed_ntfs_metadata_api")
    module.__file__ = str(SURVEY)
    exec(compile(raw, str(SURVEY), "exec"), module.__dict__)
    return module.API(), module.wide


def finalize_report(report, output, api, operation_error=None):
    """Retain partial results even if the final volume query also fails."""
    report["finished_utc"] = utc()
    volume_error = None
    try:
        report["volume_after"] = api.volume()
    except BaseException as error:
        volume_error = error
        report["status"] = "FAIL_PARTIAL_SAMPLE_RETAINED"
        report["volume_after"] = None
        report["volume_after_error"] = f"{type(error).__name__}: {error}"
        if operation_error is None:
            report.update(status="FAIL_PARTIAL_SAMPLE_RETAINED", error=report["volume_after_error"])
    try:
        save_new(output, report)
    except BaseException as receipt_error:
        original = operation_error if operation_error is not None else volume_error
        if original is None:
            raise
        if hasattr(original, "add_note"):
            original.add_note(f"Final sample receipt could not be saved: {type(receipt_error).__name__}: {receipt_error}")
        if operation_error is None:
            raise original from receipt_error
        # The caller is already re-raising this original operation exception.
        return
    if operation_error is None and volume_error is not None:
        raise volume_error


def no_reparse(path):
    for part in (path, *path.parents):
        require(not (part.stat(follow_symlinks=False).st_file_attributes & 0x400), "Reparse component refused")


def stable_hash(path, api, wide):
    """Deny writers while hashing and checking the exact open file identity."""
    import ctypes
    import msvcrt
    handle = api.k.CreateFileW(wide(path), 0x80000000, 1, None, 3, 0x08000000, None)
    require(handle != ctypes.c_void_p(-1).value, "Stable read handle unavailable; file may have a writer")
    try:
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY)
    except BaseException:
        api.k.CloseHandle(handle)
        raise
    began = time.monotonic()
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(before.st_ino > 0, "Stable file identity unavailable")
        hasher = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
        after = os.fstat(stream.fileno())
        identity = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_nlink)
        require(identity(before) == identity(after), "File changed during stable full read")
        _, allocation, links, size = api.storage(path)
        attrs = path.stat(follow_symlinks=False).st_file_attributes
        require(size == before.st_size and links == 1, "Open-file size or single-link contract differs")
        return {"identity": list(identity(before)), "sha256": hasher.hexdigest(),
                "logical_bytes": size, "allocated_bytes": allocation, "attributes": attrs,
                "read_elapsed_s": time.monotonic() - began}


def execution_guard(idle_path, output):
    # This is a fresh idle snapshot. The root's serial orchestration must keep
    # new native workloads stopped throughout hashing and compression.
    require(os.name == "nt", "Actual operation requires Windows")
    owner_raw = small(OWNER)
    owner = json.loads(owner_raw)
    require(owner.get("closure_verified") is True and owner.get("errors") == []
            and owner.get("monitor_final_handle_exit_code") is not None
            and owner.get("wsl_final_handle_exit_code") is not None
            and owner.get("power_lease", {}).get("released_utc"), "Current experiment owner has not closed")
    idle_raw = small(idle_path)
    idle = json.loads(idle_raw)
    require(idle.get("status") == "PASS_IDLE_QUERY_ONLY" and idle.get("returncode") == 0
            and idle.get("query", {}).get("matching_processes") == [], "Successful actual native idle query required")
    finished = datetime.fromisoformat(idle["finished_utc"])
    now = datetime.now(timezone.utc)
    require(finished.tzinfo is not None and 0 <= (now - finished).total_seconds() <= 60,
            "Native idle query must be fresh within sixty seconds")
    require(datetime.fromisoformat(owner["finished_utc"]) <= finished, "Idle query predates current owner closure")
    require(idle.get("outer_terminal") == {"path": str(OWNER), "sha256": digest(owner_raw)}, "Idle receipt belongs to another owner")
    output = output.absolute()
    require(output.suffix == ".json" and output.parent.is_dir() and not output.exists(), "Fresh JSON with existing parent required")
    require(output.is_relative_to(ROOT / "results/diagnostics"), "Receipt must stay in project diagnostics")
    require(not output.with_suffix(".started.json").exists(), "No repeated operation")
    no_reparse(output.parent)
    return {"owner": {"path": str(OWNER), "sha256": digest(owner_raw)},
            "native_idle": {"path": str(idle_path), "sha256": digest(idle_raw)}}


def run(idle_path, output):
    output = output.parent.resolve(strict=True) / output.name
    evidence = execution_guard(idle_path, output)
    require(digest(small(SURVEY_DATA)) == SURVEY_DATA_SHA, "Original survey metadata differs")
    survey = json.loads(small(SURVEY_DATA))
    candidates = {row["path"]: row for row in survey["largest_uncompressed_candidates"]}
    api, wide = load_api()
    volume = api.volume()
    require(volume["filesystem"] == "NTFS" and volume["file_compression_supported"], "NTFS compression support required")
    paths = []
    for relative, size in SAMPLES:
        path = ROOT / "results" / relative
        no_reparse(path)
        previous, current = candidates[relative], path.stat()
        require(previous["historical_uncompressed_candidate"] is True and previous["logical_bytes"] == size
                and current.st_size == size and current.st_mtime_ns == previous["mtime_ns"]
                and time.time_ns() - current.st_mtime_ns >= 86400 * 10**9
                and not (current.st_file_attributes & (0x200 | 0x800 | 0x4000)), "Fixed historical sample changed or is already compressed")
        paths.append(path)
    report = {"status": "STARTED_FIXED_SAMPLE_ONLY", "started_utc": utc(), "source_sha256": digest(small(__file__)),
              "guard_evidence": evidence, "volume_before": volume, "files": [],
              "claim_boundary": "Two named historical telemetry files only. No unmeasured total savings, capacity admission, VHD operation, deletion or experiment verdict change."}
    save_new(output.with_suffix(".started.json"), report)
    operation_error = None
    try:
        compact = Path(os.environ["SystemRoot"]) / "System32/compact.exe"
        for path in paths:
            before = stable_hash(path, api, wide)
            row = {"path": str(path), "before": before, "command": [str(compact), "/C", "/F", "/Q", str(path)], "started_utc": utc()}
            report["files"].append(row)
            began = time.monotonic()
            child = subprocess.run(row["command"], capture_output=True)
            row.update(returncode=child.returncode, finished_utc=utc(), elapsed_s=time.monotonic() - began,
                       stdout_hex=child.stdout.hex(), stderr_hex=child.stderr.hex())
            require(child.returncode == 0, "Exact-file compact command failed")
            after = stable_hash(path, api, wide)
            row["after"] = after
            require(before["identity"] == after["identity"] and before["sha256"] == after["sha256"], "Identity, size, mtime, links or decompressed bytes changed")
            require(after["attributes"] & 0x800 and (before["attributes"] ^ after["attributes"]) & ~0x800 == 0,
                    "Unexpected file-attribute change or compression not applied")
            row["saved_allocation_bytes"] = before["allocated_bytes"] - after["allocated_bytes"]
            require(row["saved_allocation_bytes"] >= 0, "Sample allocation increased")
            row["status"] = "PASS_BYTES_AND_TRANSPARENT_DECOMPRESSION"
        report["status"] = "PASS_FIXED_SAMPLE_ONLY_NOT_FULL_BUDGET"
        report["saved_allocation_bytes"] = sum(row["saved_allocation_bytes"] for row in report["files"])
    except BaseException as error:
        operation_error = error
        report["status"] = "FAIL_PARTIAL_SAMPLE_RETAINED"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        finalize_report(report, output, api, operation_error)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--idle-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"status": "PREPARED_ONLY_NOT_EXECUTED", "samples": SAMPLES,
                          "owner_closure_required": str(OWNER)}))
        return 0
    require(args.idle_receipt is not None and args.output is not None, "Explicit idle receipt and fresh output required")
    result = run(args.idle_receipt, args.output)
    print(json.dumps({key: result[key] for key in ("status", "saved_allocation_bytes")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
