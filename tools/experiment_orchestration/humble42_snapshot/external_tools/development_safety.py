"""Parameterized original safety4 development runner; import/describe never fly.

Both register and run require independently reviewed candidate source/build and
fresh actual core12 all PASS. Run additionally requires a separately reviewed
prospective registry SHA. Original41 results/tools are immutable history only.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import development_runner as development
import safety_runner41 as original_safety
import reviewed_freeze_build as generic
import reviewed_timing_diagnostic as stable
import source_runtime41 as source
import local_runtime_observer41 as owner

EXTERNAL = Path(__file__).resolve().parent
SCOPE = 'PARAMETERIZED_SAFETY4_ORIGINAL_DEVELOPMENT_ATTEMPTS_NOT_FORMAL_GATE'
ORIGINAL_SAFETY_CANONICAL = '4b2600def87b15d2c3bbc0fd2279aee55e14eaaef1c18e048f87b48cba3d09fd'
DEVELOPMENT_CANONICAL = '4e5614388567b60ff5ab925390a37e254c8b8940f3092aa892579cf5cbd6359f'
ORIGINAL_CARD_SHA = '4cfad726ba7349efdbc0bc20129e95aa8f2414e65adf7e31539ad887bbe46e2c'
ORIGINAL_TAIL_SHA = '05d1d11b6357db83a9805fc96f013e01c1c7741d109d6c10501e497215c2b612'
CARD = EXTERNAL/'humble41_safety_execution01.md'
TAIL = EXTERNAL/'evaluate_humble41_safety_tail01.py'
OWN = ('development_safety.py', 'development_safety.sh', 'test_development_safety.py')
require, sha, canonical = generic.require, generic.sha, generic.canonical
read_small, write_new = generic.read_small, generic.write_new
binding, bound_json = original_safety.binding, original_safety.bound_json
utc = original_safety.utc
EXECUTIONS, EVIDENCE = original_safety.EXECUTIONS, original_safety.EVIDENCE
TAIL_CHECKS, AUTO_CHECKS, LOCKED_CHECKS = original_safety.TAIL_CHECKS, original_safety.AUTO_CHECKS, original_safety.LOCKED_CHECKS
report_names, slot_facts, original_execution = original_safety.report_names, original_safety.slot_facts, original_safety.original_execution

@dataclass(frozen=True)
class Context:
    candidate: dict
    review: dict
    built: dict
    runner: object
    modules: dict
    runtime: dict
    core_contract: Path
    core_contract_sha256: str
    tools_sha256: str
    registry_sha256: str | None = None

    @property
    def root(self):
        return Path(self.candidate['frozen_root'])

    @property
    def core(self):
        return development.locations(self.candidate)['plan']

    @property
    def audit(self):
        return self.root/'results'/(self.candidate['prefix']+'_safety_seed004_audit')


def tool_manifest():
    for module in (development, original_safety, generic, stable, source, owner):
        require(Path(module.__file__).resolve(strict=True) == (EXTERNAL/Path(module.__file__).name).resolve(strict=True), 'Dependency import escaped named external source')
    require(canonical(original_safety.tool_manifest()) == ORIGINAL_SAFETY_CANONICAL, 'Original41 safety tools changed')
    require(canonical(development.tool_manifest()) == DEVELOPMENT_CANONICAL, 'Reviewed parameterized core tools changed')
    require(sha(CARD) == ORIGINAL_CARD_SHA and sha(TAIL) == ORIGINAL_TAIL_SHA, 'Original complete safety card/tail bytes changed')
    return {'schema_version': 1, 'scope': SCOPE,
        'files': {name: binding(EXTERNAL/name)['sha256'] for name in OWN},
        'original_safety_tools_canonical_sha256': ORIGINAL_SAFETY_CANONICAL,
        'development_core_tools_canonical_sha256': DEVELOPMENT_CANONICAL,
        'original_tail_script_sha256': ORIGINAL_TAIL_SHA, 'original_card_sha256': ORIGINAL_CARD_SHA,
        'root_binding': 'explicit reviewed candidate; dependency globals never modified',
        'actions': ['register', 'run'], 'requires_all12_actual_core_pass': True,
        'explicit_actual_core_contract_required': True, 'separately_reviewed_registry_sha_required_to_run': True,
        'all_four_flight_and_evaluation_argv_registered': True, 'direct_flight_single_outer_machine_lock': True,
        'normal_run_plan_used_for_safety': False, 'executions_per_slot': 5, 'evidence_per_slot': 12,
        'original_tail_unchanged': True, 'tail_interval_s': 5.2, 'observed_and_offline_gt_speed_limit_mps': .30,
        'flight_outer_timeout_s': 3200., 'evaluation_outer_timeout_s': 1800.,
        'formal_seed_use_authorized': False, 'readiness_claimed': False, 'automatic_retry': False,
        'automatic_next_action': False, 'resume_or_recovery_authorized': False}


def entry_binding(ctx, review, built):
    require(generic.valid_sha(ctx.tools_sha256) and canonical(tool_manifest()) == ctx.tools_sha256, 'Independently reviewed safety tool bytes changed')
    return {**development.entry_binding(ctx.candidate, review, built), 'safety_tools_canonical_sha256': ctx.tools_sha256}


def actual_core(ctx, review, built, runner, core_plan=None, core_plan_path=None):
    """Re-read actual complete original core12 attempts, never a manual summary."""
    path = Path(core_plan_path or ctx.core)
    require(path == ctx.core, 'Only actual explicit candidate core path can define safety')
    contract, plan = development.load_contract(ctx.candidate, review, built, runner, ctx.core_contract, ctx.core_contract_sha256)
    require(core_plan is None or core_plan == plan, 'Supplied core differs from actual immutable core file')
    selected = development.locations(ctx.candidate)
    terminal_path = selected['run_driver']/'execution_terminal.json'
    terminal = read_small(terminal_path)
    source_binding = development.entry_binding(ctx.candidate, review, built)
    expected_contract = {'path': str(ctx.core_contract), 'sha256': ctx.core_contract_sha256}
    require(terminal.get('schema_version') == 1 and terminal.get('scope') == development.SCOPE
        and terminal.get('action') == 'run-core' and type(terminal.get('returncode')) is int and terminal['returncode'] == 0
        and terminal.get('status') == 'ORIGINAL_CORE_TERMINALS_COMPLETE' and terminal.get('error') is None
        and terminal.get('slot_read_error') is None
        and all(type(terminal.get(k)) is int and terminal[k] == 12 for k in ('planned_count','attempt_count','terminal_count'))
        and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == source_binding
        and terminal.get('final_errors') == [] and terminal.get('cleanup') == {'residual_processes': []}
        and all(terminal.get(k) is False for k in development.FALSE_FIELDS)
        and terminal.get('contract') == expected_contract and terminal.get('plan') == contract['plan_pending']
        and 'zero_attempt_recovery' not in terminal,
        'Actual candidate core12 did not close completely and healthily')
    ids = [t['id'] for t in plan['trials']]
    require(len(ids) == 12 and len(set(ids)) == 12
        and [x.get('slot') for x in terminal.get('slots',[])] == ids
        and [x.get('slot') for x in terminal.get('attempts',[])] == ids, 'Actual core12 slot/attempt denominator or order differs')
    rows, bound = runner.read_slots(plan), []
    require(set(rows) == set(ids), 'Actual original core row denominator differs')
    checks = ctx.modules['humble33_diagnostic_checks01']
    for number, (trial,item,attempt) in enumerate(zip(plan['trials'],terminal['slots'],terminal['attempts']),1):
        record = rows[trial['id']]
        audit = development.original41.audit_record(runner, plan, trial, record, review, checks)
        require(record.get('status') == record.get('engineering_result') == 'PASS', 'All12 actual original core cells must PASS before safety')
        require(item == {'slot':trial['id'],'status':record['status'],'engineering_result':record['engineering_result'],'audit':audit}
            and type(attempt.get('number')) is int and attempt['number'] == number and attempt.get('error') is None
            and attempt.get('audit') == audit and type(attempt.get('runner_result',{}).get('started_this_invocation')) is int
            and attempt['runner_result']['started_this_invocation'] == 1
            and attempt.get('record') == {'status':record['status'],'engineering_result':record['engineering_result'],'record_binding':audit['record_binding']},
            'Actual original core row/attempt/report changed')
        marker_path = selected['run_driver']/f'{number:02d}_{trial["id"]}.started.json'
        require(stable.metadata_binding(marker_path,json_only=True) == attempt.get('started_marker')
            and read_small(marker_path) == {'slot':trial['id'],'number':number,'entry_binding':source_binding,
                'contract':expected_contract,'plan_sha256':plan['plan_sha256'],'started_utc':attempt['started_utc'],'original_attempt_number':1},
            'Actual original core started marker changed')
        attempt_path = selected['run_driver']/f'{number:02d}_{trial["id"]}.attempt_terminal.json'
        require(read_small(attempt_path) == attempt, 'Actual original core per-attempt terminal changed')
        bound.append({'id':trial['id'],'status':record['status'],'record_binding':audit['record_binding'],
            'attempt_terminal':stable.metadata_binding(attempt_path,json_only=True)})
    observed = owner.validate_observer_root(terminal.get('observer_owner_terminal'),selected['run_driver']/'observer_driver',ctx.candidate['frozen_root'])
    actual_rows = {k:{'status':v.get('status'),'record_sha256':v.get('record_sha256')} for k,v in rows.items()}
    require(terminal.get('actual_slot_statuses') == actual_rows
        and terminal.get('status_counts') == dict(Counter(row['status'] for row in actual_rows.values()))
        and terminal.get('observer') == observed, 'Actual core aggregate status or healthy original owner changed')
    require(not runner.simulation_processes(), 'Runtime residual remains after actual core12')
    runner.verify_sources(plan)
    return path, plan, {'result':'PASS','core_plan':development.pending_identity(plan),
        'execution_terminal':stable.metadata_binding(terminal_path,json_only=True),'completed_count':12,
        'all_original_core_cells_pass':True,'original_terminals':bound,'observer':observed,'formal_seed_use_authorized':False}


def load_frozen_module(ctx, relative, name):
    path = ctx.root / relative
    require(path.is_file() and (not path.is_symlink()), 'Missing actual frozen module')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def frozen_guard(ctx):
    return load_frozen_module(ctx, 'tools/reliability_v4_guard.py', '_humble41_safety_guard')


def frozen_bindings(ctx, plan):
    builder = load_frozen_module(ctx, 'scripts/build_reliability_v4_probe_gate.py', '_humble41_safety_gate_builder')
    require(Path(builder.v4.__file__).resolve(strict=True) == (ctx.root / 'scripts/run_reliability_v4.py').resolve(strict=True), 'Gate builder imported a runner outside actual frozen41')
    return builder.bindings(plan)


def policy_flags(ctx, runner, protocol, cls):
    """Derive registered geometry/measurement/pacing from the frozen runner."""
    require(cls in ('person', 'car'), 'Unknown safety class')
    runner.validate_protocol(protocol)
    resource = protocol['resources'][cls]
    geometry = runner.correlated_two_face_setting(resource, cls)
    recovery = runner.car_surface_recovery_setting(resource, cls)['enabled']
    source.validate_class_policy(protocol, runner)
    exclusive = runner.exclusive_navigation_setting(resource, cls)
    pacing = runner.simulation_pacing_summary(protocol)
    require(runner.simulation_pacing_declared(protocol) and pacing == protocol.get(source.PACING_FIELD) and pacing.get('safety_source_time_gates') == 'unchanged', 'Safety requires the actual explicit reviewed pacing and unchanged source gates')
    flags = []
    if geometry:
        flags.append(runner.CORRELATED_BOUND_FLAG)
    if recovery:
        flags.append(runner.CAR_SURFACE_RECOVERY_FLAG)
    if exclusive:
        flags.append(runner.EXCLUSIVE_NAVIGATION_FLAG)
    field, flag = (runner.PX4_ADAPTER_PUBLISH_RATE_FIELD, runner.PX4_ADAPTER_PUBLISH_RATE_FLAG)
    require(field in pacing, 'Safety V2 adapter cadence declaration missing')
    flags.extend([flag, str(pacing[field])])
    return (flags, geometry, recovery, pacing[field], exclusive)


def safety_definitions(ctx, runner, plan):
    development.validate_matrix(ctx.candidate, plan, runner, ctx.core)
    protocol, trials = (plan['protocol'], [])
    for cls in ('person', 'car'):
        resource = protocol['resources'][cls]
        flags, geometry, recovery, rate, exclusive = policy_flags(ctx, runner, protocol, cls)
        for case in ('auto_unique_multi', 'locked_ambiguity'):
            automatic = case == 'auto_unique_multi'
            identifier = f'{cls}_{case}_seed004'
            name = ctx.candidate['prefix'] + '_safety_' + identifier
            settings = {'name': name, 'target_class': cls, 'stage': 2, 'seed': 4, 'condition': 'clean', 'estimator_method': 'adaptive_kf', 'command_mode': 'velocity', 'gimbal_mode': 'midpoint', 'real_time_factor': protocol['real_time_factor'], 'max_inference_rate_hz': 10.0, 'monitor_tick_s': 0.02, 'control_reference': 'ground_footprint', 'motion_profile_kind': 'standard', 'model_path': str(ctx.root / resource['model']), 'inference_image_size': resource['inference_image_size'], 'inference_threads': resource['inference_threads'], 'desired_distance_m': resource['desired_distance_m'], 'takeoff_height_m': 3.0, 'takeoff_mode': 'px4_native', 'wall_timeout': protocol['flight_wall_timeout_s'], 'render_backend': 'egl', 'gazebo_render_driver': protocol['gazebo_render_driver'], 'magnetic_environment': 'gazebo_enu', 'magnetic_runtime_manifest': str(ctx.root / 'config/px4_magnetic_runtime.json'), 'magnetic_library_registration': str(ctx.root / protocol['magnetic_library_registration']), 'ros_gz_runtime_registration': str(ctx.root / 'config/ros_gz_runtime_humble22.json'), 'propagate_vehicle_uncertainty': True, 'px4_time_mode': 'source_sim', 'target_mode': 'auto_unique' if automatic else 'locked_target', 'association_mode': 'legacy' if automatic else 'hybrid_3d', 'scenario_kind': 'parallel' if automatic else 'ambiguity', 'initial_select': 'none' if automatic else 'middle', 'initial_min_candidates': 2 if automatic else 3, 'duration': 35.0 if automatic else 50.0}
            if automatic:
                settings['no_follow_duration_s'] = 35.0
            command = ['bash', str(ctx.root / 'scripts/run_research_session.sh'), str(ctx.root / 'scripts/run_stage1_trial.py')]
            for key, value in settings.items():
                command.append('--class' if key == 'target_class' else '--' + key.replace('_', '-'))
                if value is not True:
                    command.append(str(value))
            command.extend(flags)
            settings.update(correlated_two_face_bound=geometry, car_surface_recovery=recovery, px4_adapter_publish_rate_hz=rate, exclusive_navigation_reference=exclusive)
            trials.append({'id': identifier, 'name': name, 'directory': str(ctx.root / 'results' / name), 'target_class': cls, 'case': case, 'seed': 4, 'settings': settings, 'flight_command': command, 'flight_argv': list(command), 'world_source': f'ros2_ws/src/uav_tracking_bringup/worlds/stage2_flight_{cls}.sdf'})
    for trial in trials:
        commands = {'flight': trial['flight_command'], **safety_evaluations(ctx, trial)}
        trial['execution_commands'] = commands
        trial['execution_command_sha256'] = {key: canonical(value) for key, value in commands.items()}
    return trials


def verify_tail(ctx, guard=None):
    require(sha(CARD) == ORIGINAL_CARD_SHA and sha(TAIL) == ORIGINAL_TAIL_SHA, 'Original safety card or complete tail bytes changed')
    guard = guard or frozen_guard(ctx)
    registry = {'execution_card': binding(CARD), 'tail_script': binding(TAIL)}
    guard.verified_safety_card(registry, ctx.root)
    return registry


def safety_runtime(ctx, runner, plan, trial, review, checks):
    import yaml
    guard, directory = (frozen_guard(ctx), Path(trial['directory']))
    config = read_small(directory / 'run_config.json')
    expected = {**trial['settings'], 'occlusions': False, 'reselect_after_loss': False, 'no_bag': False, 'vehicle_control_point_offset_flu_m': [0.0, 0.0, 0.24]}
    require(all((key in config and config[key] == value and (type(value) is not bool or type(config[key]) is bool) for key, value in expected.items())), 'Actual safety configuration differs from its prospective argv')
    snapshot = read_small(directory / 'configuration/source_sha256.json')
    expected_sources = {key: value for key, value in plan['source_hashes'].items() if key.startswith(('scripts/', 'uav_tracking/', 'ros2_ws/src/')) and Path(key).suffix in {'.py', '.sh', '.msg'}}
    model = plan['protocol']['resources'][trial['target_class']]['model']
    expected_sources[model] = plan['source_hashes'][model]
    require(snapshot == expected_sources, 'Saved safety source/model snapshot differs')
    path = directory / 'configuration/runtime_parameters.yaml'
    require(path.is_file() and (not path.is_symlink()) and (path.stat().st_size <= 1024 * 1024), 'Unsafe safety runtime YAML')
    parameters = yaml.safe_load(path.read_text(encoding='utf-8'))
    resource, cls, argv = (plan['protocol']['resources'][trial['target_class']], trial['target_class'], trial['flight_command'])
    guard.geometry_bound_evidence(resource, cls, config, parameters, argv)
    guard.car_surface_recovery_evidence(SimpleNamespace(v4=runner), resource, cls, config, parameters, argv)
    guard.exclusive_navigation_evidence(SimpleNamespace(v4=runner), resource, cls, config, parameters, argv)
    guard.simulation_pacing_evidence(SimpleNamespace(v4=runner), plan['protocol'], config, parameters, argv)
    supported_birth = source.validate_supported_birth_runtime(cls, config, parameters)
    expected_parameters = {'uav_tracking_detection': {'navigation_enabled': True, 'depth_max_age_s': 0.02, 'model_path': config['model_path'], 'navigation_exclusive_enabled': config['exclusive_navigation_reference'], 'inference_image_size': config['inference_image_size'], 'inference_threads': config['inference_threads'], 'max_inference_rate_hz': 10.0}, 'uav_tracking_state_estimator': {'navigation_enabled': True, 'max_observation_age_s': 0.6, 'navigation_exclusive_enabled': config['exclusive_navigation_reference'], 'max_prediction_duration_s': 0.75, 'mahalanobis_gate': 9.21, 'target_mode': config['target_mode'], 'association_mode': config['association_mode'], 'propagate_vehicle_uncertainty': True, 'estimator_method': 'adaptive_kf'}, 'uav_tracking_controller': {'state_topic': '/tracking/navigation_state', 'command_mode': 'velocity', 'desired_distance_m': config['desired_distance_m'], 'desired_height_m': 2.0, 'prediction_timeout_s': 0.75}, 'uav_tracking_px4_adapter': {'use_sim_time': True, 'odometry_timestamp_mode': 'source_sim', 'odometry_source_max_age_s': 0.5, 'odometry_source_max_future_s': 0.05}, 'uav_tracking_flight_supervisor': {'takeoff_mode': 'px4_native', 'takeoff_height_m': 3.0, 'status_timestamp_mode': 'source_sim', 'status_source_max_age_s': 1.0, 'status_source_max_future_s': 0.05, 'status_timeout_s': 10.0, 'requested_simulation_real_time_factor': plan['protocol']['real_time_factor']}}
    require(all((parameters.get(node, {}).get('ros__parameters', {}).get(key) == value and (type(value) is not bool or type(parameters[node]['ros__parameters'][key]) is bool) for node, values in expected_parameters.items() for key, value in values.items())), 'Actual safety YAML gates differ')
    checks.native_handoff_runtime(directory)
    require(not runner.gazebo_rendering_evidence(directory, 'llvmpipe')['errors'] and (not runner.magnetic_environment_evidence(plan, trial)['errors']), 'Actual safety rendering/magnetic contract differs')
    return {'run_config': binding(directory / 'run_config.json'), 'runtime_parameters': binding(path), 'supported_birth_confirmation': supported_birth, 'bridge': checks.bridge_evidence(directory, review), 'processes': checks.process_evidence(directory, stage=2)}


def safety_evaluations(ctx, trial):
    directory, names = (Path(trial['directory']), report_names(trial))
    prefix = ['bash', str(ctx.root / 'scripts/run_research_session.sh')]
    specialty = [str(ctx.root / 'scripts/run_stage23_matrix.py'), '--evaluate-auto-unique', str(directory / 'rosbag'), '--target-class', trial['target_class']] if trial['case'] == 'auto_unique_multi' else [str(ctx.root / 'scripts/evaluate_stage2_flight.py'), str(directory / 'rosbag'), '--target-class', trial['target_class'], '--telemetry-jsonl', str(directory / 'telemetry.jsonl'), '--monitor-summary', str(directory / 'summary.json'), '--no-require-occlusions', '--require-ambiguity', '--terminal-expectation', 'hover']
    return {'source_clock': prefix + [str(ctx.root / 'scripts/evaluate_px4_source_clock.py'), str(directory), '--output', str(directory / names['source_clock'])], 'native_startup': prefix + [str(ctx.root / 'scripts/evaluate_native_startup.py'), str(directory), '--output', str(directory / names['native_startup'])], 'specialized': prefix + specialty + ['--output', str(directory / names['specialized'])], 'terminal_speed': prefix + [str(TAIL), str(directory), str(CARD)]}


def execute(ctx, command, name, observer, timeout):
    require(name.replace('_', '').isalnum(), 'Unsafe execution receipt name')
    actual = stable.execute_owned(command, ctx.audit / (name + '.log'), observer, timeout, ctx.root)
    path = ctx.audit / (name + '.outer_execution.json')
    write_new(path, actual)
    return {**binding(path), 'execution': actual}


def safety_report_audit(ctx, trial, runner, plan, executions):
    directory = Path(trial['directory'])
    reports = {kind: read_small(directory / name) for kind, name in report_names(trial).items()}
    for kind, script in [('source_clock', 'evaluate_px4_source_clock.py'), ('native_startup', 'evaluate_native_startup.py')]:
        spec = {'kind': kind, 'script': 'scripts/' + script, 'report': str(directory / report_names(trial)[kind]), 'evaluation_root': str(ctx.root)}
        require(runner.read_evaluation(spec, executions[kind]['execution'], plan)['result'] == 'PASS', 'Independent safety source/native report did not PASS')
    specialty = reports['specialized']
    schema, source = (2, 'OFFLINE_AUTO_UNIQUE_MULTIPLE_CANDIDATE_SAFETY') if trial['case'] == 'auto_unique_multi' else (1, 'OFFLINE_STAGE2_SAFETY_EVALUATION')
    require(specialty.get('schema_version') == schema and specialty.get('source') == source and (specialty.get('result') in ('PASS', 'FAIL')) and bool(specialty.get('checks')) and (set(specialty['checks']) == (AUTO_CHECKS if trial['case'] == 'auto_unique_multi' else LOCKED_CHECKS)) and all((type(value) is bool for value in specialty['checks'].values())) and (Path(specialty.get('inputs', {}).get('bag', '')).resolve() == (directory / 'rosbag').resolve()) and (not specialty['inputs'].get('read_errors')) and (not specialty['inputs'].get('unavailable_types')), 'Specialized safety report is incomplete/malformed/foreign')
    tail = reports['terminal_speed']
    require(tail.get('schema_version') == 1 and tail.get('result') in ('PASS', 'FAIL') and (Path(tail.get('trial', '')).resolve() == directory.resolve()) and (set(tail.get('checks', {})) == TAIL_CHECKS) and all((type(value) is bool for value in tail['checks'].values())) and (abs(tail.get('interval', {}).get('end_s', 0.0) - tail.get('interval', {}).get('start_s', 0.0) - 5.2) < 1e-06) and (tail.get('bag_reader', {}).get('clock_recorded') is True) and (not tail['bag_reader'].get('read_errors')) and (not tail['bag_reader'].get('unavailable_types')), 'Original full5.2s dual-speed audit is incomplete/malformed/foreign')
    closure = read_small(directory / 'recording_closure.json')
    final_clock = closure['observations'][-1]['last_clock_ns'] / 1000000000.0
    require(abs(tail['interval']['end_s'] - final_clock) < 1e-09, 'Tail does not reach the original final recorded Clock')
    for report in (specialty, tail):
        require(report['result'] == ('PASS' if all(report['checks'].values()) else 'FAIL'), 'Safety verdict contradicts original checks')
    return {'status': 'PASS' if specialty['result'] == tail['result'] == 'PASS' else 'FAIL', 'source_clock': 'PASS', 'native_startup': 'PASS', 'specialized': specialty['result'], 'terminal_speed': tail['result'], 'reports': {kind: binding(directory / name) for kind, name in report_names(trial).items()}}


def register_safety(ctx, review, built, runner):
    core_path, plan, complete = actual_core(ctx, review, built, runner)
    trials = safety_definitions(ctx, runner, plan)
    tail = verify_tail(ctx)
    require(not ctx.audit.exists() and (not ctx.audit.is_symlink()) and all((not Path(trial['directory']).exists() and (not Path(trial['directory']).is_symlink()) for trial in trials)) and (not runner.simulation_processes()), 'Fresh safety audit/four trial paths and idle runtime required; no retry')
    before = entry_binding(ctx, review, built)
    ctx.audit.mkdir(exist_ok=False)
    registry = {'schema_version': 1, 'kind': 'RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY', 'scope': SCOPE, 'created_utc': utc(), 'trials': trials, 'source_core_plan': {**binding(core_path), 'plan_sha256': plan['plan_sha256']}, 'core_completed_prerequisite': complete, 'source_binding': before['source'], 'freeze_source_sha256': before['source']['freeze_source_sha256'], 'flight_source_hashes': runner.flight_source_hashes(plan['source_hashes']), 'driver': binding(__file__), **tail, 'safety_tools_sha256': ctx.tools_sha256, 'entry_binding': before, 'formal_seeds_consumed': False, 'automatic_retry': False, 'policy': 'Four original attempts once; complete algorithm FAIL remains. Source/native/infra/observer faults stop; no automatic extension.'}
    write_new(ctx.audit / 'registry.json', registry)
    require(entry_binding(ctx, review, built) == before, 'Frozen source/tools changed during prospective registration')
    print(json.dumps({'registry': binding(ctx.audit / 'registry.json'), 'trials': [trial['id'] for trial in trials], 'flight_actions_executed': 0, 'requires_explicit_reviewed_registry_sha_to_run': True}))
    return 0


def checked_registry(ctx, review, built, runner, expected_sha=None, core_plan=None, core_plan_path=None):
    path, plan, complete = actual_core(ctx, review, built, runner, core_plan, core_plan_path)
    registry_path = ctx.audit / 'registry.json'
    require(generic.valid_sha(expected_sha) and sha(registry_path) == expected_sha,
            'Explicit separately reviewed registry SHA is required and must match')
    registry = read_small(registry_path)
    before = entry_binding(ctx, review, built)
    require(registry.get('schema_version') == 1 and registry.get('kind') == 'RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY' and (registry.get('scope') == SCOPE) and (registry.get('trials') == safety_definitions(ctx, runner, plan)) and (registry.get('source_core_plan') == {**binding(path), 'plan_sha256': plan['plan_sha256']}) and (registry.get('entry_binding') == before) and (registry.get('source_binding') == before['source']) and (registry.get('freeze_source_sha256') == before['source']['freeze_source_sha256']) and (registry.get('flight_source_hashes') == runner.flight_source_hashes(plan['source_hashes'])) and (registry.get('safety_tools_sha256') == ctx.tools_sha256) and (registry.get('driver') == binding(__file__)) and (registry.get('formal_seeds_consumed') is False), 'Prospective four-safety registry differs from the actual same-source core/tool configuration')
    require(registry['core_completed_prerequisite'] == complete, 'Original completed core prerequisite changed')
    require({key: registry[key] for key in ('execution_card', 'tail_script')} == verify_tail(ctx), 'Safety card/tail changed')
    return (plan, registry, before)


def run_safety(ctx, args, review, built, runner, modules):
    require(generic.valid_sha(args.registry_sha256), 'Run requires the exact separately reviewed registry SHA')
    plan, registry, before = checked_registry(ctx, review, built, runner, args.registry_sha256)
    trials = registry['trials']
    reserved = [ctx.audit / 'execution_terminal.json', ctx.audit / 'slots_facts.json', ctx.audit / 'observer_driver']
    reserved.extend((ctx.audit / (trial['id'] + suffix) for trial in trials for suffix in ('.started.json', '.json')))
    require(not any((path.exists() or path.is_symlink() for path in reserved)) and all((not Path(trial['directory']).exists() for trial in trials)) and (not runner.simulation_processes()), 'Existing safety attempt or runtime; refuse retry')
    with runner.run_lock(ctx.audit):
        return run_safety_locked(ctx, review, built, runner, modules, plan, registry, before)


def finish_action(ctx, review, built, runner, observer):
    """Retain the original owner-observed native/archive result, including failure."""
    errors, after, residual, observed = ([], None, None, None)
    actual_owner = observer._finished
    try:
        after = entry_binding(ctx, review, built)
    except BaseException as error:
        errors.append('binding:' + type(error).__name__ + ':' + str(error))
    try:
        residual = runner.simulation_processes()
        require(residual == [], 'Residual runtime processes remain')
    except BaseException as error:
        errors.append('residual:' + type(error).__name__ + ':' + str(error))
    try:
        observed = owner.validate_observer_root(actual_owner, ctx.audit / 'observer_driver', ctx.root)
    except BaseException as error:
        errors.append('observer:' + type(error).__name__ + ':' + str(error))
    return {'entry_binding_after': after, 'cleanup': {'residual_processes': residual}, 'observer_owner_terminal': actual_owner, 'observer': observed, 'final_errors': errors}


def run_safety_locked(ctx, review, built, runner, modules, plan, registry, before):
    checks = modules['humble33_diagnostic_checks01']
    observer = owner.make_observer(ctx.audit / 'observer_driver', ctx.root, archive_wall_budget_s=1800.0)
    completed, stop = ([], None)
    registry_binding, core_binding = (binding(ctx.audit / 'registry.json'), binding(ctx.core))

    def immutable():
        require(entry_binding(ctx, review, built) == before and binding(ctx.audit / 'registry.json') == registry_binding and (binding(ctx.core) == core_binding), 'Frozen source/registry/core changed during original safety attempts')
        runner.verify_sources(plan)
        require(not runner.simulation_processes(), 'Residual runtime before/after original safety attempt')
    try:
        with observer:
            for number, trial in enumerate(registry['trials'], 1):
                immutable()
                fresh = observer.check()
                require(not Path(trial['directory']).exists(), 'Safety trial already exists; no retry')
                write_new(ctx.audit / (trial['id'] + '.started.json'), {'created_utc': utc(), 'trial': trial, 'registry': registry_binding, 'source_binding': before['source'], 'observer_freshness': fresh})
                row = {'id': trial['id'], 'trial': trial, 'status': 'INFRASTRUCTURE_ERROR', 'infrastructure_stop': True, 'executions': {}, 'error': None}
                try:
                    receipt = execute(ctx, trial['flight_command'], trial['id'] + '_flight', observer, 3200.0)
                    row['executions']['flight'] = receipt
                    original_execution(receipt, trial['flight_command'])
                    require(runner.infrastructure_evidence(Path(trial['directory']), [])['stop'] is False and (not runner.simulation_processes()), 'Safety flight/recording failed to close cleanly')
                    row['runtime'] = safety_runtime(ctx, runner, plan, trial, review, checks)
                    for kind, command in safety_evaluations(ctx, trial).items():
                        output = Path(trial['directory']) / report_names(trial)[kind]
                        require(not output.exists(), 'Existing safety evaluation; no overwrite')
                        receipt = execute(ctx, command, trial['id'] + '_' + kind, observer, 1800.0)
                        row['executions'][kind] = receipt
                        original_execution(receipt, command, algorithm_exit=kind in ('specialized', 'terminal_speed'))
                    row['audit'] = safety_report_audit(ctx, trial, runner, plan, row['executions'])
                    attempts = [{'report': str(Path(trial['directory']) / report_names(trial)[kind]), 'log': receipt['execution']['log'], 'returncode': receipt['execution']['returncode']} for kind, receipt in row['executions'].items() if kind != 'flight']
                    row['infrastructure'] = runner.infrastructure_evidence(Path(trial['directory']), attempts)
                    require(row['infrastructure']['stop'] is False, 'Safety evaluator infrastructure incomplete')
                    row['status'], row['infrastructure_stop'] = (row['audit']['status'], False)
                    observer.check()
                except BaseException as error:
                    row['error'] = type(error).__name__ + ':' + str(error)
                    row['infrastructure_stop'] = True
                    raise
                finally:
                    try:
                        immutable()
                    except BaseException as error:
                        row['cleanup_error'] = type(error).__name__ + ':' + str(error)
                        row['infrastructure_stop'] = True
                    row['source_binding_after'] = before['source'] if not row.get('cleanup_error') else None
                    row['finished_utc'] = utc()
                    row['execution_facts'] = slot_facts(row, registry)
                    path = ctx.audit / (trial['id'] + '.json')
                    write_new(path, row)
                    completed.append({'id': trial['id'], 'status': row['status'], 'infrastructure_stop': row['infrastructure_stop'], 'terminal': binding(path)})
                    print(json.dumps({'event': 'COMPLETE_ORIGINAL_SAFETY_SLOT', 'number': number, 'total': 4, **completed[-1]}), flush=True)
                require(not row['infrastructure_stop'], 'Safety infrastructure fault; no automatic next attempt')
    except BaseException as error:
        stop = type(error).__name__ + ':' + str(error)
    finally:
        cleanup = finish_action(ctx, review, built, runner, observer)
        try:
            immutable()
        except BaseException as error:
            cleanup['final_errors'].append('immutable:' + type(error).__name__ + ':' + str(error))
        code = 0 if len(completed) == 4 and (not stop) and (not cleanup['final_errors']) and all((not row['infrastructure_stop'] for row in completed)) else 2
        terminal = {'schema_version': 1, 'scope': SCOPE, 'finished_utc': utc(), 'returncode': code, 'status': 'SAFETY4_ORIGINAL_ATTEMPTS_COMPLETE' if code == 0 else 'STOPPED_NO_AUTOMATIC_RETRY', 'planned_count': 4, 'attempted_count': len(completed), 'pending_count': 4 - len(completed), 'slots': completed, 'stop_reason': stop, 'registry': registry_binding, 'entry_binding_before': before, **cleanup, 'observer_owner_terminal': observer._finished, 'formal_seeds_consumed': False, 'automatic_followon_actions': False}
        write_new(ctx.audit / 'execution_terminal.json', terminal)
        facts = [{**bound_json(row['terminal'])[1]['execution_facts'], 'original_terminal': row['terminal']} for row in completed]
        data = {'schema_version': 1, 'kind': 'RELIABILITY_V4_SAFETY_EXECUTION_FACTS', 'evidence_scope': 'REAL_RECORDED_DEVELOPMENT_EVIDENCE', 'created_utc': utc(), 'result': 'PASS' if code == 0 and len(facts) == 4 and all((row['result'] == 'PASS' for row in facts)) else 'FAIL', 'registry': registry_binding, 'slots': facts, 'planned_count': 4, 'attempted_count': len(facts), 'pending_count': 4 - len(facts), 'execution_terminal': binding(ctx.audit / 'execution_terminal.json'), 'final_bindings_status': 'DEVELOPMENT_ONLY_NOT_REGISTERED_FORMAL_GATE', 'formal_seeds_consumed': False}
        write_new(ctx.audit / 'slots_facts.json', data)
        if data['result'] == 'PASS':
            summary = {'schema_version': 1, 'kind': 'RELIABILITY_V4_FINAL_SAFETY_SUMMARY', 'validation_scope': 'DEVELOPMENT_METADATA_VALIDATION_ONLY_NOT_FORMAL_ADMISSION', 'evidence_scope': 'REAL_RECORDED_DEVELOPMENT_EVIDENCE', 'created_utc': utc(), 'result': 'PASS', 'bindings': frozen_bindings(ctx, plan), 'source_facts': binding(ctx.audit / 'slots_facts.json'), 'slots': facts, 'formal_seed_use_authorized': False, 'formal_registration_created': False, 'independent_frozen_guard_validation_required': True}
            write_new(ctx.audit / 'development_validation_summary.json', summary)
            validation = {'schema_version': 1, 'scope': 'INDEPENDENT_FROZEN_SAFETY_GUARD_DEVELOPMENT_RECHECK', 'summary': binding(ctx.audit / 'development_validation_summary.json'), 'started_utc': utc(), 'formal_seed_use_authorized': False}
            try:
                validation['actual_evidence_bindings'] = _validate_completed_safety_evidence(ctx, review, built, runner, plan, ctx.core)
                validation.update(result='PASS', error=None)
            except BaseException as error:
                validation.update(result='FAIL', error=type(error).__name__ + ':' + str(error))
                code = 2
            validation['finished_utc'] = utc()
            write_new(ctx.audit / 'development_guard_validation.json', validation)
    return code


def _validate_completed_safety_evidence(ctx, review, built, runner, core_plan=None, core_plan_path=None, *, admission_path=None, admission_sha256=None):
    """Stable actual file bindings only; full frozen guard is rerun every call."""
    require(admission_path is None and admission_sha256 is None, 'No synthetic safety admission is accepted')
    plan, registry, before = checked_registry(ctx, review, built, runner, expected_sha=ctx.registry_sha256, core_plan=core_plan, core_plan_path=core_plan_path)
    terminal_path, facts_path, summary_path = (ctx.audit / name for name in ('execution_terminal.json', 'slots_facts.json', 'development_validation_summary.json'))
    terminal, facts, summary = map(read_small, (terminal_path, facts_path, summary_path))
    require(terminal.get('scope') == SCOPE and terminal.get('returncode') == 0 and (terminal.get('status') == 'SAFETY4_ORIGINAL_ATTEMPTS_COMPLETE') and (terminal.get('planned_count') == terminal.get('attempted_count') == 4) and (terminal.get('pending_count') == 0) and (terminal.get('stop_reason') is None) and (terminal.get('final_errors') == []) and (terminal.get('entry_binding_before') == before) and (terminal.get('registry') == binding(ctx.audit / 'registry.json')) and (terminal.get('entry_binding_after') == entry_binding(ctx, review, built)) and (terminal.get('cleanup') == {'residual_processes': []}) and (terminal.get('formal_seeds_consumed') is False), 'No healthy original four-safety completion')
    require(facts.get('execution_terminal') == binding(terminal_path) and facts.get('result') == 'PASS' and (facts.get('registry') == binding(ctx.audit / 'registry.json')) and (summary.get('source_facts') == binding(facts_path)) and (summary.get('slots') == facts.get('slots')) and (summary.get('validation_scope') == 'DEVELOPMENT_METADATA_VALIDATION_ONLY_NOT_FORMAL_ADMISSION') and (summary.get('bindings') == frozen_bindings(ctx, plan)), 'Original safety facts/validation summary changed')
    trials, slots = (registry['trials'], terminal.get('slots', []))
    require([row.get('id') for row in slots] == [trial['id'] for trial in trials] and len(facts.get('slots', [])) == 4, 'Original four safety slots/order incomplete')
    records = []
    modules = stable.dependencies()
    for trial, item, fact in zip(trials, slots, facts['slots']):
        path, row = bound_json(item['terminal'])
        require(path == ctx.audit / (trial['id'] + '.json') and item.get('status') == row.get('status') == 'PASS' and (item.get('infrastructure_stop') is row.get('infrastructure_stop') is False) and (row.get('trial') == trial) and (row.get('source_binding_after') == before['source']) and ({**row['execution_facts'], 'original_terminal': item['terminal']} == fact), 'Original safety slot/facts/source status changed')
        require(set(fact.get('evidence', {})) == set(EVIDENCE) | {'specialized'} and set(fact.get('executions', {})) == EXECUTIONS, 'Original 5 executions/12 evidence incomplete')
        started_path = ctx.audit / (trial['id'] + '.started.json')
        started = read_small(started_path)
        require(started.get('trial') == trial and started.get('registry') == binding(ctx.audit / 'registry.json') and (started.get('source_binding') == before['source']), 'Original safety started marker changed')
        commands = {'flight': trial['flight_command'], **safety_evaluations(ctx, trial)}
        require(set(row.get('executions', {})) == EXECUTIONS, 'Original outer execution receipt denominator differs')
        for kind, command in commands.items():
            receipt = row['executions'][kind]
            require(Path(receipt['path']) == ctx.audit / (trial['id'] + '_' + kind + '.outer_execution.json'), 'Original outer execution receipt path substituted')
            original_execution(receipt, command)
        require(slot_facts(row, registry) == row['execution_facts'], 'Original safety execution ledgers/evidence changed')
        safety_runtime(ctx, runner, plan, trial, review, modules['humble33_diagnostic_checks01'])
        records.append({'terminal': item['terminal'], 'started': binding(started_path), 'executions': {kind: {key: row['executions'][kind][key] for key in ('path', 'sha256')} for kind in sorted(EXECUTIONS)}})
    observer = owner.validate_observer_root(terminal.get('observer_owner_terminal'), ctx.audit / 'observer_driver', ctx.root)
    require(observer == terminal.get('observer'), 'Original safety observer binding differs')
    guard = frozen_guard(ctx)
    checked_at = datetime.now(timezone.utc)
    context = SimpleNamespace(core=plan, development=plan, development_path=ctx.core.resolve(strict=True), gate_bindings=frozen_bindings(ctx, plan), registration_times=[checked_at, checked_at])
    guard.validate_safety({'safety': binding(summary_path)}, context, SimpleNamespace(v4=runner))
    require(not runner.simulation_processes(), 'Residual runtime after actual safety validation')
    return {'registry': binding(ctx.audit / 'registry.json'), 'terminal': binding(terminal_path), 'facts': binding(facts_path), 'development_validation_summary': binding(summary_path), 'core_plan': {**binding(ctx.core), 'plan_sha256': plan['plan_sha256']}, 'records': records, 'observer': observer, 'frozen_guard': binding(ctx.root / 'tools/reliability_v4_guard.py'), 'all_four_original_pass': True, 'formal_seed_use_authorized': False}


def require_completed_safety(ctx, review, built, runner, core_plan=None, core_plan_path=None, *, admission_path=None, admission_sha256=None):
    """Recheck the full frozen guard and preserve its original actual outcome."""
    validation_path = ctx.audit / 'development_guard_validation.json'
    validation = read_small(validation_path)
    require(validation.get('scope') == 'INDEPENDENT_FROZEN_SAFETY_GUARD_DEVELOPMENT_RECHECK' and validation.get('result') == 'PASS' and (validation.get('error') is None) and (validation.get('formal_seed_use_authorized') is False) and (validation.get('summary') == binding(ctx.audit / 'development_validation_summary.json')), 'Original independent frozen safety-guard validation is missing or failed; no retry promotion')
    result = _validate_completed_safety_evidence(ctx, review, built, runner, core_plan, core_plan_path, admission_path=admission_path, admission_sha256=admission_sha256)
    require(validation.get('actual_evidence_bindings') == result, 'Original guard-validated evidence bindings changed')
    return {**result, 'independent_guard_validation': binding(validation_path)}


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('action',choices=('describe','register','run'))
    result.add_argument('--manifest',type=Path)
    result.add_argument('--manifest-sha256')
    result.add_argument('--core-contract',type=Path)
    result.add_argument('--core-contract-sha256')
    result.add_argument('--reviewed-tools-sha256')
    result.add_argument('--registry-sha256')
    return result


def reviewed_candidate(args):
    require(args.action in ('register','run') and generic.valid_sha(args.reviewed_tools_sha256)
        and canonical(tool_manifest()) == args.reviewed_tools_sha256, 'Explicit independently reviewed safety tools required')
    require(args.core_contract is not None and generic.valid_sha(args.core_contract_sha256), 'Explicit separately reviewed actual core runtime contract required')
    require(args.action != 'run' or generic.valid_sha(args.registry_sha256), 'Run requires the separately reviewed prospective registry SHA')
    return development.load_candidate(args.manifest,args.manifest_sha256)


def shell_root(argv):
    candidate,_=reviewed_candidate(parser().parse_args(argv))
    return candidate['frozen_root']


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.action=='describe':
            manifest=tool_manifest()
            print(json.dumps({'status':'PENDING_INDEPENDENT_TOOL_REVIEW','tool_manifest':manifest,
                'tools_canonical_sha256':canonical(manifest),'actual_action_executed':False},indent=2))
            return 0
        candidate,review=reviewed_candidate(args)
        generic.require_linux()
        modules=stable.dependencies()
        with generic.exclusive_window(),stable.stop_signals():
            built=stable.checked_build(candidate,review,modules['humble33_diagnostic_checks01'])
            runtime=development.require_runtime(candidate,review,modules['humble33_diagnostic_checks01'])
            built['_resource_runtime_binding']=runtime['runtime_contracts']['resource']
            runner=generic.runner_at(candidate['frozen_root'])
            ctx=Context(candidate,review,built,runner,modules,runtime,args.core_contract,args.core_contract_sha256,args.reviewed_tools_sha256,args.registry_sha256)
            if args.action=='register':
                return register_safety(ctx,review,built,runner)
            return run_safety(ctx,args,review,built,runner,modules)
    except (OSError,ValueError,RuntimeError,KeyError,IndexError,StopIteration,subprocess.SubprocessError) as error:
        print(json.dumps({'status':'DEVELOPMENT_SAFETY_REFUSED_OR_FAILED','reason':type(error).__name__+':'+str(error),
            **{k:False for k in development.FALSE_FIELDS}}),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
