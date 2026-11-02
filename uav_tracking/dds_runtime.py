"""Pinned Humble DDS files, environment and explicit live-process mappings.

This contract covers the production TF, bridge and Agent independently. It
does not infer one process's middleware from another, or certify flight or
shutdown success. Only generic proc parsing is shared with ros_gz runtime.
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

from uav_tracking.ros_gz_runtime import RuntimeBackend, parse_maps, parse_process_stat


SCOPE = "HUMBLE_FASTDDS_LISTENER_LIFECYCLE_A01"
PREFIX = "/root/uav_humble22/fastdds_listener_A01/install"
AGENT_LIB = "/root/uav_humble22/agent_install/lib"
SYSTEM_LIB = "/opt/ros/humble/lib"
MAX_CONFIG_BYTES = 1024 * 1024
MAX_ELF_BYTES = 512 * 1024 * 1024
PATCH_SHA256 = "a1de559704415dd11045cc30b7b51720c2740bcf4baf23f44fd4da382f17bddc"
ARCHIVE_SHA256 = "34384c79ad4902d5555a811956596b83c7da190bfa6142f2f09044f10cd2becb"
ROLE_KEYS = {
    "flight_tf": {"dds": "flight_tf_fastdds", "cdr": "flight_tf_fastcdr",
                  "rmw_cpp": "rmw_fastrtps_cpp", "rmw_shared": "rmw_fastrtps_shared_cpp"},
    "bridge": {"dds": "flight_tf_fastdds", "cdr": "flight_tf_fastcdr",
               "rmw_cpp": "rmw_fastrtps_cpp", "rmw_shared": "rmw_fastrtps_shared_cpp"},
    "agent": {"dds": "agent_fastdds", "cdr": "agent_fastcdr"},
}
ELF_KEYS = {key for roles in ROLE_KEYS.values() for key in roles.values()}


class DdsRuntimeError(ValueError):
    pass


class MappingsNotReadyError(DdsRuntimeError):
    """No conflicting mapping was found, but expected startup ELFs are absent."""


def _backend(value):
    value = value or RuntimeBackend()
    if platform.system() != "Linux" and not value.fixture_only:
        raise DdsRuntimeError("Production DDS runtime verification requires Linux")
    return value


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_json(path):
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise DdsRuntimeError("DDS JSON file exceeded size bound")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as error:
        raise DdsRuntimeError("Invalid DDS JSON file") from error
    if not isinstance(value, dict):
        raise DdsRuntimeError("DDS registration must be an object")
    return value, raw


def load_registration(path):
    return _read_json(path)[0]


def _path(value):
    if not isinstance(value, str) or not value or any(c in value for c in ("\0", "\n", "\r")):
        raise DdsRuntimeError("File paths must be nonempty single-line strings")
    path = Path(value)
    if not path.is_absolute():
        raise DdsRuntimeError("DDS file and directory paths must be absolute")
    return path


def library_family(path):
    """Match actual ELF basenames; ROS typesupport names are not DDS ELFs."""
    name = Path(path).name
    for family, pattern in (
        ("dds", r"lib(?:fastrtps|fastdds)\.so(?:\.[0-9]+)*"),
        ("cdr", r"libfastcdr\.so(?:\.[0-9]+)*"),
        ("rmw_cpp", r"librmw_fastrtps_cpp\.so(?:\.[0-9]+)*"),
        ("rmw_shared", r"librmw_fastrtps_shared_cpp\.so(?:\.[0-9]+)*"),
    ):
        if re.fullmatch(pattern, name):
            return family
    if ("__" not in name and not re.fullmatch(r"librmw_(?:implementation|dds_common)\.so(?:\.[0-9]+)*", name)
            and re.fullmatch(r"librmw_[a-zA-Z0-9_]+\.so(?:\.[0-9]+)*", name)):
        return "rmw_other"
    return None


def _structure(value, backend):
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1 or value.get("scope") != SCOPE
            or value.get("rmw_implementation") != "rmw_fastrtps_cpp"):
        raise DdsRuntimeError("DDS registration schema, scope or RMW differs")
    prefix, agent = _path(value.get("prefix")), _path(value.get("agent_library_directory"))
    if not backend.fixture_only and (str(prefix) != PREFIX or str(agent) != AGENT_LIB):
        raise DdsRuntimeError("DDS registration must use the reviewed isolated prefixes")
    if not isinstance(value.get("elf_files"), dict) or set(value["elf_files"]) != ELF_KEYS:
        raise DdsRuntimeError("DDS registration must lock exactly the six role-specific ELFs")
    descriptors = {"build_inputs": value.get("build_inputs"), **value["elf_files"]}
    for key, item in descriptors.items():
        if (not isinstance(item, dict) or set(item) != {"path", "realpath", "sha256", "bytes"}
                or type(item["bytes"]) is not int or not 0 < item["bytes"] <= MAX_ELF_BYTES
                or not isinstance(item["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])):
            raise DdsRuntimeError("Invalid pinned file descriptor: " + key)
        requested, canonical = _path(item["path"]), _path(item["realpath"])
        if key == "build_inputs":
            if canonical != prefix.parent / "build_inputs.json":
                raise DdsRuntimeError("Build receipt is outside the isolated dependency root")
            continue
        family = next(family for roles in ROLE_KEYS.values() for family, name in roles.items() if name == key)
        if library_family(requested) != family or library_family(canonical) != family:
            raise DdsRuntimeError("Pinned filename has the wrong ELF role: " + key)
        directory = prefix / "lib" if key == "flight_tf_fastdds" else agent if key.startswith("agent_") else Path(SYSTEM_LIB)
        if (key == "flight_tf_fastdds" or key.startswith("agent_") or not backend.fixture_only):
            if not canonical.is_relative_to(directory) or canonical == directory:
                raise DdsRuntimeError("Pinned ELF resolves outside its role's prefix: " + key)
    for role, roles in ROLE_KEYS.items():
        if len({value["elf_files"][key]["realpath"] for key in roles.values()}) != len(roles):
            raise DdsRuntimeError("Different ELF roles cannot share a canonical file: " + role)


def _file_record(path, *, elf):
    requested = _path(str(path))
    resolved = requested.resolve(strict=True)
    with resolved.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_ELF_BYTES:
            raise DdsRuntimeError("Expected a bounded regular DDS file: " + str(requested))
        if elf and stream.read(4) != b"\x7fELF":
            raise DdsRuntimeError("Pinned library is not ELF: " + str(requested))
        stream.seek(0)
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
    # Windows exposes creation/ctime through different native stat paths;
    # use the same stable identity fields as the existing proc/file helper.
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if (identity(before) != identity(after) or identity(after) != identity(resolved.stat())
            or requested.resolve(strict=True) != resolved):
        raise DdsRuntimeError("Pinned file changed during verification: " + str(requested))
    return {"path": str(requested), "realpath": str(resolved), "bytes": before.st_size,
            "sha256": digest.hexdigest(), "inode": before.st_ino,
            "device_major": os.major(before.st_dev) if os.name != "nt" else 0,
            "device_minor": os.minor(before.st_dev) if os.name != "nt" else before.st_dev}


def _verify_file(item, *, elf=True):
    actual = _file_record(item["path"], elf=elf)
    if any(actual[key] != item[key] for key in ("path", "realpath", "sha256", "bytes")):
        raise DdsRuntimeError("Pinned DDS file differs: " + item["path"])
    return actual


def _ld_parts(value):
    if not isinstance(value, str) or any(c in value for c in ("\0", "\n", "\r")):
        raise DdsRuntimeError("LD_LIBRARY_PATH must be a single-line string")
    if not value:
        return []
    parts = value.split(":" if os.name != "nt" else ";")
    # Fixtures use the native separator; production always uses Linux ':'.
    if any(not part or not Path(part).is_absolute() for part in parts):
        raise DdsRuntimeError("LD_LIBRARY_PATH contains an empty or relative component")
    return [os.path.normpath(part) for part in parts]


def verify_registration(value, *, backend=None, environ=None, check_environment=True):
    backend = _backend(backend)
    _structure(value, backend)
    files = {key: _verify_file(item) for key, item in value["elf_files"].items()}
    receipt = _verify_file(value["build_inputs"], elf=False)
    build, receipt_raw = _read_json(value["build_inputs"]["path"])
    if _sha(receipt_raw) != receipt["sha256"] or len(receipt_raw) != receipt["bytes"]:
        raise DdsRuntimeError("Build receipt changed during verification")
    inputs = build.get("files", {})
    if (build.get("scope") != "ISOLATED_DEPENDENCY_BUILD_NOT_RUNTIME_ACCEPTANCE"
            or not isinstance(inputs, dict) or not isinstance(inputs.get("patch"), dict)
            or not isinstance(inputs.get("source_archive"), dict)
            or inputs.get("patch", {}).get("sha256") != PATCH_SHA256
            or inputs.get("source_archive", {}).get("sha256") != ARCHIVE_SHA256):
        raise DdsRuntimeError("Build receipt does not identify the reviewed A01 source/patch")
    observed_environment = None
    if check_environment:
        env = os.environ if environ is None else environ
        distros = {env[name] for name in ("ROS_DISTRO", "STAGE1_ROS_DISTRO") if env.get(name)}
        if distros != {"humble"} or env.get("RMW_IMPLEMENTATION") != "rmw_fastrtps_cpp":
            raise DdsRuntimeError("DDS runtime requires the explicit Humble/FastDDS environment")
        parts = _ld_parts(env.get("LD_LIBRARY_PATH", ""))
        expected = [os.path.normpath(value["agent_library_directory"]), os.path.normpath(str(Path(value["prefix"]) / "lib"))]
        if parts[:2] != expected or len(parts) != len(set(parts)):
            raise DdsRuntimeError("LD_LIBRARY_PATH must put Agent first and isolated DDS second without duplicates")
        observed_environment = {"RMW_IMPLEMENTATION": env["RMW_IMPLEMENTATION"],
                                "LD_LIBRARY_PATH": env["LD_LIBRARY_PATH"], "ros_distros": sorted(distros)}
    return {"schema_version": 1, "scope": SCOPE, "status": "PASS", "fixture_only": bool(backend.fixture_only),
            "checked_utc": datetime.now(timezone.utc).isoformat(), "elf_files": files,
            "build_inputs": receipt, "environment": observed_environment,
            "claim_limit": "Pinned dependency/environment contract only; live processes and flight remain separately verified."}


def preflight(config_path, *, environ=None, backend=None):
    value, raw = _read_json(config_path)
    report = verify_registration(value, environ=environ, backend=backend)
    if Path(config_path).read_bytes() != raw:
        raise DdsRuntimeError("DDS registration changed during preflight")
    return {**report, "registration_path": str(Path(config_path).resolve()), "registration_sha256": _sha(raw)}


def environment(config_path, *, current_library_path=None, environ=None, backend=None):
    value = load_registration(config_path)
    verify_registration(value, backend=backend, check_environment=False)
    env = os.environ if environ is None else environ
    current = env.get("LD_LIBRARY_PATH", "") if current_library_path is None else current_library_path
    desired = [os.path.normpath(value["agent_library_directory"]), os.path.normpath(str(Path(value["prefix"]) / "lib"))]
    for part in _ld_parts(current):
        if part not in desired:
            desired.append(part)
    return (":" if os.name != "nt" else ";").join(desired)


def revalidate_files(config_path, *, expected_config_sha256, backend=None):
    value, raw = _read_json(config_path)
    if _sha(raw) != expected_config_sha256:
        raise DdsRuntimeError("DDS registration changed during trial")
    report = verify_registration(value, backend=backend, check_environment=False)
    if Path(config_path).read_bytes() != raw:
        raise DdsRuntimeError("DDS registration changed during file revalidation")
    return {**report, "registration_sha256": expected_config_sha256}


def verify_loaded_process(config_path, pid, *, role, expected_process, backend=None,
                          expected_config_sha256=None):
    backend = _backend(backend)
    value, raw = _read_json(config_path)
    _structure(value, backend)
    if expected_config_sha256 is not None and _sha(raw) != expected_config_sha256:
        raise DdsRuntimeError("DDS registration changed before live capture")
    if role not in ROLE_KEYS:
        raise DdsRuntimeError("DDS process role must be flight_tf, bridge or agent")
    before = parse_process_stat(backend.proc_text(pid, "stat"), pid)
    if not isinstance(expected_process, dict) or before != expected_process:
        raise DdsRuntimeError("Owned DDS process creation/parent identity changed")
    executable = backend.exe_path(pid)
    if executable.endswith(" (deleted)"):
        raise DdsRuntimeError("Owned DDS executable is deleted")
    expected = {family: value["elf_files"][key] for family, key in ROLE_KEYS[role].items()}

    def relevant_maps():
        result = []
        for mapping in parse_maps(backend.proc_text(pid, "maps")):
            path = mapping["path"].removesuffix(" (deleted)")
            family = library_family(path)
            if family is None:
                continue
            if family not in expected or mapping["deleted"]:
                raise DdsRuntimeError("Unexpected or deleted DDS/CDR/RMW mapping: " + mapping["path"])
            canonical = str(backend.namespace_file(pid, path).resolve(strict=True))
            if canonical != expected[family]["realpath"]:
                raise DdsRuntimeError("Old, mixed-version or unregistered middleware mapping: " + path)
            result.append({**mapping, "family": family, "realpath": canonical})
        missing = set(expected) - {row["family"] for row in result}
        if missing:
            raise MappingsNotReadyError("Expected middleware mappings are not ready: " + ", ".join(sorted(missing)))
        return result

    mappings = relevant_maps()
    checked = {}
    for mapping in mappings:
        family = mapping["family"]
        if family not in checked:
            actual = _file_record(backend.namespace_file(pid, mapping["path"]), elf=True)
            if any(actual[key] != expected[family][key] for key in ("realpath", "sha256", "bytes")):
                raise DdsRuntimeError("Actual mapped middleware bytes differ from registration")
            checked[family] = actual
        if any(checked[family][key] != mapping[key] for key in ("inode", "device_major", "device_minor")):
            raise DdsRuntimeError("Mapped middleware device/inode differs from namespace file")
    if (parse_process_stat(backend.proc_text(pid, "stat"), pid) != before
            or backend.exe_path(pid) != executable or relevant_maps() != mappings
            or Path(config_path).read_bytes() != raw):
        raise DdsRuntimeError("Owned DDS process or mappings changed during live capture")
    return {"schema_version": 1, "scope": SCOPE, "status": "PASS", "role": role,
            "fixture_only": bool(backend.fixture_only), "checked_utc": datetime.now(timezone.utc).isoformat(),
            "registration_sha256": _sha(raw), "process": before, "executable": executable,
            "mapped_elfs": checked, "mappings": mappings,
            "claim_limit": "This explicit PID matched at capture. Caller establishes ownership; other processes, future mappings and shutdown are separate."}
