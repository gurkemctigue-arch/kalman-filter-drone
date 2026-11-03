"""Run inert Windows observer fixtures; never run the actual observer."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    if os.name != "nt":
        raise SystemExit("Windows inert fixtures only")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-stem", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"windows_fixtures[0-9]{2}", args.output_stem):
        raise SystemExit("Explicit bounded fresh evidence stem required")
    here = Path(__file__).resolve().parent
    log = here / (args.output_stem + ".log")
    receipt = here / (args.output_stem + "_receipt.json")
    snapshots = here / (args.output_stem + "_sources")
    if log.exists() or receipt.exists() or snapshots.exists():
        raise SystemExit("Fresh output required; no overwrite or automatic retry")
    sources = [here / name for name in ("wait_owner05_closure.py", "test_wait_owner05_closure.py", Path(__file__).name)]
    before = {p.name: sha(p) for p in sources}
    snapshots.mkdir()
    for p in sources:
        (snapshots / p.name).write_bytes(p.read_bytes())
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(here), "-p", "test_wait_owner05_closure.py", "-v"]
    started = utc()
    with log.open("xb") as handle:
        child = subprocess.run(command, cwd=here, stdout=handle, stderr=subprocess.STDOUT, check=False)
    finished = utc()
    after = {p.name: sha(p) for p in sources}
    count = re.search(rb"Ran (\d+) tests? in ", log.read_bytes())
    passed = child.returncode == 0 and before == after and count is not None
    value = {"scope": "INERT_WINDOWS_SYNTHETIC_OBSERVER_FIXTURES_ONLY",
             "status": "PASS" if passed else "FAIL", "started_utc": started, "finished_utc": finished,
             "command": command, "exit_code": child.returncode, "test_count": int(count.group(1)) if count else None,
             "sources_before": before, "sources_after": after, "source_snapshots": {p.name: sha(snapshots / p.name) for p in sources},
             "log_sha256": sha(log), "platform": sys.platform, "python_version": sys.version,
             "actual_observer_launched": False, "actual_windows_handles_acquired": False, "wsl_or_native_called": False,
             "claim_boundary": "Preparation was superseded by actual owner05 fault before any observer launch. Only fake API contracts were exercised."}
    with receipt.open("x", encoding="utf8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    print(json.dumps(value))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
