#!/usr/bin/env python3
"""Seed the pinned PX4 Micro-CDR download from an independent Git-only cache.

Reads a clean existing v2.0.1 source repository, copies Git objects without
hardlinks, and optionally reruns CMake's normal clone step. No compilation,
network, global Git configuration, or copying of generated headers/libraries.
The emitted shell file scopes the public-URL rewrite to the resumed build.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

URL = "https://github.com/eProsima/Micro-CDR.git"
TAG = "v2.0.1"
COMMIT = "3d1b17703c7cf4f22def2910bc845bdb5152d7b5"


def run(arguments: list[str], environment: dict[str, str]) -> str:
    return subprocess.check_output(arguments, env=environment, text=True).strip()


def inspect(source: Path, environment: dict[str, str]) -> dict:
    prefix = ["git", "-C", str(source)]
    return {"head": run(prefix + ["rev-parse", "HEAD"], environment),
            "tag_commit": run(prefix + ["rev-parse", TAG + "^{commit}"], environment),
            "tracked_status": run(prefix + ["status", "--porcelain", "--untracked-files=no"], environment)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--clone-script", type=Path, required=True)
    parser.add_argument("--environment-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, clone_script = args.source.resolve(strict=True), args.clone_script.resolve(strict=True)
    cache = args.cache.absolute()
    for output in (cache, args.environment_file, args.output):
        if output.exists() or output.is_symlink():
            parser.error("Refusing to replace existing output: " + str(output))
        if source == output.resolve() or source in output.resolve().parents:
            parser.error("All cache/evidence outputs must be outside the existing source")
    body = clone_script.read_text(encoding="utf-8")
    if URL not in body or not re.search(r'checkout\s+"?' + re.escape(TAG) + r'"?\s+--', body):
        parser.error("CMake clone script does not request the pinned official Micro-CDR tag")
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    before = inspect(source, environment)
    if before != {"head": COMMIT, "tag_commit": COMMIT, "tracked_status": ""}:
        parser.error("Existing source is not the clean pinned Micro-CDR v2.0.1 repository")
    git_directory = Path(run(["git", "-C", str(source), "rev-parse", "--absolute-git-dir"], environment))
    if (git_directory / "objects/info/alternates").exists():
        parser.error("Existing source uses external Git alternates")
    cache.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--bare", "--no-hardlinks", "--local", str(source), str(cache)], environment)
    cached_commit = run(["git", "--git-dir=" + str(cache), "rev-parse", TAG + "^{commit}"], environment)
    if cached_commit != COMMIT or (cache / "objects/info/alternates").exists():
        raise RuntimeError("Independent cache object provenance failed")
    rewrite = "url.file://" + str(cache) + ".insteadOf"
    count = int(environment.get("GIT_CONFIG_COUNT", "0"))
    entries = ((rewrite, URL), ("protocol.file.allow", "always"))
    exports = {"GIT_CONFIG_COUNT": str(count + len(entries))}
    for offset, (key, value) in enumerate(entries):
        exports["GIT_CONFIG_KEY_" + str(count + offset)] = key
        exports["GIT_CONFIG_VALUE_" + str(count + offset)] = value
    environment.update(exports)
    # Only this generated source-download step executes. Its own successful
    # completion creates CMake's stamp; the helper never writes a stamp itself.
    run(["cmake", "-P", str(clone_script)], environment)
    downloaded = clone_script.parent.parent / "src/microcdr"
    after_download = inspect(downloaded, environment)
    if after_download != before or inspect(source, environment) != before:
        raise RuntimeError("Downloaded source differs or existing repository changed")
    stamp = downloaded.parent / "microcdr-stamp/microcdr-gitclone-lastrun.txt"
    if not stamp.is_file():
        raise RuntimeError("CMake did not generate its successful clone stamp")
    args.environment_file.parent.mkdir(parents=True, exist_ok=True)
    args.environment_file.write_text("# Scope only to the resumed isolated PX4 build.\n" + "".join(
        "export " + key + "=" + shlex.quote(value) + "\n" for key, value in exports.items()), encoding="utf-8")
    result = {"schema_version": 1, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
              "source": str(source), "source_unchanged": True, "tag": TAG, "commit": COMMIT,
              "official_url": URL, "cache": str(cache), "copied_content": "Git objects and refs only; no hardlinks",
              "clone_script": str(clone_script), "clone_script_sha256": hashlib.sha256(body.encode()).hexdigest(),
              "downloaded_source": str(downloaded), "downloaded_source_check": after_download,
              "cmake_generated_stamp": str(stamp), "environment_file": str(args.environment_file),
              "global_git_configuration_changed": False, "network_used": False, "compilation_executed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
