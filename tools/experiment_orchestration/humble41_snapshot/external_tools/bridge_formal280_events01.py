"""Read two original formal plans/slot records into fresh standard monitor events.

Observation only. Never invokes a guard, runner, WSL, simulator or monitor.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import time

EXTERNAL = Path(__file__).resolve().parent
MAX_BYTES = 8 * 1024**2
TERMINAL = {'PASS', 'FAIL', 'INCOMPLETE_EVIDENCE', 'EVALUATION_PENDING',
            'INFRASTRUCTURE_ERROR', 'INTERRUPTED'}
BATCH_SCOPE = 'SERIAL_EXISTING_GUARD_ORCHESTRATION_ONLY_NOT_ENGINEERING_ACCEPTANCE'
SCOPE = 'TWO_ORIGINAL_PLANS_READONLY_PROGRESS_NOT_ADMISSION_OR_ACCEPTANCE'


def require(value, message):
    if not value:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value, excluded):
    return hashlib.sha256(json.dumps({k: v for k, v in value.items() if k != excluded},
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def small_json(path):
    """An unfinished producer JSON is pending; duplicate/nonfinite objects refuse."""
    path = Path(path)
    if not path.exists():
        return None
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_BYTES,
            'Expected named small regular JSON: '+str(path))
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('Nonfinite JSON: '+value)
    try:
        raw = path.read_bytes()
        require(len(raw) <= MAX_BYTES, 'Small JSON grew beyond metadata limit')
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    require(isinstance(value, dict), 'Expected JSON object: '+str(path))
    return value, {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2, allow_nan=False)
        stream.write('\n')


class PlanEvents:
    def __init__(self, core_path, core_sha, extension_path, extension_sha, *, total=280):
        require(type(total) is int and total > 0, 'Positive declared total required')
        self.total, self.plans, self.entries, self.seen = total, [], [], set()
        self.unclosed = {}
        ids = set()
        for label, path, expected, mode in [('core', core_path, core_sha, 'FORMAL'),
                ('extension', extension_path, extension_sha, 'EXTENSION_FORMAL')]:
            path = Path(path).resolve(strict=True)
            require(re.fullmatch('[0-9a-f]{64}', expected or ''), 'Explicit original plan SHA required')
            source = small_json(path)
            require(source is not None, 'Original plan is absent/unfinished')
            plan, binding = source
            require(type(plan.get('schema_version')) is int and plan['schema_version'] == 1
                    and plan.get('study_kind') == 'POST_REPAIR_ENGINEERING_VALIDATION'
                    and binding['sha256'] == expected and plan.get('mode') == mode
                    and plan.get('plan_sha256') == canonical(plan, 'plan_sha256'),
                    'Original plan bytes/mode/digest differ')
            trials = plan.get('trials')
            require(isinstance(trials, list) and bool(trials), 'Original trial list required')
            self.plans.append({'label': label, 'path': path, 'plan': plan, 'binding': binding})
            for index, trial in enumerate(trials, 1):
                slot = trial.get('id') if isinstance(trial, dict) else None
                require(isinstance(slot, str) and slot not in {'.', '..'}
                        and re.fullmatch('[A-Za-z0-9_.-]+', slot) and slot not in ids,
                        'Slot IDs must be safe and globally unique across both plans')
                ids.add(slot)
                self.entries.append({'slot': slot, 'number': len(self.entries)+1,
                    'matrix_number': index, 'matrix': label, 'plan': plan,
                    'binding': binding, 'slots': path.parent/'slots', 'trial': trial})
        require(len(self.entries) == total, 'Two-plan total differs from declared denominator')
        if total == 280:
            require([len(x['plan']['trials']) for x in self.plans] == [120, 160],
                    'Formal280 requires original core120 plus extension160')
        core, extension = [x['plan'] for x in self.plans]
        reference = extension.get('core_reference_binding', {})
        require(reference.get('sha256') == self.plans[0]['binding']['sha256']
                and reference.get('plan_sha256') == core['plan_sha256']
                and extension.get('protocol_sha256') == core.get('protocol_sha256')
                and extension.get('protocol') == core.get('protocol'),
                'Extension does not bind the supplied original core/protocol')

    def header(self):
        return {'event': 'BRIDGE_BOUND_PLANS', 'utc': now(), 'total': self.total,
                'plans': [x['binding'] for x in self.plans], 'scope': SCOPE}

    def scan(self):
        previous_seen, previous_unclosed = self.seen.copy(), self.unclosed.copy()
        try:
            return self._scan()
        except BaseException:
            self.seen, self.unclosed = previous_seen, previous_unclosed
            raise

    def _scan(self):
        for plan in self.plans:
            current = small_json(plan['path'])
            require(current is not None and current[1] == plan['binding'], 'Original plan changed')
        rows = []
        for entry in self.entries:
            slot = entry['slot']
            for event, suffix in [('START_SLOT', '.started.json'), ('COMPLETE_SLOT', '.json')]:
                if (event, slot) in self.seen:
                    continue
                path = entry['slots']/(slot+suffix)
                source = small_json(path)
                if source is None:
                    continue
                original, binding = source
                require(original.get('id') == slot
                        and original.get('plan_sha256') == entry['plan']['plan_sha256'],
                        'Original slot/plan identity differs: '+slot)
                if event == 'START_SLOT':
                    require(original.get('flight_command') == entry['trial'].get('flight_command'),
                            'Original start command differs: '+slot)
                else:
                    if original.get('status') not in TERMINAL or ('START_SLOT', slot) not in self.seen:
                        self.unclosed[slot] = {'original_source': binding, 'status': original.get('status'),
                            'reason': 'UNKNOWN_OR_NONTERMINAL_STATUS_OR_MISSING_ORIGINAL_START_MARKER'}
                        continue
                    require(original.get('record_sha256') == canonical(original, 'record_sha256')
                            and original.get('execution_status') in {'COMPLETED', 'INTERRUPTED'},
                            'Original closed record digest/execution state differs: '+slot)
                observed = now()
                stamp = original.get('started_utc' if event == 'START_SLOT' else 'finished_utc')
                try:
                    valid_stamp = datetime.fromisoformat(str(stamp).replace('Z', '+00:00')).tzinfo is not None
                except ValueError:
                    valid_stamp = False
                rows.append({'event': event, 'slot': slot, 'number': entry['number'],
                    'matrix_number': entry['matrix_number'], 'matrix': entry['matrix'], 'total': self.total,
                    'utc': stamp if valid_stamp else observed,
                    'utc_basis': 'original' if valid_stamp else 'bridge_observation', 'observed_utc': observed,
                    'original_source': binding, 'plan': entry['binding'],
                    'status': original.get('status'), 'engineering_result': original.get('engineering_result'),
                    'execution_status': original.get('execution_status')})
                self.seen.add((event, slot))
                if event == 'COMPLETE_SLOT':
                    self.unclosed.pop(slot, None)
                    if original.get('infrastructure_stop') is True or original['status'] in {'INFRASTRUCTURE_ERROR', 'INTERRUPTED'}:
                        rows.append({'event': 'INFRASTRUCTURE_STOP_NO_AUTOMATIC_RETRY', 'slot': slot,
                            'utc': rows[-1]['utc'], 'total': self.total, 'status': original['status'],
                            'original_source': binding, 'plan': entry['binding']})
        return rows


def run_bridge(bridge, output, *, pid, expected_token, identity_provider, identity_checker,
               batch_summary=None, interval=5.0, sleeper=time.sleep, allowed_parent=EXTERNAL):
    require(math.isfinite(interval) and .5 <= interval <= 60, 'Polling interval must be .5..60 seconds')
    output = Path(output).absolute()
    require(output.parent.resolve(strict=True) == Path(allowed_parent).resolve()
            and not output.exists() and not output.is_symlink(), 'Fresh external output directory required')
    identity = identity_provider(pid)
    require(type(pid) is int and pid > 0 and identity.get('pid') == pid
            and identity.get('alive') is True and identity.get('start_token') == expected_token
            and isinstance(expected_token, str) and bool(expected_token), 'Batch PID creation identity is unverified')
    output.mkdir(exist_ok=False)
    reason, error, batch_binding = None, None, None
    counts, emitted = Counter(), []
    with (output/'events.jsonl').open('x', encoding='utf-8', newline='\n') as events:
        def emit(row):
            events.write(json.dumps(row, ensure_ascii=True, allow_nan=False)+'\n')
            events.flush()
            counts[row['event']] += 1
            emitted.append(row)
        emit(bridge.header())
        try:
            while True:
                for row in bridge.scan():
                    emit(row)
                if reason is not None:
                    break  # One final scan after the original terminal/process observation.
                source = small_json(Path(batch_summary)) if batch_summary is not None else None
                if source is not None:
                    summary, batch_binding = source
                    require(type(summary.get('schema_version')) is int and summary['schema_version'] == 1
                            and summary.get('scope') == BATCH_SCOPE
                            and summary.get('status') in {'GUARD_PENDING_EXHAUSTED', 'STOPPED_ORIGINAL_RECORDS_RETAINED'},
                            'Unrecognized original batch summary')
                    reason = 'ORIGINAL_BATCH_SUMMARY_PRESENT'
                    if summary['status'] == 'STOPPED_ORIGINAL_RECORDS_RETAINED':
                        emit({'event': 'STOPPED_FAULT', 'utc': now(), 'total': bridge.total,
                            'original_source': batch_binding, 'reason': 'Original serial batch stopped; original outcomes retained'})
                    continue
                if not identity_checker(identity).get('verified_alive'):
                    reason = 'ORIGINAL_PID_IDENTITY_NO_LONGER_ALIVE_OUTCOME_UNKNOWN'
                    continue
                sleeper(interval)
        except BaseException as caught:
            error = type(caught).__name__+': '+str(caught)
            reason = 'BRIDGE_STOPPED_UNVERIFIED_SOURCE_OR_OBSERVER_ERROR'
            emit({'event': 'STOPPED_FAULT', 'utc': now(), 'total': bridge.total,
                  'reason': reason, 'error': error, 'engineering_verdict_computed': False})
    started = {row['slot'] for row in emitted if row['event'] == 'START_SLOT'}
    complete = {row['slot'] for row in emitted if row['event'] == 'COMPLETE_SLOT'}
    result = {'schema_version': 1, 'scope': SCOPE, 'finished_utc': now(), 'reason': reason, 'error': error,
        'process_identity': identity, 'original_batch_summary': batch_binding,
        'plan_bindings': [x['binding'] for x in bridge.plans], 'planned_slots': bridge.total,
        'start_events': counts['START_SLOT'], 'complete_events': counts['COMPLETE_SLOT'],
        'unattempted_slots': bridge.total-len(started), 'attempted_without_terminal': sorted(started-complete),
        'unclosed_original_sources': bridge.unclosed, 'engineering_verdict_computed': False,
        'completion_boundary': 'Events describe original markers/closed records only. Original FAIL and unknown/missing evidence remain; process exit and wrapper zero never supply PASS or missing slot completion.'}
    write_new(output/'bridge_terminal.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, required=True)
    for label in ('core', 'extension'):
        parser.add_argument('--'+label+'-plan', type=Path, required=True)
        parser.add_argument('--'+label+'-plan-sha256', required=True)
    parser.add_argument('--expected-total', type=int, default=280)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--expected-start-token', required=True)
    parser.add_argument('--batch-summary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interval', type=float, default=5.0)
    args = parser.parse_args(argv)
    spec = importlib.util.spec_from_file_location('existing_progress_monitor',
        args.project_root.resolve(strict=True)/'scripts/monitor_project_progress.py')
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    bridge = PlanEvents(args.core_plan, args.core_plan_sha256, args.extension_plan,
                        args.extension_plan_sha256, total=args.expected_total)
    result = run_bridge(bridge, args.output, pid=args.pid, expected_token=args.expected_start_token,
        identity_provider=monitor.process_identity, identity_checker=monitor.verify_process,
        batch_summary=args.batch_summary, interval=args.interval)
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 2 if result['error'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
