"""Pure owned-runtime fixtures; no rclpy, nodes, Gazebo or recorder starts."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from queue import Empty, Queue
from types import SimpleNamespace as NS
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("closure_observer_candidate",
    Path(__file__).resolve().parents[1] / "scripts/close_stage1_recording.py")
closure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(closure)


def stamp(seconds=1.):
    total = round(seconds * 1e9)
    return NS(sec=total // 1_000_000_000, nanosec=total % 1_000_000_000)


def diagnostic(receipt=1., *, startup=False, sample=1.):
    return {"schema_version": 1, "mode": "source_sim", "receipt_ros_s": receipt, "output_s": receipt,
        "source_sample_s": sample, "source_publication_s": sample,
        "accepted": not startup, "source_time_valid": not startup,
        "odometry_header_s": None if startup else sample,
        "reason": "ros_clock_not_started" if startup else "validated_source_stamp"}


class FakeRuntime:
    def __init__(self, observer):
        self.observer = observer
        self.queue = Queue()
        self.open_count = self.destroy_count = self.context_shutdown_count = self.spin_count = 0
        self.fail_open = self.fail_destroy = self.block_spin = False
        self.release = threading.Event()
        self.entered = threading.Event()

    def open(self):
        self.open_count += 1
        if self.fail_open:
            raise ValueError("partial startup fixture")
        self.observer._lifecycle["subscriptions"] = [{"topic": topic} for topic in
            ("/clock", "/fmu/out/vehicle_odometry", "/vehicle/odometry_timing", "/vehicle/odometry",
             "/ground_truth/poses", "/ground_truth/vehicle_poses")]

    def context_ok(self):
        return self.context_shutdown_count == 0

    def spin_once(self, timeout_sec):
        self.spin_count += 1
        if self.block_spin:
            self.entered.set()
            self.release.wait(2.)
            return
        try:
            callback = self.queue.get(timeout=timeout_sec)
        except Empty:
            return
        callback()

    def submit(self, callback):
        self.queue.put(callback)

    def flush(self):
        reached = threading.Event()
        self.submit(reached.set)
        if not reached.wait(1.):
            raise AssertionError("Fixture worker did not consume queued callbacks")

    def wake(self):
        self.submit(lambda: None)

    def shutdown_executor(self, timeout_sec):
        return not self.block_spin

    def destroy_node(self):
        self.destroy_count += 1
        if self.fail_destroy:
            raise ValueError("owned destroy fixture")

    def shutdown_context(self):
        self.context_shutdown_count += 1


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def observer(self, **options):
        def factory(observer):
            self.runtime = FakeRuntime(observer)
            return self.runtime
        return closure.RecordingClosureObserver(expected_truth_frames={"target": ["actor"], "vehicle": ["uav"]},
            lifecycle_output=self.directory / "lifecycle.json", _runtime_factory=factory, **options)

    def pair(self, observer, *, truth_time=1.):
        runtime = self.runtime
        runtime.submit(lambda: observer._clock(NS(clock=stamp())))
        runtime.submit(lambda: observer._raw(NS(timestamp_sample=1_000_000, timestamp=1_000_000)))
        runtime.submit(lambda: observer._timing(NS(data=json.dumps(diagnostic()))))
        runtime.submit(lambda: observer._adapted(NS(header=NS(stamp=stamp()))))
        for kind, frame in (("target", "actor"), ("vehicle", "uav")):
            runtime.submit(lambda kind=kind, frame=frame: observer._truth(kind,
                NS(transforms=[NS(child_frame_id=frame, header=NS(stamp=stamp(truth_time)))])))
        runtime.flush()

    def test_start_needs_live_thread_not_data_and_reuses_runtime_until_final_close(self):
        observer = self.observer().start()
        try:
            observer.check_alive()
            self.assertFalse(observer.snapshot(readiness=True)["ready"])
            self.pair(observer)
            self.assertTrue(observer.snapshot(readiness=True)["ready"])
            before_spin = self.runtime.spin_count
            with patch.object(closure.subprocess, "run", return_value=NS(returncode=0, stdout="data: true")):
                report = observer.pause_and_drain(self.directory / "closure.json", world="owned", env={}, timeout_wall_s=1.)
            self.assertEqual(report["status"], "DRAINED_PENDING_OBSERVER_CLEANUP")
            self.assertFalse((self.directory / "closure.json").exists())
            self.assertFalse(report["observer_cleanup_completed"])
            self.assertGreaterEqual(report["closed_streams_elapsed_wall_s"], .5)
            self.assertGreater(self.runtime.spin_count, before_spin)
            self.assertEqual(self.runtime.open_count, 1)
        finally:
            result = observer.close()
        self.assertTrue(result["healthy_cleanup"])
        saved = json.loads((self.directory / "closure.json").read_text())
        self.assertEqual(saved["status"], "PASS")
        self.assertTrue(saved["observer_cleanup_completed"])
        self.assertEqual(self.runtime.context_shutdown_count, 1)
        self.assertIs(observer.close(), result)

    def test_final_clock_truth_and_quiet_gate_are_not_relaxed(self):
        observer = self.observer().start()
        self.pair(observer, truth_time=.99)
        try:
            with patch.object(closure.subprocess, "run", return_value=NS(returncode=0, stdout="true")):
                with self.assertRaisesRegex(RuntimeError, "fully drain"):
                    observer.pause_and_drain(self.directory / "closure.json", world="owned", env={}, timeout_wall_s=.6)
            with self.assertRaisesRegex(RuntimeError, "only once"):
                observer.pause_and_drain(self.directory / "other.json", world="owned", env={})
        finally:
            observer.close()
        saved = json.loads((self.directory / "closure.json").read_text())
        self.assertEqual(saved["status"], "FAIL")
        self.assertIn("missing_truth_at_final_clock", saved["observations"][-1]["failures"])
        self.assertEqual(saved["quiet_wall_s"], .5)

    def test_missing_startup_data_uses_only_closure_budget_and_never_pauses(self):
        observer = self.observer().start()
        try:
            with patch.object(closure.subprocess, "run") as service:
                with self.assertRaisesRegex(RuntimeError, "world was not paused"):
                    observer.pause_and_drain(self.directory / "closure.json", world="owned", env={}, timeout_wall_s=.08)
                service.assert_not_called()
        finally:
            observer.close()
        saved = json.loads((self.directory / "closure.json").read_text())
        self.assertEqual(saved["status"], "FAIL")
        self.assertEqual(saved["timeout_wall_s"], .08)

    def test_worker_exception_latches_and_cannot_be_hidden_by_last_good_pair(self):
        observer = self.observer().start()
        self.pair(observer)
        def crash():
            raise ValueError("worker fixture")
        self.runtime.submit(crash)
        observer._thread.join(timeout=1.)
        try:
            with self.assertRaisesRegex(RuntimeError, "worker failed"):
                observer.pause_and_drain(self.directory / "closure.json", world="owned", env={})
        finally:
            result = observer.close()
        self.assertFalse(result["healthy_cleanup"])
        self.assertIn("worker fixture", result["worker_error"])
        self.assertEqual(json.loads((self.directory / "closure.json").read_text())["status"], "FAIL")

    def test_callbacks_and_assessments_use_same_lock_and_snapshots_are_independent(self):
        observer = self.observer().start()
        try:
            with ExitStack() as stack:
                for name in ("clock", "raw", "timing", "adapted", "truth", "assess", "ready_to_pause"):
                    original = getattr(observer._state, name)
                    def checked(*args, original=original, **kwargs):
                        self.assertTrue(observer._lock._is_owned())
                        return original(*args, **kwargs)
                    stack.enter_context(patch.object(observer._state, name, side_effect=checked))
                self.pair(observer)
                snapshot = observer.snapshot(readiness=True)
                snapshot["counts"]["clock"] = 999
                self.assertEqual(observer.snapshot(readiness=True)["counts"]["clock"], 1)
        finally:
            observer.close()

    def test_partial_start_failure_is_owned_cleaned_and_has_lifecycle_receipt(self):
        def factory(observer):
            self.runtime = FakeRuntime(observer)
            self.runtime.fail_open = True
            return self.runtime
        observer = closure.RecordingClosureObserver(lifecycle_output=self.directory / "lifecycle.json", _runtime_factory=factory)
        with self.assertRaisesRegex(ValueError, "partial startup"):
            observer.start()
        self.assertEqual(self.runtime.context_shutdown_count, 1)
        saved = json.loads((self.directory / "lifecycle.json").read_text())
        self.assertEqual(saved["status"], "FAIL")
        self.assertIn("start_error", saved)
        self.assertFalse(saved["cleanup"]["external_context_shutdown"])

    def test_cleanup_timeout_is_bounded_without_destroying_a_live_worker(self):
        def factory(observer):
            self.runtime = FakeRuntime(observer)
            self.runtime.block_spin = True
            return self.runtime
        observer = closure.RecordingClosureObserver(_runtime_factory=factory, shutdown_timeout_wall_s=.05).start()
        self.assertTrue(self.runtime.entered.wait(1.))
        beginning = time.monotonic()
        result = observer.close()
        self.assertLess(time.monotonic() - beginning, .3)
        self.assertFalse(result["healthy_cleanup"])
        self.assertTrue(result["worker_still_alive"])
        self.assertEqual(self.runtime.destroy_count, 0)
        self.assertEqual(self.runtime.context_shutdown_count, 0)
        self.assertFalse(result["force_kill"])
        self.runtime.release.set()
        observer._thread.join(timeout=1.)

    def test_context_manager_keeps_original_error_when_owned_cleanup_fails(self):
        observer = self.observer().start()
        self.runtime.fail_destroy = True
        original = ValueError("original flight failure")
        self.assertFalse(observer.__exit__(ValueError, original, None))
        self.assertFalse(observer.close()["healthy_cleanup"])
        self.assertEqual(self.runtime.context_shutdown_count, 1)

    def test_callback_holding_state_lock_cannot_block_health_drain_or_cleanup(self):
        observer = self.observer(shutdown_timeout_wall_s=.05).start()
        entered, release = threading.Event(), threading.Event()
        def stalled_callback():
            with observer._lock:
                entered.set()
                release.wait(2.)
        self.runtime.submit(stalled_callback)
        self.assertTrue(entered.wait(1.))
        try:
            beginning = time.monotonic()
            observer.check_alive()
            self.assertLess(time.monotonic() - beginning, .05)
            with patch.object(closure.subprocess, "run") as service:
                with self.assertRaisesRegex(RuntimeError, "snapshot lock"):
                    observer.pause_and_drain(self.directory / "closure.json", world="owned", env={}, timeout_wall_s=.04)
                service.assert_not_called()
            beginning = time.monotonic()
            result = observer.close()
            self.assertLess(time.monotonic() - beginning, .3)
            self.assertFalse(result["healthy_cleanup"])
            self.assertIn("observer_state_snapshot_lock_timeout", result["errors"])
            self.assertEqual(self.runtime.destroy_count, 0)
            saved = json.loads((self.directory / "closure.json").read_text())
            self.assertEqual(saved["status"], "FAIL")
            self.assertFalse(saved["observer_cleanup_completed"])
            self.assertEqual(saved["startup_untimed_audit"]["status"], "UNAVAILABLE")
        finally:
            release.set()
            observer._thread.join(timeout=1.)

    def test_stalled_owned_resource_teardown_is_also_bounded_and_failed(self):
        observer = self.observer(shutdown_timeout_wall_s=.05).start()
        entered, release = threading.Event(), threading.Event()
        def stalled_destroy():
            entered.set()
            release.wait(2.)
        self.runtime.destroy_node = stalled_destroy
        beginning = time.monotonic()
        result = observer.close()
        self.assertLess(time.monotonic() - beginning, .3)
        self.assertTrue(entered.is_set())
        self.assertTrue(result["teardown_still_alive"])
        self.assertFalse(result["healthy_cleanup"])
        release.set()

    def test_legacy_wrapper_returns_finalized_report_and_keeps_existing_output(self):
        original_class = closure.RecordingClosureObserver
        def factory(**kwargs):
            observer = original_class(**kwargs, _runtime_factory=lambda owner: FakeRuntime(owner))
            original_start = observer.start
            def start():
                original_start()
                self.runtime = observer._runtime
                self.pair(observer)
                return observer
            observer.start = start
            return observer
        with patch.object(closure, "RecordingClosureObserver", side_effect=factory), \
                patch.object(closure.subprocess, "run", return_value=NS(returncode=0, stdout="true")):
            report = closure.pause_and_drain(self.directory / "closure.json", world="owned", env={},
                expected_truth_frames={"target": ["actor"], "vehicle": ["uav"]}, timeout_wall_s=1.)
            self.assertEqual(report["status"], "PASS")
            before = (self.directory / "closure.json").read_bytes()
            with self.assertRaises(FileExistsError):
                closure.pause_and_drain(self.directory / "closure.json", world="owned", env={})
            self.assertEqual(before, (self.directory / "closure.json").read_bytes())

    def test_legal_startup_zero_is_audited_but_not_a_readiness_pair(self):
        observer = self.observer().start()
        try:
            for sample in (None, 1.234567):
                self.runtime.submit(lambda sample=sample: observer._timing(NS(data=json.dumps(diagnostic(0., startup=True, sample=sample)))))
            self.runtime.flush()
            state = observer.snapshot(readiness=True)
            self.assertFalse(state["ready"])
            self.assertEqual(state["counts"]["timing"], 2)
            self.assertEqual(state["observed_complete_source_us"], None)
            self.pair(observer)
            self.assertTrue(observer.snapshot(readiness=True)["ready"])
        finally:
            observer.close()
        audit = json.loads((self.directory / "lifecycle.json").read_text())["startup_untimed_audit"]
        self.assertEqual(audit["count"], 2)
        self.assertEqual(audit["diagnostics"][1]["diagnostic"]["source_sample_s"], 1.234567)

    def test_late_zero_and_bad_startup_shape_latch_failures(self):
        defects = ("late", "receipt_bool", "source_bool", "bad_reason", "zero_source", "fractional_source", "wrong_mode")
        for defect in defects:
            with self.subTest(defect=defect):
                observer = closure.RecordingClosureObserver(_runtime_factory=lambda owner: FakeRuntime(owner)).start()
                self.runtime = observer._runtime
                try:
                    if defect == "late":
                        self.runtime.submit(lambda: observer._timing(NS(data=json.dumps(diagnostic()))))
                    payload = diagnostic(0., startup=True)
                    if defect == "receipt_bool": payload["receipt_ros_s"] = False
                    if defect == "source_bool": payload["source_sample_s"] = True
                    if defect == "bad_reason": payload["reason"] = "other_rejection"
                    if defect == "zero_source": payload["source_sample_s"] = 0
                    if defect == "fractional_source": payload["source_sample_s"] = 1.0000004
                    if defect == "wrong_mode": payload["mode"] = "receipt"
                    self.runtime.submit(lambda payload=payload: observer._timing(NS(data=json.dumps(payload))))
                    self.runtime.flush()
                    with observer._lock:
                        self.assertTrue(observer._state.errors)
                    self.assertFalse(observer.snapshot(readiness=True)["ready"])
                    self.assertEqual(observer._startup_untimed, [])
                finally:
                    observer.close()


if __name__ == "__main__":
    unittest.main()
