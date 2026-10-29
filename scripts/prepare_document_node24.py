"""Prepare official Linux Node 24 in a private cache; extraction is opt-in.

No apt/npm/global changes. Download-only is the default. Run installation only
in the separately scheduled document resource window, never during SITL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import urllib.request

VERSION = "24.15.0"
BASE_URL = "https://nodejs.org/dist/v" + VERSION
ARCHIVE = "node-v" + VERSION + "-linux-x64.tar.xz"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def official_digest(checksums, filename=ARCHIVE):
    matches = []
    for line in checksums.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+\*?([^\s]+)", line.strip())
        if match and match[2] == filename:
            matches.append(match[1])
    if len(matches) != 1:
        raise ValueError("Official SHASUMS256.txt needs one exact archive entry")
    return matches[0]


def download(url, destination, *, maximum):
    destination = Path(destination)
    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists():
        raise ValueError("Keep the earlier partial download; choose a new private cache: " + str(temporary))
    total = 0
    with urllib.request.urlopen(url, timeout=45) as response, temporary.open("xb") as stream:
        if not response.geturl().startswith(BASE_URL + "/"):
            raise ValueError("Official download redirected outside its version directory")
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > maximum:
                raise ValueError("Official artifact exceeds declared size limit")
            stream.write(block)
    temporary.rename(destination)


def private_paths(cache, tools_root):
    cache, tools_root = Path(cache).resolve(), Path(tools_root).resolve()
    if cache == tools_root or cache in tools_root.parents or tools_root in cache.parents:
        raise ValueError("Cache and installation root must be separate private directories")
    if len(cache.parts) < 4 or len(tools_root.parts) < 3:
        raise ValueError("Use dedicated absolute cache and tools directories")
    return cache, tools_root


def safe_members(archive, destination):
    destination = Path(destination).resolve()
    prefix = ARCHIVE.removesuffix(".tar.xz")
    members = archive.getmembers()
    for member in members:
        if not member.name or Path(member.name).parts[0] != prefix:
            raise ValueError("Archive member has the wrong top-level directory")
        target = (destination / member.name).resolve()
        if not target.is_relative_to(destination / prefix) or not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise ValueError("Unsafe archive member")
        if member.issym() or member.islnk():
            link = (target.parent / member.linkname).resolve() if member.issym() else (destination / member.linkname).resolve()
            if not link.is_relative_to(destination / prefix):
                raise ValueError("Archive link escapes the private Node directory")
    return members


def prepare(cache, tools_root, *, install=False, docx_modules=None):
    if sys.platform != "linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ValueError("This private runtime is explicitly Linux x64")
    cache, tools_root = private_paths(cache, tools_root)
    cache.mkdir(parents=True, exist_ok=True)
    checksums = cache / "SHASUMS256.txt"
    if not checksums.exists():
        download(BASE_URL + "/SHASUMS256.txt", checksums, maximum=1024 * 1024)
    expected = official_digest(checksums.read_text(encoding="ascii"))
    archive = cache / ARCHIVE
    if not archive.exists():
        print("Downloading official " + ARCHIVE, flush=True)
        download(BASE_URL + "/" + ARCHIVE, archive, maximum=256 * 1024 * 1024)
    if sha(archive) != expected:
        raise ValueError("Archive does not match official SHASUMS256.txt; preserve cache for diagnosis")
    result = {"schema_version": 1, "kind": "PRIVATE_DOCUMENT_NODE24", "version": VERSION,
              "archive": {"path": str(archive), "sha256": expected, "bytes": archive.stat().st_size,
                          "url": BASE_URL + "/" + ARCHIVE},
              "official_checksums": {"path": str(checksums), "sha256": sha(checksums), "url": BASE_URL + "/SHASUMS256.txt"},
              "tools_root": str(tools_root), "status": "DOWNLOADED_VERIFIED_NOT_EXTRACTED"}
    if install:
        import tarfile
        import tempfile
        tools_root.mkdir(parents=True, exist_ok=True)
        target = tools_root / ARCHIVE.removesuffix(".tar.xz")
        if target.exists():
            raise ValueError("Preserve the existing runtime; never overwrite an installation")
        staging = Path(tempfile.mkdtemp(prefix=".node24-staging-", dir=tools_root))
        with tarfile.open(archive, "r:xz") as source:
            source.extractall(staging, members=safe_members(source, staging))
        os.rename(staging / target.name, target)
        staging.rmdir()
        executable = target / "bin/node"
        version = subprocess.run([str(executable), "--version"], capture_output=True, text=True, check=True).stdout.strip()
        if version != "v" + VERSION:
            raise ValueError("Installed Node version differs")
        result.update(status="PRIVATE_RUNTIME_INSTALLED", executable=str(executable), executable_sha256=sha(executable))
        if docx_modules is not None:
            module_path = Path(docx_modules).resolve()
            package = module_path / "docx/package.json"
            if not package.is_file():
                raise ValueError("Explicit docx module directory is unavailable")
            environment = dict(os.environ, NODE_PATH=str(module_path))
            command = subprocess.run([str(executable), "-e", "console.log(require.resolve('docx'))"],
                                     capture_output=True, text=True, check=True, env=environment)
            result["docx"] = {"node_path": str(module_path), "resolved": command.stdout.strip(), "package_sha256": sha(package)}
    name = "installed_manifest.json" if install else "download_manifest.json"
    manifest = cache / name
    if manifest.exists():
        previous = json.loads(manifest.read_text(encoding="utf-8"))
        if previous != result:
            raise ValueError("Existing preparation manifest differs; choose a new cache")
    else:
        with manifest.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("/root/.cache/uav_documents/node24-" + VERSION))
    parser.add_argument("--tools-root", type=Path, default=Path("/root/uav_document_tools"))
    parser.add_argument("--install", action="store_true", help="Explicit extraction, only in the document resource window")
    parser.add_argument("--docx-modules", type=Path, help="Existing pure-JS node_modules, no npm installation")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(args.cache, args.tools_root, install=args.install, docx_modules=args.docx_modules), indent=2))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
