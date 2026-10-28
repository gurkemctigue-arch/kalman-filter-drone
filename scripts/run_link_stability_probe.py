"""One independent diagnostic flight, outside the frozen 166-slot ledger.

Use the frozen ROS environment. Live diagnostic logs stay on local ext4;
archive only small diagnostic files after every flight process has exited.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from run_guarded_full_plan import (exclusive_guard, idle_writer_window,
                                   read_plan, snapshot, verify_sources)
from run_full_plan_supplement import active_simulation_processes

MAIN = Path(__file__).resolve().parents[1]
FROZEN = Path('/root/uav_tracking_fullplan_v3')
PLAN_SHA = '58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28'
PROFILES = {
    'stage2_crossing': {
        'name': 'diagnostic_v3_car_crossing_memory_relief_20261027_v2',
        'audit': 'link_stability_probe_20261027_v2', 'stage': 2, 'class': 'car',
        'seed': 5, 'speed': '0.5122901694889702', 'mode': 'locked_target',
        'selection': 'middle', 'candidates': 3, 'scenario': 'crossing',
        'distance': '9.0', 'image': 640, 'threads': 4, 'occlusions': False,
    },
    'stage3_midpoint': {
        'name': 'diagnostic_v3_stage3_person_midpoint_link_20261027_v1',
        'audit': 'link_stability_probe_stage3_20261027_v1', 'stage': 3, 'class': 'person',
        'seed': 0, 'speed': '0.5344421851525049', 'mode': 'auto_unique',
        'selection': 'none', 'candidates': 2, 'scenario': 'parallel',
        'distance': '5.0', 'image': 320, 'threads': 2, 'occlusions': True,
    },
    'stage3_midpoint_seed001': {
        'name': 'diagnostic_v3_stage3_person_midpoint_seed001_link_20261027_v1',
        'audit': 'link_stability_probe_stage3_seed001_20261027_v1', 'stage': 3, 'class': 'person',
        'seed': 1, 'speed': '0.4634364244112401', 'mode': 'auto_unique',
        'selection': 'none', 'candidates': 2, 'scenario': 'parallel',
        'distance': '5.0', 'image': 320, 'threads': 2, 'occlusions': True,
    },
}


def now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)


def flight_argv(profile='stage2_crossing'):
    selected = PROFILES[profile]
    argv = [sys.executable, str(FROZEN / 'scripts/run_stage1_trial.py'),
            '--name', selected['name'], '--stage', str(selected['stage']),
            '--class', selected['class'], '--seed', str(selected['seed']),
            '--speed-mps', selected['speed'], '--condition', 'clean',
            '--command-mode', 'velocity', '--estimator-method', 'adaptive_kf',
            '--target-mode', selected['mode'], '--initial-select', selected['selection'],
            '--gimbal-mode', 'midpoint', '--initial-min-candidates', str(selected['candidates']),
            '--scenario-kind', selected['scenario'], '--duration', '43.0',
            '--desired-distance-m', selected['distance'], '--takeoff-height-m', '3.0',
            '--real-time-factor', '0.5', '--inference-image-size', str(selected['image']),
            '--inference-threads', str(selected['threads']), '--wall-timeout', '300.0',
            '--render-backend', 'egl']
    if selected['occlusions']:
        argv.extend(['--occlusions', '--reselect-after-loss'])
    return argv


def stop_owned(process):
    def signal_group(value):
        try:
            os.killpg(process.pid, value)
        except ProcessLookupError:
            pass

    if process.poll() is None:
        signal_group(signal.SIGINT)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            signal_group(signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                signal_group(signal.SIGKILL)
                process.wait(timeout=5)
    return process.returncode


def collect_lines(process, path, status):
    """Preserve CLI line receipts; they are not physics publication times."""
    try:
        with path.open('x', encoding='utf-8') as handle:
            for line in process.stdout:
                row = {'utc': now(), 'receipt_monotonic_ns': time.monotonic_ns(),
                       'cli_line': line.rstrip('\n')}
                encoded = json.dumps(row, ensure_ascii=False) + '\n'
                status['bytes'] += len(encoded.encode('utf-8'))
                if status['bytes'] > 16 * 1024**2:
                    status['limit_reached'] = True
                    # Keep draining bounded discarded lines; never backpressure Gazebo.
                    continue
                handle.write(encoded)
                handle.flush()
                status['lines'] += 1
    except Exception as error:
        status['error'] = f'{type(error).__name__}: {error}'


def execute(audit, profile='stage2_crossing'):
    selected = PROFILES[profile]
    trial_name = selected['name']
    if os.name != 'posix' or audit.exists() or (FROZEN / 'results' / trial_name).exists():
        raise ValueError('Linux and unused diagnostic/audit names are required; no retries/overwrite')
    if audit.is_relative_to(FROZEN.resolve()) or audit.is_relative_to((FROZEN / 'results').resolve()):
        raise ValueError('Diagnostic audit must remain outside the frozen source and results')
    with exclusive_guard(FROZEN), idle_writer_window(FROZEN):
        _, plan = read_plan(FROZEN, 'results/full_plan_research_v3', PLAN_SHA)
        verify_sources(FROZEN, plan)
        before = snapshot(FROZEN, plan)
        local = Path(tempfile.mkdtemp(prefix='tracking_link_probe_', dir='/tmp'))
        commands = {
            'ros_observer': [sys.executable, str(MAIN / 'scripts/observe_ros_link.py'),
                             '--output-dir', str(local / 'ros'), '--duration-wall-s', '720'],
            'linux_resources': [sys.executable, str(MAIN / 'scripts/watch_sim_resources.py'),
                                '--output', str(local / 'linux_resources.jsonl'), '--duration', '720'],
            'native_gazebo': ['stdbuf', '-oL', '-eL', 'gz', 'topic', '--echo',
                              '--topic', f'/world/stage{selected["stage"]}_flight/stats',
                              '--json-output', '--duration', '720'],
            'flight': flight_argv(profile),
        }
        shutil.copy2(__file__, local / 'driver_source.py')
        write_new(local / 'session.json', {'started_utc': now(), 'name': trial_name, 'profile': profile,
            'primary_166_included': False, 'plan_sha256': PLAN_SHA,
            'initial_ledger_counts': dict(Counter(row['status'] for row in before.values())),
            'commands': commands, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'limits': ['CLI receipts may include buffering; no direct inference of physics pauses',
                       'Observers cannot prove watchdog cause or algorithm success',
                       'No frozen source, safety threshold, RTF or official ledger changes']})
        env = dict(os.environ, GZ_PARTITION='stage1_flight', GZ_IP='127.0.0.1',
                   ROS_DOMAIN_ID='0', PYTHONUNBUFFERED='1')
        children, handles = {}, []
        native_status = {'bytes': 0, 'lines': 0, 'limit_reached': False, 'error': None}
        reader = None
        failure = None
        try:
            for name in ('ros_observer', 'linux_resources'):
                log = (local / (name + '.log')).open('x', encoding='utf-8')
                handles.append(log)
                children[name] = subprocess.Popen(commands[name], cwd=FROZEN, env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            native_error = (local / 'native_gazebo.stderr.log').open('x', encoding='utf-8')
            handles.append(native_error)
            children['native_gazebo'] = subprocess.Popen(commands['native_gazebo'], cwd=FROZEN, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=native_error,
                text=True, encoding='utf-8', errors='replace', bufsize=1, start_new_session=True)
            reader = threading.Thread(target=collect_lines, args=(children['native_gazebo'],
                local / 'native_gazebo_lines.jsonl', native_status), daemon=True)
            reader.start()
            time.sleep(3)
            if any(process.poll() is not None for process in children.values()):
                raise RuntimeError('A diagnostic observer exited before the flight')
            log = (local / 'flight.log').open('x', encoding='utf-8')
            handles.append(log)
            print(json.dumps({'event': 'INDEPENDENT_PROBE_STARTED', 'utc': now(),
                              'name': trial_name, 'local_logs': str(local)}, ensure_ascii=False), flush=True)
            children['flight'] = subprocess.Popen(commands['flight'], cwd=FROZEN, env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            # The unchanged frozen runner owns all flight startup/timeout/cleanup.
            deadline = time.monotonic() + 600
            while children['flight'].poll() is None:
                if any(children[name].poll() is not None for name in
                       ('ros_observer', 'linux_resources', 'native_gazebo')):
                    raise RuntimeError('An observer exited while the independent flight was running')
                if native_status['error'] or native_status['limit_reached']:
                    raise RuntimeError('Native diagnostic capture failed or reached its limit')
                if time.monotonic() > deadline:
                    raise RuntimeError('Independent diagnostic outer wall deadline exceeded')
                time.sleep(.5)
        except BaseException as error:
            failure = f'{type(error).__name__}: {error}'
            # Interrupt only our runner; its finally block owns simulator cleanup.
            if 'flight' in children and children['flight'].poll() is None:
                children['flight'].send_signal(signal.SIGINT)
                # Allow the frozen bag's 180s flush and remaining owned
                # services to finish; a timeout never certifies idle.
                children['flight'].wait(timeout=420)
            raise
        finally:
            cleanup_errors = []
            for name in ('ros_observer', 'linux_resources', 'native_gazebo'):
                if name in children:
                    try:
                        stop_owned(children[name])
                    except Exception as error:
                        cleanup_errors.append({'name': name, 'error': f'{type(error).__name__}: {error}'})
            if reader:
                reader.join(timeout=6)
            for handle in handles:
                handle.close()
            remaining = active_simulation_processes()
            after = snapshot(FROZEN, plan)
            verify_sources(FROZEN, plan)
            observer_summary_path = local / 'ros/summary.json'
            observer_summary = (json.loads(observer_summary_path.read_text(encoding='utf-8'))
                                if observer_summary_path.is_file() else {})
            writer = observer_summary.get('writer', {})
            diagnostic_complete = (failure is None and not cleanup_errors and children.get('ros_observer') is not None
                and children['ros_observer'].returncode == 0 and bool(observer_summary)
                and observer_summary.get('failure') is None and writer.get('records_written', 0) > 0
                and writer.get('dropped_aggregates') == 0 and writer.get('error') is None
                and writer.get('writer_alive') is False and writer.get('limit_reached') is False
                and native_status['lines'] > 0 and not native_status['error']
                and not native_status['limit_reached'])
            report = {'finished_utc': now(), 'failure': failure,
                'primary_166_included': False, 'official_ledger_unchanged': before == after,
                'process_returncodes': {name: proc.returncode for name, proc in children.items()},
                'native_capture': native_status, 'native_reader_alive': bool(reader and reader.is_alive()),
                'remaining_simulation_processes': remaining, 'idle_after_probe': not remaining,
                'diagnostic_capture_complete': diagnostic_complete,
                'observer_cleanup_errors': cleanup_errors,
                'local_logs': str(local), 'flight_evidence': str(FROZEN / 'results' / trial_name),
                'status': 'DIAGNOSTIC_REQUIRES_REVIEW_NO_ACCEPTANCE_VERDICT'}
            write_new(local / 'summary.json', report)
            if remaining or cleanup_errors or (reader and reader.is_alive()):
                print(json.dumps(report, ensure_ascii=False), flush=True)
                raise RuntimeError('Probe cleanup incomplete; keep local evidence, refuse archive/continuation')
            # Only small diagnostic logs, after all our flight/observer processes exit.
            shutil.copytree(local, audit)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            if before != after:
                raise RuntimeError('Official ledger changed during the independent probe')
        return 0 if diagnostic_complete and children.get('flight') and children['flight'].returncode == 0 else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--profile', choices=tuple(PROFILES), default='stage2_crossing')
    parser.add_argument('--audit-output', type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'status': 'PLAN_ONLY', 'flight': flight_argv(args.profile)}, ensure_ascii=False, indent=2))
        return 0
    audit = args.audit_output or MAIN / 'results' / PROFILES[args.profile]['audit']
    return execute(audit.resolve(), args.profile)


if __name__ == '__main__':
    raise SystemExit(main())
