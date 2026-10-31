"""Read-only Humble41 canonical core12 progress; reuse the reviewed slot-event reader.

No source review, contract, plan, runner, WSL discovery, scheduler or engineering
verdict is created. All paths and local PID creation identities are explicit.
"""
from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import time

import bridge_formal280_events01 as reader

EXTERNAL = Path(__file__).resolve().parent
READER_SHA = '0229bf564ec3609ee226b388e9024276516f76d05f8f9bdc110235c8ed18e270'
MONITOR_SHA = '759136d0eda40bb3a61c9e30e0272e1f6b8810b351dbe4c75dc17db5951bfd98'
OWN_FILES = ('bridge_humble41_events01.py', 'test_bridge_humble41_events01.py')
ROOT = '/root/uav_tracking_fullplan_v4_humble41'
SCOPE = 'HUMBLE41_READONLY_DEVELOPMENT_PROGRESS_EVENTS_ONLY'
GROUPS = ('stage1_velocity', 'stage1_position', 'stage2_crossing',
          'stage3_midpoint', 'stage3_active', 'stage3_multi_active')
PREFIXES = {'core': 'reliability_v4_humble41_probe01'}
require = reader.require


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tool_manifest():
    require(Path(reader.__file__).resolve(strict=True) == (EXTERNAL/'bridge_formal280_events01.py').resolve(strict=True)
            and sha(reader.__file__) == READER_SHA, 'Reviewed read-only event dependency changed')
    return {'schema_version': 1, 'scope': SCOPE,
        'files': {name: sha(EXTERNAL/name) for name in OWN_FILES},
        'reused_reader_sha256': READER_SHA, 'monitor_helper_sha256': MONITOR_SHA,
        'kind_counts': {'core': 12}, 'default_pid': None, 'default_plan': None,
        'consumes_prerequisite_results': False, 'may_admit_core_or_change_verdict': False,
        'engineering_verdict_computed': False, 'runtime_or_formal_action': False}


class DevelopmentEvents(reader.PlanEvents):
    """Only the original single-plan binding differs from the reviewed reader."""
    def __init__(self, path, expected_sha, kind):
        require(kind in PREFIXES and re.fullmatch('[0-9a-f]{64}', expected_sha or ''),
                'Explicit Humble41 development kind and actual plan file SHA required')
        path = Path(path).resolve(strict=True)
        source = reader.small_json(path)
        require(source is not None, 'Original development plan is absent or unfinished')
        plan, binding = source
        ids = [f'{cls}_{group}_seed004' for cls in ('person', 'car') for group in GROUPS]
        require(type(plan.get('schema_version')) is int and plan['schema_version'] == 1
            and plan.get('mode') == 'PROBE' and plan.get('frozen_root') == ROOT
            and plan.get('prefix') == PREFIXES[kind] and binding['sha256'] == expected_sha
            and plan.get('plan_sha256') == reader.canonical(plan, 'plan_sha256')
            and plan.get('selected_seeds') == [4] and type(plan['selected_seeds'][0]) is int
            and isinstance(plan.get('trials'), list)
            and [trial.get('id') for trial in plan['trials']] == ids,
            'Original Humble41 plan bytes, internal digest, scope or complete denominator differs')
        self.total, self.kind = len(ids), kind
        self.plans = [{'label': kind, 'path': path, 'plan': plan, 'binding': binding}]
        self.entries = [{'slot': trial['id'], 'number': number, 'matrix_number': number,
            'matrix': kind, 'plan': plan, 'binding': binding, 'slots': path.parent/'slots', 'trial': trial}
            for number, trial in enumerate(plan['trials'], 1)]
        self.seen, self.unclosed = set(), {}

    def header(self):
        return {'event': 'BRIDGE_BOUND_PLANS', 'utc': reader.now(), 'total': self.total,
                'plans': [item['binding'] for item in self.plans], 'scope': SCOPE, 'kind': self.kind}


def run_bridge(bridge, output, *, pid, expected_token, identity_provider, identity_checker,
               interval=5., sleeper=time.sleep, allowed_parent=EXTERNAL):
    """The existing core bridge loop, with explicit bindings and a final scan."""
    require(math.isfinite(interval) and .5 <= interval <= 60., 'Polling interval must be .5..60 s')
    output = Path(output).absolute()
    require(output.parent.resolve(strict=True) == Path(allowed_parent).resolve(strict=True)
        and not output.exists() and not output.is_symlink(), 'Fresh direct external output directory required')
    identity = identity_provider(pid)
    require(type(pid) is int and pid > 0 and identity.get('pid') == pid
        and identity.get('alive') is True and isinstance(expected_token, str) and bool(expected_token)
        and identity.get('start_token') == expected_token, 'Actual local PID creation identity is unverified')
    output.mkdir(exist_ok=False)
    counts, reason, error = Counter(), None, None
    with (output/'events.jsonl').open('x', encoding='utf-8', newline='\n') as stream:
        def emit(row):
            stream.write(json.dumps(row, allow_nan=False)+'\n'); stream.flush()
            counts[row['event']] += 1
        emit(bridge.header())
        try:
            while True:
                for row in bridge.scan():
                    emit(row)
                if reason is not None:
                    break
                if not identity_checker(identity).get('verified_alive'):
                    reason = 'ORIGINAL_PID_IDENTITY_NO_LONGER_ALIVE_OUTCOME_UNKNOWN'
                    continue
                sleeper(interval)
        except BaseException as caught:
            error = type(caught).__name__+':'+str(caught)
            reason = 'BRIDGE_STOPPED_UNVERIFIED_SOURCE_OR_OBSERVER_ERROR'
            emit({'event': 'STOPPED_FAULT', 'utc': reader.now(), 'reason': reason, 'error': error,
                  'total': bridge.total, 'engineering_verdict_computed': False})
    started = {slot for event, slot in bridge.seen if event == 'START_SLOT'}
    completed = {slot for event, slot in bridge.seen if event == 'COMPLETE_SLOT'}
    result = {'schema_version': 1, 'scope': SCOPE, 'finished_utc': reader.now(), 'reason': reason,
        'error': error, 'process_identity': identity, 'planned_slots': bridge.total,
        'plan_bindings': [item['binding'] for item in bridge.plans],
        'start_events': counts['START_SLOT'], 'complete_events': counts['COMPLETE_SLOT'],
        'unattempted_slots': bridge.total-len(started), 'attempted_without_terminal': sorted(started-completed),
        'unclosed_original_sources': bridge.unclosed, 'engineering_verdict_computed': False,
        'claim_boundary': 'Original FAIL and UNKNOWN remain; local PID exit does not create closed slots or PASS.'}
    reader.write_new(output/'bridge_terminal.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', 'watch'))
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--kind', choices=('core',))
    parser.add_argument('--plan', type=Path); parser.add_argument('--plan-sha256')
    parser.add_argument('--pid', type=int); parser.add_argument('--expected-start-token')
    parser.add_argument('--output', type=Path); parser.add_argument('--interval', type=float, default=5.)
    args = parser.parse_args(argv)
    manifest = tool_manifest()
    if args.action == 'describe':
        print(json.dumps({'tool_manifest': manifest, 'tools_canonical_sha256': reader.canonical(manifest, None),
                          'actual_action_executed': False}, indent=2))
        return 0
    require(all(value is not None for value in (args.project_root, args.kind, args.plan,
        args.plan_sha256, args.pid, args.expected_start_token, args.output)), 'Explicit watch inputs required')
    path = args.project_root.resolve(strict=True)/'scripts/monitor_project_progress.py'
    require(path.is_file() and not path.is_symlink() and sha(path) == MONITOR_SHA,
            'Existing process identity/page helper differs')
    spec = importlib.util.spec_from_file_location('humble41_existing_progress_helper', path)
    monitor = importlib.util.module_from_spec(spec); spec.loader.exec_module(monitor)
    bridge = DevelopmentEvents(args.plan, args.plan_sha256, args.kind)
    result = run_bridge(bridge, args.output, pid=args.pid, expected_token=args.expected_start_token,
        identity_provider=monitor.process_identity, identity_checker=monitor.verify_process, interval=args.interval)
    print(json.dumps(result, indent=2))
    return 0 if result['error'] is None else 2


if __name__ == '__main__':
    raise SystemExit(main())
