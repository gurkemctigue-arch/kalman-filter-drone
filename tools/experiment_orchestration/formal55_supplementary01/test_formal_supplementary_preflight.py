"""Tiny synthetic metadata only; never execute original adapter/guard or WSL."""
from __future__ import annotations
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import formal_supplementary_preflight as gate


class ExecObserved(BaseException):
    pass


class Fixture:
    def __init__(self, base):
        self.base = Path(base).resolve()
        self.root = self.base / 'synthetic_final'
        self.root.mkdir()
        self.results = self.root / 'results'
        self.results.mkdir()
        self.state = self.results / 'original_guard_state'
        self.tools_sha = gate.canonical(gate.tool_manifest())
        self.now = datetime(2020, 1, 4, tzinfo=timezone.utc)
        self.calls = []
        self.producer_dir = self.base / 'approved_producers'
        self.producer_dir.mkdir()
        for name in ('prospective_detection_dataset.py', 'evaluate_prospective_detection.py'):
            (self.producer_dir / name).write_bytes((gate.HERE.parent / name).read_bytes())
        self.review_path = self.base / 'review.json'
        self.review_path.write_bytes((gate.HERE.parent / 'prospective_detection_independent_review01.json').read_bytes())
        self.dataset = gate.source_module(gate.pin(self.producer_dir / 'prospective_detection_dataset.py'))
        self.sources = {}
        for relative in self.dataset.HELPERS:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# tiny synthetic helper, never imported\n', encoding='utf-8')
            self.sources[relative] = gate.pin(path)['sha256']
        self.sources['models/synthetic.pt'] = 'f' * 64
        (self.root / 'models').mkdir()
        (self.root / 'models/synthetic.pt').write_bytes(b'TINY NOT A MODEL; MUST NEVER BE READ')
        (self.root / 'tools').mkdir()
        self.guard_path = self.root / 'tools/reliability_v4_guard.py'
        self.guard_path.write_text('# synthetic original guard source, never executed\n', encoding='utf-8')
        self.plans = {}
        for label, axis in (('core', self.dataset.GROUPS), ('extension', self.dataset.CONDITIONS)):
            output = self.results / label
            output.mkdir()
            trials = []
            for category in self.dataset.CLASSES:
                for item in axis:
                    for seed in self.dataset.SEEDS:
                        group = item if label == 'core' else 'stage1_velocity'
                        identity = f'{category}_{item}_seed{seed}' if label == 'core' else f'{category}_extension_{item}_seed{seed}'
                        trial = {'id': identity, 'directory': str(output / 'trials' / identity), 'target_class': category,
                                 'group': group, 'stage': 3 if group.startswith('stage3') else 2 if group == 'stage2_crossing' else 1,
                                 'seed': seed}
                        if label == 'extension':
                            trial['extension_condition'] = item
                        trials.append(trial)
            self.plans[label] = {'schema_version': 1, 'mode': 'FORMAL' if label == 'core' else 'EXTENSION_FORMAL',
                'created_utc': '2020-01-01T00:00:00+00:00', 'frozen_root': str(self.root), 'results_root': str(self.results),
                'output': str(output), 'selected_classes': list(self.dataset.CLASSES), 'selected_seeds': self.dataset.SEEDS,
                'selected_groups': list(self.dataset.GROUPS), 'selected_extension_conditions': list(self.dataset.CONDITIONS),
                'source_hashes': deepcopy(self.sources), 'model_hashes': {'models/synthetic.pt': 'f' * 64}, 'trials': trials}
        self.plan_paths = {label: Path(plan['output']) / 'plan.json' for label, plan in self.plans.items()}
        self.write_plans()
        self.admission_path = self.base / 'admission.json'
        self.admission = {'schema_version': 1, 'kind': 'RELIABILITY_V4_FORMAL_ADMISSION',
            'created_utc': '2020-01-02T00:00:00+00:00', 'final_root': str(self.root), 'plans': deepcopy(self.plan_pins),
            'state_directory': str(self.state), 'tool': gate.pin(self.guard_path),
            'registrations': {}, 'calibration': {}, 'safety': {}, 'storage': {}}
        self.save_admission()
        self.protocol_path = self.base / 'protocol.json'
        self.protocol = {'schema_version': 1, 'kind': self.dataset.KIND, 'sampling_rule': deepcopy(self.dataset.RULE),
            'original_planned_slots': 280, 'created_utc': '2020-01-01T01:00:00+00:00',
            'all280_unattempted_at_protocol_creation': True, 'frozen_root': str(self.root), 'plans': deepcopy(self.plan_pins),
            'helper_source_hashes': {name: self.sources[name] for name in self.dataset.HELPERS},
            'producer_tools': self.dataset.tool_pins(), 'slots': self.protocol_slots(), 'formal_attempts_started_by_this_tool': 0}
        self.save(self.protocol_path, self.protocol)
        self.basis_path = self.base / 'basis.json'
        self.basis = {'selected_before_formal_execution': True, 'video_selection': {'seed': 1000,
            'classes': list(self.dataset.CLASSES), 'groups': list(self.dataset.GROUPS), 'scheduled_clips': 12}}
        self.save(self.basis_path, self.basis)
        self.selection_path = self.base / 'selection.json'
        self.selection = {'schema_version': 1, 'kind': 'PROSPECTIVE_SUPPLEMENTARY_DETECTION_SOURCE_SELECTIONS',
            'created_utc': '2019-12-31T00:00:00+00:00', 'selection_basis': {'repository_path': 'planning/reliability-v4-delivery-selections.json',
            'sha256': gate.pin(self.basis_path)['sha256'], 'field': 'video_selection'},
            'classes': list(self.dataset.CLASSES), 'groups': list(self.dataset.GROUPS), 'seed': 1000,
            'selected_slot_ids': [f'{category}_{group}_seed1000' for category in self.dataset.CLASSES for group in self.dataset.GROUPS],
            'scheduled_recordings': 12, 'complete_formal_ledger_denominator': 280, 'new_formal_flight_slots': 0,
            'actual_protocol_must_be_created_after_both_formal_plans_and_before_any_formal_start': True,
            'formal_seed_use_authorized': False,
            'producer_tools_canonical_sha256': '0581776c0ad6bd3c36e895d9f0795174b22bfd44eef0d1c323f9949b31432fa3',
            'sampling_rule': {'first_follow_offset_s': 1., 'period_s': 2., 'end': 'FINAL_RECORDED_CLOCK',
                'maximum_source_rgb_distance_s': .1, 'exact_tie': 'EARLIER_ACQUISITION',
                'duplicate_acquisition': 'UNKNOWN_NO_SELECTION', 'image_cap': None}}
        self.save(self.selection_path, self.selection)
        self.contract_path = self.base / 'contract.json'
        self.audit_path = self.base / 'separate_audit.jsonl'
        self.adapter_dir = self.base / 'synthetic_actual_adapter'
        self.adapter_dir.mkdir()
        for name in (*gate.ADAPTER_NAMES.values(), 'test_formal48_guard_adapter01.py'):
            (self.adapter_dir / name).write_text('# synthetic named code; never imported or executed\n', encoding='utf-8')
        adapter_manifest = {'schema_version': 1, 'scope': gate.ADAPTER_SCOPE,
            'files': {path.name: gate.pin(path)['sha256'] for path in self.adapter_dir.iterdir()}}
        self.adapter_reviewed_sha = gate.canonical(adapter_manifest)
        self.adapter_describe_path = self.base / 'actual_describe.json'
        self.save(self.adapter_describe_path, {'manifest': adapter_manifest,
            'tools_canonical_sha256': self.adapter_reviewed_sha, 'actual_action_executed': False})
        self.adapter_binding_path = self.base / 'adapter_binding.json'
        self.adapter_identity = {'schema_version': 1, 'kind': gate.ADAPTER_KIND,
            'created_utc': '2020-01-02T01:00:00+00:00',
            'shell': gate.pin(self.adapter_dir / gate.ADAPTER_NAMES['shell']),
            'python': gate.pin(self.adapter_dir / gate.ADAPTER_NAMES['python']),
            'describe': gate.pin(self.adapter_describe_path), 'manifest_canonical_sha256': self.adapter_reviewed_sha,
            'reviewed_tools_sha256': self.adapter_reviewed_sha}
        self.save(self.adapter_binding_path, self.adapter_identity)
        self.adapter_binding = gate.pin(self.adapter_binding_path)
        self.contract = {'schema_version': 1, 'kind': gate.KIND, 'created_utc': '2020-01-03T00:00:00+00:00',
            'admission': self.admission_pin, 'plans': deepcopy(self.plan_pins), 'detection_protocol': gate.pin(self.protocol_path),
            'selection': gate.pin(self.selection_path), 'selection_basis': gate.pin(self.basis_path), 'detection_review': gate.pin(self.review_path),
            'preflight_tools_sha256': self.tools_sha, 'audit_log': str(self.audit_path), 'adapter_binding': self.adapter_binding,
            'adapter': {'shell': self.adapter_identity['shell'], 'python': self.adapter_identity['python'],
                        'reviewed_tools_sha256': self.adapter_reviewed_sha, 'resolutions': {},
                        'argv_prefix': ['bash', self.adapter_identity['shell']['path'], '--manifest-sha256', self.admission_pin['sha256'],
                                        '--reviewed-tools-sha256', self.adapter_reviewed_sha]}}
        self.save_contract()

    @staticmethod
    def save(path, value):
        path.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')

    def write_plans(self):
        core = self.plans['core']
        core['plan_sha256'] = gate.canonical({key: value for key, value in core.items() if key != 'plan_sha256'})
        self.save(self.plan_paths['core'], core)
        extension = self.plans['extension']
        extension['core_reference_binding'] = {**gate.pin(self.plan_paths['core']), 'plan_sha256': core['plan_sha256']}
        extension['plan_sha256'] = gate.canonical({key: value for key, value in extension.items() if key != 'plan_sha256'})
        self.save(self.plan_paths['extension'], extension)
        self.plan_pins = {label: gate.pin(path) for label, path in self.plan_paths.items()}

    def protocol_slots(self):
        return [{'plan': label, 'slot_id': trial['id'], 'source_trial': trial['directory'],
                 'target_class': trial['target_class'], 'stage': trial['stage'], 'group': trial['group'],
                 'condition': trial.get('extension_condition'), 'seed': trial['seed'],
                 'camera_mode': 'DYNAMIC_PHYSICAL_NO_FIXED_FALLBACK' if trial['stage'] == 3 else 'PINNED_FIXED_MOUNT'}
                for label, plan in self.plans.items() for trial in plan['trials']]

    def save_admission(self):
        self.admission['manifest_sha256'] = gate.canonical({key: value for key, value in self.admission.items() if key != 'manifest_sha256'})
        self.save(self.admission_path, self.admission)
        self.admission_pin = gate.pin(self.admission_path)

    def save_contract(self):
        self.save(self.contract_path, self.contract)
        self.contract_pin = gate.pin(self.contract_path)

    def save_selection(self):
        self.save(self.selection_path, self.selection)
        self.contract['selection'] = gate.pin(self.selection_path)
        self.save_contract()

    def save_protocol(self):
        self.save(self.protocol_path, self.protocol)
        self.contract['detection_protocol'] = gate.pin(self.protocol_path)
        self.save_contract()

    def refresh_plans(self):
        self.write_plans()
        self.admission['plans'] = deepcopy(self.plan_pins)
        self.save_admission()
        self.protocol['plans'] = deepcopy(self.plan_pins)
        self.protocol['slots'] = self.protocol_slots()
        self.save(self.protocol_path, self.protocol)
        self.contract['plans'] = deepcopy(self.plan_pins)
        self.contract['admission'] = self.admission_pin
        self.contract['detection_protocol'] = gate.pin(self.protocol_path)
        self.contract['adapter']['argv_prefix'][3] = self.admission_pin['sha256']
        self.save_contract()

    def validate(self):
        return gate.validate_contract(self.contract_pin, self.admission_path, self.tools_sha, now=self.now, **self.adapter_args())

    def adapter_args(self):
        return {'adapter_binding': self.adapter_binding, 'adapter_reviewed_sha': self.adapter_reviewed_sha}

    def adapter_cli(self):
        return ['--adapter-binding', str(self.adapter_binding_path), '--adapter-binding-sha256', self.adapter_binding['sha256'],
                '--adapter-reviewed-tools-sha256', self.adapter_reviewed_sha]

    def fake_exec(self, executable, argv, env):
        self.calls.append((executable, list(argv), dict(env)))
        raise ExecObserved()

    def run(self):
        gate.run_one(self.contract_pin, self.admission_path, self.tools_sha, now=self.now, exec_function=self.fake_exec, **self.adapter_args())

    def original_start(self, *, initial=True, marker=True, terminal=True):
        self.state.mkdir(exist_ok=True)
        if initial:
            value = {'schema_version': 1, 'kind': 'RELIABILITY_V4_INITIAL_FULL280_ADMISSION',
                'created_utc': '2020-01-05T00:00:00+00:00', 'manifest_sha256': self.admission['manifest_sha256'],
                'tool': self.admission['tool'], 'initial_pending_slots': 280, 'capacity': {'scheduled_slots': 280, 'pending_slots': 280}}
            value['receipt_sha256'] = gate.canonical(value)
            self.save(self.state / 'initial_admission.json', value)
        trial = self.plans['core']['trials'][0]
        Path(trial['directory']).mkdir(parents=True)
        slots = Path(self.plans['core']['output']) / 'slots'
        slots.mkdir(exist_ok=True)
        if marker:
            self.save(slots / (trial['id'] + '.started.json'), {'id': trial['id'], 'plan_sha256': self.plans['core']['plan_sha256'],
                'started_utc': '2020-01-05T00:00:01+00:00'})
        if terminal:
            self.save(slots / (trial['id'] + '.json'), {'status': 'FAIL', 'id': trial['id']})
        self.now = datetime(2020, 1, 6, tzinfo=timezone.utc)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='supplementary_preflight_synthetic_')
        self.addCleanup(self.temp.cleanup)
        self.case = Fixture(self.temp.name)

    def refusal(self):
        with self.assertRaises((ValueError, KeyError, OSError)):
            self.case.run()
        self.assertEqual(self.case.calls, [])
        self.assertFalse(self.case.audit_path.exists())

    def test_readonly_verify_uses_actual_protocol_verifier_without_audit_or_guard_state(self):
        context = self.case.validate()
        self.assertEqual(context['protocol']['original_planned_slots'], 280)
        self.assertEqual(len(context['plans']['core']['trials']), 120)
        self.assertEqual(len(context['plans']['extension']['trials']), 160)
        self.assertFalse(self.case.audit_path.exists())
        self.assertFalse(self.case.state.exists())

    def test_first_run_only_audits_and_execs_exact_original_prefix_once(self):
        with self.assertRaises(ExecObserved):
            self.case.run()
        self.assertEqual(len(self.case.calls), 1)
        self.assertEqual(self.case.calls[0][1], self.case.contract['adapter']['argv_prefix'] + ['run-one', '--manifest', str(self.case.admission_path)])
        row = gate.decode(self.case.audit_path.read_text())
        self.assertTrue(row['first_preflight_all280_untouched'])
        self.assertIsNone(row['initial_admission'])
        self.assertFalse(self.case.state.exists())

    def test_second_run_accepts_original_started_failed_slot_and_keeps_280_denominator(self):
        with self.assertRaises(ExecObserved):
            self.case.run()
        self.case.original_start()
        with self.assertRaises(ExecObserved):
            self.case.run()
        self.assertEqual(len(self.case.calls), 2)
        rows = [gate.decode(line) for line in self.case.audit_path.read_text().splitlines()]
        self.assertEqual([row['sequence'] for row in rows], [1, 2])
        self.assertIsNotNone(rows[1]['initial_admission'])
        self.assertEqual(self.case.validate()['protocol']['original_planned_slots'], 280)
        trial = self.case.plans['core']['trials'][0]
        self.assertEqual(json.loads((Path(self.case.plans['core']['output']) / 'slots' / (trial['id'] + '.json')).read_text())['status'], 'FAIL')

    def test_no_pending_stdout_and_nonzero_exit_have_no_wrapper_decoration(self):
        for code, stdout, stderr in ((0, '{"result":"NO_PENDING_SLOTS"}\n', ''), (7, 'original stdout\n', 'original stderr\n')):
            with self.subTest(code=code), tempfile.TemporaryDirectory(prefix='stream_fixture_') as directory:
                case = Fixture(directory)
                def fake_exec(executable, argv, env):
                    print(stdout, end='')
                    print(stderr, end='', file=sys.stderr)
                    raise SystemExit(code)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                    gate.run_one(case.contract_pin, case.admission_path, case.tools_sha, now=case.now, exec_function=fake_exec, **case.adapter_args())
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(out.getvalue(), stdout)
                self.assertEqual(err.getvalue(), stderr)

    def test_original_resolution_argv_order_and_bytes_are_preserved(self):
        path = self.case.base / 'original_resolution.json'
        self.case.save(path, {'synthetic_original_resolution': True})
        binding = gate.pin(path)
        self.case.contract['adapter']['resolutions'] = {'core': binding}
        self.case.contract['adapter']['argv_prefix'] = ['bash', self.case.contract['adapter']['shell']['path'],
            '--core-resolution-sha256', binding['sha256'], '--reviewed-tools-sha256', self.case.adapter_reviewed_sha,
            '--core-resolution', binding['path'], '--manifest-sha256', self.case.admission_pin['sha256']]
        self.case.save_contract()
        with self.assertRaises(ExecObserved):
            self.case.run()
        self.assertEqual(self.case.calls[0][1][:-3], self.case.contract['adapter']['argv_prefix'])

    def test_protocol_later_than_contract_or_before_real_plans_is_refused(self):
        for value in ('2030-01-01T00:00:00+00:00', '2019-12-31T00:00:00+00:00', '2020-01-01T01:00:00'):
            with self.subTest(value=value):
                self.case.protocol['created_utc'] = value
                self.case.save_protocol()
                self.refusal()

    def test_future_contract_and_future_selection_are_refused(self):
        self.case.contract['created_utc'] = '2030-01-01T00:00:00+00:00'
        self.case.save_contract()
        self.refusal()
        self.case.contract['created_utc'] = '2020-01-03T00:00:00+00:00'
        self.case.selection['created_utc'] = '2030-01-01T00:00:00+00:00'
        self.case.save_selection()
        self.refusal()

    def test_status_or_true_flags_do_not_replace_complete_protocol_semantics(self):
        self.case.protocol['slots'] = self.case.protocol['slots'][:-1]
        self.case.protocol['status'] = 'PASS'
        self.case.save_protocol()
        self.refusal()

    def test_bound_plan_sha_source_model_and_internal_digest_cannot_drift(self):
        self.case.plans['extension']['model_hashes']['models/synthetic.pt'] = 'a' * 64
        self.case.refresh_plans()
        self.refusal()

    def test_actual_small_helper_change_is_refused_without_reading_model(self):
        relative = self.case.dataset.HELPERS[0]
        (self.case.root / relative).write_text('# changed tiny helper\n', encoding='utf-8')
        self.refusal()

    def test_metadata_verification_never_opens_weights_or_bags(self):
        original = Path.open
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.suffix, '.pt')
            self.assertNotIn('rosbag', path.parts)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            self.case.validate()

    def test_producer_bytes_and_approval_canonical_are_enforced(self):
        path = self.case.producer_dir / 'evaluate_prospective_detection.py'
        path.write_bytes(path.read_bytes() + b'\n# tamper')
        self.case.protocol['producer_tools'][path.name] = gate.pin(path)
        self.case.save_protocol()
        self.refusal()

    def test_selection_order_missing_seed_substitution_and_added_matrix_are_refused(self):
        original = deepcopy(self.case.selection)
        mutations = [lambda value: value['selected_slot_ids'].reverse(),
                     lambda value: value['selected_slot_ids'].pop(),
                     lambda value: value.update(seed=1001), lambda value: value.update(new_formal_flight_slots=1),
                     lambda value: value.update(complete_formal_ledger_denominator=12),
                     lambda value: value.update(producer_tools_canonical_sha256='a' * 64)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.case.selection = deepcopy(original)
                mutate(self.case.selection)
                self.case.save_selection()
                self.refusal()

    def test_selection_basis_sha_and_actual_video_axes_are_verified(self):
        self.case.basis['video_selection']['groups'].reverse()
        self.case.save(self.case.basis_path, self.case.basis)
        self.case.contract['selection_basis'] = gate.pin(self.case.basis_path)
        self.case.selection['selection_basis']['sha256'] = self.case.contract['selection_basis']['sha256']
        self.case.save_selection()
        self.refusal()

    def test_selected_id_cannot_relabel_actual_group_fields(self):
        trials = self.case.plans['core']['trials']
        trials[0]['id'], trials[10]['id'] = trials[10]['id'], trials[0]['id']
        self.case.refresh_plans()
        self.refusal()

    def test_wrong_admission_argument_or_manual_pass_heading_is_refused(self):
        alias = self.case.base / 'other_admission.json'
        alias.write_bytes(self.case.admission_path.read_bytes())
        with self.assertRaises(ValueError):
            gate.validate_contract(self.case.contract_pin, alias, self.case.tools_sha, now=self.case.now, **self.case.adapter_args())
        self.case.admission['status'] = 'PASS'
        self.case.admission['manifest_sha256'] = 'a' * 64
        self.case.save(self.case.admission_path, self.case.admission)
        self.case.contract['admission'] = gate.pin(self.case.admission_path)
        self.case.contract['adapter']['argv_prefix'][3] = self.case.contract['admission']['sha256']
        self.case.save_contract()
        self.refusal()

    def test_identical_copy_cannot_replace_named_original_core_plan(self):
        copied = self.case.base / 'copied_core_plan.json'
        copied.write_bytes(self.case.plan_paths['core'].read_bytes())
        binding = gate.pin(copied)
        self.case.contract['plans']['core'] = binding
        self.case.admission['plans']['core'] = binding
        self.case.save_admission()
        self.case.contract['admission'] = self.case.admission_pin
        self.case.contract['adapter']['argv_prefix'][3] = self.case.admission_pin['sha256']
        self.case.protocol['plans']['core'] = binding
        self.case.save_protocol()
        self.refusal()

    def test_a_pass_label_cannot_replace_original_source_review(self):
        self.case.save(self.case.review_path, {'status': 'PASS_SOURCE_AND_SYNTHETIC_FIXTURES_ONLY'})
        self.case.contract['detection_review'] = gate.pin(self.case.review_path)
        self.case.save_contract()
        self.refusal()

    def test_unknown_adapter_switch_duplicate_or_wrong_tools_digest_are_refused(self):
        original = deepcopy(self.case.contract['adapter'])
        for suffix in (['--slot-id', 'chosen'], ['run-one', '--manifest'], ['--manifest-sha256', self.case.admission_pin['sha256']]):
            self.case.contract['adapter'] = deepcopy(original)
            self.case.contract['adapter']['argv_prefix'] += suffix
            self.case.save_contract()
            self.refusal()
        self.case.contract['adapter'] = deepcopy(original)
        self.case.contract['adapter']['reviewed_tools_sha256'] = 'a' * 64
        self.case.save_contract()
        self.refusal()

    def test_audit_contract_and_protocol_outputs_cannot_be_inside_original_results(self):
        self.case.contract['audit_log'] = str(self.case.results / 'bad.jsonl')
        self.case.save_contract()
        self.refusal()
        self.case.contract['audit_log'] = str(self.case.audit_path)
        relocated = self.case.results / 'bad_protocol.json'
        relocated.write_bytes(self.case.protocol_path.read_bytes())
        self.case.contract['detection_protocol'] = gate.pin(relocated)
        self.case.save_contract()
        self.refusal()

    def test_original_guard_state_cannot_move_outside_actual_results(self):
        self.case.admission['state_directory'] = str(self.case.base / 'bad_state')
        self.case.save_admission()
        self.case.contract['admission'] = self.case.admission_pin
        self.case.contract['adapter']['argv_prefix'][3] = self.case.admission_pin['sha256']
        self.case.save_contract()
        self.refusal()

    def test_contract_and_other_original_pins_refuse_alias_and_tamper(self):
        alias = dict(self.case.contract_pin)
        alias['path'] = str(self.case.base / '..' / self.case.base.name / 'contract.json')
        with self.assertRaises(ValueError):
            gate.validate_contract(alias, self.case.admission_path, self.case.tools_sha, now=self.case.now, **self.case.adapter_args())
        self.case.selection_path.write_bytes(self.case.selection_path.read_bytes() + b' ')
        self.refusal()

    def test_no_prestart_audit_can_be_retrofitted_after_original_start(self):
        self.case.original_start()
        self.refusal()

    def test_existing_product_without_original_start_marker_is_refused(self):
        self.case.original_start(initial=False, marker=False)
        self.refusal()

    def test_original_started_time_future_or_before_protocol_is_refused(self):
        self.case.original_start(initial=False)
        marker = Path(self.case.plans['core']['output']) / 'slots' / (self.case.plans['core']['trials'][0]['id'] + '.started.json')
        for when in ('2019-01-01T00:00:00+00:00', '2030-01-01T00:00:00+00:00'):
            value = json.loads(marker.read_text())
            value['started_utc'] = when
            self.case.save(marker, value)
            self.refusal()

    def test_initial_pass_heading_without_original_internal_digest_is_refused(self):
        self.case.original_start()
        path = self.case.state / 'initial_admission.json'
        self.case.save(path, {'kind': 'RELIABILITY_V4_INITIAL_FULL280_ADMISSION', 'status': 'PASS', 'initial_pending_slots': 280})
        self.refusal()

    def test_audit_tamper_is_refused_without_second_exec(self):
        with self.assertRaises(ExecObserved):
            self.case.run()
        self.case.original_start()
        self.case.audit_path.write_bytes(self.case.audit_path.read_bytes() + b'\n')
        with self.assertRaises(ValueError):
            self.case.run()
        self.assertEqual(len(self.case.calls), 1)

    def test_internally_sealed_future_audit_is_still_refused(self):
        with self.assertRaises(ExecObserved):
            self.case.run()
        value = gate.decode(self.case.audit_path.read_text())
        value['created_utc'] = '2030-01-01T00:00:00+00:00'
        value['event_sha256'] = gate.canonical({key: item for key, item in value.items() if key != 'event_sha256'})
        self.case.audit_path.write_text(json.dumps(value) + '\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.case.run()
        self.assertEqual(len(self.case.calls), 1)

    def test_metadata_drift_after_audit_prevents_original_exec_and_keeps_attempt(self):
        original = gate.append_audit
        def drift(context):
            original(context)
            self.case.selection_path.write_bytes(self.case.selection_path.read_bytes() + b' ')
        with patch.object(gate, 'append_audit', drift), self.assertRaises(ValueError):
            self.case.run()
        self.assertEqual(self.case.calls, [])
        self.assertTrue(self.case.audit_path.is_file())
        self.assertFalse(self.case.state.exists())

    def test_oversized_marker_is_refused_before_loading_original_verifier(self):
        trial = self.case.plans['core']['trials'][0]
        marker = Path(self.case.plans['core']['output']) / 'slots' / (trial['id'] + '.started.json')
        marker.parent.mkdir()
        marker.write_text('{}', encoding='utf-8')
        original = Path.stat
        def fake_stat(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == marker:
                items = list(result)
                items[6] = gate.MAX_SMALL + 1
                return os.stat_result(items)
            return result
        with patch.object(Path, 'stat', fake_stat), patch.object(gate, 'source_module', side_effect=AssertionError('must reject before original verifier')):
            self.refusal()

    def test_read_limit_is_checked_again_if_metadata_grows(self):
        path = self.case.base / 'tiny.json'
        path.write_text('{}', encoding='utf-8')
        with patch.object(gate, 'MAX_SMALL', 4), patch.object(Path, 'open', return_value=io.BytesIO(b'xxxxx')):
            with self.assertRaises(ValueError):
                gate.raw(path)

    def test_main_run_one_refusal_keeps_stdout_empty(self):
        self.case.contract['created_utc'] = '2030-01-01T00:00:00+00:00'
        self.case.save_contract()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(gate.os, 'execvpe', side_effect=AssertionError('no delegation')):
            code = gate.main(['run-one', '--contract', str(self.case.contract_path), '--contract-sha256', self.case.contract_pin['sha256'],
                              '--manifest', str(self.case.admission_path), '--reviewed-tools-sha256', self.case.tools_sha] + self.case.adapter_cli())
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(json.loads(err.getvalue())['status'], 'REFUSED_BEFORE_ORIGINAL_ADAPTER_EXEC')

    def test_independent_adapter_binding_pin_cannot_be_substituted_by_contract(self):
        self.case.adapter_binding = dict(self.case.adapter_binding, sha256='a' * 64)
        self.refusal()

    def test_actual_adapter_describe_drift_after_audit_preserves_event_and_refuses_exec(self):
        original = gate.append_audit
        def drift(context):
            original(context)
            path = self.case.adapter_describe_path
            path.write_bytes(path.read_bytes() + b' ')
        with patch.object(gate, 'append_audit', drift), self.assertRaises(ValueError):
            self.case.run()
        self.assertEqual(self.case.calls, [])
        self.assertTrue(self.case.audit_path.is_file())
        self.assertFalse(self.case.state.exists())

    def test_old41_contract_is_archival_and_cannot_be_relabelled_as_new_binding(self):
        self.case.contract['kind'] = 'FORMAL_SUPPLEMENTARY_BINDING_ONLY_NOT_ADMISSION'
        self.case.save_contract()
        self.refusal()

    def test_default_and_verify_actions_cannot_exec_or_write_audit(self):
        with patch.object(gate.os, 'execvpe', side_effect=AssertionError('inert action must not execute')), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gate.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())['actual_action_executed'])
        with redirect_stdout(io.StringIO()), patch.object(gate.os, 'execvpe', side_effect=AssertionError('must not execute')):
            self.assertEqual(gate.main(['verify', '--contract', str(self.case.contract_path), '--contract-sha256', self.case.contract_pin['sha256'],
                                       '--manifest', str(self.case.admission_path), '--reviewed-tools-sha256', self.case.tools_sha] + self.case.adapter_cli()), 0)
        self.assertFalse(self.case.audit_path.exists())


class InertImportTests(unittest.TestCase):
    def test_import_describe_forbid_ros_detector_and_original_adapter_imports(self):
        script = str(Path(gate.__file__).resolve())
        program = '''import builtins, importlib.util
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in ('rosbag2_py','rclpy','ultralytics','torch','formal41_guard_adapter01','local_runtime_observer41'):
        raise AssertionError('Unexpected runtime import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__=guarded
spec=importlib.util.spec_from_file_location('inert_preflight_fixture', SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.main(['describe'])
'''.replace('SCRIPT', repr(script))
        result = subprocess.run([sys.executable, '-I', '-B', '-c', program], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['actual_action_executed'])


if __name__ == '__main__':
    unittest.main()
