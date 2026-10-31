"""One real no-SITL archive pressure run, on a new owned clone only.

The original failed source40 attempt is never modified or regraded. All live
progress/check evidence is tmpfs; final diagnostics publish only after native
observers close. Run from the clean Humble41 overlay with no other heavy task.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback

EXTERNAL = Path('/mnt/d/WSL/UAVHumble22-validation')
ROOT = Path('/root/uav_tracking_fullplan_v4_humble41')
ORIGINAL = Path('/root/uav_tracking_bag_spool/trial_ygxppdk1')
OLD_ROOT = Path('/root/uav_tracking_fullplan_v4_humble40')
OLD_SLOT = OLD_ROOT / 'results/reliability_v4_humble40_probe01_seed004_matrix/slots/person_stage3_midpoint_seed004.json'
OLD_SLOT_SHA = '605c7cf97ee8745c30068a7ed324753f3468c4bb8fb11642de2ef3edd4f52ef1'
COLLECTOR_SHA = 'f174ec21ebf962f156d76f8d35f802eebf318163555815527a3e2227b914f180'
WALL_BUDGET = 2400.


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=True, allow_nan=False, indent=2)
        stream.write('\n')


def original_stat():
    result = {}
    for relative in ('owned_spool.json', 'rosbag/metadata.yaml', 'rosbag/rosbag_0.db3',
                     'archive/rosbag_0.db3.zstd'):
        path = ORIGINAL / relative
        item = path.stat()
        if path.is_symlink() or not path.is_file():
            raise ValueError('Original must remain an ordinary retained file')
        result[relative] = {'bytes': item.st_size, 'mtime_ns': item.st_mtime_ns,
                            'inode': item.st_ino, 'device': item.st_dev}
    return result


def worker(clone, destination, receipt):
    # The marker is created by create_recording_spool for this new diagnostic.
    clone, destination, receipt = Path(clone), Path(destination), Path(receipt)
    trial = ROOT / 'results/freeze_validation/observer_archive_pressure01'
    if (clone == ORIGINAL or clone.parent != ORIGINAL.parent or
            not clone.name.startswith('trial_') or destination != trial / 'rosbag'
            or not receipt.is_relative_to(Path('/dev/shm'))):
        raise ValueError('Diagnostic clone/destination escaped fixed boundaries')
    marker = json.loads((clone / 'owned_spool.json').read_text(encoding='utf-8'))
    if Path(marker['trial']).resolve() != trial.resolve():
        raise ValueError('Diagnostic owner marker differs')
    from uav_tracking.recording_archive import finalize_recording
    started = time.monotonic()
    shutil.copytree(ORIGINAL / 'rosbag', clone / 'rosbag')
    copied = time.monotonic()
    result = finalize_recording(clone, destination, 0)
    write_new(receipt, {'status': 'PASS', 'started_utc_scope': 'clone copy then unchanged actual finalize_recording',
        'copy_wall_s': copied - started, 'total_wall_s': time.monotonic() - started,
        'original_spool': str(ORIGINAL), 'diagnostic_clone': str(clone), 'result': result,
        'original_attempt_regraded': False})
    return 0


def main(args):
    if os.environ.get('WSL_DISTRO_NAME') != 'UAVHumble22' or not ROOT.is_dir():
        raise ValueError('Actual Humble41 root is required')
    if sha(ROOT / 'scripts/observe_runtime_health.py') != COLLECTOR_SHA:
        raise ValueError('Frozen collector source differs')
    summary_path = ROOT / 'results/freeze_validation/build_validation_summary.json'
    if sha(summary_path) != args.build_summary_sha256:
        raise ValueError('Actual cold-build summary differs')
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    if summary.get('status') != 'PASS':
        raise ValueError('Actual cold-build validation has not passed')
    owner_path = EXTERNAL / 'local_runtime_observer41.py'
    if sha(owner_path) != args.owner_sha256:
        raise ValueError('Explicit external owner bytes differ')
    spec = importlib.util.spec_from_file_location('pressure41_runner', ROOT / 'scripts/run_reliability_v4.py')
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)
    if runner.simulation_processes():
        raise ValueError('A simulator, recorder, or flight graph is already active')
    sys.path.insert(0, str(EXTERNAL))
    owner = importlib.import_module('local_runtime_observer41')
    trial = ROOT / 'results/freeze_validation/observer_archive_pressure01'
    trial.mkdir(exist_ok=False)
    local = Path(tempfile.mkdtemp(prefix='uav_tracking_root41_pressure_', dir='/dev/shm'))
    local.chmod(0o700)
    before = original_stat()
    old_slot = json.loads(OLD_SLOT.read_text(encoding='utf-8'))
    original_owner = json.loads((ORIGINAL / 'owned_spool.json').read_text(encoding='utf-8'))
    original_trial = OLD_ROOT / 'results/reliability_v4_humble40_probe01_person_stage3_midpoint_seed004'
    if (sha(OLD_SLOT) != OLD_SLOT_SHA or old_slot.get('status') != 'INFRASTRUCTURE_ERROR'
            or old_slot.get('infrastructure_stop') is not True
            or Path(original_owner['trial']).resolve() != original_trial.resolve()):
        raise ValueError('Original retained failed slot/spool ownership differs')
    from uav_tracking.recording_archive import create_recording_spool
    clone = create_recording_spool(trial)
    started = time.monotonic()
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--archive-worker',
               str(clone), str(trial / 'rosbag'), str(local / 'archive_worker.json')]
    record = {'schema_version': 1, 'scope': 'ACTUAL_NO_SITL_ARCHIVE_PRESSURE_DIAGNOSTIC_ONLY',
        'started_utc': utc(), 'root': str(ROOT), 'original_spool': str(ORIGINAL),
        'diagnostic_clone': str(clone), 'local_evidence': str(local), 'command': command,
        'source': {'script': sha(__file__), 'collector': COLLECTOR_SHA,
                   'owner': args.owner_sha256, 'build_summary': args.build_summary_sha256},
        'original_failed_slot': {'path': str(OLD_SLOT), 'sha256': OLD_SLOT_SHA,
                                 'status': old_slot['status']},
        'original_spool_owner': original_owner,
        'original_stat_before': before, 'original_attempt_status': 'INFRASTRUCTURE_ERROR_RETAINED',
        'original_attempt_regraded': False, 'no_simulator_started': True,
        'formal_trials_executed': 0, 'pressure_workload_wall_budget_s': WALL_BUDGET}
    check_count, max_age, max_latency, process = 0, 0., 0., None
    error = None
    observer = owner.make_observer(trial / 'observer_driver', ROOT, archive_wall_budget_s=1800.)
    try:
        with observer:
            with (local / 'archive_worker_console.log').open('xb') as console, \
                    (local / 'checks.jsonl').open('x', encoding='utf-8') as checks:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=console,
                    stderr=subprocess.STDOUT, start_new_session=True)
                while True:
                    call_start = time.monotonic()
                    fresh = observer.check()
                    latency = time.monotonic() - call_start
                    check_count += 1
                    max_age = max(max_age, fresh['sample_age_wall_s'])
                    max_latency = max(max_latency, latency)
                    checks.write(json.dumps({'monotonic_s': time.monotonic(), 'check_latency_wall_s': latency,
                        'fresh': fresh}, allow_nan=False) + '\n')
                    checks.flush()
                    code = process.poll()
                    if code is not None:
                        if code != 0:
                            raise RuntimeError('Actual unchanged archive worker failed: ' + str(code))
                        break
                    if time.monotonic() - started > WALL_BUDGET:
                        raise TimeoutError('Diagnostic archive workload exceeded its explicit wall budget')
                    if (local / 'archive_worker_console.log').stat().st_size > 8 * 1024**2:
                        raise RuntimeError('Diagnostic console exceeded bounded local evidence budget')
                    time.sleep(.5)
            observer.check()
    except BaseException as caught:
        error = type(caught).__name__ + ':' + str(caught)
        (local / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        cleanup_actions = []
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            cleanup_actions.append('diagnostic_worker_SIGINT')
            try:
                process.wait(timeout=30.)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                cleanup_actions.append('diagnostic_worker_SIGKILL')
                process.wait(timeout=10.)
        if observer._finished is None:
            observer.finish(exception=True)
        after = original_stat()
        record.update(finished_utc=utc(), wall_s=time.monotonic() - started,
            original_stat_after=after, original_stat_unchanged=before == after,
            diagnostic_clone_retained=clone.exists(), observer=observer._finished,
            worker_exit_code=None if process is None else process.returncode,
            cleanup_actions=cleanup_actions, check_count=check_count,
            max_observer_sample_age_wall_s=max_age, max_check_latency_wall_s=max_latency,
            error=error, rosbag_published=(trial / 'rosbag/metadata.yaml').is_file())
        if error is None:
            try:
                record['observer_validation'] = owner.validate_observer_root(
                    observer._finished, trial / 'observer_driver', ROOT)
            except BaseException as caught:
                error = type(caught).__name__ + ':' + str(caught)
                record['error'] = error
        record['status'] = 'PASS' if (error is None and before == after and not cleanup_actions
            and record['worker_exit_code'] == 0 and record['rosbag_published']) else 'FAIL'
        # Native observer is already stopped. Diagnostic evidence stays retained
        # locally even if this separate closed-evidence archive fails.
        artifacts = {}
        for path in sorted(local.iterdir()):
            if not path.is_file() or path.is_symlink():
                raise ValueError('Unexpected local diagnostic artifact')
            destination = trial / path.name
            with path.open('rb') as src, destination.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            binding = {'bytes': path.stat().st_size, 'sha256': sha(path)}
            if destination.stat().st_size != binding['bytes'] or sha(destination) != binding['sha256']:
                raise ValueError('Diagnostic closed-evidence copy differs')
            artifacts[path.name] = binding
        record['diagnostic_artifacts'] = artifacts
        write_new(trial / 'execution_terminal.json', record)
    print(json.dumps({'status': record['status'], 'trial': str(trial), 'checks': check_count,
        'max_age_wall_s': max_age, 'max_check_latency_wall_s': max_latency, 'error': error}, ensure_ascii=True))
    return 0 if record['status'] == 'PASS' else 1


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--archive-worker':
        raise SystemExit(worker(*sys.argv[2:]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-sha256', required=True)
    parser.add_argument('--build-summary-sha256', required=True)
    raise SystemExit(main(parser.parse_args()))
