#!/usr/bin/env python3
"""Prepare an isolated, pinned PX4 magnetic-frame compatibility experiment.

Nothing is applied by ``plan``. ``prepare`` fetches only Git/source content
into a new checkout, never copies the original build or changes that checkout.
Compilation is deliberately separate. ``verify-runtime`` checks the resulting
source, dependency commits, ELF marker and optional actual startup log.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
CONTRACT = "gazebo_enu_flu_to_frd_v1"
MARKER = "magnetic frame contract: " + CONTRACT
PINNED_COMMIT = "d6f12ad1c4f70ad3230afd7d86e971421e02fef4"
BRIDGE = Path("src/modules/simulation/gz_bridge/GZBridge.cpp")
ORIGINAL_SHA256 = "8f6f1d7e450e341137be573a51674c6ffc518ef63badbdaa71667d0f462b8dfd"
PATCHED_SHA256 = "7d4ab7c529421865c86d5e463e5ec15eb66f580dbcc6e091ad99704815faa19d"
PATCH = PROJECT / "patches/px4/gazebo_enu_flu_to_frd.patch"
PATCH_SHA256 = "28ed1dd9a46d4470e782e606bf7d2ce3c7b86b905c9b4c67ef486868c184d871"
BINARY = Path("build/px4_sitl_default/bin/px4")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contains_marker(path: Path) -> bool:
    marker, tail = MARKER.encode(), b""
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            combined = tail + block
            if marker in combined:
                return True
            tail = combined[-len(marker):]
    return False


def git(root: Path, *args: str, raw: bool = False) -> str:
    environment = os.environ.copy()
    # Read-only audits must not opportunistically rewrite the original index.
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    output = subprocess.run(["git", "-C", str(root), *args], check=True,
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment).stdout
    return output if raw else output.strip()


def dependency_commits(root: Path) -> dict[str, dict[str, str | bool]]:
    result = {}
    for line in git(root, "submodule", "status", "--recursive").splitlines():
        if not line:
            continue
        # strip() removes the initial ' ' for a clean initialized submodule.
        status = line[0] if line[0] in "-+U" else " "
        content = line[1:] if status != " " else line.lstrip()
        commit, path, *_ = content.split()
        if status in "+U":
            raise ValueError("dependency differs from its pinned gitlink: " + path)
        result[path] = {"commit": commit, "initialized": status != "-"}
    return result


def check_source(root: Path, *, patched: bool) -> dict:
    root = Path(root).resolve()
    if git(root, "rev-parse", "HEAD") != PINNED_COMMIT:
        raise ValueError("PX4 must be at the exact registered commit")
    if sha256(PATCH) != PATCH_SHA256:
        raise ValueError("registered patch bytes changed")
    expected = PATCHED_SHA256 if patched else ORIGINAL_SHA256
    if sha256(root / BRIDGE) != expected:
        raise ValueError("GZBridge source does not match the registered contract")
    changed = set(git(root, "diff", "--name-only", "HEAD", "--ignore-submodules=untracked").splitlines())
    if changed != ({BRIDGE.as_posix()} if patched else set()):
        raise ValueError("unexpected tracked changes in PX4 checkout: " + repr(sorted(changed)))
    if git(root, "diff", "--cached", "--name-only"):
        raise ValueError("unexpected staged PX4 source changes")
    return {"px4_commit": PINNED_COMMIT, "bridge_source_sha256": expected,
            "patch_sha256": PATCH_SHA256, "dependencies": dependency_commits(root),
            "tracked_dirty_paths": sorted(changed)}


def plan(source_root: Path, destination: Path) -> dict:
    source_root, destination = Path(source_root).resolve(), Path(destination).resolve()
    if (source_root == destination or source_root in destination.parents
            or destination in source_root.parents):
        raise ValueError("isolated destination must be outside the original checkout")
    if destination.exists():
        raise ValueError("destination must not already exist; no overwrite or cleanup")
    return {"schema_version": 1, "contract": CONTRACT, "operation": "PLAN_ONLY",
            "original_root": str(source_root), "isolated_root": str(destination),
            "source_evidence": check_source(source_root, patched=False),
            "dependency_policy": "exact recursive gitlinks; never --remote",
            "copy_policy": "shallow Git fetch only; no build/results copy or alternates",
            "build_policy": "separate explicit build in isolated root only"}


def prepare(source_root: Path, destination: Path, initialize_dependencies: bool = False) -> dict:
    evidence = plan(source_root, destination)
    source_root, destination = Path(evidence["original_root"]), Path(evidence["isolated_root"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()  # Exclusive: never reuse a partial or prior checkout.
    git(destination, "init")
    git(destination, "fetch", "--no-tags", "--depth=1", str(source_root), PINNED_COMMIT)
    git(destination, "checkout", "--detach", "FETCH_HEAD")
    git(destination, "apply", "--check", str(PATCH))
    git(destination, "apply", str(PATCH))
    if initialize_dependencies:
        git(destination, "submodule", "update", "--init", "--recursive", "--depth=1")
    target = check_source(destination, patched=True)
    for path, entry in evidence["source_evidence"]["dependencies"].items():
        other = target["dependencies"].get(path)
        if other is not None and other["commit"] != entry["commit"]:
            raise ValueError("isolated dependency commit differs: " + path)
    # A second read ensures the source checkout still has the original bytes.
    check_source(source_root, patched=False)
    return {**evidence, "operation": "PREPARED_SOURCE_NOT_BUILT", "isolated_source_evidence": target,
            "dependencies_initialization_requested": initialize_dependencies,
            "created_at_utc": datetime.now(timezone.utc).isoformat()}


def apply_isolated(original_root: Path, isolated_root: Path, copy_manifest: Path) -> dict:
    """Apply only the registered patch to an independently copied source tree."""
    original_root, isolated_root = Path(original_root).resolve(), Path(isolated_root).resolve()
    if (original_root == isolated_root or original_root in isolated_root.parents
            or isolated_root in original_root.parents):
        raise ValueError("original and isolated PX4 roots must be separate sibling trees")
    copy_manifest = Path(copy_manifest).resolve()
    copied = json.loads(copy_manifest.read_text(encoding="utf-8"))
    expected = {"source": str(original_root), "destination": str(isolated_root),
                "commit": PINNED_COMMIT, "tracked_clean": True, "source_unchanged": True,
                "network_used": False, "file_method": "independent copy2 files; relative symlinks preserved",
                "excluded_source_root_directories": ["build", "install", "log"]}
    for key, value in expected.items():
        if copied.get(key) != value:
            raise ValueError("isolated copy manifest mismatch: " + key)
    for root in (original_root, isolated_root):
        if not (root / ".git").is_dir() or (root / ".git").is_symlink():
            raise ValueError("independent Git directories required")
        if (root / ".git/objects/info/alternates").exists():
            raise ValueError("external Git object alternates are not allowed")
    if os.path.samefile(original_root / BRIDGE, isolated_root / BRIDGE):
        raise ValueError("isolated bridge source must not share an inode/hardlink")
    before_original = check_source(original_root, patched=False)
    before_isolated = check_source(isolated_root, patched=False)
    original_modules = git(original_root, "submodule", "status", "--recursive", raw=True)
    isolated_modules = git(isolated_root, "submodule", "status", "--recursive", raw=True)
    if (original_modules != isolated_modules
            or hashlib.sha256(original_modules.encode()).hexdigest() != copied.get("submodule_status_sha256")
            or original_modules.splitlines() != copied.get("submodule_states")):
        raise ValueError("copy/source recursive dependency evidence differs")
    git(isolated_root, "apply", "--check", str(PATCH))
    git(isolated_root, "apply", str(PATCH))
    after_original = check_source(original_root, patched=False)
    after_isolated = check_source(isolated_root, patched=True)
    if before_original != after_original or before_isolated["dependencies"] != after_isolated["dependencies"]:
        raise RuntimeError("original source or isolated dependency evidence changed during patch")
    if git(original_root, "submodule", "status", "--recursive", raw=True) != original_modules:
        raise RuntimeError("original recursive submodule state changed during patch")
    return {"schema_version": 1, "contract": CONTRACT, "operation": "PATCH_APPLIED_NOT_BUILT",
            "original_root": str(original_root), "isolated_root": str(isolated_root),
            "copy_manifest_path": str(copy_manifest), "copy_manifest_sha256": sha256(copy_manifest),
            "original_before": before_original, "original_after": after_original,
            "isolated_before": before_isolated, "isolated_after": after_isolated,
            "original_unchanged": True, "dependencies_unchanged": True,
            "network_used": False, "build_executed": False,
            "applied_at_utc": datetime.now(timezone.utc).isoformat()}


def verify_runtime(source_root: Path, log_path: Path | None = None) -> dict:
    root = Path(source_root).resolve()
    evidence = check_source(root, patched=True)
    binary = root / BINARY
    with binary.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError("PX4 binary is not ELF")
    if not contains_marker(binary):
        raise ValueError("PX4 binary lacks the registered magnetic contract marker")
    result = {"schema_version": 1, "contract": CONTRACT, "operation": "RUNTIME_ARTIFACT_VERIFIED",
              "source_root": str(root), **evidence, "binary_path": str(binary),
              "binary_sha256": sha256(binary), "binary_bytes": binary.stat().st_size,
              "expected_startup_log_marker": MARKER, "actual_startup_log_verified": False,
              "verification_limit": "ELF/source provenance does not replace actual flight/log checks"}
    if log_path is not None:
        log_path = Path(log_path).resolve()
        if MARKER not in log_path.read_text(encoding="utf-8", errors="replace"):
            raise ValueError("actual PX4 startup log lacks magnetic contract marker")
        result.update(actual_startup_log_verified=True, actual_startup_log_path=str(log_path),
                      actual_startup_log_sha256=sha256(log_path))
    return result


def validate_runtime_manifest(path: Path) -> dict:
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    for key, expected in {"schema_version": 1, "contract": CONTRACT, "px4_commit": PINNED_COMMIT,
                          "bridge_source_sha256": PATCHED_SHA256, "patch_sha256": PATCH_SHA256,
                          "operation": "RUNTIME_ARTIFACT_VERIFIED"}.items():
        if result.get(key) != expected:
            raise ValueError("invalid magnetic runtime manifest: " + key)
    # Recheck the current source and ELF, not just an asserted manifest hash.
    current = verify_runtime(Path(result["source_root"]))
    for key in ("binary_path", "binary_sha256", "binary_bytes", "dependencies", "tracked_dirty_paths"):
        if current[key] != result.get(key):
            raise ValueError("magnetic runtime changed since verification: " + key)
    return result


def assert_runtime_unchanged(expected: dict, actual: dict) -> None:
    """Bind final startup evidence to the exact source/ELF selected initially."""
    keys = ("contract", "px4_commit", "bridge_source_sha256", "patch_sha256", "source_root",
            "binary_path", "binary_sha256", "binary_bytes", "dependencies", "tracked_dirty_paths")
    for key in keys:
        if key not in expected or actual.get(key) != expected[key]:
            raise ValueError("magnetic runtime differs from the initial verified manifest: " + key)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("plan", "prepare"):
        command = sub.add_parser(name)
        command.add_argument("--px4-root", type=Path, required=True)
        command.add_argument("--destination", type=Path, required=True)
        command.add_argument("--output", type=Path)
        if name == "prepare":
            command.add_argument("--initialize-dependencies", action="store_true")
    command = sub.add_parser("verify-runtime")
    command.add_argument("--px4-root", type=Path, required=True)
    command.add_argument("--px4-log", type=Path)
    command.add_argument("--output", type=Path)
    command = sub.add_parser("apply-isolated")
    command.add_argument("--original-root", type=Path, required=True)
    command.add_argument("--px4-root", type=Path, required=True)
    command.add_argument("--copy-manifest", type=Path, required=True)
    command.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is not None:
        output = args.output.resolve()
        if output.exists():
            raise ValueError("evidence output must not already exist")
        if args.action in ("plan", "prepare"):
            for protected in (args.px4_root.resolve(), args.destination.resolve()):
                if output == protected or protected in output.parents:
                    raise ValueError("preparation evidence must be outside both PX4 checkouts")
        elif args.action == "apply-isolated":
            for protected in (args.original_root.resolve(), args.px4_root.resolve()):
                if output == protected or protected in output.parents:
                    raise ValueError("patch evidence must be outside both PX4 checkouts")
    if args.action == "plan":
        result = plan(args.px4_root, args.destination)
    elif args.action == "prepare":
        result = prepare(args.px4_root, args.destination, args.initialize_dependencies)
    elif args.action == "apply-isolated":
        result = apply_isolated(args.original_root, args.px4_root, args.copy_manifest)
    else:
        result = verify_runtime(args.px4_root, args.px4_log)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
