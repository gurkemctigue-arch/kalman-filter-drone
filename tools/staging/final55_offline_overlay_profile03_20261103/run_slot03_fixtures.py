"""Run slot03 Windows small-evidence tests; no native or chain execution."""
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
        raise SystemExit("Windows small metadata tests only")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-stem", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"slot03_windows[0-9]{2}", args.output_stem):
        raise SystemExit("Explicit bounded evidence stem required")
    here = Path(__file__).resolve().parent
    receipt = here / (args.output_stem + "_receipt.json")
    snapshots = here / (args.output_stem + "_sources")
    patterns = ("test_historical_unknown_slot03.py", "test_owner_closure_base03.py")
    logs = [here / (args.output_stem + "_" + str(n + 1) + ".log") for n in range(len(patterns))]
    if receipt.exists() or snapshots.exists() or any(path.exists() for path in logs):
        raise SystemExit("Fresh outputs only; no overwrite or automatic repeat")
    sources = [here / name for name in ("validate_owner_closure.py", *patterns, Path(__file__).name)]
    before = {p.name: sha(p) for p in sources}
    snapshots.mkdir()
    for p in sources:
        (snapshots / p.name).write_bytes(p.read_bytes())
    started, groups = utc(), []
    for pattern, log in zip(patterns, logs):
        command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(here), "-p", pattern, "-v"]
        with log.open("xb") as handle:
            child = subprocess.run(command, cwd=here, stdout=handle, stderr=subprocess.STDOUT, check=False)
        count = re.search(rb"Ran (\d+) tests? in ", log.read_bytes())
        groups.append({"pattern": pattern, "command": command, "exit_code": child.returncode,
                       "test_count": int(count.group(1)) if count else None, "log": log.name, "log_sha256": sha(log)})
    after = {p.name: sha(p) for p in sources}
    passed = before == after and all(g["exit_code"] == 0 and g["test_count"] is not None for g in groups)
    value = {"scope": "WINDOWS_SMALL_ORIGINAL_SLOT_METADATA_AND_TAMPER_TESTS_ONLY", "status": "PASS" if passed else "FAIL",
             "started_utc": started, "finished_utc": utc(), "groups": groups,
             "test_count": sum(g["test_count"] or 0 for g in groups), "sources_before": before, "sources_after": after,
             "source_snapshots": {p.name: sha(snapshots / p.name) for p in sources},
             "wsl_or_native_called": False, "bags_models_images_read": False, "production_continuation_launched": False}
    with receipt.open("x", encoding="utf8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    print(json.dumps(value))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
