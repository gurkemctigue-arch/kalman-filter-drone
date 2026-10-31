"""Temporary Windows/stdlib fixtures; never execute a real project action."""
from contextlib import nullcontext, redirect_stderr
from copy import deepcopy
import ast
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import reviewed_freeze_build as m


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def fixture_review():
    files = {'README.md': 'a' * 64, 'config/px4_magnetic_runtime.json': m.MAGNETIC_SHA}
    return {'schema_version': 1, 'status': m.FINAL_STATUS, 'scope': m.SCOPE,
        'source_root': '/mnt/d/uav_fixture', 'frozen_root': '/root/uav_tracking_fullplan_fixture',
        'results_root': '/mnt/d/uav_fixture/results/frozen_fullplan_fixture', 'source_commit': 'a' * 40,
        'toolchain_canonical_sha256': 'b' * 64, 'files': files, 'classified_source_hashes': {'README.md': 'a' * 64},
        'baseline': {'source_commit': 'b' * 40, 'root': '/root/uav_tracking_fullplan_v4_humble33',
            'manifest_path': '/mnt/d/uav_fixture/results/frozen_fullplan_v4_humble33/freeze_validation/source_freeze_manifest.json',
            'manifest_sha256': 'c' * 64, 'files_canonical_sha256': 'd' * 64},
        'allowed_delta': {'changed': ['README.md'], 'added': [], 'removed': []},
        'source_overrides': {'config/px4_magnetic_runtime.json': {'path': m.MAGNETIC_PATH, 'sha256': m.MAGNETIC_SHA}},
        'runtime': {'distro': 'UAVHumble22', 'ros': 'humble', 'px4_root': m.PX4_ROOT, 'bridge_overlay': m.BRIDGE,
            'python': m.PYTHON, 'invariant_policy': 'HUMBLE33_SAFETY_AND_RESOURCE_CONTRACTS_UNCHANGED'},
        'action_timeouts_s': dict(m.ACTIONS), 'expected_full_suite_skips': 5, 'authorized_actions': list(m.ACTIONS),
        'closed_evidence': {'path': '/mnt/d/WSL/UAVHumble22-validation/closed_fixture.json', 'sha256': 'e' * 64},
        'additional_import_modules': [], 'formal_seed_use_authorized': False, 'flight_actions_authorized': False,
        'automatic_next_action': False}


class ReviewFixtures(unittest.TestCase):
    def test_final_profile_has_explicit_paths_commit_and_no_flight(self):
        value = fixture_review()
        self.assertIs(m.validate_review(value), value)
        for change in ({'status': 'DRAFT'}, {'source_commit': 'HEAD'}, {'formal_seed_use_authorized': True},
                {'flight_actions_authorized': True}, {'automatic_next_action': True}, {'expected_full_suite_skips': True}):
            with self.subTest(change=change):
                self.assertRaises(ValueError, m.validate_review, {**deepcopy(value), **change})

    def test_unsafe_or_historical_destination_is_refused(self):
        for root in ('/root/uav_tracking_fullplan_v4_humble32', '/root/uav_tracking_fullplan_v4_humble33',
                '/root/uav_tracking_fullplan_fixture/../old', '/tmp/free', '/root/uav_tracking_fullplan_fixture\n'):
            value = fixture_review(); value['frozen_root'] = root
            self.assertRaises(ValueError, m.validate_review, value)
        self.assertRaises(ValueError, m.absolute, '/mnt/d/source\nother')
        value = fixture_review(); value['results_root'] += '_other'
        self.assertRaises(ValueError, m.validate_review, value)

    def test_exact_delta_override_source_and_runtime_contract(self):
        changes = (lambda v: v['allowed_delta'].update(changed=['README.md', 'README.md']),
            lambda v: v['allowed_delta'].update(added=['README.md']),
            lambda v: v['allowed_delta'].update(changed=['../outside']),
            lambda v: v['files'].update({'results/old.json': 'f' * 64}),
            lambda v: v['source_overrides']['config/px4_magnetic_runtime.json'].update(path='/tmp/fake'),
            lambda v: v['runtime'].update(px4_root='/tmp/px4'),
            lambda v: v['action_timeouts_s'].update(build=1.),
            lambda v: v.update(additional_import_modules=['subprocess']))
        for change in changes:
            value = fixture_review(); change(value)
            self.assertRaises(ValueError, m.validate_review, value)

    def test_all_mutable_actions_without_real_review_reject_before_spawn_or_write(self):
        with (patch.object(m, 'launch', side_effect=AssertionError('no launch')),
                patch.object(m, 'write_new', side_effect=AssertionError('no write')),
                patch.object(m.subprocess, 'Popen', side_effect=AssertionError('no process'))):
            for action in m.ACTIONS:
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(m.main([action]), 2)

    def test_explicit_review_and_tools_sha_are_required_without_publishing(self):
        with tempfile.TemporaryDirectory(prefix='generic_freeze_review_fixture_') as temp:
            folder = Path(temp); path = folder / 'reviewed_freeze_review_fixture.json'
            value = fixture_review(); tool = {'fixture_tools': True}
            value['toolchain_canonical_sha256'] = m.canonical(tool); put(path, value)
            with patch.object(m, 'EXTERNAL', folder), patch.object(m, 'tools_manifest', return_value=tool):
                loaded = m.load_review(path, m.sha(path), 'copy')
                self.assertEqual(loaded['_review_binding']['sha256'], m.sha(path))
                self.assertRaises(ValueError, m.load_review, path, '0' * 64, 'copy')
                put(path, {**value, 'status': 'PREPARED_ONLY'})
                self.assertRaises(ValueError, m.load_review, path, m.sha(path), 'copy')

    def test_complete_pinned_import_graph_is_four_files_without_legacy_actions(self):
        manifest = m.tools_manifest()
        graph = manifest['borrowed_external_import_graph']
        self.assertEqual(graph['bounded_humble33_action.py'], ['humble33_review_guard.py'])
        self.assertEqual(graph['humble33_review_guard.py'], ['humble33_original32_retention01.py'])
        self.assertEqual(graph['humble33_original32_retention01.py'], [])
        self.assertEqual(graph['humble33_skip_contract.py'], [])
        self.assertFalse(manifest['legacy_cli_or_production_binding_called'])
        deps = m.dependencies()
        self.assertEqual(set(deps), {name.removesuffix('.py') for name in m.DEPENDENCIES})

    def test_changed_dependency_rejects_before_import(self):
        original = m.sha
        def changed(path):
            return '0' * 64 if Path(path).name == 'bounded_humble33_action.py' else original(path)
        with patch.object(m, 'sha', side_effect=changed), patch.object(m.importlib, 'import_module') as imported:
            self.assertRaises(ValueError, m.dependencies)
            imported.assert_not_called()

    def test_metadata_entrypoints_reject_payload_before_hashing(self):
        with tempfile.TemporaryDirectory(prefix='generic_freeze_payload_refusal_') as temp:
            payload = Path(temp) / 'rosbag.db3'; payload.write_bytes(b'fixture payload never read')
            review = fixture_review()
            review['baseline']['manifest_path'] = str(payload)
            review['closed_evidence']['path'] = str(payload)
            review['_review_binding'] = {'path': str(payload), 'sha256': '0' * 64}
            with patch.object(m, 'sha', side_effect=AssertionError('no payload hash')):
                self.assertRaises(ValueError, m.baseline_manifest, review)
                self.assertRaises(ValueError, m.verify_closed_capsule, review)
                self.assertRaises(ValueError, m.action_binding, review, 'prepare')
            large = Path(temp) / 'large.json'; large.write_text('{"fixture":"long"}')
            with patch.object(m, 'MAX_SMALL', 8), patch.object(m, 'sha', side_effect=AssertionError('no oversized hash')):
                review['baseline']['manifest_path'] = str(large)
                self.assertRaises(ValueError, m.baseline_manifest, review)


class SourceAndBuildFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='generic_freeze_source_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def candidate(self, data=b'new\n'):
        source = self.root / 'source'; source.mkdir()
        (source / 'README.md').write_bytes(data)
        magnetic = self.root / 'magnetic.json'; magnetic.write_bytes(b'{"fixture":true}\n')
        review = fixture_review(); review['source_root'] = str(source)
        review['files'] = {'README.md': m.sha(source / 'README.md'), 'config/px4_magnetic_runtime.json': m.sha(magnetic)}
        review['source_overrides'] = {'config/px4_magnetic_runtime.json': {'path': str(magnetic), 'sha256': m.sha(magnetic)}}
        previous = {**review['files'], 'README.md': '0' * 64}
        manifest = {'source_commit': review['baseline']['source_commit'], 'source_root': review['baseline']['root'],
            'files': previous, 'freeze_source_sha256': m.canonical(previous)}
        path = self.root / 'baseline.json'; put(path, manifest)
        review['baseline'].update(manifest_path=str(path), manifest_sha256=m.sha(path), files_canonical_sha256=m.canonical(previous))
        return review, magnetic

    def git_result(self, command, **kwargs):
        if 'rev-parse' in command: return 'a' * 40 + '\n'
        if 'status' in command: return ''
        if 'diff' in command: return b'README.md\0' if '--diff-filter=M' in command else b''
        if 'show' in command: return b'new\n'
        raise AssertionError(command)

    def test_real_byte_map_and_git_blob_equality_including_crlf(self):
        review, magnetic = self.candidate()
        with (patch.object(m, 'MAGNETIC_PATH', str(magnetic)), patch.object(m.subprocess, 'check_output', side_effect=self.git_result),
                patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=0))):
            bound = m.candidate_binding(review)
            self.assertTrue(bound['changed_or_added_blob_pairs']['README.md']['actual_equals_git_blob'])
            self.assertFalse(bound['copy_normalizes_line_endings'])
            (Path(review['source_root']) / 'README.md').write_bytes(b'new\r\n')
            review['files']['README.md'] = m.sha(Path(review['source_root']) / 'README.md')
            self.assertRaisesRegex(ValueError, 'physical bytes differ', m.candidate_binding, review)

    def test_unapproved_file_change_is_not_hidden_by_clean_git(self):
        review, _ = self.candidate()
        review['files']['unapproved.py'] = 'f' * 64
        self.assertRaisesRegex(ValueError, 'exact independently reviewed delta', m.baseline_manifest, review)

    def test_unicode_git_delta_uses_nul_paths_without_quoted_name_loss(self):
        review, magnetic = self.candidate()
        name = 'fixture_目标.py'; data = b'print(1)\n'
        (Path(review['source_root']) / name).write_bytes(data)
        review['files'][name] = m.sha(Path(review['source_root']) / name)
        review['allowed_delta']['added'] = [name]
        def git(command, **kwargs):
            if 'diff' in command and '--diff-filter=A' in command:
                self.assertIn('-z', command)
                return (name + '\0').encode('utf-8')
            if 'show' in command and command[-1].endswith(':' + name): return data
            return self.git_result(command, **kwargs)
        with (patch.object(m, 'MAGNETIC_PATH', str(magnetic)), patch.object(m.subprocess, 'check_output', side_effect=git),
                patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=0))):
            self.assertIn(name, m.candidate_binding(review)['changed_or_added_blob_pairs'])

    def test_binary_copy_preserves_existing_crlf_and_refuses_overwrite(self):
        source = self.root / 'old.obj'; source.write_bytes(b'v 1 2 3\r\nv 4 5 6\r\n')
        target = self.root / 'new/assets/old.obj'
        m.copy_registered_file(source, target, m.sha(source))
        self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertRaises(FileExistsError, m.copy_registered_file, source, target, m.sha(source))
        self.assertRaises(ValueError, m.copy_registered_file, source, self.root / 'bad.obj', '0' * 64)

    def test_cold_build_refuses_existing_install_before_any_command(self):
        root = self.root / 'frozen'; (root / 'ros2_ws/install').mkdir(parents=True)
        with patch.object(m, 'frozen_binding', return_value={'fixture': True}), patch.object(m.subprocess, 'run') as run:
            self.assertRaisesRegex(ValueError, 'Cold build', m.build, {'frozen_root': str(root)})
            run.assert_not_called()

    def test_build_command_selects_exact_four_packages_and_system_fastcdr(self):
        command = m.build_command('/fixture/python', '/fixture/colcon')
        index = command.index('--packages-select')
        self.assertEqual(command[index + 1:command.index('--cmake-args')], list(m.PACKAGES))
        self.assertEqual(len(m.PACKAGES), 4)
        self.assertIn('-Dfastcdr_DIR=/opt/ros/humble/lib/cmake/fastcdr', command)
        self.assertIn('--merge-install', command); self.assertIn('--symlink-install', command)

    def test_full_suite_runs_once_and_retains_nonzero_log_without_retry(self):
        directory = self.root / 'results/freeze_validation'; directory.mkdir(parents=True)
        review = {'frozen_root': str(self.root), 'results_root': str(directory.parent)}
        def command(args, **kwargs):
            self.assertEqual(args[-4:], ['discover', '-s', 'tests', '-v'])
            kwargs['stdout'].write('Ran 2 tests in 0.1s\nFAILED (errors=1)\n')
            return SimpleNamespace(returncode=1)
        with patch.object(m.subprocess, 'run', side_effect=command) as run:
            result, text, _ = m.execute_suite_once(review, {'source': 'fixture'})
            self.assertEqual(result.returncode, 1); self.assertIn('FAILED', text)
            self.assertRaises(FileExistsError, m.execute_suite_once, review, {'source': 'fixture'})
            self.assertEqual(run.call_count, 1)

    def test_actual_fastcdr_flags_and_links_cannot_include_agent_prefix(self):
        root = self.root / 'frozen'; package = root / 'ros2_ws/build/uav_tracking_interfaces'
        system = self.root / 'system_fastcdr'; system.mkdir()
        (system / 'fastcdr-config.cmake').write_text('fixture config')
        package.mkdir(parents=True)
        (package / 'CMakeCache.txt').write_text('fastcdr_DIR:PATH=' + str(system) + '\n')
        for name in ('typesupport_fastrtps_c', 'typesupport_fastrtps_cpp'):
            folder = package / 'CMakeFiles' / name; folder.mkdir(parents=True)
            (folder / 'flags.make').write_text('-I/opt/ros/humble/include')
            (folder / 'link.txt').write_text('/usr/bin/cc -lfastcdr')
        output = self.root / 'results/freeze_validation'; output.mkdir(parents=True)
        review = {'frozen_root': str(root), 'results_root': str(output.parent)}
        with patch.object(m, 'SYSTEM_FASTCDR', str(system)):
            report = m.verify_fastcdr(review)
            self.assertEqual(report['status'], 'MATCHES_HUMBLE_SYSTEM_FASTCDR')
            before = (output / 'fastcdr_provenance.json').read_bytes()
            replay = m.verify_fastcdr(review, write=False)
            self.assertEqual(replay['inputs_sha256'], report['inputs_sha256'])
            self.assertEqual((output / 'fastcdr_provenance.json').read_bytes(), before)
            (package / 'CMakeFiles/typesupport_fastrtps_c/flags.make').write_text('-I' + m.FORBIDDEN_COMPILE)
            self.assertRaises(ValueError, m.verify_fastcdr, review)

    def test_real_cdr_payload_and_all_eleven_checks_match_reviewed_baseline(self):
        old = ast.parse((m.EXTERNAL / 'verify_humble33_imports.py').read_text(encoding='utf-8'))
        new = ast.parse((m.EXTERNAL / 'reviewed_freeze_build.py').read_text(encoding='utf-8'))
        function, = [n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == 'installed_checks']
        def payload(nodes):
            start = next(i for i, n in enumerate(nodes) if isinstance(n, ast.ImportFrom) and n.module == 'rclpy.serialization')
            end = next(i for i, n in enumerate(nodes) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'checks' for t in n.targets))
            return [ast.dump(n, include_attributes=False) for n in nodes[start:end + 1]]
        self.assertEqual(payload(old.body), payload(function.body))


class CapsuleAndOwnershipFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='generic_freeze_capsule_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def capsule(self):
        folder = self.root / 'frozen_fullplan_v4_humble32/core'
        slots = []
        paths = []
        for index in range(12):
            identifier = 'person_stage1_velocity_seed004' if index == 0 else 'cell' + str(index)
            status = 'FAIL' if index == 0 else 'PASS'
            record = {'id': identifier, 'status': status}; record['record_sha256'] = m.canonical(record)
            path = folder / 'slots' / (identifier + '.json'); put(path, record); paths.append(path)
            slots.append({'slot': identifier, 'status': status})
        core = folder / 'execution_terminal.json'
        put(core, {'scope': 'HUMBLE32_CORE12_ORIGINAL_ATTEMPTS_AND_CLEANUP_NOT_FORMAL_GATE', 'finished_utc': '2026-10-31T00:00:00+00:00',
            'returncode': 0, 'planned_count': 12, 'terminal_count': 12, 'slots': slots,
            'status_counts': {'FAIL': 1, 'PASS': 11},
            'cleanup': {'residual_processes': [], 'residual_probe_error': None}})
        previous = self.root / 'predecessor/action.terminal.json'
        put(previous, {'scope': 'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE', 'finished_utc': '2026-10-31T00:00:00+00:00',
            'status': 'FAILED', 'direct_child_returncode': 7,
            'binding_before': {'source': {'freeze_source_sha256': 'd' * 64}},
            'binding_after': {'source': {'freeze_source_sha256': 'd' * 64}},
            'cleanup': {'actual_proc_group_empty': True, 'direct_child_reaped': True, 'residual_processes': []}})
        paths += [core, previous]
        value = {'schema_version': 1, 'scope': 'CLOSED_32_CORE_AND_PREDECESSOR_METADATA_ONLY', 'all_inputs_closed': True,
            'payload_reread': False, 'readiness_claimed': False,
            'files': {p.as_posix(): {'sha256': m.sha(p), 'bytes': p.stat().st_size} for p in paths},
            'boundaries': {'original32_core': {'closed': True, 'receipt': core.as_posix()},
                'predecessor': {'closed': True, 'receipt': previous.as_posix()}},
            'retained_fields': [{'path': p.as_posix(), 'field': 'status', 'expected': slot['status']}
                for p, slot in zip(paths[:12], slots)] + [
                {'path': core.as_posix(), 'field': 'status_counts', 'expected': {'FAIL': 1, 'PASS': 11}},
                {'path': core.as_posix(), 'field': 'returncode', 'expected': 0},
                {'path': previous.as_posix(), 'field': 'status', 'expected': 'FAILED'},
                {'path': previous.as_posix(), 'field': 'direct_child_returncode', 'expected': 7}]}
        path = self.root / 'capsule.json'; put(path, value)
        review = fixture_review(); review['closed_evidence'] = {'path': str(path), 'sha256': m.sha(path)}
        return review, value, path, paths

    def verify(self, review):
        # Path-syntax policy is tested separately; the fixture filesystem is Windows.
        with patch.object(m, 'EXTERNAL', self.root), patch.object(m, 'absolute', side_effect=lambda p: p):
            return m.verify_closed_capsule(review)

    def test_original_core_fail_and_failed_predecessor_are_retained_without_promotion(self):
        review, _, _, _ = self.capsule()
        report = self.verify(review)
        self.assertEqual(report['files'], 14)
        self.assertFalse(report['payloads_reverified'])

    def test_original_metadata_mutation_or_fake_all_pass_is_rejected(self):
        review, value, path, paths = self.capsule()
        record = m.read_small(paths[0]); record['status'] = 'PASS'; put(paths[0], record)
        self.assertRaises(ValueError, self.verify, review)
        value['files'][paths[0].as_posix()].update(sha256=m.sha(paths[0]), bytes=paths[0].stat().st_size)
        put(path, value); review['closed_evidence']['sha256'] = m.sha(path)
        self.assertRaises(ValueError, self.verify, review)

    def test_capsule_never_reads_payload_or_accepts_live_boundary(self):
        review, value, path, paths = self.capsule()
        payload = self.root / 'rosbag.db3'; payload.write_bytes(b'fixture payload must not be hashed')
        value['files'][payload.as_posix()] = {'sha256': '0' * 64, 'bytes': payload.stat().st_size}
        put(path, value); review['closed_evidence']['sha256'] = m.sha(path)
        original = m.sha
        with patch.object(m, 'sha', side_effect=lambda p: (_ for _ in ()).throw(AssertionError('payload read')) if Path(p) == payload else original(p)):
            self.assertRaises(ValueError, self.verify, review)
        value['files'].pop(payload.as_posix()); value['boundaries']['predecessor']['closed'] = False
        put(path, value); review['closed_evidence']['sha256'] = m.sha(path)
        self.assertRaises(ValueError, self.verify, review)

    def test_capsule_must_explicitly_retain_every_status_and_match_predecessor_source(self):
        review, value, path, _ = self.capsule()
        original = deepcopy(value)
        value['retained_fields'].pop(5)
        put(path, value); review['closed_evidence']['sha256'] = m.sha(path)
        self.assertRaisesRegex(ValueError, 'statuses/counts', self.verify, review)
        value = original
        predecessor = Path(value['boundaries']['predecessor']['receipt'])
        terminal = m.read_small(predecessor)
        terminal['binding_after']['source']['freeze_source_sha256'] = '0' * 64
        put(predecessor, terminal)
        value['files'][predecessor.as_posix()] = {'sha256': m.sha(predecessor), 'bytes': predecessor.stat().st_size}
        put(path, value); review['closed_evidence']['sha256'] = m.sha(path)
        self.assertRaisesRegex(ValueError, 'actual predecessor source', self.verify, review)

    def test_single_action_launcher_passes_reviewed_budgets_and_generic_binding(self):
        review = fixture_review(); bounded = Mock(); bounded.run_bounded.return_value = {'status': 'PASS'}
        with (patch.object(m, 'EXTERNAL', self.root), patch.object(m, 'require_linux'),
                patch.object(m, 'dependencies', return_value={'bounded_humble33_action': bounded}),
                patch.object(m, 'action_binding', return_value={'source': 'fixture'}) as binding,
                patch.object(m, 'exclusive_window', return_value=nullcontext())):
            result = m.launch(review, 'build', self.root / 'fixture.json', 'a' * 64)
            self.assertEqual(result['status'], 'PASS')
            kwargs = bounded.run_bounded.call_args.kwargs
            self.assertEqual((kwargs['timeout_s'], kwargs['grace_s'], kwargs['kill_confirm_s']), (1800., 30., 5.))
            self.assertEqual(kwargs['binding']('after'), {'source': 'fixture'})
            self.assertEqual(bounded.run_bounded.call_count, 1)
            self.assertGreaterEqual(binding.call_count, 3)

    def test_internal_child_cannot_use_wrong_owned_group(self):
        review = fixture_review(); action = 'prepare'
        folder = self.root / 'reviewed_freeze_actions_fixture' / action; folder.mkdir(parents=True)
        put(folder / 'action.process.json', {'pid': 456, 'pgid': 456, 'session': 456, 'observed_leader_stat': {'start_ticks': 42}})
        stat = lambda pid: {'pid': 123} if pid == 123 else {'pid': 456, 'ppid': 123, 'start_ticks': 42}
        deps = {'bounded_humble33_action': SimpleNamespace(process_stat=stat)}
        with (patch.object(m, 'EXTERNAL', self.root), patch.object(m, 'require_linux'), patch.object(m, 'dependencies', return_value=deps),
                patch.dict(m.os.environ, REVIEWED_FREEZE_RECEIPT_DIR=str(folder), REVIEWED_FREEZE_PARENT_PID='123'),
                patch.object(m.os, 'getpgrp', return_value=999, create=True), patch.object(m.os, 'getsid', return_value=999, create=True),
                patch.object(m, 'action_binding', side_effect=AssertionError('no action'))):
            self.assertRaisesRegex(ValueError, 'owned bounded session', m.child_action, review, action, 'action')


if __name__ == '__main__':
    unittest.main(verbosity=2)
