"""Independent fake-only I/O/provenance edges; no real recording or ROS import."""
import ast
from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import extract_native_causal_window as tool
from test_extract_native_causal_window import Fixture, FakeRuntime


class IndependentNativeExportChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='independent_native_export_fake_')
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(self.temp.name)

    def test_all_original_fake_bytes_unchanged_and_exact_io_passes(self):
        original = {str(path.relative_to(self.fixture.root)): path.read_bytes()
                    for path in self.fixture.root.rglob('*') if path.is_file()}
        digest = tool.digest
        calls = []
        def counted(path):
            calls.append(Path(path).resolve())
            return digest(path)
        with patch.object(tool, 'digest', side_effect=counted):
            result = self.fixture.run()
        after = {str(path.relative_to(self.fixture.root)): path.read_bytes()
                 for path in self.fixture.root.rglob('*') if path.is_file()}
        self.assertEqual(original, after)
        self.assertEqual(calls, [self.fixture.payload, self.fixture.payload])
        self.assertEqual(result['compressed_hash_passes'], 2)
        self.assertEqual(self.fixture.runtime.opens, 1)
        self.assertEqual(self.fixture.runtime.reader.index, len(self.fixture.rows))

    def test_changed_generated_message_module_invalidates_completed_raw_export(self):
        generated = self.fixture.base / 'synthetic_generated_message.py'
        generated.write_text('# pinned fake generated class\n', encoding='utf-8')
        runtime = FakeRuntime(self.fixture)
        runtime.receipt['generated_module_pins'] = {'synthetic/msg/Class': tool.pin(generated)}
        self.fixture.on_close = lambda: generated.write_text('# changed after export\n', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            tool.execute(self.fixture.args, runtime_factory=lambda context, args: runtime)
        report = tool.decode((self.fixture.output / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'ABORTED_PARTIAL_ORIGINALS_RETAINED')
        self.assertFalse(report['original_pins_and_compressed_payloads_unchanged'])
        self.assertTrue(runtime.closed)

    def test_no_close_api_and_borrowed_teardown_error_still_remove_owned_cache(self):
        runtime = tool.NativeRuntime.__new__(tool.NativeRuntime)
        runtime.module, runtime.receipt = None, {'owned_native_caches': []}
        @contextmanager
        def original(path, module):
            with tempfile.TemporaryDirectory(prefix='fake_borrowed_') as nested:
                self.assertTrue(Path(nested).is_relative_to(self.fixture.cache))
                yield object(), {'fake_only': True}
            raise ValueError('fake borrowed teardown error')
        runtime.open_original = original
        before = tempfile.tempdir
        with self.assertRaisesRegex(ValueError, 'borrowed teardown'):
            with runtime.open({'cache_parent': self.fixture.cache, 'trial': self.fixture.trial}):
                pass
        report = runtime.receipt['owned_native_caches'][0]
        self.assertEqual(report['reader_close_api'], 'NOT_AVAILABLE_REFERENCE_RELEASE_ONLY')
        self.assertTrue(report['removed'])
        self.assertTrue(report['tempfile_tempdir_restored'])
        self.assertIs(tempfile.tempdir, before)
        self.assertEqual(list(self.fixture.cache.iterdir()), [])

    def test_insufficient_cache_never_creates_output_or_runtime(self):
        factories = []
        def runtime(context, args):
            factories.append(True)
            raise AssertionError('no runtime construction')
        with patch.object(tool.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError, 'Insufficient'):
                tool.execute(self.fixture.args, runtime_factory=runtime)
        self.assertEqual(factories, [])
        self.assertFalse(self.fixture.output.exists())

    def test_corrupt_compressed_bytes_are_refused_before_native_open(self):
        self.fixture.payload.write_bytes(b'X' * self.fixture.payload.stat().st_size)
        runtime = FakeRuntime(self.fixture)
        with self.assertRaises(RuntimeError):
            tool.execute(self.fixture.args, runtime_factory=lambda context, args: runtime)
        self.assertEqual(runtime.opens, 0)
        result = tool.decode((self.fixture.output / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(result['status'], 'ABORTED_PARTIAL_ORIGINALS_RETAINED')
        self.assertEqual(result['native_traversals'], 0)

    def test_duplicate_exact_camera_info_keeps_both_original_occurrences(self):
        row = next(row for row in self.fixture.rows if row[0] == tool.INFO)
        self.fixture.rows.append(row)
        for kind in ('raw_validation', 'native_reader_validation'):
            self.fixture.integrity[kind]['topic_counts'][tool.INFO] += 1
        self.fixture.integrity['native_reader_validation']['message_count'] += 1
        self.fixture.save(self.fixture.trial / 'bag_integrity.json', self.fixture.integrity)
        self.fixture.refresh()
        self.fixture.pin_args()
        self.fixture.run()
        request = tool.decode((self.fixture.output / 'image_requests.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(request['status'], 'MISSING_OR_DUPLICATE_NO_SUBSTITUTION')
        self.assertEqual(len(request['components'][tool.INFO]), 2)
        self.assertNotEqual(request['components'][tool.INFO][0]['record_index'], request['components'][tool.INFO][1]['record_index'])

    def test_wire_schema_equivalence_keeps_bounds_and_signedness(self):
        self.assertEqual(tool.wire_type('float64[36]'), tool.wire_type('double[36]'))
        self.assertEqual(tool.wire_type('uint8[<=4]'), tool.wire_type('sequence<uint8, 4>'))
        self.assertNotEqual(tool.wire_type('uint8[<=4]'), tool.wire_type('sequence<uint8>'))
        self.assertNotEqual(tool.wire_type('int8'), tool.wire_type('uint8'))

    def test_sources_parse_using_python310_grammar(self):
        for name in ('extract_native_causal_window.py', 'test_extract_native_causal_window.py', Path(__file__).name):
            ast.parse(Path(__file__).with_name(name).read_text(encoding='utf-8'), feature_version=(3, 10))


if __name__ == '__main__':
    unittest.main(verbosity=2)
