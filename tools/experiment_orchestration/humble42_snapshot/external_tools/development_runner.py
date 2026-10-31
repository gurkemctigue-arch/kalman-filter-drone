"""Parameterized, independently admitted core12 development execution.

Import/describe are inert. Planning writes only PENDING candidates. Running
requires a separately reviewed contract for the actual newly persisted plan.
The frozen normal runner retains every flight/evaluator argv and its SITL lock.
Safety4 and extension16 are deliberately refused by this release.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

import local_runtime_observer41 as owner
import development_resource_guard as resources
import development_freeze_build as development_build
import matrix_runner41 as original41
import reviewed_freeze_build as generic
import reviewed_timing_diagnostic as stable
import source_runtime41 as policy

EXTERNAL = Path(__file__).resolve().parent
SCOPE = 'PARAMETERIZED_CORE12_NORMAL_RUNNER_DEVELOPMENT_ONLY'
CANDIDATE = 'FINAL_DEVELOPMENT_CANDIDATE_INDEPENDENTLY_REVIEWED'
PENDING = 'PENDING_DEVELOPMENT_RUNTIME_REVIEW_NOT_EXECUTABLE'
FINAL = 'FINAL_DEVELOPMENT_NORMAL_RUNNER_INDEPENDENTLY_REVIEWED'
INFRA_SCOPE = 'ORIGINAL41_IDENTICAL_INFRASTRUCTURE_ONLY_NOT_CANDIDATE_SAME_SOURCE'
ORIGINAL_ROOT = '/root/uav_tracking_fullplan_v4_humble41'
ORIGINAL_CLOSURE = 'root_core41_original_closure_verification01.json'
ORIGINAL_CLOSURE_SHA = 'cf3bf657ae3127c5db58d6f69cc7546314de16faf316708056580f7c59292aed'
ORIGINAL_REVIEW = 'reviewed_freeze_review_humble41_01.json'
ORIGINAL_REVIEW_SHA = 'c112dca912301f7d2f79a6bc113dd21592c285f1c1cacb4a21511f22b34d50b9'
ORIGINAL_MATRIX_CANONICAL = '8c9241e5f9ba7a54988b27d0f016e40d52ece37b8c9c85de410cb24463361cf3'
OWN_FILES = ('development_runner.py', 'development_runner.sh', 'test_development_runner.py',
             'development_resource_guard.py', 'test_development_resource_guard.py')
INFRA_FILES = ('scripts/observe_runtime_health.py', 'uav_tracking/recording_archive.py',
               'uav_tracking/__init__.py')
CLASSES = ('person', 'car')
GROUPS = ('stage1_velocity', 'stage1_position', 'stage2_crossing',
          'stage3_midpoint', 'stage3_active', 'stage3_multi_active')
FALSE_FIELDS = ('formal_seed_use_authorized', 'readiness_claimed', 'automatic_retry',
                'automatic_next_action', 'resume_or_recovery_authorized')
require, sha, canonical = generic.require, generic.sha, generic.canonical
read_small, write_new = generic.read_small, generic.write_new


def utc():
    return datetime.now(timezone.utc).isoformat()


def tool_manifest():
    """Only source identities, with no results/environment/runtime actions."""
    for module in (generic, stable, policy, owner, original41, resources, development_build):
        require(Path(module.__file__).resolve(strict=True) ==
                (EXTERNAL/Path(module.__file__).name).resolve(strict=True),
                'Dependency import escaped named external source')
    require(canonical(original41.tool_manifest()) == ORIGINAL_MATRIX_CANONICAL,
            'Original41 matrix/owner/collector/dependency bytes changed')
    files = {}
    for name in OWN_FILES:
        path = EXTERNAL/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
                'Missing bounded development runner source/test')
        files[name] = sha(path)
    return {'schema_version': 1, 'scope': SCOPE, 'files': files,
        'original41_tools_canonical_sha256': ORIGINAL_MATRIX_CANONICAL,
        'normal_runner_apis': ['make_plan', 'persist_plan', 'run_plan'],
        'root_binding': 'explicit reviewed candidate; no dependency globals modified',
        'core_cells': 12, 'classes': list(CLASSES), 'groups': list(GROUPS), 'seed': 4,
        'resource_and_pacing_binding': 'actual reviewed protocol and frozen runner validation',
        'runtime_resource_adapter': 'development_resource_guard; named512 receipt and original nonresource checks',
        'development_build_driver_tools_canonical_sha256': canonical(development_build.tool_manifest()),
        'pressure_reuse_scope': INFRA_SCOPE, 'pressure_implementation_files': list(INFRA_FILES),
        'driver_acquires_machine_sitl_lock': False, 'run_plan_acquires_own_sitl_lock': True,
        'flight_or_evaluator_argv_modified': False, 'maximum_new_trials_per_call': 1,
        'observer_owner_sha256': original41.OWNER_SHA,
        'observer_collector_sha256': original41.COLLECTOR_SHA,
        'observer_max_sample_age_wall_s': 10., 'observer_session_wall_s': 7200.,
        'observer_rotation_wall_s': 5400., 'observer_archive_wall_budget_s': 1800.,
        'plan_produces': PENDING, 'run_requires': FINAL,
        'extension_actions_executable': False, 'safety_actions_executable': False,
        'extension_future_prerequisites': ['fresh candidate core12 all PASS',
                                          'independent same-source safety4 original execution all PASS'],
        'default_candidate': None, 'default_contract': None,
        **{name: False for name in FALSE_FIELDS}}


def checked_metadata(expected, *, json_only=False):
    require(isinstance(expected, dict) and set(expected) == {'path', 'sha256'}
            and generic.valid_sha(expected.get('sha256')), 'Explicit metadata path/SHA256 required')
    require(stable.metadata_binding(expected['path'], json_only=json_only) == expected,
            'Bound metadata bytes/path changed: '+str(expected.get('path')))
    return expected


def checked_archived_source(expected):
    """Check raw source bytes separately from the JSON/log metadata parser."""
    require(isinstance(expected, dict) and set(expected) == {'path', 'sha256'}
            and generic.valid_sha(expected.get('sha256')),
            'Explicit archived source path/SHA256 required')
    path = Path(expected['path'])
    require(path.is_absolute() and path.suffix in ('.py', '.sh')
            and path.is_file() and not path.is_symlink()
            and path.stat().st_size <= generic.MAX_SMALL
            and sha(path) == expected['sha256'],
            'Bounded archived source bytes changed: '+str(path))
    return expected


def matrix_order(candidate=None):
    candidate = {} if candidate is None else candidate
    classes, groups = candidate.get('core_classes', list(CLASSES)), candidate.get('core_groups', list(GROUPS))
    for selected, complete in ((classes, CLASSES), (groups, GROUPS)):
        require(isinstance(selected, list) and all(type(item) is str for item in selected)
                and len(selected) == len(complete) and set(selected) == set(complete),
                'Candidate ordering must contain every original class/group exactly once')
    return classes, groups


def experiment(candidate=None):
    classes, groups = matrix_order(candidate)
    return {'classes': classes, 'groups': groups, 'seed': 4,
            'duration_s': 75., 'flight_count': 12}


def locations(candidate):
    root, prefix = Path(candidate['frozen_root']), candidate['prefix']
    output = root/'results'/f'{prefix}_seed004_matrix'
    return {'output': output, 'plan': output/'plan.json', 'run_driver': output/'observed_driver01',
            'plan_driver': root/'results/freeze_validation'/f'{prefix}_core_plan_driver01',
            'pending_contract': EXTERNAL/f'development_contract_core_{prefix}_pending01.json'}


def validate_candidate(value):
    require(isinstance(value, dict) and type(value.get('schema_version')) is int
            and value['schema_version'] == 1 and value.get('scope') == SCOPE
            and value.get('status') == CANDIDATE, 'Final independently reviewed candidate manifest required')
    root = generic.absolute(value.get('frozen_root'))
    require(re.fullmatch(r'/root/uav_tracking_fullplan_[A-Za-z0-9_]+', root)
            and root not in (ORIGINAL_ROOT, '/root/uav_tracking_fullplan_v4_humble40',
                             '/root/uav_tracking_fullplan_v4_humble32', '/root/uav_tracking_fullplan_v4_humble33'),
            'Dedicated new candidate source root required')
    prefix = value.get('prefix')
    require(isinstance(prefix, str) and re.fullmatch(r'reliability_v4_[A-Za-z0-9][A-Za-z0-9_-]{0,70}', prefix)
            and prefix != original41.PREFIXES['core'], 'Explicit fresh candidate prefix required')
    exp = value.get('experiment')
    require(exp == experiment(value) and type(exp.get('seed')) is int and type(exp.get('flight_count')) is int
            and type(exp.get('duration_s')) in (int, float), 'Complete class2/group6/strict integer seed4 core required')
    require(value.get('authorized_actions') == ['plan-core', 'run-core']
            and all(value.get(name) is False for name in FALSE_FIELDS)
            and 'zero_attempt_recovery' not in value,
            'No formal, readiness, retry, recovery or automatic follow-on permission')
    require(value.get('original41_closure') == {
        'path': generic.LINUX_EXTERNAL+'/'+ORIGINAL_CLOSURE, 'sha256': ORIGINAL_CLOSURE_SHA},
        'Exact actual original41 closure receipt required; arbitrary summaries cannot authorize')
    require(value.get('pressure_reuse', {}).get('scope') == INFRA_SCOPE
            and isinstance(value['pressure_reuse'].get('implementation_hashes'), dict)
            and set(value['pressure_reuse']['implementation_hashes']) == set(INFRA_FILES)
            and all(generic.valid_sha(x) for x in value['pressure_reuse']['implementation_hashes'].values()),
            'Explicit original41 identical-infrastructure pressure migration required')
    require(generic.valid_sha(value.get('tools_canonical_sha256')),
            'Explicit independently reviewed tool identity required')
    for name in ('source_review', 'protocol'):
        binding = value.get(name)
        require(isinstance(binding, dict) and set(binding) == {'path', 'sha256'}
                and generic.valid_sha(binding.get('sha256')), 'Candidate needs '+name+' metadata/SHA')
    require(value['protocol']['path'] == root+'/'+policy.PROTOCOL_PATH,
            'Candidate protocol path escaped frozen root')
    require(isinstance(value.get('build_evidence'), dict)
            and set(value['build_evidence']) == {'summary', 'build_terminal', 'validate_terminal'},
            'Actual cold-build summary/build/validate terminal bindings required')
    expected_paths = {'summary': root+'/results/freeze_validation/build_validation_summary.json'}
    label = Path(root).name.removeprefix('uav_tracking_fullplan_')
    for action in ('build', 'validate'):
        expected_paths[action+'_terminal'] = generic.LINUX_EXTERNAL+f'/reviewed_freeze_actions_{label}/{action}/action.terminal.json'
    for name, path in expected_paths.items():
        entry = value['build_evidence'][name]
        require(isinstance(entry, dict) and set(entry) == {'path', 'sha256'} and entry.get('path') == path
                and generic.valid_sha(entry.get('sha256')), 'Candidate build binding escaped actual '+name)
    return value


def load_candidate(path, expected_sha):
    require(path is not None and generic.valid_sha(expected_sha), 'Explicit candidate manifest path and SHA required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True)
            and re.fullmatch(r'development_candidate_[A-Za-z0-9_]+\.json', path.name),
            'Named external development candidate manifest required')
    value = read_small(path)
    require(sha(path) == expected_sha, 'Candidate manifest SHA mismatch')
    validate_candidate(value)
    require(value['tools_canonical_sha256'] == canonical(tool_manifest()), 'Reviewed development tool bytes changed')
    checked_metadata(value['protocol'], json_only=True)
    protocol = read_small(value['protocol']['path'])
    review_binding = value['source_review']
    named512 = protocol.get('car_input_scale_registration',{}).get('revision') == resources.REVISION
    loader = development_build.load_review if named512 else generic.load_review
    review = loader(review_binding['path'], review_binding['sha256'], 'validate')
    require(review['frozen_root'] == value['frozen_root'], 'Candidate root differs from actual source review')
    require(review.get('files', {}).get(policy.PROTOCOL_PATH) == value['protocol']['sha256']
            and type(protocol.get('duration_s')) in (int, float) and protocol['duration_s'] == 75.
            and isinstance(protocol.get('seeds'), list) and 4 not in protocol['seeds'],
            'Actual reviewed75s protocol required; held-out seeds cannot be consumed')
    policy.validate_class_policy(protocol)
    for entry in value['build_evidence'].values():
        checked_metadata(entry, json_only=True)
    if named512:
        require_supplement_build(value,review)
    value['_manifest_binding'] = {'path': str(path), 'sha256': expected_sha}
    return value, review


def require_supplement_build(candidate,review):
    """Old generic summaries alone cannot admit a new512 build driver."""
    supplement = development_build.supplement_binding(review)
    require(candidate.get('development_build_driver_tools_canonical_sha256') ==
            canonical(development_build.tool_manifest()), 'Candidate must explicitly bind the new512 build driver tools')
    evidence = candidate['build_evidence']
    terminals, runtime_evidence = {}, {}
    for action in ('build','validate'):
        binding = evidence[action+'_terminal']
        checked_metadata(binding,json_only=True)
        terminal = read_small(binding['path'])
        before = terminal.get('binding_before')
        require(terminal.get('action') == action and terminal.get('status') == 'PASS'
                and isinstance(before,dict) and before == terminal.get('binding_after')
                and before.get('review') == review['_review_binding']
                and before.get('development_resource_override') == supplement,
                'Actual new512 build/validate terminal lacks the reviewed supplement: '+action)
        terminals[action] = binding
        directory = Path(binding['path']).parent
        preflight_path = directory/'runtime_preflight.json'
        preflight_binding = stable.metadata_binding(preflight_path,json_only=True)
        preflight = read_small(preflight_path)
        require(type(preflight.get('schema_version')) is int and preflight['schema_version'] == 1
                and preflight.get('action_binding') == before,
                'Actual new512 runtime preflight is not bound to its original action: '+action)
        development_build.verify_512_runtime(preflight.get('runtime'),candidate['frozen_root'])
        closures = {}
        phases = ('action','post_build') if action == 'build' else ('action',)
        for phase in phases:
            closure_path = directory/f'runtime_preflight_{phase}_closure.json'
            closure_binding = stable.metadata_binding(closure_path,json_only=True)
            closure = read_small(closure_path)
            require(type(closure.get('schema_version')) is int and closure['schema_version'] == 1
                    and closure.get('action_binding') == before
                    and closure.get('before_sha256') == closure.get('after_sha256') == preflight_binding['sha256']
                    and closure.get('strict512_resource_verified') is True
                    and closure.get('evidence_files_unchanged') is True,
                    'Actual new512 runtime preflight closure missing/changed: '+action+':'+phase)
            checked_metadata(closure_binding,json_only=True)
            closures[phase] = closure_binding
        checked_metadata(preflight_binding,json_only=True)
        runtime_evidence[action] = {'preflight':preflight_binding,'closures':closures,
                                   'strict512_resource_verified':True,'evidence_files_unchanged':True}
    manifest_path = Path(candidate['frozen_root'])/'results/freeze_validation/source_freeze_manifest.json'
    manifest_binding = stable.metadata_binding(manifest_path,json_only=True)
    manifest = read_small(manifest_path)
    require(manifest.get('development_resource_override') == supplement
            and manifest.get('final_review') == review['_review_binding'],
            'Actual new512 source freeze manifest lacks the reviewed supplement')
    archived = manifest_path.parent/'external_wrappers'
    files = {**development_build.tool_manifest()['files'], **resources.tool_manifest()['files']}
    for name,digest in files.items():
        checked_archived_source({'path':str(archived/name),'sha256':digest})
    return {'supplement':supplement,'source_freeze_manifest':manifest_binding,
            'actual_action_terminals':terminals,'actual_runtime_preflight_evidence':runtime_evidence,
            'archived_driver_and_guard_files':files}


def original_closure_binding():
    """Retain original small evidence; do not rerun/regrade its large rosbag study."""
    binding = {'path': generic.LINUX_EXTERNAL+'/'+ORIGINAL_CLOSURE, 'sha256': ORIGINAL_CLOSURE_SHA}
    checked_metadata(binding, json_only=True)
    receipt = read_small(binding['path'])
    closed = receipt.get('original_closure_verifier', {})
    require(receipt.get('scope') == 'ACTUAL_ORIGINAL_CORE41_CLOSURE_WITH_FAILURE_PRESERVED'
            and receipt.get('all_pass_required') is False and receipt.get('safety_or_extension_admitted') is False
            and receipt.get('formal_seeds_consumed') is False
            and closed.get('result') == 'PASS' and closed.get('completed_count') == 12
            and closed.get('all_original_core_cells_pass') is False,
            'Original closure must retain its actual 11PASS/1FAIL boundary')
    plan_binding = closed['core_plan']['plan']
    checked_metadata(plan_binding, json_only=True)
    plan = read_small(plan_binding['path'])
    # The historical parser/evaluator source must retain the exact bytes whose
    # original results are being reread. Large bag/model payloads are not replayed.
    for relative, digest in plan.get('source_hashes', {}).items():
        if Path(relative).suffix in ('.py', '.sh'):
            path = Path(ORIGINAL_ROOT)/relative
            require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL
                    and sha(path) == digest, 'Original41 reader/evaluator source changed: '+relative)
    runner = generic.runner_at(ORIGINAL_ROOT)
    runner.validate_plan(plan, Path(plan_binding['path']))
    expected_ids = [f'{cls}_{group}_seed004' for cls in CLASSES for group in GROUPS]
    require(plan.get('frozen_root') == ORIGINAL_ROOT and [t['id'] for t in plan['trials']] == expected_ids
            and [v.get('id') for v in closed.get('original_terminals', [])] == expected_ids,
            'Original41 core denominator/order changed')
    checked_metadata(closed['execution_terminal'], json_only=True)
    terminal = read_small(closed['execution_terminal']['path'])
    require(terminal.get('returncode') == 0 and type(terminal.get('returncode')) is int
            and terminal.get('planned_count') == terminal.get('attempt_count') == terminal.get('terminal_count') == 12
            and terminal.get('entry_binding_before') == terminal.get('entry_binding_after')
            and terminal.get('final_errors') == [] and terminal.get('cleanup', {}).get('residual_processes') == [],
            'Original41 execution source/cleanup changed')
    statuses = []
    for trial, original, attempt in zip(plan['trials'], closed['original_terminals'], terminal['attempts']):
        record_binding = original['record_binding']
        checked_metadata({k: record_binding[k] for k in ('path', 'sha256')}, json_only=True)
        checked_metadata(record_binding['started_marker'], json_only=True)
        checked_metadata(original['attempt_terminal'], json_only=True)
        require(read_small(original['attempt_terminal']['path']) == attempt
                and attempt.get('error') is None and attempt.get('audit', {}).get('record_binding') == record_binding,
                'Original41 attempt/start/audit metadata changed')
        record = read_small(record_binding['path'])
        require(record.get('status') == record.get('engineering_result') == original['status']
                and record.get('record_sha256') == record_binding['record_sha256']
                and record.get('infrastructure_stop') is False,
                'Original41 record status/infrastructure changed')
        entries = []
        for spec in trial['evaluations']:
            recorded = next(x for x in record['evaluations'] if x['kind'] == spec['kind'])
            execution = recorded['execution']
            require(execution.get('command') == spec['command'] and execution.get('error') is None,
                    'Original41 evaluator argv changed')
            current = runner.read_evaluation(spec, execution, plan)
            require(current == recorded, 'Original41 original evaluator report/hash changed')
            entries.append(current)
        flight = next(x for x in record['commands'] if x['kind'] == 'flight')
        require(flight.get('command') == trial['flight_command'] and flight.get('returncode') == 0
                and flight.get('error') is None, 'Original41 flight argv/result changed')
        verdict, _ = runner.engineering_verdict(plan, trial, flight, entries)
        require(verdict == original['status'], 'Original41 engineering result differs from bound original reports')
        statuses.append(original['status'])
    require(Counter(statuses) == {'PASS': 11, 'FAIL': 1}, 'Original41 failures cannot be erased or upgraded')
    observed = owner.validate_observer_root(terminal.get('observer_owner_terminal'),
        Path(closed['execution_terminal']['path']).parent/'observer_driver', ORIGINAL_ROOT)
    require(observed == terminal.get('observer') == closed.get('observer'), 'Original41 actual owner evidence changed')
    return {'receipt': binding, 'execution_terminal': closed['execution_terminal'],
            'status_counts': dict(Counter(statuses)), 'all_core_pass': False,
            'historical_evidence_only_not_candidate_acceptance': True}


def infrastructure_binding(candidate, review):
    """Revalidate real41 pressure under its original root, then compare code bytes.

    No new-root same-source pressure claim is made. The new source must have
    byte-identical collector/archive implementation and unchanged owner bounds.
    """
    closure = read_small(generic.LINUX_EXTERNAL+'/'+ORIGINAL_CLOSURE)['original_closure_verifier']
    terminal = read_small(closure['execution_terminal']['path'])
    retained = terminal['entry_binding_before']['source41_binding']
    old_review = generic.load_review(EXTERNAL/ORIGINAL_REVIEW, ORIGINAL_REVIEW_SHA, 'validate')
    pressure = original41.require_completed_pressure(old_review,
        {'bound_build_metadata': retained['build_metadata']})
    migration = candidate['pressure_reuse']
    require(migration.get('original_execution_terminal') == pressure['execution_terminal']
            and migration.get('scope') == INFRA_SCOPE, 'Candidate must name the actual41 pressure terminal')
    hashes = {}
    for relative in INFRA_FILES:
        expected = migration['implementation_hashes'][relative]
        require(sha(Path(ORIGINAL_ROOT)/relative) == expected
                and sha(Path(candidate['frozen_root'])/relative) == expected
                and old_review.get('files', {}).get(relative) == review.get('files', {}).get(relative) == expected,
                'Pressure implementation changed; new same-source no-SITL pressure required: '+relative)
        hashes[relative] = expected
    return {'scope': INFRA_SCOPE, 'original_pressure': pressure,
            'identical_implementation_hashes': hashes, 'candidate_same_source_pressure_claimed': False}


def entry_binding(candidate, review, built):
    checked_metadata(candidate['_manifest_binding'], json_only=True)
    require(candidate['tools_canonical_sha256'] == canonical(tool_manifest()), 'Reviewed development tools changed')
    actual = generic.action_binding(review, 'validate')
    require(actual['source'] == built['source'] and actual['closed_original_evidence'] == built['closed_original_evidence'],
            'Frozen candidate source or retained history changed')
    for entry in built['bound_build_metadata'].values():
        checked_metadata(entry, json_only=Path(entry['path']).suffix == '.json')
    checked_metadata(candidate['protocol'], json_only=True)
    require(isinstance(built.get('_resource_runtime_binding'),dict), 'Actual resource runtime preflight binding required')
    resource_runtime = resources.revalidate_resource_binding(built['_resource_runtime_binding'])
    supplement = require_supplement_build(candidate,review) if resource_runtime.get('registration',{}).get('revision') == resources.REVISION else None
    require(sha(Path(candidate['frozen_root'])/'scripts/observe_runtime_health.py') == original41.COLLECTOR_SHA,
            'New source collector differs from original41 owner implementation')
    return {'candidate_manifest': candidate['_manifest_binding'], 'source_review': review['_review_binding'],
            'source': built['source'], 'closed_original_evidence': built['closed_original_evidence'],
            'build_metadata': built['bound_build_metadata'], 'protocol': candidate['protocol'],
            'tools_canonical_sha256': candidate['tools_canonical_sha256'],
            'actual_resource_runtime': resource_runtime,
            'development_source_build': supplement,
            'original41_closure': original_closure_binding(),
            'pressure_migration': infrastructure_binding(candidate, review)}


def require_runtime(candidate, review, checks):
    return resources.require_runtime(candidate,review,checks)


def validate_matrix(candidate, plan, runner, path=None):
    runner.validate_plan(plan, path)
    selected = locations(candidate)
    classes, groups = matrix_order(candidate)
    expected_ids = [f'{cls}_{group}_seed004' for cls in classes for group in groups]
    require(plan.get('mode') == 'PROBE' and plan.get('frozen_root') == candidate['frozen_root']
            and plan.get('prefix') == candidate['prefix']
            and Path(plan['output']).resolve() == selected['output'].resolve()
            and plan.get('selected_classes') == classes and plan.get('selected_seeds') == [4]
            and type(plan['selected_seeds'][0]) is int and plan.get('selected_groups') == groups
            and [trial.get('id') for trial in plan.get('trials', [])] == expected_ids
            and plan.get('protocol_sha256') == candidate['protocol']['sha256'],
            'Exact fresh candidate2-class/seed004/core12 matrix required')
    protocol = read_small(candidate['protocol']['path'])
    require(plan.get('protocol') == protocol and protocol.get('duration_s') == 75.
            and 4 not in protocol.get('seeds', []), 'Actual immutable reviewed protocol required')
    policy.validate_class_policy(protocol, runner)
    pacing = protocol.get(policy.PACING_FIELD)
    require(isinstance(pacing, dict) and pacing.get('safety_source_time_gates') == 'unchanged'
            and pacing.get('follow_duration_s') == 75.
            and runner.simulation_pacing_declared(protocol), 'Explicit frozen resource pacing registration required')
    require(plan.get('postprocessing_timeout_s') == 1800. and plan.get('evaluation_timeout_s') == 1800.
            and plan.get('trial_timeout_s') == protocol['flight_wall_timeout_s']+1800.,
            'Frozen original child/postprocessing/evaluation budgets required')
    for trial, (cls, group) in zip(plan['trials'], ((c, g) for c in classes for g in groups)):
        resources, car = protocol['resources'][cls], cls == 'car'
        require(trial.get('target_class') == cls and trial.get('group') == group
                and type(trial.get('seed')) is int and trial['seed'] == 4
                and trial.get('duration_s') == 75. and trial.get('wall_timeout_s') == protocol['flight_wall_timeout_s']
                and all(trial.get(key) == resources[key] for key in
                        ('model', 'inference_image_size', 'inference_threads', 'desired_distance_m'))
                and type(trial.get('inference_image_size')) is int and type(trial.get('inference_threads')) is int
                and runner.correlated_two_face_trial_binding(plan, trial) == (car, car)
                and runner.car_surface_recovery_trial_binding(plan, trial) == (car, car),
                'Actual reviewed class resource/geometry/surface policy differs')
        require(trial.get(policy.PACING_FIELD) == pacing
                and runner.simulation_pacing_trial_binding(plan, trial) == pacing
                and type(trial.get(policy.ADAPTER_FIELD)) in (int, float)
                and trial[policy.ADAPTER_FIELD] == pacing[policy.ADAPTER_FIELD], 'Actual registered per-slot pacing differs')
        original41.validate_exclusive_trial(plan, trial, runner)
        command = trial['flight_command']
        require(command.count(policy.ADAPTER_FLAG) == 1
                and not any(token.startswith(policy.ADAPTER_FLAG+'=') for token in command),
                'One original explicit adapter publication flag required')
        require(float(command[command.index(policy.ADAPTER_FLAG)+1]) == pacing[policy.ADAPTER_FIELD],
                'Original adapter argv differs from actual protocol')
    return plan


def checked_plan(candidate, runner):
    path = locations(candidate)['plan']
    plan = read_small(path)
    validate_matrix(candidate, plan, runner, path)
    runner.verify_sources(plan)
    return plan


def pending_identity(plan):
    return {'plan': stable.metadata_binding(Path(plan['output'])/'plan.json', json_only=True),
            'plan_sha256': plan['plan_sha256'], 'slot_ids': [t['id'] for t in plan['trials']],
            'initial_status_counts': {'PENDING': len(plan['trials'])}}


def require_fresh_rows(plan, rows):
    require(set(rows) == {t['id'] for t in plan['trials']}
            and all(row.get('status') == 'PENDING' for row in rows.values()),
            'Every fresh core12 slot must be untouched PENDING; retries/resume forbidden')
    require(not any(Path(t['directory']).exists() or Path(t['directory']).is_symlink() for t in plan['trials']),
            'Old trial products cannot be reused')


def make_observer(candidate, directory):
    return owner.make_observer(directory/'observer_driver', candidate['frozen_root'], archive_wall_budget_s=1800.)


def finish_action(candidate, review, built, runner, observer, directory):
    errors, after, residual, observed = [], None, None, None
    actual_owner = observer._finished
    try:
        after = entry_binding(candidate, review, built)
    except BaseException as caught:
        errors.append('binding:'+type(caught).__name__+':'+str(caught))
    try:
        residual = runner.simulation_processes()
        require(residual == [], 'Residual runtime processes remain')
    except BaseException as caught:
        errors.append('residual:'+type(caught).__name__+':'+str(caught))
    try:
        observed = owner.validate_observer_root(actual_owner, directory/'observer_driver', candidate['frozen_root'])
    except BaseException as caught:
        errors.append('observer:'+type(caught).__name__+':'+str(caught))
    return {'entry_binding_after': after, 'cleanup': {'residual_processes': residual},
            'observer_owner_terminal': actual_owner, 'observer': observed, 'final_errors': errors}


def plan_core(candidate, review, built, runner, runtime):
    selected = locations(candidate)
    require(not any(selected[k].exists() or selected[k].is_symlink() for k in
                    ('output', 'plan_driver', 'pending_contract')) and not runner.simulation_processes(),
            'Fresh plan/driver/contract and idle runtime required')
    before = entry_binding(candidate, review, built)
    directory = selected['plan_driver']
    directory.mkdir(exist_ok=False)
    observer = make_observer(candidate, directory)
    error, initial = None, None
    try:
        with observer:
            classes, groups = matrix_order(candidate)
            plan = runner.make_plan(Path(candidate['frozen_root']), selected['output'], candidate['prefix'],
                formal=False, seeds=[4], groups=groups, classes=classes)
            validate_matrix(candidate, plan, runner)
            runner.persist_plan(plan)
            require_fresh_rows(plan, runner.read_slots(plan))
            initial = pending_identity(plan)
            observer.check()
    except BaseException as caught:
        error = type(caught).__name__+':'+str(caught)
    cleanup = finish_action(candidate, review, built, runner, observer, directory)
    code = 0 if error is None and initial and cleanup['entry_binding_after'] == before and not cleanup['final_errors'] else 2
    terminal_path = directory/'execution_terminal.json'
    write_new(terminal_path, {'schema_version': 1, 'scope': SCOPE, 'action': 'plan-core', 'returncode': code,
        'finished_utc': utc(), 'error': error, 'entry_binding_before': before, 'initial_pending': initial,
        'runtime_preflight': runtime, **cleanup, 'flights_started': 0, **{name: False for name in FALSE_FIELDS}})
    if code == 0:
        value = {'schema_version': 1, 'scope': SCOPE, 'status': PENDING, 'matrix_kind': 'core',
            'created_utc': utc(), 'candidate_manifest': candidate['_manifest_binding'],
            'entry_binding': before, 'plan_pending': initial,
            'plan_terminal': stable.metadata_binding(terminal_path, json_only=True),
            'experiment': experiment(candidate), **{name: False for name in FALSE_FIELDS}}
        write_new(selected['pending_contract'], value)
        print(json.dumps({'pending_contract': str(selected['pending_contract']),
            'sha256': sha(selected['pending_contract']), 'status': PENDING, 'flights_started': 0}), flush=True)
    return code


def load_contract(candidate, review, built, runner, path, expected_sha):
    require(path is not None and generic.valid_sha(expected_sha), 'Explicit separately reviewed actual contract required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True)
            and re.fullmatch(r'development_contract_core_[A-Za-z0-9_-]+\.json', path.name),
            'Named external core runtime contract required')
    value = read_small(path)
    require(sha(path) == expected_sha and type(value.get('schema_version')) is int
            and value['schema_version'] == 1 and value.get('scope') == SCOPE and value.get('status') == FINAL
            and value.get('matrix_kind') == 'core' and value.get('candidate_manifest') == candidate['_manifest_binding']
            and value.get('entry_binding') == entry_binding(candidate, review, built),
            'Concrete independently reviewed final contract required; PENDING cannot run')
    exp = value.get('experiment')
    require(exp == experiment(candidate) and type(exp.get('seed')) is int and type(exp.get('flight_count')) is int
            and all(value.get(name) is False for name in FALSE_FIELDS) and 'zero_attempt_recovery' not in value,
            'Only complete original development core12 is admitted; no retry/formal/recovery')
    plan = checked_plan(candidate, runner)
    initial, selected = pending_identity(plan), locations(candidate)
    require(value.get('plan_pending') == initial, 'Actual pending plan identity changed')
    original41.require_same_metadata_file(stable.metadata_binding(selected['plan'], json_only=True), initial['plan'])
    terminal_path = selected['plan_driver']/'execution_terminal.json'
    require(stable.metadata_binding(terminal_path, json_only=True) == value.get('plan_terminal'),
            'Original plan terminal changed')
    terminal = read_small(terminal_path)
    require(terminal.get('scope') == SCOPE and terminal.get('action') == 'plan-core'
            and type(terminal.get('returncode')) is int and terminal['returncode'] == 0
            and terminal.get('error') is None and terminal.get('initial_pending') == initial
            and type(terminal.get('flights_started')) is int and terminal['flights_started'] == 0
            and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == value['entry_binding']
            and terminal.get('final_errors') == [] and terminal.get('cleanup', {}).get('residual_processes') == [],
            'Actual plan did not close with original clean source/owner evidence')
    observed = owner.validate_observer_root(terminal.get('observer_owner_terminal'),
        selected['plan_driver']/'observer_driver', candidate['frozen_root'])
    require(terminal.get('observer') == observed, 'Original plan observer differs from real post-wait owner outcome')
    return value, plan


def observed_run_plan(runner, plan, observer):
    # The normal runner alone owns its SITL lock. Never wrap it with run_lock.
    def execute(command, log, cwd, timeout):
        return stable.execute_owned(command, log, observer, timeout, cwd)
    return runner.run_plan(plan, max_new_trials=1, command_runner=execute)


def run_core(candidate, review, built, runner, modules, runtime, contract_path, contract_sha):
    contract, plan = load_contract(candidate, review, built, runner, contract_path, contract_sha)
    selected = locations(candidate)
    directory = selected['run_driver']
    require_fresh_rows(plan, runner.read_slots(plan))
    require(not directory.exists() and not directory.is_symlink() and not runner.simulation_processes(),
            'Fresh run driver and idle runtime required; no resume or retry')
    before = entry_binding(candidate, review, built)
    directory.mkdir(exist_ok=False)
    observer = make_observer(candidate, directory)
    attempts, completed, error = [], [], None
    checks = modules['humble33_diagnostic_checks01']
    try:
        with observer:
            for number, trial in enumerate(plan['trials'], 1):
                require(entry_binding(candidate, review, built) == before, 'Source/build/history/tools changed before next original slot')
                require(sha(contract_path) == contract_sha, 'Final actual contract changed')
                runner.verify_sources(plan)
                original41.require_same_metadata_file(stable.metadata_binding(selected['plan'], json_only=True),
                    contract['plan_pending']['plan'])
                rows = runner.read_slots(plan)
                require(rows[trial['id']]['status'] == 'PENDING' and not runner.simulation_processes()
                        and not Path(trial['directory']).exists() and not Path(trial['directory']).is_symlink(),
                        'Original slot already attempted/products present or runtime active; no retry')
                for prior in completed:
                    prior_trial = next(t for t in plan['trials'] if t['id'] == prior['slot'])
                    require(checks.terminal_binding(runner, plan, prior_trial, rows[prior['slot']]) ==
                            prior['audit']['record_binding'], 'Prior immutable terminal changed')
                observer.check()
                attempt = {'slot': trial['id'], 'number': number, 'started_utc': utc(),
                           'runner_result': None, 'record': None, 'audit': None, 'error': None}
                attempts.append(attempt)
                marker = directory/f'{number:02d}_{trial["id"]}.started.json'
                write_new(marker, {'slot': trial['id'], 'number': number, 'entry_binding': before,
                    'contract': {'path': str(contract_path), 'sha256': contract_sha}, 'plan_sha256': plan['plan_sha256'],
                    'started_utc': attempt['started_utc'], 'original_attempt_number': 1})
                attempt['started_marker'] = stable.metadata_binding(marker, json_only=True)
                print(json.dumps({'event': 'START_ORIGINAL_DEVELOPMENT_SLOT', 'slot': trial['id'],
                                  'number': number, 'total': 12}), flush=True)
                try:
                    attempt['runner_result'] = observed_run_plan(runner, plan, observer)
                    record = runner.read_slots(plan)[trial['id']]
                    attempt['record'] = {'status': record.get('status'), 'engineering_result': record.get('engineering_result'),
                        'record_binding': checks.terminal_binding(runner, plan, trial, record)}
                    # This original41 function is root-independent: it uses the supplied
                    # frozen runner/plan/trial and original report/runtime/cleanup files.
                    attempt['audit'] = original41.audit_record(runner, plan, trial, record, review, checks)
                    require(type(attempt['runner_result'].get('started_this_invocation')) is int
                            and attempt['runner_result']['started_this_invocation'] == 1,
                            'Normal runner must consume exactly one original slot')
                    observer.check()
                    require(entry_binding(candidate, review, built) == before and sha(contract_path) == contract_sha,
                            'Source/build/history/tools/contract changed during original slot')
                    completed.append({'slot': trial['id'], 'status': record['status'],
                                      'engineering_result': record['engineering_result'], 'audit': attempt['audit']})
                except BaseException as caught:
                    attempt['error'] = type(caught).__name__+':'+str(caught)
                    raise
                finally:
                    attempt['finished_utc'] = utc()
                    write_new(directory/f'{number:02d}_{trial["id"]}.attempt_terminal.json', attempt)
    except BaseException as caught:
        error = type(caught).__name__+':'+str(caught)
    cleanup = finish_action(candidate, review, built, runner, observer, directory)
    code = 0 if error is None and len(completed) == 12 and cleanup['entry_binding_after'] == before and not cleanup['final_errors'] else 2
    actual_rows, row_error = None, None
    try:
        actual_rows = {key: {'status': row.get('status'), 'record_sha256': row.get('record_sha256')}
                       for key, row in runner.read_slots(plan).items()}
    except BaseException as caught:
        row_error, code = type(caught).__name__+':'+str(caught), 2
    write_new(directory/'execution_terminal.json', {'schema_version': 1, 'scope': SCOPE, 'action': 'run-core',
        'finished_utc': utc(), 'returncode': code, 'error': error,
        'status': 'ORIGINAL_CORE_TERMINALS_COMPLETE' if code == 0 else 'STOPPED_ORIGINAL_ATTEMPTS_RETAINED',
        'entry_binding_before': before, 'runtime_preflight': runtime,
        'contract': {'path': str(contract_path), 'sha256': contract_sha}, 'plan': contract['plan_pending'],
        'planned_count': 12, 'attempt_count': len(attempts), 'terminal_count': len(completed),
        'attempts': attempts, 'slots': completed, 'actual_slot_statuses': actual_rows, 'slot_read_error': row_error,
        'status_counts': dict(Counter(row['status'] for row in (actual_rows or {}).values())), **cleanup,
        **{name: False for name in FALSE_FIELDS},
        'claim_boundary': 'Complete original development attempts retain algorithm FAIL; no safety4, extension16 or formal acceptance is granted.'})
    return code


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', choices=('describe', 'plan-core', 'run-core', 'plan-extension', 'run-extension', 'plan-safety', 'run-safety'))
    result.add_argument('--manifest', type=Path)
    result.add_argument('--manifest-sha256')
    result.add_argument('--contract', type=Path)
    result.add_argument('--contract-sha256')
    return result


def reviewed_candidate(args):
    require(args.action in ('plan-core', 'run-core'),
            'Safety4 is independent; extension16 requires fresh candidate core12 all PASS and actual safety4 acceptance; neither action is executable here')
    if args.action == 'run-core':
        require(args.contract is not None and generic.valid_sha(args.contract_sha256),
                'Run requires separately reviewed final actual contract and SHA')
    return load_candidate(args.manifest, args.manifest_sha256)


def shell_root(argv):
    candidate, _ = reviewed_candidate(parser().parse_args(argv))
    return candidate['frozen_root']


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == 'describe':
            manifest = tool_manifest()
            print(json.dumps({'status': 'PENDING_INDEPENDENT_TOOL_REVIEW', 'tool_manifest': manifest,
                'tools_canonical_sha256': canonical(manifest), 'actual_action_executed': False,
                'candidate_manifest_required': CANDIDATE, 'run_contract_required': FINAL}, indent=2))
            return 0
        candidate, review = reviewed_candidate(args)
        generic.require_linux()
        modules = stable.dependencies()
        with generic.exclusive_window(), stable.stop_signals():
            built = stable.checked_build(candidate, review, modules['humble33_diagnostic_checks01'])
            runtime = require_runtime(candidate, review, modules['humble33_diagnostic_checks01'])
            built['_resource_runtime_binding'] = runtime['runtime_contracts']['resource']
            runner = generic.runner_at(candidate['frozen_root'])
            if args.action == 'plan-core':
                return plan_core(candidate, review, built, runner, runtime)
            return run_core(candidate, review, built, runner, modules, runtime, args.contract, args.contract_sha256)
    except (OSError, ValueError, RuntimeError, KeyError, IndexError, StopIteration, subprocess.SubprocessError) as caught:
        print(json.dumps({'status': 'DEVELOPMENT_ACTION_REFUSED_OR_FAILED',
            'reason': type(caught).__name__+':'+str(caught), **{name: False for name in FALSE_FIELDS}}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
