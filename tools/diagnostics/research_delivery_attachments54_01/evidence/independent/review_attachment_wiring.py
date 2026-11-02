"""Independent Windows synthetic regression and small-source pin receipt."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path("D:/基于yolo和卡尔曼滤波")
OUT = Path(__file__).resolve().parent
FILES = (
    "scripts/build_acceptance_dashboard.py", "scripts/build_reliability_v4_report.py",
    "tests/test_acceptance_dashboard_v4.py", "tests/test_reliability_v4_report.py",
)


def pin(path):
    assert path.is_file() and path.stat().st_size <= 1024 ** 2
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    before = {name: pin(ROOT / name) for name in FILES}
    for name in FILES:
        ast.parse((ROOT / name).read_text(encoding="utf-8-sig"), feature_version=(3, 10))
    command = [sys.executable, "-X", "utf8", "-B", "-m", "unittest", "-v",
               "tests.test_acceptance_dashboard_v4", "tests.test_reliability_v4_report"]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    started = datetime.now(timezone.utc).isoformat()
    run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                         encoding="utf-8", errors="strict", check=False, timeout=180)
    finished = datetime.now(timezone.utc).isoformat()
    after = {name: pin(ROOT / name) for name in FILES}
    assert before == after, "Reviewed source changed during regression"
    log = OUT / "independent_unittest01.log"
    with log.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(run.stdout)
        stream.write(run.stderr)
    receipt = {"schema_version": 1, "kind": "INDEPENDENT_ATTACHMENT_WIRING_WINDOWS_SYNTHETIC_REVIEW",
        "started_utc": started, "finished_utc": finished, "command": command, "cwd": str(ROOT),
        "exit_code": run.returncode, "source_before": before, "source_after": after,
        "source_unchanged": True, "python310_ast": "PASS", "log": pin(log), "reviewer": pin(Path(__file__)),
        "scope": "Synthetic saved JSON and document blocks only; no actual experiment or report build",
        "limitations": ["No WSL/ROS/PX4/Gazebo/native process started.",
            "No original bag, raw JSONL, telemetry, model payload or actual large report was read.",
            "Attachment validity is bounded saved-source consistency, not independent semantic re-evaluation.",
            "No original engineering verdict, formal metadata, trial or package was changed."]}
    target = OUT / "independent_review01.json"
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(run.stdout)
    print(run.stderr)
    print(json.dumps({"receipt": pin(target), "exit_code": run.returncode, "source_unchanged": True}, ensure_ascii=False))
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
