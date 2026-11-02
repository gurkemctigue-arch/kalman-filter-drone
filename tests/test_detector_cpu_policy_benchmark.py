"""CPU policy and pacing contracts, without torch/ROS or inference."""
from contextlib import redirect_stderr
import importlib.util
import io
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "tools/diagnostics/detector_tail_candidate01/benchmark_cpu_policy.py"
SPEC = importlib.util.spec_from_file_location("detector_cpu_policy_benchmark", SOURCE)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class FakeTorch:
    def __init__(self, threads=8):
        self.threads, self.calls, self.interop_calls = threads, [], []

    def get_num_threads(self):
        return self.threads

    def set_num_threads(self, value):
        self.calls.append(value)
        self.threads = value

    def set_num_interop_threads(self, value):
        self.interop_calls.append(value)


class CpuPolicyTests(unittest.TestCase):
    def make(self, policy):
        torch, cv_calls = FakeTorch(), []
        return benchmark.CpuPolicy(torch, NS(setNumThreads=cv_calls.append), policy, 4), torch, cv_calls

    def test_baseline_preserves_repeated_production_callback_enforcement(self):
        policy, torch, cv_calls = self.make("baseline")
        policy.initialize()
        policy(None); policy(None)
        self.assertEqual(torch.calls, [4, 4, 4])
        self.assertEqual(torch.interop_calls, [])
        self.assertEqual(cv_calls, [])
        self.assertTrue(all(row["set_called"] for row in policy.callbacks))

    def test_guarded_still_corrects_lazy_backend_reset_then_skips_same_count(self):
        policy, torch, cv_calls = self.make("guarded")
        policy.initialize()
        torch.threads = 8  # Ultralytics lazy select_device resets the pool.
        policy(None); policy(None)
        self.assertEqual(torch.calls, [4, 4])
        self.assertEqual([row["before"] for row in policy.callbacks], [8, 4])
        self.assertEqual([row["set_called"] for row in policy.callbacks], [True, False])
        self.assertEqual([row["after"] for row in policy.callbacks], [4, 4])
        self.assertEqual(torch.interop_calls, [])
        self.assertEqual(cv_calls, [])

    def test_bounded_aux_is_an_explicit_separate_initialization_variable(self):
        policy, torch, cv_calls = self.make("bounded_aux")
        policy.initialize()
        policy(None); policy(None)
        self.assertEqual(torch.calls, [4])
        self.assertEqual(torch.interop_calls, [1])
        self.assertEqual(cv_calls, [1])

    def test_callback_rejects_a_pool_change_that_did_not_take_effect(self):
        policy, torch, _ = self.make("guarded")
        torch.set_num_threads = lambda _: None
        with self.assertRaisesRegex(RuntimeError, "did not take effect"):
            policy(None)
        self.assertEqual(policy.callbacks[-1]["after"], 8)

    def test_callback_timing_includes_guard_but_records_it_as_a_predict_subset(self):
        policy, _, _ = self.make("guarded")
        ticks = iter([2.0, 2.05])
        policy.clock = lambda: next(ticks)
        policy(None)
        self.assertAlmostEqual(policy.callbacks[0]["wall_s"], .05)
        self.assertIsInstance(policy.callbacks[0]["native_thread_id"], int)


class PacingAndEnvironmentTests(unittest.TestCase):
    def test_pacing_sleeps_only_remaining_period(self):
        sleeps = []
        benchmark.delay_until_next(10., 1., clock=lambda: 10.4, sleep=sleeps.append)
        self.assertAlmostEqual(sleeps[0], .6)

    def test_late_job_does_not_sleep_or_catch_up_with_a_backlog(self):
        sleeps = []
        benchmark.delay_until_next(10., 1., clock=lambda: 11.8, sleep=sleeps.append)
        benchmark.delay_until_next(11.8, 1., clock=lambda: 12.2, sleep=sleeps.append)
        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], .6)

    def test_first_job_starts_without_delay(self):
        sleeps = []
        benchmark.delay_until_next(None, 1., clock=lambda: 0., sleep=sleeps.append)
        self.assertEqual(sleeps, [])

    def test_inherited_wait_policy_does_not_change_existing_environment(self):
        with patch.dict(os.environ, {"OMP_WAIT_POLICY": "ACTIVE", "KMP_BLOCKTIME": "200"}, clear=True):
            before = dict(os.environ)
            evidence = benchmark.configure_wait_policy("inherited")
            self.assertEqual(dict(os.environ), before)
            self.assertEqual(evidence["inherited"], evidence["after"])

    def test_passive_is_explicit_and_retains_original_values(self):
        with patch.dict(os.environ, {"OMP_WAIT_POLICY": "ACTIVE", "KMP_BLOCKTIME": "200", "MKL_NUM_THREADS": "1"}, clear=True):
            evidence = benchmark.configure_wait_policy("passive")
            self.assertEqual(evidence["inherited"]["OMP_WAIT_POLICY"], "ACTIVE")
            self.assertEqual(evidence["after"]["OMP_WAIT_POLICY"], "PASSIVE")
            self.assertEqual(evidence["after"]["KMP_BLOCKTIME"], "0")
            self.assertEqual(os.environ["MKL_NUM_THREADS"], "1")

    def test_default_is_small_logged_measurement_with_exactly_one_policy(self):
        args = benchmark.parse_args(["--input-dir", "raw", "--model", "weights.pt", "--output", "new", "--policy", "baseline"])
        self.assertEqual((args.policy, args.wait_policy, args.threads, args.imgsz), ("baseline", "inherited", 4, 512))
        self.assertEqual((args.warmup, args.repeats, args.limit_images, args.period), (3, 3, 12, 1.))

    def test_invalid_pacing_and_underpowered_measurements_are_rejected(self):
        base = ["--input-dir", "raw", "--model", "weights.pt", "--output", "new", "--policy", "baseline"]
        for extra in (("--period", "nan"), ("--period", "inf"), ("--period", "-1"),
                      ("--period", "31"), ("--repeats", "1"), ("--warmup", "2"),
                      ("--limit-images", "0"), ("--threads", "8")):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                benchmark.parse_args([*base, *extra])


if __name__ == "__main__":
    unittest.main()
