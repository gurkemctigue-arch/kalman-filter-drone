"""Pure/fake extension41 controls. Never ROS, WSL, flight, build or old payload."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from copy import deepcopy
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import extension_runner41 as m

def fixture(kind='extension'):
    dimensions = m.CONDITIONS if kind == 'extension' else m.GROUPS
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

class ExtensionControls(unittest.TestCase):
    def test_complete16_original_specs_are_accepted_without_mutation(self):
            plan = fixture(); original = deepcopy(plan)
            self.assertIs(m.validate_matrix(plan, runner_fixture(), 'extension'), plan)
            self.assertEqual(plan, original)
            self.assertEqual([trial['extension_condition'] for trial in plan['trials']], list(m.CONDITIONS)*2)
            self.assertEqual(plan['trials'][8]['inference_image_size'], 640)

    def test_nonfinal_safety_pin_refuses_before_source_exec(self):
            with patch.object(m.importlib.util, 'spec_from_file_location') as imported:
                self.assertRaises(ValueError, m.load_safety_api, 'a'*64, m.SAFETY_PY_SHA)
                self.assertRaises(ValueError, m.load_safety_api, m.SAFETY_TOOLS_SHA, 'b'*64)
            imported.assert_not_called()

    def test_newowner_finish_result_is_preserved_and_old_validator_is_unused(self):
            actual = {'original_owner_post_wait': True}
            observer = SimpleNamespace(_finished=actual)
            runner = SimpleNamespace(simulation_processes=lambda: [])
            observed = {'owner_terminal': actual, 'native_and_archive_both_verified': True}
            with patch.object(m, 'entry_binding', return_value={'actualsource41': True}), \
                patch.object(m.owner, 'validate_observer_root', return_value=observed) as validated, \
                patch.object(m.stable, 'validate_observer_root', side_effect=AssertionError('Old validator unchanged')):
                result = m.finish_action({}, {}, runner, observer, Path('/fixture'), {})
            self.assertIs(result['observer_owner_terminal'], actual)
            self.assertIs(result['observer'], observed)
            self.assertEqual(result['final_errors'], [])
            validated.assert_called_once_with(actual, Path('/fixture/observer_driver'), m.ROOT)

    def test_extension_plan_contract_load_requires_original_full_owner_outcome(self):
            from contextlib import ExitStack
            with tempfile.TemporaryDirectory(prefix='extension41_plan_owner_fake_') as temporary, ExitStack() as stack:
                root = Path(temporary)
                selected = {'output': root/'matrix', 'plan': root/'matrix/plan.json',
                    'run_driver': root/'matrix/observed_driver01', 'plan_driver': root/'plan_driver'}
                selected['output'].mkdir(); selected['plan_driver'].mkdir()
                plan = fixture(); plan['output'] = str(selected['output'])
                selected['plan'].write_text(json.dumps(plan), encoding='utf-8')
                initial = m.pending_identity(plan)
                source, build, manifest = {'source': 'synthetic'}, {'build': 'synthetic'}, {'tools': 'synthetic'}
                review = {'_review_binding': {'path': '/synthetic/review.json', 'sha256': 'a'*64}}
                actual_owner, observed = {'original_post_wait': True}, {'raw_validated': True}
                terminal = {'scope': m.SCOPE, 'action': 'plan', 'matrix_kind': 'extension', 'returncode': 0,
                    'error': None, 'initial_pending': initial, 'flights_started': 0,
                    'entry_binding_before': source, 'entry_binding_after': source,
                    'prerequisites': None, 'final_errors': [], 'cleanup': {'residual_processes': []},
                    'observer_owner_terminal': actual_owner, 'observer': observed}
                path = root/'extension_runner41_contract_extension_final_fake.json'
                terminal_path = selected['plan_driver']/'execution_terminal.json'
                value = {'schema_version': 1, 'scope': m.SCOPE, 'status': m.FINAL, 'matrix_kind': 'extension',
                    'frozen_root': m.ROOT, 'source_review': review['_review_binding'], 'entry_binding': source,
                    'tools_canonical_sha256': m.canonical(manifest), 'build_evidence': build,
                    'plan_pending': initial, 'prerequisites': None,
                    'experiment': {'classes': list(m.CLASSES), 'seed': 4, 'duration_s': 75., 'flight_count': 16},
                    **{key: False for key in ('formal_seed_use_authorized', 'readiness_claimed', 'automatic_retry', 'automatic_next_action')}}
                for name, content in {'EXTERNAL': root, 'locations': lambda kind: selected,
                    'checked_plan': lambda *a: plan, 'verify_same_core': lambda *a: None,
                    'entry_binding': lambda *a: source, 'tool_manifest': lambda: manifest,
                    'require_prerequisites': lambda *a: None}.items():
                    stack.enter_context(patch.object(m, name, content))
                stack.enter_context(patch.object(m.source, 'build_evidence', return_value=build))
                validated = stack.enter_context(patch.object(m.owner, 'validate_observer_root',
                    side_effect=lambda actual, *a: observed if actual == actual_owner else
                        (_ for _ in ()).throw(ValueError('Original full owner outcome missing'))))
                stack.enter_context(patch.object(m.stable, 'validate_observer_root', side_effect=AssertionError('No legacy validator')))
                for missing in (False, True):
                    changed = deepcopy(terminal)
                    if missing: changed.pop('observer_owner_terminal')
                    terminal_path.write_text(json.dumps(changed), encoding='utf-8')
                    value['plan_terminal'] = m.stable.metadata_binding(terminal_path, json_only=True)
                    path.write_text(json.dumps(value), encoding='utf-8')
                    if missing:
                        self.assertRaisesRegex(ValueError, 'Original full owner', m.load_contract, 'extension',
                            path, m.sha(path), SimpleNamespace(), review, {}, object(), {})
                    else:
                        self.assertEqual(m.load_contract('extension', path, m.sha(path), SimpleNamespace(), review, {}, object(), {})[0], value)
                self.assertEqual(validated.call_args_list[0].args, (actual_owner, selected['plan_driver']/'observer_driver', m.ROOT))

    def test_describe_does_not_import_safety_or_enter_runtime_or_write(self):
            with patch.object(m, 'load_safety_api') as safety, patch.object(m, 'reviewed_source') as review, \
                patch.object(m.stable, 'dependencies') as deps, patch.object(m, 'write_new') as written, \
                patch.object(m.subprocess, 'Popen') as spawned, redirect_stdout(io.StringIO()) as output:
                self.assertEqual(m.main(['describe']), 0)
            self.assertFalse(json.loads(output.getvalue())['actual_action_executed'])
            for mocked in (safety, review, deps, written, spawned): mocked.assert_not_called()

    def test_incomplete_duplicated_reordered_formal_or_foreign_matrix_cannot_pass(self):
            for kind in ('extension',):
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
            for index in (0, 8):
                for field, value in ((m.source.ADAPTER_FIELD, True), (m.source.ADAPTER_FIELD, 20.),
                    ('inference_threads', 1), ('desired_distance_m', 99.), ('duration_s', 20.)):
                    plan = fixture(); plan['trials'][index][field] = value
                    self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), 'extension')
                for command in ([], ['original', m.source.ADAPTER_FLAG],
                    ['original', m.source.ADAPTER_FLAG, '20'], ['original', m.source.ADAPTER_FLAG, 'nan'],
                    ['original', m.source.ADAPTER_FLAG+'=50'],
                    ['original', m.source.ADAPTER_FLAG, '50', m.source.ADAPTER_FLAG, '50']):
                    plan = fixture(); plan['trials'][index]['flight_command'] = command
                    self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), 'extension')
                plan = fixture(); plan['trials'][index][m.source.PACING_FIELD].pop(m.source.ADAPTER_FIELD)
                self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), 'extension')
            plan = fixture(); plan['protocol'][m.source.PACING_FIELD]['safety_source_time_gates'] = 'modified'
            self.assertRaises(ValueError, m.validate_matrix, plan, runner_fixture(), 'extension')

    def test_person_cannot_inherit_car_surface_recovery(self):
            runner = runner_fixture()
            runner.car_surface_recovery_trial_binding = Mock(return_value=(True, True))
            self.assertRaises(ValueError, m.validate_matrix, fixture(), runner, 'extension')

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

    def test_extension_cannot_reach_safety_or_plan_when_actual_core_is_not_all_pass(self):
            runner = runner_fixture()
            args = SimpleNamespace(safety_tools_sha256='a'*64, safety_python_sha256='b'*64)
            with patch.object(m, 'checked_plan', return_value=fixture()), \
                patch.object(m, 'require_completed_core', side_effect=ValueError('Original FAIL retained')) as core, \
                patch.object(m, 'load_safety_api') as safety, patch.object(m, 'write_new') as written:
                self.assertRaises(ValueError, m.require_prerequisites, 'extension', args, {}, {}, runner)
            self.assertIs(core.call_args.kwargs['all_pass'], True)
            safety.assert_not_called(); written.assert_not_called()

    def test_extension_calls_actual_reviewed_safety_verifier_with_original_core_path(self):
            plan, runner = fixture(), runner_fixture()
            manifest = {'pure_fixture': True}
            args = SimpleNamespace(safety_tools_sha256=m.canonical(manifest), safety_python_sha256='b'*64)
            safety = SimpleNamespace(tool_manifest=lambda: manifest,
                require_completed_safety=Mock(return_value={'actual_registry_sha256': 'b'*64}))
            with patch.object(m, 'checked_plan', return_value=plan), \
                patch.object(m, 'require_completed_core', return_value={'actual12': True}) as core, \
                patch.object(m, 'load_safety_api', return_value=safety):
                result = m.require_prerequisites('extension', args, {'review': 1}, {'built': 1}, runner)
            core.assert_called_once_with({'review': 1}, {'built': 1}, runner, plan, m.locations('core')['plan'], all_pass=True)
            safety.require_completed_safety.assert_called_once_with({'review': 1}, {'built': 1}, runner,
                core_plan=plan, core_plan_path=m.locations('core')['plan'])
            self.assertEqual(result['safety'], {'actual_registry_sha256': 'b'*64})
            self.assertEqual(result['safety_python_sha256'], 'b'*64)

    def test_modified_safety_python_is_rejected_before_any_module_execution(self):
            with tempfile.TemporaryDirectory(prefix='matrix38_untrusted_python_') as directory:
                base = Path(directory)
                marker = base/'must_not_be_written.txt'
                path = base/(m.SAFETY_MODULE+'.py')
                original = "def tool_manifest(): return {'fixture': True}\n"
                path.write_text(original, encoding='utf-8')
                reviewed_raw_sha = m.sha(path)
                # The modified module could return the same manifest after causing
                # a side effect. Its raw byte mismatch must stop before even loading.
                path.write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("executed")\n'+original,
                    encoding='utf-8')
                with patch.object(m, 'EXTERNAL', base), patch.object(m, 'SAFETY_TOOLS_SHA', m.canonical({'fixture': True})), patch.object(m, 'SAFETY_PY_SHA', reviewed_raw_sha), patch.object(m.importlib.util, 'spec_from_file_location') as imported:
                    self.assertRaises(ValueError, m.load_safety_api, m.canonical({'fixture': True}), reviewed_raw_sha)
                imported.assert_not_called()
                self.assertFalse(marker.exists())

    def test_verified_safety_source_executes_checked_bytes_and_then_checks_full_manifest(self):
            with tempfile.TemporaryDirectory(prefix='matrix38_verified_python_') as directory:
                base = Path(directory); path = base/(m.SAFETY_MODULE+'.py')
                path.write_text("VERIFIED_FIXTURE = True\ndef tool_manifest(): return {'fixture': True}\n", encoding='utf-8')
                with patch.object(m, 'EXTERNAL', base), patch.object(m, 'SAFETY_TOOLS_SHA', m.canonical({'fixture': True})), patch.object(m, 'SAFETY_PY_SHA', m.sha(path)), patch.dict(m.sys.modules, {}, clear=False):
                    actual = m.load_safety_api(m.canonical({'fixture': True}), m.sha(path))
                    self.assertTrue(actual.VERIFIED_FIXTURE)
                    self.assertRaises(ValueError, m.load_safety_api, 'c'*64, m.sha(path))

    def test_safety_path_change_after_first_hash_never_executes_replacement_bytes(self):
            with tempfile.TemporaryDirectory(prefix='matrix38_python_path_change_') as directory:
                base = Path(directory); path = base/(m.SAFETY_MODULE+'.py'); marker = base/'replacement_executed.txt'
                path.write_text("VERIFIED_FIXTURE = True\ndef tool_manifest(): return {'fixture': True}\n", encoding='utf-8')
                expected_raw = m.sha(path)
                original_spec = m.importlib.util.spec_from_file_location
                def replace_after_hash(name, filename):
                    path.write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("executed")\n', encoding='utf-8')
                    return original_spec(name, filename)
                with patch.object(m, 'EXTERNAL', base), patch.object(m, 'SAFETY_TOOLS_SHA', m.canonical({'fixture': True})), patch.object(m, 'SAFETY_PY_SHA', expected_raw), patch.dict(m.sys.modules, {}, clear=False), \
                    patch.object(m.importlib.util, 'spec_from_file_location', side_effect=replace_after_hash):
                    self.assertRaises(ValueError, m.load_safety_api, m.canonical({'fixture': True}), expected_raw)
                    self.assertTrue(m.sys.modules[m.SAFETY_MODULE].VERIFIED_FIXTURE)
                self.assertFalse(marker.exists())

    def test_car_only_exclusive_policy_is_bound_in_all16_specs(self):
            for kind in ('extension',):
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

    def test_actual_frozen_runtime_validator_checks_both_nodes_and_both_classes(self):
            source_root = Path(os.environ.get('MATRIX41_TEST_SOURCE_ROOT',
                os.environ.get('STAGE1_PROJECT_ROOT', 'D:/基于yolo和卡尔曼滤波' if os.name == 'nt' else m.ROOT)))
            spec = importlib.util.spec_from_file_location('extension41_actual_exclusive_runtime_fixture', source_root/'scripts/run_reliability_v4.py')
            actual = importlib.util.module_from_spec(spec); spec.loader.exec_module(actual)
            plan = fixture()
            for cls, index in (('person', 0), ('car', 8)):
                trial = plan['trials'][index]; enabled = cls == 'car'
                configuration = {'exclusive_navigation_reference': enabled, 'car_surface_recovery': enabled}
                parameters = {node: {'ros__parameters': {'navigation_exclusive_enabled': enabled}}
                    for node in ('uav_tracking_detection', 'uav_tracking_state_estimator')}
                parameters['uav_tracking_detection']['ros__parameters']['car_surface_recovery_enabled'] = enabled
                parameters['uav_tracking_state_estimator']['ros__parameters']['supported_birth_confirmation_required'] = enabled
                self.assertEqual(m.validate_exclusive_runtime(plan, trial, configuration, parameters, actual)['errors'], [])
                for node in parameters:
                    changed = deepcopy(parameters); changed[node]['ros__parameters']['navigation_exclusive_enabled'] = not enabled
                    self.assertRaises(ValueError, m.validate_exclusive_runtime, plan, trial, configuration, changed, actual)
                for node, field in (('uav_tracking_detection', 'car_surface_recovery_enabled'),
                    ('uav_tracking_state_estimator', 'supported_birth_confirmation_required')):
                    for value in (None, not enabled, int(enabled), str(enabled)):
                        changed = deepcopy(parameters)
                        if value is None: changed[node]['ros__parameters'].pop(field)
                        else: changed[node]['ros__parameters'][field] = value
                        self.assertRaises(ValueError, m.validate_exclusive_runtime, plan, trial, configuration, changed, actual)
                changed = {'exclusive_navigation_reference': 1 if enabled else True}
                self.assertRaises(ValueError, m.validate_exclusive_runtime, plan, trial, changed, parameters, actual)
    def test_manifest_pins_actual_core_dependency_and_exposes_only16(self):
        result=m.tool_manifest()
        self.assertEqual(result['actions'], ['plan-extension','run-extension'])
        self.assertFalse(result['core_actions_exposed'])
        self.assertTrue(result['requires_all12_original_core_pass'])
        self.assertTrue(result['requires_all4_original_safety_and_frozen_guard_pass'])
        self.assertEqual(result['extension_cells'],16)
        self.assertEqual(result['core_dependency']['python_sha256'],m.CORE_PY_SHA)
        self.assertEqual(result['source41_tools_canonical_sha256'],m.SOURCE_CANONICAL)
        self.assertEqual(result['safety_dependency'], {'python_sha256': m.SAFETY_PY_SHA,
            'tools_canonical_sha256': m.SAFETY_TOOLS_SHA})
        self.assertTrue(result['observer_original_post_wait_terminal_required'])
        self.assertFalse(result['formal_seed_use_authorized'])

    def test_owned_source_files_must_be_present_bounded_and_not_symlinks(self):
        with tempfile.TemporaryDirectory(prefix='extension41_own_') as d:
            root=Path(d)
            with patch.object(m,'EXTERNAL',root):
                self.assertRaises(ValueError,m.checked_own_files)
                for name in m.OWN_FILES:
                    (root/name).write_text('xx',encoding='utf-8')
                self.assertEqual(set(m.checked_own_files()),set(m.OWN_FILES))
                with patch.object(m.generic,'MAX_SMALL',1):
                    self.assertRaises(ValueError,m.checked_own_files)
                with patch.object(Path,'is_symlink',return_value=True):
                    self.assertRaises(ValueError,m.checked_own_files)

    def test_core_actions_cannot_reach_any_mutable_api(self):
        for action in ['plan-core','run-core']:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                m.parser().parse_args([action])
        for function,args in [(m.plan_matrix,('core',None,None,None,None,None,None,None)),
                              (m.run_matrix,('core',None,None,None,None,None,None))]:
            with self.assertRaises(ValueError):function(*args)

    def test_core_verifier_delegates_to_original_core41_and_forces_all_pass(self):
        api=SimpleNamespace(require_completed_core=Mock(return_value={'synthetic':True}))
        with patch.object(m,'core_module',return_value=api):
            self.assertEqual(m.require_completed_core('r','b','v',core_plan='p',core_plan_path='path'),{'synthetic':True})
            api.require_completed_core.assert_called_once_with('r','b','v','p','path',all_pass=True)
            with self.assertRaises(ValueError):m.require_completed_core('r','b','v',all_pass=False)

    def test_core_python_mutation_refuses_before_module_execution(self):
        with tempfile.TemporaryDirectory(prefix='extension41_source_') as d:
            p=Path(d)/'matrix_runner41.py';p.write_text("raise AssertionError('must not execute')",encoding='utf-8')
            with patch.object(m,'EXTERNAL',Path(d)), self.assertRaisesRegex(ValueError,'before module execution'):
                m.core_module()

    def test_no_default_contract_or_recovery_path(self):
        opts=m.parser().parse_args(['describe'])
        self.assertIsNone(opts.contract)
        self.assertFalse(hasattr(m,'validate_zero_attempt_recovery'))
        self.assertEqual(m.locations('extension')['run_driver'].name,'observed_driver01')
        self.assertEqual(m.locations('core')['run_driver'].name,'observed_driver01')

    def test_original_core_plan_uses_dependency_validator_and_path(self):
        api=SimpleNamespace(checked_plan=Mock(return_value={'original':'core'}))
        with patch.object(m,'core_module',return_value=api):
            self.assertEqual(m.checked_plan('core','v','p','path'),{'original':'core'})
            api.checked_plan.assert_called_once_with('core','v','p','path')


class BatchControls(unittest.TestCase):
    def run_batch(self, infrastructure_at=None, preexisting=False, source_drift=False, check_admission=False):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory(prefix='extension41_batch_mock_') as temporary, ExitStack() as stack:
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
            contract = {'plan_pending': {'plan': plan_binding}, 'prerequisites': None}
            patches = {
                'locations': lambda kind: selected, 'load_contract': lambda *a: (contract, plan),
                'checked_plan': lambda *a, **k: plan, 'entry_binding': entry,
                'require_prerequisites': lambda *a: None, 'make_observer': lambda *a: Observer(),
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
                    self.assertRaises(ValueError, m.run_matrix, 'extension', args, {}, {}, runner, modules, {})
                    self.assertFalse(selected['run_driver'].exists())
                    self.assertEqual(calls, [])
                    return
                code = m.run_matrix('extension', args, {}, {}, runner, modules, {})
            terminal = json.loads((selected['run_driver']/'execution_terminal.json').read_text(encoding='utf-8'))
            runner.run_lock.assert_not_called()
            self.assertEqual(commands, [next(t['flight_command'] for t in plan['trials'] if t['id'] == identifier) for identifier in calls])
            return code, terminal, calls

    def test_all16_algorithm_failures_remain_in_denominator_without_retry(self):
        code, terminal, calls = self.run_batch()
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 16)
        self.assertEqual(terminal['status_counts'], {'FAIL': 16})
        self.assertEqual(terminal['terminal_count'], 16)
        self.assertFalse(terminal['readiness_claimed'])

    def test_infrastructure_attempt_is_retained_and_stops_before_next_slot(self):
        code, terminal, calls = self.run_batch(infrastructure_at=2)
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 3)
        self.assertEqual(terminal['attempt_count'], 3)
        self.assertEqual(terminal['terminal_count'], 2)
        self.assertEqual(terminal['status_counts'], {'FAIL': 2, 'INFRASTRUCTURE_ERROR': 1, 'PENDING': 13})
        self.assertEqual(terminal['attempts'][-1]['record']['status'], 'INFRASTRUCTURE_ERROR')
        self.assertIsNotNone(terminal['attempts'][-1]['error'])

    def test_source_drift_stops_before_new_attempt(self):
        code, terminal, calls = self.run_batch(source_drift=True)
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(terminal['status_counts'], {'FAIL': 1, 'PENDING': 15})

    def test_preexisting_original_slot_refuses_fresh_batch_without_resume(self):
        self.run_batch(preexisting=True)

if __name__ == "__main__":
    unittest.main()
