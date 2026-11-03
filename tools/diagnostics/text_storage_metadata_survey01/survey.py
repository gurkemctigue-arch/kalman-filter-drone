"""Bounded Windows metadata-only survey of historical project result text.

Never opens payload contents, follows reparse points, changes file attributes,
compresses/deletes files, invokes WSL, or touches VHD files. Writes one new report.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "results"
EXTENSIONS = {".jsonl", ".log", ".json", ".csv", ".yaml", ".yml", ".txt", ".md", ".html", ".htm", ".xml", ".sdf"}
SKIP_COMPONENTS = {"rosbag", "rosbag_raw", "rosbag_work", "rosbag_tmp", "models", "weights", "videos", "video", "frames", "images", "rgb_frames", "__pycache__", ".git", "node_modules"}
SKIP_TOP = {"project_progress", "monitor_humble54_probe02_owner04"}
MAX_SECONDS, MAX_DIRECTORIES, MAX_ENTRIES = 50.0, 30000, 250000


def utc():
    return datetime.now(timezone.utc).isoformat()


def wide(path):
    text = str(path)
    return text if text.startswith("\\\\?\\") else "\\\\?\\" + text


class StandardInfo(ctypes.Structure):
    _fields_ = [("allocation", ctypes.c_longlong), ("end_of_file", ctypes.c_longlong),
                ("links", wintypes.DWORD), ("delete_pending", ctypes.c_ubyte), ("directory", ctypes.c_ubyte)]


class API:
    def __init__(self):
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.k.GetCompressedFileSizeW.restype = wintypes.DWORD
        self.k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.k.CreateFileW.restype = wintypes.HANDLE
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.k.CloseHandle.restype = wintypes.BOOL
        self.k.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        self.k.GetFileInformationByHandleEx.restype = wintypes.BOOL
        self.k.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR, wintypes.DWORD]
        self.k.GetVolumeInformationW.restype = wintypes.BOOL
        self.k.GetDiskFreeSpaceExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong),
            ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong)]
        self.k.GetDiskFreeSpaceExW.restype = wintypes.BOOL

    def volume(self):
        label, filesystem = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
        serial, maximum, flags = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
        if not self.k.GetVolumeInformationW("D:\\", label, 261, ctypes.byref(serial), ctypes.byref(maximum),
                                            ctypes.byref(flags), filesystem, 261):
            raise ctypes.WinError(ctypes.get_last_error())
        available, total, free = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
        if not self.k.GetDiskFreeSpaceExW("D:\\", ctypes.byref(available), ctypes.byref(total), ctypes.byref(free)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"filesystem": filesystem.value, "label": label.value, "flags": flags.value,
                "file_compression_supported": bool(flags.value & 0x10),
                "entire_volume_compressed": bool(flags.value & 0x8000),
                "bytes_total": total.value, "bytes_available": available.value, "bytes_free": free.value,
                "sampled_utc": utc()}

    def storage(self, path):
        high = wintypes.DWORD()
        ctypes.set_last_error(0)
        low = self.k.GetCompressedFileSizeW(wide(path), ctypes.byref(high))
        if low == 0xffffffff and ctypes.get_last_error() != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        reported = (high.value << 32) | low
        # FILE_READ_ATTRIBUTES only; sharing READ|WRITE|DELETE. No data access.
        handle = self.k.CreateFileW(wide(path), 0x80, 7, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            value = StandardInfo()
            if not self.k.GetFileInformationByHandleEx(handle, 1, ctypes.byref(value), ctypes.sizeof(value)):
                raise ctypes.WinError(ctypes.get_last_error())
            return reported, value.allocation, value.links, value.end_of_file
        finally:
            self.k.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ValueError("Windows and a new output required")
    api = API()
    report = {"scope": "BOUNDED_WINDOWS_RESULT_TEXT_METADATA_ONLY_NOT_COMPRESSION_TEST", "started_utc": utc(),
              "source": {"path": str(Path(__file__).resolve()), "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "root": str(RESULTS), "volume_before": api.volume(), "contents_read": False,
              "wsl_called": False, "attributes_changed": False, "files_compressed_or_deleted": False,
              "vhd_touched": False, "limits": {"seconds": MAX_SECONDS, "directories": MAX_DIRECTORIES, "entries": MAX_ENTRIES},
              "exclusions": {"components": sorted(SKIP_COMPONENTS), "top_level": sorted(SKIP_TOP),
                  "name_fragments_any_depth": ["probe02", "owner04", "followon05", "final55"],
                  "all_reparse_points": True, "candidate_minimum_age_hours": 24,
                  "candidate_minimum_logical_bytes": 1048576},
              "allocation_basis": "FileStandardInfo.AllocationSize via read-attributes-only handle; excludes shared filesystem metadata. GetCompressedFileSizeW is retained separately and can equal logical bytes for uncompressed files.",
              "errors": [], "skipped_directories": [], "scan_counts": defaultdict(int)}
    began, cutoff = time.monotonic(), time.time() - 86400
    stack, rows, ids = [RESULTS], [], set()
    reason = "COMPLETE_WITH_DECLARED_EXCLUSIONS"
    while stack:
        if (time.monotonic() - began >= MAX_SECONDS or report["scan_counts"]["directories"] >= MAX_DIRECTORIES
                or report["scan_counts"]["entries"] >= MAX_ENTRIES):
            reason = "BOUNDED_PARTIAL_SURVEY"
            break
        directory = stack.pop()
        report["scan_counts"]["directories"] += 1
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    report["scan_counts"]["entries"] += 1
                    if time.monotonic() - began >= MAX_SECONDS or report["scan_counts"]["entries"] >= MAX_ENTRIES:
                        reason = "BOUNDED_PARTIAL_SURVEY"
                        break
                    relative = Path(entry.path).relative_to(RESULTS)
                    parts = [p.lower() for p in relative.parts]
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        attrs = getattr(stat, "st_file_attributes", 0)
                        if attrs & 0x400:
                            report["scan_counts"]["reparse_points_skipped"] += 1
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if (parts[0] in SKIP_TOP or entry.name.lower() in SKIP_COMPONENTS
                                    or any(s in p for p in parts for s in ("probe02", "owner04", "followon05", "final55"))):
                                if len(report["skipped_directories"]) < 300:
                                    report["skipped_directories"].append(relative.as_posix())
                                report["scan_counts"]["directories_excluded"] += 1
                            else:
                                stack.append(Path(entry.path))
                            continue
                        extension = Path(entry.name).suffix.lower()
                        if extension not in EXTENSIONS:
                            report["scan_counts"]["non_text_files_not_opened"] += 1
                            continue
                        if stat.st_mtime >= time.time() - 7200:
                            report["scan_counts"]["recent_text_files_excluded"] += 1
                            continue
                        identity = (stat.st_dev, stat.st_ino)
                        if stat.st_ino and identity in ids:
                            report["scan_counts"]["hardlink_duplicates_skipped"] += 1
                            continue
                        if stat.st_ino:
                            ids.add(identity)
                        stored, allocated, links, eof = api.storage(Path(entry.path))
                        if eof != stat.st_size:
                            report["scan_counts"]["changing_size_files_excluded"] += 1
                            continue
                        compressed, sparse, encrypted = bool(attrs & 0x800), bool(attrs & 0x200), bool(attrs & 0x4000)
                        rows.append({"path": relative.as_posix(), "version": relative.parts[0], "extension": extension,
                                     "basename": entry.name, "logical_bytes": stat.st_size,
                                     "compressed_file_size_api_bytes": stored, "allocated_bytes": allocated,
                                     "compressed": compressed, "sparse": sparse, "encrypted": encrypted,
                                     "hardlinks": links, "mtime_ns": stat.st_mtime_ns,
                                     "historical_uncompressed_candidate": (not compressed and not sparse and not encrypted
                                         and links == 1 and stat.st_size >= 1048576 and stat.st_mtime < cutoff)})
                    except OSError as error:
                        if len(report["errors"]) < 100:
                            report["errors"].append({"path": relative.as_posix(), "error": str(error)})
        except OSError as error:
            if len(report["errors"]) < 100:
                report["errors"].append({"path": str(directory.relative_to(RESULTS)), "error": str(error)})
    def aggregate(selected, key):
        groups = {}
        for row in selected:
            name = row[key]
            group = groups.setdefault(name, {"group": name, "files": 0, "logical_bytes": 0,
                "allocated_bytes": 0, "compressed_file_size_api_bytes": 0, "already_compressed_files": 0})
            group["files"] += 1
            for field in ("logical_bytes", "allocated_bytes", "compressed_file_size_api_bytes"):
                group[field] += row[field]
            group["already_compressed_files"] += row["compressed"]
        return sorted(groups.values(), key=lambda row: row["allocated_bytes"], reverse=True)
    candidates = [row for row in rows if row["historical_uncompressed_candidate"]]
    report.update(status=reason, elapsed_s=time.monotonic() - began, pending_directories=len(stack),
                  text_files_observed=len(rows), candidate_files=len(candidates),
                  totals={field: sum(row[field] for row in rows) for field in ("logical_bytes", "allocated_bytes", "compressed_file_size_api_bytes")},
                  candidate_totals={field: sum(row[field] for row in candidates) for field in ("logical_bytes", "allocated_bytes")},
                  by_extension=aggregate(rows, "extension"), by_version=aggregate(rows, "version"),
                  candidate_by_extension=aggregate(candidates, "extension"), candidate_by_version=aggregate(candidates, "version"),
                  candidate_by_basename=aggregate(candidates, "basename")[:30],
                  largest_uncompressed_candidates=sorted(candidates, key=lambda row: row["allocated_bytes"], reverse=True)[:60],
                  volume_after=api.volume(), finished_utc=utc(),
                  claim_boundary="Metadata identifies an upper pool for optional reversible transparent compression. No compression ratio or reclaimable capacity was measured, and no sufficiency for formal280 is asserted.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": reason, "elapsed_s": report["elapsed_s"], "text_files": len(rows),
                      "candidate_files": len(candidates), "candidate_allocated_bytes": report["candidate_totals"]["allocated_bytes"],
                      "report": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
