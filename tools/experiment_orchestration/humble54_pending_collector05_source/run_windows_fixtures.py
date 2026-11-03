"""Run only Windows synthetic fixtures and preserve their actual output bytes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if os.name != "nt":
        raise SystemExit("Windows-only synthetic fixture runner")
    root = Path(__file__).resolve().parent
    sources = [root / name for name in (
        "collect_humble54_pending05.py", "test_collect_humble54_pending05.py", Path(__file__).name)]
    before = {path.name: sha(path) for path in sources}
    log = root / "windows_test01.log"
    receipt = root / "windows_test01_receipt.json"
    if log.exists() or receipt.exists():
        raise SystemExit("Fresh output files required; no overwrite or automatic rerun")
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(root),
               "-p", "test_collect_humble54_pending05.py", "-v"]
    started = utc()
    with log.open("xb") as handle:
        child = subprocess.run(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT, check=False)
    finished = utc()
    after = {path.name: sha(path) for path in sources}
    count = re.search(rb"Ran (\d+) tests? in ", log.read_bytes())
    passed = child.returncode == 0 and before == after and count is not None
    value = {
        "scope": "WINDOWS_SYNTHETIC_FAKE_CHILD_TESTS_ONLY_NOT_NATIVE_SIMULATION",
        "started_utc": started, "finished_utc": finished,
        "command": command, "python_version": sys.version, "platform": sys.platform,
        "exit_code": child.returncode, "test_count": int(count.group(1)) if count else None,
        "status": "PASS" if passed else "FAIL",
        "sources_before": before, "sources_after": after,
        "log": {"path": str(log), "sha256": sha(log)},
        "wsl_called": False, "ros_or_gazebo_started": False,
        "production_collection_invoked": False,
        "claim_boundary": "Fixture result only; production profile remains disabled and has no approved prefix."
    }
    with receipt.open("x", encoding="utf8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    print(json.dumps(value))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
