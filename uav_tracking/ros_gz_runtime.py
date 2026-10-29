"""Prospective ros_gz source/ELF registration and owned-PID verification.

This standard-library module launches no ROS or simulator. Registration is a
candidate for independent review; consumers must bind its file SHA separately.
Live evidence covers the executable, ldd closure and ros_gz mappings, not every
library that an unrelated ROS plugin may load dynamically.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess

MAX_COMMAND_BYTES = 16 * 1024 * 1024
# RelWithDebInfo libros_gz_bridge is about 538 MB in the actual A01 build.
# Keep debug symbols and stream hashes; this is a resource bound, not flight safety.
MAX_ELF_BYTES = 1024 * 1024 * 1024
MAX_PROC_BYTES = 8 * 1024 * 1024
SCHEMA = 1
KIND = "ROS_GZ_RUNTIME_REGISTRATION"


class RuntimeRegistrationError(ValueError):
    pass


class RuntimeBackend:
    """Native Linux reads. Tests override probes and explicitly mark fixtures."""
    fixture_only = False

    def __init__(self, proc_root=Path("/proc")):
        self.proc_root = Path(proc_root)

    def command(self, argv, *, cwd=None):
        try:
            result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeRegistrationError("Probe could not complete: " + argv[0]) from error
        if result.returncode:
            raise RuntimeRegistrationError("Probe failed: " + argv[0] + " (exit " + str(result.returncode) + ")")
        if len(result.stdout) > MAX_COMMAND_BYTES:
            raise RuntimeRegistrationError("Probe output exceeded bound: " + argv[0])
        return result.stdout

    def proc_text(self, pid, filename):
        with (self.proc_root / str(pid) / filename).open("rb") as stream:
            data = stream.read(MAX_PROC_BYTES + 1)
        if len(data) > MAX_PROC_BYTES:
            raise RuntimeRegistrationError("Proc record exceeded bound: " + filename)
        return os.fsdecode(data)

    def exe_path(self, pid):
        return os.readlink(self.proc_root / str(pid) / "exe")

    def exe_file(self, pid):
        return self.proc_root / str(pid) / "exe"

    def namespace_file(self, pid, path):
        return self.proc_root / str(pid) / "root" / str(path).lstrip("/")


def _backend(value):
    value = value or RuntimeBackend()
    if platform.system() != "Linux" and not value.fixture_only:
        raise RuntimeRegistrationError("Production ros_gz runtime probes require Linux")
    return value


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def registration_digest(value):
    content = {key: item for key, item in value.items() if key != "registration_digest"}
    return _sha(json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _regular_file(path, *, elf=False):
    requested = Path(path).absolute()
    resolved = requested.resolve(strict=True)
    with resolved.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_ELF_BYTES:
            raise RuntimeRegistrationError("Not a bounded regular file: " + str(requested))
        if elf and stream.read(4) != b"\x7fELF":
            raise RuntimeRegistrationError("Expected ELF file: " + str(requested))
        stream.seek(0)
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if (identity(before) != identity(after) or identity(after) != identity(resolved.stat())
            or requested.resolve(strict=True) != resolved):
        raise RuntimeRegistrationError("File changed during hashing: " + str(requested))
    return {"path": str(requested), "real_path": str(resolved), "bytes": before.st_size,
            "sha256": digest.hexdigest(), "device_major": os.major(before.st_dev) if os.name != "nt" else 0,
            "device_minor": os.minor(before.st_dev) if os.name != "nt" else before.st_dev,
            "inode": before.st_ino}


def _inside(path, root):
    return Path(path).resolve(strict=True).is_relative_to(Path(root).resolve(strict=True))


def source_snapshot(repo_root, backend):
    repo = Path(repo_root).resolve(strict=True)

    def git(*arguments):
        return backend.command(["git", "-C", str(repo), *arguments])

    top = Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve(strict=True)
    if top != repo:
        raise RuntimeRegistrationError("repo_root must be the actual Git top-level directory")
    commit = git("rev-parse", "HEAD").decode("ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{40,64}", commit):
        raise RuntimeRegistrationError("Invalid Git commit")
    status_bytes = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    if any(row.startswith(b"?? ") for row in status_bytes.split(b"\0")):
        raise RuntimeRegistrationError("Untracked source files must be reviewed or removed before registration")
    flags = git("ls-files", "-v", "-z")
    if not flags or any(row and not row.startswith(b"H ") for row in flags.split(b"\0")):
        raise RuntimeRegistrationError("Source index has hidden, skipped or conflicted tracked entries")
    diff = git("diff", "--binary", "HEAD", "--")
    staged = git("diff", "--cached", "--binary", "--")
    submodules = git("submodule", "status", "--recursive")
    return {"repo_root": str(repo), "commit": commit,
            "tracked_diff_sha256": _sha(diff), "tracked_diff_bytes": len(diff),
            "staged_diff_sha256": _sha(staged), "tracked_status_sha256": _sha(status_bytes),
            "submodule_status_sha256": _sha(submodules)}


def parse_ldd(text):
    """Resolve ldd's complete printed DT_NEEDED closure; reject missing libs."""
    libraries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"linux-vdso\S*\s+\(0x[0-9a-fA-F]+\)", line):
            continue
        matched = re.fullmatch(r"(\S+)\s+=>\s+(.+?)\s+\(0x[0-9a-fA-F]+\)", line)
        direct = re.fullmatch(r"(.+?)\s+\(0x[0-9a-fA-F]+\)", line)
        if matched:
            soname, path = matched.groups()
        elif direct and Path(direct[1]).is_absolute():
            path, soname = direct[1], Path(direct[1]).name
        else:
            raise RuntimeRegistrationError("Unresolved or unsupported ldd entry: " + line)
        if not Path(path).is_absolute():
            raise RuntimeRegistrationError("ldd dependency is not an absolute path")
        libraries.append({"soname": soname, "path": path})
    if not libraries:
        raise RuntimeRegistrationError("ldd did not identify any ELF dependencies")
    return libraries


def _bridge_files(overlay_root, backend, plugin_elf_paths=()):
    overlay = Path(overlay_root).resolve(strict=True)
    candidates = [overlay / "install/ros_gz_bridge/lib/ros_gz_bridge/parameter_bridge",
                  overlay / "install/lib/ros_gz_bridge/parameter_bridge"]
    found = [path for path in candidates if path.is_file()]
    if len(found) != 1:
        raise RuntimeRegistrationError("Require exactly one isolated/merged parameter_bridge in overlay/install")
    executable = _regular_file(found[0], elf=True)
    if not _inside(executable["real_path"], overlay):
        raise RuntimeRegistrationError("parameter_bridge resolves outside selected overlay")
    plugins = [_regular_file(path, elf=True) for path in plugin_elf_paths]
    plugins.sort(key=lambda row: row["path"])
    if len({row["real_path"] for row in plugins}) != len(plugins):
        raise RuntimeRegistrationError("Duplicate explicit plugin ELF")
    dependencies_by_name = {}
    for inspected in [executable, *plugins]:
        for row in parse_ldd(os.fsdecode(backend.command(["ldd", inspected["path"]]))):
            existing = dependencies_by_name.get(row["soname"])
            if existing is not None:
                if str(Path(row["path"]).resolve(strict=True)) != existing["real_path"]:
                    raise RuntimeRegistrationError("Plugin/executable resolve conflicting dependency paths: " + row["soname"])
                continue
            item = {"soname": row["soname"], **_regular_file(row["path"], elf=True)}
            if re.fullmatch(r"libros_gz_bridge\.so(?:\.[0-9]+)*", item["soname"]) and not _inside(item["real_path"], overlay):
                raise RuntimeRegistrationError("Old or mixed ros_gz dependency outside selected overlay")
            dependencies_by_name[item["soname"]] = item
    for plugin in plugins:
        if (re.fullmatch(r"libros_gz_bridge\.so(?:\.[0-9]+)*", Path(plugin["real_path"]).name)
                and not _inside(plugin["real_path"], overlay)):
            raise RuntimeRegistrationError("Old bridge cannot be declared as an allowed plugin")
    dependencies = sorted(dependencies_by_name.values(), key=lambda row: (row["soname"], row["path"]))
    bridge = [row for row in dependencies if re.fullmatch(r"libros_gz_bridge\.so(?:\.[0-9]+)*", row["soname"])]
    if len(bridge) != 1:
        raise RuntimeRegistrationError("ldd must resolve exactly one libros_gz_bridge ELF")
    return executable, dependencies, plugins


def create_registration(overlay_root, repo_root, *, patch_path=None, expected_commit=None,
                        plugin_elf_paths=(), backend=None):
    backend = _backend(backend)
    overlay = Path(overlay_root).resolve(strict=True)
    source = source_snapshot(repo_root, backend)
    if expected_commit is not None and source["commit"] != expected_commit:
        raise RuntimeRegistrationError("Source commit differs from explicit expected commit")
    if source["tracked_diff_bytes"] and patch_path is None:
        raise RuntimeRegistrationError("A dirty source checkout requires an explicit reviewed patch file")
    patch = _regular_file(patch_path) if patch_path is not None else None
    executable, dependencies, plugins = _bridge_files(overlay, backend, plugin_elf_paths)
    if source_snapshot(repo_root, backend) != source:
        raise RuntimeRegistrationError("Source changed during registration")
    registration = {"schema_version": SCHEMA, "kind": KIND, "status": "CANDIDATE_REQUIRES_INDEPENDENT_REVIEW",
        "created_utc": datetime.now(timezone.utc).isoformat(), "fixture_only": bool(backend.fixture_only),
        "evidence_scope": "ORCHESTRATION_FIXTURE_ONLY" if backend.fixture_only else "LINUX_ROS_GZ_SOURCE_AND_ELF",
        "overlay_root": str(overlay), "source": source, "patch": patch,
        "executable": executable, "dependencies": dependencies, "plugins": plugins,
        "claim_limit": "Candidate source/ELF snapshot only. Bind its file SHA in independent review before use; no successful shutdown or flight is asserted."}
    registration["registration_digest"] = registration_digest(registration)
    return registration


def _stable_file_fields(item):
    return {key: item[key] for key in ("path", "real_path", "bytes", "sha256")}


def _validate_structure(value, backend):
    if (not isinstance(value, dict) or value.get("schema_version") != SCHEMA or value.get("kind") != KIND
            or value.get("status") != "CANDIDATE_REQUIRES_INDEPENDENT_REVIEW"
            or value.get("registration_digest") != registration_digest(value)):
        raise RuntimeRegistrationError("Registration schema/kind/status/digest is invalid")
    if type(value.get("fixture_only")) is not bool or value["fixture_only"] != bool(backend.fixture_only):
        raise RuntimeRegistrationError("Fixture evidence cannot verify a production runtime")
    expected_scope = "ORCHESTRATION_FIXTURE_ONLY" if backend.fixture_only else "LINUX_ROS_GZ_SOURCE_AND_ELF"
    if value.get("evidence_scope") != expected_scope:
        raise RuntimeRegistrationError("Registration evidence scope is inconsistent")


def verify_registration(value, *, patch_path=None, backend=None):
    backend = _backend(backend)
    _validate_structure(value, backend)
    observed = create_registration(value["overlay_root"], value["source"]["repo_root"],
        patch_path=patch_path if patch_path is not None else (value.get("patch") or {}).get("path"),
        expected_commit=value["source"]["commit"],
        plugin_elf_paths=[row["path"] for row in value.get("plugins", [])], backend=backend)
    if observed["source"] != value["source"]:
        raise RuntimeRegistrationError("Registered source commit/diff/index/submodules changed")
    for key in ("executable", "patch"):
        original, current = value.get(key), observed.get(key)
        compare = _stable_file_fields if key == "executable" else lambda item: {field: item[field] for field in ("sha256", "bytes")}
        if (original is None) != (current is None) or (original is not None and compare(original) != compare(current)):
            raise RuntimeRegistrationError("Registered file changed: " + key)
    recorded = [{"soname": row["soname"], **_stable_file_fields(row)} for row in value["dependencies"]]
    current = [{"soname": row["soname"], **_stable_file_fields(row)} for row in observed["dependencies"]]
    if recorded != current:
        raise RuntimeRegistrationError("Registered dependency paths or ELF bytes changed")
    if ([_stable_file_fields(row) for row in value.get("plugins", [])]
            != [_stable_file_fields(row) for row in observed["plugins"]]):
        raise RuntimeRegistrationError("Registered plugin paths or ELF bytes changed")
    return {"status": "PASS", "scope": "CURRENT_SOURCE_AND_ELF_MATCH_REGISTERED_CANDIDATE",
            "fixture_only": bool(backend.fixture_only), "registration_digest": value["registration_digest"],
            "checked_dependency_count": len(recorded),
            "checked_plugin_count": len(observed["plugins"]),
            "patch_verified_path": (observed.get("patch") or {}).get("real_path")}


def parse_process_stat(text, pid):
    closing = text.rfind(")")
    opening = text.find("(")
    if opening < 1 or closing < opening or text[:opening].strip() != str(pid):
        raise RuntimeRegistrationError("Malformed or wrong-PID proc stat")
    fields = text[closing + 1:].split()
    if len(fields) < 20 or fields[0] in {"Z", "X"}:
        raise RuntimeRegistrationError("Proc identity is truncated or no longer alive")
    try:
        return {"pid": pid, "parent_pid": int(fields[1]), "process_group": int(fields[2]),
                "session": int(fields[3]), "start_ticks": int(fields[19])}
    except ValueError as error:
        raise RuntimeRegistrationError("Invalid proc identity integers") from error


def parse_maps(text):
    result = []
    for line in text.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 5:
            raise RuntimeRegistrationError("Malformed proc maps row")
        if len(parts) != 6 or parts[4] == "0" or parts[5].startswith("["):
            continue
        path = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), parts[5])
        try:
            major, minor = (int(value, 16) for value in parts[3].split(":"))
            inode = int(parts[4])
        except ValueError as error:
            raise RuntimeRegistrationError("Malformed mapping device/inode") from error
        result.append({"path": path, "deleted": path.endswith(" (deleted)"),
                       "device_major": major, "device_minor": minor, "inode": inode})
    return result


def verify_live_process(value, pid, *, expected_start_ticks=None, patch_path=None, backend=None):
    backend = _backend(backend)
    current = verify_registration(value, patch_path=patch_path, backend=backend)
    if type(pid) is not int or pid <= 0:
        raise RuntimeRegistrationError("A positive explicit bridge PID is required")
    before = parse_process_stat(backend.proc_text(pid, "stat"), pid)
    if expected_start_ticks is not None and (type(expected_start_ticks) is not int
                                            or before["start_ticks"] != expected_start_ticks):
        raise RuntimeRegistrationError("Bridge PID creation identity differs from launch receipt")
    exe_path = backend.exe_path(pid)
    if exe_path.endswith(" (deleted)"):
        raise RuntimeRegistrationError("Live bridge executable is deleted")
    if str(Path(exe_path).resolve(strict=True)) != value["executable"]["real_path"]:
        raise RuntimeRegistrationError("Live PID is not the registered overlay parameter_bridge")
    executable = _regular_file(backend.exe_file(pid), elf=True)
    if executable["sha256"] != value["executable"]["sha256"]:
        raise RuntimeRegistrationError("Live executable ELF differs from registration")
    expected = {}
    for row in [value["executable"], *value["dependencies"], *value.get("plugins", [])]:
        if row["real_path"] in expected and row["sha256"] != expected[row["real_path"]]["sha256"]:
            raise RuntimeRegistrationError("Registered ELF aliases have conflicting hashes")
        expected[row["real_path"]] = row
    checked = {}
    maps = parse_maps(backend.proc_text(pid, "maps"))
    for mapping in maps:
        path = mapping["path"][:-10] if mapping["deleted"] else mapping["path"]
        basename = Path(path).name
        ros_gz = basename == "parameter_bridge" or basename.startswith("libros_gz_")
        if mapping["deleted"] and (ros_gz or path in expected):
            raise RuntimeRegistrationError("Registered or ros_gz mapped ELF is deleted")
        namespace = backend.namespace_file(pid, path)
        try:
            canonical = str(namespace.resolve(strict=True))
        except OSError:
            if ros_gz or path in expected:
                raise RuntimeRegistrationError("Registered or ros_gz mapping is unreadable: " + path)
            continue
        # Namespace paths contain /proc/PID/root; their resolved file is the
        # actual mapped namespace file, never an assumed host-side soname.
        if ros_gz and canonical not in expected:
            raise RuntimeRegistrationError("Unregistered/old ros_gz ELF mapped in bridge PID: " + path)
        if canonical not in expected:
            continue
        if canonical in checked:
            if any(checked[canonical][key] != mapping[key] for key in ("device_major", "device_minor", "inode")):
                raise RuntimeRegistrationError("Mapping identity changed within proc maps")
            continue
        actual = _regular_file(namespace, elf=True)
        if any(actual[key] != mapping[key] for key in ("device_major", "device_minor", "inode")):
            raise RuntimeRegistrationError("Mapped ELF device/inode differs from current namespace file")
        if actual["sha256"] != expected[canonical]["sha256"]:
            raise RuntimeRegistrationError("Actual mapped ELF bytes differ from registration")
        checked[canonical] = {**mapping, "sha256": actual["sha256"], "bytes": actual["bytes"]}
    missing = sorted(set(expected) - set(checked))
    if missing:
        raise RuntimeRegistrationError("Registered ELF dependencies are missing from live maps: " + ", ".join(missing))
    if parse_process_stat(backend.proc_text(pid, "stat"), pid) != before:
        raise RuntimeRegistrationError("Bridge PID identity changed during verification")
    if backend.exe_path(pid) != exe_path:
        raise RuntimeRegistrationError("Bridge executable changed during verification")
    return {**current, "scope": "LIVE_PID_EXE_AND_MAPS_MATCH_REGISTERED_ROS_GZ_RUNTIME",
            "checked_utc": datetime.now(timezone.utc).isoformat(), "process": before,
            "mapped_elf_count": len(checked), "mapped_elfs": [checked[key] for key in sorted(checked)],
            "claim_limit": "This explicit PID matched during the check. Caller must establish ownership; successful shutdown, continuous health and flight acceptance are separate."}
