"""Pure source41 helper checks; no WSL, payload, planning, or simulator."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import source_runtime41 as m


class SourceBindings(unittest.TestCase):
    def test_manifest_has_new_root_and_no_probe_or_runtime_authority(self):
        value = m.tool_manifest()
        self.assertEqual(value['frozen_root'], '/root/uav_tracking_fullplan_v4_humble41')
        self.assertFalse(value['single_probe_requirement'])
        self.assertFalse(value['dependency_globals_modified'])
        self.assertFalse(value['runtime_actions_exposed'])
        self.assertEqual(value['stable_tools_canonical_sha256'], m.STABLE_CANONICAL)

    def test_build_receipts_are_source41_own_summary_and_actual_actions(self):
        with patch.object(m.stable, 'metadata_binding', side_effect=lambda p, **k: {'path': str(p), 'sha256': 'a'*64}):
            result = m.build_evidence({'frozen_root': m.ROOT})
            self.assertEqual(set(result), {'summary', 'build_terminal', 'validate_terminal'})
            self.assertIn('/reviewed_freeze_actions_v4_humble41/build/', result['build_terminal']['path'])
            self.assertTrue(result['summary']['path'].startswith(m.ROOT+'/results/'))
            self.assertRaises(ValueError, m.build_evidence, {'frozen_root': m.ROOT.replace('41', '40')})

    def test_class_policy_requires_car_true_and_person_omission(self):
        protocol = {'resources': {'car': {m.EXCLUSIVE_FIELD: True}, 'person': {}}}
        runner = SimpleNamespace(exclusive_navigation_declared=lambda p: True,
            exclusive_navigation_summary=lambda p: {'car': True, 'person': False})
        self.assertEqual(m.validate_class_policy(protocol, runner), m.EXPECTED_CLASS_POLICY)
        for cls, value in (('car', False), ('car', 1), ('person', False), ('person', True)):
            changed = deepcopy(protocol); changed['resources'][cls][m.EXCLUSIVE_FIELD] = value
            self.assertRaises(ValueError, m.validate_class_policy, changed, runner)

    def test_runtime_birth_values_use_strict_class_boolean(self):
        for cls in ('car', 'person'):
            expected = cls == 'car'
            config = {'car_surface_recovery': expected}
            params = {'uav_tracking_detection': {'ros__parameters': {'car_surface_recovery_enabled': expected}},
                'uav_tracking_state_estimator': {'ros__parameters': {'supported_birth_confirmation_required': expected}}}
            self.assertEqual(m.validate_supported_birth_runtime(cls, config, params)['target_class'], cls)
            for bad in (int(expected), str(expected), None, not expected):
                changed = deepcopy(params)
                changed['uav_tracking_state_estimator']['ros__parameters']['supported_birth_confirmation_required'] = bad
                self.assertRaises(ValueError, m.validate_supported_birth_runtime, cls, config, changed)

    def test_entry_rechecks_original_source_and_metadata_without_mutating_built(self):
        metadata = {'path': '/synthetic/summary.json', 'sha256': 'a'*64}
        built = {'_reviewed_tools_sha256': m.canonical(m.tool_manifest()),
            'source': {'actual_source41': True}, 'closed_original_evidence': {'retained40': True},
            'bound_build_metadata': {'summary': metadata}}
        before = deepcopy(built)
        review = {'_review_binding': {'path': '/synthetic/review.json', 'sha256': 'b'*64}}
        actual = {'source': built['source'], 'closed_original_evidence': built['closed_original_evidence']}
        with patch.object(m.generic, 'action_binding', return_value=actual), \
                patch.object(m.stable, 'metadata_binding', return_value=metadata), \
                patch.object(m, 'source_policy_binding', return_value={'policy': True}):
            result = m.entry_binding(review, built)
            self.assertEqual(result['source'], built['source'])
            self.assertEqual(built, before)
            self.assertRaises(ValueError, m.entry_binding, review, {**built, '_reviewed_tools_sha256': 'f'*64})


if __name__ == '__main__':
    unittest.main()
