"""Describe by default; explicitly verify one closed six-trace offline reduction.

No ROS, simulator, owner, native launcher, or flight-stack imports or commands.
The existing machine lock is held without creating it or changing its contents.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
LOCK_PATH = Path("/tmp/uav_tracking_reliability_v4_sitl.lock")
ROLES = ("detector", "estimator", "controller", "adapter", "replay", "monitor")
SHA = re.compile(r"[0-9a-f]{64}\Z")
REDUCER_FIELDS = (
    "schema_version", "scope", "status", "metric", "begin_ns", "end_ns", "edges",
    "opportunity_counts", "command_categories", "replayed_input_counts_by_kind", "replay_summaries",
    "replay_to_sensor_callback_association", "adapter_callback_count", "candidate_command_count",
    "unknown_command_count", "unknown_reasons", "received_rgb_count", "rgb_with_candidate_count",
    "candidate_subset_statistics_ns", "commands", "rgb_opportunities", "historical_strict_changed",
    "historical_strict_unknown", "physical_e2e", "graph_boundary", "claim_boundary", "trace_bindings")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def identity(path):
    info = Path(path).lstat()
    require(stat.S_ISREG(info.st_mode), "input must be an existing regular non-symlink file: " + str(path))
    return {"device": info.st_dev, "inode": info.st_ino, "bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}


def bound_file(path, expected_sha, *, expected_bytes=None, max_bytes=None, read=False):
    require(type(expected_sha) is str and SHA.fullmatch(expected_sha), "expected SHA-256 must be explicit lowercase hex")
    before = identity(path)
    if expected_bytes is not None:
        require(type(expected_bytes) is int and expected_bytes >= 0 and before["bytes"] == expected_bytes, "input size differs: " + str(path))
    if max_bytes is not None:
        require(before["bytes"] <= max_bytes, "refusing oversized metadata: " + str(path))
    digest, total, chunks = hashlib.sha256(), 0, []
    with Path(path).open("rb") as stream:
        require(os.fstat(stream.fileno()).st_ino == before["inode"], "input replaced before open")
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            require(total <= before["bytes"], "input grew while reading")
            digest.update(block)
            if read:
                chunks.append(block)
    require(total == before["bytes"] and identity(path) == before, "input changed while reading: " + str(path))
    require(digest.hexdigest() == expected_sha, "input SHA-256 differs: " + str(path))
    result = {"path": str(path), "bytes": total, "sha256": digest.hexdigest(), "identity": before}
    return (result, b"".join(chunks)) if read else result


@contextmanager
def existing_machine_lock():
    # Importing or describing this CLI requires no POSIX-only module.
    import fcntl
    before = identity(LOCK_PATH)
    descriptor = os.open(str(LOCK_PATH), os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    held = False
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and (opened.st_dev, opened.st_ino) == (before["device"], before["inode"]),
                "machine lock was replaced")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held = True
        require(identity(LOCK_PATH) == before, "machine lock changed during acquire")
        yield {"path": str(LOCK_PATH), "mode": "INTERNAL_EXISTING_FILE_NONBLOCKING_EXCLUSIVE_FLOCK",
               "created": False, "identity": before}
        require(identity(LOCK_PATH) == before, "machine lock changed while held")
    finally:
        if held:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def current_rss_bytes():
    try:
        if sys.platform.startswith("linux"):
            fields = Path("/proc/self/statm").read_text(encoding="ascii").split()
            return int(fields[1]) * os.sysconf("SC_PAGE_SIZE")
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            function = ctypes.windll.psapi.GetProcessMemoryInfo
            function.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            if function(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return counters.WorkingSetSize
    except Exception:
        pass
    return None


def measured_reduce(function, paths, **kwargs):
    samples, stop = [], threading.Event()
    def sample():
        value = current_rss_bytes()
        if type(value) is int:
            samples.append(value)
    def poll():
        while not stop.wait(0.05):
            sample()
    sample()
    worker = threading.Thread(target=poll, name="offline-reducer-self-rss", daemon=True)
    worker.start()
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    try:
        result = function(paths, **kwargs)
    finally:
        elapsed_wall, elapsed_cpu = time.perf_counter_ns() - wall, time.process_time_ns() - cpu
        stop.set()
        worker.join()
        sample()
    return result, {"scope": "THIS_OFFLINE_CANDIDATE_REDUCE_FILES_CALL_ONLY_NOT_NATIVE_PIPELINE",
                    "wall_ns": elapsed_wall, "process_cpu_ns": elapsed_cpu,
                    "rss_peak_sampled_bytes": max(samples, default=None), "rss_sample_count": len(samples),
                    "rss_sample_interval_seconds": 0.05,
                    "rss_boundary": "Current process RSS sampled around/during the call; includes baseline resident memory; sampling can miss brief peaks. Sampler overhead is included. Not a ru_maxrss delta."}


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # Avoid writing .pyc files into the fixed source trees.
    exec(compile(Path(path).read_bytes(), str(path), "exec"), module.__dict__)
    return module


def source_bindings(args):
    manifest_binding, raw = bound_file(args.source_map, args.source_map_sha256, max_bytes=4 * 1024 * 1024, read=True)
    manifest = json.loads(raw)
    bindings = [manifest_binding]
    for name in ("bench.py", "observer.py", "reducer.py", "typed_message.py"):
        require(type(manifest) is dict and name in manifest, "original07 map is missing runtime source")
        bindings.append(bound_file(Path(args.source_map).parent / name, manifest[name], max_bytes=4 * 1024 * 1024))
    for path, digest in ((args.candidate, args.candidate_sha256),
                         (Path(args.candidate).parent / "indexed_reduction.py", args.helper_sha256),
                         (args.probe, args.probe_sha256), (Path(__file__), args.cli_sha256)):
        bindings.append(bound_file(path, digest, max_bytes=4 * 1024 * 1024))
    tree = ast.parse(Path(args.candidate).read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "reduce_events")
    returned = function.body[-1]
    require(isinstance(returned, ast.Return) and isinstance(returned.value, ast.Dict), "unexpected reducer return schema")
    keys = [key.value for key in returned.value.keys if isinstance(key, ast.Constant) and type(key.value) is str]
    require(len(keys) == len(returned.value.keys) and set(keys) | {"trace_bindings"} == set(REDUCER_FIELDS),
            "CLI reducer field list differs from candidate source")
    return bindings


def closed_summary(args):
    binding, raw = bound_file(args.summary, args.summary_sha256, max_bytes=32 * 1024 * 1024, read=True)
    summary = json.loads(raw)
    require(summary.get("native_complete") is True and summary.get("error") is None and summary.get("cleanup_errors") == [],
            "original native execution is not cleanly closed")
    exits = summary.get("process_exit_codes")
    require(type(exits) is dict and set(exits) == set(ROLES) - {"monitor"}
            and all(type(value) is int and value == 0 for value in exits.values()), "original worker exits are not all int0")
    groups = summary.get("owned_group_status")
    require(type(groups) is dict and len(groups) == 5 and all(type(row) is dict and row.get("leader_returncode") == 0
            and type(row.get("leader_returncode")) is int and row.get("group_still_present") is False for row in groups.values()),
            "original owned groups did not close")
    require(all(key in summary for key in REDUCER_FIELDS), "original summary is missing reducer fields")
    traces = summary["trace_bindings"]
    require(type(traces) is list and len(traces) == 6, "exactly six original trace bindings required")
    root = Path(args.trace_root).resolve(strict=True)
    require({Path(row["path"]).name for row in traces} == {role + ".jsonl" for role in ROLES}, "six trace role names differ")
    for row in traces:
        require(type(row) is dict and set(row) == {"path", "bytes", "sha256"}, "unexpected original trace binding schema")
        path = Path(row["path"])
        require(path.is_absolute() and path.parent.resolve(strict=True) == root and str(path) == row["path"], "trace path leaves exact root")
        identity(path)
    return summary, binding


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def output_path(args):
    output = Path(args.output).resolve()
    require(not output.exists(), "output must be a new unused directory")
    protected = (Path(args.trace_root).resolve(), Path(args.summary).resolve().parent,
                 Path(args.source_map).resolve().parent, Path(args.candidate).resolve().parent,
                 Path(args.probe).resolve().parent)
    for tree in protected:
        require(not output.is_relative_to(tree) and not tree.is_relative_to(output),
                "output overlaps protected input/source tree: " + str(tree))
    return output


def execute(args):
    output = output_path(args)
    with existing_machine_lock() as lock:
        sources = source_bindings(args)
        summary, summary_binding = closed_summary(args)
        traces = [bound_file(row["path"], row["sha256"], expected_bytes=row["bytes"]) for row in summary["trace_bindings"]]
        output.mkdir(parents=True, exist_ok=False)
        receipt = {"scope": "INDEPENDENT_OFFLINE_CLOSED_TRACE_EQUIVALENCE_NOT_NATIVE_TERMINAL",
                   "started_utc": datetime.now(timezone.utc).isoformat(), "success": False,
                   "lock": lock, "original_summary": summary_binding, "original_traces": traces,
                   "source_bindings": sources, "native_started": False, "native_terminal_modified": False,
                   "native_idle_check": "NOT_PERFORMED_BY_THIS_CLI_ROOT_SCHEDULER_MUST_USE_REVIEWED_CHECK",
                   "formal_progress": "0/280_UNCHANGED", "physical_e2e": "NOT_OBSERVED"}
        try:
            source_root = Path(args.source_map).parent
            module_at("typed_message", source_root / "typed_message.py")
            module_at("observer", source_root / "observer.py")
            module_at("indexed_reduction", Path(args.candidate).parent / "indexed_reduction.py")
            module = module_at("checked_offline_reducer_candidate", args.candidate)
            paths = [row["path"] for row in summary["trace_bindings"]]
            result, performance = measured_reduce(module.reduce_files, paths, probe_path=args.probe,
                                                   begin_ns=summary["begin_ns"], end_ns=summary["end_ns"], native_complete=True)
            receipt["performance"] = performance
            require(set(result) == set(REDUCER_FIELDS), "candidate output has missing or unexpected reducer fields")
            comparisons = {key: canonical(result[key]) == canonical(summary[key]) for key in REDUCER_FIELDS}
            receipt["field_exact_equality"] = comparisons
            receipt["all_reducer_fields_equal"] = all(comparisons.values())
            receipt["reducer_field_count"] = len(comparisons)
            # Re-hash the exact raw sources after the measured region. Hashing,
            # source checks, comparison and JSON output are outside its timings.
            after_traces = [bound_file(row["path"], row["sha256"], expected_bytes=row["bytes"]) for row in summary["trace_bindings"]]
            require(after_traces == traces, "original traces changed during offline reduction")
            require(source_bindings(args) == sources, "bound source changed during offline reduction")
            require(bound_file(args.summary, args.summary_sha256, max_bytes=32 * 1024 * 1024) == summary_binding,
                    "original summary changed during offline reduction")
            receipt["all_bound_inputs_unchanged"] = True
            receipt["success"] = all(comparisons.values())
            result_path = output / "candidate_result.json"
            write_json(result_path, result)
            receipt["candidate_result"] = {"path": str(result_path), "bytes": result_path.stat().st_size,
                                           "sha256": hashlib.sha256(result_path.read_bytes()).hexdigest()}
        except Exception as error:
            receipt["error"] = {"type": type(error).__name__, "message": str(error)[:4096]}
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "verification_receipt.json", receipt)
        print(json.dumps({"output": str(output), "success": receipt["success"],
                          "all_reducer_fields_equal": receipt.get("all_reducer_fields_equal"),
                          "performance": receipt.get("performance"), "error": receipt.get("error")}, ensure_ascii=True))
        return 0 if receipt["success"] else 2


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command")
    commands.add_parser("describe")
    run = commands.add_parser("execute")
    for name in ("summary", "summary-sha256", "trace-root", "output", "source-map", "source-map-sha256",
                 "candidate", "candidate-sha256", "helper-sha256", "probe", "probe-sha256", "cli-sha256"):
        run.add_argument("--" + name, required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command != "execute":
        print(json.dumps({"default": "DESCRIBE_ONLY_NO_INPUT_READ_OR_OUTPUT_WRITE", "execution": "execute requires explicit original summary/source SHA inputs and unused output",
                          "lock": str(LOCK_PATH), "lock_mode": "existing ordinary non-symlink file; internal nonblocking exclusive POSIX flock; never created",
                          "reducer_fields": list(REDUCER_FIELDS), "native_started": False,
                          "native_idle_check": "root must use reviewed check separately", "physical_e2e": "NOT_OBSERVED", "formal_progress": "0/280_UNCHANGED"}, ensure_ascii=True))
        return 0
    try:
        return execute(args)
    except Exception as error:
        print(json.dumps({"success": False, "error": {"type": type(error).__name__, "message": str(error)[:4096]}, "native_started": False}, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
