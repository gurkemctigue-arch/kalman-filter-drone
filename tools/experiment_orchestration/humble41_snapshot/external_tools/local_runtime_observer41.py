"""Explicit tmpfs observer owner; no flight/plan/build actions or legacy edits.

The collector owns its new health leaf. This owner owns bounded local console
and metadata, ten-second checks, native shutdown, and a separately bounded
archive subprocess. All native sessions stop before any D archive is copied.
Raw local evidence is never removed, including on errors.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid

LIVE_BASE = Path("/dev/shm/uav_tracking_runtime_health")
D_ROOT = Path("/mnt/d")
SCOPE = "HUMBLE41_TMPFS_RUNTIME_OBSERVER_NATIVE_AND_ARCHIVE_SEPARATE"
MODE = "private_tmpfs_external_archive"
MAX_SAMPLE_AGE_WALL_S = 10.
SESSION_WALL_S = 7200.
ROTATE_WALL_S = 5400.
HEALTH_LIMIT = 64 * 1024**2
CONSOLE_LIMIT = 256 * 1024
SMALL_LIMIT = 1024**2
TAIL_LIMIT = 64 * 1024
ARCHIVE_WALL_S = 1800.


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def write_new(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    require(len(raw) <= SMALL_LIMIT, "Owner metadata exceeds its bound")
    with Path(path).open("xb") as stream:
        stream.write(raw)
    return path


def read_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= SMALL_LIMIT,
            "Missing/unsafe bounded owner metadata")
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def file_binding(path, limit):
    path = Path(path)
    first = path.lstat()
    require(stat.S_ISREG(first.st_mode) and first.st_size <= limit,
            "Missing, linked, nonregular or oversized observer artifact")
    digest = hashlib.sha256()
    counted = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            counted += len(chunk)
            require(counted <= limit, "Observer artifact grew beyond its byte bound")
            digest.update(chunk)
    last = path.lstat()
    require((first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns)
            == (last.st_dev, last.st_ino, last.st_size, last.st_mtime_ns),
            "Observer artifact changed while hashing")
    return {"path": str(path), "bytes": first.st_size, "sha256": digest.hexdigest()}


def mount_for(path):
    """Read proc metadata only; never statvfs the archive in the live path."""
    path = Path(path)
    matches = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        fields = left.split()
        mountpoint = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4])
        if path == Path(mountpoint) or path.is_relative_to(Path(mountpoint)):
            matches.append((len(Path(mountpoint).parts), mountpoint, right.split()[0]))
    require(matches, "No mount metadata for observer path")
    _, mountpoint, filesystem = max(matches)
    return {"mountpoint": mountpoint, "filesystem": filesystem}


def check_private(path):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts and path.resolve() == path
            and path.is_relative_to(LIVE_BASE), "Live path must be a real private descendant")
    current = LIVE_BASE
    for name in (None, *path.relative_to(LIVE_BASE).parts):
        if name is not None:
            current = current / name
        value = current.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid()
                and stat.S_IMODE(value.st_mode) == 0o700,
                "Live parents must belong to this uid with mode0700")
    require(mount_for(path) == {"mountpoint": str(LIVE_BASE.parent), "filesystem": "tmpfs"},
            "Live evidence requires the actual /dev/shm tmpfs without nested mounts")


def prepare_live():
    require(os.name == "posix", "Actual owner requires Linux")
    LIVE_BASE.mkdir(mode=0o700, exist_ok=True)
    check_private(LIVE_BASE)
    folder = LIVE_BASE / ("owner41_" + uuid.uuid4().hex)
    folder.mkdir(mode=0o700)
    check_private(folder)
    return folder


def capacity(path):
    check_private(path)
    value = os.statvfs(path)
    free = value.f_bavail * value.f_frsize
    # Two bounded sessions may overlap; retained older bytes already reduce free.
    reserve = 2 * (HEALTH_LIMIT + CONSOLE_LIMIT + SMALL_LIMIT)
    require(free >= reserve, "Insufficient tmpfs capacity for overlapping bounded observers")
    return {"mount": mount_for(path), "free_bytes": free, "required_free_bytes": reserve,
            "health_limit_bytes": HEALTH_LIMIT, "console_limit_bytes": CONSOLE_LIMIT}


def archive_destination(directory, root):
    """Resolve a prospective destination once before any live collector starts."""
    root = Path(root)
    require(root.is_absolute(), "Explicit absolute frozen source root required")
    destination = Path(directory).resolve()
    results = (root / "results").resolve(strict=True)
    require(destination != results and destination.is_relative_to(results)
            and destination.is_relative_to(D_ROOT.resolve(strict=True)),
            "Archive must be below this frozen root's actual D results")
    require(not destination.exists() and not destination.is_symlink(),
            "Fresh observer archive required; no retry or overwrite")
    return destination


def observer_command(root, archive_session, live_session):
    return [sys.executable, "-B", str(Path(root) / "scripts/observe_runtime_health.py"),
            "--output-dir", str(Path(archive_session) / "runtime_health"),
            "--live-output-dir", str(Path(live_session) / "runtime_health"),
            "--duration-wall-s", "7200", "--max-log-mib", "64", "--ros"]


def latest_sample(path):
    with Path(path).open("rb") as stream:
        stream.seek(0, 2)
        start = max(0, stream.tell() - TAIL_LIMIT)
        stream.seek(start)
        raw = stream.read(TAIL_LIMIT)
    if start:
        boundary = raw.find(b"\n")
        raw = raw[boundary + 1:] if boundary >= 0 else b""
    end = raw.rfind(b"\n")
    require(end >= 0, "No complete observer line")
    for line in reversed(raw[:end].splitlines()):
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(row, dict) and row.get("event") == "RUNTIME_HEALTH_SAMPLE":
            return row
    raise ValueError("No complete runtime health sample in bounded local tail")


def validate_sample(sample, now, archive_health, live_directory=None):
    stamp = sample.get("monotonic_s")
    require(finite(stamp) and -1e-6 <= now - stamp <= 10.,
            "Latest complete observer sample is stale/future or lacks finite monotonic time")
    receiver, writer = sample.get("ros_receiver"), sample.get("writer")
    require(isinstance(receiver, dict) and receiver.get("thread_alive") is True
            and receiver.get("error") is None, "Observer ROS receiver stopped or errored")
    require(isinstance(writer, dict) and writer.get("error") is None
            and writer.get("limit_reached") is False and writer.get("writer_alive") is True
            and type(writer.get("dropped_aggregates")) is int and writer["dropped_aggregates"] == 0,
            "Observer writer error, limit or incomplete status")
    deferred = sample.get("disk", {}).get("output_d_mount")
    require(deferred == {"path": str(archive_health), "status": "deferred_to_archive_owner"},
            "Live sample must explicitly defer archive-volume inspection")
    if live_directory is not None:
        require(sample.get("disk", {}).get("live_output_tmpfs", {}).get("path") == str(live_directory),
                "Live sample tmpfs path differs")
    return {"latest_sample_monotonic_s": stamp, "sample_age_wall_s": now - stamp,
            "max_sample_age_wall_s": 10., "checked_monotonic_s": now}


class Console:
    """Drain a pipe without unbounded stdout buffers or writes outside tmpfs."""
    def __init__(self, pipe, path):
        self.pipe, self.path = pipe, Path(path)
        self.bytes = 0
        self.error = None
        self.overflow = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            with self.path.open("xb") as stream:
                while True:
                    chunk = self.pipe.read(4096)
                    if not chunk:
                        break
                    remaining = CONSOLE_LIMIT - self.bytes
                    if len(chunk) > remaining:
                        self.overflow = True
                    kept = chunk[:max(0, remaining)]
                    stream.write(kept)
                    self.bytes += len(kept)
                    stream.flush()
        except Exception as error:
            self.error = type(error).__name__ + ":" + str(error)
        finally:
            self.pipe.close()

    def finish(self):
        self.thread.join(timeout=2.)
        require(not self.thread.is_alive() and self.error is None and not self.overflow,
                "Local console failed, overflowed or did not close")


class Session:
    def __init__(self, owner, index):
        self.owner, self.index = owner, index
        self.local = owner.live / f"session_{index:03d}"
        self.local.mkdir(mode=0o700)
        self.archive = owner.directory / self.local.name
        self.command = observer_command(owner.root, self.archive, self.local)
        self.process = self.console = None
        self.first_check = self.last_check = None
        self.first_fresh_at = None
        self.native = None
        self.started = time.monotonic()
        self.started_utc = utc()
        self.capacity = capacity(self.local)

    @property
    def health(self):
        return self.local / "runtime_health/health.jsonl"

    def start(self):
        require(file_binding(self.owner.root / "scripts/observe_runtime_health.py", SMALL_LIMIT)
                == self.owner.collector_source, "Collector source changed before spawn")
        self.process = subprocess.Popen(self.command, cwd=self.owner.root, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.console = Console(self.process.stdout, self.local / "observer_console.log")
        deadline, last_error = time.monotonic() + 10., None
        while time.monotonic() < deadline and self.process.poll() is None:
            try:
                self.first_check = self.check()
                self._started_contract()
                self.first_fresh_at = time.monotonic()
                return self
            except (OSError, ValueError, RuntimeError) as error:
                last_error = str(error)
            time.sleep(.1)
        raise RuntimeError("No healthy first local observer sample within10s:" + str(last_error))

    def _started_contract(self):
        with self.health.open("rb") as stream:
            raw = stream.readline(SMALL_LIMIT + 1)
        require(len(raw) <= SMALL_LIMIT and raw.endswith(b"\n"), "Invalid bounded START record")
        row = json.loads(raw)
        require(row.get("event") == "RUNTIME_HEALTH_OBSERVER_STARTED"
                and row.get("storage_mode") == MODE and row.get("ros_enabled") is True
                and row.get("duration_wall_s") == 7200. and row.get("period_wall_s") == 1.
                and row.get("live_output") == str(self.local / "runtime_health")
                and row.get("archive_output") == str(self.archive / "runtime_health")
                and row.get("archive_status") == "pending_external_owner",
                "Collector START does not bind explicit local/D paths and policy")
        require(row.get("output_mount", {}).get("filesystem") == "tmpfs"
                and row["output_mount"].get("mountpoint") == str(LIVE_BASE.parent),
                "Collector START did not observe the actual tmpfs")

    def check(self):
        began = time.monotonic()
        require(self.process is not None and self.process.poll() is None,
                "Independent local observer stopped; no next attempt allowed")
        check_private(self.local)
        require(self.health.stat().st_size <= HEALTH_LIMIT, "Local health limit exceeded")
        self.last_check = validate_sample(latest_sample(self.health), time.monotonic(),
                                          self.archive / "runtime_health", self.local / "runtime_health")
        self.last_check["check_duration_wall_s"] = time.monotonic() - began
        return self.last_check

    def stop_native(self, exception=False):
        if self.native is not None:
            return self.native
        unexpected = self.process is not None and self.process.poll() is not None
        errors, forced = [], False
        try:
            self.check()
        except Exception as error:
            errors.append("final_sample:" + type(error).__name__ + ":" + str(error))
        stop_requested, stop_utc = time.monotonic(), utc()
        code = None
        if self.process is not None:
            if self.process.poll() is None:
                try:
                    self.process.send_signal(signal.SIGTERM)
                except OSError as error:
                    errors.append("signal:" + str(error))
            try:
                code = self.process.wait(timeout=10.)
            except subprocess.TimeoutExpired:
                forced = True
                try:
                    self.process.kill()
                    code = self.process.wait(timeout=5.)
                except (OSError, subprocess.TimeoutExpired) as error:
                    errors.append("forced_cleanup:" + str(error))
                    code = self.process.poll()
        native_exit = time.monotonic()
        try:
            require(self.console is not None, "No owned local console")
            self.console.finish()
            self._closed_contract()
        except Exception as error:
            errors.append("closed:" + type(error).__name__ + ":" + str(error))
        self.native = {
            "index": self.index, "command": self.command, "source_root": str(self.owner.root),
            "live_directory": str(self.local), "archive_directory": str(self.archive),
            "started_utc": self.started_utc, "started_monotonic_s": self.started,
            "first_fresh_monotonic_s": self.first_fresh_at,
            "stop_requested_utc": stop_utc, "stop_requested_monotonic_s": stop_requested,
            "native_exit_utc": utc(),
            "native_exit_monotonic_s": native_exit, "native_shutdown_wall_s": native_exit - stop_requested,
            "observer_exit_code": code, "observer_forced_stop": forced,
            "ended_before_requested_stop": unexpected, "driver_exception": bool(exception),
            "first_fresh_sample": self.first_check, "final_fresh_sample": self.last_check,
            "errors": errors, "capacity": self.capacity,
            "healthy_cleanup": code == 0 and not forced and not unexpected and not exception and not errors,
            "local_evidence_removed": False,
        }
        write_new(self.local / "native_exit_terminal.json", self.native)
        return self.native

    def _closed_contract(self):
        console = (self.local / "observer_console.log").read_bytes()
        require(len(console) <= CONSOLE_LIMIT, "Console is oversized")
        final = json.loads(console.splitlines()[-1])
        writer, receiver = final.get("writer_final", {}), final.get("ros_receiver_final", {})
        size = self.health.stat().st_size
        require(final.get("storage_mode") == MODE and final.get("flushed_cleanly") is True
                and final.get("reason") in ("signal", "duration_reached")
                and final.get("output") == str(self.archive / "runtime_health")
                and final.get("live_output") == str(self.local / "runtime_health")
                and final.get("health_log") == str(self.health)
                and final.get("health_log_stat_error") is None
                and type(final.get("health_log_size_bytes")) is int
                and final["health_log_size_bytes"] == size <= HEALTH_LIMIT
                and writer.get("bytes_written") == size and writer.get("writer_alive") is False
                and writer.get("error") is None and writer.get("limit_reached") is False
                and writer.get("dropped_aggregates") == 0
                and receiver.get("thread_alive") is False and receiver.get("error") is None,
                "Collector did not close a complete, bounded, natively flushed local log")
        require(final.get("cleanup") == {
            "live_directory_removed": False, "archive_performed": False,
            "responsible_owner": "external_archive_owner", "local_evidence_retained": True},
            "Collector attempted archive/removal or did not retain original evidence")
        with self.health.open("rb") as stream:
            stream.seek(max(0, size - TAIL_LIMIT))
            tail = stream.read(TAIL_LIMIT)
        require(tail.endswith(b"\n") and json.loads(tail.splitlines()[-1]).get("event")
                == "RUNTIME_HEALTH_OBSERVER_STOPPED", "No complete native STOP record")


def validate_closed_raw(folder, original_live, original_archive, collector_source, expected_samples=()):
    """Re-derive closed health evidence; recorded booleans and new hashes do not suffice."""
    folder, original_live, original_archive = map(Path, (folder, original_live, original_archive))
    health = folder / "runtime_health/health.jsonl"
    size = file_binding(health, HEALTH_LIMIT)["bytes"]
    count, started, stopped, last_stamp = 0, None, None, None
    missing_samples = set(expected_samples)
    with health.open("rb") as stream:
        for raw in stream:
            require(raw.endswith(b"\n") and len(raw) <= SMALL_LIMIT, "Partial/oversized health row")
            row = json.loads(raw)
            event = row.get("event")
            require(row.get("schema_version") == 1 and finite(row.get("monotonic_s")),
                    "Health row lacks original schema/monotonic clock")
            if event == "RUNTIME_HEALTH_OBSERVER_STARTED":
                require(started is None and count == 0 and stopped is None, "Repeated/reordered START")
                started = row
            elif event == "RUNTIME_HEALTH_SAMPLE":
                require(started is not None and stopped is None
                        and (last_stamp is None or row["monotonic_s"] > last_stamp),
                        "Reordered/duplicate sample acquisition")
                validate_sample(row, row["monotonic_s"], original_archive / "runtime_health",
                                original_live / "runtime_health")
                last_stamp = row["monotonic_s"]
                missing_samples.discard(last_stamp)
                count += 1
            elif event == "RUNTIME_HEALTH_OBSERVER_STOPPED":
                require(started is not None and stopped is None and count > 0, "Invalid STOP ordering")
                stopped = row
            else:
                raise ValueError("Unexpected health event")
    require(started is not None and stopped is not None and count > 0, "Missing original START/sample/STOP")
    require(not missing_samples, "Native observed fresh sample is missing from original raw log")
    require(started.get("storage_mode") == MODE and started.get("ros_enabled") is True
            and started.get("duration_wall_s") == 7200. and started.get("period_wall_s") == 1.
            and started.get("live_output") == str(original_live / "runtime_health")
            and started.get("archive_output") == str(original_archive / "runtime_health")
            and started.get("archive_status") == "pending_external_owner"
            and started.get("output_mount", {}).get("filesystem") == "tmpfs"
            and started["output_mount"].get("mountpoint") == str(LIVE_BASE.parent)
            and started.get("source_sha256", {}).get("observe_runtime_health.py") == collector_source["sha256"],
            "Archived START source/path/tmpfs/policy differs")
    require(stopped.get("reason") in ("signal", "duration_reached")
            and type(stopped.get("samples_collected")) is int
            and stopped["samples_collected"] == count == stopped.get("samples_submitted")
            and started["monotonic_s"] <= last_stamp <= stopped["monotonic_s"],
            "STOP count/clock/reason does not match all original samples")
    console = (folder / "observer_console.log").read_bytes()
    require(len(console) <= CONSOLE_LIMIT and console.endswith(b"\n"), "Invalid bounded console")
    final = json.loads(console.splitlines()[-1])
    writer, receiver = final.get("writer_final", {}), final.get("ros_receiver_final", {})
    require(final.get("storage_mode") == MODE and final.get("flushed_cleanly") is True
            and final.get("reason") == stopped["reason"]
            and final.get("samples_collected") == count == final.get("samples_submitted")
            and final.get("output") == str(original_archive / "runtime_health")
            and final.get("live_output") == str(original_live / "runtime_health")
            and final.get("health_log") == str(original_live / "runtime_health/health.jsonl")
            and final.get("health_log_stat_error") is None
            and type(final.get("health_log_size_bytes")) is int and final["health_log_size_bytes"] == size
            and writer.get("bytes_written") == size and writer.get("writer_alive") is False
            and writer.get("error") is None and writer.get("limit_reached") is False
            and type(writer.get("dropped_aggregates")) is int and writer["dropped_aggregates"] == 0
            and receiver.get("thread_alive") is False and receiver.get("error") is None
            and stopped.get("ros_receiver_final") == receiver,
            "Archived console/STOP/writer/receiver/count/size do not agree")
    require(final.get("cleanup") == {"live_directory_removed": False, "archive_performed": False,
            "responsible_owner": "external_archive_owner", "local_evidence_retained": True},
            "Archived collector removed local evidence or performed its own archive")
    return {"samples": count, "last_sample_monotonic_s": last_stamp,
            "start_monotonic_s": started["monotonic_s"], "stop_monotonic_s": stopped["monotonic_s"]}


def _allowed_relative(name):
    return bool(re.fullmatch(
        r"(native_exit_terminal\.json|session_[0-9]{3}/(observer_console\.log|native_exit_terminal\.json|runtime_health/health\.jsonl))",
        name))


def _artifact_limit(name):
    return HEALTH_LIMIT if name.endswith("health.jsonl") else CONSOLE_LIMIT if name.endswith(".log") else SMALL_LIMIT


def _copy_new(source, destination, expected):
    require(file_binding(source, _artifact_limit(str(source))) == expected, "Original local bytes changed")
    require(not destination.exists() and not destination.is_symlink(), "Archive refuses overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(destination.parent.resolve() == destination.parent, "Archive ancestor alias")
    with source.open("rb") as original, destination.open("xb") as copied:
        while True:
            chunk = original.read(65536)
            if not chunk:
                break
            copied.write(chunk)
        copied.flush()
        os.fsync(copied.fileno())
    after = file_binding(source, _artifact_limit(str(source)))
    target = file_binding(destination, _artifact_limit(str(source)))
    require(after == expected and (target["bytes"], target["sha256"]) == (after["bytes"], after["sha256"]),
            "Bidirectional archive byte/hash verification failed")
    return {"local_before_and_after": after, "archive": target}


def _archive_worker(manifest_path, expected_sha):
    """Bound by its owner's process wait; blocked D I/O cannot stall that wait."""
    manifest_path = Path(manifest_path)
    require(file_binding(manifest_path, SMALL_LIMIT)["sha256"] == expected_sha, "Archive manifest changed")
    manifest = read_json(manifest_path)
    live, destination = Path(manifest["live_directory"]), Path(manifest["archive_directory"])
    check_private(live)
    require(manifest_path == live / "archive_manifest.json"
            and manifest["scope"] == SCOPE and destination.is_relative_to(D_ROOT.resolve(strict=True))
            and destination.is_relative_to((Path(manifest["source_root"]) / "results").resolve(strict=True)),
            "Archive manifest paths/root differ")
    require(file_binding(Path(__file__), SMALL_LIMIT) == manifest["owner_source"], "Archive owner source changed")
    require(file_binding(Path(manifest["source_root"]) / "scripts/observe_runtime_health.py", SMALL_LIMIT)
            == manifest["collector_source"], "Frozen collector source changed")
    native = read_json(live / "native_exit_terminal.json")
    require(native == manifest["native"], "Native aggregate changed")
    require(time.monotonic() >= native["all_native_exit_monotonic_s"], "Archive precedes native exit")
    started, started_utc, copies = time.monotonic(), utc(), []
    for item in manifest["files"]:
        name = item["relative_path"]
        require(_allowed_relative(name), "Unexpected local artifact in archive manifest")
        source, target = live / name, destination / name
        require(source.resolve() == source and target.resolve() == target, "Linked archive/live artifact")
        copies.append({"relative_path": name, **_copy_new(source, target, item["binding"])})
    manifest_binding = file_binding(manifest_path, SMALL_LIMIT)
    _copy_new(manifest_path, destination / "archive_manifest.json", manifest_binding)
    finished = time.monotonic()
    terminal = {
        "schema_version": 1, "scope": SCOPE, "source_root": manifest["source_root"],
        "live_directory": str(live), "archive_directory": str(destination),
        "owner_source": manifest["owner_source"], "collector_source": manifest["collector_source"],
        "native": native, "archive_manifest": {"path": str(destination / "archive_manifest.json"),
            "sha256": expected_sha, "bytes": manifest_binding["bytes"]},
        "archive": {"status": "VERIFIED_COPY", "started_utc": started_utc, "finished_utc": utc(),
            "started_monotonic_s": started, "payload_verified_monotonic_s": finished,
            "payload_elapsed_wall_s": finished - started,
            "wall_budget_s": manifest["archive_wall_budget_s"], "copies": copies,
            "local_evidence_removed": False},
        # Only the external owner can observe this process's eventual exit and
        # full elapsed time. This D artifact cannot self-authorize completion.
        "healthy_cleanup": False,
        "status": "COPY_VERIFIED_PENDING_OWNER_CLOSURE",
        "formal_seed_use_authorized": False, "readiness_claimed": False,
    }
    write_new(live / "execution_terminal.json", terminal)
    # A failed/partial D final remains evidence; the owner never retries or promotes it.
    write_new(destination / "execution_terminal.json", terminal)
    local_binding = file_binding(live / "execution_terminal.json", SMALL_LIMIT)
    copied_binding = file_binding(destination / "execution_terminal.json", SMALL_LIMIT)
    require((local_binding["bytes"], local_binding["sha256"])
            == (copied_binding["bytes"], copied_binding["sha256"]), "Final copy metadata differs")
    return 0


class RollingObserver:
    def __init__(self, directory, root, *, archive_wall_budget_s=ARCHIVE_WALL_S):
        require(finite(archive_wall_budget_s) and 0 < archive_wall_budget_s <= ARCHIVE_WALL_S,
                "Explicit finite archive budget must stay within original1800s allowance")
        self.root = Path(root)
        self.directory = archive_destination(directory, root)
        self.archive_wall_budget_s = float(archive_wall_budget_s)
        self.live = None
        self.sessions, self.rotations = [], []
        self.current = None
        self._finished = None
        self.started_utc = None
        self.collector_source = file_binding(self.root / "scripts/observe_runtime_health.py", SMALL_LIMIT)
        self.owner_source = file_binding(Path(__file__), SMALL_LIMIT)

    def __enter__(self):
        self.live = prepare_live()
        self.started_utc = utc()
        try:
            self.current = self._start_session()
            return self
        except BaseException:
            self.finish(exception=True)
            raise

    def _start_session(self):
        session = Session(self, len(self.sessions) + 1)
        self.sessions.append(session)
        return session.start()

    def check(self):
        require(self.current is not None and self._finished is None, "Local rolling owner is not live")
        before = self.current.check()
        if time.monotonic() - self.current.started >= ROTATE_WALL_S:
            old = self.current
            new = self._start_session()
            try:
                old_last, new_first = old.check(), new.check()
                result = old.stop_native()
                require(result["healthy_cleanup"], "Old local session native cleanup failed")
                new_after = new.check()
            except BaseException:
                new.stop_native(exception=True)
                raise
            self.current = new
            self.rotations.append({"old_index": old.index, "new_index": new.index,
                "old_last_fresh_sample": old_last, "new_first_fresh_sample": new_first,
                "new_fresh_after_old_finish": new_after,
                "completed_monotonic_s": time.monotonic()})
            return new_after
        return before

    def finish(self, exception=False):
        if self._finished is not None:
            return self._finished
        try:
            return self._finish(exception)
        except Exception as error:
            cleanup_errors = []
            for session in self.sessions:
                if session.native is None:
                    try:
                        session.stop_native(exception=True)
                    except Exception as caught:
                        cleanup_errors.append(type(caught).__name__ + ":" + str(caught))
            self._finished = {"schema_version": 1, "scope": SCOPE, "healthy_cleanup": False,
                "status": "OWNER_INFRA_ERROR", "error": type(error).__name__ + ":" + str(error),
                "live_directory": str(self.live), "cleanup_errors": cleanup_errors,
                "local_evidence_removed": False}
            if self.live is not None:
                path = self.live / "owner_failure_terminal.json"
                if not path.exists():
                    write_new(path, self._finished)
            return self._finished

    def _finish(self, exception=False):
        if self.live is None:
            self._finished = {"scope": SCOPE, "healthy_cleanup": False, "error": "No local owner started"}
            return self._finished
        for session in self.sessions:
            session.stop_native(exception=exception)
        for session in self.sessions:
            if session.native["healthy_cleanup"]:
                validate_closed_raw(session.local, session.local, session.archive, self.collector_source,
                    (session.first_check["latest_sample_monotonic_s"],
                     session.last_check["latest_sample_monotonic_s"]))
        native = {
            "schema_version": 1, "scope": SCOPE, "source_root": str(self.root),
            "live_directory": str(self.live), "archive_directory": str(self.directory),
            "started_utc": self.started_utc, "native_finished_utc": utc(),
            "session_duration_wall_s": 7200., "rotation_wall_s": 5400.,
            "max_sample_age_wall_s": 10., "driver_exception": bool(exception),
            "all_native_exit_monotonic_s": max((s.native["native_exit_monotonic_s"] for s in self.sessions),
                                               default=time.monotonic()),
            "sessions": [s.native for s in self.sessions], "rotations": self.rotations,
            "healthy_cleanup": bool(self.sessions) and not exception
                               and all(s.native["healthy_cleanup"] for s in self.sessions)}
        write_new(self.live / "native_exit_terminal.json", native)
        files = []
        names = ["native_exit_terminal.json"]
        for session in self.sessions:
            names.extend(str(p.relative_to(self.live)).replace(os.sep, "/") for p in
                         (session.local / "observer_console.log", session.local / "native_exit_terminal.json",
                          session.health) if p.is_file())
        for name in names:
            files.append({"relative_path": name, "binding": file_binding(self.live / name, _artifact_limit(name))})
        manifest = {"schema_version": 1, "scope": SCOPE, "source_root": str(self.root),
            "live_directory": str(self.live), "archive_directory": str(self.directory),
            "native": native, "files": files, "owner_source": self.owner_source,
            "collector_source": self.collector_source, "archive_wall_budget_s": self.archive_wall_budget_s}
        path = self.live / "archive_manifest.json"
        write_new(path, manifest)
        digest = file_binding(path, SMALL_LIMIT)["sha256"]
        command = [sys.executable, "-B", str(Path(__file__)), "_archive-worker",
                   "--manifest", str(path), "--manifest-sha256", digest]
        started = time.monotonic()
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        console = Console(process.stdout, self.live / "archive_console.log")
        error, forced = None, False
        try:
            code = process.wait(timeout=self.archive_wall_budget_s)
        except subprocess.TimeoutExpired:
            forced, error = True, "ARCHIVE_WALL_TIMEOUT"
            try:
                process.kill()
                code = process.wait(timeout=5.)
            except (OSError, subprocess.TimeoutExpired) as caught:
                code, error = process.poll(), "ARCHIVE_FORCED_CLEANUP:" + str(caught)
        try:
            console.finish()
        except Exception as caught:
            error = "ARCHIVE_CONSOLE:" + str(caught)
        execution = {"command": command, "returncode": code, "forced_stop": forced,
                     "error": error, "elapsed_wall_s": time.monotonic() - started,
                     "wall_budget_s": self.archive_wall_budget_s}
        write_new(self.live / "archive_process_terminal.json", execution)
        if code == 0 and not forced and error is None and execution["elapsed_wall_s"] <= self.archive_wall_budget_s:
            copied = read_json(self.live / "execution_terminal.json")
            local_binding = file_binding(self.live / "execution_terminal.json", SMALL_LIMIT)
            self._finished = {**copied, "healthy_cleanup": native["healthy_cleanup"],
                "status": "COMPLETE" if native["healthy_cleanup"] else "NATIVE_FAILED_RAW_ARCHIVED",
                "archive_process": execution,
                "copy_terminal": {**local_binding, "path": str(self.directory / "execution_terminal.json")}}
            write_new(self.live / "owner_execution_terminal.json", self._finished)
        else:
            self._finished = {"schema_version": 1, "scope": SCOPE, "healthy_cleanup": False,
                "status": "ARCHIVE_INFRA_ERROR", "native": native, "archive_process": execution,
                "live_directory": str(self.live), "local_evidence_removed": False}
            write_new(self.live / "owner_failure_terminal.json", self._finished)
        return self._finished

    def __exit__(self, exc_type, exc, traceback):
        result = self.finish(exception=exc_type is not None)
        if exc_type is None:
            require(result.get("healthy_cleanup") is True, "Local observer/native/archive did not close healthily")


class SingleObserver(RollingObserver):
    def check(self):
        require(self.current is not None and self._finished is None, "Single owner is not live")
        return self.current.check()


def make_observer(directory, root, *, archive_wall_budget_s=ARCHIVE_WALL_S):
    return RollingObserver(directory, root, archive_wall_budget_s=archive_wall_budget_s)


def tool_manifest():
    """Portable source identity only; never starts an observer or reads results."""
    external = Path(__file__).resolve().parent
    return {"schema_version": 1, "scope": SCOPE,
        "files": {name: file_binding(external / name, SMALL_LIMIT)["sha256"] for name in
                  ("local_runtime_observer41.py", "test_local_runtime_observer41.py")},
        "live_base": LIVE_BASE.as_posix(), "sample_max_age_wall_s": 10.,
        "session_wall_s": 7200., "rotation_wall_s": 5400.,
        "health_limit_bytes": HEALTH_LIMIT, "console_limit_bytes": CONSOLE_LIMIT,
        "archive_max_wall_s": ARCHIVE_WALL_S,
        "requires_original_owner_post_wait_result": True,
        "native_stop_precedes_D_archive": True, "removes_local_evidence": False}


def validate_observer_root(terminal_or_none, directory, root):
    """Require original caller-recorded owner outcome, then validate copied raw.

    Persist the returned owner_terminal in the actual outer driver/pressure
    receipt. A D copy candidate alone or None can never authorize completion.
    Age is anchored to native stop, not the separately timed D copy.
    """
    require(isinstance(terminal_or_none, dict), "Original owner post-wait outcome is required; None cannot authorize")
    directory = Path(directory).resolve(strict=True)
    require(directory.is_relative_to((Path(root) / "results").resolve(strict=True))
            and directory.is_relative_to(D_ROOT.resolve(strict=True)), "Archived owner escaped actual D results")
    copied = read_json(directory / "execution_terminal.json")
    actual = terminal_or_none
    require(copied.get("status") == "COPY_VERIFIED_PENDING_OWNER_CLOSURE"
            and copied.get("healthy_cleanup") is False,
            "Original D copy candidate was promoted or rewritten")
    expected_copy = file_binding(directory / "execution_terminal.json", SMALL_LIMIT)
    require(actual.get("copy_terminal") == expected_copy,
            "Caller-recorded copy terminal binding differs")
    process = actual.get("archive_process", {})
    require(type(process.get("returncode")) is int and process["returncode"] == 0
            and process.get("forced_stop") is False and process.get("error") is None
            and finite(process.get("elapsed_wall_s")) and finite(process.get("wall_budget_s"))
            and 0 <= process["elapsed_wall_s"] <= process["wall_budget_s"] <= ARCHIVE_WALL_S
            and process["wall_budget_s"] > 0,
            "Original owner observed failed, forced, or over-budget archive process")
    require(actual == {**copied, "healthy_cleanup": True, "status": "COMPLETE",
                       "archive_process": process, "copy_terminal": expected_copy},
            "Owner outcome differs from original immutable D copy candidate")
    require(actual.get("schema_version") == 1 and actual.get("scope") == SCOPE
            and actual.get("source_root") == str(Path(root))
            and actual.get("archive_directory") == str(directory)
            and actual.get("status") == "COMPLETE" and actual.get("healthy_cleanup") is True
            and actual.get("formal_seed_use_authorized") is False and actual.get("readiness_claimed") is False,
            "Original local owner did not complete natively and archive successfully")
    manifest = read_json(directory / "archive_manifest.json")
    require(file_binding(directory / "archive_manifest.json", SMALL_LIMIT) == actual["archive_manifest"],
            "Archived manifest changed")
    live = Path(actual["live_directory"])
    require(live.parent == LIVE_BASE and re.fullmatch(r"owner41_[0-9a-f]{32}", live.name)
            and manifest.get("live_directory") == str(live)
            and manifest.get("archive_directory") == str(directory)
            and manifest.get("source_root") == str(Path(root)), "Original live/archive provenance differs")
    require(process.get("command") == [sys.executable, "-B", str(Path(__file__)), "_archive-worker",
            "--manifest", str(live / "archive_manifest.json"),
            "--manifest-sha256", actual["archive_manifest"]["sha256"]],
            "Original archive process command/manifest binding differs")
    require(actual["owner_source"] == file_binding(Path(__file__), SMALL_LIMIT)
            and actual["collector_source"] == file_binding(Path(root) / "scripts/observe_runtime_health.py", SMALL_LIMIT),
            "Actual owner or frozen collector source changed")
    require(manifest.get("owner_source") == actual["owner_source"]
            and manifest.get("collector_source") == actual["collector_source"]
            and manifest.get("scope") == SCOPE and manifest.get("schema_version") == 1,
            "Manifest owner/collector/scope differs")
    native, archive = actual["native"], actual["archive"]
    require(native == manifest["native"] == read_json(directory / "native_exit_terminal.json")
            and native.get("healthy_cleanup") is True
            and native.get("driver_exception") is False and native.get("session_duration_wall_s") == 7200.
            and native.get("rotation_wall_s") == 5400. and native.get("max_sample_age_wall_s") == 10.,
            "Native original bounds or outcome changed")
    require(archive.get("status") == "VERIFIED_COPY" and archive.get("local_evidence_removed") is False
            and finite(archive.get("wall_budget_s")) and 0 < archive["wall_budget_s"] <= ARCHIVE_WALL_S
            and archive["wall_budget_s"] == manifest.get("archive_wall_budget_s")
            and archive["started_monotonic_s"] >= native["all_native_exit_monotonic_s"]
            and 0 <= archive["payload_elapsed_wall_s"] <= archive["wall_budget_s"]
            and archive["payload_verified_monotonic_s"] - archive["started_monotonic_s"]
                == archive["payload_elapsed_wall_s"]
            and archive["wall_budget_s"] == process["wall_budget_s"]
            and archive["payload_elapsed_wall_s"] <= process["elapsed_wall_s"] + 1e-6,
            "Archive timing/phase/budget differs")
    files, copies = manifest["files"], archive["copies"]
    require(len(files) == len(copies) and len({f["relative_path"] for f in files}) == len(files),
            "Original artifact denominator differs")
    for original, copied in zip(files, copies):
        name = original["relative_path"]
        require(_allowed_relative(name) and copied["relative_path"] == name
                and original["binding"] == copied["local_before_and_after"]
                and original["binding"]["path"] == str(live / name), "Original copy input binding differs")
        target = file_binding(directory / name, _artifact_limit(name))
        require(target == copied["archive"]
                and (target["bytes"], target["sha256"])
                    == (original["binding"]["bytes"], original["binding"]["sha256"]),
                "Archived raw bytes/hash differ from original local evidence")
    sessions = native.get("sessions")
    require(isinstance(sessions, list) and sessions and len(native.get("rotations", [])) == len(sessions)-1,
            "Missing native sessions/rotation evidence")
    for index, session in enumerate(sessions, 1):
        local, folder = live / f"session_{index:03d}", directory / f"session_{index:03d}"
        require(session == read_json(folder / "native_exit_terminal.json")
                and session.get("index") == index and session.get("command") == observer_command(root, folder, local)
                and session.get("healthy_cleanup") is True and session.get("observer_exit_code") == 0
                and type(session["observer_exit_code"]) is int
                and all(session.get(key) is False for key in
                        ("observer_forced_stop", "ended_before_requested_stop", "driver_exception"))
                and session.get("errors") == [] and session.get("local_evidence_removed") is False,
                "Original native session command/outcome/cleanup differs")
        first, final = session["first_fresh_sample"], session["final_fresh_sample"]
        for fresh in (first, final):
            require(finite(fresh.get("latest_sample_monotonic_s"))
                    and finite(fresh.get("sample_age_wall_s")) and -1e-6 <= fresh["sample_age_wall_s"] <= 10.
                    and fresh.get("max_sample_age_wall_s") == 10.
                    and finite(fresh.get("checked_monotonic_s"))
                    and abs(fresh["checked_monotonic_s"] - fresh["latest_sample_monotonic_s"]
                            - fresh["sample_age_wall_s"]) <= 1e-6, "Original10s freshness differs")
        require(0 <= session["started_monotonic_s"] <= session["stop_requested_monotonic_s"]
                <= session["native_exit_monotonic_s"]
                and session["stop_requested_monotonic_s"] - session["started_monotonic_s"] < 7200.
                and -1e-6 <= session["stop_requested_monotonic_s"] - final["latest_sample_monotonic_s"] <= 10.
                and session["native_shutdown_wall_s"] <= 10.,
                "Native timing changed; archive time must not replace native freshness")
        proof = session["capacity"]
        require(proof["mount"] == {"mountpoint": str(LIVE_BASE.parent), "filesystem": "tmpfs"}
                and proof["free_bytes"] >= proof["required_free_bytes"]
                and proof["required_free_bytes"] == 2 * (HEALTH_LIMIT + CONSOLE_LIMIT + SMALL_LIMIT)
                and proof["health_limit_bytes"] == HEALTH_LIMIT and proof["console_limit_bytes"] == CONSOLE_LIMIT,
                "Original tmpfs capacity/mount/bounds missing")
        required = {f"session_{index:03d}/{name}" for name in
                    ("observer_console.log", "native_exit_terminal.json", "runtime_health/health.jsonl")}
        require(required <= {f["relative_path"] for f in files}, "Original raw session artifacts missing")
        raw = validate_closed_raw(folder, local, folder, actual["collector_source"],
            (first["latest_sample_monotonic_s"], final["latest_sample_monotonic_s"]))
        require(final["latest_sample_monotonic_s"] <= raw["last_sample_monotonic_s"]
                    <= session["native_exit_monotonic_s"]
                and session["started_monotonic_s"] <= session["first_fresh_monotonic_s"]
                    <= session["stop_requested_monotonic_s"],
                "Native fresh fields disagree with original raw log")
        if index > 1:
            previous, rotation = sessions[index - 2], native["rotations"][index - 2]
            require(rotation.get("old_index") == index - 1 and rotation.get("new_index") == index
                    and previous["started_monotonic_s"] + ROTATE_WALL_S <= session["started_monotonic_s"]
                    <= session["first_fresh_monotonic_s"] <= previous["native_exit_monotonic_s"]
                    <= rotation["completed_monotonic_s"] <= session["stop_requested_monotonic_s"]
                    and first["latest_sample_monotonic_s"]
                        <= previous["final_fresh_sample"]["latest_sample_monotonic_s"] + 10.,
                    "No original overlap/handoff between local sessions")
            for key in ("old_last_fresh_sample", "new_first_fresh_sample", "new_fresh_after_old_finish"):
                fresh = rotation.get(key, {})
                require(finite(fresh.get("latest_sample_monotonic_s"))
                        and finite(fresh.get("sample_age_wall_s")) and -1e-6 <= fresh["sample_age_wall_s"] <= 10.
                        and fresh.get("max_sample_age_wall_s") == 10., "Rotation lost original10s freshness")
    require(native["all_native_exit_monotonic_s"]
            == max(session["native_exit_monotonic_s"] for session in sessions), "Native exit aggregate differs")
    require(len(files) == 1 + 3 * len(sessions)
            and "native_exit_terminal.json" in {f["relative_path"] for f in files},
            "Original complete raw artifact set changed")
    return {"path": str(directory / "execution_terminal.json"),
            "sha256": file_binding(directory / "execution_terminal.json", SMALL_LIMIT)["sha256"],
            "scope": SCOPE, "session_count": len(sessions), "native_and_archive_both_verified": True,
            "owner_terminal": actual}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("_archive-worker",))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        raise SystemExit(_archive_worker(args.manifest, args.manifest_sha256))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"scope": SCOPE, "status": "ARCHIVE_REFUSED", "error": str(error)}), file=sys.stderr)
        raise SystemExit(2)
