"""Run the existing read-only extractor on the actual probe02 dropout bag."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[3]
OUTPUT = REPO / 'results/diagnostics/humble54_probe02_dropout_review03'
EXTRACT = REPO / 'results/diagnostics/humble54_probe02_person_dropout_input_extract03'
SCRIPT = '''set -euo pipefail
tracking_repo="$1"
tracking_dev=/root/uav_tracking_fullplan_v4_humble54
bash /mnt/d/WSL/UAVHumble22-validation/check_humble54_native_idle02.sh
export HUMBLE22_PROJECT_ROOT="$tracking_dev"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export PYTHONDONTWRITEBYTECODE=1 STAGE1_TRANSIENT_DIR=/tmp TMPDIR=/tmp
source "$tracking_dev/scripts/humble22_env.sh"
bash "$tracking_dev/scripts/run_research_session.sh" "$tracking_repo/tools/diagnostics/humble54_dropout_gap01/extract_short_window.py" --source-root "$tracking_dev" --plan "$tracking_dev/results/reliability_v4_humble54_extension16_probe02_matrix/plan.json" --slot-id person_extension_dropout_seed004 --output "$tracking_repo/results/diagnostics/humble54_probe02_person_dropout_input_extract03"
'''

def utc():
    return datetime.now(timezone.utc).isoformat()

def main():
    assert not OUTPUT.exists() and not EXTRACT.exists(), 'No overwrite or retry'
    outer = json.loads((REPO / 'results/diagnostics/humble54_probe02_windows_owner05/terminal.json').read_text())
    assert outer['closure_verified'] is True and outer['status'] == 'STOPPED_FAULT'
    extractor = REPO / 'tools/diagnostics/humble54_dropout_gap01/extract_short_window.py'
    assert hashlib.sha256(extractor.read_bytes()).hexdigest() == '364156694a5db1777b7b3615614ae32b5cc128a7f8bbc09e213e1a168854fbf4'
    OUTPUT.mkdir()
    native_repo = '/mnt/' + REPO.drive[0].lower() + REPO.as_posix()[2:]
    command = ['wsl.exe', '--distribution', 'UAVHumble22', '--exec', 'bash', '-c', SCRIPT, '_', native_repo]
    receipt = {'kind': 'ACTUAL_PROBE02_READONLY_SHORT_INPUT_EXTRACTION', 'started_utc': utc(), 'command': command, 'original_results_changed': False}
    (OUTPUT / 'started.json').write_text(json.dumps(receipt, indent=2) + '\n')
    with (OUTPUT / 'stdout.log').open('xb') as stdout, (OUTPUT / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        receipt['returncode'] = child.wait()
    receipt['finished_utc'] = utc()
    receipt['status'] = 'EXTRACTION_COMPLETED_PENDING_REVIEW' if receipt['returncode'] == 0 else 'EXTRACTION_FAILED_PARTIAL_RETAINED'
    (OUTPUT / 'terminal.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
    return receipt['returncode']

if __name__ == '__main__':
    raise SystemExit(main())
