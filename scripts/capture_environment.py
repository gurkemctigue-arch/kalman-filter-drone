"""Capture a read-only Linux environment manifest for a stage-one trial.

Source ROS and the two workspaces first. This script records versions, source
commits, package inventories, model/config hashes and APT signature evidence.
It does not install/upgrade packages, contact a ROS graph, or change GPU/ROS
environment variables. Only the requested JSON output is written.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any


ENVIRONMENT_ALLOWLIST = (
    "ROS_DISTRO", "ROS_VERSION", "ROS_PYTHON_VERSION", "RMW_IMPLEMENTATION", "ROS_DOMAIN_ID",
    "ROS_LOCALHOST_ONLY", "AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH", "GZ_PARTITION", "GZ_IP",
    "GZ_SIM_RESOURCE_PATH", "GZ_SIM_SYSTEM_PLUGIN_PATH", "DISPLAY", "WAYLAND_DISPLAY",
    "LIBGL_ALWAYS_SOFTWARE", "MESA_LOADER_DRIVER_OVERRIDE", "GALLIUM_DRIVER",
    "MESA_D3D12_DEFAULT_ADAPTER_NAME", "STAGE1_AUTO_START", "STAGE1_TAKEOFF_HEIGHT_M",
)
ROS_FINGERPRINT = "C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654"


def command(args: list[str], timeout: float = 15.0) -> dict[str, Any]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return {"argv": args, "returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": args, "returncode": None, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_info(path: Path, include_content: bool = False) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    result = {"path": str(path), "exists": True, "bytes": path.stat().st_size, "sha256": sha256(path)}
    if include_content:
        # Repository credentials, if present, are not part of this manifest.
        text = path.read_text(encoding="utf-8", errors="replace")
        result["content"] = re.sub(r"(https?://)[^/\s@]+@", r"\1<redacted>@", text)
    return result


def git_info(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        return {"path": str(path), "repository_found": False}
    return {
        "path": str(path), "repository_found": True,
        "commit": command(["git", "-C", str(path), "rev-parse", "HEAD"]),
        "describe": command(["git", "-C", str(path), "describe", "--tags", "--always", "--dirty"]),
        "branch": command(["git", "-C", str(path), "branch", "--show-current"]),
        "status": command(["git", "-C", str(path), "status", "--porcelain"]),
        "submodules": command(["git", "-C", str(path), "submodule", "status", "--recursive"], timeout=25),
    }


def python_packages() -> dict[str, str]:
    return dict(sorted((distribution.metadata.get("Name", "unknown"), distribution.version)
                       for distribution in importlib.metadata.distributions()))


def key_details(path: Path) -> dict[str, Any]:
    result = command(["gpg", "--batch", "--no-options", "--show-keys", "--with-colons", str(path)])
    fields = [line.split(":") for line in result["stdout"].splitlines()]
    fingerprints = [row[9] for row in fields if row[0] == "fpr" and len(row) > 9]
    public = next((row for row in fields if row[0] == "pub" and len(row) > 6), None)
    expires = int(public[6]) if public is not None and public[6].isdigit() else None
    return {
        **file_info(path), "inspection": result, "fingerprints": fingerprints,
        "primary_fingerprint_matches_ros": bool(fingerprints and fingerprints[0] == ROS_FINGERPRINT),
        "expires_utc": datetime.fromtimestamp(expires, timezone.utc).isoformat() if expires else None,
        "unexpired": bool(expires is not None and expires > datetime.now(timezone.utc).timestamp()),
    }


def apt_info() -> dict[str, Any]:
    files = [Path("/etc/apt/sources.list")]
    directory = Path("/etc/apt/sources.list.d")
    if directory.is_dir():
        files.extend(path for path in sorted(directory.iterdir()) if path.suffix in {".list", ".sources"})
    sources = [file_info(path, include_content=True) for path in files if path.is_file()]
    active_ros = []
    for source in sources:
        active_text = "\n".join(line for line in source["content"].splitlines() if not line.lstrip().startswith("#"))
        if "packages.ros.org/ros2/ubuntu" not in active_text:
            continue
        active_ros.append({
            "path": source["path"],
            "trusted_bypass": bool(re.search(r"trusted\s*(?:=|:)\s*(?:yes|true|1)", active_text, re.I)),
            "signed_by_configured": bool(re.search(r"signed-by\s*(?:=|:)\s*\S+", active_text, re.I)),
        })
    keyring = Path("/usr/share/keyrings/ros-archive-keyring.gpg")
    key = key_details(keyring)
    releases = sorted(Path("/var/lib/apt/lists").glob("*packages.ros.org*ros2*InRelease"))
    verification = [{"inrelease": file_info(path),
                     "gpgv": command(["gpgv", "--status-fd", "1", "--keyring", str(keyring), str(path)])}
                    for path in releases]
    # Capture only relevant boolean options, never proxy URLs/credentials.
    configuration = command(["apt-config", "dump"])
    insecure_options = [line for line in configuration["stdout"].splitlines()
                        if any(name in line.lower() for name in ("allowinsecure", "allowunauthenticated", "allowdowngradetoinsecure"))]
    unsafe_global_option = any(re.search(r'"(?:true|yes|1)"', line, re.I) for line in insecure_options)
    verified = bool(verification and all(row["gpgv"]["returncode"] == 0 and "[GNUPG:] VALIDSIG " + ROS_FINGERPRINT in row["gpgv"]["stdout"] for row in verification))
    return {
        "sources": sources, "active_ros_sources": active_ros, "ros_keyring": key,
        "cached_ros_inrelease_verification": verification, "insecure_option_lines": insecure_options,
        "ros_signature_verification_ready": bool(active_ros and all(not row["trusted_bypass"] and row["signed_by_configured"] for row in active_ros)
                                                 and not unsafe_global_option and key["primary_fingerprint_matches_ros"] and key["unexpired"] and verified),
        "note": "Verifies cached signed repository metadata. This capture does not apt update, install or upgrade anything.",
    }


def project_files(root: Path) -> list[dict[str, Any]]:
    paths: set[Path] = set()
    for base in (root / "uav_tracking", root / "scripts", root / "config", root / "launch", root / "ros2_ws" / "src"):
        if base.is_dir():
            paths.update(path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in {
                ".py", ".sh", ".yaml", ".yml", ".sdf", ".config", ".xml", ".msg",
                ".dae", ".obj", ".mtl", ".stl", ".png", ".jpg", ".jpeg",
            })
    if (root / "models").is_dir():
        paths.update(path for path in (root / "models").rglob("*") if path.is_file()
                     and path.suffix.lower() in {".pt", ".onnx", ".xml", ".bin", ".yaml", ".json"})
    return [{**file_info(path), "relative_path": path.relative_to(root).as_posix()} for path in sorted(paths)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Default: PROJECT/results/environment_manifest.json")
    parser.add_argument("--px4-root", type=Path, default=Path("/root/PX4-Autopilot"))
    parser.add_argument("--px4-msgs-root", type=Path, default=Path("/root/px4_msgs_ws/src/px4_msgs"))
    parser.add_argument("--agent-root", type=Path, default=Path("/root/Micro-XRCE-DDS-Agent"))
    parser.add_argument("--skip-gl-probe", action="store_true", help="Skip glxinfo -B while retaining GPU device/env evidence")
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("Run inside the actual Linux/WSL ROS environment")
    root = args.project_root.resolve()
    output = args.output or root / "results" / "environment_manifest.json"
    now = datetime.now(timezone.utc).isoformat()
    agents = Path(shutil.which("MicroXRCEAgent") or "/usr/local/bin/MicroXRCEAgent")
    agent_dependencies = command(["ldd", str(agents)])
    local_libraries = sorted(set(re.findall(r"=>\s+(/usr/local/\S+)", agent_dependencies["stdout"])))
    package_query = command(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${db:Status-Status}\n"])
    packages = []
    for line in package_query["stdout"].splitlines():
        fields = line.split("\t")
        if len(fields) == 3 and fields[2] == "installed":
            packages.append({"name": fields[0], "version": fields[1]})
    vendor_packages = [row for row in packages if row["name"].startswith(("ros-jazzy-", "libgz-", "gz-"))]
    manifest = {
        "schema_version": 1, "captured_at_utc": now, "project_root": str(root), "capture_script": file_info(Path(__file__).resolve()),
        "capture_is_read_only": True,
        "host": {"os_release": file_info(Path("/etc/os-release"), include_content=True),
                 "uname": command(["uname", "-a"]), "lscpu": command(["lscpu", "-J"]),
                 "memory_kib": {key.rstrip(":"): int(value.split()[0]) for key, value in
                                (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
                                if key in {"MemTotal", "SwapTotal"}}},
        "python": {"executable": sys.executable, "version": platform.python_version(), "packages": python_packages()},
        "ros_gazebo": {"ros_distro": os.environ.get("ROS_DISTRO"), "gz_sim_version": command(["gz", "sim", "--version"]),
                       "installed_ros_gz_packages": vendor_packages,
                       "graph_probe_note": "No ROS graph discovery/daemon/doctor command was run"},
        "repositories": {"project": git_info(root), "px4": git_info(args.px4_root),
                         "px4_msgs": git_info(args.px4_msgs_root), "micro_xrce_dds_agent": git_info(args.agent_root)},
        "binaries": {"px4": file_info(args.px4_root / "build/px4_sitl_default/bin/px4"), "agent": file_info(agents),
                     "agent_ldd": agent_dependencies, "agent_local_libraries": [file_info(Path(path)) for path in local_libraries]},
        "gpu": {"dxg_present": Path("/dev/dxg").exists(),
                "dri_devices": sorted(str(path) for path in Path("/dev/dri").glob("*")) if Path("/dev/dri").is_dir() else [],
                "glxinfo": {"skipped": True} if args.skip_gl_probe else command(["glxinfo", "-B"], timeout=10),
                "nvidia_smi": command(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], timeout=5),
                "note": "Probe uses this shell's existing environment without overrides; it does not assert the renderer used by another running Gazebo process"},
        "environment_allowlist": {name: os.environ[name] for name in ENVIRONMENT_ALLOWLIST if name in os.environ},
        "apt": apt_info(), "installed_debian_packages": packages, "project_asset_hashes": project_files(root),
        "limitations": ["A manifest records installed state; it is not a claim that every end-to-end acceptance test passed.",
                        "Host Windows GPU model/driver may be documented separately; WSL /dev/dxg and current-shell GL probes have different semantics.",
                        "No credentials, full environment dump, repository remotes, or proxy configuration are collected."],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), "captured_at_utc": now,
                      "python": manifest["python"]["version"], "ros_distro": manifest["ros_gazebo"]["ros_distro"],
                      "debian_package_count": len(packages), "asset_hash_count": len(manifest["project_asset_hashes"]),
                      "ros_signature_verification_ready": manifest["apt"]["ros_signature_verification_ready"]}, indent=2))


if __name__ == "__main__":
    main()
