"""Independent, source-preserving zstd/SQLite audit; run only after flights are idle.

Uses installed libzstd directly, so no zstd CLI, ROS node, or package install is
needed. Generated caches are retained and their exact paths are reported.
The optional ROS compression-reader comparison runs only if both independent
decompressions contain valid SQLite databases. Nothing repairs the source bag.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import ctypes as C
import ctypes.util
from datetime import datetime, timezone
import gc
import hashlib
import json
import mmap
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time


class InputBuffer(C.Structure):
    _fields_ = [("src", C.c_void_p), ("size", C.c_size_t), ("pos", C.c_size_t)]


class OutputBuffer(C.Structure):
    _fields_ = [("dst", C.c_void_p), ("size", C.c_size_t), ("pos", C.c_size_t)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(path: Path) -> dict:
    info = path.stat()
    return {"path": str(path), "bytes": info.st_size, "mtime_ns": info.st_mtime_ns,
            "device": info.st_dev, "inode": info.st_ino, "sha256": sha256(path)}


class ZstdStream:
    def __init__(self):
        name = ctypes.util.find_library("zstd")
        if name is None:
            raise RuntimeError("Installed libzstd was not found; no package is installed by this audit")
        self.library_name = name
        self.lib = C.CDLL(name)
        definitions = {
            "ZSTD_createDStream": (C.c_void_p, []),
            "ZSTD_freeDStream": (C.c_size_t, [C.c_void_p]),
            "ZSTD_initDStream": (C.c_size_t, [C.c_void_p]),
            "ZSTD_decompressStream": (C.c_size_t, [C.c_void_p, C.POINTER(OutputBuffer), C.POINTER(InputBuffer)]),
            "ZSTD_isError": (C.c_uint, [C.c_size_t]),
            "ZSTD_getErrorName": (C.c_char_p, [C.c_size_t]),
            "ZSTD_versionString": (C.c_char_p, []),
            "ZSTD_getFrameContentSize": (C.c_ulonglong, [C.c_void_p, C.c_size_t]),
            "ZSTD_findFrameCompressedSize": (C.c_size_t, [C.c_void_p, C.c_size_t]),
        }
        for name, (result, arguments) in definitions.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, arguments

    def check(self, value: int) -> int:
        if self.lib.ZSTD_isError(value):
            raise RuntimeError(self.lib.ZSTD_getErrorName(value).decode("utf-8", "replace"))
        return value

    def header(self, source: Path) -> dict:
        with source.open("rb") as handle:
            header = handle.read(18)
        buffer = C.create_string_buffer(header)
        size = int(self.lib.ZSTD_getFrameContentSize(buffer, len(header)))
        return {"first_frame_content_size": size if size < 2**64 - 2 else None,
                "first_frame_checksum_flag": bool(header[4] & 4)
                if len(header) >= 5 and header[:4] == b"\x28\xb5\x2f\xfd" else None,
                "library": self.library_name, "version": self.lib.ZSTD_versionString().decode()}

    def scan_frames(self, source: Path) -> dict:
        """Parse frame boundaries without decoding, using a private, source-preserving mapping."""
        size, offset, frames = source.stat().st_size, 0, []
        with source.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_COPY) as mapped:
            memory = (C.c_char * size).from_buffer(mapped)
            try:
                while offset < size:
                    count = int(self.lib.ZSTD_findFrameCompressedSize(C.addressof(memory) + offset, size - offset))
                    if self.lib.ZSTD_isError(count):
                        return {"complete": False, "complete_frames": frames, "failure_offset": offset,
                                "remaining_source_bytes": size - offset,
                                "error": self.lib.ZSTD_getErrorName(count).decode()}
                    if count == 0:
                        raise RuntimeError("frame scanner made no progress")
                    frames.append({"offset": offset, "compressed_bytes": count})
                    offset += count
                return {"complete": True, "complete_frames": frames, "source_bytes": size}
            finally:
                del memory

    def decompress(self, source: Path, destination: Path | None = None,
                   expected_bytes: int | None = None, space_guard=None) -> dict:
        context = self.lib.ZSTD_createDStream()
        if not context:
            raise MemoryError("ZSTD_createDStream failed")
        started, size, frames, remaining, consumed = time.monotonic(), 0, 0, None, 0
        digest, next_guard = hashlib.sha256(), 0
        try:
            self.check(self.lib.ZSTD_initDStream(context))
            with source.open("rb") as compressed, (destination.open("xb") if destination else nullcontext()) as output:
                for block in iter(lambda: compressed.read(1024 * 1024), b""):
                    memory = C.create_string_buffer(block)
                    incoming = InputBuffer(C.cast(memory, C.c_void_p), len(block), 0)
                    output_full = False
                    while incoming.pos < incoming.size or output_full:
                        buffer = C.create_string_buffer(4 * 1024 * 1024)
                        outgoing = OutputBuffer(C.cast(buffer, C.c_void_p), len(buffer), 0)
                        previous = incoming.pos
                        remaining = self.check(self.lib.ZSTD_decompressStream(context, C.byref(outgoing), C.byref(incoming)))
                        consumed += incoming.pos - previous
                        if outgoing.pos:
                            if expected_bytes is not None and size + outgoing.pos > expected_bytes:
                                raise RuntimeError("decompressed stream exceeds previously measured length")
                            if output is not None and space_guard is not None and size >= next_guard:
                                space_guard(max(0, (expected_bytes or size + outgoing.pos) - size))
                                next_guard = size + 64 * 1024**2
                            payload = buffer.raw[:outgoing.pos]
                            digest.update(payload)
                            if output is not None:
                                output.write(payload)
                            size += outgoing.pos
                        if remaining == 0:
                            frames += 1
                        output_full = outgoing.pos == outgoing.size and remaining != 0
                        if incoming.pos == previous and outgoing.pos == 0 and incoming.pos < incoming.size:
                            raise RuntimeError("zstd stream made no progress")
                if output is not None:
                    output.flush()
                    os.fsync(output.fileno())
            if expected_bytes is not None and size != expected_bytes:
                raise RuntimeError("decompressed stream differs from previously measured length")
            return {"stream_test": "COMPLETE" if remaining == 0 else "INCOMPLETE_FINAL_FRAME",
                    "last_return_bytes_needed": remaining, "completed_frames": frames, "decompressed_bytes": size,
                    "compressed_bytes_consumed": consumed, "source_bytes": source.stat().st_size,
                    "decompressed_sha256": digest.hexdigest(), "output_written": destination is not None,
                    "wall_s": time.monotonic() - started,
                    "checksum_semantics": "libzstd validates frame checksums when present; valid compression does not imply a valid SQLite database"}
        finally:
            self.lib.ZSTD_freeDStream(context)


def sqlite_audit(path: Path) -> dict:
    result = {"path": str(path), "sqlite_version": sqlite3.sqlite_version,
              "mode": "mode=ro&immutable=1; PRAGMA query_only=ON; PRAGMA temp_store=MEMORY", "valid": False}
    if not path.is_file():
        return {**result, "error": "decompressed database is absent"}
    result["before"] = fingerprint(path)
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=10) as database:
            database.execute("PRAGMA query_only=ON")
            database.execute("PRAGMA temp_store=MEMORY")
            result["integrity_check"] = [row[0] for row in database.execute("PRAGMA integrity_check")]
            result["schema"] = list(database.execute("SELECT name, sql FROM sqlite_schema WHERE type='table' ORDER BY name"))
            result["message_count"] = database.execute("SELECT count(*) FROM messages").fetchone()[0]
            result["topic_counts"] = list(database.execute("SELECT topics.name, count(messages.id) FROM topics LEFT JOIN messages ON topics.id=messages.topic_id GROUP BY topics.id"))
            result["page_size"] = database.execute("PRAGMA page_size").fetchone()[0]
            result["page_count"] = database.execute("PRAGMA page_count").fetchone()[0]
            result["valid"] = result["integrity_check"] == ["ok"]
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result["after_sha256"] = sha256(path)
    result["database_unchanged_by_audit"] = result["before"]["sha256"] == result["after_sha256"]
    return result


def ros_reader_probe(bag: Path, source: Path, root: Path) -> dict:
    """Stage copies, never links, before invoking the installed read-only reader."""
    root.mkdir()
    shutil.copy2(bag / "metadata.yaml", root / "metadata.yaml")
    copied = root / source.name
    shutil.copy2(source, copied)
    report = {"cache": str(root), "staging": "copies_only", "compressed_copy_before": fingerprint(copied)}
    try:
        import rosbag2_py
        reader = rosbag2_py.SequentialCompressionReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(root), storage_id="sqlite3"),
                    rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"))
        report["open_succeeded"] = True
        report["topics"] = [topic.name for topic in reader.get_all_topics_and_types()]
        del reader
        gc.collect()
    except Exception as error:
        report.update(open_succeeded=False, error=f"{type(error).__name__}: {error}")
        gc.collect()
    report["compressed_copy_after_sha256"] = sha256(copied)
    report["sqlite"] = sqlite_audit(root / source.name.removesuffix(".zstd"))
    return report


def windows_c_free() -> int:
    executable = shutil.which("powershell.exe") or "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    probe = subprocess.run([executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::Write((Get-PSDrive -Name C).Free)"],
                           check=True, capture_output=True, timeout=30)
    value = int(probe.stdout.decode("ascii").strip())
    if value <= 0:
        raise OSError("Host Windows C free space could not be established")
    return value


def run(args) -> dict:
    import yaml  # Existing ROS installation dependency; this script installs nothing.

    bag, output = args.bag.resolve(strict=True), args.output.resolve()
    if not bag.is_dir() or output.is_relative_to(bag) or bag.is_relative_to(output):
        raise ValueError("Output must be a new directory outside the source bag and its ancestors")
    metadata_file = bag / "metadata.yaml"
    metadata = yaml.safe_load(metadata_file.read_text(encoding="utf-8"))["rosbag2_bagfile_information"]
    filenames = metadata["relative_file_paths"]
    if (metadata["storage_identifier"] != "sqlite3" or metadata["compression_format"] != "zstd"
            or str(metadata["compression_mode"]).lower() != "file" or len(filenames) != 1):
        raise ValueError("This diagnostic requires one SQLite file with FILE zstd compression")
    source = (bag / filenames[0]).resolve(strict=True)
    if source.parent != bag or not source.name.endswith(".db3.zstd"):
        raise ValueError("Unexpected bag filename or path escaping the source directory")
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing audit output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    decoder = ZstdStream()
    header = decoder.header(source)
    ext4_parent = args.ext4_temp_root.resolve(strict=True)
    capacities = {"ext4": shutil.disk_usage(ext4_parent)._asdict(),
                  "output_filesystem": shutil.disk_usage(output.parent)._asdict()}
    output.mkdir()
    drvfs = output / "cache_drvfs"
    drvfs.mkdir()
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "script_sha256": sha256(Path(__file__)),
              "source_before": fingerprint(source), "metadata_before": fingerprint(metadata_file),
              "metadata_message_count": metadata["message_count"], "zstd_header": header,
              "disk_space_before": capacities, "host_c_reserve_bytes": args.host_c_reserve_bytes,
              "cache_paths": {"drvfs": str(drvfs)},
              "cache_policy": "retained; only newly generated caches may later be removed after exact-path validation",
              "routes": {}, "ros_reader_probes": {}}
    try:
        if args.native_only:
            # The compression plugin writes only into this fresh D staging
            # directory; its output is kept for direct hash/SQLite comparison.
            report["scope"] = "native SequentialCompressionReader open/topics only, retained copied inputs and decompressed output"
            report["ros_reader_probes"]["drvfs"] = ros_reader_probe(bag, source, drvfs / "ros_compression_reader")
            print(json.dumps({"native_reader": report["ros_reader_probes"]["drvfs"]}), flush=True)
            return report
        if args.pass_control is not None:
            control_source = args.pass_control.resolve(strict=True)
            control = {"before": fingerprint(control_source), "header": decoder.header(control_source),
                       "scope": "known PASS control, stream/hash/frame scan only; no database written"}
            report["pass_control"] = control
            try:
                control["frame_scan"] = decoder.scan_frames(control_source)
                control["stream_only"] = decoder.decompress(control_source)
            finally:
                control["after"] = fingerprint(control_source)
                control["unchanged"] = control["before"] == control["after"]
            print(json.dumps({"pass_control": control}), flush=True)
        # Measure the complete stream without allocating a database on either filesystem.
        report["frame_scan"] = decoder.scan_frames(source)
        report["stream_only"] = decoder.decompress(source)
        expected = report["stream_only"]["decompressed_bytes"]
        print(json.dumps({"stream_only": report["stream_only"]}), flush=True)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if args.stream_only:
            report["scope"] = "stream-only: no database allocation, no SQLite/ROS reader probes"
            return report
        reserve = args.host_c_reserve_bytes

        def drive_guard(remaining):
            if shutil.disk_usage(drvfs).free < remaining + reserve:
                raise OSError("D output filesystem no longer has space for remaining measured bytes plus reserve")

        # D is first, regardless of the misleading virtual capacity reported by ext4 df.
        routes = [("drvfs", drvfs, drive_guard)]
        drive_guard(expected)
        for label, directory, guard in routes:
            destination = directory / source.name.removesuffix(".zstd")
            route = {"cache": str(directory)}
            try:
                route["zstd"] = decoder.decompress(source, destination, expected, guard)
                route["matches_stream_only_sha256"] = route["zstd"]["decompressed_sha256"] == report["stream_only"]["decompressed_sha256"]
                route["sqlite"] = sqlite_audit(destination)
            except Exception as error:
                route["error"] = f"{type(error).__name__}: {error}"
            report["routes"][label] = route
            print(json.dumps({"completed_route": label, "zstd": route.get("zstd"),
                              "sqlite_valid": route.get("sqlite", {}).get("valid"),
                              "error": route.get("error") or route.get("sqlite", {}).get("error")}), flush=True)
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        # A second route may write ext4 only after the real Windows backing drive
        # has been measured. Its admission check and 64 MiB guards use host C.
        try:
            report["host_c_free_before_ext4"] = windows_c_free()
            if args.skip_ext4:
                report["routes"]["ext4"] = {"skipped": "explicit --skip-ext4"}
            elif report["stream_only"]["stream_test"] != "COMPLETE":
                report["routes"]["ext4"] = {"skipped": "source zstd stream is incomplete; another filesystem cannot restore absent frame bytes"}
            elif report["host_c_free_before_ext4"] < expected + reserve + 128 * 1024**2:
                report["routes"]["ext4"] = {"skipped": "measured database plus 2 GiB reserve and 128 MiB allocation margin exceeds real host C free space",
                                            "expected_database_bytes": expected}
            else:
                def ext4_guard(remaining):
                    free = windows_c_free()
                    if free < remaining + reserve + 128 * 1024**2:
                        raise OSError("host C free space no longer fits remaining measured bytes plus reserve/allocation margin")
                ext4_guard(expected)
                ext4 = Path(tempfile.mkdtemp(prefix="uav_bag_integrity_", dir=ext4_parent))
                report["cache_paths"]["ext4"] = str(ext4)
                route = {"cache": str(ext4), "guard_interval_bytes": 64 * 1024**2}
                report["routes"]["ext4"] = route
                destination = ext4 / source.name.removesuffix(".zstd")
                route["zstd"] = decoder.decompress(source, destination, expected, ext4_guard)
                route["matches_stream_only_sha256"] = route["zstd"]["decompressed_sha256"] == report["stream_only"]["decompressed_sha256"]
                route["sqlite"] = sqlite_audit(destination)
            report["host_c_free_after_ext4"] = windows_c_free()
        except Exception as error:
            report["routes"].setdefault("ext4", {})["error"] = f"{type(error).__name__}: {error}"
        print(json.dumps({"completed_route": "ext4", "result": report["routes"]["ext4"]}), flush=True)
        all_valid = all(route.get("sqlite", {}).get("valid") is True for route in report["routes"].values())
        if args.ros_reader_probes and all_valid:
            # The ROS plugin does not expose a 64 MiB output guard. Keep any
            # optional additional decompression on D, never the host C VHD.
            drive_guard(expected + source.stat().st_size)
            report["ros_reader_probes"]["drvfs"] = ros_reader_probe(bag, source, drvfs / "ros_compression_reader")
            report["ros_reader_probes"]["ext4"] = {"skipped": "ROS plugin has no enforceable streaming host C free-space guard"}
        else:
            report["ros_reader_probe_scope"] = "not requested" if not args.ros_reader_probes else "skipped: independent SQLite already invalid; repeating the ROS reader is unnecessary to localize the payload"
    except Exception as error:
        report["fatal_error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["source_after"] = fingerprint(source)
        report["metadata_after"] = fingerprint(metadata_file)
        report["source_unchanged"] = report["source_before"] == report["source_after"]
        report["metadata_unchanged"] = report["metadata_before"] == report["metadata_after"]
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bag", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ext4-temp-root", type=Path, default=Path("/tmp"))
    parser.add_argument("--ros-reader-probes", action="store_true")
    parser.add_argument("--skip-ext4", action="store_true")
    parser.add_argument("--host-c-reserve-bytes", type=int, default=2 * 1024**3)
    parser.add_argument("--pass-control", type=Path, help="Known PASS compressed file; only scan/hash its decoded stream")
    parser.add_argument("--stream-only", action="store_true", help="Do not allocate any decompressed database")
    parser.add_argument("--native-only", action="store_true", help="Only probe installed ROS compression reader on fresh D copies")
    arguments = parser.parse_args()
    result = run(arguments)
    print(json.dumps({"report": str(arguments.output.resolve()), "source_unchanged": result["source_unchanged"],
                      "metadata_unchanged": result["metadata_unchanged"], "cache_paths": result["cache_paths"]}), flush=True)
