"""Explicit Windows metadata query for the isolated lossless22 benchmark."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[3]
SURVEY = ROOT / "tools/diagnostics/text_storage_metadata_survey01/survey.py"
SURVEY_SHA = "a4a88958d2f5075dc2cc13db01e35ea2a595f7513a3f8be39c1247da47f91a6b"


class Memory(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
        (name, ctypes.c_ulonglong) for name in
        ("total_phys", "available_phys", "total_pagefile", "available_pagefile",
         "total_virtual", "available_virtual", "available_extended_virtual")]


def query():
    if os.name != "nt":
        raise RuntimeError("Windows metadata query only")
    import winreg
    raw = SURVEY.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SURVEY_SHA:
        raise ValueError("Original metadata API source changed")
    module = types.ModuleType("lossless22_original_windows_metadata_api")
    module.__file__ = str(SURVEY)
    exec(compile(raw, str(SURVEY), "exec"), module.__dict__)
    api = module.API()
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    api.k.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(Memory)]
    api.k.GlobalMemoryStatusEx.restype = ctypes.c_int
    if not api.k.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise ctypes.WinError(ctypes.get_last_error())
    matches = []
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Lxss") as key:
        for index in range(winreg.QueryInfoKey(key)[0]):
            with winreg.OpenKey(key, winreg.EnumKey(key, index)) as distro:
                if winreg.QueryValueEx(distro, "DistributionName")[0] == "UAVHumble22":
                    base = str(winreg.QueryValueEx(distro, "BasePath")[0]).removeprefix("\\\\?\\")
                    matches.append(Path(base) / "ext4.vhdx")
    if len(matches) != 1:
        raise ValueError("Exactly one registry-backed UAVHumble22 VHD required")
    vhd = matches[0]
    if vhd.drive.upper() != "D:":
        raise ValueError("This fixed benchmark requires the registry-backed VHD on its reserved D volume")
    reported, allocation, links, logical = api.storage(vhd)
    return {"utc": datetime.now(timezone.utc).isoformat(),
            "host_available_memory_bytes": memory.available_phys,
            "host_total_memory_bytes": memory.total_phys,
            "D_volume": api.volume(), "vhd": {"path": str(vhd),
                "logical_bytes": logical, "allocated_bytes": allocation,
                "reported_compressed_bytes": reported, "links": links},
            "scope": "MEMORY_REGISTRY_AND_READ_ATTRIBUTES_ONLY_NO_VHD_PAYLOAD_READ"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="store_true")
    args = parser.parse_args()
    if not args.query:
        parser.error("An explicit --query is required")
    print(json.dumps(query(), ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
