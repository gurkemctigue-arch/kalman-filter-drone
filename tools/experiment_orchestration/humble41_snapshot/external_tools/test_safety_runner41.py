"""Pure/source and temporary metadata checks; never WSL, flight or bag input."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import safety_runner41 as m

SOURCE = Path(os.environ.get('STAGE1_PROJECT_ROOT') or
    ('D:/基于yolo和卡尔曼滤波' if os.name == 'nt' else '/mnt/d/基于yolo和卡尔曼滤波'))
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))
from scripts import run_reliability_v4 as v4
from tools import reliability_v4_guard as guard

IDS = ['person_auto_unique_multi_seed004', 'person_locked_ambiguity_seed004',
       'car_auto_unique_multi_seed004', 'car_locked_ambiguity_seed004']
EXECUTIONS = {'flight', 'source_clock', 'native_startup', 'specialized', 'terminal_speed'}
EVIDENCE = {'run_config', 'source_snapshot', 'runtime_parameters', 'bag_integrity',
    'recording_closure', 'process_exit_codes', 'source_clock', 'native_startup', 'specialized',
    'terminal_speed', 'rendering', 'magnetic'}


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False)+'\n', encoding='utf-8')
    return m.binding(path)


def runner_fixture():
    # Only storage/source-plan binding is mocked; all real policy validators run.
    runner = SimpleNamespace(**vars(v4))
    runner.validate_plan = Mock()
    runner.verify_sources = Mock()
    runner.simulation_processes = Mock(return_value=[])
    runner.run_plan = Mock(side_effect=AssertionError('Safety must not call the normal run_plan'))
    return runner


def plan_fixture():
    protocol = json.loads((SOURCE/v4.PROTOCOL_PATH).read_text(encoding='utf-8'))
    return {'mode': 'PROBE', 'frozen_root': str(m.ROOT), 'selected_classes': ['person', 'car'],
        'selected_seeds': [4], 'selected_groups': list(v4.GROUPS), 'trials': [{} for _ in range(12)],
        'protocol': protocol, 'plan_sha256': 'a'*64,
        'source_hashes': {'scripts/run_stage1_trial.py': 'b'*64}}


class SafetyRunnerTests(unittest.TestCase):
    def test_tool_manifest_paths_have_identical_posix_semantics_on_windows_and_linux(self):
        manifest = m.tool_manifest()
        self.assertEqual(manifest['frozen_root'], m.ROOT.as_posix())
        self.assertEqual(manifest['core_plan'], m.CORE.as_posix())
        self.assertNotIn('\\', manifest['frozen_root'])
        self.assertNotIn('\\', manifest['core_plan'])

    def test_safety_runtime_checks_source41_birth_policy_in_actual_saved_yaml(self):
        # Minimal synthetic archive reaches the new policy check; other
        # required safety YAML is intentionally absent, so this never claims
        # a complete runtime PASS or touches a real trial.
        for trial in (self.trials[0], self.trials[2]):
            cls = trial['target_class']; car = cls == 'car'
            directory = Path(trial['directory'])
            configuration = {**trial['settings'], 'occlusions': False, 'reselect_after_loss': False,
                'no_bag': False, 'vehicle_control_point_offset_flu_m': [0., 0., .24]}
            model = self.plan['protocol']['resources'][cls]['model']
            self.plan['source_hashes'][model] = 'e'*64
            snapshot = {key: value for key, value in self.plan['source_hashes'].items()
                if key.startswith(('scripts/', 'uav_tracking/', 'ros2_ws/src/'))
                and Path(key).suffix in {'.py', '.sh', '.msg'}}
            snapshot[model] = 'e'*64
            dump(directory/'run_config.json', configuration)
            dump(directory/'configuration/source_sha256.json', snapshot)
            parameters = {
                'uav_tracking_detection': {'ros__parameters': {'car_surface_recovery_enabled': car}},
                'uav_tracking_state_estimator': {'ros__parameters': {'supported_birth_confirmation_required': car}}}
            fake_guard = SimpleNamespace(**{name: Mock() for name in ('geometry_bound_evidence',
                'car_surface_recovery_evidence', 'exclusive_navigation_evidence', 'simulation_pacing_evidence')})
            path = directory/'configuration/runtime_parameters.yaml'
            for defect in (None, 'missing', 'opposite', 'integer'):
                changed = deepcopy(parameters)
                values = changed['uav_tracking_state_estimator']['ros__parameters']
                if defect == 'missing': values.pop('supported_birth_confirmation_required')
                elif defect == 'opposite': values['supported_birth_confirmation_required'] = not car
                elif defect == 'integer': values['supported_birth_confirmation_required'] = int(car)
                dump(path, changed)
                with self.subTest(cls=cls, defect=defect), patch.object(m, 'frozen_guard', return_value=fake_guard):
                    message = 'Actual safety YAML gates differ' if defect is None else 'Actual source41 archived class policy differs'
                    self.assertRaisesRegex(ValueError, message, m.safety_runtime,
                        self.runner, self.plan, trial, {}, object())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='safety41_pure_')
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name).resolve()
        for name, value in {'ROOT': self.temp/'frozen41', 'AUDIT': self.temp/'audit',
                'CORE': self.temp/'frozen41/results/core/plan.json',
                'CARD': self.temp/'card.md', 'TAIL': self.temp/'tail.py'}.items():
            p = patch.object(m, name, value)
            p.start(); self.addCleanup(p.stop)
        self.runner, self.plan = runner_fixture(), plan_fixture()
        self.trials = m.safety_definitions(self.runner, self.plan)
        self.core_binding = dump(m.CORE, self.plan)
        canonical = (SOURCE/'planning/reliability-v4-ambiguity-execution.md').read_bytes()
        m.CARD.write_bytes(canonical)
        (m.ROOT/'planning').mkdir(exist_ok=True)
        (m.ROOT/'planning/reliability-v4-ambiguity-execution.md').write_bytes(canonical)
        m.TAIL.write_bytes(guard.safety_tail_code(m.CARD))
        self.tail_binding = {'execution_card': m.binding(m.CARD), 'tail_script': m.binding(m.TAIL)}
        self.before = {'source': {'freeze_source_sha256': 'c'*64}, 'safety_tools_canonical_sha256': 'd'*64}
        self.built = {'_safety_tools_sha256': 'd'*64}

    def register(self):
        with patch.object(m, 'actual_core', return_value=(m.CORE, self.plan, {'completed_count': 12})), \
                patch.object(m, 'verify_tail', return_value=self.tail_binding), \
                patch.object(m, 'entry_binding', return_value=self.before), \
                patch.object(m, 'execute') as execute, redirect_stdout(io.StringIO()):
            self.assertEqual(m.register_safety({}, self.built, self.runner), 0)
            execute.assert_not_called()
        return m.read_small(m.AUDIT/'registry.json')

    def fact_fixture(self):
        trial = self.trials[0]
        directory = Path(trial['directory'])
        names = {**m.EVIDENCE, 'specialized': 'auto_unique_evaluation_v2.json'}
        for relative in names.values():
            dump(directory/relative, {})
        executions = {}
        for kind in sorted(EXECUTIONS):
            log = self.temp/(kind+'.log')
            log.write_text('original fixture command output\n', encoding='utf-8')
            actual = {'command': ['fixture', kind], 'started_utc': '2026-10-31T01:00:00+00:00',
                'finished_utc': '2026-10-31T01:00:01+00:00', 'returncode': 0, 'error': None,
                'outer_cleanup_actions': [], 'log': str(log)}
            outer = dump(self.temp/(kind+'.outer.json'), actual)
            executions[kind] = {**outer, 'execution': actual}
        row = {'trial': trial, 'status': 'PASS', 'infrastructure_stop': False,
            'executions': executions, 'error': None}
        return row, {'tail_script': self.tail_binding['tail_script']}

    def test_real_v2_contract_produces_ordered_four_slots_and_exact_policy_flags(self):
        self.assertEqual([trial['id'] for trial in self.trials], IDS)
        for trial in self.trials:
            command, settings = trial['flight_command'], trial['settings']
            car = trial['target_class'] == 'car'
            self.assertEqual(trial['flight_argv'], command)
            self.assertEqual(command.count('--px4-adapter-publish-rate-hz'), 1)
            self.assertEqual(command[command.index('--px4-adapter-publish-rate-hz')+1], '50.0')
            self.assertEqual(command.count('--car-surface-recovery'), int(car))
            self.assertEqual(command.count('--exclusive-navigation-reference'), int(car))
            self.assertEqual(command.count('--correlated-two-face-bound'), int(car))
            self.assertIs(settings['car_surface_recovery'], car)
            self.assertIs(settings['exclusive_navigation_reference'], car)
            self.assertEqual(settings['px4_adapter_publish_rate_hz'], 50.)
            self.assertEqual((settings['stage'], settings['seed'], settings['command_mode'], settings['gimbal_mode']),
                             (2, 4, 'velocity', 'midpoint'))
            self.assertNotIn('--occlusions', command)
            self.assertNotIn('--reselect-after-loss', command)
            self.assertFalse(any(value.startswith('--car-surface-recovery=') or
                value.startswith('--px4-adapter-publish-rate-hz=') or
                value.startswith('--exclusive-navigation-reference=') for value in command))

    def test_unique_and_locked_preserve_distinct_selection_and_safety_scenarios(self):
        for trial in self.trials:
            settings = trial['settings']
            if trial['case'] == 'auto_unique_multi':
                expected = ('auto_unique', 'legacy', 'parallel', 'none', 2, 35.)
                self.assertEqual(settings['no_follow_duration_s'], 35.)
            else:
                expected = ('locked_target', 'hybrid_3d', 'ambiguity', 'middle', 3, 50.)
                self.assertNotIn('no_follow_duration_s', settings)
            self.assertEqual(tuple(settings[key] for key in ('target_mode', 'association_mode',
                'scenario_kind', 'initial_select', 'initial_min_candidates', 'duration')), expected)

    def test_v1_incomplete_pacing_and_malformed_class_policies_are_rejected(self):
        original = self.plan['protocol']
        changed = []
        value = deepcopy(original); value[v4.SIMULATION_PACING_FIELD] = deepcopy(v4.SIMULATION_PACING_V1); changed.append(value)
        value = deepcopy(original); value[v4.SIMULATION_PACING_FIELD].pop(v4.PX4_ADAPTER_PUBLISH_RATE_FIELD); changed.append(value)
        value = deepcopy(original); value[v4.SIMULATION_PACING_FIELD][v4.PX4_ADAPTER_PUBLISH_RATE_FIELD] = True; changed.append(value)
        value = deepcopy(original); value['resources']['car'][v4.CORRELATED_BOUND_FIELD] = 1; changed.append(value)
        value = deepcopy(original); value['resources']['car'][v4.CAR_SURFACE_RECOVERY_FIELD]['enabled'] = 1; changed.append(value)
        value = deepcopy(original); value['resources']['car'][v4.CAR_SURFACE_RECOVERY_FIELD].pop('method'); changed.append(value)
        value = deepcopy(original); value['resources']['person'][v4.CAR_SURFACE_RECOVERY_FIELD] = {
            **deepcopy(v4.CAR_SURFACE_RECOVERY_V1), 'enabled': True}; changed.append(value)
        value = deepcopy(original); value['resources']['car'][v4.EXCLUSIVE_NAVIGATION_FIELD] = 1; changed.append(value)
        value = deepcopy(original); value['resources']['car'][v4.EXCLUSIVE_NAVIGATION_FIELD] = False; changed.append(value)
        value = deepcopy(original); value['resources']['person'][v4.EXCLUSIVE_NAVIGATION_FIELD] = False; changed.append(value)
        for index, protocol in enumerate(changed):
            with self.subTest(index=index), self.assertRaises(ValueError):
                m.policy_flags(self.runner, protocol, 'car')

    def test_subset_core_and_held_out_seed_cannot_define_safety(self):
        for key, value in [('selected_classes', ['car']), ('selected_groups', ['stage2_crossing']),
                           ('selected_seeds', [1000]), ('selected_seeds', [True]), ('trials', [{}])]:
            plan = deepcopy(self.plan); plan[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.safety_definitions(self.runner, plan)

    def test_tail_card_and_script_are_byte_exact_and_marker_remains_unique(self):
        self.assertEqual(m.verify_tail(guard), self.tail_binding)
        code = m.TAIL.read_bytes()
        m.TAIL.write_bytes(code+b'\n')
        with self.assertRaises(ValueError):
            m.verify_tail(guard)
        m.TAIL.write_bytes(code)
        m.CARD.write_bytes(m.CARD.read_bytes()+b"\n<<'PY'\npass\nPY\n")
        with self.assertRaises(ValueError):
            m.verify_tail(guard)

    def test_original_evaluator_argv_matches_frozen_safety_contract(self):
        for trial in self.trials:
            directory = Path(trial['directory'])
            commands = {'flight': trial['flight_command'], **m.safety_evaluations(trial)}
            self.assertEqual(set(commands), EXECUTIONS)
            ledger = {key: {'argv': value} for key, value in commands.items()}
            ledger['terminal_speed']['code_script'] = self.tail_binding['tail_script']
            artifacts = {key: (directory/name, {}) for key, name in m.report_names(trial).items()}
            guard.safety_command_contract(ledger, artifacts, m.ROOT, directory,
                trial['target_class'], trial['case'], execution_card=m.CARD)
            self.assertEqual(len(commands['terminal_speed']), 5)
            if trial['case'] == 'locked_ambiguity':
                ledger['specialized']['argv'] = [x for x in commands['specialized'] if x != '--require-ambiguity']
                with self.assertRaises(ValueError):
                    guard.safety_command_contract(ledger, artifacts, m.ROOT, directory,
                        trial['target_class'], trial['case'], execution_card=m.CARD)

    def test_failed_completed_core_prerequisite_prevents_registration_or_flight(self):
        matrix = SimpleNamespace(require_completed_core=Mock(side_effect=ValueError('core incomplete')))
        with patch.object(m, 'matrix_module', return_value=matrix), \
                patch.object(m, 'execute') as execute, patch.object(m, 'write_new') as written, \
                self.assertRaisesRegex(ValueError, 'core incomplete'):
            m.register_safety({}, self.built, self.runner)
        execute.assert_not_called(); written.assert_not_called()
        self.assertFalse(m.AUDIT.exists())
        self.runner.verify_sources.assert_not_called()
        self.assertTrue(matrix.require_completed_core.call_args.kwargs['all_pass'])

    def test_registry_persists_all_four_original_argv_and_bindings_without_execution(self):
        registry = self.register()
        self.assertEqual([row['id'] for row in registry['trials']], IDS)
        self.assertEqual([row['flight_argv'] for row in registry['trials']],
                         [trial['flight_command'] for trial in self.trials])
        self.assertEqual(registry['source_core_plan'], {**self.core_binding, 'plan_sha256': self.plan['plan_sha256']})
        self.assertEqual(registry['execution_card'], m.binding(m.CARD))
        self.assertEqual(registry['tail_script'], m.binding(m.TAIL))
        self.assertEqual(registry['driver'], m.binding(m.__file__))
        self.assertFalse(registry['automatic_retry'])

    def test_run_requires_persisted_four_argv_and_takes_one_outer_lock_only(self):
        self.register()
        calls = []
        @contextmanager
        def locked(directory):
            calls.append(('enter', directory)); yield; calls.append(('exit', directory))
        self.runner.run_lock = Mock(side_effect=locked)
        def inside(*args):
            persisted = m.read_small(m.AUDIT/'registry.json')
            self.assertEqual([row['id'] for row in persisted['trials']], IDS)
            self.assertEqual(len(persisted['trials']), 4)
            self.assertEqual(calls, [('enter', m.AUDIT)])
            return 0
        args = SimpleNamespace(registry_sha256=m.sha(m.AUDIT/'registry.json'))
        with patch.object(m, 'actual_core', return_value=(m.CORE, self.plan, {'completed_count': 12})), \
                patch.object(m, 'verify_tail', return_value=self.tail_binding), \
                patch.object(m, 'entry_binding', return_value=self.before), \
                patch.object(m, 'run_safety_locked', side_effect=inside) as run:
            self.assertEqual(m.run_safety(args, {}, self.built, self.runner, {}), 0)
        self.runner.run_lock.assert_called_once_with(m.AUDIT)
        self.runner.run_plan.assert_not_called(); run.assert_called_once()
        self.assertEqual(calls, [('enter', m.AUDIT), ('exit', m.AUDIT)])

    def test_missing_registry_bad_hash_or_started_attempt_refuses_without_flight(self):
        self.runner.run_lock = Mock(side_effect=AssertionError('No lock before valid registry'))
        with patch.object(m, 'run_safety_locked') as run:
            with self.assertRaises(ValueError):
                m.run_safety(SimpleNamespace(registry_sha256=None), {}, self.built, self.runner, {})
            self.register()
            with patch.object(m, 'actual_core', return_value=(m.CORE, self.plan, {'completed_count': 12})), \
                    patch.object(m, 'verify_tail', return_value=self.tail_binding), \
                    patch.object(m, 'entry_binding', return_value=self.before):
                with self.assertRaises(ValueError):
                    m.run_safety(SimpleNamespace(registry_sha256='0'*64), {}, self.built, self.runner, {})
                dump(m.AUDIT/(IDS[0]+'.started.json'), {'original_attempt': True})
                with self.assertRaisesRegex(ValueError, 'refuse retry'):
                    m.run_safety(SimpleNamespace(registry_sha256=m.sha(m.AUDIT/'registry.json')),
                                 {}, self.built, self.runner, {})
            run.assert_not_called()
        self.runner.run_lock.assert_not_called()

    def test_first_execution_fault_retains_one_attempt_and_three_pending_without_retry(self):
        registry = self.register()
        before = self.before
        class Observer:
            def __init__(self, directory, root): self._finished = None
            def __enter__(self): return self
            def __exit__(self, *args): self._finished = {'healthy_cleanup': True}
            def check(self): return {'sample_age_wall_s': 0.}
        def first_execution(command, name, observer, timeout):
            persisted = m.read_small(m.AUDIT/'registry.json')
            self.assertEqual([item['id'] for item in persisted['trials']], IDS)
            self.assertEqual([item['flight_argv'] for item in persisted['trials']],
                             [trial['flight_command'] for trial in self.trials])
            self.assertTrue((m.AUDIT/(IDS[0]+'.started.json')).is_file())
            self.assertEqual(command, self.trials[0]['flight_command'])
            raise RuntimeError('original owned flight stopped')
        cleanup = {'entry_binding_after': before, 'cleanup': {'residual_processes': []},
                   'observer': None, 'final_errors': []}
        modules = {'humble33_diagnostic_checks01': object(), 'humble33_development_observer01': object()}
        with patch.object(m.owner, 'make_observer', side_effect=lambda directory, root, **kwargs: Observer(directory, root)), \
                patch.object(m, 'entry_binding', return_value=before), \
                patch.object(m, 'execute', side_effect=first_execution) as executed, \
                patch.object(m, 'finish_action', return_value=cleanup), \
                patch.object(m.subprocess, 'Popen') as spawned, redirect_stdout(io.StringIO()):
            self.assertEqual(m.run_safety_locked({}, self.built, self.runner, modules,
                                               self.plan, registry, before), 2)
        executed.assert_called_once(); spawned.assert_not_called()
        terminal, facts = m.read_small(m.AUDIT/'execution_terminal.json'), m.read_small(m.AUDIT/'slots_facts.json')
        self.assertEqual((terminal['attempted_count'], terminal['pending_count']), (1, 3))
        self.assertEqual((facts['attempted_count'], facts['pending_count'], facts['result']), (1, 3, 'FAIL'))
        self.assertEqual([item['id'] for item in terminal['slots']], [IDS[0]])
        row = m.read_small(m.AUDIT/(IDS[0]+'.json'))
        self.assertIn('original owned flight stopped', row['error'])
        self.assertTrue(row['infrastructure_stop'])
        self.assertEqual(row['execution_facts']['executions'], {})
        self.assertEqual(set(row['execution_facts']['missing_evidence']), EVIDENCE)
        self.assertFalse((m.AUDIT/(IDS[1]+'.started.json')).exists())

    def test_observer_start_failure_retains_four_pending_and_never_executes(self):
        registry = self.register()
        class FailedObserver:
            def __init__(self, directory, root): self._finished = None
            def __enter__(self):
                self._finished = {'healthy_cleanup': False, 'driver_exception': True}
                raise RuntimeError('no fresh observer sample')
            def __exit__(self, *args): pass
        cleanup = {'entry_binding_after': self.before, 'cleanup': {'residual_processes': []},
                   'observer': None, 'final_errors': ['observer:unhealthy']}
        modules = {'humble33_diagnostic_checks01': object(), 'humble33_development_observer01': object()}
        with patch.object(m.owner, 'make_observer', side_effect=lambda directory, root, **kwargs: FailedObserver(directory, root)), \
                patch.object(m, 'entry_binding', return_value=self.before), \
                patch.object(m, 'execute') as executed, \
                patch.object(m, 'finish_action', return_value=cleanup), \
                patch.object(m.subprocess, 'Popen') as spawned:
            self.assertEqual(m.run_safety_locked({}, self.built, self.runner, modules,
                                               self.plan, registry, self.before), 2)
        executed.assert_not_called(); spawned.assert_not_called()
        terminal, facts = m.read_small(m.AUDIT/'execution_terminal.json'), m.read_small(m.AUDIT/'slots_facts.json')
        self.assertEqual((terminal['attempted_count'], terminal['pending_count']), (0, 4))
        self.assertFalse(terminal['observer_owner_terminal']['healthy_cleanup'])
        self.assertEqual(terminal['final_errors'], ['observer:unhealthy'])
        self.assertIn('no fresh observer sample', terminal['stop_reason'])
        self.assertEqual((facts['result'], facts['slots']), ('FAIL', []))

    def guard_receipt_fixture(self, result='PASS', error=None):
        summary = dump(m.AUDIT/'development_validation_summary.json',
                       {'result': 'PASS', 'independent_frozen_guard_validation_required': True})
        actual = {'registry': {'path': str(m.AUDIT/'registry.json'), 'sha256': 'e'*64},
                  'all_four_original_pass': True, 'formal_seed_use_authorized': False}
        validation = {'schema_version': 1, 'scope': 'INDEPENDENT_FROZEN_SAFETY_GUARD_DEVELOPMENT_RECHECK',
            'summary': summary, 'result': result, 'error': error,
            'formal_seed_use_authorized': False, 'actual_evidence_bindings': actual}
        dump(m.AUDIT/'development_guard_validation.json', validation)
        return actual

    def test_original_guard_pass_is_rechecked_twice_without_receipt_rewrite(self):
        actual = self.guard_receipt_fixture()
        path = m.AUDIT/'development_guard_validation.json'
        original_bytes = path.read_bytes()
        with patch.object(m, '_validate_completed_safety_evidence', return_value=actual) as independent, \
                patch.object(m, 'write_new') as written:
            first = m.require_completed_safety({}, self.built, self.runner, self.plan, m.CORE)
            second = m.require_completed_safety({}, self.built, self.runner, self.plan, m.CORE)
        self.assertEqual(first, second)
        self.assertEqual(independent.call_count, 2)
        self.assertEqual(first['independent_guard_validation'], m.binding(path))
        self.assertEqual(path.read_bytes(), original_bytes)
        written.assert_not_called()

    def test_missing_or_original_failed_guard_receipt_is_never_retested_or_promoted(self):
        with patch.object(m, '_validate_completed_safety_evidence') as independent:
            with self.assertRaises(ValueError):
                m.require_completed_safety({}, self.built, self.runner)
            for result, error in [('FAIL', 'ValueError:original guard rejection'),
                                  ('PASS', 'RuntimeError:incomplete original check')]:
                self.guard_receipt_fixture(result, error)
                with self.subTest(result=result, error=error), self.assertRaisesRegex(ValueError, 'no retry promotion'):
                    m.require_completed_safety({}, self.built, self.runner)
            independent.assert_not_called()

    def test_guard_receipt_summary_binding_drift_refuses_before_new_validation(self):
        self.guard_receipt_fixture()
        dump(m.AUDIT/'development_validation_summary.json', {'result': 'PASS', 'changed_after_guard': True})
        with patch.object(m, '_validate_completed_safety_evidence') as independent, \
                self.assertRaisesRegex(ValueError, 'no retry promotion'):
            m.require_completed_safety({}, self.built, self.runner)
        independent.assert_not_called()

    def test_changed_actual_evidence_bindings_cannot_reuse_original_guard_pass(self):
        actual = self.guard_receipt_fixture()
        changed = deepcopy(actual)
        changed['registry']['sha256'] = 'f'*64
        path = m.AUDIT/'development_guard_validation.json'
        original = path.read_bytes()
        with patch.object(m, '_validate_completed_safety_evidence', return_value=changed) as independent, \
                self.assertRaisesRegex(ValueError, 'evidence bindings changed'):
            m.require_completed_safety({}, self.built, self.runner)
        independent.assert_called_once()
        self.assertEqual(path.read_bytes(), original)

    def test_final_guard_rejection_keeps_all_four_original_complete_slots_and_records_failure(self):
        registry = self.register()
        before, frozen_bytes = self.before, {}
        class Observer:
            def __init__(self, directory, root): self._finished = None
            def __enter__(self): return self
            def __exit__(self, *args): self._finished = {'healthy_cleanup': True}
            def check(self): return {'sample_age_wall_s': 0.}
        def successful_execution(command, name, observer, timeout):
            if command[2] == str(m.ROOT/'scripts/run_stage1_trial.py'):
                trial = next(trial for trial in self.trials if trial['flight_command'] == command)
                directory = Path(trial['directory'])
                for key, relative in m.EVIDENCE.items():
                    if key not in m.report_names(trial):
                        dump(directory/relative, {})
            else:
                output = (Path(command[command.index('--output')+1]) if '--output' in command else
                          Path(command[3])/'terminal_hover_speed_evaluation.json')
                dump(output, {})
            log = m.AUDIT/(name+'.log')
            log.write_text('pure mock command completed\n', encoding='utf-8')
            execution = {'command': command, 'started_utc': m.utc(), 'finished_utc': m.utc(),
                'returncode': 0, 'error': None, 'outer_cleanup_actions': [], 'log': str(log),
                'timeout_wall_s': timeout}
            return {**dump(m.AUDIT/(name+'.outer.json'), execution), 'execution': execution}
        def independent_rejection(*args):
            retained = [m.AUDIT/(identifier+'.json') for identifier in IDS]
            retained.extend(m.AUDIT/name for name in ('execution_terminal.json', 'slots_facts.json',
                                                     'development_validation_summary.json'))
            frozen_bytes.update({path: path.read_bytes() for path in retained})
            raise ValueError('independent final guard rejected actual evidence')
        cleanup = {'entry_binding_after': before, 'cleanup': {'residual_processes': []},
                   'observer': None, 'final_errors': []}
        modules = {'humble33_diagnostic_checks01': object(), 'humble33_development_observer01': object()}
        self.runner.infrastructure_evidence = Mock(return_value={'stop': False})
        with patch.object(m.owner, 'make_observer', side_effect=lambda directory, root, **kwargs: Observer(directory, root)), \
                patch.object(m, 'entry_binding', return_value=before), \
                patch.object(m, 'execute', side_effect=successful_execution) as executed, \
                patch.object(m, 'safety_runtime', return_value={'status': 'PASS'}), \
                patch.object(m, 'safety_report_audit', return_value={'status': 'PASS'}), \
                patch.object(m, 'frozen_bindings', return_value={'fixture': 'same source'}), \
                patch.object(m, '_validate_completed_safety_evidence', side_effect=independent_rejection) as independent, \
                patch.object(m, 'finish_action', return_value=cleanup), \
                patch.object(m.subprocess, 'Popen') as spawned, redirect_stdout(io.StringIO()):
            self.assertEqual(m.run_safety_locked({}, self.built, self.runner, modules,
                                               self.plan, registry, before), 2)
        self.assertEqual(executed.call_count, 20)
        independent.assert_called_once(); spawned.assert_not_called()
        terminal = m.read_small(m.AUDIT/'execution_terminal.json')
        facts = m.read_small(m.AUDIT/'slots_facts.json')
        validation = m.read_small(m.AUDIT/'development_guard_validation.json')
        self.assertEqual((terminal['returncode'], terminal['attempted_count'], terminal['pending_count']), (0, 4, 0))
        self.assertEqual((facts['result'], facts['attempted_count'], facts['pending_count']), ('PASS', 4, 0))
        self.assertEqual([item['id'] for item in facts['slots']], IDS)
        for slot in facts['slots']:
            self.assertEqual(slot['result'], 'PASS')
            self.assertEqual(set(slot['executions']), EXECUTIONS)
            self.assertEqual(set(slot['evidence']), EVIDENCE)
        self.assertEqual(validation['result'], 'FAIL')
        self.assertIn('independent final guard rejected', validation['error'])
        for path, original in frozen_bytes.items():
            self.assertEqual(path.read_bytes(), original)
        with patch.object(m, '_validate_completed_safety_evidence') as retried, self.assertRaises(ValueError):
            m.require_completed_safety({}, self.built, self.runner)
        retried.assert_not_called()

    def test_slot_facts_keep_five_execution_ledgers_and_twelve_named_evidence(self):
        row, registry = self.fact_fixture()
        facts = m.slot_facts(row, registry)
        self.assertEqual(facts['result'], 'PASS')
        self.assertEqual(set(facts['executions']), EXECUTIONS)
        self.assertEqual(set(facts['evidence']), EVIDENCE)
        self.assertEqual(facts['missing_evidence'], [])
        self.assertEqual(facts['executions']['terminal_speed']['code_script'], registry['tail_script'])

    def test_slot_facts_retain_algorithm_failure_missing_evidence_and_partial_execution(self):
        row, registry = self.fact_fixture()
        row['status'] = 'FAIL'
        row['executions']['specialized']['execution']['returncode'] = 2
        facts = m.slot_facts(row, registry)
        self.assertEqual((facts['result'], facts['original_status']), ('FAIL', 'FAIL'))
        self.assertEqual(facts['executions']['specialized']['returncode'], 2)
        Path(facts['evidence']['specialized']['path']).unlink()
        row['executions'].pop('terminal_speed')
        row.update(status='INFRASTRUCTURE_ERROR', infrastructure_stop=True, error='missing original report')
        facts = m.slot_facts(row, registry)
        self.assertEqual(facts['result'], 'FAIL')
        self.assertIn('specialized', facts['missing_evidence'])
        self.assertEqual(len(facts['executions']), 4)
        self.assertEqual(facts['original_error'], 'missing original report')

    def test_cli_missing_explicit_authorization_refuses_before_runtime_or_writes(self):
        with patch.object(m.subprocess, 'Popen') as spawned, patch.object(m, 'write_new') as written, \
                patch.object(m.generic, 'require_linux') as linux, patch.object(m, 'tool_manifest') as tools, \
                patch.object(m, 'register_safety') as registered, patch.object(m, 'run_safety') as run, \
                redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(['register']), 2)
            self.assertEqual(m.main(['run']), 2)
        for mocked in (spawned, written, linux, tools, registered, run):
            mocked.assert_not_called()

    def test_matrix_raw_hash_is_checked_before_execution_and_only_checked_source_runs(self):
        external = self.temp/'untrusted_external'
        external.mkdir()
        path = external/'matrix_runner41.py'
        marker = external/'executed.txt'
        source = ("from pathlib import Path\n"
                  f"Path({str(marker)!r}).write_text('CHECKED_SOURCE', encoding='utf-8')\n"
                  "TOKEN = 'checked original source'\n").encode('utf-8')
        path.write_bytes(source)
        digest = hashlib.sha256(source).hexdigest()
        with patch.object(m, 'EXTERNAL', external), patch.object(m, 'MATRIX_PY_SHA', '0'*64), \
                patch.object(m.importlib, 'import_module') as imported, self.assertRaisesRegex(ValueError, 'before execution'):
            m.matrix_module()
        self.assertFalse(marker.exists())
        imported.assert_not_called()
        with patch.object(m, 'EXTERNAL', external), patch.object(m, 'MATRIX_PY_SHA', digest), \
                patch.object(m.importlib, 'import_module') as imported, patch.dict(m.sys.modules):
            actual = m.matrix_module()
        self.assertEqual(actual.TOKEN, 'checked original source')
        self.assertEqual(Path(actual.__file__).resolve(), path.resolve())
        self.assertEqual(marker.read_text(encoding='utf-8'), 'CHECKED_SOURCE')
        self.assertEqual(path.read_bytes(), source)
        imported.assert_not_called()

    def test_matrix_path_swap_after_hash_never_executes_replacement_and_is_rejected(self):
        external = self.temp/'racing_external'
        external.mkdir()
        path = external/'matrix_runner41.py'
        original_marker, replacement_marker = external/'checked.txt', external/'untrusted.txt'
        source = ("from pathlib import Path\n"
                  f"Path({str(original_marker)!r}).write_text('CHECKED', encoding='utf-8')\n").encode('utf-8')
        replacement = ("from pathlib import Path\n"
                       f"Path({str(replacement_marker)!r}).write_text('UNTRUSTED', encoding='utf-8')\n").encode('utf-8')
        path.write_bytes(source)
        digest = hashlib.sha256(source).hexdigest()
        original_spec = m.importlib.util.spec_from_file_location
        def replace_after_hash(name, filename, *args, **kwargs):
            self.assertEqual(Path(filename), path)
            path.write_bytes(replacement)
            return original_spec(name, filename, *args, **kwargs)
        with patch.object(m, 'EXTERNAL', external), patch.object(m, 'MATRIX_PY_SHA', digest), \
                patch.object(m.importlib.util, 'spec_from_file_location', side_effect=replace_after_hash) as spec, \
                patch.object(m.importlib, 'import_module') as imported, patch.dict(m.sys.modules), \
                self.assertRaisesRegex(ValueError, 'path/bytes changed'):
            m.matrix_module()
        spec.assert_called_once()
        imported.assert_not_called()
        self.assertTrue(original_marker.is_file())
        self.assertFalse(replacement_marker.exists())
        self.assertEqual(path.read_bytes(), replacement)

    def test_finish_action_persists_exact_original_owner_result_and_post_wait_validation(self):
        actual = {'status': 'COMPLETE', 'healthy_cleanup': True,
                  'archive_process': {'returncode': 0, 'elapsed_wall_s': 31., 'wall_budget_s': 1800.}}
        owner = SimpleNamespace(_finished=actual)
        validated = {'owner_terminal': actual, 'sessions': ['original session']}
        after = {'source': {'freeze_source_sha256': 'a'*64}}
        with patch.object(m.source, 'entry_binding', return_value=after), \
                patch.object(m.owner, 'validate_observer_root', return_value=validated) as validate, \
                patch.object(m, 'write_new') as write, patch.object(m.subprocess, 'Popen') as spawn:
            result = m.finish_action({}, self.built, self.runner, owner)
        validate.assert_called_once_with(actual, m.AUDIT/'observer_driver', m.ROOT)
        self.assertIs(result['observer_owner_terminal'], actual)
        self.assertEqual(result['observer'], validated)
        self.assertEqual(result['entry_binding_after'], after)
        self.assertEqual(result['final_errors'], [])
        write.assert_not_called(); spawn.assert_not_called()

    def test_missing_owner_result_is_never_recovered_from_D_copy_candidate(self):
        owner = SimpleNamespace(_finished=None)
        with patch.object(m.source, 'entry_binding', return_value={}), \
                patch.object(m, 'write_new') as write, patch.object(m.subprocess, 'Popen') as spawn:
            result = m.finish_action({}, self.built, self.runner, owner)
        self.assertIsNone(result['observer_owner_terminal'])
        self.assertIsNone(result['observer'])
        self.assertEqual(len(result['final_errors']), 1)
        self.assertIn('Original owner post-wait outcome is required', result['final_errors'][0])
        write.assert_not_called(); spawn.assert_not_called()

    def test_owner_failure_and_binding_cleanup_faults_are_retained_together(self):
        actual = {'status': 'OWNER_INFRA_ERROR', 'healthy_cleanup': False, 'error': 'archive timeout'}
        owner = SimpleNamespace(_finished=actual)
        self.runner.simulation_processes = Mock(return_value=['still-running-child'])
        with patch.object(m.source, 'entry_binding', side_effect=ValueError('source changed')), \
                patch.object(m.owner, 'validate_observer_root', side_effect=ValueError('unhealthy owner')) as validate:
            result = m.finish_action({}, self.built, self.runner, owner)
        validate.assert_called_once_with(actual, m.AUDIT/'observer_driver', m.ROOT)
        self.assertIs(result['observer_owner_terminal'], actual)
        self.assertIsNone(result['observer'])
        self.assertEqual(result['cleanup'], {'residual_processes': ['still-running-child']})
        self.assertEqual(len(result['final_errors']), 3)
        self.assertTrue(any('source changed' in value for value in result['final_errors']))
        self.assertTrue(any('Residual runtime' in value for value in result['final_errors']))
        self.assertTrue(any('unhealthy owner' in value for value in result['final_errors']))

    def test_describe_is_inert_and_never_loads_review_build_or_runtime(self):
        with patch.object(m, 'tool_manifest', return_value={'fixture': 'source only'}), \
                patch.object(m, 'reviewed_source') as review, patch.object(m.stable, 'dependencies') as deps, \
                patch.object(m.generic, 'require_linux') as linux, patch.object(m, 'write_new') as written, \
                patch.object(m.subprocess, 'Popen') as spawned, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.main(['describe']), 0)
        self.assertFalse(json.loads(output.getvalue())['actual_action_executed'])
        for mocked in (review, deps, linux, written, spawned):
            mocked.assert_not_called()


if __name__ == '__main__':
    unittest.main()
