"""Exact rsync-filtered source/copy byte maps for one immutable freeze attempt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re

RSYNC_EXCLUSIONS = ("__pycache__", ".pytest_cache", "results/", ".git/", "node_modules/",
                    ".test_temp/", "*.egg-info/", "ros2_ws/build/", "ros2_ws/install/", "ros2_ws/log/")


def now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_filters(script):
    actual = tuple(re.findall(r"--exclude='([^']+)'", Path(script).read_text(encoding="utf-8")))
    if actual != RSYNC_EXCLUSIONS:
        raise ValueError("Public freeze rsync exclusions differ from the byte-map rules")


def excluded(relative, directory):
    """Rsync trailing-slash rules select directories; slash rules use root paths."""
    for pattern in RSYNC_EXCLUSIONS:
        directory_only = pattern.endswith("/")
        if directory_only and not directory:
            continue
        value = pattern.rstrip("/")
        candidate = relative if "/" in value else relative.rsplit("/", 1)[-1]
        if fnmatch.fnmatchcase(candidate, value):
            return True
    return False


def file_map(root):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Expected a source or frozen directory")
    result = {}
    def walk(directory, prefix=""):
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        for entry in entries:
            relative = prefix + entry.name
            directory_entry = entry.is_dir(follow_symlinks=False)
            if excluded(relative, directory_entry):
                continue
            path = Path(entry.path)
            if entry.is_symlink():
                result[relative] = {"kind": "symlink", "target": os.readlink(path)}
            elif directory_entry:
                walk(path, relative + "/")
            elif entry.is_file(follow_symlinks=False):
                before = path.stat(follow_symlinks=False)
                digest = sha(path)
                after = path.stat(follow_symlinks=False)
                if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                    raise RuntimeError("File changed while hashing: " + relative)
                result[relative] = {"kind": "file", "bytes": after.st_size, "sha256": digest}
            else:
                raise ValueError("Unsupported non-regular source entry: " + relative)
    walk(root)
    return result


def differences(expected, actual):
    return {"missing": sorted(expected.keys() - actual.keys()),
            "added": sorted(actual.keys() - expected.keys()),
            "changed": sorted(name for name in expected.keys() & actual.keys() if expected[name] != actual[name])}


def snapshot(source, output):
    source = Path(source).resolve(strict=True)
    validate_filters(source / "scripts/freeze_full_plan_workspace.sh")
    evidence = {"schema_version": 1, "created_utc": now(), "source": str(source),
                "rsync_exclusions": list(RSYNC_EXCLUSIONS), "entries": file_map(source)}
    write_new(output, evidence)
    return evidence


def verify(before_path, source, frozen, output_dir, build_returncode=0, results_store=None):
    source = Path(source).resolve(strict=True)
    frozen = Path(frozen).absolute()
    output_dir = Path(output_dir).resolve(strict=True)
    report_path = output_dir / "source_frozen_integrity.json"
    if report_path.exists() or report_path.is_symlink():
        raise FileExistsError("Integrity result already exists; select a new attempt")
    before = json.loads(Path(before_path).read_text(encoding="utf-8"))
    report = {"schema_version": 1, "created_utc": now(), "status": "FAIL",
              "scope": "RSYNC_FILTERED_SOURCE_PRE_POST_AND_COMPLETE_FROZEN_COPY_BYTES",
              "source": str(source), "frozen": str(frozen), "build_returncode": build_returncode,
              "before": {"path": str(Path(before_path).absolute()), "sha256": sha(before_path)},
              "rsync_exclusions": list(RSYNC_EXCLUSIONS), "errors": []}
    try:
        if before.get("source") != str(source) or before.get("rsync_exclusions") != list(RSYNC_EXCLUSIONS):
            raise ValueError("Pre-freeze map belongs to another source or filter set")
        validate_filters(source / "scripts/freeze_full_plan_workspace.sh")
        expected = before["entries"]
        after = file_map(source)
        write_new(output_dir / "source_after.json", {"source": str(source), "entries": after})
        report["source_pre_post"] = differences(expected, after)
        copied = file_map(frozen)
        if results_store is not None:
            # Public freeze creates this one new artifact after rsync. It was
            # not copied source: verify its exact destination before allowing it.
            results_link = frozen / "results"
            if not results_link.is_symlink() or results_link.resolve(strict=True) != Path(results_store).resolve(strict=True):
                raise ValueError("Generated frozen results symlink does not select the declared new store")
            if "results" in expected:
                raise ValueError("Source already contained a results symlink; cannot treat it as a generated artifact")
            report["generated_results_link"] = {"path": str(results_link), "target": os.readlink(results_link),
                                                 "expected_store": str(Path(results_store).resolve(strict=True))}
            copied.pop("results")
        write_new(output_dir / "frozen_actual.json", {"frozen": str(frozen), "entries": copied})
        report["maps"] = {name: {"path": str(output_dir / name), "sha256": sha(output_dir / name)}
                          for name in ("source_after.json", "frozen_actual.json")}
        report["frozen_copy"] = differences(expected, copied)
        report["expected_entries"] = len(expected)
        report["actual_source_entries"] = len(after)
        report["actual_frozen_entries"] = len(copied)
        report["source_unchanged"] = not any(report["source_pre_post"].values())
        report["copy_identical"] = not any(report["frozen_copy"].values())
        if report["source_unchanged"] and report["copy_identical"]:
            report["status"] = "PASS"
    except Exception as error:
        report["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        write_new(report_path, report)
    print(json.dumps({"status": report["status"], "integrity_report": str(report_path)}), flush=True)
    return report


def publish(source_dir, output_dir):
    source_dir, output_dir = Path(source_dir).resolve(strict=True), Path(output_dir)
    names = ("source_before.json", "source_after.json", "frozen_actual.json", "source_frozen_integrity.json")
    output_dir.mkdir(exist_ok=False)
    for name in names:
        source = source_dir / name
        if source.is_file():
            with (output_dir / name).open("xb") as stream:
                stream.write(source.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    command = commands.add_parser("snapshot")
    command.add_argument("--source", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("verify")
    command.add_argument("--before", type=Path, required=True)
    command.add_argument("--source", type=Path, required=True)
    command.add_argument("--frozen", type=Path, required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--build-returncode", type=int, required=True)
    command.add_argument("--results-store", type=Path)
    command = commands.add_parser("publish")
    command.add_argument("--source-dir", type=Path, required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "snapshot":
        snapshot(args.source, args.output)
    elif args.action == "verify":
        result = verify(args.before, args.source, args.frozen, args.output_dir, args.build_returncode, args.results_store)
        raise SystemExit(0 if result["status"] == "PASS" else 2)
    else:
        publish(args.source_dir, args.output_dir)
