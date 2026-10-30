"""Close, validate, and archive SQLite rosbag recordings without recorder compression.

Record on local Linux ext4. Standard zstd closes a complete compressed frame;
both byte equality and ROS's native compressed reader must pass before publish.
Failed artifacts remain in their uniquely owned spool for diagnosis.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import uuid

import yaml


ZSTD_ARCHIVE_ARGUMENTS = ("-T4", "-19", "--long=27", "--check")


def archive_compression_profile() -> dict:
    """Describe the fixed lossless profile used for future closed recordings."""
    return {"name": "zstd19_long27", "executable": "zstd", "arguments": list(ZSTD_ARCHIVE_ARGUMENTS),
            "threads": 4, "level": 19, "long_window_log": 27, "checksum": True}


class RecordingArchiveError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _contained_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise RecordingArchiveError("Invalid relative rosbag file name")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink() or not path.is_file():
        raise RecordingArchiveError("Rosbag file is missing, linked, or outside its directory: " + relative)
    return path


def validate_sqlite_recording(bag: Path) -> dict:
    """Read every SQLite page and compare actual per-topic rows with metadata."""
    bag = Path(bag).resolve(strict=True)
    metadata_path = bag / "metadata.yaml"
    info = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))["rosbag2_bagfile_information"]
    if info.get("storage_identifier") != "sqlite3":
        raise RecordingArchiveError("Only SQLite recordings are supported")
    if info.get("compression_format") or str(info.get("compression_mode", "none")).lower() not in {"", "none"}:
        raise RecordingArchiveError("Recorder must produce uncompressed SQLite files")
    paths = info.get("relative_file_paths")
    if not isinstance(paths, list) or not paths or len(set(paths)) != len(paths):
        raise RecordingArchiveError("Missing or duplicate recording files")
    expected_topics = {}
    for item in info.get("topics_with_message_count", []):
        name = item["topic_metadata"]["name"]
        if name in expected_topics:
            raise RecordingArchiveError("Duplicate topic metadata")
        expected_topics[name] = int(item["message_count"])
    if not expected_topics or any(count < 0 for count in expected_topics.values()):
        raise RecordingArchiveError("Missing or invalid topic counts")
    counts = Counter()
    files = []
    for relative in paths:
        path = _contained_file(bag, relative)
        if path.suffix != ".db3":
            raise RecordingArchiveError("Recorder did not produce a plain .db3 file")
        if any(p.exists() and p.stat().st_size for p in (Path(str(path) + "-wal"), Path(str(path) + "-journal"))):
            raise RecordingArchiveError("Recording has an unclosed SQLite WAL/journal")
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RecordingArchiveError("SQLite integrity_check failed: " + relative)
            topics = dict(connection.execute("SELECT id,name FROM topics"))
            grouped = connection.execute("SELECT topic_id,count(*) FROM messages GROUP BY topic_id").fetchall()
            if any(identifier not in topics for identifier, _ in grouped):
                raise RecordingArchiveError("Message references an unknown topic")
            for identifier, count in grouped:
                counts[topics[identifier]] += count
            count = sum(number for _, number in grouped)
            bounds = connection.execute("SELECT min(timestamp),max(timestamp) FROM messages").fetchone()
        finally:
            connection.close()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path),
                      "message_count": count, "first_timestamp_ns": bounds[0], "last_timestamp_ns": bounds[1],
                      "sqlite_integrity": "ok"})
    expected_total = int(info.get("message_count", -1))
    observed = {name: counts[name] for name in expected_topics}
    if set(counts) - set(expected_topics) or observed != expected_topics or sum(counts.values()) != expected_total:
        raise RecordingArchiveError("SQLite rows do not match metadata message/topic counts")
    listed = {item["path"]: int(item["message_count"]) for item in info.get("files", [])}
    if listed and listed != {item["path"]: item["message_count"] for item in files}:
        raise RecordingArchiveError("SQLite file counts do not match metadata files")
    return {"status": "PASS", "metadata_sha256": sha256(metadata_path), "message_count": expected_total,
            "topic_counts": expected_topics, "files": files}


def create_recording_spool(trial: Path, base: Path = Path("/root/uav_tracking_bag_spool")) -> Path:
    if os.name != "posix" or not Path("/proc/self/mountinfo").is_file():
        raise RecordingArchiveError("Live recording requires a Linux ext4 spool")
    if shutil.which("zstd") is None:
        raise RecordingArchiveError("Install the zstd CLI before starting a recorded trial")
    base.mkdir(parents=True, exist_ok=True)
    resolved = base.resolve()
    mounts = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        separator = fields.index("-")
        mount = Path(fields[4].replace("\\040", " "))
        if resolved == mount or mount in resolved.parents:
            mounts.append((len(str(mount)), fields[separator + 1]))
    if not mounts or max(mounts)[1] != "ext4":
        raise RecordingArchiveError("Recording spool must resolve to Linux ext4")
    spool = Path(tempfile.mkdtemp(prefix="trial_", dir=resolved))
    (spool / "owned_spool.json").write_text(json.dumps({"trial": str(Path(trial).resolve()),
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    return spool


def verify_native_reader(bag: Path, expected: dict, reader_factory=None) -> dict:
    if reader_factory is None:
        import rosbag2_py
        reader = rosbag2_py.SequentialCompressionReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id="sqlite3"),
                    rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"))
    else:
        reader = reader_factory(bag)
    counts = Counter()
    while reader.has_next():
        topic, _, _ = reader.read_next()
        counts[topic] += 1
    observed = {name: counts[name] for name in expected["topic_counts"]}
    if observed != expected["topic_counts"] or set(counts) - set(observed) or sum(counts.values()) != expected["message_count"]:
        raise RecordingArchiveError("Native ROS compressed-reader rows do not match validated source")
    return {"status": "PASS", "reader": type(reader).__name__, "message_count": sum(counts.values()),
            "topic_counts": observed, "full_stream_read": True}


def finalize_recording(spool: Path, destination: Path, recorder_exit_code: int, reader_factory=None) -> dict:
    spool, destination = Path(spool).resolve(strict=True), Path(destination).absolute()
    owner = json.loads((spool / "owned_spool.json").read_text(encoding="utf-8"))
    if Path(owner["trial"]).resolve() != destination.parent.resolve() or destination.exists():
        raise RecordingArchiveError("Recording spool ownership or new destination does not match")
    if recorder_exit_code != 0:
        raise RecordingArchiveError("Recorder did not close successfully; spool retained")
    processing_started_at_utc = datetime.now(timezone.utc).isoformat()
    processing_started = time.monotonic()
    source = spool / "rosbag"
    raw = validate_sqlite_recording(source)
    archive = spool / "archive"
    archive.mkdir(exist_ok=False)
    info = yaml.safe_load((source / "metadata.yaml").read_text(encoding="utf-8"))
    compressed_files = []
    for item in raw["files"]:
        source_file = _contained_file(source, item["path"])
        compressed_name = item["path"] + ".zstd"
        compressed = archive / compressed_name
        compressed.parent.mkdir(parents=True, exist_ok=True)
        compression_command = ["zstd", *ZSTD_ARCHIVE_ARGUMENTS, "-q", str(source_file), "-o", str(compressed)]
        compression_started = time.monotonic()
        subprocess.run(compression_command, check=True)
        compression_wall_s = time.monotonic() - compression_started
        subprocess.run(["zstd", "--test", "-q", str(compressed)], check=True)
        digest, size = hashlib.sha256(), 0
        with subprocess.Popen(["zstd", "--decompress", "--stdout", "-q", str(compressed)], stdout=subprocess.PIPE) as process:
            for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
                digest.update(block); size += len(block)
            if process.wait() or digest.hexdigest() != item["sha256"] or size != item["bytes"]:
                raise RecordingArchiveError("Standard zstd roundtrip differs from validated SQLite bytes")
        compressed_files.append({"path": compressed_name, "sha256": sha256(compressed), "bytes": compressed.stat().st_size,
                                 "raw_sha256": item["sha256"], "raw_bytes": item["bytes"], "zstd_test": "PASS",
                                 "compression_command": compression_command, "compression_wall_s": compression_wall_s})
    metadata = info["rosbag2_bagfile_information"]
    metadata.update(compression_format="zstd", compression_mode="FILE",
                    relative_file_paths=[item["path"] for item in compressed_files])
    for item in metadata.get("files", []):
        item["path"] += ".zstd"
    (archive / "metadata.yaml").write_text(yaml.safe_dump(info, sort_keys=False), encoding="utf-8")
    native = verify_native_reader(archive, raw, reader_factory)
    # Native file decompression creates .db3 siblings in this owned ext4 stage.
    # Their hashes must equal the checked original before they are discarded.
    if reader_factory is None:
        for item in raw["files"]:
            decoded = _contained_file(archive, item["path"])
            if decoded.stat().st_size != item["bytes"] or sha256(decoded) != item["sha256"]:
                raise RecordingArchiveError("Native decompression differs from original SQLite bytes")
            decoded.unlink()
    pending = destination.parent / (".rosbag_" + uuid.uuid4().hex + ".pending")
    shutil.copytree(archive, pending)
    for item in compressed_files:
        if sha256(_contained_file(pending, item["path"])) != item["sha256"]:
            raise RecordingArchiveError("Published-drive copy differs from validated archive")
    if sha256(pending / "metadata.yaml") != sha256(archive / "metadata.yaml"):
        raise RecordingArchiveError("Published-drive metadata differs from validated archive")
    pending.rename(destination)
    result = {"schema_version": 1, "status": "PASS", "policy": "ext4_sqlite_close_standard_zstd_verified_native_read",
              "source_spool": str(spool), "destination": str(destination), "recorder_exit_code": recorder_exit_code,
              "raw_validation": raw, "compressed_files": compressed_files, "native_reader_validation": native,
              "compression_profile": archive_compression_profile(),
              "zstd_version": subprocess.check_output(["zstd", "--version"], text=True).strip(),
              "published_metadata_sha256": sha256(destination / "metadata.yaml"),
              "finished_at_utc": datetime.now(timezone.utc).isoformat(), "spool_retained": False}
    # Only remove the uniquely created spool whose marker and source we checked.
    if spool.parent.name != "uav_tracking_bag_spool" or not spool.name.startswith("trial_"):
        result["spool_retained"] = True
    else:
        shutil.rmtree(spool)
    result["archive_processing"] = {"started_at_utc": processing_started_at_utc,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(), "wall_s": time.monotonic() - processing_started,
        "scope": "closed_recording_validation_compression_native_read_verified_copy_and_owned_spool_cleanup"}
    return result
