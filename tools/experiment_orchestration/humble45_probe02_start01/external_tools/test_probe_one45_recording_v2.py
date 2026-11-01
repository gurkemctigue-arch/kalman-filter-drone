"""Pure contract/trial invariants; no WSL, actual plan, source/model or flight."""
from copy import deepcopy
import subprocess
import sys
import unittest
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import probe_one45_recording_v2 as probe
import source_runtime41 as policy


def previous():
    old = '/root/uav_tracking_fullplan_v4_humble43'
    name = 'reliability_v4_humble43_extensions_probe01_'+probe.SLOT
    return {'id': probe.SLOT, 'name': name, 'stage': 1, 'multi_target': False,
            'seed': 4, 'duration_s': 75., 'desired_distance_m': 12.,
            'flight_command': ['bash', old+'/scripts/run_research_session.sh', old+'/scripts/run_stage1_trial.py',
                '--name', name, '--duration', '75.0', '--seed', '4', '--desired-distance-m', '12.0', '--real-time-factor', '0.125'],
            'evaluations': [{'kind': kind, 'command': ['bash', old+'/scripts/run_research_session.sh',
                old+'/scripts/evaluate_'+kind+'.py', old+'/results/'+name]} for kind in probe.KINDS]}


class OriginalTrialInvariantTests(unittest.TestCase):
    def setUp(self):
        self.old = previous()
        self.new = probe.remap_trial(self.old)

    def assert_rejected(self, mutate):
        mutate(self.new)
        with self.assertRaises(ValueError):
            probe.require_original_trial(self.new, self.old)

    def test_only_root_and_name_remap(self):
        probe.require_original_trial(self.new, self.old)
        self.assertIn(probe.ROOT+'/scripts/run_stage1_trial.py', self.new['flight_command'])
        self.assertEqual(self.new['name'], probe.NAME)

    def test_reference_is_not_mutated(self):
        self.assertEqual(self.old, previous())

    def test_distance_change_rejected(self):
        self.assert_rejected(lambda t: t.update(desired_distance_m=9.))

    def test_duration_change_rejected(self):
        self.assert_rejected(lambda t: t.update(duration_s=60.))

    def test_formal_seed_rejected(self):
        self.assert_rejected(lambda t: t.update(seed=1000))

    def test_wrong_name_rejected(self):
        self.assert_rejected(lambda t: t.update(name=probe.NAME.replace('extension_', '')))

    def test_additional_command_flag_rejected(self):
        self.assert_rejected(lambda t: t['flight_command'].append('--new-flag'))

    def test_drop_clock_evaluator_rejected(self):
        self.assert_rejected(lambda t: t['evaluations'].pop(0))

    def test_change_evaluator_order_rejected(self):
        self.assert_rejected(lambda t: t['evaluations'].reverse())

    def test_evaluator_threshold_change_rejected(self):
        self.assert_rejected(lambda t: t['evaluations'][0]['command'].extend(['--tolerance', '.1']))

    def test_old_root_in_evaluator_rejected(self):
        self.assert_rejected(lambda t: t['evaluations'][1]['command'].__setitem__(1,
            '/root/uav_tracking_fullplan_v4_humble43/scripts/run_research_session.sh'))

    def test_extra_trial_field_rejected(self):
        self.assert_rejected(lambda t: t.update(unregistered=True))

    def test_experiment_nonformal_single(self):
        value = probe.experiment()
        self.assertEqual(value['flight_count'], 1)
        self.assertFalse(value['counted_as_core_or_formal'])
        self.assertEqual(value['desired_distance_m'], 12.)

    def test_cli_missing_plan_arguments_returns_refusal_code(self):
        # Missing root/prefix fail the first validate_args check, before Backend.
        result = subprocess.run([sys.executable, '-B', probe.__file__, 'plan'],
            cwd=probe.HERE, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=10, check=False)
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        self.assertIn('REFUSED_OR_ORIGINAL_ATTEMPT_RETAINED', result.stderr)
        self.assertIn('Only fresh45 recording diagnostic is supported', result.stderr)


class ArchivedPosixPath(PurePosixPath):
    """Lexical Linux paths only; original frozen availability is restored by runner.

    This scoped Windows fixture changes no production source or dependency global
    outside the test call, and opens no Linux root, model, bag, or runtime process.
    """
    def is_file(self):
        return False


class WholeValidateOneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        review_path = probe.HERE/'reviewed_freeze_review_v4_humble45_01.json'
        cls.review = probe.read(review_path)
        source = cls.review['source_root']
        if os.name == 'nt' and source.startswith('/mnt/d/'):
            source = 'D:/' + source[len('/mnt/d/'):]
        cls.project = Path(source)
        runner_path = cls.project/'scripts/run_reliability_v4.py'
        if probe.pin(runner_path)['sha256'] != cls.review['files']['scripts/run_reliability_v4.py']:
            raise AssertionError('Pure tests require the actual reviewed45 runner source bytes')
        spec = importlib.util.spec_from_file_location('recording45_v2_pure_actual_runner', runner_path)
        cls.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.runner)
        cls.protocol_raw = (cls.project/policy.PROTOCOL_PATH).read_bytes()
        if hashlib.sha256(cls.protocol_raw).hexdigest() != cls.review['files'][policy.PROTOCOL_PATH]:
            raise AssertionError('Pure tests require actual reviewed45 protocol bytes')
        cls.current_protocol = json.loads(cls.protocol_raw)
        cls.reference_path = cls.project/'results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/plan.json'
        if probe.pin(cls.reference_path)['sha256'] != probe.REFERENCE_PLAN_SHA:
            raise AssertionError('Original43 reference bytes changed')
        cls.old_plan = probe.read(cls.reference_path)
        if cls.old_plan['protocol'] != cls.current_protocol:
            raise AssertionError('Actual43 reference must retain the actual current512 protocol')

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='recording45_v2_validate_one_')
        self.addCleanup(directory.cleanup)
        protocol_path = Path(directory.name)/'protocol.json'
        protocol_path.write_bytes(self.protocol_raw)
        self.protocol_path = protocol_path
        self.backend = SimpleNamespace(
            runner=self.runner,
            review={'source_root': str(self.project)},
            candidate={'protocol': probe.pin(protocol_path)},
            core=SimpleNamespace(policy=policy),
            checks=SimpleNamespace(require_plan_resources=self.forbidden_legacy_checker))
        def remap(value):
            if isinstance(value, str):
                return value.replace('/root/uav_tracking_fullplan_v4_humble43', probe.ROOT).replace(
                    'reliability_v4_humble43_extensions_probe01', probe.PREFIX)
            if isinstance(value, list):
                return [remap(item) for item in value]
            if isinstance(value, dict):
                return {key: remap(item) for key, item in value.items()}
            return value
        self.plan = remap(deepcopy(self.old_plan))
        self.plan.update(prefix=probe.PREFIX, frozen_root=probe.ROOT,
            selected_classes=['car'], selected_seeds=[4],
            selected_groups=['stage1_velocity', 'stage1_position'],
            selected_extension_conditions=['far_distance'])
        self.plan['trials'] = [trial for trial in self.plan['trials'] if trial['id'] == probe.SLOT]
        self.plan['protocol'] = deepcopy(self.current_protocol)

    @staticmethod
    def forbidden_legacy_checker(plan):
        raise AssertionError('Legacy640/.25/600 resource checker must never run')

    def validate(self):
        # Re-sign each negative fixture so failure cannot be a stale digest alone.
        self.plan['plan_sha256'] = self.runner.digest(self.plan, ('plan_sha256',))
        with patch.object(self.runner, 'Path', ArchivedPosixPath):
            return probe.validate_one(self.plan, self.backend, None)

    def assert_protocol_rejected(self, mutate):
        mutate(self.plan['protocol'])
        with self.assertRaises(ValueError):
            self.validate()

    def test_actual_current512_complete_validate_one_passes(self):
        bound = self.validate()
        self.assertEqual(bound['plan']['sha256'], probe.REFERENCE_PLAN_SHA)
        self.assertEqual(self.plan['protocol']['resources']['car']['inference_image_size'], 512)
        self.assertEqual(self.plan['protocol']['real_time_factor'], .125)
        self.assertEqual(self.plan['protocol']['flight_wall_timeout_s'], 1000.)
        self.assertEqual(self.plan['protocol']['safety_gates']['max_observation_age_s'], .6)
        self.assertEqual(self.plan['protocol']['safety_gates']['max_prediction_duration_s'], .75)
        self.assertTrue(bound['original_failure_retained'])

    def test_legacy640_resource_rejected(self):
        self.assert_protocol_rejected(lambda p: p['resources']['car'].update(inference_image_size=640))

    def test_legacy_rtf025_rejected(self):
        self.assert_protocol_rejected(lambda p: p.update(real_time_factor=.25))

    def test_legacy_wall600_rejected(self):
        self.assert_protocol_rejected(lambda p: p.update(flight_wall_timeout_s=600.))

    def test_observation_age_change_from_original06_rejected(self):
        self.assert_protocol_rejected(lambda p: p['safety_gates'].update(max_observation_age_s=.61))

    def test_prediction_duration_change_from_original075_rejected(self):
        self.assert_protocol_rejected(lambda p: p['safety_gates'].update(max_prediction_duration_s=.76))

    def test_duration_change_rejected(self):
        self.assert_protocol_rejected(lambda p: p.update(duration_s=76.))

    def test_inference_rate_change_rejected(self):
        self.assert_protocol_rejected(lambda p: p.update(max_inference_rate_hz=11.))

    def test_status_timing_change_rejected(self):
        self.assert_protocol_rejected(lambda p: p['supervisor_status_timing'].update(status_timeout_wall_s=11.))

    def test_model04_change_rejected(self):
        self.assert_protocol_rejected(lambda p: p['resources']['car'].update(model='models/yolo11m.pt'))

    def test_cpu4_change_rejected(self):
        self.assert_protocol_rejected(lambda p: p['resources']['car'].update(inference_threads=2))

    def test_car_two_face_change_rejected(self):
        self.assert_protocol_rejected(lambda p: p['resources']['car'].update(navigation_correlated_two_face_bound=False))

    def test_person_two_face_enable_rejected(self):
        self.assert_protocol_rejected(lambda p: p['resources']['person'].update(navigation_correlated_two_face_bound=True))

    def test_car512_registration_change_rejected(self):
        self.assert_protocol_rejected(lambda p: p['car_input_scale_registration'].update(revision='car_train20_04_m640_cpu4_v1'))

    def test_adapter50_registration_change_rejected(self):
        self.assert_protocol_rejected(lambda p: p[policy.PACING_FIELD].update(px4_adapter_publish_rate_hz=40.))

    def test_pacing_source_safety_change_rejected(self):
        self.assert_protocol_rejected(lambda p: p[policy.PACING_FIELD].update(safety_source_time_gates='changed'))

    def test_complete_candidate_protocol_equality_rejects_extra_field(self):
        # The real normal runner accepts extra descriptive keys; this must reach
        # the new full candidate equality gate rather than a generic protocol error.
        self.plan['protocol']['unregistered_descriptive_key'] = 'different'
        with self.assertRaisesRegex(ValueError, 'Plan protocol differs from actual immutable'):
            self.validate()

    def test_candidate_protocol_original_bytes_must_remain_bound(self):
        self.protocol_path.write_bytes(self.protocol_raw + b' ')
        with self.assertRaisesRegex(ValueError, 'Exact original metadata path/SHA differs'):
            self.validate()

    def test_real_validate_plan_rejects_changed_trial_argv(self):
        self.plan['trials'][0]['flight_command'].append('--unregistered')
        with self.assertRaises(ValueError):
            self.validate()


if __name__ == '__main__':
    unittest.main()
