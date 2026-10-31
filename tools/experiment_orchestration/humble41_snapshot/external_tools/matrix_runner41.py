"""Humble41 complete same-source core12 with separately reviewed actual contracts.

Describe/import are inert. Plans produce pending, non-executable review
candidates. Runs require separately reviewed actual contracts. The normal
frozen runner alone owns its SITL lock and every original flight/evaluator argv.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import source_runtime41 as source
import local_runtime_observer41 as owner
import reviewed_freeze_build as generic
import reviewed_timing_diagnostic as stable

EXTERNAL = Path(__file__).resolve().parent
TOOL_STATUS = 'RELEASE_CANDIDATE_PENDING_INDEPENDENT_TOOL_REVIEW'
ROOT = source.ROOT
SCOPE = 'HUMBLE41_CORE12_NORMAL_RUNNER_DEVELOPMENT_ONLY'
COLLECTOR_SHA = 'f174ec21ebf962f156d76f8d35f802eebf318163555815527a3e2227b914f180'
OWNER_SHA = '2f1348d862525777800df823780a269ef235b0df8d96b9ec378dc61c2be99914'
OWNER_TEST_SHA = 'c06937b3323584712ae0b0f79c8e22e1433eb4395626e177bfa3d12a05dc343c'
PRESSURE_SHA = '6cb0f7b97a426cb79537b51aa810661364e34438054676424fd4fafdf1aa692e'
PRESSURE_SHELL_SHA = '6e11546a5e47f2708cd6b6efd5daac917dc8459366e08b696d63b10148ad5f02'
ORIGINAL_SPOOL = '/root/uav_tracking_bag_spool/trial_ygxppdk1'
ORIGINAL_SLOT = '/root/uav_tracking_fullplan_v4_humble40/results/reliability_v4_humble40_probe01_seed004_matrix/slots/person_stage3_midpoint_seed004.json'
ORIGINAL_SLOT_SHA = '605c7cf97ee8745c30068a7ed324753f3468c4bb8fb11642de2ef3edd4f52ef1'
OWN_FILES = ('matrix_runner41.py', 'matrix_runner41.sh', 'test_matrix_runner41.py')
CLASSES = ('person', 'car')
GROUPS = ('stage1_velocity', 'stage1_position', 'stage2_crossing',
          'stage3_midpoint', 'stage3_active', 'stage3_multi_active')
PREFIXES = {'core': 'reliability_v4_humble41_probe01'}
PENDING = 'PENDING_MATRIX_RUNTIME_REVIEW_NOT_EXECUTABLE'
FINAL = 'FINAL_MATRIX_NORMAL_RUNNER_DEVELOPMENT_INDEPENDENTLY_REVIEWED'
require, sha, canonical = generic.require, generic.sha, generic.canonical
read_small, write_new = generic.read_small, generic.write_new


def utc():
    return datetime.now(timezone.utc).isoformat()


def tool_manifest():
    require(Path(source.__file__).resolve(strict=True) == (EXTERNAL/'source_runtime41.py').resolve(strict=True),
        'Named independent source41 binding helper required')
    require(Path(owner.__file__).resolve(strict=True) == (EXTERNAL/'local_runtime_observer41.py').resolve(strict=True)
        and sha(owner.__file__) == OWNER_SHA
        and sha(EXTERNAL/'test_local_runtime_observer41.py') == OWNER_TEST_SHA,
        'Final separately reviewed owner41 source/test bytes required')
    require(sha(EXTERNAL/'root_archive_observer41_pressure01.py') == PRESSURE_SHA
        and sha(EXTERNAL/'root_archive_observer41_pressure01.sh') == PRESSURE_SHELL_SHA,
        'Reviewed no-SITL pressure harness bytes changed')
    files = {}
    for name in OWN_FILES:
        path = EXTERNAL/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
            'Missing bounded external41 matrix helper')
        files[name] = sha(path)
    return {'schema_version': 1, 'scope': SCOPE, 'files': files,
        'source41_tools_canonical_sha256': canonical(source.tool_manifest()),
        'owner41_sha256': OWNER_SHA, 'owner41_test_sha256': OWNER_TEST_SHA,
        'collector41_sha256': COLLECTOR_SHA,
        'pressure_harness_sha256': PRESSURE_SHA, 'pressure_shell_sha256': PRESSURE_SHELL_SHA,
        'normal_runner_apis': ['make_plan', 'persist_plan', 'run_plan'],
        'driver_acquires_machine_sitl_lock': False, 'run_plan_acquires_own_sitl_lock': True,
        'maximum_new_trials_per_normal_runner_call': 1, 'automatic_retry': False,
        'automatic_followon_action': False, 'default_real_contract': None,
        'flight_or_evaluator_argv_modified': False, 'formal_seed_use_authorized': False,
        'core_cells': 12, 'extension_actions_exposed': False, 'classes': list(CLASSES), 'seed': 4,
        'prerequisite': 'same-source actual no-SITL archive pressure PASS; original40 unchanged; rechecked before each flight',
        'single_car_probe_required': False, 'groups': list(GROUPS),
        'required_simulation_pacing': source.EXPECTED_PACING_V2,
        'expected_class_policy': source.EXPECTED_CLASS_POLICY,
        'exclusive_measurement_validator': 'actual frozen runner.exclusive_navigation_runtime_evidence',
        'observer_owner': 'local_runtime_observer41; native tmpfs exit then bounded1800s archive; caller actual result persisted',
        'observer_session_wall_s': 7200, 'observer_rotation_wall_s': 5400,
        'observer_max_sample_age_wall_s': 10., 'observer_archive_wall_budget_s': 1800.,
        'core_driver': 'observed_driver01', 'resume_or_recovery_authorized': False,
        'immutable_plan_identity': 'EXACT_SHA256_AND_SAME_PHYSICAL_FILE'}


def locations(kind):
    require(kind == 'core', 'Humble41 release supports only a new core12; safety/extension require separate tooling')
    root = Path(ROOT)
    output = root/'results'/f'{PREFIXES[kind]}_seed004_matrix'
    return {'output': output, 'plan': output/'plan.json',
        'run_driver': output/'observed_driver01',
        'plan_driver': root/f'results/freeze_validation/matrix_runner41_{kind}_plan_driver01',
        'pending_contract': EXTERNAL/f'matrix_runner41_contract_{kind}_pending01.json'}


def entry_binding(review, built):
    borrowed = dict(built, _reviewed_tools_sha256=canonical(source.tool_manifest()))
    require(review.get('files', {}).get('scripts/observe_runtime_health.py') == COLLECTOR_SHA
        and sha(Path(ROOT)/'scripts/observe_runtime_health.py') == COLLECTOR_SHA,
        'Actual source41 collector differs from final reviewed native tmpfs collector')
    return {'source41_binding': source.entry_binding(review, borrowed),
        'matrix_tools_canonical_sha256': canonical(tool_manifest())}


def require_runtime(review, checks):
    result = source.require_runtime(review, checks)
    command = ['/bin/bash', ROOT+'/scripts/run_stage1_flight.sh', 'check', 'person']
    actual = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=60)
    require(actual.returncode == 0 and actual.stdout.strip(), 'Person read-only runtime preflight failed')
    result['checks']['person_check'] = {'command': command, 'returncode': actual.returncode,
        'output_lines': sorted(re.sub(r'\(0x[0-9a-fA-F]+\)', '(address omitted)', actual.stdout).splitlines())}
    return result


def validate_pacing(plan, trial, runner):
    expected = canonical(source.EXPECTED_PACING_V2)
    require(runner.simulation_pacing_declared(plan['protocol'])
        and canonical(runner.SIMULATION_PACING_V2) == expected
        and canonical(plan['protocol'].get(source.PACING_FIELD)) == expected
        and canonical(trial.get(source.PACING_FIELD)) == expected
        and canonical(runner.simulation_pacing_trial_binding(plan, trial)) == expected,
        'Every class/cell must explicitly bind complete41 V2 pacing')
    command = trial.get('flight_command')
    require(type(trial.get(source.ADAPTER_FIELD)) in (int, float) and trial[source.ADAPTER_FIELD] == 50.
        and isinstance(command, list) and all(isinstance(token, str) for token in command)
        and command.count(source.ADAPTER_FLAG) == 1
        and not any(token.startswith(source.ADAPTER_FLAG+'=') for token in command)
        and command.index(source.ADAPTER_FLAG)+1 < len(command),
        'One explicit adapter50 spec/argv binding required')
    try:
        rate = float(command[command.index(source.ADAPTER_FLAG)+1])
    except (ValueError, TypeError) as error:
        raise ValueError('Adapter50 argv must be numeric') from error
    require(rate == 50., 'Adapter publication cadence differs from registered50')


def validate_matrix(plan, runner, kind, path=None):
    runner.validate_plan(plan, path)
    selected = locations(kind)
    dimensions = GROUPS
    expected_ids = [f'{cls}_{cell}_seed004' for cls in CLASSES for cell in dimensions]
    require(plan.get('mode') == 'PROBE'
        and plan.get('frozen_root') == ROOT and plan.get('prefix') == PREFIXES[kind]
        and Path(plan['output']).resolve() == selected['output'].resolve()
        and plan.get('selected_classes') == list(CLASSES) and plan.get('selected_seeds') == [4]
        and type(plan['selected_seeds'][0]) is int
        and plan.get('selected_groups') == list(GROUPS)
        and isinstance(plan.get('trials'), list)
        and [trial.get('id') for trial in plan['trials']] == expected_ids,
        'Exact fresh41 class2/seed004 core12 matrix required')
    require(plan.get('trial_timeout_s') == 2800. and plan.get('postprocessing_timeout_s') == 1800.
        and plan.get('evaluation_timeout_s') == 1800., 'Registered41 original child budgets required')
    source.validate_class_policy(plan['protocol'], runner)
    for trial, (cls, cell) in zip(plan['trials'], ((cls, cell) for cls in CLASSES for cell in dimensions)):
        car = cls == 'car'
        require(trial.get('target_class') == cls and type(trial.get('seed')) is int and trial['seed'] == 4
            and trial.get('duration_s') == 75. and trial.get('wall_timeout_s') == 1000.
            and trial.get('model') == ('models/yolo11m_car_sim_train20_04.pt' if car else 'models/yolo11n.pt')
            and type(trial.get('inference_image_size')) is int and trial['inference_image_size'] == (640 if car else 320)
            and type(trial.get('inference_threads')) is int and trial['inference_threads'] == (4 if car else 2)
            and runner.correlated_two_face_trial_binding(plan, trial) == (car, car)
            and runner.car_surface_recovery_declared(plan['protocol'])
            and runner.car_surface_recovery_trial_binding(plan, trial) == (car, car),
            'Original class model/resources/car-only geometry and surface recovery required')
        require(trial.get('group') == cell,
            'Matrix cell identity differs')
        expected_distance = 9. if car else 5.
        require(trial.get('desired_distance_m') == expected_distance, 'Original registered class/condition distance required')
        validate_pacing(plan, trial, runner)
        validate_exclusive_trial(plan, trial, runner)
    return plan


def validate_exclusive_trial(plan, trial, runner):
    car = trial['target_class'] == 'car'
    require((trial.get(source.EXCLUSIVE_FIELD) is True if car else source.EXCLUSIVE_FIELD not in trial)
        and runner.exclusive_navigation_trial_binding(plan, trial) == (car, car),
        'Actual41 immutable trial must retain car-only explicit exclusive policy')
    command = trial['flight_command']
    require(command.count(source.EXCLUSIVE_FLAG) == int(car)
        and not any(value.startswith(source.EXCLUSIVE_FLAG+'=') for value in command),
        'Actual41 original exclusive CLI binding differs')


def validate_exclusive_runtime(plan, trial, configuration, parameters, runner):
    source.validate_class_policy(plan['protocol'], runner)
    validate_exclusive_trial(plan, trial, runner)
    cls = trial['target_class']; car = cls == 'car'
    result = runner.exclusive_navigation_runtime_evidence(plan['protocol']['resources'][cls], cls,
        configuration, parameters, trial['flight_command'])
    require(isinstance(result, dict) and result.get('enabled') is car and result.get('explicit') is car
        and result.get('errors') == [], 'Actual41 frozen exclusive runtime validator rejected archive')
    return {**result, 'supported_birth_confirmation':
        source.validate_supported_birth_runtime(cls, configuration, parameters)}


def exclusive_runtime_archive(runner, plan, trial, record):
    import yaml
    directory = Path(trial['directory'])
    config_path, parameters_path = directory/'run_config.json', directory/'configuration/runtime_parameters.yaml'
    config_binding = stable.metadata_binding(config_path, json_only=True)
    require(parameters_path.is_file() and not parameters_path.is_symlink()
        and parameters_path.stat().st_size <= 1024*1024, 'Named bounded actual runtime YAML required')
    parameters_binding = {'path': str(parameters_path), 'sha256': sha(parameters_path)}
    configuration = read_small(config_path)
    parameters = yaml.safe_load(parameters_path.read_text(encoding='utf-8'))
    evidence = validate_exclusive_runtime(plan, trial, configuration, parameters, runner)
    recorded = record.get('runtime_configuration', {})
    require(recorded.get('errors') == [] and recorded.get('run_config_sha256') == config_binding['sha256']
        and recorded.get('runtime_parameters_sha256') == parameters_binding['sha256']
        and sha(config_path) == config_binding['sha256'] and sha(parameters_path) == parameters_binding['sha256'],
        'Original41 runtime archive changed or differs from original terminal')
    return {'normal_runner_evidence': evidence, 'run_config': config_binding, 'runtime_parameters': parameters_binding}


def checked_plan(kind, runner, supplied=None, supplied_path=None):
    path = locations(kind)['plan']
    require(supplied_path is None or Path(supplied_path) == path, 'Only the actual41 canonical matrix path is supported')
    plan = read_small(path)
    require(supplied is None or supplied == plan, 'Supplied matrix differs from its original actual file')
    validate_matrix(plan, runner, kind, path)
    runner.verify_sources(plan)
    return plan


def pending_identity(plan):
    return {'plan': stable.metadata_binding(Path(plan['output'])/'plan.json', json_only=True),
        'plan_sha256': plan['plan_sha256'], 'slot_ids': [trial['id'] for trial in plan['trials']],
        'initial_status_counts': {'PENDING': len(plan['trials'])}}


def require_same_metadata_file(actual, expected):
    """A lexical /root symlink alias is valid only for the same bound file."""
    require(isinstance(actual, dict) and isinstance(expected, dict)
        and set(actual) == set(expected) == {'path', 'sha256'}
        and generic.valid_sha(actual.get('sha256')) and actual['sha256'] == expected.get('sha256'),
        'Immutable matrix plan SHA256 changed')
    left, right = Path(actual['path']), Path(expected['path'])
    require(left.is_file() and right.is_file() and not left.is_symlink() and not right.is_symlink()
        and left.samefile(right), 'Immutable matrix plan paths do not name the same physical file')






def make_observer(modules, directory):
    return owner.make_observer(directory/'observer_driver', ROOT, archive_wall_budget_s=1800.)


def finish_action(review, built, runner, observer, directory, modules):
    errors, after, residual, observed = [], None, None, None
    actual_owner = observer._finished
    try: after = entry_binding(review, built)
    except BaseException as caught: errors.append('binding:'+type(caught).__name__+':'+str(caught))
    try:
        residual = runner.simulation_processes()
        require(residual == [], 'Residual runtime processes remain')
    except BaseException as caught: errors.append('residual:'+type(caught).__name__+':'+str(caught))
    try:
        observed = owner.validate_observer_root(actual_owner, directory/'observer_driver', ROOT)
    except BaseException as caught: errors.append('observer:'+type(caught).__name__+':'+str(caught))
    return {'entry_binding_after': after, 'cleanup': {'residual_processes': residual},
        'observer_owner_terminal': actual_owner, 'observer': observed, 'final_errors': errors}


def require_prerequisites(kind, args, review, built, runner):
    require(kind == 'core', 'Only the complete new41 core12 is supported')
    return require_completed_pressure(review, built)


def retained_original_stat():
    """Only stat original40 large artifacts; never salvage, rewrite, or regrade."""
    values = {}
    for relative in ('owned_spool.json', 'rosbag/metadata.yaml', 'rosbag/rosbag_0.db3',
                     'archive/rosbag_0.db3.zstd'):
        path = Path(ORIGINAL_SPOOL)/relative
        require(path.is_file() and not path.is_symlink(), 'Original40 retained spool artifact missing')
        item = path.stat()
        values[relative] = {'bytes': item.st_size, 'mtime_ns': item.st_mtime_ns,
                            'inode': item.st_ino, 'device': item.st_dev}
    return values


def pressure_artifact(directory, name, expected):
    require(name in ('archive_worker.json', 'archive_worker_console.log', 'checks.jsonl')
        and isinstance(expected, dict) and set(expected) == {'bytes', 'sha256'},
        'Exact actual pressure artifact binding required')
    path = directory/name
    require(type(expected['bytes']) is int and 0 <= expected['bytes'] <= generic.MAX_SMALL
        and generic.valid_sha(expected['sha256']) and path.is_file() and not path.is_symlink()
        and path.stat().st_size == expected['bytes'] and sha(path) == expected['sha256'],
        'Actual pressure artifact bytes/hash changed: '+name)
    return {'path': str(path), **expected}


def require_completed_pressure(review, built):
    """Admit only the original same-source native-and-copy pressure execution."""
    directory = Path(ROOT)/'results/freeze_validation/observer_archive_pressure01'
    path = directory/'execution_terminal.json'
    terminal_binding = stable.metadata_binding(path, json_only=True)
    value = read_small(path)
    summary = source.build_evidence(review)['summary']
    require(built.get('bound_build_metadata', {}).get('summary') == summary
        and review.get('frozen_root') == ROOT
        and review.get('files', {}).get('scripts/observe_runtime_health.py') == COLLECTOR_SHA
        and sha(Path(ROOT)/'scripts/observe_runtime_health.py') == COLLECTOR_SHA
        and value.get('source') == {'script': PRESSURE_SHA, 'collector': COLLECTOR_SHA,
            'owner': OWNER_SHA, 'build_summary': summary['sha256']},
        'Actual41 source, cold-build, collector, owner, and pressure harness must match')
    require(value.get('schema_version') == 1
        and value.get('scope') == 'ACTUAL_NO_SITL_ARCHIVE_PRESSURE_DIAGNOSTIC_ONLY'
        and value.get('root') == ROOT and value.get('status') == 'PASS'
        and value.get('error') is None and value.get('original_spool') == ORIGINAL_SPOOL
        and value.get('original_attempt_status') == 'INFRASTRUCTURE_ERROR_RETAINED'
        and value.get('original_attempt_regraded') is False
        and value.get('no_simulator_started') is True
        and type(value.get('formal_trials_executed')) is int and value['formal_trials_executed'] == 0
        and value.get('pressure_workload_wall_budget_s') == 2400.
        and value.get('original_stat_unchanged') is True and value.get('cleanup_actions') == []
        and type(value.get('worker_exit_code')) is int and value['worker_exit_code'] == 0
        and value.get('rosbag_published') is True,
        'Original same-source actual no-SITL pressure must PASS without cleanup or regrading')
    require(value.get('original_stat_before') == value.get('original_stat_after') == retained_original_stat(),
        'Original40 spool stat evidence changed or was not retained')
    old = read_small(ORIGINAL_SLOT)
    require(sha(ORIGINAL_SLOT) == ORIGINAL_SLOT_SHA and old.get('status') == 'INFRASTRUCTURE_ERROR'
        and old.get('infrastructure_stop') is True
        and value.get('original_failed_slot') == {'path': ORIGINAL_SLOT, 'sha256': ORIGINAL_SLOT_SHA,
            'status': 'INFRASTRUCTURE_ERROR'}
        and value.get('original_spool_owner') == read_small(Path(ORIGINAL_SPOOL)/'owned_spool.json'),
        'Original40 failed attempt or spool ownership changed')
    clone = Path(value.get('diagnostic_clone', ''))
    local = Path(value.get('local_evidence', ''))
    require(clone.parent == Path(ORIGINAL_SPOOL).parent and clone != Path(ORIGINAL_SPOOL)
        and re.fullmatch(r'trial_[A-Za-z0-9_]+', clone.name)
        and local.parent == Path('/dev/shm') and local.name.startswith('uav_tracking_root41_pressure_')
        and value.get('command') == [sys.executable, '-B', str(EXTERNAL/'root_archive_observer41_pressure01.py'),
            '--archive-worker', str(clone), str(directory/'rosbag'), str(local/'archive_worker.json')],
        'Actual pressure worker command/owned clone provenance differs')
    artifacts = value.get('diagnostic_artifacts')
    require(isinstance(artifacts, dict) and set(artifacts) ==
        {'archive_worker.json', 'archive_worker_console.log', 'checks.jsonl'},
        'Original complete pressure artifact set required')
    bound = {name: pressure_artifact(directory, name, entry) for name, entry in artifacts.items()}
    worker = read_small(directory/'archive_worker.json')
    result = worker.get('result', {})
    metadata = directory/'rosbag/metadata.yaml'
    require(metadata.is_file() and not metadata.is_symlink() and metadata.stat().st_size <= 1024*1024,
        'Named bounded pressure metadata.yaml required; no bag payload is reread')
    require(worker.get('status') == 'PASS' and worker.get('original_spool') == ORIGINAL_SPOOL
        and worker.get('diagnostic_clone') == str(clone) and worker.get('original_attempt_regraded') is False
        and owner.finite(worker.get('total_wall_s')) and 0 <= worker['total_wall_s'] <= 2400.
        and result.get('status') == 'PASS' and result.get('source_spool') == str(clone)
        and result.get('destination') == str(directory/'rosbag')
        and result.get('recorder_exit_code') == 0
        and result.get('raw_validation', {}).get('status') == 'PASS'
        and result.get('native_reader_validation', {}).get('status') == 'PASS'
        and sha(metadata) == result.get('published_metadata_sha256'),
        'Actual unchanged finalize_recording completion evidence differs')
    checks_path = directory/'checks.jsonl'
    checks = [json.loads(line) for line in checks_path.read_text(encoding='utf-8').splitlines()]
    require(type(value.get('check_count')) is int and value['check_count'] == len(checks) and checks,
        'Original pressure freshness check denominator differs')
    ages, latencies = [], []
    for check in checks:
        fresh = check.get('fresh', {})
        age, latency = fresh.get('sample_age_wall_s'), check.get('check_latency_wall_s')
        require(owner.finite(age) and -1e-6 <= age <= 10. and fresh.get('max_sample_age_wall_s') == 10.
            and owner.finite(latency) and latency >= 0., 'Original10s pressure freshness failed')
        ages.append(age); latencies.append(latency)
    require(value.get('max_observer_sample_age_wall_s') == max(ages)
        and value.get('max_check_latency_wall_s') == max(latencies),
        'Pressure aggregate differs from its original checks')
    observed = owner.validate_observer_root(value.get('observer'), directory/'observer_driver', ROOT)
    require(value.get('observer_validation') == observed and observed.get('owner_terminal') == value['observer'],
        'Original pressure owner outcome differs from independently validated raw archive')
    require(stable.metadata_binding(path, json_only=True) == terminal_binding,
        'Original pressure terminal changed during validation')
    return {'result': 'PASS', 'execution_terminal': terminal_binding, 'build_summary': summary,
        'observer': observed, 'diagnostic_artifacts': bound,
        'original40_failed_slot': value['original_failed_slot'],
        'original40_stat_unchanged': True, 'original40_regraded': False,
        'formal_seed_use_authorized': False}


def plan_matrix(kind, args, review, built, runner, modules, runtime, evidence):
    selected = locations(kind)
    require(not any(path.exists() or path.is_symlink() for key, path in selected.items()
        if key in ('output', 'plan_driver', 'pending_contract')) and not runner.simulation_processes(),
        'Fresh plan/driver/pending-contract paths and idle runtime required')
    prerequisites = require_prerequisites(kind, args, review, built, runner)
    before = entry_binding(review, built)
    directory = selected['plan_driver']
    directory.mkdir(exist_ok=False)
    observer = make_observer(modules, directory)
    error, initial = None, None
    try:
        with observer:
            plan = runner.make_plan(Path(ROOT), selected['output'], PREFIXES[kind],
                formal=False, seeds=[4], groups=list(GROUPS), classes=list(CLASSES))
            validate_matrix(plan, runner, kind)
            runner.persist_plan(plan)
            rows = runner.read_slots(plan)
            require(set(rows) == {trial['id'] for trial in plan['trials']}
                and all(row['status'] == 'PENDING' for row in rows.values()), 'Every new matrix slot must be untouched PENDING')
            initial = pending_identity(plan)
            require(require_prerequisites(kind, args, review, built, runner) == prerequisites,
                'Actual extension prerequisites changed during planning')
            observer.check()
    except BaseException as caught: error = type(caught).__name__+':'+str(caught)
    cleanup = finish_action(review, built, runner, observer, directory, modules)
    require_same = cleanup['entry_binding_after'] == before
    code = 0 if error is None and initial and require_same and not cleanup['final_errors'] else 2
    terminal_path = directory/'execution_terminal.json'
    write_new(terminal_path, {'schema_version': 1, 'scope': SCOPE, 'action': 'plan', 'matrix_kind': kind,
        'finished_utc': utc(), 'returncode': code, 'error': error, 'entry_binding_before': before,
        'initial_pending': initial, 'prerequisites': prerequisites, 'runtime_preflight': runtime,
        **cleanup, 'flights_started': 0, 'formal_seed_use_authorized': False, 'automatic_next_action': False})
    if code == 0:
        value = {'schema_version': 1, 'scope': SCOPE, 'status': PENDING, 'matrix_kind': kind, 'created_utc': utc(),
            'frozen_root': ROOT, 'source_review': review['_review_binding'], 'entry_binding': before,
            'tools_canonical_sha256': canonical(tool_manifest()), 'build_evidence': evidence,
            'plan_pending': initial, 'plan_terminal': stable.metadata_binding(terminal_path, json_only=True),
            'prerequisites': prerequisites, 'experiment': {'classes': list(CLASSES), 'seed': 4,
                'duration_s': 75., 'flight_count': 12},
            'formal_seed_use_authorized': False, 'readiness_claimed': False,
            'automatic_retry': False, 'automatic_next_action': False}
        write_new(selected['pending_contract'], value)
        print(json.dumps({'pending_contract': str(selected['pending_contract']), 'sha256': sha(selected['pending_contract']),
            'status': PENDING, 'flights_started': 0}), flush=True)
    return code


def load_contract(kind, path, expected_sha, args, review, built, runner, modules):
    require(kind == 'core', 'Only the complete new41 core12 is supported')
    require(path is not None and generic.valid_sha(expected_sha), 'Explicit separately reviewed matrix contract SHA required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True)
        and re.fullmatch(r'matrix_runner41_contract_'+kind+r'_[A-Za-z0-9_]+\.json', path.name),
        'Named external41 contract for the selected matrix required')
    value = read_small(path)
    require(sha(path) == expected_sha and type(value.get('schema_version')) is int and value['schema_version'] == 1
        and value.get('scope') == SCOPE and value.get('status') == FINAL and value.get('matrix_kind') == kind
        and value.get('frozen_root') == ROOT and value.get('source_review') == review['_review_binding']
        and value.get('entry_binding') == entry_binding(review, built)
        and value.get('tools_canonical_sha256') == canonical(tool_manifest())
        and value.get('build_evidence') == source.build_evidence(review),
        'Concrete final same-source/build/tools matrix contract required; pending cannot execute')
    require(value.get('experiment') == {'classes': list(CLASSES), 'seed': 4,
        'duration_s': 75., 'flight_count': 12}
        and type(value['experiment']['seed']) is int and type(value['experiment']['flight_count']) is int
        and all(value.get(name) is False for name in ('formal_seed_use_authorized', 'readiness_claimed',
            'automatic_retry', 'automatic_next_action')), 'Only the original complete development matrix is authorized')
    plan = checked_plan(kind, runner)
    initial = pending_identity(plan)
    prerequisites = require_prerequisites(kind, args, review, built, runner)
    require(value.get('plan_pending') == initial and value.get('prerequisites') == prerequisites,
        'Original plan or actual core/safety prerequisite binding changed')
    require('zero_attempt_recovery' not in value, 'New41 contract cannot carry any inherited recovery permission')
    selected = locations(kind)
    terminal_path = selected['plan_driver']/'execution_terminal.json'
    require(stable.metadata_binding(terminal_path, json_only=True) == value.get('plan_terminal'), 'Original plan terminal changed')
    terminal = read_small(terminal_path)
    require(terminal.get('scope') == SCOPE and terminal.get('action') == 'plan' and terminal.get('matrix_kind') == kind
        and type(terminal.get('returncode')) is int and terminal['returncode'] == 0 and terminal.get('error') is None
        and terminal.get('initial_pending') == initial and terminal.get('flights_started') == 0
        and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == entry_binding(review, built)
        and terminal.get('prerequisites') == prerequisites and terminal.get('final_errors') == []
        and terminal.get('cleanup', {}).get('residual_processes') == [], 'Original matrix plan did not close cleanly')
    observed = owner.validate_observer_root(terminal.get('observer_owner_terminal'),
        selected['plan_driver']/'observer_driver', ROOT)
    require(terminal.get('observer') == observed, 'Original plan observer differs from its actual owner outcome')
    return value, plan


def observed_run_plan(runner, plan, observer):
    # No outer runner.run_lock: the original normal runner acquires it itself.
    def execute(command, log, cwd, timeout):
        return stable.execute_owned(command, log, observer, timeout, cwd)
    return runner.run_plan(plan, max_new_trials=1, command_runner=execute)


def audit_record(runner, plan, trial, record, review, checks, *, extension=False):
    binding = checks.require_completed_record(runner, plan, trial, record)
    runtime = runner.runtime_configuration(plan, trial)
    require(runtime.get('errors') == [], 'Actual original matrix runtime configuration differs')
    entries = []
    for spec in trial['evaluations']:
        recorded = next((entry for entry in record['evaluations'] if entry['kind'] == spec['kind']), None)
        require(isinstance(recorded, dict) and isinstance(recorded.get('execution'), dict),
            'Actual original evaluator execution is missing: '+spec['kind'])
        execution = recorded['execution']
        require(execution.get('command') == spec['command'] and type(execution.get('returncode')) is int
            and execution['returncode'] in (0, 2) and execution.get('error') is None,
            'Original evaluator command/execution differs: '+spec['kind'])
        current = runner.read_evaluation(spec, execution, plan)
        require(current == recorded, 'Original evaluator report/hash changed: '+spec['kind'])
        entries.append(current)
    require(all(next((entry['result'] for entry in entries if entry['kind'] == kind), None) == 'PASS'
        for kind in ('source_clock', 'native_startup')), 'Original source-clock/native-startup evidence must independently PASS')
    flight = next(entry for entry in record['commands'] if entry['kind'] == 'flight')
    require(flight.get('command') == trial['flight_command'] and type(flight.get('returncode')) is int
        and flight['returncode'] == 0 and flight.get('error') is None,
        'Original flight command/execution differs')
    result, _ = runner.engineering_verdict(plan, trial, flight, entries)
    require(result == record['status'] == record['engineering_result'], 'Original engineering verdict changed on actual report reread')
    audited = {'record_binding': binding, 'runtime': runtime,
        'exclusive_navigation': exclusive_runtime_archive(runner, plan, trial, record),
        'bridge': checks.bridge_evidence(trial['directory'], review),
        'processes': checks.process_evidence(trial['directory'], stage=trial['stage'],
            multi_target=trial['multi_target'], condition=trial.get('condition', 'clean')),
        'closed75_archive': checks.closed75_archive(trial, record)}
    if extension:
        audited['known_algorithm_failures'] = runner.extension_algorithm_failures(plan, trial, flight, entries)
    return audited


def run_matrix(kind, args, review, built, runner, modules, runtime):
    contract, plan = load_contract(kind, args.contract, args.contract_sha256,
        args, review, built, runner, modules)
    selected = locations(kind)
    directory = selected['run_driver']
    rows = runner.read_slots(plan)
    require(all(row['status'] == 'PENDING' for row in rows.values()) and not directory.exists()
        and not directory.is_symlink() and not runner.simulation_processes(),
        'Fresh matrix requires every slot untouched PENDING and idle runtime; no resume or retry')
    before = entry_binding(review, built)
    directory.mkdir(exist_ok=False)
    observer = make_observer(modules, directory)
    attempts, completed, error = [], [], None
    checks = modules['humble33_diagnostic_checks01']
    try:
        with observer:
            for number, trial in enumerate(plan['trials'], 1):
                require(entry_binding(review, built) == before, 'Source/build/tools changed before next original slot')
                require(sha(args.contract) == args.contract_sha256, 'Final matrix contract changed')
                require(require_prerequisites(kind, args, review, built, runner) == contract['prerequisites'],
                    'Actual extension prerequisites changed')
                runner.verify_sources(plan)
                require_same_metadata_file(stable.metadata_binding(selected['plan'], json_only=True),
                    contract['plan_pending']['plan'])
                rows = runner.read_slots(plan)
                require(rows[trial['id']]['status'] == 'PENDING' and not runner.simulation_processes(),
                    'Original slot already attempted or runtime active; no retry')
                for previous in completed:
                    require(checks.terminal_binding(runner, plan, next(t for t in plan['trials'] if t['id'] == previous['slot']),
                        rows[previous['slot']]) == previous['audit']['record_binding'], 'Prior immutable terminal changed')
                observer.check()
                attempt = {'slot': trial['id'], 'number': number, 'started_utc': utc(),
                    'runner_result': None, 'record': None, 'audit': None, 'error': None}
                attempts.append(attempt)
                marker_path = directory/f'{number:02d}_{trial["id"]}.started.json'
                write_new(marker_path,
                    {'slot': trial['id'], 'number': number, 'entry_binding': before,
                        'contract': {'path': str(args.contract), 'sha256': args.contract_sha256},
                        'plan_sha256': plan['plan_sha256'], 'started_utc': attempt['started_utc'], 'original_attempt_number': 1})
                attempt['started_marker'] = stable.metadata_binding(marker_path, json_only=True)
                print(json.dumps({'event': 'START_ORIGINAL_MATRIX_SLOT', 'slot': trial['id'],
                    'number': number, 'total': len(plan['trials'])}), flush=True)
                try:
                    attempt['runner_result'] = observed_run_plan(runner, plan, observer)
                    record = runner.read_slots(plan)[trial['id']]
                    attempt['record'] = {'status': record.get('status'), 'engineering_result': record.get('engineering_result'),
                        'record_binding': checks.terminal_binding(runner, plan, trial, record)}
                    attempt['audit'] = audit_record(runner, plan, trial, record, review, checks, extension=kind == 'extension')
                    require(attempt['runner_result'].get('started_this_invocation') == 1, 'Normal runner did not consume exactly one original slot')
                    observer.check()
                    require(entry_binding(review, built) == before, 'Source/build/tools changed during original slot')
                    require(sha(args.contract) == args.contract_sha256, 'Matrix contract changed during original slot')
                    completed.append({'slot': trial['id'], 'status': record['status'], 'engineering_result': record['engineering_result'],
                        'audit': attempt['audit']})
                except BaseException as caught:
                    attempt['error'] = type(caught).__name__+':'+str(caught)
                    raise
                finally:
                    attempt['finished_utc'] = utc()
                    write_new(directory/f'{number:02d}_{trial["id"]}.attempt_terminal.json', attempt)
    except BaseException as caught: error = type(caught).__name__+':'+str(caught)
    cleanup = finish_action(review, built, runner, observer, directory, modules)
    code = 0 if error is None and len(completed) == len(plan['trials']) and cleanup['entry_binding_after'] == before and not cleanup['final_errors'] else 2
    actual_rows, row_error = None, None
    try:
        actual_rows = {key: {'status': row.get('status'), 'record_sha256': row.get('record_sha256')}
            for key, row in runner.read_slots(plan).items()}
    except BaseException as caught:
        row_error = type(caught).__name__+':'+str(caught)
        code = 2
    write_new(directory/'execution_terminal.json', {'schema_version': 1, 'scope': SCOPE, 'action': 'run',
        'matrix_kind': kind, 'finished_utc': utc(), 'returncode': code,
        'status': 'ORIGINAL_MATRIX_TERMINALS_COMPLETE' if code == 0 else 'STOPPED_ORIGINAL_ATTEMPTS_RETAINED',
        'error': error, 'entry_binding_before': before, 'runtime_preflight': runtime,
        'contract': {'path': str(args.contract), 'sha256': args.contract_sha256},
        'plan': contract['plan_pending'], 'prerequisites': contract['prerequisites'],
        'planned_count': len(plan['trials']), 'attempt_count': len(attempts), 'terminal_count': len(completed),
        'attempts': attempts, 'slots': completed, 'actual_slot_statuses': actual_rows, 'slot_read_error': row_error,
        'status_counts': dict(Counter(row['status'] for row in (actual_rows or {}).values())), **cleanup,
        'formal_seed_use_authorized': False, 'readiness_claimed': False, 'automatic_retry': False,
        'automatic_next_action': False,
        'claim_boundary': 'Closed original development attempts preserve algorithm FAIL. They do not establish formal admission or full project acceptance.'})
    return code


def require_completed_core(review, built, runner, core_plan=None, core_plan_path=None, *, all_pass=False):
    """Shared actual metadata verifier for safety and extension prerequisites."""
    require(type(all_pass) is bool, 'Explicit boolean core admission policy required')
    plan = checked_plan('core', runner, core_plan, core_plan_path)
    selected = locations('core')
    path = selected['run_driver']/'execution_terminal.json'
    terminal = read_small(path)
    modules = stable.dependencies()
    checks = modules['humble33_diagnostic_checks01']
    source = entry_binding(review, built)
    require(terminal.get('schema_version') == 1 and terminal.get('scope') == SCOPE
        and terminal.get('action') == 'run' and terminal.get('matrix_kind') == 'core'
        and type(terminal.get('returncode')) is int and terminal['returncode'] == 0
        and terminal.get('status') == 'ORIGINAL_MATRIX_TERMINALS_COMPLETE'
        and terminal.get('error') is None and terminal.get('slot_read_error') is None
        and terminal.get('planned_count') == terminal.get('attempt_count') == terminal.get('terminal_count') == 12
        and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == source
        and terminal.get('final_errors') == [] and terminal.get('cleanup', {}).get('residual_processes') == []
        and all(terminal.get(name) is False for name in ('formal_seed_use_authorized', 'readiness_claimed',
            'automatic_retry', 'automatic_next_action')), 'Actual41 core12 did not close completely and healthily')
    contract = terminal.get('contract', {})
    actual_contract, _ = load_contract('core', contract.get('path'), contract.get('sha256'),
        argparse.Namespace(), review, built, runner, modules)
    require(terminal.get('plan') == actual_contract['plan_pending']
        and terminal.get('prerequisites') == actual_contract['prerequisites']
        and 'zero_attempt_recovery' not in terminal,
        'Original core plan/runtime contract binding changed')
    expected_ids = [trial['id'] for trial in plan['trials']]
    require([item.get('slot') for item in terminal.get('slots', [])] == expected_ids
        and [item.get('slot') for item in terminal.get('attempts', [])] == expected_ids,
        'Original core12 slot/attempt denominator or order differs')
    rows, bound = runner.read_slots(plan), []
    for number, (trial, item, attempt) in enumerate(zip(plan['trials'], terminal['slots'], terminal['attempts']), 1):
        record = rows[trial['id']]
        audit = audit_record(runner, plan, trial, record, review, checks)
        require(item == {'slot': trial['id'], 'status': record['status'], 'engineering_result': record['engineering_result'], 'audit': audit}
            and attempt.get('number') == number and attempt.get('error') is None
            and attempt.get('audit') == audit and attempt.get('runner_result', {}).get('started_this_invocation') == 1
            and attempt.get('record') == {'status': record['status'], 'engineering_result': record['engineering_result'],
                'record_binding': audit['record_binding']},
            'Original core row/attempt/report binding changed')
        marker_path = selected['run_driver']/f'{number:02d}_{trial["id"]}.started.json'
        require(stable.metadata_binding(marker_path, json_only=True) == attempt.get('started_marker')
            and read_small(marker_path) == {'slot': trial['id'], 'number': number, 'entry_binding': source,
                'contract': contract, 'plan_sha256': plan['plan_sha256'], 'started_utc': attempt['started_utc'],
                'original_attempt_number': 1}, 'Original matrix driver started marker changed')
        attempt_path = selected['run_driver']/f'{number:02d}_{trial["id"]}.attempt_terminal.json'
        require(read_small(attempt_path) == attempt, 'Original core per-attempt terminal changed')
        if all_pass:
            require(record['status'] == record['engineering_result'] == 'PASS', 'All12 original core cells must PASS before extension planning or execution')
        bound.append({'id': trial['id'], 'status': record['status'], 'record_binding': audit['record_binding'],
            'attempt_terminal': stable.metadata_binding(attempt_path, json_only=True)})
    observed = owner.validate_observer_root(terminal.get('observer_owner_terminal'),
        selected['run_driver']/'observer_driver', ROOT)
    actual_rows = {key: {'status': row.get('status'), 'record_sha256': row.get('record_sha256')} for key, row in rows.items()}
    require(terminal.get('actual_slot_statuses') == actual_rows
        and terminal.get('status_counts') == dict(Counter(row['status'] for row in actual_rows.values()))
        and terminal.get('observer') == observed, 'Original core aggregate status/observer differs from actual evidence')
    require(not runner.simulation_processes(), 'Runtime residual remains after original core12')
    return {'result': 'PASS', 'core_plan': pending_identity(plan),
        'execution_terminal': stable.metadata_binding(path, json_only=True), 'completed_count': 12,
        'all_original_core_cells_pass': all(row['status'] == 'PASS' for row in bound),
        'original_terminals': bound, 'observer': observed, 'formal_seed_use_authorized': False}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', choices=('describe', 'plan-core', 'run-core'))
    result.add_argument('--review', type=Path); result.add_argument('--review-sha256')
    result.add_argument('--reviewed-tools-sha256'); result.add_argument('--frozen-root')
    result.add_argument('--contract', type=Path); result.add_argument('--contract-sha256')
    return result


def reviewed_source(args):
    require(args.action in ('plan-core', 'run-core'), 'Only new core12 development is in scope')
    require(args.action != 'describe' and args.frozen_root == ROOT
        and args.review is not None
        and generic.valid_sha(args.review_sha256) and generic.valid_sha(args.reviewed_tools_sha256)
        and canonical(tool_manifest()) == args.reviewed_tools_sha256,
        'Explicit41 source review/root/independently reviewed matrix tools required')
    if args.action.startswith('run-'):
        require(args.contract is not None and generic.valid_sha(args.contract_sha256),
            'Run requires a separate actual final matrix contract SHA')
    review = generic.load_review(args.review, args.review_sha256, 'validate')
    require(review['frozen_root'] == ROOT, 'Actual same-source41 source review required')
    return review


def shell_root(argv):
    reviewed_source(parser().parse_args(argv))
    return ROOT


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action == 'describe':
        manifest = tool_manifest()
        print(json.dumps({'status': TOOL_STATUS, 'tool_manifest': manifest,
            'tools_canonical_sha256': canonical(manifest), 'frozen_root': ROOT,
            'prefix': PREFIXES['core'], 'core_driver': 'observed_driver01',
            'interfaces_enabled': ['describe', 'plan-core', 'run-core'],
            'all_initial_slots_required': 'PENDING', 'resume_or_recovery_authorized': False,
            'requires_actual_source_review_and_build': True,
            'run_requires_separate_final_contract': True, 'actual_action_executed': False}, indent=2))
        return 0
    try:
        review = reviewed_source(args)
        generic.require_linux()
        modules = stable.dependencies()
        with generic.exclusive_window(), stable.stop_signals():
            evidence = source.build_evidence(review)
            built = stable.checked_build({'build_evidence': evidence}, review, modules['humble33_diagnostic_checks01'])
            runtime = require_runtime(review, modules['humble33_diagnostic_checks01'])
            require(canonical(tool_manifest()) == args.reviewed_tools_sha256, 'Reviewed matrix tools changed during preflight')
            runner = generic.runner_at(ROOT)
            verb, kind = args.action.split('-', 1)
            if verb == 'plan': return plan_matrix(kind, args, review, built, runner, modules, runtime, evidence)
            return run_matrix(kind, args, review, built, runner, modules, runtime)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as caught:
        print(json.dumps({'status': 'MATRIX_ACTION_REFUSED_OR_FAILED',
            'reason': type(caught).__name__+':'+str(caught), 'automatic_retry': False,
            'readiness_claimed': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
