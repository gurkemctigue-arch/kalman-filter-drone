"""Bounded Linux resource observation; never signals or changes a process.

Run separately from the immutable simulation checkout. Each JSONL sample reads
only small /proc files and records scheduling gaps, memory, swap and PSI.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time


def sample(previous):
    current = time.monotonic()
    result = {"utc": datetime.now(timezone.utc).isoformat(), "monotonic_s": current,
              "sample_gap_wall_s": None if previous is None else current - previous}
    for name in ("uptime", "loadavg", "meminfo", "vmstat", "stat",
                 "pressure/cpu", "pressure/memory", "pressure/io"):
        path = Path("/proc") / name
        try:
            value = path.read_text(encoding="ascii")
            if name == "stat":
                value = "\n".join(line for line in value.splitlines()
                                  if line.startswith(("cpu ", "ctxt ", "btime ", "processes ", "procs_")))
            elif name == "vmstat":
                value = "\n".join(line for line in value.splitlines()
                                  if line.startswith(("pswpin ", "pswpout ", "oom_kill ", "pgmajfault ")))
            result[name] = value
        except OSError as error:
            result[name] = {"read_error": str(error)}
    return result, current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=600.)
    parser.add_argument("--interval", type=float, default=1.)
    args = parser.parse_args()
    if not Path("/proc/meminfo").is_file() or not 1 <= args.duration <= 3600 or not .5 <= args.interval <= 30:
        parser.error("Linux /proc and bounded duration/interval are required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    previous = None
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "READ_ONLY_OBSERVER_STARTED", "duration_s": args.duration,
            "interval_s": args.interval, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "utc": datetime.now(timezone.utc).isoformat()}, allow_nan=False) + "\n")
        while time.monotonic() - started < args.duration:
            value, previous = sample(previous)
            handle.write(json.dumps(value, allow_nan=False) + "\n")
            handle.flush()
            time.sleep(args.interval)
        handle.write(json.dumps({"event": "BOUNDED_OBSERVER_COMPLETED", "elapsed_wall_s": time.monotonic() - started}) + "\n")


if __name__ == "__main__":
    main()
