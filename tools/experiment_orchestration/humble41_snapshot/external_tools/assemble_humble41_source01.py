"""Assemble pending Humble41 source review from actual clean committed bytes.

Actual40 stopped core remains 3 PASS / 1 infrastructure error / 8 pending.
The generic predecessor boundary uses its healthy build, never runtime success.
This helper only writes new pending metadata; it never publishes final source
review, a runtime contract, a freeze, a build, or a flight.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True

EXTERNAL = Path(__file__).resolve().parent
TOOL_STATUS = 'DRAFT_PENDING_INDEPENDENT_TOOL_AND_FAKE_REVIEW'
OWN_FILES = ('assemble_humble41_source01.py', 'test_assemble_humble41_source01.py')
NEW_ROOT = '/root/uav_tracking_fullplan_v4_humble41'
BASE_ROOT = '/root/uav_tracking_fullplan_v4_humble40'
BASE_COMMIT = '0f75efc724875647e8c15d264e64da9f4fa0af78'
EXPECTED_DELTA = {'changed': ['scripts/observe_runtime_health.py'],
                  'added': ['tests/test_runtime_health_live_output.py'], 'removed': []}
CORE_RELATIVE = 'reliability_v4_humble40_probe01_seed004_matrix'
STOPPED_REVIEW_NAME = 'humble40_core_stopped_fault_independent01.json'
EXPECTED_COUNTS = {'PASS': 3, 'INFRASTRUCTURE_ERROR': 1, 'PENDING': 8}
MAGNETIC = 'config/px4_magnetic_runtime.json'
MAX_SMALL = 16 * 1024**2
CLOSED = {'PASS', 'FAIL', 'INCOMPLETE_EVIDENCE', 'EVALUATION_PENDING',
          'INFRASTRUCTURE_ERROR', 'INTERRUPTED'}


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def small(path):
    path = Path(path)
    require(path.suffix == '.json' and path.is_file() and not path.is_symlink()
            and path.stat().st_size <= MAX_SMALL, 'Named small regular JSON required: '+str(path))
    raw = path.read_bytes()
    require(len(raw) <= MAX_SMALL, 'Metadata grew beyond the small-file bound')
    value = json.loads(raw.decode('utf-8-sig'),
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError('Nonfinite JSON: '+token)))
    require(isinstance(value, dict), 'JSON object required')
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tool_manifest():
    generic = importlib.import_module('reviewed_freeze_build')
    require(Path(generic.__file__).resolve(strict=True) == (EXTERNAL/'reviewed_freeze_build.py').resolve(strict=True),
            'Stable source assembly dependency escaped its reviewed directory')
    files = {}
    for name in OWN_FILES:
        path = EXTERNAL/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL,
                'Missing bounded released assembler/test: '+name)
        files[name] = sha(path)
    return {'schema_version': 1, 'scope': 'HUMBLE41_OBSERVER_ONLY_SOURCE_PENDING_ASSEMBLY_ONLY',
        'files': files, 'generic_tools_canonical_sha256': canonical(generic.tools_manifest()),
        'predecessor_root': BASE_ROOT, 'new_root': NEW_ROOT,
        'requires_actual_clean_commit': True, 'requires_actual_stopped40_core_and_independent_review_sha256': True,
        'allowed_source_delta': EXPECTED_DELTA, 'single_car_probe_required': False,
        'writes_pending_metadata_only': True, 'final_review_created': False,
        'runtime_contract_created': False, 'payload_reread': False, 'formal_seed_use_authorized': False}


def lin(path):
    value = Path(path).resolve(strict=True).as_posix()
    require(value.startswith('D:/'), 'Explicit D-drive metadata/source is required')
    return '/mnt/d/'+value[3:]


def win(path):
    require(isinstance(path, str) and path.startswith('/mnt/d/')
            and '..' not in path.split('/'), 'Unsupported inherited metadata path')
    return Path('D:/'+path[len('/mnt/d/'):])


def write_pending(path, value):
    raw = json.dumps(value, indent=2, allow_nan=False)+'\n'
    require(len(raw.encode()) <= MAX_SMALL, 'Pending metadata exceeds the bounded schema')
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(raw)


def closed40_capsule(root, prior, prior_path, manifest_path, expected_terminal_sha, expected_fault_review_sha):
    """Build closure stays healthy; stopped runtime and its pending cells stay stopped."""
    for digest in (expected_terminal_sha, expected_fault_review_sha):
        require(re.fullmatch('[0-9a-f]{64}', digest or ''), 'Explicit stopped40 driver/review SHA required')
    inherited_path = win(prior['closed_evidence']['path'])
    require(sha(inherited_path) == prior['closed_evidence']['sha256'], 'Inherited closed capsule changed')
    inherited = small(inherited_path)
    require(inherited.get('all_inputs_closed') is True and inherited.get('payload_reread') is False
        and inherited.get('readiness_claimed') is False
        and inherited.get('predecessor38_core12', {}).get('status_counts') == {'PASS': 11, 'FAIL': 1}
        and inherited.get('predecessor39_singleprobe', {}).get('status') == 'FAIL',
        'Older38/39 outcomes must remain in the unchanged inherited capsule')
    files, facts = {}, []
    def retain(path, *fields):
        path = Path(path); value = small(path); name = lin(path)
        files[name] = {'sha256': sha(path), 'bytes': path.stat().st_size}
        for field in fields or tuple(value):
            actual = value
            for part in field.split('.'):
                require(isinstance(actual, dict) and part in actual, 'Missing retained field: '+field)
                actual = actual[part]
            facts.append({'path': name, 'field': field, 'expected': deepcopy(actual)})
        return value
    # Only original32 remains direct. Older39 paths are outside the generic
    # baseline40 allow-list, so preserve its already-bound external capsule.
    for name, old in inherited['files'].items():
        if '/results/frozen_fullplan_v4_humble32/' in name:
            retain(win(name))
            require(files[name] == old, 'Original32 closed metadata changed')
    require(len(files) == 13, 'Original32 requires exactly its named13 metadata files')
    retain(inherited_path, 'all_inputs_closed', 'payload_reread', 'readiness_claimed',
           'predecessor38_core12', 'predecessor39_singleprobe')
    retain(prior_path, 'source_commit', 'files', 'classified_source_hashes', 'closed_evidence')
    retain(manifest_path)
    results = root/'results/frozen_fullplan_v4_humble40'
    matrix = results/CORE_RELATIVE
    plan_path = matrix/'plan.json'; plan = retain(plan_path)
    expected_ids = [f'{cls}_{group}_seed004' for cls in ('person', 'car') for group in
        ('stage1_velocity', 'stage1_position', 'stage2_crossing', 'stage3_midpoint', 'stage3_active', 'stage3_multi_active')]
    require(plan.get('mode') == 'PROBE' and plan.get('source_hashes') == prior['classified_source_hashes']
        and plan.get('protocol_sha256') == prior['files'].get('planning/reliability-v4-preregistration.json')
        and plan.get('plan_sha256') == canonical({k:v for k,v in plan.items() if k != 'plan_sha256'})
        and [trial.get('id') for trial in plan.get('trials', [])] == expected_ids,
        'Actual40 immutable complete12 plan required; not a completed12 claim')
    terminal_path = matrix/'observed_driver01/execution_terminal.json'
    require(sha(terminal_path) == expected_terminal_sha, 'Actual40 stopped driver bytes changed')
    terminal = retain(terminal_path)
    entry = terminal.get('entry_binding_before', {})
    common = entry.get('common_probe40_binding', {})
    source = common.get('source', {})
    require(terminal.get('scope') == 'HUMBLE40_CORE12_NORMAL_RUNNER_DEVELOPMENT_ONLY'
        and type(terminal.get('returncode')) is int and terminal['returncode'] == 2
        and terminal.get('status') == 'STOPPED_ORIGINAL_ATTEMPTS_RETAINED'
        and terminal.get('error') == 'ValueError:Incomplete/infrastructure attempt requires diagnosis: person_stage3_midpoint_seed004'
        and isinstance(terminal.get('finished_utc'), str)
        and terminal.get('final_errors') == ['observer:ValueError:Rolling observer aggregate is incomplete or unhealthy']
        and terminal.get('cleanup', {}).get('residual_processes') == []
        and terminal.get('entry_binding_after') == entry
        and source.get('manifest_sha256') == sha(manifest_path)
        and source.get('freeze_source_sha256') == canonical(prior['files'])
        and common.get('source_review') == {'path':lin(prior_path), 'sha256':sha(prior_path)}
        and terminal.get('observer') is None
        and all(terminal.get(key) is False for key in ('formal_seed_use_authorized', 'readiness_claimed', 'automatic_retry', 'automatic_next_action')),
        'Original stopped40 fault/source/cleanup must remain explicit and unchanged')
    require(terminal.get('planned_count') == 12 and terminal.get('attempt_count') == 4
        and terminal.get('terminal_count') == 3 and terminal.get('status_counts') == EXPECTED_COUNTS
        and terminal.get('slot_read_error') is None
        and [a.get('slot') for a in terminal.get('attempts', [])] == expected_ids[:4]
        and [a.get('slot') for a in terminal.get('slots', [])] == expected_ids[:3],
        'Original40 audit3/attempt4/planned12 denominator differs')
    statuses = {}
    for index, trial in enumerate(plan['trials']):
        slot = trial['id']; path = matrix/'slots'/(slot+'.json')
        marker_path = matrix/'slots'/(slot+'.started.json')
        driver_marker = matrix/'observed_driver01'/f'{index+1:02d}_{slot}.started.json'
        attempt_path = matrix/'observed_driver01'/f'{index+1:02d}_{slot}.attempt_terminal.json'
        if index >= 4:
            require(not any(p.exists() or p.is_symlink() for p in (path, marker_path, driver_marker, attempt_path)),
                'Original40 pending cell was attempted after the stop')
            statuses[slot] = {'status':'PENDING', 'record_sha256':None}
            continue
        record = retain(path); marker = retain(marker_path); retain(driver_marker)
        attempt = retain(attempt_path)
        expected = 'PASS' if index < 3 else 'INFRASTRUCTURE_ERROR'
        require(record.get('id') == slot and record.get('status') == expected
            and record.get('engineering_result') == ('PASS' if index < 3 else 'FAIL')
            and record.get('execution_status') == 'COMPLETED'
            and record.get('infrastructure_stop') is (index == 3)
            and record.get('record_sha256') == canonical({k:v for k,v in record.items() if k != 'record_sha256'})
            and record.get('plan_sha256') == marker.get('plan_sha256') == plan['plan_sha256']
            and marker.get('id') == slot and marker.get('flight_command') == trial.get('flight_command')
            and marker.get('started_utc') == record.get('started_utc')
            and attempt == terminal['attempts'][index]
            and attempt.get('record', {}).get('record_binding', {}).get('sha256') == sha(path)
            and attempt['record']['record_binding'].get('record_sha256') == record['record_sha256'],
            'Original40 slot/attempt/start bytes or retained status differ: '+slot)
        statuses[slot] = {'status':expected, 'record_sha256':record['record_sha256']}
        if index == 3:
            flight = record.get('commands', [{}])[0]
            require(len(record.get('commands', [])) == 1 and record.get('evaluations') == []
                and record.get('flight_exit_code') == flight.get('returncode') == -2
                and flight.get('command') == trial.get('flight_command')
                and flight.get('error') == 'RuntimeError:Latest complete observer sample is stale or future: 25.23778100799973'
                and attempt.get('audit') is None
                and attempt.get('runner_result', {}).get('status_counts') == EXPECTED_COUNTS
                and attempt['runner_result'].get('terminal_count') == 4
                and attempt['runner_result'].get('pending_ids') == expected_ids[4:],
                'Fourth40 infrastructure stop cannot be regraded or completed')
    require(terminal.get('actual_slot_statuses') == statuses, 'Original40 persisted statuses contradict its denominator')
    observer_root = matrix/'observed_driver01/observer_driver'
    aggregate = retain(observer_root/'execution_terminal.json')
    session = retain(observer_root/'session_001/execution_terminal.json')
    require(aggregate.get('healthy_cleanup') is False and aggregate.get('driver_exception') is True
        and aggregate.get('max_sample_age_wall_s') == 10.0
        and len(aggregate.get('sessions', [])) == 1
        and aggregate['sessions'][0].get('terminal') == session
        and aggregate['sessions'][0].get('terminal_binding', {}).get('sha256') == sha(observer_root/'session_001/execution_terminal.json')
        and session.get('observer_exit_code') == 0 and session.get('healthy_cleanup') is False
        and session.get('driver_exception') is True, 'Original40 unhealthy observer must remain unhealthy')
    review_path = EXTERNAL/STOPPED_REVIEW_NAME
    require(sha(review_path) == expected_fault_review_sha, 'Independent stopped40 fault review changed')
    fault = retain(review_path)
    require(fault.get('status') == 'INDEPENDENT_SOURCE40_CORE_STOPPED_FAULT_RECORD_CLOSURE_RETAINED'
        and fault.get('driver', {}).get('sha256') == expected_terminal_sha
        and fault.get('counts', {}).get('status_counts') == EXPECTED_COUNTS
        and fault['counts'].get('planned') == 12 and fault['counts'].get('original_driver_attempt_count') == 4
        and fault['counts'].get('original_driver_terminal_count') == 3
        and fault['counts'].get('normal_runner_terminal_count') == 4
        and fault.get('unattempted8') == expected_ids[4:]
        and all(fault.get(key) is False for key in ('original04_regraded', 'payload_read', 'formal_seed_use_authorized', 'readiness_claimed')),
        'Independent40 stop retention cannot authorize runtime acceptance or recovery')
    build = common.get('build_metadata', {})
    summary_path = results/'freeze_validation/build_validation_summary.json'
    summary = retain(summary_path)
    require(summary.get('status') == 'PASS' and summary.get('returncode') == 0
        and summary.get('source_unchanged') is True and summary.get('four_packages_built') is True
        and summary.get('module_ament_isolation') is True
        and summary.get('source_binding_before') == summary.get('source_binding_after') == source
        and build.get('summary') == {'path':BASE_ROOT+'/results/freeze_validation/build_validation_summary.json','sha256':sha(summary_path)},
        'Actual40 healthy build boundary differs from original source')
    for action in ('build', 'validate'):
        path = EXTERNAL/f'reviewed_freeze_actions_v4_humble40/{action}/action.terminal.json'
        value = retain(path)
        require(value.get('scope') == 'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE'
            and value.get('status') == 'PASS' and type(value.get('direct_child_returncode')) is int
            and value['direct_child_returncode'] == 0
            and value.get('binding_before', {}).get('source') == value.get('binding_after', {}).get('source')
            and value['binding_before']['source'].get('freeze_source_sha256') == canonical(prior['files'])
            and value.get('cleanup', {}).get('actual_proc_group_empty') is True
            and value['cleanup'].get('direct_child_reaped') is True and value['cleanup'].get('residual_processes') == []
            and build.get(action+'_terminal') == {'path':lin(path), 'sha256':sha(path)},
            'Actual40 predecessor build action must be independently healthy: '+action)
    predecessor = lin(EXTERNAL/'reviewed_freeze_actions_v4_humble40/validate/action.terminal.json')
    return {'schema_version':1, 'scope':'CLOSED_32_CORE_AND_PREDECESSOR_METADATA_ONLY',
        'all_inputs_closed':True, 'payload_reread':False, 'readiness_claimed':False,
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'assembly_status':'ACTUAL40_BUILD_CLOSED_AND_RUNTIME_STOPPED_RETAINED_NOT_ACCEPTANCE',
        'files':dict(sorted(files.items())), 'retained_fields':facts,
        'boundaries':{'original32_core':deepcopy(inherited['boundaries']['original32_core']),
                      'predecessor':{'closed':True,'receipt':predecessor}},
        'predecessor38_core12':deepcopy(inherited['predecessor38_core12']),
        'predecessor39_singleprobe':deepcopy(inherited['predecessor39_singleprobe']),
        'predecessor40_core_stopped':{'plan':lin(plan_path), 'driver':lin(terminal_path),
            'fault_review':lin(review_path), 'planned_count':12, 'attempt_count':4,
            'driver_audited_terminal_count':3, 'persisted_terminal_count':4,
            'status_counts':dict(EXPECTED_COUNTS), 'pending_ids':expected_ids[4:],
            'runtime_acceptance':False, 'retry_or_resume_authorized':False, 'readiness_claimed':False},
        'claim_boundary':'Closed metadata and healthy40 build only. Original40 runtime stopped3PASS/1INFRA/8PENDING and unhealthy observer remain; all_inputs_closed does not mean all planned flights completed. No new runtime acceptance, retry, required single-car probe or formal-seed authority.'}

def assemble_pending(args):
    require(re.fullmatch('[0-9a-f]{64}', args.reviewed_tools_sha256 or '')
        and canonical(tool_manifest()) == args.reviewed_tools_sha256, 'Explicit independently reviewed assembler tools SHA required')
    require(re.fullmatch('[0-9a-f]{40}', args.commit or ''), 'Actual clean full41 commit is required')
    require(re.fullmatch('[0-9a-f]{64}', args.baseline_review_sha256 or ''), 'Actual40 review SHA required')
    require(re.fullmatch('[0-9a-f]{64}', args.core_terminal_sha256 or ''),
            'Explicit independently checked actual40 stopped core driver SHA required')
    require(re.fullmatch('[0-9a-f]{64}', args.stopped_core_review_sha256 or ''),
            'Explicit independent stopped40 fault-review SHA required')
    root = Path(args.source_root).resolve(strict=True)
    prior_path = Path(args.baseline_review).resolve(strict=True)
    require(sha(prior_path) == args.baseline_review_sha256, 'Actual40 source review changed')
    prior = small(prior_path)
    require(prior['frozen_root'] == BASE_ROOT and prior['source_commit'] == BASE_COMMIT and lin(root) == prior['source_root'], 'Actual40 source/root required')
    sys.path.insert(0, str(EXTERNAL))
    generic = importlib.import_module('reviewed_freeze_build')
    generic.validate_review(prior)
    require(canonical(generic.tools_manifest()) == prior['toolchain_canonical_sha256'], 'Stable generic tools changed')
    git = lambda *tokens: subprocess.check_output(['git', '-c', 'core.quotepath=false',
        '-c', 'core.autocrlf=true', '-C', str(root), *tokens])
    require(not git('status', '--porcelain=v1') and git('rev-parse', 'HEAD').decode().strip() == args.commit,
            'Actual clean committed source is required')
    subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', prior['source_commit'], args.commit], check=True)
    manifest_path = root/'results/frozen_fullplan_v4_humble40/freeze_validation/source_freeze_manifest.json'
    manifest = small(manifest_path)
    require(manifest['files'] == prior['files'] and manifest['source_commit'] == prior['source_commit']
        and manifest['freeze_source_sha256'] == canonical(prior['files']), 'Actual40 manifest differs')
    tracked = sorted(name.decode('utf-8') for name in git('ls-files', '-z').split(b'\0') if name)
    ignored = prior['assembly_provenance']['inherited_ignored_resources']
    require(len(ignored) == 9 and not set(ignored) & set(tracked), 'Inherited source resource set differs')
    files = {}
    for name in sorted(tracked+ignored):
        path = root/name
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root), 'Unsafe source: '+name)
        files[name] = prior['source_overrides'][name]['sha256'] if name == MAGNETIC else sha(path)
    actual_delta = generic.delta(prior['files'], files)
    require(actual_delta == EXPECTED_DELTA, 'Only the observer and its new live-output test may differ from source40')
    committed_delta = {'changed': [], 'added': [], 'removed': []}
    for row in git('diff', '--no-renames', '--name-status', prior['source_commit'], args.commit, '--').decode().splitlines():
        kind, name = row.split('\t')
        require(kind in {'M', 'A', 'D'}, 'Unsupported non-file source delta')
        committed_delta[{'M': 'changed', 'A': 'added', 'D': 'removed'}[kind]].append(name)
    require(actual_delta == {key: sorted(value) for key, value in committed_delta.items()}, 'Actual/git source byte delta differs')
    for name in actual_delta['changed']+actual_delta['added']:
        require((root/name).read_bytes() == git('show', args.commit+':'+name), 'Source is not committed bytes: '+name)
    sys.path.insert(0, str(root))
    runner = importlib.import_module('scripts.run_reliability_v4')
    classified = runner.source_hashes(root)
    classified[MAGNETIC] = files[MAGNETIC]
    require(all(files.get(name) == digest for name, digest in classified.items()), 'Incomplete classified source map')
    protocol_path = root/runner.PROTOCOL_PATH
    protocol = small(protocol_path)
    runner.validate_protocol(protocol)
    require(runner.simulation_pacing_summary(protocol) == runner.SIMULATION_PACING_V2
        and runner.exclusive_navigation_summary(protocol) == {'person': False, 'car': True},
        'Only unchanged pacing and original car-only exclusive policy are supported')
    review_path = EXTERNAL/'reviewed_freeze_review_humble41_pending01.json'
    capsule_path = EXTERNAL/'reviewed_freeze_closed_humble41_pending01.json'
    require(not any(path.exists() or path.is_symlink() for path in (review_path, capsule_path,
        root/'results/frozen_fullplan_v4_humble41',
        EXTERNAL/'reviewed_freeze_review_humble41_01.json',
        EXTERNAL/'reviewed_freeze_actions_v4_humble41')), 'Never overwrite pending/frozen41 paths')
    capsule = closed40_capsule(root, prior, prior_path, manifest_path,
        args.core_terminal_sha256, args.stopped_core_review_sha256)
    capsule_raw = json.dumps(capsule, indent=2, allow_nan=False)+'\n'
    capsule_digest = hashlib.sha256(capsule_raw.encode('utf-8')).hexdigest()
    capsule_linux_path = lin(capsule_path.parent)+'/'+capsule_path.name
    review = deepcopy(prior)
    review.pop('independent_review_receipt', None)
    review.update(status='PENDING_ROOT_INDEPENDENT_REVIEW_NOT_EXECUTABLE',
        created_utc=datetime.now(timezone.utc).isoformat(), source_commit=args.commit, frozen_root=NEW_ROOT,
        results_root=prior['source_root']+'/results/frozen_fullplan_v4_humble41', files=files,
        classified_source_hashes=classified, allowed_delta=actual_delta,
        baseline={'source_commit': prior['source_commit'], 'root': BASE_ROOT,
            'manifest_path': lin(manifest_path), 'manifest_sha256': sha(manifest_path),
            'files_canonical_sha256': canonical(prior['files'])},
        closed_evidence={'path': capsule_linux_path, 'sha256': capsule_digest},
        candidate_protocol={'path': lin(protocol_path), 'sha256': sha(protocol_path),
            'status': 'COMMITTED_SOURCE_ONLY_NOT_FROZEN_NOT_EXECUTED', 'car_surface_enabled': True,
            'exclusive_navigation': {'person': False, 'car': True},
            'pacing_revision': runner.SIMULATION_PACING_V2['revision']},
        assembly_provenance={'status': 'ACTUAL41_OBSERVER_ONLY_SOURCE_AND_STOPPED40_RUNTIME_METADATA_PENDING_REVIEW',
            'source_file_count': len(files), 'classified_source_count': len(classified),
            'tracked_file_count': len(tracked), 'inherited_ignored_resources': deepcopy(ignored),
            'files_canonical_sha256': canonical(files), 'classified_canonical_sha256': canonical(classified),
            'predecessor_source_review': {'path': lin(prior_path), 'sha256': sha(prior_path)},
            'formal_or_runtime_acceptance_claimed': False})
    review['formal_seed_use_authorized'] = False
    review['flight_actions_authorized'] = False
    review['automatic_next_action'] = False
    review['additional_import_modules'] = sorted(set(prior.get('additional_import_modules', []))
        | set(args.additional_import_module))
    schema_only = deepcopy(review)
    schema_only['status'] = generic.FINAL_STATUS
    generic.validate_review(schema_only)  # In-memory schema check; no final publication.
    # Validate both candidates before creating either exclusive output.
    require(all(len((json.dumps(value, indent=2, allow_nan=False)+'\n').encode('utf-8')) <= MAX_SMALL
        for value in (capsule, review)), 'Pending metadata exceeds the bounded schema')
    require(not git('status', '--porcelain=v1') and git('rev-parse', 'HEAD').decode().strip() == args.commit,
            'Actual clean committed source must remain unchanged through pending publication')
    write_pending(capsule_path, capsule)
    require(sha(capsule_path) == capsule_digest, 'New pending capsule bytes differ from their prospective binding')
    write_pending(review_path, review)
    return {'status': 'PENDING_ONLY_NOT_EXECUTABLE', 'review': str(review_path), 'review_sha256': sha(review_path),
        'closed_capsule': str(capsule_path), 'closed_capsule_sha256': sha(capsule_path),
        'final_review_created': False, 'runtime_contract_created': False, 'flight_or_formal_action': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', 'assemble-pending'))
    parser.add_argument('--source-root', type=Path, default=Path.cwd())
    parser.add_argument('--commit')
    parser.add_argument('--baseline-review', type=Path,
        default=EXTERNAL/'reviewed_freeze_review_humble40_01.json')
    parser.add_argument('--baseline-review-sha256')
    parser.add_argument('--core-terminal-sha256')
    parser.add_argument('--stopped-core-review-sha256')
    parser.add_argument('--reviewed-tools-sha256')
    parser.add_argument('--additional-import-module', action='append', default=[])
    args = parser.parse_args(argv)
    if args.action == 'describe':
        print(json.dumps({'status': TOOL_STATUS, 'tool_manifest': tool_manifest(),
            'tools_canonical_sha256': canonical(tool_manifest()),
            'new_root': NEW_ROOT, 'predecessor_root': BASE_ROOT,
            'assembly_interface_enabled': True, 'actual_action_executed': False,
            'final_review_or_runtime_contract_created': False}, indent=2))
        return 0
    try:
        result = assemble_pending(args)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as caught:
        print(json.dumps({'status': 'SOURCE_PENDING_ASSEMBLY_REFUSED_OR_FAILED',
            'reason': type(caught).__name__+':'+str(caught),
            'final_review_created': False, 'runtime_contract_created': False}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
