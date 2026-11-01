"""Run the complete local suite once and retain its original output bytes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

root = Path.cwd().resolve()
external = Path('D:/WSL/UAVHumble22-validation')
log = external / 'humble47_full_windows_suite01.log'
receipt = external / 'humble47_full_windows_suite01_receipt.json'
assert not log.exists() and not receipt.exists()
names = ['tests/test_car_surface_registration.py', 'scripts/run_stage1_trial.py',
         'scripts/run_reliability_v4.py', 'scripts/build_reliability_v4_probe_gate.py',
         'ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/flight_supervisor.py']
def hashes():
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
before = hashes()
assert before[names[0]] == '35c49e0fa21a9bbafc294550668c99c5ea251c4378e8bb338c89bd4b0e2d1e2c'
command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v']
environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                   OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
started_utc = datetime.now(timezone.utc).isoformat()
started = time.monotonic()
with log.open('xb') as stream:
    result = subprocess.run(command, cwd=root, env=environment, stdout=stream, stderr=subprocess.STDOUT)
after = hashes()
text = log.read_text(encoding='utf-8', errors='replace')
counts = re.findall(r'(?m)^Ran ([0-9]+) tests in ([0-9.]+)s$', text)
value = {'scope': 'ACTUAL_COMPLETE_WINDOWS_SUITE_NOT_NATIVE_BUILD_OR_FLIGHT_ACCEPTANCE',
         'started_utc': started_utc, 'finished_utc': datetime.now(timezone.utc).isoformat(),
         'elapsed_wall_s': time.monotonic()-started, 'command': command, 'returncode': result.returncode,
         'python_version': sys.version, 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
         'counts_from_original_footer': counts, 'sources_before': before, 'sources_after': after,
         'sources_unchanged': before == after,
         'status': 'PASS' if result.returncode == 0 and before == after else 'FAIL'}
with receipt.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(value, stream, indent=2); stream.write('\n')
print(json.dumps(value, indent=2))
raise SystemExit(result.returncode if before == after else 2)
