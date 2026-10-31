"""Bound one complete Humble33 action and retain its actual owned-group outcome.

Production CLI permits only the fixed reviewed wrapper. Fixtures call the
generic runner with temporary evidence and inert Python/sleep children.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import humble33_review_guard as guard

ACTION_TIMEOUTS = {'prepare': 300., 'copy': 300., 'build': 1800., 'validate': 600.}
TERM_GRACE_S = 30.
KILL_CONFIRM_S = 5.
RECEIPTS = guard.EXTERNAL / 'humble33_action_receipts01'


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def process_stat(pid):
    try:
        text = (Path('/proc') / str(pid) / 'stat').read_text()
    except FileNotFoundError:
        return None
    tail = text[text.rfind(')') + 2:].split()
    return {'pid': int(pid), 'state': tail[0], 'ppid': int(tail[1]),
            'pgid': int(tail[2]), 'session': int(tail[3]), 'start_ticks': int(tail[19])}


def group_members(pgid):
    if pgid <= 1 or pgid == os.getpgrp():
        raise ValueError('Refusing to inspect/signal an unowned process group')
    result = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            item = process_stat(int(path.name))
        except ProcessLookupError:
            continue
        if item is not None and item['pgid'] == pgid:
            if item['session'] != pgid:
                raise ValueError('Owned process group escaped its created session')
            result.append(item)
    return sorted(result, key=lambda item: item['pid'])


@contextmanager
def child_subreaper():
    """Adopt and reap orphaned group children rather than leave PID1 zombies."""
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_GET_CHILD_SUBREAPER failed')
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER failed')
    try:
        yield
    finally:
        if libc.prctl(36, previous.value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'Restoring child subreaper failed')


def reap_group(process):
    # Let Popen retain the direct child's real return code before reaping any
    # separately adopted descendants from this particular group.
    process.poll()
    for item in group_members(process.pid):
        if item['pid'] == process.pid or item['ppid'] != os.getpid():
            continue
        try:
            os.waitpid(item['pid'], os.WNOHANG)
        except ChildProcessError:
            pass


def wait_group(process, deadline):
    while True:
        reap_group(process)
        members = group_members(process.pid)
        if process.poll() is not None and not members:
            return []
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return members
        time.sleep(min(.05, remaining))


def cleanup_group(process, grace_s, kill_confirm_s):
    reap_group(process)
    observed = group_members(process.pid)
    actions = []
    if observed:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        actions.append({'signal': 'SIGTERM', 'sent_utc': utc_now(), 'grace_s': grace_s,
                        'members_at_signal': observed})
    remaining = wait_group(process, time.monotonic() + grace_s)
    if remaining:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        actions.append({'signal': 'SIGKILL', 'sent_utc': utc_now(), 'confirm_s': kill_confirm_s,
                        'members_at_signal': remaining})
        remaining = wait_group(process, time.monotonic() + kill_confirm_s)
    return {'members_before_cleanup': observed, 'signals': actions,
            'residual_processes': remaining, 'actual_proc_group_empty': not remaining,
            'direct_child_reaped': process.poll() is not None}


def run_bounded(command, evidence_dir, *, action, timeout_s, grace_s=TERM_GRACE_S,
                kill_confirm_s=KILL_CONFIRM_S, binding=None, environment=None):
    """One exclusive attempt; wait limits include all wrapper descendants."""
    if os.name != 'posix' or not sys.platform.startswith('linux'):
        raise ValueError('Actual process-group verification requires Linux /proc')
    if (any(type(value) not in (int, float) or not math.isfinite(value)
            for value in (timeout_s, grace_s, kill_confirm_s))
            or timeout_s <= 0 or grace_s < 0 or kill_confirm_s <= 0):
        raise ValueError('Invalid fixed wall-time or cleanup budget')
    evidence_dir = Path(evidence_dir)
    before = binding('before') if binding is not None else None
    evidence_dir.mkdir()  # Exclusive action reservation; never delete/retry it.
    started, timer = utc_now(), time.monotonic()
    write_new(evidence_dir / 'action.started.json', {
        'schema_version': 1, 'action': action, 'started_utc': started, 'command': command,
        'timeout_s': timeout_s, 'term_grace_s': grace_s, 'kill_confirm_s': kill_confirm_s,
        'execution_count': 1, 'automatic_retry': False, 'automatic_next_step': False,
        'binding_before': before, 'formal_seeds_consumed': False})
    process = None
    requested = []
    old_handlers = {}
    status, failure, cleanup = 'SPAWN_ERROR', None, None

    def requested_stop(number, _frame):
        requested.append(number)

    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            old_handlers[number] = signal.signal(number, requested_stop)
        with child_subreaper(), (evidence_dir / 'action.log').open('x', encoding='utf-8') as log:
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                    stderr=subprocess.STDOUT, start_new_session=True, env=environment)
                write_new(evidence_dir / 'action.process.json', {'pid': process.pid,
                    'pgid': process.pid, 'session': process.pid, 'created_utc': utc_now(),
                    'observed_leader_stat': process_stat(process.pid)})
                deadline = timer + timeout_s
                while process.poll() is None:
                    if requested:
                        status = 'INTERRUPTED'
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        status = 'TIMED_OUT'
                        break
                    try:
                        process.wait(timeout=min(.05, remaining))
                    except subprocess.TimeoutExpired:
                        pass
                else:
                    status = ('INTERRUPTED' if requested else 'TIMED_OUT' if time.monotonic() > deadline
                              else 'PASS' if process.returncode == 0 else 'FAILED')
                # A wrapper which exits with live children did not finish cleanly.
                reap_group(process)
                live_after_exit = group_members(process.pid)
                if status in {'PASS', 'FAILED'} and live_after_exit:
                    status = 'RESIDUAL_PROCESSES'
            except BaseException as error:
                status, failure = 'LAUNCHER_ERROR', type(error).__name__ + ': ' + str(error)
            finally:
                if process is not None:
                    cleanup = cleanup_group(process, grace_s, kill_confirm_s)
                    if not cleanup['actual_proc_group_empty'] or not cleanup['direct_child_reaped']:
                        status = 'CLEANUP_FAILED'
    except BaseException as error:
        status, failure = 'LAUNCHER_ERROR', type(error).__name__ + ': ' + str(error)
    finally:
        for number, handler in old_handlers.items():
            signal.signal(number, handler)
    after, binding_error = None, None
    try:
        after = binding('after') if binding is not None else None
        if before != after:
            binding_error = 'Source/review/original28/original29/original30 binding changed across action'
    except BaseException as error:
        binding_error = type(error).__name__ + ': ' + str(error)
    if status == 'PASS' and binding_error is not None:
        status = 'BINDING_ERROR'
    receipt = {'schema_version': 1, 'scope': 'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE',
        'action': action, 'status': status, 'started_utc': started, 'finished_utc': utc_now(),
        'elapsed_wall_s': time.monotonic() - timer, 'timeout_s': timeout_s,
        'term_grace_s': grace_s, 'kill_confirm_s': kill_confirm_s, 'command': command,
        'pid': process.pid if process else None, 'direct_child_returncode': process.poll() if process else None,
        'requested_signals': requested, 'launcher_error': failure, 'cleanup': cleanup,
        'binding_before': before, 'binding_after': after, 'binding_error': binding_error,
        'action_log_sha256': guard.sha(evidence_dir / 'action.log') if (evidence_dir / 'action.log').is_file() else None,
        'execution_count': 1, 'automatic_retry': False, 'automatic_next_step': False,
        'formal_seeds_consumed': False, 'runtime_acceptance': 'NOT_EVALUATED'}
    write_new(evidence_dir / 'action.terminal.json', receipt)
    return receipt


def production_binding(review, _phase):
    if guard.sha(guard.REVIEW) != review['_review_sha256']:
        raise ValueError('Final33 review changed during bounded action')
    guard.verified_files(guard.EXTERNAL, review['helpers_sha256'])
    original = guard.require_original28(review)
    original29 = guard.require_original29(review)
    original30 = guard.require_original30(review)
    original31 = guard.require_original31(review)
    original32 = guard.require_original32(review)
    action = review['_action']
    if action in {'prepare', 'copy'}:
        guard.require_candidate_sources(review)
        source = {'source_root': str(guard.SOURCE), 'source_commit': review['source_commit'],
                  'files_canonical_sha256': guard.canonical(review['files'])}
    else:
        source = guard.require_frozen_sources(review)
    return {'review_sha256': review['_review_sha256'], 'source': source, 'original28': original, 'original29': original29, 'original30': original30, 'original31': original31, 'original32': original32}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['describe', *ACTION_TIMEOUTS])
    parser.add_argument('--output', type=Path, help='Exclusive external prepare receipt only')
    args = parser.parse_args(argv)
    if args.action == 'describe':
        print(json.dumps({'status': 'PREPARED_ONLY_NOT_EXECUTED', 'action_timeout_s': ACTION_TIMEOUTS,
            'term_grace_s': TERM_GRACE_S, 'kill_confirm_s': KILL_CONFIRM_S,
            'receipts': str(RECEIPTS), 'automatic_next_step': False, 'automatic_retry': False}))
        return 0
    if args.output is not None and args.action != 'prepare':
        parser.error('--output is only valid for prepare')
    if os.environ.get('WSL_DISTRO_NAME') != 'UAVHumble22':
        raise ValueError('Bounded32 actions belong exclusively to WSL UAVHumble22')
    review = guard.read_small(guard.REVIEW)
    guard.validate_review(review, args.action)
    review['_action'], review['_review_sha256'] = args.action, guard.sha(guard.REVIEW)
    production_binding(review, 'before')
    command = ['/bin/bash', str(guard.EXTERNAL / 'run_humble33_action.sh'), args.action]
    if args.action == 'prepare':
        command += ['--output', str(args.output or guard.EXTERNAL / 'humble33_preflight01.json')]
    environment = dict(os.environ, HUMBLE33_BOUNDED_ACTION=args.action,
                       HUMBLE33_BOUNDED_LAUNCHER_PID=str(os.getpid()))
    if RECEIPTS.is_symlink():
        raise ValueError('Bounded action receipt directory cannot be a symlink')
    RECEIPTS.mkdir(exist_ok=True)
    receipt = run_bounded(command, RECEIPTS / args.action, action=args.action,
        timeout_s=ACTION_TIMEOUTS[args.action], environment=environment,
        binding=lambda phase: production_binding(review, phase))
    print(json.dumps(receipt))
    return 0 if receipt['status'] == 'PASS' else (124 if receipt['status'] == 'TIMED_OUT' else 2)


if __name__ == '__main__':
    raise SystemExit(main())
