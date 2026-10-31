"""Pure/mock Humble41 core controls; no ROS, WSL, source planning or payload."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import matrix_runner41 as m


def fixture(kind='core'):
    dimensions = m.GROUPS
    trials = []
    for cls in m.CLASSES:
        car = cls == 'car'
        for cell in dimensions:
            group = ('stage1_position' if cell == 'speed_changes_position' else 'stage1_velocity') if kind == 'extension' else cell
            identifier = f'{cls}_extension_{cell}_seed004' if kind == 'extension' else f'{cls}_{cell}_seed004'
            trial = {'id': identifier, 'target_class': cls, 'seed': 4, 'group': group,
                'stage': 1 if group.startswith('stage1_') else 2 if group == 'stage2_crossing' else 3,
                'multi_target': group == 'stage3_multi_active', 'duration_s': 75., 'wall_timeout_s': 1000.,
                'model': 'models/yolo11m_car_sim_train20_04.pt' if car else 'models/yolo11n.pt',
                'inference_image_size': 640 if car else 320, 'inference_threads': 4 if car else 2,
                'desired_distance_m': (12. if car else 7.) if kind == 'extension' and cell == 'far_distance' else (9. if car else 5.),
                m.source.PACING_FIELD: deepcopy(m.source.EXPECTED_PACING_V2), m.source.ADAPTER_FIELD: 50.,
                'flight_command': ['original', identifier, m.source.ADAPTER_FLAG, '50.0'],
                'evaluations': [], 'directory': '/synthetic/'+identifier}
            if car:
                trial[m.source.EXCLUSIVE_FIELD] = True
                trial['flight_command'].append(m.source.EXCLUSIVE_FLAG)
            if kind == 'extension': trial['extension_condition'] = cell
            trials.append(trial)
    result = {'mode': 'EXTENSION_PROBE' if kind == 'extension' else 'PROBE', 'prefix': m.PREFIXES[kind],
        'frozen_root': m.ROOT, 'output': str(m.locations(kind)['output']),
        'selected_classes': list(m.CLASSES), 'selected_seeds': [4],
        'selected_groups': ['stage1_velocity', 'stage1_position'] if kind == 'extension' else list(m.GROUPS),
        'protocol': {m.source.PACING_FIELD: deepcopy(m.source.EXPECTED_PACING_V2),
            'resources': {'car': {m.source.EXCLUSIVE_FIELD: True}, 'person': {}}},
        'trials': trials, 'trial_timeout_s': 2800., 'postprocessing_timeout_s': 1800., 'evaluation_timeout_s': 1800.,
        'plan_sha256': 'synthetic_plan'}
    if kind == 'extension': result['selected_extension_conditions'] = list(m.CONDITIONS)
    return result


def runner_fixture():
    return SimpleNamespace(validate_plan=Mock(), SIMULATION_PACING_V2=deepcopy(m.source.EXPECTED_PACING_V2),
        simulation_pacing_declared=Mock(return_value=True),
        simulation_pacing_trial_binding=Mock(return_value=deepcopy(m.source.EXPECTED_PACING_V2)),
        correlated_two_face_trial_binding=lambda p, t: (t['target_class'] == 'car', t['target_class'] == 'car'),
        car_surface_recovery_declared=Mock(return_value=True),
        car_surface_recovery_trial_binding=lambda p, t: (t['target_class'] == 'car', t['target_class'] == 'car'),
        exclusive_navigation_declared=Mock(return_value=True),
        exclusive_navigation_summary=lambda p: {'car': True, 'person': False},
        exclusive_navigation_trial_binding=lambda p, t: (t['target_class'] == 'car', t['target_class'] == 'car'))



class MatrixControls(unittest.TestCase):
    def test_manifest_has_same_source_pressure_and_new_explicit_owner(self):
        manifest = m.tool_manifest()
        self.assertEqual(manifest['source41_tools_canonical_sha256'], m.canonical(m.source.tool_manifest()))
        self.assertFalse(manifest['single_car_probe_required'])
        self.assertFalse(manifest['driver_acquires_machine_sitl_lock'])
        self.assertFalse(manifest['flight_or_evaluator_argv_modified'])
        self.assertEqual(manifest['maximum_new_trials_per_normal_runner_call'], 1)
        self.assertIsNone(manifest['default_real_contract'])
        self.assertEqual(manifest['observer_archive_wall_budget_s'], 1800.)

    def test_missing_pressure_prevents_any_plan_or_driver_creation(self):
        with tempfile.TemporaryDirectory(prefix='matrix41_pressure_gate_fake_') as temporary:
            base = Path(temporary)
            selected = {'output': base/'matrix', 'plan_driver': base/'driver', 'pending_contract': base/'pending.json'}
            runner = SimpleNamespace(simulation_processes=Mock(return_value=[]), make_plan=Mock())
            with patch.object(m, 'locations', return_value=selected), \
                patch.object(m, 'require_completed_pressure', side_effect=ValueError('Actual pressure absent')), \
                patch.object(m, 'entry_binding') as entry, patch.object(m, 'write_new') as written:
                self.assertRaisesRegex(ValueError, 'pressure absent', m.plan_matrix, 'core', None, {}, {}, runner, {}, {}, {})
                runner.make_plan.assert_not_called(); entry.assert_not_called(); written.assert_not_called()
                self.assertFalse(selected['plan_driver'].exists())

    def test_owner_finish_result_is_embedded_and_validator_never_receives_none(self):
        actual_owner = {'actual_post_wait': True}
        observer = SimpleNamespace(_finished=actual_owner)
        runner = SimpleNamespace(simulation_processes=lambda: [])
        observed = {'native_and_archive_both_verified': True, 'owner_terminal': actual_owner}
        with patch.object(m, 'entry_binding', return_value={'source': True}), \
            patch.object(m.owner, 'validate_observer_root', return_value=observed) as owner_validator, \
            patch.object(m.stable, 'validate_observer_root', side_effect=AssertionError('Old validator must stay unchanged')):
            result = m.finish_action({}, {}, runner, observer, Path('/fixture'), {})
            self.assertIs(result['observer_owner_terminal'], actual_owner)
            self.assertIs(result['observer'], observed)
            self.assertEqual(result['final_errors'], [])
            owner_validator.assert_called_once_with(actual_owner, Path('/fixture/observer_driver'), m.ROOT)

    def test_new_owner_creation_keeps_original_archive_budget(self):
        with patch.object(m.owner, 'make_observer', return_value='original_new_owner') as made, \
            patch.object(m.stable, 'observer_types', side_effect=AssertionError('No old owner')):
            self.assertEqual(m.make_observer({}, Path('/fixture')), 'original_new_owner')
        made.assert_called_once_with(Path('/fixture/observer_driver'), m.ROOT, archive_wall_budget_s=1800.)




    def test_missing_explicit_review_or_contract_refuses_before_any_action(self):
        with patch.object(m, 'write_new') as written, patch.object(m.subprocess, 'Popen') as spawned, \
            patch.object(m.stable, 'dependencies') as deps, redirect_stderr(io.StringIO()):
            for action in ('plan-core', 'run-core'):
                self.assertEqual(m.main([action]), 2)
        written.assert_not_called(); spawned.assert_not_called(); deps.assert_not_called()


    def test_complete_core_matrix_preserve_every_spec(self):
        for kind, count in (('core', 12),):
            plan = fixture(kind); before = deepcopy(plan)
            self.assertIs(m.validate_matrix(plan, runner_fixture(), kind), plan)
            self.assertEqual(len(plan['trials']), count)
            self.assertEqual(plan, before)


    def test_incomplete_duplicated_reordered_formal_or_foreign_matrix_cannot_pass(self):
        for kind in ('core',):
            variants = []
            for key, value in (('mode', 'FORMAL'), ('selected_seeds', [True]), ('selected_seeds', [1000]),
                ('selected_classes', ['car']), ('frozen_root', '/root/foreign'), ('trial_timeout_s', 2400.)):
                changed = fixture(kind); changed[key] = value; variants.append(changed)
            changed = fixture(kind); changed['trials'].pop(); variants.append(changed)
            changed = fixture(kind); changed['trials'][1] = deepcopy(changed['trials'][0]); variants.append(changed)
            changed = fixture(kind); changed['trials'].reverse(); variants.append(changed)
            for plan in variants:
                self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), kind)


    def test_v2_spec_and_original_adapter_flag_are_required_for_both_classes(self):
        for index in (0, 6):
            for field, value in ((m.source.ADAPTER_FIELD, True), (m.source.ADAPTER_FIELD, 20.),
                ('inference_threads', 1), ('desired_distance_m', 99.), ('duration_s', 20.)):
                plan = fixture(); plan['trials'][index][field] = value
                self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), 'core')
            for command in ([], ['original', m.source.ADAPTER_FLAG],
                ['original', m.source.ADAPTER_FLAG, '20'], ['original', m.source.ADAPTER_FLAG, 'nan'],
                ['original', m.source.ADAPTER_FLAG+'=50'],
                ['original', m.source.ADAPTER_FLAG, '50', m.source.ADAPTER_FLAG, '50']):
                plan = fixture(); plan['trials'][index]['flight_command'] = command
                self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), 'core')
            plan = fixture(); plan['trials'][index][m.source.PACING_FIELD].pop(m.source.ADAPTER_FIELD)
            self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), 'core')
        plan = fixture(); plan['protocol'][m.source.PACING_FIELD]['safety_source_time_gates'] = 'modified'
        self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), 'core')


    def test_person_cannot_inherit_car_surface_recovery(self):
        runner = runner_fixture()
        runner.car_surface_recovery_trial_binding = Mock(return_value=(True, True))
        self.assertRaises(ValueError, m.validate_matrix, fixture(), runner, 'core')

    def test_actual_runtime_birth_policy_cannot_hide_behind_accepting_normal_runner(self):
        plan = fixture(); runner = runner_fixture()
        for index in (0, 6):
            trial = plan['trials'][index]
            car = trial['target_class'] == 'car'
            runner.exclusive_navigation_runtime_evidence = Mock(return_value={'enabled': car, 'explicit': car, 'errors': []})
            configuration = {'car_surface_recovery': car}
            parameters = {
                'uav_tracking_detection': {'ros__parameters': {'car_surface_recovery_enabled': car}},
                'uav_tracking_state_estimator': {'ros__parameters': {'supported_birth_confirmation_required': car}}}
            result = m.validate_exclusive_runtime(plan, trial, configuration, parameters, runner)
            self.assertEqual(result['supported_birth_confirmation']['target_class'], trial['target_class'])
            for node, field in (('uav_tracking_detection', 'car_surface_recovery_enabled'),
                ('uav_tracking_state_estimator', 'supported_birth_confirmation_required')):
                for bad in (None, not car, int(car), str(car)):
                    changed = deepcopy(parameters)
                    if bad is None: changed[node]['ros__parameters'].pop(field)
                    else: changed[node]['ros__parameters'][field] = bad
                    with self.subTest(target_class=trial['target_class'], node=node, bad=bad):
                        self.assertRaises(ValueError, m.validate_exclusive_runtime,
                            plan, trial, configuration, changed, runner)


    def test_normal_runner_receives_original_command_one_attempt_and_no_outer_lock(self):
        command = ['original', '--unchanged']
        log, cwd, timeout = Path('/fixture/log'), Path(m.ROOT), 2800.
        def normal(plan, *, max_new_trials, command_runner):
            self.assertEqual(max_new_trials, 1)
            return command_runner(command, log, cwd, timeout)
        runner = SimpleNamespace(run_plan=normal, run_lock=Mock(side_effect=AssertionError('No outer SITL lock')))
        observer, receipt = object(), {'returncode': 0}
        with patch.object(m.stable, 'execute_owned', return_value=receipt) as executed:
            self.assertIs(m.observed_run_plan(runner, fixture(), observer), receipt)
        executed.assert_called_once_with(command, log, observer, timeout, cwd)
        runner.run_lock.assert_not_called()


    def test_actual_build_failure_prevents_runtime_plan_or_driver_creation(self):
        @contextmanager
        def window(): yield
        with patch.object(m, 'reviewed_source', return_value={}), patch.object(m.generic, 'require_linux'), \
            patch.object(m.stable, 'dependencies', return_value={'humble33_diagnostic_checks01': object()}), \
            patch.object(m.generic, 'exclusive_window', window), patch.object(m.stable, 'stop_signals', window), \
            patch.object(m.source, 'build_evidence', return_value={}), \
            patch.object(m.stable, 'checked_build', side_effect=ValueError('No actual build')), \
            patch.object(m, 'require_runtime') as runtime, patch.object(m, 'plan_matrix') as planned, \
            patch.object(m, 'write_new') as written, redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(['plan-core']), 2)
        runtime.assert_not_called(); planned.assert_not_called(); written.assert_not_called()


    def test_pending_or_old_contract_cannot_read_a_matrix_or_start_process(self):
        with tempfile.TemporaryDirectory(prefix='matrix41_pending_control_') as directory:
            base = Path(directory)
            pending = base/'matrix_runner41_contract_core_pending01.json'
            pending.write_text(json.dumps({'schema_version': 1, 'scope': m.SCOPE, 'status': m.PENDING}), encoding='utf-8')
            old = base/'car_surface_probe36_contract_final01.json'; old.write_text('{}', encoding='utf-8')
            with patch.object(m, 'EXTERNAL', base), patch.object(m, 'checked_plan') as checked, \
                patch.object(m.subprocess, 'Popen') as spawned, patch.object(m, 'write_new') as written:
                for path in (pending, old):
                    self.assertRaises(ValueError, m.load_contract, 'core', path, m.sha(path), object(), {}, {}, object(), {})
            checked.assert_not_called(); spawned.assert_not_called(); written.assert_not_called()


    def test_actual_report_and_command_drift_cannot_hide_behind_an_ordinary_fail(self):
        plan = fixture(); trial = plan['trials'][0]
        trial['evaluations'] = [{'kind': kind, 'command': ['original_evaluator', kind]}
            for kind in ('source_clock', 'native_startup')]
        original_entries = [{'kind': spec['kind'], 'result': 'PASS', 'report_sha256': 'b'*64,
            'execution': {'command': spec['command'], 'returncode': 0, 'error': None}} for spec in trial['evaluations']]
        checks = SimpleNamespace(require_completed_record=Mock(return_value={'record': True}),
            bridge_evidence=Mock(return_value={}), process_evidence=Mock(return_value={}), closed75_archive=Mock(return_value={}))
        for change in (None, 'evaluator_argv', 'report_sha', 'source_clock_fail', 'flight_argv'):
            record = {'status': 'FAIL', 'engineering_result': 'FAIL', 'evaluations': deepcopy(original_entries),
                'commands': [{'kind': 'flight', 'command': trial['flight_command'], 'returncode': 0, 'error': None}]}
            current = deepcopy(record['evaluations'])
            if change == 'evaluator_argv': record['evaluations'][0]['execution']['command'] = ['replacement']
            if change == 'report_sha': current[0]['report_sha256'] = 'c'*64
            if change == 'source_clock_fail':
                current[0]['result'] = record['evaluations'][0]['result'] = 'FAIL'
            if change == 'flight_argv': record['commands'][0]['command'] = ['replacement']
            runner = SimpleNamespace(runtime_configuration=Mock(return_value={'errors': []}),
                read_evaluation=lambda spec, execution, plan: next(row for row in current if row['kind'] == spec['kind']),
                engineering_verdict=Mock(return_value=('FAIL', {})))
            with self.subTest(change=change), patch.object(m, 'exclusive_runtime_archive', return_value={'actual_archive': True}):
                if change is None:
                    result = m.audit_record(runner, plan, trial, record, {}, checks)
                    self.assertEqual(result['record_binding'], {'record': True})
                else:
                    self.assertRaises(ValueError, m.audit_record, runner, plan, trial, record, {}, checks)
                    runner.engineering_verdict.assert_not_called()


    def test_car_only_exclusive_policy_is_bound_in_all_12_specs(self):
        for kind in ('core',):
            for index in (0, 6 if kind == 'core' else 8):
                original = fixture(kind)
                mutations = []
                changed = deepcopy(original); changed['trials'][index][m.source.EXCLUSIVE_FIELD] = 1; mutations.append(changed)
                changed = deepcopy(original); changed['trials'][index]['flight_command'].append(m.source.EXCLUSIVE_FLAG); mutations.append(changed)
                changed = deepcopy(original); changed['trials'][index]['flight_command'].append(m.source.EXCLUSIVE_FLAG+'=true'); mutations.append(changed)
                changed = deepcopy(original); changed['protocol']['resources']['car'][m.source.EXCLUSIVE_FIELD] = False; mutations.append(changed)
                changed = deepcopy(original); changed['protocol']['resources']['person'][m.source.EXCLUSIVE_FIELD] = False; mutations.append(changed)
                for plan in mutations:
                    self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), kind)



class BatchControls(unittest.TestCase):
    def run_batch(self, infrastructure_at=None, preexisting=False, source_drift=False, check_admission=False,
                  pressure_drift_after_first=False):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory(prefix='matrix41_batch_mock_') as temporary, ExitStack() as stack:
            base = Path(temporary)
            plan = fixture()
            selected = {'output': base/'matrix', 'plan': base/'matrix/plan.json',
                'run_driver': base/'matrix/observed_driver01', 'plan_driver': base/'plan_driver',
                'pending_contract': base/'pending.json'}
            selected['output'].mkdir(); selected['plan'].write_text('{}', encoding='utf-8')
            plan['output'] = str(selected['output'])
            records = {trial['id']: {'id': trial['id'], 'status': 'PENDING'} for trial in plan['trials']}
            if preexisting: records[plan['trials'][0]['id']]['status'] = 'FAIL'
            calls, commands = [], []
            def binding(runner, plan, trial, record):
                return {'slot': trial['id'], 'record_sha256': 'synthetic_'+trial['id'], 'status': record['status']}
            checks = SimpleNamespace(terminal_binding=binding)
            modules = {'humble33_diagnostic_checks01': checks, 'humble33_development_observer01': object()}
            def execute(command, log, observer, timeout, cwd):
                commands.append(command)
                return {'command': command, 'returncode': 0, 'error': None}
            def normal(plan, *, max_new_trials, command_runner):
                self.assertEqual(max_new_trials, 1)
                trial = next(t for t in plan['trials'] if records[t['id']]['status'] == 'PENDING')
                index = len(calls); calls.append(trial['id'])
                command_runner(trial['flight_command'], base/'log', Path(m.ROOT), 2800.)
                bad = index == infrastructure_at
                records[trial['id']] = {'id': trial['id'], 'status': 'INFRASTRUCTURE_ERROR' if bad else 'FAIL',
                    'engineering_result': 'FAIL', 'record_sha256': 'synthetic_'+trial['id']}
                return {'started_this_invocation': 1}
            runner = SimpleNamespace(run_plan=normal, simulation_processes=lambda: [],
                verify_sources=lambda p: None, read_slots=lambda p: records,
                run_lock=Mock(side_effect=AssertionError('No outer lock')))
            class Observer:
                _finished = None
                def __enter__(self): return self
                def __exit__(self, *args): self._finished = {}; return False
                def check(self): return {'pure_fixture_fresh': True}
            source = {'same_source': True}
            entries = [0]
            def entry(*args):
                entries[0] += 1
                return source if not source_drift or entries[0] <= 3 else {'changed': True}
            def audit(runner, plan, trial, record, review, checks, **kwargs):
                if record['status'] == 'INFRASTRUCTURE_ERROR': raise ValueError('Original infrastructure stop')
                return {'record_binding': binding(runner, plan, trial, record)}
            plan_binding = {'path': str(selected['plan']), 'sha256': 'c'*64}
            prerequisites = {'same_source_pressure': 'PASS'}
            contract = {'plan_pending': {'plan': plan_binding}, 'prerequisites': prerequisites}
            def prerequisite(*args):
                if pressure_drift_after_first and calls:
                    raise ValueError('Pressure changed before next slot')
                return prerequisites
            patches = {
                'locations': lambda kind: selected, 'load_contract': lambda *a: (contract, plan),
                'checked_plan': lambda *a, **k: plan, 'entry_binding': entry,
                'require_prerequisites': prerequisite, 'make_observer': lambda *a: Observer(),
                'audit_record': audit, 'sha': lambda path: 'a'*64,
                'finish_action': lambda *a: {'entry_binding_after': source, 'cleanup': {'residual_processes': []},
                    'observer': {'fixture_observer': True}, 'observer_owner_terminal': {'actual_owner': True}, 'final_errors': []},
            }
            for name, value in patches.items(): stack.enter_context(patch.object(m, name, value))
            stack.enter_context(patch.object(m.stable, 'execute_owned', side_effect=execute))
            stack.enter_context(patch.object(m.stable, 'metadata_binding',
                side_effect=lambda path, **kwargs: {'path': str(path), 'sha256': 'c'*64}))
            stack.enter_context(patch.object(m.stable, 'dependencies', return_value=modules))
            stack.enter_context(patch.object(m.owner, 'validate_observer_root', return_value={'fixture_observer': True}))
            args = SimpleNamespace(contract=base/'final_contract.json', contract_sha256='a'*64, safety_tools_sha256=None)
            with redirect_stdout(io.StringIO()):
                if preexisting:
                    self.assertRaises(ValueError, m.run_matrix, 'core', args, {}, {}, runner, modules, {})
                    self.assertFalse(selected['run_driver'].exists())
                    self.assertEqual(calls, [])
                    return
                code = m.run_matrix('core', args, {}, {}, runner, modules, {})
            terminal = json.loads((selected['run_driver']/'execution_terminal.json').read_text(encoding='utf-8'))
            if check_admission:
                accepted = m.require_completed_core({}, {}, runner, all_pass=False)
                self.assertEqual(accepted['completed_count'], 12)
                self.assertFalse(accepted['all_original_core_cells_pass'])
                self.assertRaises(ValueError, m.require_completed_core, {}, {}, runner, all_pass=True)
            runner.run_lock.assert_not_called()
            self.assertEqual(commands, [next(t['flight_command'] for t in plan['trials'] if t['id'] == identifier) for identifier in calls])
            return code, terminal, calls

    def test_all12_algorithm_failures_remain_in_denominator_without_retry(self):
        code, terminal, calls = self.run_batch(check_admission=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 12)
        self.assertEqual(terminal['status_counts'], {'FAIL': 12})
        self.assertEqual(terminal['terminal_count'], 12)
        self.assertFalse(terminal['readiness_claimed'])

    def test_infrastructure_attempt_is_retained_and_stops_before_next_slot(self):
        code, terminal, calls = self.run_batch(infrastructure_at=2)
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 3)
        self.assertEqual(terminal['attempt_count'], 3)
        self.assertEqual(terminal['terminal_count'], 2)
        self.assertEqual(terminal['status_counts'], {'FAIL': 2, 'INFRASTRUCTURE_ERROR': 1, 'PENDING': 9})
        self.assertEqual(terminal['attempts'][-1]['record']['status'], 'INFRASTRUCTURE_ERROR')
        self.assertIsNotNone(terminal['attempts'][-1]['error'])

    def test_source_drift_stops_before_new_attempt(self):
        code, terminal, calls = self.run_batch(source_drift=True)
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(terminal['status_counts'], {'FAIL': 1, 'PENDING': 11})

    def test_pressure_drift_is_rechecked_and_stops_before_second_flight(self):
        code, terminal, calls = self.run_batch(pressure_drift_after_first=True)
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(terminal['status_counts'], {'FAIL': 1, 'PENDING': 11})
        self.assertIn('Pressure changed', terminal['error'])

    def test_preexisting_original_slot_refuses_fresh_batch_without_resume(self):
        self.run_batch(preexisting=True)



class ReleaseControls(unittest.TestCase):
    def test_describe_resolves_source_manifest_and_never_enters_runtime(self):
        with patch.object(m, 'reviewed_source') as review, patch.object(m.stable, 'dependencies') as deps, \
            patch.object(m, 'write_new') as written, patch.object(m.subprocess, 'Popen') as spawned, \
            redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.main(['describe']), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value['tools_canonical_sha256'], m.canonical(m.tool_manifest()))
        self.assertEqual(value['tool_manifest']['source41_tools_canonical_sha256'],
                         m.canonical(m.source.tool_manifest()))
        self.assertIn('test_matrix_runner41.py', value['tool_manifest']['files'])
        self.assertEqual(value['core_driver'], 'observed_driver01')
        self.assertFalse(value['actual_action_executed'])
        self.assertFalse(value['resume_or_recovery_authorized'])
        for mocked in (review, deps, written, spawned):
            mocked.assert_not_called()

    def test_unsupported_extension_is_not_exposed_by_parser_or_locations(self):
        with redirect_stderr(io.StringIO()):
            self.assertRaises(SystemExit, m.parser().parse_args, ['plan-extension'])
        self.assertRaises(ValueError, m.locations, 'extension')

    def test_same_physical_file_alias_passes_but_byte_identical_copy_does_not(self):
        with tempfile.TemporaryDirectory(prefix='matrix41_alias_fake_') as directory:
            root = Path(directory)
            original, alias, copied = root/'plan.json', root/'alias.json', root/'copy.json'
            original.write_text('{}', encoding='utf-8')
            os.link(original, alias)
            copied.write_bytes(original.read_bytes())
            expected = m.stable.metadata_binding(original, json_only=True)
            observed = m.stable.metadata_binding(alias, json_only=True)
            self.assertNotEqual(observed['path'], expected['path'])
            m.require_same_metadata_file(observed, expected)
            self.assertRaises(ValueError, m.require_same_metadata_file,
                              m.stable.metadata_binding(copied, json_only=True), expected)
            alias.write_text('{"changed":true}', encoding='utf-8')
            self.assertRaises(ValueError, m.require_same_metadata_file,
                              m.stable.metadata_binding(alias, json_only=True), expected)

    def test_review_arguments_and_missing_contract_refuse_before_loading_source(self):
        with patch.object(m.generic, 'load_review') as loaded:
            args = m.parser().parse_args(['plan-core', '--frozen-root', m.ROOT,
                '--review-sha256', 'a'*64, '--reviewed-tools-sha256', m.canonical(m.tool_manifest())])
            self.assertRaises(ValueError, m.reviewed_source, args)
            args.review = Path('/synthetic/review.json')
            args.action = 'run-core'
            self.assertRaisesRegex(ValueError, 'contract', m.reviewed_source, args)
        loaded.assert_not_called()

    def test_final_fake_contract_binds_source_driver_plan_and_forbids_recovery(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory(prefix='matrix41_contract_fake_') as directory, ExitStack() as stack:
            root = Path(directory)
            selected = {'output': root/'matrix', 'plan': root/'matrix/plan.json',
                'run_driver': root/'matrix/observed_driver01', 'plan_driver': root/'plan_driver',
                'pending_contract': root/'matrix_runner41_contract_core_pending01.json'}
            selected['output'].mkdir(); selected['plan_driver'].mkdir()
            plan = fixture(); plan['output'] = str(selected['output'])
            selected['plan'].write_text(json.dumps(plan), encoding='utf-8')
            initial = m.pending_identity(plan)
            source = {'source': 'synthetic reviewed source'}
            review = {'_review_binding': {'path': '/synthetic/review.json', 'sha256': 'a'*64}}
            build, manifest = {'summary': 'synthetic build'}, {'tools': 'synthetic manifest'}
            terminal = {'scope': m.SCOPE, 'action': 'plan', 'matrix_kind': 'core',
                'returncode': 0, 'error': None, 'initial_pending': initial, 'flights_started': 0,
                'entry_binding_before': source, 'entry_binding_after': source,
                'prerequisites': None, 'observer_owner_terminal': {'actual_owner': True}, 'observer': {}, 'final_errors': [], 'cleanup': {'residual_processes': []}}
            terminal_path = selected['plan_driver']/'execution_terminal.json'
            terminal_path.write_text(json.dumps(terminal), encoding='utf-8')
            value = {'schema_version': 1, 'scope': m.SCOPE, 'status': m.FINAL, 'matrix_kind': 'core',
                'frozen_root': m.ROOT, 'source_review': review['_review_binding'], 'entry_binding': source,
                'tools_canonical_sha256': m.canonical(manifest), 'build_evidence': build,
                'plan_pending': initial, 'plan_terminal': m.stable.metadata_binding(terminal_path, json_only=True),
                'prerequisites': None, 'experiment': {'classes': list(m.CLASSES), 'seed': 4,
                    'duration_s': 75., 'flight_count': 12},
                **{key: False for key in ('formal_seed_use_authorized', 'readiness_claimed',
                                         'automatic_retry', 'automatic_next_action')}}
            path = root/'matrix_runner41_contract_core_final_fake.json'
            stack.enter_context(patch.object(m, 'EXTERNAL', root))
            stack.enter_context(patch.object(m, 'locations', return_value=selected))
            stack.enter_context(patch.object(m, 'checked_plan', return_value=plan))
            stack.enter_context(patch.object(m, 'entry_binding', return_value=source))
            stack.enter_context(patch.object(m, 'tool_manifest', return_value=manifest))
            stack.enter_context(patch.object(m.source, 'build_evidence', return_value=build))
            stack.enter_context(patch.object(m, 'require_prerequisites', return_value=None))
            stack.enter_context(patch.object(m.owner, 'validate_observer_root', return_value={}))
            for defect in (None, 'source', 'entry', 'build', 'plan', 'driver', 'recovery'):
                changed = deepcopy(value)
                terminal_path.write_text(json.dumps(terminal), encoding='utf-8')
                if defect == 'source': changed['source_review']['sha256'] = 'f'*64
                elif defect == 'entry': changed['entry_binding'] = {'changed': True}
                elif defect == 'build': changed['build_evidence'] = {'changed': True}
                elif defect == 'plan': changed['plan_pending']['plan_sha256'] = 'changed'
                elif defect == 'driver':
                    wrong = deepcopy(terminal); wrong['flights_started'] = 1
                    terminal_path.write_text(json.dumps(wrong), encoding='utf-8')
                    changed['plan_terminal'] = m.stable.metadata_binding(terminal_path, json_only=True)
                elif defect == 'recovery': changed['zero_attempt_recovery'] = {}
                path.write_text(json.dumps(changed), encoding='utf-8')
                with self.subTest(defect=defect):
                    if defect is None:
                        actual, actual_plan = m.load_contract('core', path, m.sha(path),
                            SimpleNamespace(), review, {}, object(), {'humble33_development_observer01': object()})
                        self.assertEqual(actual, value)
                        self.assertIs(actual_plan, plan)
                    else:
                        self.assertRaises(ValueError, m.load_contract, 'core', path, m.sha(path),
                            SimpleNamespace(), review, {}, object(), {'humble33_development_observer01': object()})


class PressureAdmission(unittest.TestCase):
    def scenario(self, mutation=None, *, owner_failure=False):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory(prefix='matrix41_pressure_fake_') as temporary, ExitStack() as stack:
            root = Path(temporary)
            directory = root/'results/freeze_validation/observer_archive_pressure01'
            directory.mkdir(parents=True)
            (directory/'rosbag').mkdir()
            (root/'scripts').mkdir()
            collector = root/'scripts/observe_runtime_health.py'; collector.write_text('fixture', encoding='utf-8')
            (directory/'rosbag/metadata.yaml').write_text('fixture metadata', encoding='utf-8')
            original = root/'uav_tracking_bag_spool/trial_original'
            original.mkdir(parents=True)
            owner_json = {'trial': 'retained original40 trial'}
            (original/'owned_spool.json').write_text(json.dumps(owner_json), encoding='utf-8')
            old_slot = root/'original40.json'
            old_slot.write_text(json.dumps({'status': 'INFRASTRUCTURE_ERROR', 'infrastructure_stop': True}), encoding='utf-8')
            clone = original.parent/'trial_new_owned'
            local = Path('/dev/shm/uav_tracking_root41_pressure_fixture')
            external = root/'external'; external.mkdir()
            summary_path = root/'summary.json'; summary_path.write_text('{}', encoding='utf-8')
            summary = m.stable.metadata_binding(summary_path, json_only=True)
            collector_sha = m.sha(collector)
            review = {'frozen_root': str(root), 'files': {'scripts/observe_runtime_health.py': collector_sha}}
            built = {'bound_build_metadata': {'summary': summary}}
            actual_owner = {'original_actual_post_wait_outcome': True}
            observed = {'native_and_archive_both_verified': True, 'owner_terminal': actual_owner}
            stat = {'retained_original40': {'bytes': 10, 'mtime_ns': 123, 'inode': 1, 'device': 2}}
            worker = {'status': 'PASS', 'original_spool': str(original), 'diagnostic_clone': str(clone),
                'original_attempt_regraded': False, 'total_wall_s': 10.,
                'result': {'status': 'PASS', 'source_spool': str(clone), 'destination': str(directory/'rosbag'),
                    'recorder_exit_code': 0, 'raw_validation': {'status': 'PASS'},
                    'native_reader_validation': {'status': 'PASS'},
                    'published_metadata_sha256': m.sha(directory/'rosbag/metadata.yaml')}}
            (directory/'archive_worker.json').write_text(json.dumps(worker), encoding='utf-8')
            (directory/'archive_worker_console.log').write_text('', encoding='utf-8')
            check = {'fresh': {'sample_age_wall_s': .2, 'max_sample_age_wall_s': 10.}, 'check_latency_wall_s': .01}
            (directory/'checks.jsonl').write_text(json.dumps(check)+'\n', encoding='utf-8')
            artifacts = {name: {'bytes': (directory/name).stat().st_size, 'sha256': m.sha(directory/name)}
                for name in ('archive_worker.json', 'archive_worker_console.log', 'checks.jsonl')}
            value = {'schema_version': 1, 'scope': 'ACTUAL_NO_SITL_ARCHIVE_PRESSURE_DIAGNOSTIC_ONLY',
                'root': str(root), 'status': 'PASS', 'error': None, 'original_spool': str(original),
                'source': {'script': m.PRESSURE_SHA, 'collector': collector_sha, 'owner': m.OWNER_SHA,
                    'build_summary': summary['sha256']},
                'original_attempt_status': 'INFRASTRUCTURE_ERROR_RETAINED', 'original_attempt_regraded': False,
                'no_simulator_started': True, 'formal_trials_executed': 0, 'pressure_workload_wall_budget_s': 2400.,
                'original_stat_unchanged': True, 'original_stat_before': stat, 'original_stat_after': stat,
                'cleanup_actions': [], 'worker_exit_code': 0, 'rosbag_published': True,
                'original_failed_slot': {'path': str(old_slot), 'sha256': m.sha(old_slot), 'status': 'INFRASTRUCTURE_ERROR'},
                'original_spool_owner': owner_json, 'diagnostic_clone': str(clone), 'local_evidence': str(local),
                'command': [m.sys.executable, '-B', str(external/'root_archive_observer41_pressure01.py'),
                    '--archive-worker', str(clone), str(directory/'rosbag'), str(local/'archive_worker.json')],
                'diagnostic_artifacts': artifacts, 'check_count': 1, 'max_observer_sample_age_wall_s': .2,
                'max_check_latency_wall_s': .01, 'observer': actual_owner, 'observer_validation': observed}
            if mutation is not None: mutation(value, directory, review, built)
            (directory/'execution_terminal.json').write_text(json.dumps(value), encoding='utf-8')
            for name, content in {'ROOT': str(root), 'EXTERNAL': external, 'ORIGINAL_SPOOL': str(original),
                'ORIGINAL_SLOT': str(old_slot), 'ORIGINAL_SLOT_SHA': m.sha(old_slot), 'COLLECTOR_SHA': collector_sha}.items():
                stack.enter_context(patch.object(m, name, content))
            stack.enter_context(patch.object(m.source, 'build_evidence', return_value={'summary': summary}))
            stack.enter_context(patch.object(m, 'retained_original_stat', return_value=stat))
            validator = stack.enter_context(patch.object(m.owner, 'validate_observer_root',
                side_effect=ValueError('Actual owner failure') if owner_failure else lambda actual, *a:
                    observed if actual == actual_owner else (_ for _ in ()).throw(ValueError('Missing actual owner result'))))
            result = m.require_completed_pressure(review, built)
            self.assertEqual(result['result'], 'PASS')
            self.assertFalse(result['original40_regraded'])
            validator.assert_called_once_with(actual_owner, directory/'observer_driver', str(root))
            return result

    def test_actual_complete_pressure_fixture_is_accepted_only_with_original_owner(self):
        self.scenario()

    def test_pass_label_cannot_replace_actual_pressure_evidence(self):
        defects = [
            lambda v, *a: v.update(status='FAIL'),
            lambda v, *a: v.update(original_stat_unchanged=False),
            lambda v, *a: v.update(original_attempt_regraded=True),
            lambda v, *a: v.update(cleanup_actions=['SIGINT']),
            lambda v, *a: v.update(no_simulator_started=False),
            lambda v, *a: v.update(formal_trials_executed=1),
            lambda v, *a: v.update(worker_exit_code=-2),
            lambda v, *a: v['source'].update(build_summary='f'*64),
            lambda v, *a: v['source'].update(owner='f'*64),
            lambda v, *a: v.update(original_failed_slot={}),
            lambda v, *a: v.update(original_stat_before={'changed': True}),
            lambda v, *a: v.update(observer=None),
            lambda v, *a: v.update(observer_validation={'invented_PASS': True}),
            lambda v, *a: v.update(check_count=2),
            lambda v, *a: v.update(max_observer_sample_age_wall_s=0.),
            lambda v, d, *a: (d/'archive_worker.json').write_text('{}', encoding='utf-8'),
            lambda v, d, *a: (d/'rosbag/metadata.yaml').write_text('changed', encoding='utf-8'),
        ]
        for number, defect in enumerate(defects):
            with self.subTest(defect=number):
                self.assertRaises(ValueError, self.scenario, defect)

    def test_native_or_archive_owner_failure_blocks_admission(self):
        self.assertRaisesRegex(ValueError, 'Actual owner failure', self.scenario, owner_failure=True)


if __name__ == "__main__": unittest.main()
