#!/usr/bin/env python3
"""Capture actual magnetic ELF mappings from one owned Gazebo process tree.

Only the supplied session/group and its descendants are inspected. No global
process enumeration, signalling, simulator launch, or target truth is used.
The source registration and actual mapped binary evidence are separate fields.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "config/gazebo_magnetic_reference.json"
REGISTRATION = ROOT / "config/gazebo_magnetic_runtime.json"
KINDS = {"gazebo_sim": "libgz-sim8-magnetometer-system.so", "gazebo_sensors": "libgz-sensors8-magnetometer.so"}
SOURCE_FIELDS = tuple(kind + suffix for kind in KINDS
                      for suffix in ("_version", "_commit", "_source_sha256"))


def load_registration(registration_json: Path, lookup_json: Path = LOOKUP) -> dict:
    """Validate a pre-audited environment declaration; never register loaded ELF.

    Release-source variants are an explicit whitelist. Equal source file hashes
    do not by themselves permit an unregistered release tag or commit.
    """
    registration = json.loads(Path(registration_json).read_text(encoding="utf-8"))
    lookup = json.loads(Path(lookup_json).read_text(encoding="utf-8"))
    if registration.get("schema_version") != 1 or registration.get("status") != "AUDITED_INSTALLED_PACKAGES":
        raise ValueError("magnetic runtime registration must be a pre-audited schema-1 declaration")
    environment_id = registration.get("environment_id")
    if not isinstance(environment_id, str) or not environment_id.strip():
        raise ValueError("magnetic runtime registration requires an environment_id")
    environment = registration.get("environment", {})
    if environment.get("os_id") != "ubuntu" or (environment.get("os_version"), environment.get("ros_distro")) not in {
            ("24.04", "jazzy"), ("22.04", "humble")}:
        raise ValueError("magnetic runtime registration environment has not been audited")
    source = registration.get("source_registration", {})
    variants = lookup.get("audited_source_variants", [])
    if (not variants or any(set(item) != set(SOURCE_FIELDS) for item in variants)
            or set(source) != set(SOURCE_FIELDS) or source not in variants):
        raise ValueError("magnetic release source registration is outside the audited variants")
    libraries = registration.get("libraries", {})
    if set(libraries) != set(KINDS):
        raise ValueError("magnetic runtime registration must identify exactly both magnetic libraries")
    for kind, prefix in KINDS.items():
        library = libraries[kind]
        path = library.get("path", "")
        if not isinstance(path, str):
            raise ValueError("magnetic runtime library path must be a string: " + kind)
        filename = PurePosixPath(path).name
        if (not path.startswith("/") or ".." in PurePosixPath(path).parts
                or filename != prefix + "." + source[kind + "_version"]
                or not re.fullmatch(r"[0-9a-f]{64}", library.get("sha256", ""))
                or not library.get("package") or not library.get("package_version")
                or library.get("package_file_md5_matches") is not True):
            raise ValueError("magnetic runtime registration library audit is incomplete: " + kind)
        if environment["ros_distro"] == "jazzy":
            expected_prefix = "/opt/ros/jazzy/opt/" + ("gz_sim_vendor/" if kind == "gazebo_sim" else "gz_sensors_vendor/")
            expected_package = "ros-jazzy-gz-" + ("sim-vendor" if kind == "gazebo_sim" else "sensors-vendor")
        else:
            expected_prefix = "/usr/lib/x86_64-linux-gnu/"
            expected_package = "libgz-sim8-plugins:amd64" if kind == "gazebo_sim" else "libgz-sensors8-magnetometer:amd64"
        if not path.startswith(expected_prefix) or library["package"] != expected_package:
            raise ValueError("magnetic runtime library path/package conflicts with its declared environment")
    provenance = registration.get("package_repository_provenance", {})
    if not all(isinstance(provenance.get(field), str) and provenance[field].strip()
               for field in ("repository", "authentication", "evidence")):
        raise ValueError("magnetic runtime registration requires repository authentication evidence")
    return registration


class LibrariesNotReady(ValueError):
    pass


def read_bounded(path: Path, limit: int) -> str:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("proc evidence size limit exceeded: " + str(path))
    return data.decode("utf-8", errors="surrogateescape")


def parse_stat(text: str) -> dict:
    start, end = text.find("("), text.rfind(")")
    if start < 1 or end <= start:
        raise ValueError("malformed proc stat")
    pid = int(text[:start].strip())
    fields = text[end + 1:].split()
    if len(fields) < 20:
        raise ValueError("truncated proc stat")
    return {"pid": pid, "comm": text[start+1:end], "parent_pid": int(fields[1]),
            "process_group": int(fields[2]), "session": int(fields[3]), "start_ticks": int(fields[19])}


def parse_magnetic_maps(text: str) -> list[dict]:
    result = []
    for line in text.splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or not fields[4].isdigit() or int(fields[4]) == 0:
            continue
        path = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), fields[5])
        deleted = path.endswith(" (deleted)")
        filename = Path(path[:-10] if deleted else path).name
        for kind, prefix in KINDS.items():
            if filename == prefix or filename.startswith(prefix + "."):
                major, minor = (int(value, 16) for value in fields[3].split(":"))
                result.append({"kind": kind, "address": fields[0], "permissions": fields[1],
                               "device_major": major, "device_minor": minor, "inode": int(fields[4]),
                               "mapped_path": path, "deleted": deleted})
    return result


def mapped_binary_evidence(proc_root: Path, pid: int, mapping: dict) -> dict:
    if mapping["deleted"] or not mapping["mapped_path"].startswith("/"):
        raise ValueError("magnetic mapped binary is deleted or has no absolute path")
    namespace_path = proc_root / str(pid) / "root" / mapping["mapped_path"].lstrip("/")
    before = namespace_path.stat()
    if (before.st_ino != mapping["inode"] or os.major(before.st_dev) != mapping["device_major"]
            or os.minor(before.st_dev) != mapping["device_minor"]):
        raise ValueError("mapped magnetic binary no longer matches filesystem device/inode")
    digest = hashlib.sha256()
    if before.st_size > 64 * 1024 * 1024:
        raise ValueError("magnetic binary size exceeds registered evidence bound")
    with namespace_path.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError("mapped magnetic library is not ELF")
        stream.seek(0)
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = namespace_path.stat()
    if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns):
        raise ValueError("mapped magnetic binary changed during hashing")
    return {"kind": mapping["kind"], "mapped_path": mapping["mapped_path"], "inode": before.st_ino,
            "device_major": mapping["device_major"], "device_minor": mapping["device_minor"],
            "bytes": before.st_size, "sha256": digest.hexdigest(), "observed_pids": [pid]}


def capture(leader_pid: int, *, proc_root: Path = Path("/proc"), lookup_json: Path = LOOKUP,
            registration_json: Path = REGISTRATION,
            process_limit: int = 64, thread_limit: int = 512) -> dict:
    if isinstance(leader_pid, bool) or not isinstance(leader_pid, int) or leader_pid <= 0:
        raise ValueError("a positive owned Gazebo session/group leader PID is required")
    registration_json = Path(registration_json).resolve()
    registration_bytes = registration_json.read_bytes()
    registration = load_registration(registration_json, lookup_json)
    if registration_json.read_bytes() != registration_bytes:
        raise ValueError("magnetic runtime registration changed while being validated")
    proc_root = Path(proc_root)
    def identity(pid):
        item = parse_stat(read_bounded(proc_root / str(pid) / "stat", 65536))
        if item["pid"] != pid:
            raise ValueError("proc PID identity mismatch")
        return item
    leader = identity(leader_pid)
    if leader["session"] != leader_pid or leader["process_group"] != leader_pid:
        raise ValueError("Gazebo must have its own registered session/process group")
    queue, seen, processes, excluded, binaries = deque([leader_pid]), set(), [], [], {}
    while queue:
        pid = queue.popleft()
        if pid in seen:
            continue
        seen.add(pid)
        if len(seen) > process_limit:
            raise ValueError("owned Gazebo process evidence bound exceeded")
        try:
            before = identity(pid)
        except FileNotFoundError:
            continue
        if before["session"] != leader_pid or before["process_group"] != leader_pid:
            excluded.append({"pid": pid, "reason": "descendant_outside_owned_session_group"})
            continue  # Never inspect this process's maps or descendants.
        tasks = list((proc_root / str(pid) / "task").iterdir())
        if len(tasks) > thread_limit:
            raise ValueError("owned Gazebo thread evidence bound exceeded")
        for task in tasks:
            if task.name.isdigit():
                try:
                    queue.extend(int(child) for child in read_bounded(task / "children", 65536).split())
                except FileNotFoundError:
                    pass
        mappings = parse_magnetic_maps(read_bounded(proc_root / str(pid) / "maps", 16 * 1024 * 1024))
        for item in mappings:
            key = (item["kind"], item["device_major"], item["device_minor"], item["inode"])
            if key in binaries:
                if pid not in binaries[key]["observed_pids"]:
                    binaries[key]["observed_pids"].append(pid)
            else:
                binaries[key] = mapped_binary_evidence(proc_root, pid, item)
        if identity(pid) != before:
            raise ValueError("Gazebo PID was reused or changed process identity during capture")
        processes.append(before)
    if identity(leader_pid) != leader:
        raise ValueError("Gazebo session leader changed during capture")
    actual = list(binaries.values())
    for kind in KINDS:
        selected = [item for item in actual if item["kind"] == kind]
        if not selected:
            raise LibrariesNotReady("mapped magnetic library not loaded yet: " + kind)
        if len(selected) != 1:
            raise ValueError("exactly one mapped registered magnetic library required: " + kind)
        expected = registration["libraries"][kind]
        if selected[0]["sha256"] != expected["sha256"] or selected[0]["mapped_path"] != expected["path"]:
            raise ValueError("loaded magnetic library differs from the registered environment: " + kind)
    return {"schema_version": 1, "verified": True, "captured_monotonic_s": time.monotonic(),
            "owned_leader_pid": leader_pid, "owned_session": leader_pid, "owned_process_group": leader_pid,
            "scope": "bounded descendant walk via owned /proc/PID/task/TID/children; no global process enumeration",
            "observed_processes": processes, "excluded_descendants": excluded,
            "actual_loaded_libraries": actual,
            "registration_path": str(registration_json),
            "registration_sha256": hashlib.sha256(registration_bytes).hexdigest(),
            "environment_id": registration["environment_id"],
            "expected_source_registration": registration["source_registration"],
            "source_vs_binary_limit": "Mapped ELF device/inode/hash matches the registered binary; release source provenance remains a separate declaration"}


def capture_ready(leader_pid: int, *, registration_json: Path = REGISTRATION,
                  lookup_json: Path = LOOKUP) -> dict:
    # World service advertisement can precede completion of plugin loading.
    # Only a missing transient library/process is retried; hash or scope
    # conflicts are terminal. At most 0.9 s of explicit retry delay.
    for attempt in range(10):
        try:
            return {**capture(leader_pid, registration_json=registration_json,
                              lookup_json=lookup_json), "capture_attempts": attempt + 1}
        except (LibrariesNotReady, FileNotFoundError):
            if attempt == 9:
                raise
            time.sleep(.1)
    raise AssertionError("bounded capture loop exhausted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gazebo-pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--registration", default=REGISTRATION, type=Path)
    parser.add_argument("--source-lookup", default=LOOKUP, type=Path)
    args = parser.parse_args()
    result = capture_ready(args.gazebo_pid, registration_json=args.registration,
                           lookup_json=args.source_lookup)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
