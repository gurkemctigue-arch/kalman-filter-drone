"""Capture an owned Gazebo's actual rendering ELF and explicit CPU contract."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import time

CPU_ENVIRONMENT = {"LIBGL_ALWAYS_SOFTWARE":"1", "MESA_LOADER_DRIVER_OVERRIDE":"swrast", "GALLIUM_DRIVER":"llvmpipe"}
RENDER_ENVIRONMENT_KEYS = (*CPU_ENVIRONMENT, "LP_NUM_THREADS", "OMP_NUM_THREADS", "DISPLAY", "EGL_PLATFORM")
RENDER_LIBRARY_MARKERS = ("/dri/", "mesa", "ogre", "libegl", "libglx", "libgz-rendering", "d3d12", "dxcore", "libllvm", "libglapi")


def rendering_contract_issues(expected_driver, environment, library_paths):
    """Actual libraries and environment must agree; auto retains its old meaning."""
    if expected_driver not in {"auto", "llvmpipe"}:
        return ["unknown_requested_gazebo_render_driver"]
    paths = [str(path).lower() for path in library_paths]
    if not paths:
        return ["rendering_libraries_not_initialized"]
    if expected_driver == "auto":
        return [] if any("/dri/" in path or "libd3d12" in path for path in paths) else ["rendering_libraries_not_initialized"]
    issues = ["wrong_gazebo_environment:" + key for key, value in CPU_ENVIRONMENT.items()
              if environment.get(key) != value]
    if not any(Path(path).name == "swrast_dri.so" for path in paths):
        issues.append("missing_actual_swrast_dri")
    if not any("libllvm" in Path(path).name for path in paths):
        issues.append("missing_actual_llvm")
    if any("libd3d12" in Path(path).name or "/usr/lib/wsl/drivers/" in path for path in paths):
        issues.append("unexpected_actual_wsl_d3d12_driver")
    return issues


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def capture(pid, expected_driver, *, proc_root=Path("/proc")):
    if type(pid) is not int or pid <= 0:
        raise ValueError("An explicit owned positive Gazebo PID is required")
    process = Path(proc_root) / str(pid)
    raw_environment = (process / "environ").read_bytes().split(b"\0")
    environment = {}
    for field in raw_environment:
        key, separator, value = field.partition(b"=")
        name = key.decode(errors="replace")
        if separator and name in RENDER_ENVIRONMENT_KEYS:
            environment[name] = value.decode(errors="replace")
    mappings = [line for line in (process / "maps").read_text().splitlines()
                if len(line.split(maxsplit=5)) == 6
                and any(marker in line.lower() for marker in RENDER_LIBRARY_MARKERS)]
    libraries, provenance_issues = {}, []
    for line in mappings:
        fields = line.split(maxsplit=5)
        name = fields[5]
        if name in libraries:
            continue
        path = Path(name)
        try:
            stat = path.stat()
            device = tuple(int(part, 16) for part in fields[3].split(":"))
            if (stat.st_ino != int(fields[4])
                    or (os.major(stat.st_dev), os.minor(stat.st_dev)) != device):
                raise ValueError("mapped ELF inode/device does not match current path")
            libraries[name] = {"sha256":_sha256(path), "inode":stat.st_ino,
                               "device_major":device[0], "device_minor":device[1]}
        except (OSError, ValueError) as error:
            provenance_issues.append("rendering_elf_unverifiable:" + name + ":" + str(error))
    issues = rendering_contract_issues(expected_driver, environment, libraries) + provenance_issues
    return {"schema_version":1, "status":"FAIL" if issues else "PASS", "owned_pid":pid,
        "expected_driver":expected_driver, "actual_process_environment":environment,
        "actual_mappings":mappings, "actual_libraries":libraries, "contract_issues":issues,
        "evidence_scope":"actual Gazebo process ELF mapping and selected environment; renderer performance is measured separately"}


def capture_ready(pid, expected_driver, timeout_s=15.):
    """Call after unpause; initialized camera rendering is needed for evidence."""
    deadline = time.monotonic() + timeout_s
    attempts = 0
    while True:
        attempts += 1
        result = capture(pid, expected_driver)
        result["attempts"] = attempts
        waiting = {"rendering_libraries_not_initialized", "missing_actual_swrast_dri", "missing_actual_llvm"}
        if result["status"] == "PASS" or not set(result["contract_issues"]).issubset(waiting) or time.monotonic() >= deadline:
            return result
        time.sleep(.2)
