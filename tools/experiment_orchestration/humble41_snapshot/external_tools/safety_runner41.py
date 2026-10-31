"""Prospective four original safety attempts for actual frozen41 canonical core.

Describe/import are inert. Register requires actual healthy closed core12 and
same-source build and all12 original core PASS. Run requires the exact separately reviewed registry SHA.
No formal admission, retry, automatic extension, or historical result rewrite.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import reviewed_freeze_build as generic
import reviewed_timing_diagnostic as stable
import source_runtime41 as source
import local_runtime_observer41 as owner

EXTERNAL = Path(__file__).resolve().parent
ROOT = Path('/root/uav_tracking_fullplan_v4_humble41')
AUDIT = ROOT/'results/reliability_v4_humble41_safety_seed004_audit'
CORE = ROOT/'results/reliability_v4_humble41_probe01_seed004_matrix/plan.json'
CARD = EXTERNAL/'humble41_safety_execution01.md'
TAIL = EXTERNAL/'evaluate_humble41_safety_tail01.py'
SCOPE = 'HUMBLE41_SAFETY4_ORIGINAL_DEVELOPMENT_ATTEMPTS_NOT_FORMAL_GATE'
OWN = ('safety_runner41.py', 'safety_runner41.sh', 'test_safety_runner41.py',
       'humble41_safety_execution01.md', 'evaluate_humble41_safety_tail01.py')
SOURCE_SHA = '044ab32510e89c9da462040c5ff2391840b92ed6efd6dbda18fd218e6cd55686'
MATRIX_SHA = '8c9241e5f9ba7a54988b27d0f016e40d52ece37b8c9c85de410cb24463361cf3'
MATRIX_PY_SHA = '1e748d97f4c5687d53447af3acbe4506072279c063e6e77b31b262fe76df3ced'
OWNER_TOOLS_SHA = 'e558bf367038a2bb3530d7e5a8ea3e3fae7eb84ac19d02acedecc7c5c2be3ea3'
require, sha, canonical = generic.require, generic.sha, generic.canonical
read_small, write_new = generic.read_small, generic.write_new
EXECUTIONS = {'flight', 'source_clock', 'native_startup', 'specialized', 'terminal_speed'}
EVIDENCE = {'run_config': 'run_config.json', 'source_snapshot': 'configuration/source_sha256.json',
    'runtime_parameters': 'configuration/runtime_parameters.yaml', 'bag_integrity': 'bag_integrity.json',
    'recording_closure': 'recording_closure.json', 'process_exit_codes': 'process_exit_codes.json',
    'source_clock': 'px4_source_clock_report.json', 'native_startup': 'native_startup_report.json',
    'terminal_speed': 'terminal_hover_speed_evaluation.json',
    'rendering': 'configuration/gazebo_rendering_libraries.json', 'magnetic': 'configuration/magnetic_environment.json'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def binding(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
            'Missing/unsafe named metadata/source binding')
    return {'path': str(path), 'sha256': sha(path)}


def bound_json(item):
    require(isinstance(item, dict) and set(item) == {'path', 'sha256'}, 'Exact named JSON binding required')
    path = Path(item['path'])
    require(path.is_absolute() and binding(path) == item, 'Bound original JSON changed')
    return path, read_small(path)


def matrix_module():
    path = EXTERNAL/'matrix_runner41.py'
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
            'Actual reviewed bounded matrix Python source is required')
    source = path.read_bytes()
    require(hashlib.sha256(source).hexdigest() == MATRIX_PY_SHA,
            'Actual reviewed matrix Python bytes must match before execution')
    name = '_humble41_safety_matrix_dependency'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # Execute exactly the bytes just checked, never a second pathname read.
    exec(compile(source, str(path), 'exec'), module.__dict__)
    require(Path(module.__file__).resolve() == path.resolve() and sha(path) == MATRIX_PY_SHA,
            'Matrix Python path/bytes changed during import')
    return module


def tool_manifest():
    require(Path(source.__file__).resolve(strict=True) == (EXTERNAL/'source_runtime41.py').resolve(strict=True)
            and canonical(source.tool_manifest()) == SOURCE_SHA, 'Pinned source41 common tools changed')
    require(Path(owner.__file__).resolve(strict=True) == (EXTERNAL/'local_runtime_observer41.py').resolve(strict=True)
            and canonical(owner.tool_manifest()) == OWNER_TOOLS_SHA, 'Pinned observer41 native owner changed')
    matrix = matrix_module()
    matrix_manifest = matrix.tool_manifest()
    require(canonical(matrix_manifest) == MATRIX_SHA, 'Pinned actual41 core-only tools changed')
    return {'schema_version': 1, 'scope': SCOPE, 'files': {name: binding(EXTERNAL/name)['sha256'] for name in OWN},
        'source41_common': source.tool_manifest(), 'source41_common_canonical_sha256': SOURCE_SHA,
        'matrix_tools': matrix_manifest, 'matrix_tools_canonical_sha256': MATRIX_SHA,
        'matrix_python_sha256': MATRIX_PY_SHA,
        'observer_owner_tools': owner.tool_manifest(), 'observer_owner_canonical_sha256': OWNER_TOOLS_SHA,
        'observer_original_post_wait_terminal_required': True,
        'observer_max_sample_age_wall_s': 10., 'observer_archive_wall_budget_s': 1800.,
        'frozen_root': ROOT.as_posix(), 'core_plan': CORE.as_posix(),
        'actions': ['register', 'run'], 'requires_all12_original_core_pass': True, 'fixed_seed': 4, 'formal_seed_use_authorized': False,
        'all_flight_argv_registered_before_first_flight': True, 'direct_flight_single_outer_machine_lock': True,
        'normal_run_plan_used_for_safety': False, 'automatic_retry': False, 'automatic_next_action': False,
        'original_tail_unchanged': True, 'original_5_executions_and_12_evidence': True,
        'flight_wall_resource_budget_s': 1000., 'archive_wall_resource_budget_s': 1800.,
        'owned_child_cleanup_allowance_s': 280., 'outer_cleanup_margin_s': 120.,
        'flight_outer_timeout_s': 3200., 'evaluation_outer_timeout_s': 1800.}


def common_built(built):
    return {**built, '_reviewed_tools_sha256': SOURCE_SHA}


def entry_binding(review, built):
    expected = built.get('_safety_tools_sha256')
    require(generic.valid_sha(expected) and canonical(tool_manifest()) == expected, 'Reviewed safety tools changed')
    return {**source.entry_binding(review, common_built(built)), 'safety_tools_canonical_sha256': expected}


def load_frozen_module(relative, name):
    path = ROOT/relative
    require(path.is_file() and not path.is_symlink(), 'Missing actual frozen module')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def frozen_guard():
    return load_frozen_module('tools/reliability_v4_guard.py', '_humble41_safety_guard')


def frozen_bindings(plan):
    builder = load_frozen_module('scripts/build_reliability_v4_probe_gate.py', '_humble41_safety_gate_builder')
    require(Path(builder.v4.__file__).resolve(strict=True) == (ROOT/'scripts/run_reliability_v4.py').resolve(strict=True),
            'Gate builder imported a runner outside actual frozen41')
    return builder.bindings(plan)


def policy_flags(runner, protocol, cls):
    """Derive registered geometry/measurement/pacing from the frozen runner."""
    require(cls in ('person', 'car'), 'Unknown safety class')
    runner.validate_protocol(protocol)
    resource = protocol['resources'][cls]
    geometry = runner.correlated_two_face_setting(resource, cls)
    recovery = runner.car_surface_recovery_setting(resource, cls)['enabled']
    source.validate_class_policy(protocol, runner)
    exclusive = runner.exclusive_navigation_setting(resource, cls)
    pacing = runner.simulation_pacing_summary(protocol)
    require(canonical(pacing) == canonical(source.EXPECTED_PACING_V2), 'Safety requires the complete41 V2 contract')
    flags = []
    if geometry:
        flags.append(runner.CORRELATED_BOUND_FLAG)
    if recovery:
        flags.append(runner.CAR_SURFACE_RECOVERY_FLAG)
    if exclusive:
        flags.append(runner.EXCLUSIVE_NAVIGATION_FLAG)
    field, flag = runner.PX4_ADAPTER_PUBLISH_RATE_FIELD, runner.PX4_ADAPTER_PUBLISH_RATE_FLAG
    require(field in pacing, 'Safety V2 adapter cadence declaration missing')
    flags.extend([flag, str(pacing[field])])
    return flags, geometry, recovery, pacing[field], exclusive


def safety_definitions(runner, plan):
    runner.validate_plan(plan)
    require(plan.get('mode') == 'PROBE' and plan.get('frozen_root') == str(ROOT)
            and plan.get('selected_classes') == ['person', 'car'] and plan.get('selected_seeds') == [4]
            and plan.get('selected_groups') == list(runner.GROUPS) and len(plan.get('trials', [])) == 12,
            'Only the actual complete canonical41 core12 can define safety')
    protocol, trials = plan['protocol'], []
    for cls in ('person', 'car'):
        resource = protocol['resources'][cls]
        flags, geometry, recovery, rate, exclusive = policy_flags(runner, protocol, cls)
        for case in ('auto_unique_multi', 'locked_ambiguity'):
            automatic = case == 'auto_unique_multi'
            identifier = f'{cls}_{case}_seed004'
            name = 'reliability_v4_humble41_safety_' + identifier
            settings = {'name': name, 'target_class': cls, 'stage': 2, 'seed': 4,
                'condition': 'clean', 'estimator_method': 'adaptive_kf', 'command_mode': 'velocity',
                'gimbal_mode': 'midpoint', 'real_time_factor': protocol['real_time_factor'],
                'max_inference_rate_hz': 10., 'monitor_tick_s': .02, 'control_reference': 'ground_footprint',
                'motion_profile_kind': 'standard', 'model_path': str(ROOT/resource['model']),
                'inference_image_size': resource['inference_image_size'], 'inference_threads': resource['inference_threads'],
                'desired_distance_m': resource['desired_distance_m'], 'takeoff_height_m': 3., 'takeoff_mode': 'px4_native',
                'wall_timeout': protocol['flight_wall_timeout_s'], 'render_backend': 'egl',
                'gazebo_render_driver': protocol['gazebo_render_driver'], 'magnetic_environment': 'gazebo_enu',
                'magnetic_runtime_manifest': str(ROOT/'config/px4_magnetic_runtime.json'),
                'magnetic_library_registration': str(ROOT/protocol['magnetic_library_registration']),
                'ros_gz_runtime_registration': str(ROOT/'config/ros_gz_runtime_humble22.json'),
                'propagate_vehicle_uncertainty': True, 'px4_time_mode': 'source_sim',
                'target_mode': 'auto_unique' if automatic else 'locked_target',
                'association_mode': 'legacy' if automatic else 'hybrid_3d',
                'scenario_kind': 'parallel' if automatic else 'ambiguity',
                'initial_select': 'none' if automatic else 'middle', 'initial_min_candidates': 2 if automatic else 3,
                'duration': 35. if automatic else 50.}
            if automatic:
                settings['no_follow_duration_s'] = 35.
            command = ['bash', str(ROOT/'scripts/run_research_session.sh'), str(ROOT/'scripts/run_stage1_trial.py')]
            for key, value in settings.items():
                command.append('--class' if key == 'target_class' else '--'+key.replace('_', '-'))
                if value is not True:
                    command.append(str(value))
            command.extend(flags)
            settings.update(correlated_two_face_bound=geometry, car_surface_recovery=recovery,
                            px4_adapter_publish_rate_hz=rate, exclusive_navigation_reference=exclusive)
            trials.append({'id': identifier, 'name': name, 'directory': str(ROOT/'results'/name),
                'target_class': cls, 'case': case, 'seed': 4, 'settings': settings,
                'flight_command': command, 'flight_argv': list(command),
                'world_source': f'ros2_ws/src/uav_tracking_bringup/worlds/stage2_flight_{cls}.sdf'})
    return trials


def verify_tail(guard=None):
    guard = guard or frozen_guard()
    registry = {'execution_card': binding(CARD), 'tail_script': binding(TAIL)}
    guard.verified_safety_card(registry, ROOT)
    return registry


def safety_runtime(runner, plan, trial, review, checks):
    import yaml
    guard, directory = frozen_guard(), Path(trial['directory'])
    config = read_small(directory/'run_config.json')
    expected = {**trial['settings'], 'occlusions': False, 'reselect_after_loss': False, 'no_bag': False,
        'vehicle_control_point_offset_flu_m': [0., 0., .24]}
    require(all(key in config and config[key] == value and (type(value) is not bool or type(config[key]) is bool)
                for key, value in expected.items()), 'Actual safety configuration differs from its prospective argv')
    snapshot = read_small(directory/'configuration/source_sha256.json')
    expected_sources = {key: value for key, value in plan['source_hashes'].items()
        if key.startswith(('scripts/', 'uav_tracking/', 'ros2_ws/src/')) and Path(key).suffix in {'.py', '.sh', '.msg'}}
    model = plan['protocol']['resources'][trial['target_class']]['model']
    expected_sources[model] = plan['source_hashes'][model]
    require(snapshot == expected_sources, 'Saved safety source/model snapshot differs')
    path = directory/'configuration/runtime_parameters.yaml'
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1024*1024, 'Unsafe safety runtime YAML')
    parameters = yaml.safe_load(path.read_text(encoding='utf-8'))
    resource, cls, argv = plan['protocol']['resources'][trial['target_class']], trial['target_class'], trial['flight_command']
    guard.geometry_bound_evidence(resource, cls, config, parameters, argv)
    guard.car_surface_recovery_evidence(SimpleNamespace(v4=runner), resource, cls, config, parameters, argv)
    guard.exclusive_navigation_evidence(SimpleNamespace(v4=runner), resource, cls, config, parameters, argv)
    guard.simulation_pacing_evidence(SimpleNamespace(v4=runner), plan['protocol'], config, parameters, argv)
    supported_birth = source.validate_supported_birth_runtime(cls, config, parameters)
    expected_parameters = {
        'uav_tracking_detection': {'navigation_enabled': True, 'depth_max_age_s': .02, 'model_path': config['model_path'],
            'navigation_exclusive_enabled': config['exclusive_navigation_reference'],
            'inference_image_size': config['inference_image_size'], 'inference_threads': config['inference_threads'],
            'max_inference_rate_hz': 10.},
        'uav_tracking_state_estimator': {'navigation_enabled': True, 'max_observation_age_s': .6,
            'navigation_exclusive_enabled': config['exclusive_navigation_reference'],
            'max_prediction_duration_s': .75, 'mahalanobis_gate': 9.21, 'target_mode': config['target_mode'],
            'association_mode': config['association_mode'], 'propagate_vehicle_uncertainty': True, 'estimator_method': 'adaptive_kf'},
        'uav_tracking_controller': {'state_topic': '/tracking/navigation_state', 'command_mode': 'velocity',
            'desired_distance_m': config['desired_distance_m'], 'desired_height_m': 2., 'prediction_timeout_s': .75},
        'uav_tracking_px4_adapter': {'use_sim_time': True, 'odometry_timestamp_mode': 'source_sim',
            'odometry_source_max_age_s': .5, 'odometry_source_max_future_s': .05},
        'uav_tracking_flight_supervisor': {'takeoff_mode': 'px4_native', 'takeoff_height_m': 3.,
            'status_timestamp_mode': 'source_sim', 'status_source_max_age_s': 1., 'status_source_max_future_s': .05,
            'status_timeout_s': 10., 'requested_simulation_real_time_factor': plan['protocol']['real_time_factor']}}
    require(all(parameters.get(node, {}).get('ros__parameters', {}).get(key) == value
                and (type(value) is not bool or type(parameters[node]['ros__parameters'][key]) is bool)
                for node, values in expected_parameters.items() for key, value in values.items()), 'Actual safety YAML gates differ')
    checks.native_handoff_runtime(directory)
    require(not runner.gazebo_rendering_evidence(directory, 'llvmpipe')['errors']
            and not runner.magnetic_environment_evidence(plan, trial)['errors'], 'Actual safety rendering/magnetic contract differs')
    return {'run_config': binding(directory/'run_config.json'), 'runtime_parameters': binding(path),
        'supported_birth_confirmation': supported_birth,
        'bridge': checks.bridge_evidence(directory, review), 'processes': checks.process_evidence(directory, stage=2)}


TAIL_CHECKS = {'input_decode_complete', 'odom_tail_spans_five_seconds',
    'odom_tail_covers_original_end', 'all_observed_odom_speeds_le_0_30_mps',
    'gt_tail_spans_five_seconds', 'gt_tail_covers_original_end',
    'last_gt_equals_final_clock', 'all_gt_secant_speeds_le_0_30_mps'}


AUTO_CHECKS = {'clock_recorded', 'input_decodes_without_errors', 'fresh_multi_box_evidence_is_persistent',
    'track_snapshot_messages_valid', 'no_explicit_selection', 'never_automatically_tracks_a_candidate',
    'never_issues_follow_control', 'all_motion_commands_invalid', 'armed_and_offboard_observed',
    'all_final_streams_span_five_seconds', 'all_final_streams_cover_tail', 'final_state_is_ambiguous',
    'final_controller_is_hover', 'actual_final_vehicle_speed_below_threshold'}


LOCKED_CHECKS = {'clock_recorded', 'input_decodes_without_errors', 'armed_and_offboard_observed',
    'initial_explicit_box_confirmed_fresh', 'initial_box_matches_selected_track_snapshot',
    'no_tracking_before_initial_selection', 'multiple_same_class_fresh_tracks_observed',
    'all_tracks_snapshots_present_and_valid', 'task_uuid_changes_require_explicit_selection',
    'long_loss_cannot_reactivate_without_explicit_selection', 'long_loss_cannot_control_before_explicit_selection',
    'active_states_remain_fresh', 'selected_geometric_ambiguity_observed_if_required',
    'observed_ambiguities_suspend_control', 'required_short_and_long_occlusions_present',
    'recorded_occlusions_pass', 'detection_diagnostics_valid', 'terminal_hover_follows_selected_ambiguity',
    'final_sustained_hover'}


def report_names(trial):
    return {'source_clock': 'px4_source_clock_report.json', 'native_startup': 'native_startup_report.json',
        'specialized': 'auto_unique_evaluation_v2.json' if trial['case'] == 'auto_unique_multi' else 'stage2_evaluation.json',
        'terminal_speed': 'terminal_hover_speed_evaluation.json'}


def safety_evaluations(trial):
    directory, names = Path(trial['directory']), report_names(trial)
    prefix = ['bash', str(ROOT / 'scripts/run_research_session.sh')]
    specialty = ([str(ROOT / 'scripts/run_stage23_matrix.py'), '--evaluate-auto-unique', str(directory / 'rosbag'),
        '--target-class', trial['target_class']] if trial['case'] == 'auto_unique_multi' else
        [str(ROOT / 'scripts/evaluate_stage2_flight.py'), str(directory / 'rosbag'), '--target-class', trial['target_class'],
         '--telemetry-jsonl', str(directory / 'telemetry.jsonl'), '--monitor-summary', str(directory / 'summary.json'),
         '--no-require-occlusions', '--require-ambiguity', '--terminal-expectation', 'hover'])
    return {'source_clock': prefix + [str(ROOT / 'scripts/evaluate_px4_source_clock.py'), str(directory), '--output', str(directory / names['source_clock'])],
        'native_startup': prefix + [str(ROOT / 'scripts/evaluate_native_startup.py'), str(directory), '--output', str(directory / names['native_startup'])],
        'specialized': prefix + specialty + ['--output', str(directory / names['specialized'])],
        'terminal_speed': prefix + [str(TAIL), str(directory), str(CARD)]}


def slot_facts(row, registry):
    trial, names = row['trial'], report_names(row['trial'])
    directory = Path(trial['directory'])
    files = {'run_config': 'run_config.json', 'source_snapshot': 'configuration/source_sha256.json',
        'runtime_parameters': 'configuration/runtime_parameters.yaml', 'bag_integrity': 'bag_integrity.json',
        'recording_closure': 'recording_closure.json', 'process_exit_codes': 'process_exit_codes.json', **names,
        'rendering': 'configuration/gazebo_rendering_libraries.json', 'magnetic': 'configuration/magnetic_environment.json'}
    evidence, missing, executions = {}, [], {}
    for kind, relative in files.items():
        path = directory / relative
        if path.is_file() and not path.is_symlink():
            evidence[kind] = binding(path)
        else:
            missing.append(kind)
    for kind, receipt in row['executions'].items():
        actual = receipt['execution']
        value = {'argv': actual['command'], 'started_utc': actual.get('started_utc'), 'finished_utc': actual.get('finished_utc'),
            'returncode': actual['returncode'], 'error': actual.get('error'), 'outer_cleanup_actions': actual['outer_cleanup_actions'],
            'outer_receipt': {'path': receipt['path'], 'sha256': receipt['sha256']}}
        path = Path(actual['log'])
        if path.is_file() and not path.is_symlink():
            value['log'] = binding(path)
        else:
            missing.append(kind + '_execution_log')
        if kind == 'terminal_speed':
            value['code_script'] = registry['tail_script']
        executions[kind] = value
    passed = (row['status'] == 'PASS' and row['infrastructure_stop'] is False and not missing
        and set(executions) == {'flight', 'source_clock', 'native_startup', 'specialized', 'terminal_speed'}
        and all(type(value['returncode']) is int and value['returncode'] == 0 and value['error'] is None
                and value['outer_cleanup_actions'] == [] and value['started_utc'] and value['finished_utc']
                for value in executions.values()))
    return {**{key: trial[key] for key in ('id', 'target_class', 'case', 'seed')},
        'result': 'PASS' if passed else 'FAIL', 'original_status': row['status'], 'trial_directory': str(directory),
        'executions': executions, 'evidence': evidence, 'missing_evidence': missing,
        'infrastructure_stop': row['infrastructure_stop'], 'original_error': row.get('error')}


def original_execution(receipt, command, *, algorithm_exit=False):
    _, actual = bound_json({key: receipt[key] for key in ('path', 'sha256')})
    require(actual == receipt['execution'] and actual.get('command') == command
        and type(actual.get('returncode')) is int and actual['returncode'] in ({0, 2} if algorithm_exit else {0})
        and actual.get('error') is None and actual.get('outer_cleanup_actions') == [],
        'Original owned safety command/observer did not close cleanly')
    require(datetime.fromisoformat(actual['started_utc']) <= datetime.fromisoformat(actual['finished_utc']), 'Execution UTC order differs')
    binding(actual['log'])
    return actual


def execute(command, name, observer, timeout):
    require(name.replace('_', '').isalnum(), 'Unsafe execution receipt name')
    actual = stable.execute_owned(command, AUDIT/(name+'.log'), observer, timeout, ROOT)
    path = AUDIT/(name+'.outer_execution.json')
    write_new(path, actual)
    return {**binding(path), 'execution': actual}


def safety_report_audit(trial, runner, plan, executions):
    directory = Path(trial['directory'])
    reports = {kind: read_small(directory/name) for kind, name in report_names(trial).items()}
    for kind, script in [('source_clock', 'evaluate_px4_source_clock.py'), ('native_startup', 'evaluate_native_startup.py')]:
        spec = {'kind': kind, 'script': 'scripts/'+script, 'report': str(directory/report_names(trial)[kind]),
                'evaluation_root': str(ROOT)}
        require(runner.read_evaluation(spec, executions[kind]['execution'], plan)['result'] == 'PASS',
                'Independent safety source/native report did not PASS')
    specialty = reports['specialized']
    schema, source = ((2, 'OFFLINE_AUTO_UNIQUE_MULTIPLE_CANDIDATE_SAFETY') if trial['case'] == 'auto_unique_multi'
                     else (1, 'OFFLINE_STAGE2_SAFETY_EVALUATION'))
    require(specialty.get('schema_version') == schema and specialty.get('source') == source
        and specialty.get('result') in ('PASS', 'FAIL') and bool(specialty.get('checks'))
        and set(specialty['checks']) == (AUTO_CHECKS if trial['case'] == 'auto_unique_multi' else LOCKED_CHECKS)
        and all(type(value) is bool for value in specialty['checks'].values())
        and Path(specialty.get('inputs', {}).get('bag', '')).resolve() == (directory/'rosbag').resolve()
        and not specialty['inputs'].get('read_errors') and not specialty['inputs'].get('unavailable_types'),
        'Specialized safety report is incomplete/malformed/foreign')
    tail = reports['terminal_speed']
    require(tail.get('schema_version') == 1 and tail.get('result') in ('PASS', 'FAIL')
        and Path(tail.get('trial', '')).resolve() == directory.resolve()
        and set(tail.get('checks', {})) == TAIL_CHECKS and all(type(value) is bool for value in tail['checks'].values())
        and abs(tail.get('interval', {}).get('end_s', 0.)-tail.get('interval', {}).get('start_s', 0.)-5.2) < 1e-6
        and tail.get('bag_reader', {}).get('clock_recorded') is True
        and not tail['bag_reader'].get('read_errors') and not tail['bag_reader'].get('unavailable_types'),
        'Original full5.2s dual-speed audit is incomplete/malformed/foreign')
    closure = read_small(directory/'recording_closure.json')
    final_clock = closure['observations'][-1]['last_clock_ns']/1e9
    require(abs(tail['interval']['end_s']-final_clock) < 1e-9, 'Tail does not reach the original final recorded Clock')
    for report in (specialty, tail):
        require(report['result'] == ('PASS' if all(report['checks'].values()) else 'FAIL'), 'Safety verdict contradicts original checks')
    return {'status': 'PASS' if specialty['result'] == tail['result'] == 'PASS' else 'FAIL',
        'source_clock': 'PASS', 'native_startup': 'PASS', 'specialized': specialty['result'], 'terminal_speed': tail['result'],
        'reports': {kind: binding(directory/name) for kind, name in report_names(trial).items()}}


def actual_core(review, built, runner, core_plan=None, core_plan_path=None):
    path = Path(core_plan_path or CORE)
    require(path == CORE, 'Only the actual canonical41 core path may define safety')
    plan = read_small(path)
    require(core_plan is None or core_plan == plan, 'Supplied core plan differs from actual canonical file')
    complete = matrix_module().require_completed_core(review, built, runner, plan, path, all_pass=True)
    runner.verify_sources(plan)
    return path, plan, complete


def register_safety(review, built, runner):
    core_path, plan, complete = actual_core(review, built, runner)
    trials = safety_definitions(runner, plan)
    tail = verify_tail()
    require(not AUDIT.exists() and not AUDIT.is_symlink()
        and all(not Path(trial['directory']).exists() and not Path(trial['directory']).is_symlink() for trial in trials)
        and not runner.simulation_processes(), 'Fresh safety audit/four trial paths and idle runtime required; no retry')
    before = entry_binding(review, built)
    AUDIT.mkdir(exist_ok=False)
    registry = {'schema_version': 1, 'kind': 'RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY',
        'scope': SCOPE, 'created_utc': utc(), 'trials': trials,
        'source_core_plan': {**binding(core_path), 'plan_sha256': plan['plan_sha256']},
        'core_completed_prerequisite': complete, 'source_binding': before['source'],
        'freeze_source_sha256': before['source']['freeze_source_sha256'],
        'flight_source_hashes': runner.flight_source_hashes(plan['source_hashes']),
        'driver': binding(__file__), **tail, 'safety_tools_sha256': built['_safety_tools_sha256'],
        'entry_binding': before, 'formal_seeds_consumed': False, 'automatic_retry': False,
        'policy': 'Four original attempts once; complete algorithm FAIL remains. Source/native/infra/observer faults stop; no automatic extension.'}
    write_new(AUDIT/'registry.json', registry)
    require(entry_binding(review, built) == before, 'Frozen source/tools changed during prospective registration')
    print(json.dumps({'registry': binding(AUDIT/'registry.json'), 'trials': [trial['id'] for trial in trials],
        'flight_actions_executed': 0, 'requires_explicit_reviewed_registry_sha_to_run': True}))
    return 0


def checked_registry(review, built, runner, expected_sha=None, core_plan=None, core_plan_path=None):
    path, plan, complete = actual_core(review, built, runner, core_plan, core_plan_path)
    registry_path = AUDIT/'registry.json'
    require(expected_sha is None or generic.valid_sha(expected_sha) and sha(registry_path) == expected_sha,
            'Explicit reviewed registry SHA changed')
    registry = read_small(registry_path)
    before = entry_binding(review, built)
    require(registry.get('schema_version') == 1
        and registry.get('kind') == 'RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY'
        and registry.get('scope') == SCOPE and registry.get('trials') == safety_definitions(runner, plan)
        and registry.get('source_core_plan') == {**binding(path), 'plan_sha256': plan['plan_sha256']}
        and registry.get('entry_binding') == before and registry.get('source_binding') == before['source']
        and registry.get('freeze_source_sha256') == before['source']['freeze_source_sha256']
        and registry.get('flight_source_hashes') == runner.flight_source_hashes(plan['source_hashes'])
        and registry.get('safety_tools_sha256') == built['_safety_tools_sha256']
        and registry.get('driver') == binding(__file__) and registry.get('formal_seeds_consumed') is False,
        'Prospective four-safety registry differs from the actual same-source core/tool configuration')
    require(registry['core_completed_prerequisite'] == complete, 'Original completed core prerequisite changed')
    require({key: registry[key] for key in ('execution_card', 'tail_script')} == verify_tail(), 'Safety card/tail changed')
    return plan, registry, before


def run_safety(args, review, built, runner, modules):
    require(generic.valid_sha(args.registry_sha256), 'Run requires the exact separately reviewed registry SHA')
    plan, registry, before = checked_registry(review, built, runner, args.registry_sha256)
    trials = registry['trials']
    reserved = [AUDIT/'execution_terminal.json', AUDIT/'slots_facts.json', AUDIT/'observer_driver']
    reserved.extend(AUDIT/(trial['id']+suffix) for trial in trials for suffix in ('.started.json', '.json'))
    require(not any(path.exists() or path.is_symlink() for path in reserved)
        and all(not Path(trial['directory']).exists() for trial in trials)
        and not runner.simulation_processes(), 'Existing safety attempt or runtime; refuse retry')
    # Direct run_stage1_trial does not acquire the runner's machine lock itself.
    with runner.run_lock(AUDIT):
        return run_safety_locked(review, built, runner, modules, plan, registry, before)


def finish_action(review, built, runner, observer):
    """Retain the original owner-observed native/archive result, including failure."""
    errors, after, residual, observed = [], None, None, None
    actual_owner = observer._finished
    try:
        after = source.entry_binding(review, common_built(built))
    except BaseException as error:
        errors.append('binding:'+type(error).__name__+':'+str(error))
    try:
        residual = runner.simulation_processes()
        require(residual == [], 'Residual runtime processes remain')
    except BaseException as error:
        errors.append('residual:'+type(error).__name__+':'+str(error))
    try:
        observed = owner.validate_observer_root(actual_owner, AUDIT/'observer_driver', ROOT)
    except BaseException as error:
        errors.append('observer:'+type(error).__name__+':'+str(error))
    return {'entry_binding_after': after, 'cleanup': {'residual_processes': residual},
        'observer_owner_terminal': actual_owner, 'observer': observed, 'final_errors': errors}


def run_safety_locked(review, built, runner, modules, plan, registry, before):
    checks = modules['humble33_diagnostic_checks01']
    observer = owner.make_observer(AUDIT/'observer_driver', ROOT, archive_wall_budget_s=1800.)
    completed, stop = [], None
    registry_binding, core_binding = binding(AUDIT/'registry.json'), binding(CORE)
    def immutable():
        require(entry_binding(review, built) == before and binding(AUDIT/'registry.json') == registry_binding
            and binding(CORE) == core_binding, 'Frozen source/registry/core changed during original safety attempts')
        runner.verify_sources(plan)
        require(not runner.simulation_processes(), 'Residual runtime before/after original safety attempt')
    try:
        with observer:
            for number, trial in enumerate(registry['trials'], 1):
                immutable()
                fresh = observer.check()
                require(not Path(trial['directory']).exists(), 'Safety trial already exists; no retry')
                write_new(AUDIT/(trial['id']+'.started.json'), {'created_utc': utc(), 'trial': trial,
                    'registry': registry_binding, 'source_binding': before['source'], 'observer_freshness': fresh})
                row = {'id': trial['id'], 'trial': trial, 'status': 'INFRASTRUCTURE_ERROR',
                    'infrastructure_stop': True, 'executions': {}, 'error': None}
                try:
                    receipt = execute(trial['flight_command'], trial['id']+'_flight', observer, 3200.)
                    row['executions']['flight'] = receipt
                    original_execution(receipt, trial['flight_command'])
                    require(runner.infrastructure_evidence(Path(trial['directory']), [])['stop'] is False
                        and not runner.simulation_processes(), 'Safety flight/recording failed to close cleanly')
                    row['runtime'] = safety_runtime(runner, plan, trial, review, checks)
                    for kind, command in safety_evaluations(trial).items():
                        output = Path(trial['directory'])/report_names(trial)[kind]
                        require(not output.exists(), 'Existing safety evaluation; no overwrite')
                        receipt = execute(command, trial['id']+'_'+kind, observer, 1800.)
                        row['executions'][kind] = receipt
                        original_execution(receipt, command, algorithm_exit=kind in ('specialized', 'terminal_speed'))
                    row['audit'] = safety_report_audit(trial, runner, plan, row['executions'])
                    attempts = [{'report': str(Path(trial['directory'])/report_names(trial)[kind]),
                        'log': receipt['execution']['log'], 'returncode': receipt['execution']['returncode']}
                        for kind, receipt in row['executions'].items() if kind != 'flight']
                    row['infrastructure'] = runner.infrastructure_evidence(Path(trial['directory']), attempts)
                    require(row['infrastructure']['stop'] is False, 'Safety evaluator infrastructure incomplete')
                    row['status'], row['infrastructure_stop'] = row['audit']['status'], False
                    observer.check()
                except BaseException as error:
                    row['error'] = type(error).__name__+':'+str(error)
                    row['infrastructure_stop'] = True
                    raise
                finally:
                    try:
                        immutable()
                    except BaseException as error:
                        row['cleanup_error'] = type(error).__name__+':'+str(error)
                        row['infrastructure_stop'] = True
                    row['source_binding_after'] = before['source'] if not row.get('cleanup_error') else None
                    row['finished_utc'] = utc()
                    row['execution_facts'] = slot_facts(row, registry)
                    path = AUDIT/(trial['id']+'.json')
                    write_new(path, row)
                    completed.append({'id': trial['id'], 'status': row['status'],
                        'infrastructure_stop': row['infrastructure_stop'], 'terminal': binding(path)})
                    print(json.dumps({'event': 'COMPLETE_ORIGINAL_SAFETY_SLOT', 'number': number, 'total': 4, **completed[-1]}), flush=True)
                require(not row['infrastructure_stop'], 'Safety infrastructure fault; no automatic next attempt')
    except BaseException as error:
        stop = type(error).__name__+':'+str(error)
    finally:
        cleanup = finish_action(review, built, runner, observer)
        try:
            immutable()
        except BaseException as error:
            cleanup['final_errors'].append('immutable:'+type(error).__name__+':'+str(error))
        code = 0 if len(completed) == 4 and not stop and not cleanup['final_errors'] and all(not row['infrastructure_stop'] for row in completed) else 2
        terminal = {'schema_version': 1, 'scope': SCOPE, 'finished_utc': utc(), 'returncode': code,
            'status': 'SAFETY4_ORIGINAL_ATTEMPTS_COMPLETE' if code == 0 else 'STOPPED_NO_AUTOMATIC_RETRY',
            'planned_count': 4, 'attempted_count': len(completed), 'pending_count': 4-len(completed),
            'slots': completed, 'stop_reason': stop, 'registry': registry_binding,
            'entry_binding_before': before, **cleanup, 'observer_owner_terminal': observer._finished,
            'formal_seeds_consumed': False, 'automatic_followon_actions': False}
        write_new(AUDIT/'execution_terminal.json', terminal)
        facts = [{**bound_json(row['terminal'])[1]['execution_facts'], 'original_terminal': row['terminal']} for row in completed]
        data = {'schema_version': 1, 'kind': 'RELIABILITY_V4_SAFETY_EXECUTION_FACTS',
            'evidence_scope': 'REAL_RECORDED_DEVELOPMENT_EVIDENCE', 'created_utc': utc(),
            'result': 'PASS' if code == 0 and len(facts) == 4 and all(row['result'] == 'PASS' for row in facts) else 'FAIL',
            'registry': registry_binding, 'slots': facts, 'planned_count': 4, 'attempted_count': len(facts),
            'pending_count': 4-len(facts), 'execution_terminal': binding(AUDIT/'execution_terminal.json'),
            'final_bindings_status': 'DEVELOPMENT_ONLY_NOT_REGISTERED_FORMAL_GATE', 'formal_seeds_consumed': False}
        write_new(AUDIT/'slots_facts.json', data)
        if data['result'] == 'PASS':
            summary = {'schema_version': 1, 'kind': 'RELIABILITY_V4_FINAL_SAFETY_SUMMARY',
                'validation_scope': 'DEVELOPMENT_METADATA_VALIDATION_ONLY_NOT_FORMAL_ADMISSION',
                'evidence_scope': 'REAL_RECORDED_DEVELOPMENT_EVIDENCE', 'created_utc': utc(), 'result': 'PASS',
                'bindings': frozen_bindings(plan), 'source_facts': binding(AUDIT/'slots_facts.json'), 'slots': facts,
                'formal_seed_use_authorized': False, 'formal_registration_created': False,
                'independent_frozen_guard_validation_required': True}
            write_new(AUDIT/'development_validation_summary.json', summary)
            # Full frozen guard validates original evidence, not an assembled PASS.
            validation = {'schema_version': 1, 'scope': 'INDEPENDENT_FROZEN_SAFETY_GUARD_DEVELOPMENT_RECHECK',
                'summary': binding(AUDIT/'development_validation_summary.json'), 'started_utc': utc(),
                'formal_seed_use_authorized': False}
            try:
                validation['actual_evidence_bindings'] = _validate_completed_safety_evidence(review, built, runner, plan, CORE)
                validation.update(result='PASS', error=None)
            except BaseException as error:
                validation.update(result='FAIL', error=type(error).__name__+':'+str(error))
                code = 2
            validation['finished_utc'] = utc()
            write_new(AUDIT/'development_guard_validation.json', validation)
    return code


def _validate_completed_safety_evidence(review, built, runner, core_plan=None, core_plan_path=None, *,
                                        admission_path=None, admission_sha256=None):
    """Stable actual file bindings only; full frozen guard is rerun every call."""
    require(admission_path is None and admission_sha256 is None, 'No synthetic safety admission is accepted')
    built = {**built, '_safety_tools_sha256': canonical(tool_manifest())}
    plan, registry, before = checked_registry(review, built, runner, core_plan=core_plan, core_plan_path=core_plan_path)
    terminal_path, facts_path, summary_path = (AUDIT/name for name in
        ('execution_terminal.json', 'slots_facts.json', 'development_validation_summary.json'))
    terminal, facts, summary = map(read_small, (terminal_path, facts_path, summary_path))
    require(terminal.get('scope') == SCOPE and terminal.get('returncode') == 0
        and terminal.get('status') == 'SAFETY4_ORIGINAL_ATTEMPTS_COMPLETE'
        and terminal.get('planned_count') == terminal.get('attempted_count') == 4 and terminal.get('pending_count') == 0
        and terminal.get('stop_reason') is None and terminal.get('final_errors') == []
        and terminal.get('entry_binding_before') == before
        and terminal.get('registry') == binding(AUDIT/'registry.json')
        and terminal.get('entry_binding_after') == source.entry_binding(review, common_built(built))
        and terminal.get('cleanup') == {'residual_processes': []}
        and terminal.get('formal_seeds_consumed') is False, 'No healthy original four-safety completion')
    require(facts.get('execution_terminal') == binding(terminal_path) and facts.get('result') == 'PASS'
        and facts.get('registry') == binding(AUDIT/'registry.json')
        and summary.get('source_facts') == binding(facts_path) and summary.get('slots') == facts.get('slots')
        and summary.get('validation_scope') == 'DEVELOPMENT_METADATA_VALIDATION_ONLY_NOT_FORMAL_ADMISSION'
        and summary.get('bindings') == frozen_bindings(plan), 'Original safety facts/validation summary changed')
    trials, slots = registry['trials'], terminal.get('slots', [])
    require([row.get('id') for row in slots] == [trial['id'] for trial in trials]
        and len(facts.get('slots', [])) == 4, 'Original four safety slots/order incomplete')
    records = []
    modules = stable.dependencies()
    for trial, item, fact in zip(trials, slots, facts['slots']):
        path, row = bound_json(item['terminal'])
        require(path == AUDIT/(trial['id']+'.json') and item.get('status') == row.get('status') == 'PASS'
            and item.get('infrastructure_stop') is row.get('infrastructure_stop') is False
            and row.get('trial') == trial and row.get('source_binding_after') == before['source']
            and {**row['execution_facts'], 'original_terminal': item['terminal']} == fact,
            'Original safety slot/facts/source status changed')
        require(set(fact.get('evidence', {})) == set(EVIDENCE)|{'specialized'}
            and set(fact.get('executions', {})) == EXECUTIONS, 'Original 5 executions/12 evidence incomplete')
        started_path = AUDIT/(trial['id']+'.started.json')
        started = read_small(started_path)
        require(started.get('trial') == trial and started.get('registry') == binding(AUDIT/'registry.json')
            and started.get('source_binding') == before['source'], 'Original safety started marker changed')
        commands = {'flight': trial['flight_command'], **safety_evaluations(trial)}
        require(set(row.get('executions', {})) == EXECUTIONS, 'Original outer execution receipt denominator differs')
        for kind, command in commands.items():
            receipt = row['executions'][kind]
            require(Path(receipt['path']) == AUDIT/(trial['id']+'_'+kind+'.outer_execution.json'),
                    'Original outer execution receipt path substituted')
            original_execution(receipt, command)
        require(slot_facts(row, registry) == row['execution_facts'], 'Original safety execution ledgers/evidence changed')
        safety_runtime(runner, plan, trial, review, modules['humble33_diagnostic_checks01'])
        records.append({'terminal': item['terminal'], 'started': binding(started_path),
                        'executions': {kind: {key: row['executions'][kind][key] for key in ('path', 'sha256')}
                                       for kind in sorted(EXECUTIONS)}})
    observer = owner.validate_observer_root(terminal.get('observer_owner_terminal'),
        AUDIT/'observer_driver', ROOT)
    require(observer == terminal.get('observer'), 'Original safety observer binding differs')
    guard = frozen_guard()
    checked_at = datetime.now(timezone.utc)
    # The final formal guard will check real registration timestamps again.
    # This development-only invocation checks chronology against real now,
    # without creating or inventing a formal protocol registration.
    context = SimpleNamespace(core=plan, development=plan, development_path=CORE.resolve(strict=True),
        gate_bindings=frozen_bindings(plan), registration_times=[checked_at, checked_at])
    guard.validate_safety({'safety': binding(summary_path)}, context, SimpleNamespace(v4=runner))
    require(not runner.simulation_processes(), 'Residual runtime after actual safety validation')
    return {'registry': binding(AUDIT/'registry.json'), 'terminal': binding(terminal_path),
        'facts': binding(facts_path), 'development_validation_summary': binding(summary_path),
        'core_plan': {**binding(CORE), 'plan_sha256': plan['plan_sha256']}, 'records': records,
        'observer': observer, 'frozen_guard': binding(ROOT/'tools/reliability_v4_guard.py'),
        'all_four_original_pass': True, 'formal_seed_use_authorized': False}


def require_completed_safety(review, built, runner, core_plan=None, core_plan_path=None, *,
                             admission_path=None, admission_sha256=None):
    """Recheck the full frozen guard and preserve its original actual outcome."""
    validation_path = AUDIT/'development_guard_validation.json'
    validation = read_small(validation_path)
    require(validation.get('scope') == 'INDEPENDENT_FROZEN_SAFETY_GUARD_DEVELOPMENT_RECHECK'
        and validation.get('result') == 'PASS' and validation.get('error') is None
        and validation.get('formal_seed_use_authorized') is False
        and validation.get('summary') == binding(AUDIT/'development_validation_summary.json'),
        'Original independent frozen safety-guard validation is missing or failed; no retry promotion')
    result = _validate_completed_safety_evidence(review, built, runner, core_plan, core_plan_path,
        admission_path=admission_path, admission_sha256=admission_sha256)
    require(validation.get('actual_evidence_bindings') == result, 'Original guard-validated evidence bindings changed')
    return {**result, 'independent_guard_validation': binding(validation_path)}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', choices=('describe', 'register', 'run'))
    result.add_argument('--review', type=Path); result.add_argument('--review-sha256')
    result.add_argument('--reviewed-tools-sha256'); result.add_argument('--frozen-root')
    result.add_argument('--registry-sha256')
    return result


def reviewed_source(args):
    require(args.action in ('register', 'run') and args.frozen_root == str(ROOT)
        and generic.valid_sha(args.review_sha256) and generic.valid_sha(args.reviewed_tools_sha256)
        and canonical(tool_manifest()) == args.reviewed_tools_sha256, 'Explicit41 source/root/reviewed safety tools required')
    require(args.action != 'run' or generic.valid_sha(args.registry_sha256), 'Run requires the separately reviewed original registry SHA')
    review = generic.load_review(args.review, args.review_sha256, 'validate')
    require(review['frozen_root'] == str(ROOT), 'Wrong source review root')
    return review


def shell_root(argv):
    reviewed_source(parser().parse_args(argv))
    return str(ROOT)


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
            built.update(_reviewed_tools_sha256=SOURCE_SHA, _safety_tools_sha256=args.reviewed_tools_sha256)
            source.require_runtime(review, modules['humble33_diagnostic_checks01'])
            runner = generic.runner_at(ROOT)
            if args.action == 'register':
                return register_safety(review, built, runner)
            return run_safety(args, review, built, runner, modules)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'SAFETY_REFUSED_OR_STOPPED_OR_FAILED',
            'reason': type(error).__name__+':'+str(error), 'automatic_retry': False, 'readiness_claimed': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
