"""Root-only launcher for the reviewed fixed six-file historical NTFS batch.

Default is inert. Root may pass --execute only in its exclusive idle maintenance
window after source publication is terminal and before any cold build/flight.
This launcher never kills applications or starts a build. It preserves actual
read-only idle evidence, invokes the pinned wrapper once, and retains raw output.
No optimistic savings or admission is inferred from a successful process exit.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
WRAPPER = BASE / 'windows_ntfs_closed_batch46_01.py'
WRAPPER_SHA = 'a20bda2dbad2317c0e4dff98ee6e7a44378bb34f0942b30fada325cd4eca3f18'
MANIFEST = BASE / 'humble46_closed_text_ntfs_batch01_manifest.json'
MANIFEST_SHA = '3c74fcf983dde5d5b6b6ca01b32a574c0d9207b73206413dc10e41bb32a906b9'
REVIEW = BASE / 'humble46_closed_text_ntfs_batch01_independent02.json'
REVIEW_SHA = 'a7262cfcc8208e86a84cbb97b96932d70e911e73bdefbf8130c24d4b710516ae'
PREFLIGHT = BASE / 'humble46_ntfs_closed_batch_idle_root01.json'
EXECUTION = BASE / 'humble46_ntfs_closed_batch_execution_root01.jsonl'
OUTCOME = BASE / 'humble46_ntfs_closed_batch_root_outcome01.json'
NATIVE_BUSY = re.compile(r'(?:^|[/\s])(?:colcon|pytest|ctest|cmake|ninja|make|cc1plus|cc1|ld|ar)(?:\s|$)', re.I)
WINDOWS_EXTRA_BUSY = re.compile(r'windows_ntfs_(?:maintenance41|pilot45_01|closed_batch46_01)\.py|run_ntfs_pilot45_root01\.py|development_(?:core|safety)|colcon\s+build', re.I)
CIM_SCRIPT = r"""$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$trackingNtfsProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(python(?:[0-9.]*)?|pythonw|powershell|pwsh|wsl|bash|px4|gz|gazebo|MicroXRCEAgent)(?:\.exe)?$'
} | Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine)
[ordered]@{query_utc=[DateTimeOffset]::UtcNow.ToString('o');query_pid=$PID;records=$trackingNtfsProcesses} | ConvertTo-Json -Depth 5 -Compress
"""
CIM_ARGV = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', CIM_SCRIPT]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def raw_process(argv, timeout):
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
        return {'argv': argv, 'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
                'returncode': result.returncode, 'stdout_base64': base64.b64encode(result.stdout).decode('ascii'),
                'stderr_base64': base64.b64encode(result.stderr).decode('ascii'),
                'stdout': result.stdout.decode('utf-8', errors='replace'), 'stderr_utf8_replace': result.stderr.decode('utf-8', errors='replace')}
    except subprocess.TimeoutExpired as error:
        return {'argv': argv, 'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
                'returncode': None, 'timeout_s': timeout, 'stdout_base64': base64.b64encode(error.stdout or b'').decode('ascii'),
                'stderr_base64': base64.b64encode(error.stderr or b'').decode('ascii'),
                'stdout': (error.stdout or b'').decode('utf-8', errors='replace')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'status': 'INERT_NOT_EXECUTED', 'wrapper_sha256': WRAPPER_SHA,
                          'manifest_sha256': MANIFEST_SHA, 'files': 6, 'original_allocation_bytes': 823865344,
                          'requires_root_exclusive_idle_after_source_terminal_before_build': True,
                          'capacity_credit': 0}))
        return 0
    if os.name != 'nt' or any(path.exists() for path in (PREFLIGHT, EXECUTION, OUTCOME)):
        print(json.dumps({'status': 'REFUSED_NO_WSL_OR_MUTATION', 'reason': 'Windows and three new fixed output paths required; never overwrite/retry original files'}))
        return 1
    outcome = {'scope': 'ROOT_ACTUAL_REVIEWED_SIX_FILE_NTFS_MAINTENANCE_WHOLE_CALL', 'status': 'REFUSED',
               'wrapper_called_count': 0, 'capacity_credit': 0, 'started_utc': datetime.now(timezone.utc).isoformat()}
    code = 1
    try:
        require(sha(WRAPPER) == WRAPPER_SHA and sha(MANIFEST) == MANIFEST_SHA and sha(REVIEW) == REVIEW_SHA, 'Reviewed fixed wrapper/manifest/independent pins changed')
        review = json.loads(REVIEW.read_text(encoding='utf-8'))
        require(review['status'] == 'PASS_AFTER_CLOSE_JOURNAL_ROLLBACK_FIX_PENDING_ROOT_FRESH_EXCLUSIVE_IDLE_WINDOW' and review['blockers'] == [], 'Independent review has unresolved blockers')
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location('reviewed_ntfs_closed_batch46', WRAPPER)
        batch = importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)
        require(batch.MANIFEST_SHA == MANIFEST_SHA and sha(batch.HELPER) == batch.HELPER_SHA and sha(batch.CORE) == batch.CORE_SHA, 'Pinned helper/manifest/original45 terminal changed')
        idle = outcome['actual_wsl_idle_check'] = raw_process(batch.IDLE_ARGV, 30)
        require(idle['returncode'] == 0 and idle['stdout'].splitlines(), 'Actual WSL ps failed/empty; no wrapper call')
        require(all(re.fullmatch(r'\s*\d+\s+.+', line) and not batch.BUSY.search(line) and not NATIVE_BUSY.search(line) for line in idle['stdout'].splitlines()), 'WSL has simulation/build/evaluation activity; postpone maintenance')
        checked = datetime.fromisoformat(idle['finished_utc'])
        windows = outcome['actual_windows_producer_check'] = raw_process(CIM_ARGV, 30)
        require(windows['returncode'] == 0, 'Read-only Win32_Process query failed; no wrapper call')
        snapshot = json.loads(windows['stdout'])
        require(isinstance(snapshot['records'], list), 'Malformed Windows producer snapshot')
        ignored = {os.getpid(), int(snapshot['query_pid'])}
        busy = []
        for record in snapshot['records']:
            command = record.get('CommandLine') or ''
            if int(record['ProcessId']) in ignored:
                continue
            named_wsl = record['Name'].lower() == 'wsl.exe' and 'uavhumble22' in command.lower()
            if named_wsl or batch.BUSY.search(command) or WINDOWS_EXTRA_BUSY.search(command):
                busy.append(record)
        windows['matching_active_producers'] = busy
        require(busy == [], 'Matching Windows producer still alive; no applications are terminated; postpone maintenance')
        require(sha(batch.CORE) == batch.CORE_SHA and sha(WRAPPER) == WRAPPER_SHA and sha(MANIFEST) == MANIFEST_SHA, 'Reviewed source/original45 changed during idle checks')
        receipt = {'scope': batch.SCOPE, 'action': 'compress', 'manifest_sha256': MANIFEST_SHA,
                   'wrapper_sha256': WRAPPER_SHA, 'helper_sha256': batch.HELPER_SHA,
                   'checked_utc': checked.isoformat(), 'expires_utc': (checked + timedelta(seconds=120)).isoformat(),
                   'root_maintains_exclusive_idle_window': True, 'preserve_core45_original_failure': True,
                   'core_terminal': {'path': str(batch.CORE), 'sha256': batch.CORE_SHA},
                   'idle_check': {**idle, 'checked_utc': checked.isoformat()},
                   'windows_producer_pids': [], 'windows_producer_check': windows,
                   'writer_exclusion_boundary': 'No matching named Windows producer observed in captured read-only Win32_Process snapshot. Root owns continuing Windows/WSL idle; this is not all-process no-writer certification.',
                   'independent_review': {'path': str(REVIEW), 'sha256': REVIEW_SHA}}
        raw = (json.dumps(receipt, ensure_ascii=True, indent=2) + '\n').encode('utf-8')
        require(len(raw) <= 1024**2, 'Gate exceeds fixed wrapper metadata bound')
        require(0 <= (datetime.now(timezone.utc)-checked).total_seconds() <= 120, 'Idle evidence expired during checks')
        with PREFLIGHT.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        command = [sys.executable, '-B', str(WRAPPER), '--execute', '--action', 'compress',
                   '--preflight', str(PREFLIGHT), '--preflight-sha256', sha(PREFLIGHT), '--receipt', str(EXECUTION)]
        outcome.update(status='WRAPPER_STARTED', command=command, wrapper_called_count=1,
                       source_pins={'wrapper': WRAPPER_SHA, 'manifest': MANIFEST_SHA, 'independent_review': REVIEW_SHA},
                       preflight={'path': str(PREFLIGHT), 'sha256': sha(PREFLIGHT)})
        started = time.monotonic()
        # Do not kill a mutating wrapper on a launcher timer: its per-file native
        # readback is bounded; its own exception handling must retain rollback.
        result = subprocess.run(command, capture_output=True, check=False)
        outcome['whole_call'] = {'argv': command, 'returncode': result.returncode,
                                'elapsed_wall_s': time.monotonic()-started,
                                'stdout_base64': base64.b64encode(result.stdout).decode('ascii'),
                                'stderr_base64': base64.b64encode(result.stderr).decode('ascii'),
                                'stdout': result.stdout.decode('utf-8', errors='replace'),
                                'stderr_utf8_replace': result.stderr.decode('utf-8', errors='replace')}
        outcome['original45_terminal_sha256_after'] = sha(batch.CORE)
        outcome['execution_receipt'] = {'path': str(EXECUTION), 'sha256': sha(EXECUTION)} if EXECUTION.exists() else None
        outcome['preflight_unchanged'] = sha(PREFLIGHT) == outcome['preflight']['sha256']
        require(outcome['original45_terminal_sha256_after'] == batch.CORE_SHA and outcome['preflight_unchanged'], 'Original45 failure or root gate changed')
        outcome.update(status='WRAPPER_EXITED_AWAIT_ROOT_EVIDENCE_REVIEW', capacity_credit=0,
                       review_boundary='Whole-call exit0 plus six durable CLOSED events/final COMPLETE, native SHA, logical preservation, actual allocation/host-free and clean receipt close require root review. No ratio/budget credit is inferred here.')
        code = result.returncode
    except BaseException as error:
        outcome.update(status='REFUSED_OR_ERROR_NO_AUTOMATIC_RETRY', error=repr(error), capacity_credit=0)
    finally:
        outcome['finished_utc'] = datetime.now(timezone.utc).isoformat()
        outcome['launcher_returncode'] = code
        try:
            with OUTCOME.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(outcome, stream, ensure_ascii=True, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        except BaseException as failed:
            outcome.update(status='ERROR_OUTCOME_RECEIPT_FAILED', receipt_error=repr(failed), launcher_returncode=1)
            code = 1
        print(json.dumps(outcome, ensure_ascii=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
