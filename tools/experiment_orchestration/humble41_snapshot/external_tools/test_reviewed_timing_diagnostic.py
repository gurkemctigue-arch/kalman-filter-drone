"""Pure temporary/mocked fixtures; no WSL, ROS, project tests, or real action."""
import ast
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import humble33_development_observer01 as legacy
import humble33_diagnostic_checks01 as checks
import reviewed_timing_diagnostic as m


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def fixture_admission():
    root = '/root/uav_tracking_fullplan_fixture'
    evidence = {'summary': root + '/results/freeze_validation/build_validation_summary.json'}
    for action in ('build', 'validate'):
        evidence[action + '_terminal'] = m.generic.LINUX_EXTERNAL + '/reviewed_freeze_actions_fixture/' + action + '/action.terminal.json'
    return {'schema_version': 1, 'status': m.FINAL_STATUS, 'scope': m.SCOPE,
        'frozen_root': root, 'plan_path': root + '/results/' + m.PREFIX + '_seed004_matrix/plan.json',
        'source_commit': 'a' * 40, 'diagnostic_tools_canonical_sha256': 'b' * 64,
        'source_review': {'path': '/fixture/final_source_review.json', 'sha256': 'c' * 64},
        'experiment': {'class': 'person', 'group': 'stage1_velocity', 'seed': 4, 'duration_s': 75,
            'inference_image_size': 320, 'inference_threads': 2, 'prefix': m.PREFIX, 'slot': m.SLOT},
        'authorized_actions': ['plan', 'run'], 'formal_seed_use_authorized': False, 'readiness_claimed': False,
        'automatic_retry': False, 'automatic_next_action': False,
        'build_evidence': {name: {'path': path, 'sha256': 'd' * 64} for name, path in evidence.items()}}


def timing_report():
    return {'status': 'LOG_TIMING_ANALYZED_E2E_UNAVAILABLE', 'counts': {'outcomes': {'completed': 1}},
        'limits': {'source_e2e_to_estimator_or_state_status': 'UNKNOWN_REQUIRES_SEPARATE_DELIVERY_STATE_EVIDENCE',
            'runtime_success_claimed': False, 'readiness_claimed': False}}


class TemporaryFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='reviewed_timing_pure_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class AdmissionFixtures(TemporaryFixtures):
    def test_valid_schema_has_no_default_real_profile(self):
        value = fixture_admission()
        self.assertIs(m.validate_admission(value), value)
        self.assertIsNone(m.parser().parse_args(['run']).admission)

    def test_missing_or_draft_admission_refuses_before_writes_or_spawn(self):
        with patch.object(m.subprocess, 'Popen') as spawn, patch.object(m, 'write_new') as write:
            with redirect_stderr(io.StringIO()): self.assertEqual(m.main(['run']), 2)
            for value in ({}, dict(fixture_admission(), status='DRAFT')):
                self.assertRaises(ValueError, m.validate_admission, value)
            spawn.assert_not_called(); write.assert_not_called()

    def test_wrong_root_plan_action_tool_and_scientific_scope_reject(self):
        cases = [('plan_path', '/root/other/plan.json'), ('frozen_root', '/root/../escape'),
            ('source_commit', 'short'), ('diagnostic_tools_canonical_sha256', 'bad'),
            ('authorized_actions', ['plan', 'run', 'core']), ('formal_seed_use_authorized', True),
            ('readiness_claimed', True), ('automatic_retry', True), ('automatic_next_action', True)]
        for field, value in cases:
            with self.subTest(field=field):
                admission = fixture_admission(); admission[field] = value
                self.assertRaises(ValueError, m.validate_admission, admission)

    def test_wrong_slot_class_seed_duration_size_threads_and_malformed_evidence_reject(self):
        for field, value in [('class', 'car'), ('seed', 0), ('seed', 4.), ('duration_s', 30),
                ('inference_image_size', 640), ('inference_threads', 4), ('slot', 'other')]:
            admission = fixture_admission(); admission['experiment'][field] = value
            self.assertRaises(ValueError, m.validate_admission, admission)
        for value in (None, [], 'not-a-binding', {'path': '/foreign.json', 'sha256': 'd' * 64}):
            admission = fixture_admission(); admission['build_evidence']['summary'] = value
            self.assertRaises(ValueError, m.validate_admission, admission)

    def registry(self):
        admission = fixture_admission(); manifest = {'fixture': True}
        admission['diagnostic_tools_canonical_sha256'] = m.canonical(manifest)
        path = self.root / 'reviewed_timing_review_fixture.json'; put(path, admission)
        source = {'frozen_root': admission['frozen_root'], 'source_commit': admission['source_commit'],
            'flight_actions_authorized': False}
        return admission, manifest, path, source

    def load(self, admission, manifest, path, source, **changes):
        args = dict(path=path, expected_sha=m.sha(path), reviewed_tools=m.canonical(manifest), action='run',
            frozen_root=admission['frozen_root'], plan_path=admission['plan_path']); args.update(changes)
        with patch.object(m, 'EXTERNAL', self.root), patch.object(m, 'tool_manifest', return_value=manifest), \
                patch.object(m.generic, 'load_review', return_value=source):
            return m.load_admission(**args)

    def test_separate_admission_binds_source_without_promoting_build_review(self):
        admission, manifest, path, source = self.registry()
        actual, actual_source = self.load(admission, manifest, path, source)
        self.assertEqual(actual['_admission_binding']['sha256'], m.sha(path))
        self.assertIs(actual_source, source); self.assertFalse(source['flight_actions_authorized'])

    def test_registry_sha_explicit_root_plan_tool_and_source_mismatch(self):
        admission, manifest, path, source = self.registry()
        for args in ({'expected_sha': '0' * 64}, {'reviewed_tools': '0' * 64},
                {'frozen_root': '/root/other'}, {'plan_path': '/root/other/plan.json'}):
            self.assertRaises(ValueError, self.load, admission, manifest, path, source, **args)
        for key in ('frozen_root', 'source_commit'):
            wrong = dict(source); wrong[key] = 'foreign'
            self.assertRaises(ValueError, self.load, admission, manifest, path, wrong)
        foreign = self.root / 'arbitrary.json'; put(foreign, admission)
        self.assertRaises(ValueError, self.load, admission, manifest, foreign, source)

    def test_transitive_import_closure_is_explicit_and_pin_changed_helper_rejects(self):
        graph = m.dependency_graph()
        self.assertEqual(graph['humble33_development_observer01.py'], ['humble33_review_guard.py'])
        self.assertEqual(graph['humble33_diagnostic_checks01.py'], ['humble33_review_guard.py'])
        self.assertEqual(graph['analyze_humble33_inference_timing01.py'], [])
        with patch.object(m, 'GENERIC_CANONICAL', '0' * 64):
            self.assertRaisesRegex(ValueError, 'toolchain changed', m.tool_manifest)


class BuildFixtures(TemporaryFixtures):
    def fixture(self):
        root = self.root / 'frozen'; root.mkdir(); directory = root / 'results/freeze_validation'; directory.mkdir(parents=True)
        (root / 'ros2_ws/install').mkdir(parents=True)
        frozen = {'freeze_source_sha256': 'e' * 64}; original = {'retained_failed_predecessor': True}
        review = {'frozen_root': str(root), '_review_binding': {'path': '/fixture/review.json', 'sha256': 'f' * 64}, 'files': {}}
        review['additional_import_modules'] = ['uav_tracking_nodes.inference_timing', 'uav_tracking_nodes.inference_worker']
        modules = {}
        for index, name in enumerate(set(m.generic.MODULES) | set(review['additional_import_modules'])):
            path = root / ('module' + str(index) + '.py'); path.write_text('# fixture\n')
            modules[name] = SimpleNamespace(__file__=str(path)); review['files'][path.relative_to(root).as_posix()] = m.sha(path)
        (directory / 'unittest.log').write_text('Ran 1 test\nOK (skipped=5)\n')
        put(directory / 'generated_message_roundtrip.json', {'status': 'PASS', 'source_binding_after_roundtrip': frozen,
            'scope': 'ACTUAL_BUILT_ROS_MESSAGE_SERIALIZATION_ONLY_NO_NODE_NO_SIMULATION',
            'checks': dict.fromkeys(m.generic.CDR_CHECK_NAMES, True), 'execution_count': 1})
        put(directory / 'import_isolation.json', {'root': str(root), 'isolated': True,
            'module_files': {name: value.__file__ for name, value in modules.items()},
            'ros_package_prefixes': dict.fromkeys(m.generic.PACKAGES, str(root / 'ros2_ws/install')),
            'selected_bridge_overlay': m.generic.BRIDGE, 'bridge_runtime_validation': {'status': 'PASS'}})
        fastcdr = {'status': 'MATCHES_HUMBLE_SYSTEM_FASTCDR', 'inputs_sha256': '9' * 64}
        put(directory / 'fastcdr_provenance.json', fastcdr)
        summary = {'status': 'PASS', 'returncode': 0, 'tests': 1, 'skipped': 5, 'execution_count': 1,
            'source_unchanged': True, 'source_binding_before': frozen, 'source_binding_after': frozen,
            'final_review': review['_review_binding'], 'toolchain_canonical_sha256': m.GENERIC_CANONICAL,
            'freeze_source_sha256': frozen['freeze_source_sha256'], 'four_packages_built': True,
            'module_ament_isolation': True, 'closed_original_evidence_before': original,
            'closed_original_evidence_after': original, 'closed_original_evidence_unchanged': True,
            'formal_seeds_consumed': False, 'bounded_action_terminal_must_be_PASS': True,
            'suite_log_sha256': m.sha(directory / 'unittest.log'),
            'generated_message_roundtrip_sha256': m.sha(directory / 'generated_message_roundtrip.json')}
        summary_path = directory / 'build_validation_summary.json'; put(summary_path, summary)
        evidence = {'summary': m.metadata_binding(summary_path, json_only=True)}
        for action in ('build', 'validate'):
            terminal = self.root / action / 'action.terminal.json'
            binding = {'source': frozen, 'review': review['_review_binding'], 'closed_original_evidence': original}
            put(terminal, {'scope': 'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE',
                'action': action, 'status': 'PASS', 'direct_child_returncode': 0, 'execution_count': 1,
                'binding_before': binding, 'binding_after': binding,
                'cleanup': {'actual_proc_group_empty': True, 'direct_child_reaped': True, 'residual_processes': []}})
            evidence[action + '_terminal'] = m.metadata_binding(terminal, json_only=True)
        return {'build_evidence': evidence}, review, frozen, original, directory, modules, fastcdr

    def invoke(self, data, importer=None):
        admission, review, frozen, original, directory, modules, fastcdr = data
        with ExitStack() as stack:
            stack.enter_context(patch.object(m.generic, 'frozen_binding', return_value=frozen))
            stack.enter_context(patch.object(m.generic, 'verify_closed_capsule', return_value=original))
            stack.enter_context(patch.object(m.generic, 'validation_dir', return_value=directory))
            stack.enter_context(patch.object(m.generic, 'verify_fastcdr', return_value=fastcdr))
            stack.enter_context(patch.object(m.importlib, 'import_module', side_effect=importer or modules.__getitem__))
            stack.enter_context(patch.object(m.subprocess, 'check_output', return_value=str(Path(review['frozen_root']) / 'ros2_ws/install')))
            stack.enter_context(patch.dict(os.environ, dict(checks.RUNTIME_ENVIRONMENT,
                PATH='/root/uav_humble22/agent_install/bin:/fixture/bin',
                LD_LIBRARY_PATH='/root/uav_humble22/agent_install/lib:/fixture/overlay/lib')))
            stack.enter_context(redirect_stdout(io.StringIO()))
            return m.checked_build(admission, review, checks)

    def change(self, data, key, mutate):
        evidence = data[0]['build_evidence'][key]; path = Path(evidence['path'])
        value = m.read_small(path); mutate(value); put(path, value); evidence['sha256'] = m.sha(path)

    def test_actual_same_source_build_suite_and_eleven_cdr_checks_gate(self):
        data = self.fixture(); before = {p: p.read_bytes() for p in data[4].iterdir()}
        result = self.invoke(data)
        self.assertEqual(result['source'], data[2]); self.assertEqual(result['closed_original_evidence'], data[3])
        self.assertEqual(before, {p: p.read_bytes() for p in data[4].iterdir()})

    def test_actual_failed_build_or_validate_refuses_even_if_summary_pass(self):
        data = self.fixture()
        for key in ('build_terminal', 'validate_terminal'):
            original = deepcopy(m.read_small(data[0]['build_evidence'][key]['path']))
            self.change(data, key, lambda value: value.update(status='FAILED', direct_child_returncode=1))
            self.assertRaisesRegex(ValueError, 'did not PASS', self.invoke, data)
            put(Path(data[0]['build_evidence'][key]['path']), original)
            data[0]['build_evidence'][key]['sha256'] = m.sha(data[0]['build_evidence'][key]['path'])

    def test_nonzero_suite_wrong_source_or_incomplete_isolation_reject(self):
        data = self.fixture(); original = deepcopy(m.read_small(data[0]['build_evidence']['summary']['path']))
        for field, value in [('returncode', 1), ('skipped', 0), ('source_binding_after', {}), ('execution_count', 2)]:
            self.change(data, 'summary', lambda summary: summary.update({field: value}))
            self.assertRaises(ValueError, self.invoke, data)
            put(Path(data[0]['build_evidence']['summary']['path']), original)
            data[0]['build_evidence']['summary']['sha256'] = m.sha(data[0]['build_evidence']['summary']['path'])
        isolation = m.read_small(data[4] / 'import_isolation.json'); isolation['module_files'].pop(next(iter(isolation['module_files'])))
        put(data[4] / 'import_isolation.json', isolation)
        self.assertRaisesRegex(ValueError, 'isolation missing', self.invoke, data)

    def test_changed_original_suite_log_is_rejected(self):
        data = self.fixture(); (data[4] / 'unittest.log').write_text('fake PASS')
        self.assertRaisesRegex(ValueError, 'suite/CDR log changed', self.invoke, data)

    def test_entry_rechecks_closed_capsule_as_well_as_frozen_source(self):
        admission = fixture_admission(); admission['_admission_binding'] = {'path': '/fixture/admission.json', 'sha256': 'a' * 64}
        manifest = {}; admission['diagnostic_tools_canonical_sha256'] = m.canonical(manifest)
        built = {'source': {'same': True}, 'closed_original_evidence': {'original': True}, 'bound_build_metadata': {}}
        with patch.object(m, 'metadata_binding', return_value=admission['_admission_binding']), \
                patch.object(m, 'tool_manifest', return_value=manifest), \
                patch.object(m.generic, 'action_binding', return_value={'source': built['source'], 'closed_original_evidence': {'changed': True}}):
            self.assertRaisesRegex(ValueError, 'closed original', m.entry_binding, admission, {}, built)

    def test_import_environment_mutation_is_recorded_and_exactly_restored(self):
        data = self.fixture(); before = '/root/uav_humble22/agent_install/lib:/fixture/overlay/lib'
        cv2_prefix = '/fixture/venv/site-packages/cv2/../../lib64:'
        def importer(name):
            if name == 'uav_tracking_nodes.detector_node':
                os.environ['LD_LIBRARY_PATH'] = cv2_prefix + os.environ['LD_LIBRARY_PATH']
                os.environ['TIMING_FIXTURE_OTHER'] = 'import_keeps_this'
            return data[5][name]
        result = self.invoke(data, importer)
        report = result['module_import_environment']
        self.assertEqual(report['before_import_ld_library_path'], before)
        self.assertEqual(report['after_import_ld_library_path'], cv2_prefix + before)
        self.assertEqual(report['restored_ld_library_path'], before)
        self.assertEqual(report['effects'], [{'module': 'uav_tracking_nodes.detector_node', 'before': before, 'after': cv2_prefix + before}])
        self.assertEqual(report['contract_before'], report['contract_after_restore'])

    def test_invalid_entry_environment_fails_before_source_or_module_access(self):
        with patch.dict(os.environ, {'LD_LIBRARY_PATH': '/foreign/lib', 'PATH': '/foreign/bin'}), \
                patch.object(m.generic, 'frozen_binding') as frozen, patch.object(m.importlib, 'import_module') as imported:
            self.assertRaises(ValueError, m.checked_build, {}, {}, checks)
            frozen.assert_not_called(); imported.assert_not_called()

    def test_import_exception_restores_exact_ld_without_resetting_other_environment(self):
        data = self.fixture(); before = '/root/uav_humble22/agent_install/lib:/fixture/overlay/lib'; seen = []
        real_contract = checks.require_environment_contract
        def observed_contract():
            result = real_contract(); seen.append((os.environ['LD_LIBRARY_PATH'], os.environ.get('TIMING_FIXTURE_OTHER')))
            return result
        def importer(name):
            if name == 'uav_tracking_nodes.detector_node':
                os.environ['LD_LIBRARY_PATH'] = '/fixture/cv2/lib64:' + before
                os.environ['TIMING_FIXTURE_OTHER'] = 'keep_on_exception'
                raise ImportError('fixture module import fails after changing LD')
            return data[5][name]
        with patch.object(checks, 'require_environment_contract', side_effect=observed_contract):
            self.assertRaisesRegex(ImportError, 'fixture module import', self.invoke, data, importer)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[-1], (before, 'keep_on_exception'))

    def test_import_contract_violation_outside_ld_remains_a_failure(self):
        data = self.fixture()
        def importer(name):
            if name == 'uav_tracking_nodes.detector_node':
                os.environ['LD_LIBRARY_PATH'] = '/fixture/cv2/lib64:' + os.environ['LD_LIBRARY_PATH']
                os.environ['PATH'] = '/foreign/bin:' + os.environ['PATH']
            return data[5][name]
        self.assertRaisesRegex(ValueError, 'path prefix is missing: PATH', self.invoke, data, importer)


class ObserverFixtures(TemporaryFixtures):
    def sample(self, stamp):
        return {'latest_sample_monotonic_s': stamp, 'sample_age_wall_s': 0., 'max_sample_age_wall_s': 10.}

    def clock(self, seconds):
        return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)).isoformat()

    def fixture(self, count=1):
        directory = self.root / 'observer'; root = self.root / 'actual_frozen'; items = []
        for index in range(1, count + 1):
            start = 100. if index == 1 else 5500.
            first = start + 1; finish = (5504. if count > 1 else 120.) if index == 1 else 5520.
            folder = directory / f'session_{index:03d}'; (folder / 'runtime_health').mkdir(parents=True)
            (folder / 'observer_console.log').write_text('fixture log\n')
            (folder / 'runtime_health/health.jsonl').write_text('{}\n')
            original = {'finished_utc': self.clock(finish), 'command': m.observer_command(root, folder),
                'observer_exit_code': 0, 'observer_forced_stop': False, 'ended_before_requested_stop': False,
                'driver_exception': False, 'final_fresh_sample': self.sample(finish - .1),
                'final_sample_error': None, 'healthy_cleanup': True}
            path = folder / 'execution_terminal.json'; put(path, original)
            items.append({'index': index, 'directory': str(folder), 'started_utc': self.clock(start),
                'started_monotonic_s': start, 'first_fresh_utc': self.clock(first), 'first_fresh_monotonic_s': first,
                'first_fresh_sample': self.sample(first - .1), 'finished_utc': self.clock(finish),
                'finished_monotonic_s': finish, 'terminal': original, 'terminal_binding': m.metadata_binding(path, json_only=True),
                'artifacts': {name: {'path': str(folder / name), 'sha256': m.sha(folder / name)}
                    for name in ('observer_console.log', 'runtime_health/health.jsonl')}})
        rotations = []
        if count == 2:
            rotations.append({'old_index': 1, 'new_index': 2, 'new_first_fresh_utc': items[1]['first_fresh_utc'],
                'old_last_fresh_sample': self.sample(5503.), 'new_first_fresh_sample': self.sample(5502.),
                'old_finished_utc': items[0]['finished_utc'], 'new_fresh_after_old_finish': self.sample(5504.5),
                'completed_utc': self.clock(5505.), 'completed_monotonic_s': 5505.})
        terminal = {'schema_version': 1, 'scope': legacy.SCOPE, 'started_utc': self.clock(99.),
            'finished_utc': self.clock(5530.), 'rotation_wall_s': 5400., 'session_duration_wall_s': 7200,
            'max_sample_age_wall_s': 10., 'sessions': items, 'rotations': rotations,
            'driver_exception': False, 'healthy_cleanup': True}
        put(directory / 'execution_terminal.json', terminal)
        return directory, root, terminal

    def test_explicit_root_command_and_cwd_leave_legacy_global_unchanged(self):
        old_root = legacy.ROOT; observer_type, _ = m.observer_types(legacy)
        observer = observer_type(self.root / 'live', self.root / 'frozen')
        process = Mock(); process.poll.return_value = None
        with patch.object(m.subprocess, 'Popen', return_value=process) as spawn, \
                patch.object(observer, 'check', return_value=self.sample(1.)):
            self.assertIs(observer.__enter__(), observer)
            observer.console.close()
        self.assertEqual(spawn.call_args.kwargs['cwd'], self.root / 'frozen')
        self.assertEqual(observer.command[2], str(self.root / 'frozen/scripts/observe_runtime_health.py'))
        self.assertEqual(legacy.ROOT, old_root)

    def test_adapter_retains_original_check_finish_rotation_and_cleanup(self):
        observer, rolling = m.observer_types(legacy)
        self.assertIs(observer.check, legacy.IndependentObserver.check)
        self.assertIs(observer.finish, legacy.IndependentObserver.finish)
        for name in ('check', 'close_session', 'finish', '__exit__'):
            self.assertIs(getattr(rolling, name), getattr(legacy.RollingIndependentObserver, name))

    def test_one_and_two_session_original_receipts_validate_without_mutation(self):
        for count in (1, 2):
            with self.subTest(count=count), tempfile.TemporaryDirectory(dir=self.root) as path:
                previous = self.root; self.root = Path(path)
                directory, root, terminal = self.fixture(count)
                before = {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()}
                self.assertEqual(m.validate_observer_root(terminal, directory, root, legacy)['session_count'], count)
                self.assertEqual(before, {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()})
                self.root = previous

    def test_port_is_original_validator_with_only_root_command_and_alias_changes(self):
        original = (m.EXTERNAL / 'humble33_development_observer01.py').read_text(encoding='utf-8')
        candidate = (m.EXTERNAL / 'reviewed_timing_diagnostic.py').read_text(encoding='utf-8')
        original_node = next(n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef) and n.name == 'validate_rolling_observer')
        new_node = next(n for n in ast.parse(candidate).body if isinstance(n, ast.FunctionDef) and n.name == 'validate_observer_root')
        class Normalize(ast.NodeTransformer):
            def visit_Name(self, node):
                node.id = {'observer_scope': 'SCOPE', 'rotation_wall_s': 'ROTATE_WALL_S'}.get(node.id, node.id)
                return node
            def visit_Call(self, node):
                self.generic_visit(node)
                if isinstance(node.func, ast.Name) and node.func.id == 'observer_command':
                    node.func.id = 'command'; node.args = node.args[1:]
                return node
        self.assertEqual([ast.dump(n, include_attributes=False) for n in original_node.body],
            [ast.dump(Normalize().visit(n), include_attributes=False) for n in new_node.body[3:]])

    def test_wrong_root_or_changed_log_rejects(self):
        directory, root, terminal = self.fixture()
        self.assertRaises(ValueError, m.validate_observer_root, terminal, directory, self.root / 'foreign', legacy)
        (directory / 'session_001/runtime_health/health.jsonl').write_text('changed\n')
        self.assertRaises(ValueError, m.validate_observer_root, terminal, directory, root, legacy)

    def test_stale_freshness_original_deadline_overlap_and_forced_stop_reject(self):
        directory, root, original = self.fixture(2)
        for kind in ('stale', 'deadline', 'overlap', 'forced', 'rotation'):
            terminal = deepcopy(original); item = terminal['sessions'][0]
            if kind == 'stale': item['first_fresh_sample']['sample_age_wall_s'] = 11.
            if kind == 'deadline': item['finished_monotonic_s'] = item['started_monotonic_s'] + 7200.
            if kind == 'overlap': terminal['sessions'][1]['first_fresh_monotonic_s'] = 5506.
            if kind == 'rotation': terminal['rotation_wall_s'] = 1000.
            if kind == 'forced':
                item['terminal']['observer_forced_stop'] = True
                path = Path(item['terminal_binding']['path']); put(path, item['terminal'])
                item['terminal_binding']['sha256'] = m.sha(path)
            put(directory / 'execution_terminal.json', terminal)
            self.assertRaises(ValueError, m.validate_observer_root, terminal, directory, root, legacy)
            if kind == 'forced':
                put(Path(original['sessions'][0]['terminal_binding']['path']), original['sessions'][0]['terminal'])


class ExecutionFixtures(TemporaryFixtures):
    def plan_data(self):
        trial = {'id': m.SLOT, 'seed': 4, 'duration_s': 75, 'model': 'models/yolo11n.pt',
            'inference_image_size': 320, 'inference_threads': 2, 'evaluations': ['a', 'b', 'c']}
        plan = {'mode': 'PROBE', 'prefix': m.PREFIX, 'frozen_root': '/root/fixture', 'selected_seeds': [4],
            'selected_classes': ['person'], 'selected_groups': ['stage1_velocity'], 'trials': [trial],
            'trial_timeout_s': 1800., 'evaluation_timeout_s': 240., 'plan_sha256': 'a' * 64}
        return plan, trial

    def test_outer_budget_includes_every_original_evaluator_and_margin(self):
        plan, trial = self.plan_data(); result = m.outer_allowance(plan, trial)
        self.assertEqual(result['outer_allowance_s'], 1800 + 3 * 240 + 280 + 120)
        self.assertEqual(result['evaluation_count'], 3)
        self.assertEqual(result['original_child_cleanup_graces_s'], [240, 30, 10])
        # A last evaluator can consume its complete original timeout followed by
        # all SIGINT/SIGTERM/SIGKILL graces and still leave the external margin.
        last_child_cleanup_end = plan['trial_timeout_s'] + len(trial['evaluations']) * plan['evaluation_timeout_s'] + 240 + 30 + 10
        self.assertEqual(result['outer_allowance_s'] - last_child_cleanup_end, 120.)
        for value in (True, float('inf'), float('nan'), 0, -1):
            self.assertRaises(ValueError, m.outer_allowance, dict(plan, trial_timeout_s=value), trial)

    def test_original_plan_has_exact_one_pending_slot_and_resources(self):
        plan, trial = self.plan_data(); path = self.root / 'plan.json'; put(path, plan)
        runner = Mock(); runner.read_slots.return_value = {m.SLOT: {'status': 'PENDING'}}; checks = Mock()
        admission = {'frozen_root': '/root/fixture', 'plan_path': str(path)}
        with patch.object(m.generic, 'runner_at', return_value=runner):
            self.assertEqual(m.plan_checked(admission, checks)[2], trial)
            checks.require_plan_resources.assert_called_once_with(plan)
            for field, value in [('selected_seeds', [0]), ('selected_classes', ['car']), ('trials', [trial, trial])]:
                put(path, dict(plan, **{field: value})); self.assertRaises(ValueError, m.plan_checked, admission, checks)
            changed = deepcopy(plan); changed['trials'][0]['inference_threads'] = 4; put(path, changed)
            self.assertRaises(ValueError, m.plan_checked, admission, checks)

    def test_owned_command_once_preserves_all_original_cleanup_graces(self):
        process = Mock(); process.poll.side_effect = [None, None, None, None, 0]
        process.wait.side_effect = [m.subprocess.TimeoutExpired('fixture', 240), m.subprocess.TimeoutExpired('fixture', 30), 0]
        observer = Mock(); observer.check.side_effect = RuntimeError('fixture stop')
        with patch.object(m.subprocess, 'Popen', return_value=process) as spawn, patch.object(m.signal, 'SIGKILL', 9, create=True):
            result = m.execute_owned(['fixture_only_no_real_child'], self.root / 'outer.log', observer, 600., self.root)
        spawn.assert_called_once(); self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertEqual([item['grace_s'] for item in result['outer_cleanup_actions']], [240, 30, 10])
        self.assertEqual([call.kwargs['timeout'] for call in process.wait.call_args_list], [240, 30, 10])
        self.assertRaises(ValueError, m.clean_execution, result, ['fixture_only_no_real_child'])

    def test_complete_timing_required_but_e2e_stays_unknown(self):
        m.require_timing_evidence(timing_report())
        for status in ('INCOMPLETE_TIMING_EVIDENCE', 'NO_TIMING_SAMPLES'):
            self.assertRaises(ValueError, m.require_timing_evidence, dict(timing_report(), status=status))
        report = timing_report(); report['limits']['source_e2e_to_estimator_or_state_status'] = 'KNOWN'
        self.assertRaises(ValueError, m.require_timing_evidence, report)

    def test_bounded_timing_report_refuses_oversize_before_writing_and_never_overwrites(self):
        path = self.root / 'timing.json'
        with patch.object(m.generic, 'MAX_SMALL', 100):
            self.assertRaises(ValueError, m.save_timing_report, path, {'blob': 'x' * 200})
        self.assertFalse(path.exists()); m.save_timing_report(path, timing_report())
        self.assertRaises(FileExistsError, m.save_timing_report, path, timing_report())

    def test_original_failed_slot_is_retained_once_without_retry_or_success_claim(self):
        plan, trial = self.plan_data(); admission = {'frozen_root': str(self.root), 'plan_path': str(self.root / 'matrix/plan.json')}
        selected = m.paths(admission); selected['plan_driver'].mkdir(parents=True); put(selected['plan'], plan)
        trial['directory'] = str(self.root / 'trial'); Path(trial['directory']).mkdir()
        log = Path(trial['directory']) / 'ros.log'; log.write_text('fixture log')
        record = {'status': 'FAIL', 'artifact_hashes': {'ros.log': m.sha(log)}}
        binding = {'source': 'same'}; built = {'source': 'same'}
        receipt = {'returncode': 0, 'action': 'plan', 'flights_started': 0, 'diagnostic_entry_binding': binding,
            'initial_pending': {'plan': m.metadata_binding(selected['plan'], json_only=True), 'plan_sha256': plan['plan_sha256'], 'slot': m.SLOT, 'status': 'PENDING'}}
        put(selected['plan'].parent / 'diagnostic_plan_receipt01.json', receipt)
        put(selected['plan_driver'] / 'execution_terminal.json', receipt)
        runner = Mock(); runner.TERMINAL = {'PASS', 'FAIL'}; runner.simulation_processes.return_value = []
        machine_lock = threading.Lock(); owners = []
        @contextmanager
        def original_machine_lock(directory):
            # Model two independent LOCK_EX|LOCK_NB opens of the same machine
            # lock: an outer acquisition would make the original child fail.
            if not machine_lock.acquire(blocking=False):
                raise BlockingIOError('original runner machine lock already held')
            owners.append(str(directory))
            try: yield
            finally: machine_lock.release()
        runner.run_lock.side_effect = original_machine_lock
        runner.read_slots.return_value = {m.SLOT: record}
        runner.runtime_configuration.return_value = {'errors': []}
        checks = Mock(); checks.terminal_binding.return_value = {'original': True}
        for name in ('bridge_evidence', 'process_evidence', 'closed75_archive'):
            getattr(checks, name).return_value = {'fixture': True}
        analyzer = Mock(); analyzer.analyze.return_value = timing_report()
        modules = {'humble33_diagnostic_checks01': checks, 'humble33_development_observer01': legacy,
            'analyze_humble33_inference_timing01': analyzer}
        observer = SimpleNamespace(_finished={'fixture': True})
        class FixtureObserver:
            def __init__(self, *args): pass
            def __enter__(self): return observer
            def __exit__(self, *args): return False
            def check(self): return None
        observer.check = Mock()
        with ExitStack() as stack:
            stack.enter_context(patch.object(m, 'plan_checked', return_value=(runner, plan, trial, {'status': 'PENDING'})))
            stack.enter_context(patch.object(m, 'entry_binding', return_value=binding))
            stack.enter_context(patch.object(m, 'validate_observer_root'))
            stack.enter_context(patch.object(m, 'observer_types', return_value=(None, FixtureObserver)))
            stack.enter_context(patch.object(m, 'final_cleanup', return_value={'final_errors': []}))
            def child_execute(*args):
                with runner.run_lock('original_child_run_plan'):
                    return {'returncode': 0}
            execute = stack.enter_context(patch.object(m, 'execute_owned', side_effect=child_execute))
            stack.enter_context(patch.object(m, 'clean_execution'))
            self.assertEqual(m.run_main(admission, {}, built, modules, {}), 0)
            execute.assert_called_once()
            self.assertEqual(owners, ['original_child_run_plan'])
            runner.run_lock.assert_called_once_with('original_child_run_plan')
            terminal = m.read_small(selected['run_driver'] / 'execution_terminal.json')
            self.assertEqual(terminal['slot']['status'], 'FAIL')
            self.assertFalse(terminal['readiness_claimed']); self.assertFalse(terminal['automatic_next_action'])
            self.assertRaisesRegex(ValueError, 'no retry', m.run_main, admission, {}, built, modules, {})
            execute.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
