"""Verify the instrument uses the real helper and preserves the baseline."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from tools.diagnostics.detector_tail_candidate01 import benchmark_cpu_policy as original
from tools.diagnostics.detector_tail_candidate01 import benchmark_production_guard as benchmark
from tests.test_detector_cpu_policy_benchmark import FakeTorch


class ProductionGuardBenchmarkTests(unittest.TestCase):
    def test_guarded_calls_imported_production_helper_for_each_prediction(self):
        torch = FakeTorch()
        policy = benchmark.create_policy(torch, NS(setNumThreads=lambda _: None), "guarded", 4)
        actual_helper, metadata = benchmark.load_production_helper()
        self.assertIs(policy.helper, actual_helper)
        self.assertEqual(policy.helper_metadata, metadata)
        policy.helper = Mock(wraps=actual_helper)
        policy.initialize()
        policy(None)  # Existing pool is four; real production helper skips setter.
        torch.threads = 8  # Lazy backend or external reset must be corrected.
        policy(None)
        self.assertEqual(policy.helper.call_count, 2)
        self.assertEqual(torch.calls, [4, 4])
        self.assertEqual([row["explicit_python_setter_calls"] for row in policy.callbacks], [0, 1])
        self.assertEqual([row["after"] for row in policy.callbacks], [4, 4])
        self.assertTrue(all(row["production_helper"] == metadata for row in policy.callbacks))

    def test_baseline_uses_unchanged_original_policy_without_loading_guard(self):
        old_class = original.CpuPolicy
        torch = FakeTorch()
        with patch.object(benchmark, "load_production_helper", side_effect=AssertionError("baseline must not load guard")):
            policy = benchmark.create_policy(torch, NS(setNumThreads=lambda _: None), "baseline", 4)
            self.assertIs(type(policy), old_class)
            policy.initialize()
            policy(None); policy(None)
        self.assertEqual(torch.calls, [4, 4, 4])
        self.assertIs(original.CpuPolicy, old_class)

    def test_helper_source_rejects_installed_module_and_substituted_function(self):
        helper, _ = benchmark.load_production_helper()
        for module in (
            NS(__file__=benchmark.__file__, enforce_cpu_thread_count=helper),
            NS(__file__=str(benchmark.DETECTOR_SOURCE), enforce_cpu_thread_count=lambda *_: 4),
        ):
            with self.subTest(module=module), self.assertRaisesRegex(ValueError, "different source"):
                benchmark.validate_helper_source(module)

    def test_production_exception_is_not_hidden_or_replaced_by_instrument(self):
        torch = NS(get_num_threads=lambda: 8, set_num_threads=lambda _: None)
        policy = benchmark.create_policy(torch, NS(), "guarded", 4)
        with self.assertRaisesRegex(RuntimeError, "did not take effect"):
            policy(None)
        self.assertEqual(policy.callbacks, [])

    def test_default_and_source_receipt_pin_the_real_production_file(self):
        args = benchmark.parse_args(["--input-dir", "raw", "--model", "weight.pt", "--output", "new", "--policy", "guarded"])
        self.assertEqual((args.warmup, args.limit_images, args.repeats, args.period), (3, 12, 12, 1.))
        sources = benchmark.source_metadata()
        helper, metadata = benchmark.load_production_helper()
        self.assertEqual(sources["detector"]["sha256"], metadata["sha256"])
        self.assertEqual(sources["detector"]["path"], metadata["path"])
        self.assertEqual(sources["derived_from"]["sha256"], benchmark.EXPECTED_INSTRUMENT_SHA256)
        self.assertEqual(helper.__name__, "enforce_cpu_thread_count")


if __name__ == "__main__":
    unittest.main()
