"""Serially invoke the existing formal guard; never choose or retry a slot.

The command prefix must enter the correct Humble environment and end with the
actual bound guard script. This wrapper appends only run-one --manifest PATH.
Original guard admission/outcome files are authoritative; stdout is retained
as a log because an environment wrapper may print text before the CLI JSON.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

TOTAL = 280
MAX_METADATA_BYTES = 128 * 1024**2
CLOSED = {'PASS', 'FAIL', 'INCOMPLETE_EVIDENCE', 'EVALUATION_PENDING'}
INVOCATION = re.compile(r'\d{8}T\d{6}_[0-9a-f]{32}')
SCOPE = 'SERIAL_EXISTING_GUARD_ORCHESTRATION_ONLY_NOT_ENGINEERING_ACCEPTANCE'


def require(value, message):
    if not value:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def metadata_bytes(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_METADATA_BYTES,
            'Missing, linked or oversized metadata: '+str(path))
    require(path.suffix in {'.json', '.py'}, 'Only named JSON/code metadata may be read')
    return path.read_bytes()


def digest(path):
    return hashlib.sha256(metadata_bytes(path)).hexdigest()


def parse_object(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: '+key)
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('Nonfinite JSON: '+value)
    result = json.loads(data, object_pairs_hook=pairs, parse_constant=nonfinite)
    require(isinstance(result, dict), 'One complete JSON object is required')
    return result


def load(path):
    return parse_object(metadata_bytes(path).decode('utf-8-sig'))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def binding(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': digest(path)}


def valid_binding(value):
    return (isinstance(value, dict) and set(value) == {'path', 'sha256'}
        and isinstance(value['path'], str) and Path(value['path']).is_absolute()
        and isinstance(value['sha256'], str) and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None)


def integer(value, name, minimum=0, maximum=TOTAL):
    require(type(value) is int and minimum <= value <= maximum, 'Invalid '+name)
    return value


def capacity(value):
    require(isinstance(value, dict) and type(value.get('scheduled_slots')) is int
            and value['scheduled_slots'] == TOTAL, 'Guard capacity must retain the full280 denominator')
    return integer(value.get('pending_slots'), 'guard pending count')


def directories(state):
    if not state.exists():
        return set()
    require(state.is_dir() and not state.is_symlink(), 'Guard state is not a regular directory')
    result = set()
    for path in state.iterdir():
        if INVOCATION.fullmatch(path.name):
            require(path.is_dir() and not path.is_symlink(), 'Linked/invalid guard invocation')
            result.add(path.name)
    return result


def completed_receipt(directory, manifest_path, manifest, manifest_binding):
    """Check original routing/closure receipts, leaving all admission to guard."""
    outcome = load(directory/'outcome.json')
    require(outcome.get('schema_version') == 1 and type(outcome['schema_version']) is int
        and outcome.get('kind') == 'RELIABILITY_V4_GUARD_SINGLE_INVOCATION'
        and outcome.get('result') == 'COMPLETED', 'Original guard did not complete one closed slot')
    require(type(outcome.get('returncode')) is int and outcome['returncode'] == 0
        and outcome.get('error') is None and type(outcome.get('started_this_invocation')) is int
        and outcome['started_this_invocation'] == 1 and outcome.get('preserved_status') in CLOSED,
        'Guard completion/ordinary terminal semantics are invalid')
    slot = outcome.get('slot_id')
    require(isinstance(slot, str) and bool(slot.strip()), 'Guard slot identity is missing')
    admission_path = directory/'admission.json'
    require(outcome.get('admission') == binding(admission_path), 'Original admission binding changed')
    admission = load(admission_path)
    require(type(admission.get('schema_version')) is int and admission['schema_version'] == 1
        and admission.get('kind') == 'RELIABILITY_V4_GUARD_ADMISSION_CHECK' and admission.get('result') == 'PASS'
        and admission.get('manifest') == manifest_binding
        and admission.get('manifest_sha256') == manifest.get('manifest_sha256')
        and admission.get('tool') == manifest.get('tool'), 'Guard receipt binds another manifest/tool')
    require(admission.get('next_matrix') in {'core', 'extension'} and admission.get('next_slot_id') == slot
        and isinstance(admission.get('command'), list) and bool(admission['command']),
        'Original guard routing is incomplete')
    log = outcome.get('runner_log')
    require(valid_binding(log) and Path(log['path']) == directory/'runner.log'
        and (directory/'runner.log').is_file() and not (directory/'runner.log').is_symlink(),
        'Original runner-log binding/path is missing')
    before, after = capacity(admission.get('capacity')), capacity(outcome.get('capacity_after'))
    require(before >= 1 and after == before-1, 'Guard pending denominator did not decrease by exactly one')
    require(binding(manifest_path) == manifest_binding, 'Admission manifest changed during invocation')
    return outcome, admission, before, after


def exhausted_stdout(path, manifest, manifest_binding):
    """Only the original no-invocation terminal sentinel uses stdout as JSON."""
    require(path.stat().st_size <= MAX_METADATA_BYTES, 'Oversized guard stdout')
    value = parse_object(path.read_text(encoding='utf-8-sig'))
    require(type(value.get('schema_version')) is int and value['schema_version'] == 1
        and value.get('kind') == 'RELIABILITY_V4_GUARD_ADMISSION_CHECK' and value.get('result') == 'PASS'
        and value.get('execution') == 'NO_PENDING_SLOTS'
        and type(value.get('started_this_invocation')) is int and value['started_this_invocation'] == 0
        and value.get('next_matrix') is None and value.get('next_slot_id') is None
        and value.get('command') is None and value.get('manifest') == manifest_binding
        and value.get('manifest_sha256') == manifest.get('manifest_sha256')
        and value.get('tool') == manifest.get('tool') and capacity(value.get('capacity')) == 0,
        'No original guard invocation/outcome or verified NO_PENDING_SLOTS sentinel')
    return value


def run(manifest_path, output_path, guard_command, *, command_runner=subprocess.run):
    output = Path(output_path).absolute()
    require(not output.exists() and not output.is_symlink(), 'Batch output already exists; never overwrite or resume it')
    require(output.parent.is_dir() and not output.parent.is_symlink(), 'Explicit existing output parent required')
    output = output.resolve()
    manifest_path = Path(manifest_path).absolute()
    require(not manifest_path.is_symlink(), 'Manifest must be an original regular file')
    manifest_path = manifest_path.resolve(strict=True)
    manifest_binding = binding(manifest_path)
    manifest = load(manifest_path)
    require(manifest.get('kind') == 'RELIABILITY_V4_FORMAL_ADMISSION'
        and isinstance(manifest.get('state_directory'), str)
        and Path(manifest['state_directory']).is_absolute(), 'Original admission manifest with state directory required')
    state = Path(manifest['state_directory']).resolve()
    require(not output.is_relative_to(state) and not state.is_relative_to(output), 'Batch output must be independent of original guard state')
    root = Path(manifest.get('final_root', '')).resolve()
    require(not output.is_relative_to(root), 'Batch output must be outside the frozen final root')
    require(isinstance(guard_command, list) and bool(guard_command)
        and all(isinstance(token, str) and bool(token) for token in guard_command), 'Explicit argv command prefix required')
    command = list(guard_command)+['run-one', '--manifest', str(manifest_path)]
    output.mkdir(exist_ok=False)
    write_new(output/'started.json', {'schema_version': 1, 'scope': SCOPE, 'created_utc': now(),
        'manifest': manifest_binding, 'command': command, 'tool': binding(__file__),
        'working_directory': str(Path.cwd()), 'automatic_retry': False,
        'slot_selection': 'Existing guard only; wrapper never chooses or changes a slot'})
    seen, statuses, pending, initial, calls = set(), Counter(), None, None, 0
    status, error, child_code = 'STOPPED_ORIGINAL_RECORDS_RETAINED', None, None
    with (output/'events.jsonl').open('x', encoding='utf-8') as events:
        def event(name, **values):
            json.dump({'created_utc': now(), 'event': name, **values}, events, ensure_ascii=False, allow_nan=False)
            events.write('\n')
            events.flush()
        try:
            for number in range(1, TOTAL+1):
                child_code = None
                require(binding(manifest_path) == manifest_binding, 'Original admission manifest changed')
                previous = directories(state)
                invocation = output/f'{number:04d}'
                invocation.mkdir(exist_ok=False)
                calls += 1
                event('GUARD_CALL_STARTED', number=number, stdout=str(invocation/'stdout.log'), stderr=str(invocation/'stderr.log'))
                with (invocation/'stdout.log').open('xb') as stdout, (invocation/'stderr.log').open('xb') as stderr:
                    child = command_runner(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, check=False)
                child_code = child.returncode
                write_new(invocation/'process.json', {'returncode': child_code, 'finished_utc': now()})
                require(type(child_code) is int and child_code == 0, 'Guard process did not exit zero')
                created = directories(state)-previous
                if not created:
                    sentinel = exhausted_stdout(invocation/'stdout.log', manifest, manifest_binding)
                    require(pending in {None, 0}, 'No-pending sentinel contradicts the previous guard count')
                    require(binding(manifest_path) == manifest_binding, 'Manifest changed before exhaustion')
                    pending, initial = 0, 0 if initial is None else initial
                    write_new(invocation/'observed_result.json', sentinel)
                    event('NO_PENDING_SLOTS', number=number, pending_slots=0)
                    status = 'GUARD_PENDING_EXHAUSTED'
                    break
                require(len(created) == 1, 'Guard call did not create exactly one original invocation directory')
                directory = state/next(iter(created))
                result, admission, before, after = completed_receipt(directory, manifest_path, manifest, manifest_binding)
                require(pending is None or before == pending, 'Guard remaining count changed outside this serial loop')
                require(result['slot_id'] not in seen, 'Guard repeated a slot already observed in this batch')
                initial = before if initial is None else initial
                seen.add(result['slot_id'])
                statuses[result['preserved_status']] += 1
                pending = after
                write_new(invocation/'observed_result.json', {'original_outcome': binding(directory/'outcome.json'),
                    'original_admission': binding(directory/'admission.json'), 'next_matrix': admission['next_matrix'],
                    'slot_id': result['slot_id'], 'preserved_status': result['preserved_status'], 'pending_slots': after})
                event('ORIGINAL_SLOT_CLOSED', number=number, matrix=admission['next_matrix'], slot_id=result['slot_id'],
                    preserved_status=result['preserved_status'], pending_slots=after, guard_directory=str(directory))
                if after == 0:
                    require(len(seen) == initial, 'Final zero pending does not account for every slot remaining at batch entry')
                    status = 'GUARD_PENDING_EXHAUSTED'
                    break
            else:
                raise ValueError('Full280 call ceiling reached without verified zero pending')
        except BaseException as caught:
            error = type(caught).__name__+': '+str(caught)
            event('BATCH_STOPPED', number=calls, returncode=child_code, error=error,
                  original_slot_action='Preserve all guard/slot files; no automatic retry or recovery')
        result = {'schema_version': 1, 'scope': SCOPE, 'finished_utc': now(), 'status': status, 'error': error,
            'manifest': manifest_binding, 'guard_calls_this_batch': calls, 'closed_slots_this_batch': len(seen),
            'observed_terminal_status_counts': dict(statuses), 'guard_reported_pending_slots': pending,
            'pending_count_current_after_verified_completion': status == 'GUARD_PENDING_EXHAUSTED',
            'remaining_at_batch_entry': initial,
            'already_consumed_before_batch': TOTAL-initial if initial is not None else None,
            'scheduled_slots': TOTAL, 'automatic_retry': False,
            'completion_boundary': 'Zero PENDING reported by the existing guard; original FAIL/unknown evidence and all280 denominator remain. This is not all-PASS or project acceptance.'}
        write_new(output/'summary.json', result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--guard-command', nargs=argparse.REMAINDER, required=True,
                        help='Last option: argv prefix ending in the original guard.py; wrapper appends run-one --manifest')
    args = parser.parse_args(argv)
    try:
        result = run(args.manifest, args.output, args.guard_command)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result['status'] == 'GUARD_PENDING_EXHAUSTED' else 2
    except (OSError, ValueError, TypeError, KeyError) as caught:
        print(json.dumps({'status': 'REFUSED_BEFORE_BATCH', 'error': type(caught).__name__+': '+str(caught),
                          'automatic_retry': False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
