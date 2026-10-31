"""Explicit same-source Humble41 extension16 development actions only.

Describe/import are inert. Plans produce pending, non-executable review
candidates. Runs require separately reviewed actual contracts. The normal
frozen runner alone owns its SITL lock and every original flight/evaluator argv.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
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
ROOT = source.ROOT
SCOPE = 'HUMBLE41_EXTENSION16_NORMAL_RUNNER_DEVELOPMENT_ONLY'
SOURCE_CANONICAL = '044ab32510e89c9da462040c5ff2391840b92ed6efd6dbda18fd218e6cd55686'
CORE_PY_SHA = '1e748d97f4c5687d53447af3acbe4506072279c063e6e77b31b262fe76df3ced'
CORE_TOOLS_SHA = '8c9241e5f9ba7a54988b27d0f016e40d52ece37b8c9c85de410cb24463361cf3'
OWN_FILES = ('extension_runner41.py', 'extension_runner41.sh', 'test_extension_runner41.py')
CLASSES = ('person', 'car')
GROUPS = ('stage1_velocity', 'stage1_position', 'stage2_crossing',
          'stage3_midpoint', 'stage3_active', 'stage3_multi_active')
CONDITIONS = ('depth_noise', 'depth_holes', 'dropout', 'latency', 'combined',
              'speed_changes_velocity', 'speed_changes_position', 'far_distance')
PREFIXES = {'core': 'reliability_v4_humble41_probe01',
            'extension': 'reliability_v4_humble41_extensions_probe'}
PENDING = 'PENDING_MATRIX_RUNTIME_REVIEW_NOT_EXECUTABLE'
FINAL = 'FINAL_MATRIX_NORMAL_RUNNER_DEVELOPMENT_INDEPENDENTLY_REVIEWED'
SAFETY_MODULE = 'safety_runner41'
SAFETY_PY_SHA = '68f0b5567daccb4e27c08ba2d28a82e53dc90793d12e884415e9c0d48ab7854f'
SAFETY_TOOLS_SHA = '4b2600def87b15d2c3bbc0fd2279aee55e14eaaef1c18e048f87b48cba3d09fd'
require, sha, canonical = generic.require, generic.sha, generic.canonical
read_small, write_new = generic.read_small, generic.write_new


def utc():
    return datetime.now(timezone.utc).isoformat()


def core_module():
    path = EXTERNAL/'matrix_runner41.py'
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
            'Actual bounded41 core-only dependency is required')
    source = path.read_bytes()
    require(hashlib.sha256(source).hexdigest() == CORE_PY_SHA,
            'Core41 Python bytes changed before module execution')
    name = '_humble41_extension_core_dependency'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, str(path), 'exec'), module.__dict__)
    require(Path(module.__file__).resolve(strict=True) == path.resolve(strict=True)
            and sha(path) == CORE_PY_SHA and canonical(module.tool_manifest()) == CORE_TOOLS_SHA,
            'Reviewed core41 dependency changed')
    return module


def checked_own_files():
    files = {}
    for name in OWN_FILES:
        path = EXTERNAL/name
        require(path.is_file() and not path.is_symlink()
                and path.stat().st_size <= generic.MAX_SMALL,
                'Missing or unsafe bounded external41 extension helper')
        files[name] = sha(path)
    return files


def tool_manifest():
    require(Path(source.__file__).resolve(strict=True) == (EXTERNAL/'source_runtime41.py').resolve(strict=True)
            and canonical(source.tool_manifest()) == SOURCE_CANONICAL,
            'Reviewed41 independent source/build binding chain changed')
    core = core_module()
    return {'schema_version': 1, 'scope': SCOPE,
        'status': 'RELEASE_CANDIDATE_PENDING_INDEPENDENT_TOOL_REVIEW',
        'files': checked_own_files(),
        'source41_tools_canonical_sha256': SOURCE_CANONICAL,
        'core_dependency': {'python_sha256': CORE_PY_SHA, 'tools_canonical_sha256': CORE_TOOLS_SHA,
                            'frozen_root': core.ROOT},
        'normal_runner_apis': ['make_extension_plan', 'persist_plan', 'run_plan'],
        'actions': ['plan-extension', 'run-extension'], 'extension_cells': 16,
        'classes': list(CLASSES), 'seed': 4, 'extension_conditions': list(CONDITIONS),
        'core_actions_exposed': False, 'requires_all12_original_core_pass': True,
        'requires_all4_original_safety_and_frozen_guard_pass': True,
        'required_simulation_pacing': source.EXPECTED_PACING_V2,
        'expected_class_policy': source.EXPECTED_CLASS_POLICY,
        'extension_safety_validator': SAFETY_MODULE+'.require_completed_safety',
        'safety_dependency': {'python_sha256': SAFETY_PY_SHA, 'tools_canonical_sha256': SAFETY_TOOLS_SHA},
        'observer_owner_dependency': core.tool_manifest()['owner41_sha256'],
        'observer_original_post_wait_terminal_required': True,
        'observer_max_sample_age_wall_s': 10., 'observer_archive_wall_budget_s': 1800.,
        'extension_safety_python_bytes_sha_checked_before_exec': True,
        'maximum_new_trials_per_normal_runner_call': 1,
        'driver_acquires_machine_sitl_lock': False, 'run_plan_acquires_own_sitl_lock': True,
        'original_algorithm_failures_retained': True, 'formal_seed_use_authorized': False,
        'automatic_retry': False, 'automatic_followon_action': False,
        'flight_or_evaluator_argv_modified': False, 'default_real_contract': None,
        'immutable_plan_identity': 'EXACT_SHA256_AND_SAME_PHYSICAL_FILE'}




def locations(kind):
    require(kind in ('core', 'extension'), 'Unknown development matrix')
    if kind == 'core':
        return core_module().locations('core')
    root = Path(ROOT)
    output = root/'results'/f'{PREFIXES[kind]}_seed004_matrix'
    return {'output': output, 'plan': output/'plan.json',
        'run_driver': output/'observed_driver01',
        'plan_driver': root/'results/freeze_validation/extension_runner41_plan_driver01',
        'pending_contract': EXTERNAL/'extension_runner41_contract_extension_pending01.json'}




def entry_binding(review, built):
    # The source41 helper validates its own manifest; extension identity is bound separately.
    borrowed = dict(built, _reviewed_tools_sha256=SOURCE_CANONICAL)
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
    require(kind == 'extension', 'Extension41 cannot validate or create a new core matrix')
    runner.validate_plan(plan, path)
    selected = locations(kind)
    dimensions = CONDITIONS if kind == 'extension' else GROUPS
    expected_ids = [f'{cls}_extension_{cell}_seed004' if kind == 'extension'
        else f'{cls}_{cell}_seed004' for cls in CLASSES for cell in dimensions]
    require(plan.get('mode') == ('EXTENSION_PROBE' if kind == 'extension' else 'PROBE')
        and plan.get('frozen_root') == ROOT and plan.get('prefix') == PREFIXES[kind]
        and Path(plan['output']).resolve() == selected['output'].resolve()
        and plan.get('selected_classes') == list(CLASSES) and plan.get('selected_seeds') == [4]
        and type(plan['selected_seeds'][0]) is int
        and plan.get('selected_groups') == (['stage1_velocity', 'stage1_position'] if kind == 'extension' else list(GROUPS))
        and isinstance(plan.get('trials'), list)
        and [trial.get('id') for trial in plan['trials']] == expected_ids,
        'Exact fresh41 class2/seed004 core12 or extension16 matrix required')
    require(kind != 'extension' or plan.get('selected_extension_conditions') == list(CONDITIONS),
        'All eight registered extension conditions required')
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
        require(trial.get('extension_condition') == cell if kind == 'extension' else trial.get('group') == cell,
            'Matrix cell identity differs')
        expected_distance = (12. if car else 7.) if kind == 'extension' and cell == 'far_distance' else (9. if car else 5.)
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
    if kind == 'core':
        return core_module().checked_plan(kind, runner, supplied, supplied_path)
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


def load_safety_api(expected_sha, expected_python_sha256):
    require(generic.valid_sha(expected_sha) and generic.valid_sha(expected_python_sha256)
        and expected_sha == SAFETY_TOOLS_SHA and expected_python_sha256 == SAFETY_PY_SHA,
        'Extension actions require explicit independently reviewed safety tool and Python byte SHAs')
    path = EXTERNAL/(SAFETY_MODULE+'.py')
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
        'Actual bounded41 safety validator is unavailable')
    reviewed_bytes = path.read_bytes()
    require(hashlib.sha256(reviewed_bytes).hexdigest() == expected_python_sha256,
        'Actual41 safety Python bytes differ before any module execution')
    spec = importlib.util.spec_from_file_location(SAFETY_MODULE, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # Execute exactly the bytes checked above, rather than reopening a source
    # path or accepting a cached bytecode file after the first identity check.
    exec(compile(reviewed_bytes, str(path), 'exec'), module.__dict__)
    require(Path(module.__file__).resolve(strict=True) == path.resolve(strict=True)
        and sha(path) == expected_python_sha256
        and canonical(module.tool_manifest()) == expected_sha, 'Reviewed41 safety validator bytes changed')
    return module


def require_prerequisites(kind, args, review, built, runner):
    if kind == 'core':
        return None
    core = checked_plan('core', runner)
    core_result = require_completed_core(review, built, runner, core, locations('core')['plan'], all_pass=True)
    safety = load_safety_api(args.safety_tools_sha256, args.safety_python_sha256)
    result = safety.require_completed_safety(review, built, runner, core_plan=core,
        core_plan_path=locations('core')['plan'])
    require(canonical(safety.tool_manifest()) == args.safety_tools_sha256, 'Safety validator changed during admission')
    return {'core': core_result, 'safety': result, 'safety_tools_canonical_sha256': args.safety_tools_sha256,
        'safety_python_sha256': args.safety_python_sha256}


def verify_same_core(plan, runner):
    core = checked_plan('core', runner)
    require(all(plan.get(field) == core.get(field) for field in ('protocol', 'source_hashes', 'model_hashes',
        'config_hashes', 'magnetic_runtime_binding', 'magnetic_library_binding')),
        'Extension source/model/runtime/protocol differs from actual41 core')


def plan_matrix(kind, args, review, built, runner, modules, runtime, evidence):
    require(kind == 'extension', 'Extension41 exposes only extension plan/run')
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
            plan = runner.make_extension_plan(Path(ROOT), selected['output'], PREFIXES[kind],
                formal=False, seeds=[4], conditions=list(CONDITIONS), classes=list(CLASSES))
            verify_same_core(plan, runner)
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
                'duration_s': 75., 'flight_count': 12 if kind == 'core' else 16},
            'formal_seed_use_authorized': False, 'readiness_claimed': False,
            'automatic_retry': False, 'automatic_next_action': False}
        write_new(selected['pending_contract'], value)
        print(json.dumps({'pending_contract': str(selected['pending_contract']), 'sha256': sha(selected['pending_contract']),
            'status': PENDING, 'flights_started': 0}), flush=True)
    return code


def load_contract(kind, path, expected_sha, args, review, built, runner, modules):
    require(kind == 'extension', 'Extension41 cannot load a core execution contract')
    require(path is not None and generic.valid_sha(expected_sha), 'Explicit separately reviewed matrix contract SHA required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True)
        and re.fullmatch(r'extension_runner41_contract_'+kind+r'_[A-Za-z0-9_]+\.json', path.name),
        'Named external41 contract for the selected matrix required')
    value = read_small(path)
    require(sha(path) == expected_sha and type(value.get('schema_version')) is int and value['schema_version'] == 1
        and value.get('scope') == SCOPE and value.get('status') == FINAL and value.get('matrix_kind') == kind
        and value.get('frozen_root') == ROOT and value.get('source_review') == review['_review_binding']
        and value.get('entry_binding') == entry_binding(review, built)
        and value.get('tools_canonical_sha256') == canonical(tool_manifest())
        and value.get('build_evidence') == source.build_evidence(review),
        'Concrete final same-source/build/tools matrix contract required; draft cannot execute')
    require(value.get('experiment') == {'classes': list(CLASSES), 'seed': 4,
        'duration_s': 75., 'flight_count': 12 if kind == 'core' else 16}
        and type(value['experiment']['seed']) is int and type(value['experiment']['flight_count']) is int
        and all(value.get(name) is False for name in ('formal_seed_use_authorized', 'readiness_claimed',
            'automatic_retry', 'automatic_next_action')), 'Only the original complete development matrix is authorized')
    plan = checked_plan(kind, runner)
    if kind == 'extension': verify_same_core(plan, runner)
    initial = pending_identity(plan)
    prerequisites = require_prerequisites(kind, args, review, built, runner)
    require(value.get('plan_pending') == initial and value.get('prerequisites') == prerequisites,
        'Original plan or actual core/safety prerequisite binding changed')
    historical_entry = value['entry_binding']
    require('zero_attempt_recovery' not in value, 'Original41 extension cannot borrow historical core recovery')
    selected = locations(kind)
    terminal_path = selected['plan_driver']/'execution_terminal.json'
    require(stable.metadata_binding(terminal_path, json_only=True) == value.get('plan_terminal'), 'Original plan terminal changed')
    terminal = read_small(terminal_path)
    require(terminal.get('scope') == SCOPE and terminal.get('action') == 'plan' and terminal.get('matrix_kind') == kind
        and type(terminal.get('returncode')) is int and terminal['returncode'] == 0 and terminal.get('error') is None
        and terminal.get('initial_pending') == initial and terminal.get('flights_started') == 0
        and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == historical_entry
        and terminal.get('prerequisites') == prerequisites and terminal.get('final_errors') == []
        and terminal.get('cleanup', {}).get('residual_processes') == [], 'Original matrix plan did not close cleanly')
    observed = owner.validate_observer_root(terminal.get('observer_owner_terminal'),
        selected['plan_driver']/'observer_driver', ROOT)
    require(terminal.get('observer') == observed, 'Original extension plan observer differs from actual owner outcome')
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
    require(kind == 'extension', 'Extension41 exposes only extension plan/run')
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
        'zero_attempt_recovery': None,
        'planned_count': len(plan['trials']), 'attempt_count': len(attempts), 'terminal_count': len(completed),
        'attempts': attempts, 'slots': completed, 'actual_slot_statuses': actual_rows, 'slot_read_error': row_error,
        'status_counts': dict(Counter(row['status'] for row in (actual_rows or {}).values())), **cleanup,
        'formal_seed_use_authorized': False, 'readiness_claimed': False, 'automatic_retry': False,
        'automatic_next_action': False,
        'claim_boundary': 'Closed original development attempts preserve algorithm FAIL. They do not establish formal admission or full project acceptance.'})
    return code


def require_completed_core(review, built, runner, core_plan=None, core_plan_path=None, *, all_pass=True):
    require(all_pass is True, 'Follow-up41 always requires all12 original core PASS')
    return core_module().require_completed_core(review, built, runner, core_plan, core_plan_path,
                                                all_pass=True)




def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', choices=('describe', 'plan-extension', 'run-extension'))
    result.add_argument('--review', type=Path); result.add_argument('--review-sha256')
    result.add_argument('--reviewed-tools-sha256'); result.add_argument('--frozen-root')
    result.add_argument('--contract', type=Path); result.add_argument('--contract-sha256')
    result.add_argument('--safety-tools-sha256')
    result.add_argument('--safety-python-sha256')
    return result


def reviewed_source(args):
    require(args.action != 'describe' and args.frozen_root == ROOT
        and generic.valid_sha(args.review_sha256) and generic.valid_sha(args.reviewed_tools_sha256)
        and canonical(tool_manifest()) == args.reviewed_tools_sha256,
        'Explicit41 source review/root/independently reviewed matrix tools required')
    if args.action.startswith('run-'):
        require(args.contract is not None and generic.valid_sha(args.contract_sha256),
            'Run requires a separate actual final matrix contract SHA')
    if args.action.endswith('-extension'):
        require(generic.valid_sha(args.safety_tools_sha256) and generic.valid_sha(args.safety_python_sha256),
            'Extension requires reviewed actual41 safety validator tool and Python byte SHAs')
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
        print(json.dumps({'manifest': manifest, 'tools_canonical_sha256': canonical(manifest),
            'actual_action_executed': False}, indent=2))
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
