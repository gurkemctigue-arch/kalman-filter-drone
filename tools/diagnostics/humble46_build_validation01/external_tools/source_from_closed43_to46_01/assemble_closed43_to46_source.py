"""Healthy43 -> fresh46 PENDING source adapter; preserve failed44/stopped45.

SOURCE PREPARATION ONLY. Both real commit and independently reviewed complete
source-map pins must be fixed before execution. No WSL startup, build, flight,
formal registration or automatic next action is performed by this adapter.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
EXTERNAL = HERE.parent
ADAPTER45_SHA = '96446f5e18d8c6fae813dd36f3edf018346d01cd0ca7f81b3031aa8f84547607'
# Root will supply real committed source and prospective independent review.
# Never substitute a guessed commit or self-certified current working tree.
NEW_COMMIT = 'de89a6696d60a113929c97bab775dc2258ef4d01'
SOURCE_PINS_SHA = '427be692d9706aa901b3843d92f5422ebff5cc076bbfd5f0942290af066ec4d8'
SOURCE_PINS = HERE/'reviewed_commit46_maps01.json'
HISTORY_PINS = HERE/'historical45_metadata_pins01.json'
HISTORY_PINS_SHA = 'c386b25fd3998ab44917881c944d1eb70afc7db608e169c6a47c7412bcb7a483'
ROOT45 = '/root/uav_tracking_fullplan_v4_humble45'
COMMIT45 = '57dd00965b749c64060cd86409fa6e68feb1c10a'
REVIEW45_SHA = 'a526b2e342bc2b5889266ef15592656f5c98eb7833bed33856d0c2d084d69b50'
MANIFEST45_SHA = 'e85627c38791ffda37ee1a53ea29e4a2adfc4ce204c80f016dfb9aca00952c02'
MAP45_SHA = '7013fa62edddc400379a5b6fdb3c6700f3ee74e38208f90d8062227c4ca7e2b6'
CORE45_SHA = '7de32e4471c90bee52f02ea886a8b3c87e5ef5011e4d97855e21234b1109ebcb'
MATRIX45 = 'reliability_v4_humble45_probe01_seed004_matrix'
COUNTS45 = {'PASS': 1, 'INFRASTRUCTURE_ERROR': 1, 'PENDING': 10}
OWNER_ERROR45 = 'observer:ValueError:Owner outcome differs from original immutable D copy candidate'


def reused():
    path = EXTERNAL/'source_from_closed43_to45_01/assemble_closed43_to45_source.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != ADAPTER45_SHA:
        raise ValueError('Original45 narrow metadata adapter changed')
    spec = importlib.util.spec_from_file_location('_unchanged_source45_adapter', path)
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    return prior, *prior.reused()


def retain45_history(source, r, helper, generic, directory):
    """Copy exactly34 pinned small metadata originals, never bags or health data."""
    require = generic.require
    require(helper.sha(HISTORY_PINS) == HISTORY_PINS_SHA, 'Original45 metadata inventory changed')
    inventory = helper.read_small(HISTORY_PINS)
    require(inventory.get('scope') == 'EXACT45_SMALL_METADATA_ORIGINAL_PINS_NOT_RUNTIME_ACCEPTANCE'
            and inventory.get('payloads_read') is False and len(inventory.get('files', [])) == 34,
            'Exact bounded45 original metadata inventory required')
    require(not directory.exists() and not directory.is_symlink(), 'Fresh46 historical45 copy directory required')
    roots = {'external': EXTERNAL, 'results45': source/'results/frozen_fullplan_v4_humble45'}
    originals, copies = {}, {}
    for row in inventory['files']:
        require(row['origin'] in roots and generic.valid_sha(row['sha256'])
                and type(row['bytes']) is int and 0 <= row['bytes'] <= generic.MAX_SMALL,
                'Invalid historical45 pin')
        relative = generic.relative(row['relative_path'])
        path = roots[row['origin']]/relative
        key = row['origin']+'/'+row['relative_path']
        require(key not in originals and path.is_file() and not path.is_symlink()
                and path.resolve(strict=True).is_relative_to(roots[row['origin']].resolve(strict=True))
                and path.stat().st_size == row['bytes'] and helper.sha(path) == row['sha256'],
                'Original45 metadata changed: '+key)
        originals[key] = (path, row)
    directory.mkdir(exist_ok=False)
    for key, (path, row) in originals.items():
        target = directory/key
        generic.copy_registered_file(path, target, row['sha256'])
        require(target.stat().st_size == row['bytes'] and helper.sha(path) == row['sha256'],
                'Original45 metadata changed during copy: '+key)
        if target.suffix == '.json':
            r.retain(target, expected_sha=row['sha256'], expected_bytes=row['bytes'])
        else:
            r.files[str(target)] = {'sha256': row['sha256'], 'bytes': row['bytes']}
        copies[key] = {'original': {'path': str(path), 'sha256': row['sha256'], 'bytes': row['bytes']},
                       'external_copy': {'path': str(target), 'sha256': row['sha256'], 'bytes': row['bytes']},
                       'original_before_after_unchanged': True}

    def copied(origin, relative, fields=()):
        row = originals[origin+'/'+relative][1]
        return r.retain(directory/origin/relative, fields, row['sha256'], row['bytes'])

    review45 = copied('external', 'reviewed_freeze_review_v4_humble45_01.json',
                      ('source_commit', 'frozen_root', 'files', 'closed_evidence'))
    require(helper.sha(directory/'external/reviewed_freeze_review_v4_humble45_01.json') == REVIEW45_SHA,
            'Original45 final source review pin differs')
    generic.validate_review(review45)
    require(review45['source_root'] == str(source) and review45['source_commit'] == COMMIT45
            and review45['frozen_root'] == ROOT45, 'Actual45 original source review required')
    manifest = copied('results45', 'freeze_validation/source_freeze_manifest.json')
    require(helper.sha(directory/'results45/freeze_validation/source_freeze_manifest.json') == MANIFEST45_SHA
            and manifest['source_commit'] == COMMIT45 and manifest['source_root'] == ROOT45
            and manifest['files'] == review45['files']
            and manifest['freeze_source_sha256'] == generic.canonical(manifest['files']) == MAP45_SHA,
            'Original45 complete frozen source identity differs')
    actions = {}
    for action in ('build', 'validate'):
        value = copied('external', 'reviewed_freeze_actions_v4_humble45/'+action+'/action.terminal.json',
                       ('status', 'direct_child_returncode', 'cleanup'))
        bound = value.get('binding_before', {})
        require(value.get('scope') == 'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE'
                and value.get('action') == action and value.get('status') == 'PASS'
                and type(value.get('direct_child_returncode')) is int and value['direct_child_returncode'] == 0
                and bound == value.get('binding_after') and isinstance(value.get('finished_utc'), str)
                and bound.get('source', {}).get('manifest_sha256') == MANIFEST45_SHA
                and bound['source'].get('freeze_source_sha256') == MAP45_SHA
                and value.get('cleanup', {}).get('actual_proc_group_empty') is True
                and value['cleanup'].get('direct_child_reaped') is True
                and value['cleanup'].get('residual_processes') == [], 'Original45 healthy build/validate differs')
        actions[action] = {'status': 'PASS', 'direct_child_returncode': 0, 'cleanup_closed': True}
    summary = copied('results45', 'freeze_validation/build_validation_summary.json',
        ('status', 'returncode', 'tests', 'skipped', 'execution_count', 'source_unchanged',
         'source_binding_before', 'source_binding_after'))
    require(summary.get('status') == 'PASS' and summary.get('returncode') == 0
            and summary.get('tests') == 1767 and summary.get('skipped') == 5
            and summary.get('execution_count') == 1 and summary.get('source_unchanged') is True
            and summary.get('source_binding_before') == summary.get('source_binding_after')
            and summary['source_binding_before'].get('manifest_sha256') == MANIFEST45_SHA
            and summary['source_binding_before'].get('freeze_source_sha256') == MAP45_SHA
            and summary['suite_log_sha256'] == helper.sha(directory/'results45/freeze_validation/unittest.log'),
            'Original45 suite1767/5 healthy result differs')
    footer = (directory/'results45/freeze_validation/unittest.log').read_text(encoding='utf-8').splitlines()
    require([line for line in footer if line.startswith('OK (')] == ['OK (skipped=5)']
            and not any(line.startswith(('ERROR: ', 'FAIL: ', 'FAILED (')) for line in footer),
            'Actual45 successful suite footer differs')
    prefix = MATRIX45+'/'
    core = copied('results45', prefix+'observed_driver01/execution_terminal.json',
        ('status', 'returncode', 'planned_count', 'attempt_count', 'terminal_count', 'status_counts',
         'actual_slot_statuses', 'final_errors', 'observer_owner_terminal'))
    require(helper.sha(directory/'results45'/prefix/'observed_driver01/execution_terminal.json') == CORE45_SHA
            and core.get('status') == 'STOPPED_ORIGINAL_ATTEMPTS_RETAINED' and core.get('returncode') == 2
            and core.get('planned_count') == 12 and core.get('attempt_count') == 2
            and core.get('terminal_count') == 1 and core.get('status_counts') == COUNTS45
            and core.get('final_errors') == [OWNER_ERROR45]
            and core.get('cleanup', {}).get('residual_processes') == [], 'Original45 stopped/owner failure changed')
    require(core['entry_binding_before'] == core['entry_binding_after']
            and core['entry_binding_before']['source_review']['sha256'] == REVIEW45_SHA
            and core['entry_binding_before']['source']['manifest_sha256'] == MANIFEST45_SHA
            and core['entry_binding_before']['source']['freeze_source_sha256'] == MAP45_SHA,
            'Original45 core source identity changed')
    plan = copied('results45', prefix+'plan.json')
    require(plan['frozen_root'] == ROOT45 and plan['plan_sha256'] == core['plan']['plan_sha256']
            and generic.canonical({k:v for k,v in plan.items() if k != 'plan_sha256'}) == plan['plan_sha256'],
            'Original45 plan self digest changed')
    statuses = core['actual_slot_statuses']
    require(len(statuses) == 12 and list(statuses) == core['plan']['slot_ids']
            and dict(Counter(row['status'] for row in statuses.values())) == COUNTS45
            and len(core['attempts']) == 2 and len(core['slots']) == 1,
            'Original45 full planned denominator changed')
    for index, (mode, status) in enumerate((('velocity', 'PASS'), ('position', 'INFRASTRUCTURE_ERROR')), 1):
        slot = 'person_stage1_'+mode+'_seed004'
        record = copied('results45', prefix+'slots/'+slot+'.json',
                        ('status', 'engineering_result', 'evaluations', 'flight_exit_code', 'infrastructure_stop'))
        require(record['id'] == slot and record['status'] == statuses[slot]['status'] == status
                and record['record_sha256'] == statuses[slot]['record_sha256']
                and record['record_sha256'] == generic.canonical({k:v for k,v in record.items() if k != 'record_sha256'})
                and record['plan_sha256'] == plan['plan_sha256'], 'Original45 slot digest/status changed')
        attempt = copied('results45', prefix+'observed_driver01/%02d_%s.attempt_terminal.json' % (index, slot))
        require(attempt == core['attempts'][index-1] and attempt['number'] == index
                and attempt['slot'] == slot and attempt['record']['status'] == status,
                'Original45 attempted slot order changed')
        for kind in ('recording_closure.json', 'bag_integrity.json'):
            report = copied('results45', 'reliability_v4_humble45_probe01_'+slot+'/'+kind, ('status',))
            require(report['status'] == 'PASS', 'Original45 recording closure/integrity differs')
        if mode == 'position':
            require(record['engineering_result'] == 'FAIL' and record['evaluations'] == []
                    and record['flight_exit_code'] == 1 and record['infrastructure_stop'] is True
                    and attempt.get('audit') is None and attempt.get('error'),
                    'Original45 infrastructure failure cannot gain evaluations/acceptance')
    for slot, row in statuses.items():
        if row['status'] == 'PENDING':
            path = source/'results/frozen_fullplan_v4_humble45'/MATRIX45/'slots'
            require(row.get('record_sha256') is None and not (path/(slot+'.json')).exists()
                    and not (path/(slot+'.started.json')).exists(), 'Untouched45 slots changed')
    owner = core['observer_owner_terminal']
    copy = copied('results45', prefix+'observed_driver01/observer_driver/execution_terminal.json',
                  ('status', 'healthy_cleanup'))
    native = copied('results45', prefix+'observed_driver01/observer_driver/native_exit_terminal.json',
                    ('driver_exception', 'healthy_cleanup'))
    archive = copied('results45', prefix+'observed_driver01/observer_driver/archive_manifest.json')
    require(owner['status'] == 'NATIVE_FAILED_RAW_ARCHIVED' and owner['healthy_cleanup'] is False
            and copy['status'] == 'COPY_VERIFIED_PENDING_OWNER_CLOSURE' and copy['healthy_cleanup'] is False
            and native['driver_exception'] is True and native['healthy_cleanup'] is False
            and owner['native'] == copy['native'] == archive['native'] == native
            and native['source_root'] == ROOT45 and len(native['sessions']) == 1
            and native['sessions'][0]['observer_exit_code'] == 0
            and native['sessions'][0]['observer_forced_stop'] is False
            and owner['readiness_claimed'] is False, 'Original45 failed owner must remain failed')
    require(all(path.stat().st_size == row['bytes'] and helper.sha(path) == row['sha256']
                for path, row in originals.values()), 'Original45 metadata changed after retention')
    return {'scope': 'HISTORICAL45_BUILD_VALIDATE_PASS_STOPPED_CORE_OWNER_FAILURE_NOT46_ACCEPTANCE',
        'source_commit': COMMIT45, 'build_validate_actions': actions,
        'suite': {'status': 'PASS', 'tests': 1767, 'skipped': 5, 'execution_count': 1},
        'core': {k: deepcopy(core[k]) for k in ('status', 'returncode', 'planned_count', 'attempt_count',
                                             'terminal_count', 'status_counts', 'final_errors')},
        'failed_owner': {'status': owner['status'], 'healthy_cleanup': False, 'runtime_acceptance': False},
        'metadata_copies': copies, 'readiness_claimed': False, 'runtime46_acceptance': False}


def reviewed_source(source, commit, prior, helper, generic, git):
    """Actual complete source and classified maps must equal independent pins."""
    require = generic.require
    require(helper.sha(SOURCE_PINS) == SOURCE_PINS_SHA, 'Independent actual46 source pins changed')
    pins = helper.read_small(SOURCE_PINS)
    require(pins.get('schema_version') == 1
            and pins.get('scope') == 'COMMITTED46_FULL_SOURCE_AND_CLASSIFIED_MAPS_NOT_RUNTIME_ACCEPTANCE'
            and pins.get('source_commit') == commit and pins.get('source_root') == str(source)
            and pins.get('baseline_commit') == prior['source_commit']
            and pins.get('status') == 'ACTUAL_COMMIT_MAPS_PREPARED_FOR_INDEPENDENT_REVIEW'
            and pins.get('formal_or_runtime_acceptance_claimed') is False,
            'Actual46 author maps bound for independent review required')
    tracked = sorted(name.decode('utf-8') for name in git('ls-files', '-z').split(b'\0') if name)
    ignored = prior['assembly_provenance']['inherited_ignored_resources']
    require(not set(tracked) & set(ignored), 'Inherited ignored assets became tracked')
    files = {}
    for name in sorted(tracked+ignored):
        relative = generic.relative(name)
        override = prior['source_overrides'].get(name)
        path = Path(override['path']) if override else source/relative
        require(path.is_file() and not path.is_symlink(), 'Missing physical candidate source: '+name)
        files[name] = helper.sha(path)
    delta = generic.delta(prior['files'], files)
    actual_delta = {key: sorted(name.decode('utf-8') for name in git('diff', '--no-renames', '--name-only',
        '-z', '--diff-filter='+code, prior['source_commit'], commit, '--').split(b'\0') if name)
        for code, key in (('M', 'changed'), ('A', 'added'), ('D', 'removed'))}
    require(files == pins.get('files') and delta == actual_delta == pins.get('allowed_delta')
            and generic.canonical(files) == pins.get('files_canonical_sha256'),
            'Complete actual Git/physical46 map/delta differs from reviewed source')
    # Original generic.candidate_binding below additionally checks each changed
    # or added physical byte string against its exact committed Git blob.
    runner = generic.runner_at(source)
    classified = runner.source_hashes(source)
    classified['config/px4_magnetic_runtime.json'] = files['config/px4_magnetic_runtime.json']
    runtime_delta = generic.delta(prior['classified_source_hashes'], classified)
    require(all(files.get(name) == digest for name, digest in classified.items())
            and classified == pins.get('classified_source_hashes')
            and runtime_delta == pins.get('classified_delta')
            and generic.canonical(classified) == pins.get('classified_canonical_sha256'),
            'Actual complete classified46 map/delta differs; no runtime44 equality assumption')
    for bound in pins.get('review_evidence', []):
        path = Path(bound['path'])
        require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(EXTERNAL)
                and path.stat().st_size <= generic.MAX_SMALL and helper.sha(path) == bound['sha256'],
                'Final actual46 review/test source evidence changed')
    require(pins.get('review_evidence'), 'Actual final source/test independent evidence required')
    return pins, tracked, ignored, files, classified, delta, runtime_delta, runner


def stream_contract(source, protocol, files, classified, runner, generic, pins):
    """Check registered .5/.05 source,4 wall,10 cap and actual gate binding."""
    require = generic.require
    registration = runner.supervisor_stream_summary(protocol)
    require(protocol.get('real_time_factor') == .125 and registration == protocol.get('supervisor_stream_timing')
            and registration.get('stream_timestamp_mode') == 'source_sim'
            and registration.get('odometry_source_max_age_s') == registration.get('command_source_max_age_s') == .5
            and registration.get('odometry_source_max_future_s') == registration.get('command_source_max_future_s') == .05
            and registration.get('odometry_timeout_wall_s') == registration.get('command_timeout_wall_s') == 4.
            and registration.get('receipt_wall_max_s') == 10.
            and generic.canonical(registration) == pins.get('supervisor_stream_timing_sha256'),
            'Reviewed46 registered stream timing differs')
    runner.supervisor_stream_trial_binding(protocol, {'supervisor_stream_timing': registration,
        'flight_command': ['--supervisor-stream-timestamp-mode', 'source_sim']})
    path = source/'scripts/build_reliability_v4_probe_gate.py'
    require(classified.get('scripts/build_reliability_v4_probe_gate.py') == files[str(path.relative_to(source))],
            'Actual new gate generator must be classified source')
    spec = importlib.util.spec_from_file_location('_actual46_gate_binding_only', path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    require(Path(gate.v4.__file__).resolve() == Path(runner.__file__).resolve(), 'Gate imported another source runner')
    prospective = {'protocol': protocol, 'source_hashes': classified,
        'model_hashes': {key:value for key,value in classified.items() if key.endswith('.pt')},
        'magnetic_runtime_binding': {'manifest_sha256': files['config/px4_magnetic_runtime.json']},
        'magnetic_library_binding': {'registration_sha256': files['config/gazebo_magnetic_runtime_humble22.json']}}
    binding = gate.bindings(prospective)
    require(binding.get('supervisor_stream_timing_sha256') == generic.canonical(registration)
            and binding == pins.get('prospective_gate_bindings'), 'Actual new gate binding differs from reviewed source')
    return {'registration': registration, 'sha256': generic.canonical(registration),
            'prospective_gate_bindings': binding, 'runtime_measured': False, 'gate_generated': False}


def assemble(args):
    # Fail before backend imports, source/history reads, directory creation or Git.
    if not (isinstance(NEW_COMMIT, str) and re.fullmatch('[0-9a-f]{40}', NEW_COMMIT)
            and isinstance(SOURCE_PINS_SHA, str) and re.fullmatch('[0-9a-f]{64}', SOURCE_PINS_SHA)
            and args.commit == NEW_COMMIT and args.name == 'v4_humble46'):
        raise ValueError('UNPREPARED: root must first pin actual reviewed46 commit and independent source-map SHA')
    adapter45, adapter, helper, generic, development, build_driver = reused()
    require = generic.require
    require(sys.platform == 'linux' and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22', 'Native UAVHumble22 metadata execution required')
    require(args.core_tools_sha256 == adapter.CORE_TOOLS == generic.canonical(development.tool_manifest()), 'Original strict core tools changed')
    source = args.source_root.resolve(strict=True)
    require(str(source).startswith('/mnt/d/') and source.is_dir() and not args.source_root.is_symlink(), 'Physical D-drive source required')
    def git(*tokens):
        return subprocess.check_output(['git', '-c', 'core.autocrlf=true', '-C', str(source), *tokens])
    require(not git('status', '--porcelain') and git('rev-parse', 'HEAD').decode().strip() == args.commit, 'Actual clean reviewed46 HEAD required')
    subprocess.run(['git', '-C', str(source), 'merge-base', '--is-ancestor', adapter.BASE_COMMIT, args.commit], check=True)
    frozen = '/root/uav_tracking_fullplan_v4_humble46'
    results = source/'results/frozen_fullplan_v4_humble46'
    history44, history45 = HERE/'history44_metadata01', HERE/'history45_metadata01'
    outcome_path = EXTERNAL/'closed43_failed44_stopped45_metadata_for_v4_humble46_pending01.json'
    capsule_path = EXTERNAL/'reviewed_freeze_closed_v4_humble46_pending01.json'
    review_path = EXTERNAL/'reviewed_freeze_review_v4_humble46_pending01.json'
    require(not any(path.exists() or path.is_symlink() for path in
        (Path(frozen), results, history44, history45, outcome_path, capsule_path, review_path)), 'Every46 output/history path must be fresh')
    r, prior, manifest_path, inherited, validate_path, outcomes43 = adapter.retain43(source, helper, generic)
    pins, tracked, ignored, files, classified, delta, runtime_delta, runner = reviewed_source(
        source, args.commit, prior, helper, generic, git)
    protocol_path = source/runner.PROTOCOL_PATH
    protocol = helper.read_small(protocol_path)
    runner.validate_protocol(protocol)
    require(protocol.get('car_input_scale_registration') == runner.CAR_INPUT_SCALE_REGISTRATION_TRAIN04_512,
            'Original strict explicit512 resource contract required')
    stream = stream_contract(source, protocol, files, classified, runner, generic, pins)
    _, failed44 = adapter45.retain_failed44(source, r, helper, generic, history44)
    stopped45 = retain45_history(source, r, helper, generic, history45)
    r.retain(SOURCE_PINS, ('source_commit', 'allowed_delta', 'classified_delta'), SOURCE_PINS_SHA)
    r.retain(HISTORY_PINS, expected_sha=HISTORY_PINS_SHA)
    for bound in pins['review_evidence']:
        path = Path(bound['path'])
        r.files[str(path)] = {'sha256': bound['sha256'], 'bytes': path.stat().st_size}
    override = build_driver.expected_override()
    override['status'] = 'PENDING_INDEPENDENT_RESOURCE_BUILD_REVIEW_NOT_EXECUTABLE'
    outcome = {'schema_version': 1, 'scope': 'HEALTHY43_FAILED44_STOPPED45_METADATA_NOT46_ACCEPTANCE',
        'created_utc': helper.utc(), 'source_predecessor': adapter.BASE_ROOT,
        'outcomes43': outcomes43, 'historical44': failed44, 'historical45': stopped45,
        'files': deepcopy(r.files), 'retained_fields': deepcopy(r.facts),
        'payload_reread': False, 'readiness_claimed': False}
    generic.write_new(outcome_path, outcome)
    r.retain(outcome_path, ('outcomes43', 'historical44', 'historical45', 'readiness_claimed'))
    capsule = {'schema_version': 1, 'scope': 'CLOSED_32_CORE_AND_PREDECESSOR_METADATA_ONLY',
        'created_utc': helper.utc(), 'all_inputs_closed': True, 'payload_reread': False, 'readiness_claimed': False,
        'files': dict(sorted(r.files.items())), 'retained_fields': r.facts,
        'boundaries': {'original32_core': inherited['boundaries']['original32_core'],
                       'predecessor': {'closed': True, 'receipt': str(validate_path)}},
        'original43_44_45_outcomes': {'path': str(outcome_path), 'sha256': helper.sha(outcome_path)},
        'source_predecessor_scope': 'HEALTHY43_BUILD_VALIDATE_ONLY_NOT44_OR45_RUNTIME_ACCEPTANCE'}
    review = deepcopy(prior)
    review.pop('independent_review_receipt', None)
    review.update(status='PENDING_ROOT_INDEPENDENT_REVIEW_NOT_EXECUTABLE', created_utc=helper.utc(),
        source_root=str(source), source_commit=args.commit, frozen_root=frozen, results_root=str(results),
        files=files, classified_source_hashes=classified, allowed_delta=delta,
        baseline={'source_commit': adapter.BASE_COMMIT, 'root': adapter.BASE_ROOT, 'manifest_path': str(manifest_path),
                  'manifest_sha256': adapter.MANIFEST_SHA, 'files_canonical_sha256': adapter.MAP_SHA},
        candidate_protocol={'path': str(protocol_path), 'sha256': helper.sha(protocol_path),
            'status': 'COMMITTED_SOURCE_ONLY_NOT_FROZEN_NOT_EXECUTED',
            'exclusive_navigation': runner.exclusive_navigation_summary(protocol),
            'pacing_revision': runner.simulation_pacing_summary(protocol).get('revision'),
            'supervisor_stream_timing': stream},
        development_resource_override=override,
        assembly_provenance={'status': 'ACTUAL_PENDING_SOURCE_REVIEW_ONLY', 'tracked_file_count': len(tracked),
            'inherited_ignored_resources': ignored, 'source_file_count': len(files), 'classified_source_count': len(classified),
            'formal_or_runtime_acceptance_claimed': False, 'runtime_delta_from43': runtime_delta,
            'actual_independent_source_maps': {'path': str(SOURCE_PINS), 'sha256': SOURCE_PINS_SHA},
            'original43_44_45_outcomes': {'path': str(outcome_path), 'sha256': helper.sha(outcome_path)},
            'assembler': {'path': str(Path(__file__).resolve()), 'sha256': helper.sha(__file__),
                'reused45_adapter_sha256': ADAPTER45_SHA, 'reused44_adapter_sha256': adapter45.ADAPTER44_SHA,
                'reused42_helper_sha256': adapter.HELPER_SHA}})
    generic.write_new(capsule_path, capsule)
    review['closed_evidence'] = {'path': str(capsule_path), 'sha256': helper.sha(capsule_path)}
    schema_only = deepcopy(review)
    schema_only['status'] = generic.FINAL_STATUS  # Never published FINAL here.
    generic.validate_review(schema_only)
    generic.verify_closed_capsule(schema_only)
    generic.candidate_binding(schema_only)
    require(not git('status', '--porcelain') and git('rev-parse', 'HEAD').decode().strip() == args.commit,
            'Source changed during46 metadata assembly')
    generic.write_new(review_path, review)
    print(json.dumps({'status': 'PENDING_ONLY_NOT_EXECUTABLE', 'review': str(review_path),
        'review_sha256': helper.sha(review_path), 'capsule': str(capsule_path), 'original43_44_45': str(outcome_path),
        'full_source_delta': delta, 'runtime_delta_from43': runtime_delta,
        'supervisor_stream_timing_sha256': stream['sha256'], 'flight_or_build_started': False}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--name', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--core-tools-sha256', required=True)
    assemble(parser.parse_args())


if __name__ == '__main__':
    main()
