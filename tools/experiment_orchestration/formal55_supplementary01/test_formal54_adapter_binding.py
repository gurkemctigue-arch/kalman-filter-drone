"""Small synthetic adapter metadata; no adapter import/exec, WSL or flight."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import formal_supplementary_preflight as gate


class ExplicitAdapterBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='formal54_adapter_metadata_')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.directory = self.base / 'synthetic_actual48'
        self.directory.mkdir()
        for name in (*gate.ADAPTER_NAMES.values(), 'test_formal48_guard_adapter01.py'):
            (self.directory / name).write_text('# synthetic code never executed\n', encoding='utf-8')
        self.manifest = {'schema_version': 1, 'scope': gate.ADAPTER_SCOPE,
            'files': {path.name: gate.pin(path)['sha256'] for path in self.directory.iterdir()}}
        self.approved = gate.canonical(self.manifest)
        self.describe_path = self.base / 'actual_describe.json'
        self.description = {'manifest': self.manifest, 'tools_canonical_sha256': self.approved,
                            'actual_action_executed': False}
        self.save(self.describe_path, self.description)
        self.path = self.base / 'identity.json'
        self.identity = {'schema_version': 1, 'kind': gate.ADAPTER_KIND,
            'created_utc': '2020-01-01T00:00:00+00:00',
            'shell': gate.pin(self.directory / gate.ADAPTER_NAMES['shell']),
            'python': gate.pin(self.directory / gate.ADAPTER_NAMES['python']),
            'describe': gate.pin(self.describe_path), 'manifest_canonical_sha256': self.approved,
            'reviewed_tools_sha256': self.approved}
        self.save(self.path, self.identity)
        self.when = datetime(2020, 1, 2, tzinfo=timezone.utc)

    @staticmethod
    def save(path, value):
        path.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')

    def check(self, approved=None):
        return gate.adapter_identity(gate.pin(self.path), approved or self.approved, self.when)

    def refresh(self):
        self.save(self.describe_path, self.description)
        self.identity['describe'] = gate.pin(self.describe_path)
        self.save(self.path, self.identity)

    def reject(self):
        with self.assertRaises((ValueError, KeyError, OSError)):
            self.check()

    def test_actual48_binding_accepts_exact_physical_files_and_actual_describe(self):
        identity, pins = self.check()
        self.assertEqual(identity, self.identity)
        self.assertEqual(len(pins), 5)
        self.assertEqual({Path(item['path']).suffix for item in pins}, {'.json', '.py', '.sh'})

    def test_describe_raw_bytes_pin_refuses_even_whitespace_change(self):
        self.describe_path.write_bytes(self.describe_path.read_bytes() + b' ')
        self.reject()

    def test_describe_internal_canonical_cannot_be_replaced_by_pass_heading(self):
        self.description['tools_canonical_sha256'] = 'a' * 64
        self.refresh()
        self.reject()

    def test_self_consistent_forged_manifest_cannot_replace_independent_reviewed_sha(self):
        self.manifest['invented_pass'] = True
        forged = gate.canonical(self.manifest)
        self.description['tools_canonical_sha256'] = forged
        self.identity['manifest_canonical_sha256'] = forged
        self.identity['reviewed_tools_sha256'] = forged
        self.refresh()
        self.reject()

    def test_independent_cli_reviewed_sha_is_required_and_separate(self):
        for approved in ('a' * 64, '', None):
            with self.subTest(approved=approved), self.assertRaises(ValueError):
                gate.adapter_identity(gate.pin(self.path), approved, self.when)

    def test_code_tamper_with_refreshed_identity_pin_still_refuses_manifest_mismatch(self):
        path = self.directory / gate.ADAPTER_NAMES['python']
        path.write_bytes(path.read_bytes() + b'# tampered\n')
        self.identity['python'] = gate.pin(path)
        self.save(self.path, self.identity)
        self.reject()

    def test_actual_adapter_author_test_is_part_of_the_bound_manifest(self):
        path = self.directory / 'test_formal48_guard_adapter01.py'
        path.write_bytes(path.read_bytes() + b'# tampered\n')
        self.reject()

    def test_binding_cannot_be_future_or_naive_relative_to_prospective_contract(self):
        for value in ('2030-01-01T00:00:00+00:00', '2020-01-01T00:00:00'):
            self.identity['created_utc'] = value
            self.save(self.path, self.identity)
            self.reject()

    def test_description_cannot_claim_flight_action_or_different_scope(self):
        self.description['actual_action_executed'] = True
        self.refresh()
        self.reject()
        self.description['actual_action_executed'] = False
        self.manifest['scope'] = 'HISTORICAL41'
        changed = gate.canonical(self.manifest)
        self.description['tools_canonical_sha256'] = changed
        self.identity['manifest_canonical_sha256'] = changed
        self.identity['reviewed_tools_sha256'] = changed
        self.refresh()
        with self.assertRaises(ValueError):
            self.check(approved=changed)

    def test_old41_python_name_is_not_an_actual48_identity(self):
        path = self.directory / 'formal41_guard_adapter01.py'
        path.write_bytes((self.directory / gate.ADAPTER_NAMES['python']).read_bytes())
        self.identity['python'] = gate.pin(path)
        self.save(self.path, self.identity)
        self.reject()

    def test_actual_admission_file_sha_and_internal_canonical_are_not_interchangeable(self):
        admission = {'path': str(self.base / 'admission.json'), 'sha256': 'b' * 64}
        value = {'shell': self.identity['shell'], 'python': self.identity['python'],
            'reviewed_tools_sha256': self.approved, 'resolutions': {},
            'argv_prefix': ['bash', self.identity['shell']['path'], '--manifest-sha256', 'c' * 64,
                            '--reviewed-tools-sha256', self.approved]}
        with self.assertRaises(ValueError):
            gate.adapter_prefix(value, admission, self.identity)

    def test_contract_cannot_delegate_an_identical_copy_at_an_unbound_path(self):
        other = self.base / 'copy'
        other.mkdir()
        path = other / gate.ADAPTER_NAMES['shell']
        path.write_bytes((self.directory / gate.ADAPTER_NAMES['shell']).read_bytes())
        value = {'shell': gate.pin(path), 'python': self.identity['python'],
            'reviewed_tools_sha256': self.approved, 'resolutions': {}, 'argv_prefix': []}
        with self.assertRaises(ValueError):
            gate.adapter_prefix(value, {'sha256': 'a' * 64}, self.identity)


if __name__ == '__main__':
    unittest.main()
