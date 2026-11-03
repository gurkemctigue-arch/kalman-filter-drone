"""Record Windows-only gate/outer contracts with no native process launch."""
from datetime import datetime, timezone
import argparse
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
        raise SystemExit("Windows-only contract fixtures")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-stem", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"windows_contracts[0-9]{2}", args.output_stem):
        raise SystemExit("Explicit bounded contract evidence stem required")
    here = Path(__file__).resolve().parent
    project = here.parents[2]
    sources = [here / "run_registered05.py", here / "test_registered05.py", Path(__file__).resolve(),
               project / "tools/experiment_orchestration/humble54_probe02_windows_owner05/start_owner05.py"]
    before = {p.relative_to(project).as_posix(): sha(p) for p in sources}
    log, receipt = here / (args.output_stem + ".log"), here / (args.output_stem + "_receipt.json")
    if log.exists() or receipt.exists():
        raise SystemExit("Fresh contract evidence required; never overwrite or rerun automatically")
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(here), "-p", "test_registered05.py", "-v"]
    started = utc()
    with log.open("xb") as handle:
        child = subprocess.run(command, cwd=project, stdout=handle, stderr=subprocess.STDOUT, check=False)
    finished = utc()
    after = {p.relative_to(project).as_posix(): sha(p) for p in sources}
    count = re.search(rb"Ran (\d+) tests? in ", log.read_bytes())
    passed = child.returncode == 0 and before == after and count is not None
    value = {"scope": "WINDOWS_PURE_GATE_AND_OUTER_CONTRACTS_ONLY_NO_NATIVE_RUN",
             "status": "PASS" if passed else "FAIL", "started_utc": started, "finished_utc": finished,
             "command": command, "exit_code": child.returncode, "test_count": int(count.group(1)) if count else None,
             "sources_before": before, "sources_after": after, "log_sha256": sha(log),
             "python_version": sys.version, "platform": sys.platform,
             "actual_prefix_registered": False, "production_gate_executed": False,
             "wsl_or_simulation_called": False, "claim_boundary": "Prepared source contracts only. No actual closed-chain/profile instance is configured or approved."}
    with receipt.open("x", encoding="utf8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    print(json.dumps(value))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
