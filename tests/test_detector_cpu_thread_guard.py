"""The production thread guard corrects resets and preserves a valid pool."""
from threading import Barrier, Lock, Thread, local
from types import SimpleNamespace as NS
import unittest

from tests import test_detector_worker as worker_tests

detector = worker_tests.detector


class MutableTorch:
    def __init__(self, count):
        self.count, self.set_calls = count, []

    def get_num_threads(self):
        return self.count

    def set_num_threads(self, count):
        self.set_calls.append(count)
        self.count = count


class CpuThreadGuardTests(unittest.TestCase):
    def test_lazy_backend_reset_is_corrected_before_first_prediction(self):
        torch = MutableTorch(8)
        self.assertEqual(detector.enforce_cpu_thread_count(torch, 4), 4)
        self.assertEqual(torch.set_calls, [4])

    def test_same_effective_pool_is_not_set_again_on_following_predictions(self):
        torch = MutableTorch(4)
        for _ in range(4):
            self.assertEqual(detector.enforce_cpu_thread_count(torch, 4), 4)
        self.assertEqual(torch.set_calls, [])

    def test_external_reset_is_detected_after_successful_earlier_prediction(self):
        torch = MutableTorch(4)
        detector.enforce_cpu_thread_count(torch, 4)
        torch.count = 8
        self.assertEqual(detector.enforce_cpu_thread_count(torch, 4), 4)
        self.assertEqual(torch.set_calls, [4])

    def test_background_threads_read_their_own_effective_pool_without_a_global_ready_flag(self):
        state, lock, barrier = local(), Lock(), Barrier(2)
        results, calls, errors = [], [], []
        def set_threads(count):
            state.count = count
            with lock:
                calls.append(state.name)
        torch = NS(get_num_threads=lambda: state.count, set_num_threads=set_threads)
        def run(name, count):
            try:
                state.name, state.count = name, count
                barrier.wait(timeout=2.)
                first = detector.enforce_cpu_thread_count(torch, 4)
                second = detector.enforce_cpu_thread_count(torch, 4)
                with lock:
                    results.append((name, first, second))
            except BaseException as error:
                with lock:
                    errors.append(error)
        threads = [Thread(target=run, args=("already_four", 4)), Thread(target=run, args=("reset_to_eight", 8))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3.)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), [("already_four", 4, 4), ("reset_to_eight", 4, 4)])
        self.assertEqual(calls, ["reset_to_eight"])

    def test_ineffective_setter_raises_instead_of_reporting_an_invented_limit(self):
        torch = NS(get_num_threads=lambda: 8, set_num_threads=lambda _: None)
        with self.assertRaisesRegex(RuntimeError, "did not take effect"):
            detector.enforce_cpu_thread_count(torch, 4)

    def test_guard_exception_reaches_real_production_worker_error_handler(self):
        torch = NS(get_num_threads=lambda: 8, set_num_threads=lambda _: None)
        errors = []
        worker = worker_tests.NonQueuingWorker(
            lambda _: detector.enforce_cpu_thread_count(torch, 4), errors.append)
        try:
            self.assertTrue(worker.submit(None))
            self.assertTrue(worker.wait_idle(timeout=2.))
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], RuntimeError)
            self.assertIn("did not take effect", str(errors[0]))
            self.assertFalse(worker.busy)
        finally:
            worker.shutdown()


if __name__ == "__main__":
    unittest.main()
