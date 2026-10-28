"""Copy a clean PX4 source/Git cache without build outputs or network access.

Preserves the exact initialized/uninitialized submodule state. Files are copied,
never hard-linked; the source is inspected with optional Git locks disabled.
Existing destinations are refused and failed partial copies are left for review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


PX4_V1170 = "d6f12ad1c4f70ad3230afd7d86e971421e02fef4"


def inspect(source: Path) -> dict:
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    def git(*arguments: str) -> str:
        result = subprocess.run(["git", "-C", str(source), *arguments], env=environment,
                                check=True, capture_output=True, text=True)
        return result.stdout
    commit = git("rev-parse", "HEAD").strip()
    dirty = git("status", "--porcelain", "--untracked-files=no").strip()
    submodules = git("submodule", "status", "--recursive")
    return {"commit": commit, "tracked_clean": not dirty,
            "submodule_status_sha256": hashlib.sha256(submodules.encode()).hexdigest(),
            "submodule_states": submodules.splitlines(),
            "initialized_submodules": sum(line.startswith(" ") for line in submodules.splitlines()),
            "uninitialized_submodules": sum(line.startswith("-") for line in submodules.splitlines())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/root/PX4-Autopilot"))
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--expected-commit", default=PX4_V1170)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("Run inside the Linux distribution containing the source cache")
    source = args.source.resolve(strict=True)
    destination = args.destination.absolute()
    if destination.exists() or destination.is_symlink():
        parser.error("Destination exists; refusing to overwrite or reuse it")
    resolved_destination = destination.resolve()
    if resolved_destination == source or source in resolved_destination.parents or resolved_destination in source.parents:
        parser.error("Source and destination must be separate sibling trees")
    resolved_manifest = args.manifest.resolve()
    if resolved_manifest == source or source in resolved_manifest.parents:
        parser.error("Manifest must be outside the source tree")
    if not (source / ".git").is_dir():
        parser.error("Source must contain its independent Git directory")
    if (source / ".git/objects/info/alternates").exists():
        parser.error("Source uses an external Git object alternate; make an independent cache first")
    before = inspect(source)
    if before["commit"] != args.expected_commit or not before["tracked_clean"]:
        parser.error("Source commit or tracked cleanliness does not match the requested baseline")
    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {"__pycache__"} & set(names)
        if Path(directory) == source:
            ignored |= {"build", "install", "log"} & set(names)
        return ignored
    shutil.copytree(source, resolved_destination, symlinks=True, copy_function=shutil.copy2, ignore=ignore)
    copied = inspect(resolved_destination)
    after = inspect(source)
    if before != after or before != copied:
        raise RuntimeError("Source changed during copy or destination Git/submodule evidence differs")
    manifest = {"copied_at_utc": datetime.now(timezone.utc).isoformat(), "source": str(source),
                "destination": str(resolved_destination), "network_used": False,
                "file_method": "independent copy2 files; relative symlinks preserved",
                "excluded_source_root_directories": ["build", "install", "log"],
                "source_unchanged": True, **copied}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "submodule_states"}))


if __name__ == "__main__":
    main()
