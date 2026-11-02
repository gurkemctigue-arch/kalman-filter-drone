"""Synthetic path/file metadata and fake exec only; never import a guard.

The production Linux literal is checked separately. Windows file fixtures
relocate its constant to one temporary file and synthetic digest, without
adding a caller-supplied policy argument to the production API.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import formal_supplementary_preflight as gate
import test_formal_supplementary_preflight as original


ACTUAL_FIXED_PIN = {
    'path': '/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py',
    'sha256': 'e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e',
}


class GuardBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='formal55_guard_synthetic_')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.fixed = self.base / 'synthetic_fixed_audit' / 'tools' / 'reliability_v4_guard.py'
        self.fixed.parent.mkdir(parents=True)
        self.fixed.write_bytes(b'# tiny synthetic guard source; never imported or executed\n')
        self.synthetic_fixed_pin = gate.pin(self.fixed)

    def full_external_fixture(self):
        case = original.Fixture(self.base)
        case.admission['tool'] = deepcopy(self.synthetic_fixed_pin)
        case.save_admission()
        case.contract['admission'] = case.admission_pin
        case.contract['adapter']['argv_prefix'][3] = case.admission_pin['sha256']
        case.save_contract()
        return case

    def test_production_literal_and_manifest_are_the_single_fixed_external_pin(self):
        self.assertEqual(gate.FIXED_AUDIT_GUARD, ACTUAL_FIXED_PIN)
        self.assertEqual(gate.tool_manifest()['guard_source_policy'], {
            'legacy': 'actual final_root/tools/reliability_v4_guard.py',
            'fixed_external': ACTUAL_FIXED_PIN})
        self.assertEqual(gate.KIND, 'FORMAL55_SUPPLEMENTARY_BINDING_ONLY_NOT_ADMISSION')

    def test_actual_linux_literal_policy_only_with_explicit_mock_file_boundary(self):
        # Pure Linux path-policy check; this never claims that the native file
        # was read on Windows. Physical file hashing is exercised below.
        with patch.object(gate, 'checked', return_value=Path(ACTUAL_FIXED_PIN['path'])) as checked:
            result = gate.guard_source_binding(deepcopy(ACTUAL_FIXED_PIN), self.base / 'other_final')
        checked.assert_called_once_with(ACTUAL_FIXED_PIN)
        self.assertEqual(result, Path(ACTUAL_FIXED_PIN['path']))

    def test_original_same_root_full_contract_remains_accepted(self):
        case = original.Fixture(self.base)
        context = case.validate()
        self.assertEqual(context['admission']['tool'], gate.pin(case.guard_path))
        self.assertIn(context['admission']['tool'], context['input_pins'])
        self.assertFalse(case.audit_path.exists())

    def test_fixed_external_full_contract_and_fake_exec_keep_the_same_checked_pin(self):
        with patch.object(gate, 'FIXED_AUDIT_GUARD', self.synthetic_fixed_pin):
            case = self.full_external_fixture()
            context = case.validate()
            self.assertEqual(context['admission']['tool'], self.synthetic_fixed_pin)
            self.assertIn(self.synthetic_fixed_pin, context['input_pins'])
            self.assertFalse(case.audit_path.exists())
            with self.assertRaises(original.ExecObserved):
                case.run()
            self.assertEqual(len(case.calls), 1)
            self.assertEqual(case.calls[0][1], case.contract['adapter']['argv_prefix']
                             + ['run-one', '--manifest', str(case.admission_path)])

    def test_identical_source_at_any_other_external_path_is_refused(self):
        other = self.base / 'identical_guard.py'
        other.write_bytes(self.fixed.read_bytes())
        with patch.object(gate, 'FIXED_AUDIT_GUARD', self.synthetic_fixed_pin):
            with self.assertRaisesRegex(ValueError, 'exact fixed audit path/SHA'):
                gate.guard_source_binding(gate.pin(other), self.base / 'other_final')

    def test_wrong_declared_or_actual_rehashed_sha_at_fixed_path_is_refused(self):
        with patch.object(gate, 'FIXED_AUDIT_GUARD', self.synthetic_fixed_pin):
            wrong_declared = {**self.synthetic_fixed_pin, 'sha256': 'a' * 64}
            with self.assertRaisesRegex(ValueError, 'physical original-file pin'):
                gate.guard_source_binding(wrong_declared, self.base / 'other_final')
            self.fixed.write_bytes(b'# changed synthetic source; still never executed\n')
            with self.assertRaisesRegex(ValueError, 'exact fixed audit path/SHA'):
                gate.guard_source_binding(gate.pin(self.fixed), self.base / 'other_final')

    def test_changed_source_with_the_original_binding_is_refused(self):
        with patch.object(gate, 'FIXED_AUDIT_GUARD', self.synthetic_fixed_pin):
            self.fixed.write_bytes(self.fixed.read_bytes() + b'# changed\n')
            with self.assertRaisesRegex(ValueError, 'physical original-file pin'):
                gate.guard_source_binding(self.synthetic_fixed_pin, self.base / 'other_final')

    def test_fixed_source_changed_after_validation_is_rechecked_before_fake_exec(self):
        with patch.object(gate, 'FIXED_AUDIT_GUARD', self.synthetic_fixed_pin):
            case = self.full_external_fixture()
            append = gate.append_audit
            def changed_after_audit(context):
                append(context)
                self.fixed.write_bytes(self.fixed.read_bytes() + b'# changed after validation\n')
            with patch.object(gate, 'append_audit', side_effect=changed_after_audit):
                with self.assertRaisesRegex(ValueError, 'physical original-file pin'):
                    case.run()
            self.assertEqual(case.calls, [])
            self.assertTrue(case.audit_path.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
