"""Observe logging streams before flight; reuse them for paused recording close."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import threading
import time

from uav_tracking.recording_closure import StreamDrainState


def utc():
    return datetime.now(timezone.utc).isoformat()


class _RosRuntime:
    """Own a separate context; never stop the runner's or global ROS context."""
    def __init__(self, observer):
        self.observer = observer
        self.rclpy = self.context = self.node = self.executor = None
        self.subscriptions = []

    def open(self):
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from nav_msgs.msg import Odometry
        from px4_msgs.msg import VehicleOdometry
        from rosgraph_msgs.msg import Clock
        from std_msgs.msg import String
        from tf2_msgs.msg import TFMessage
        self.rclpy = rclpy
        self.context = rclpy.context.Context()
        rclpy.init(context=self.context)
        self.node = rclpy.create_node("uav_trial_recording_closure", context=self.context)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        observer = self.observer
        subscriptions = [(Clock, "/clock", observer._clock, 20),
            (VehicleOdometry, "/fmu/out/vehicle_odometry", observer._raw, qos_profile_sensor_data),
            (String, "/vehicle/odometry_timing", observer._timing, 100),
            (Odometry, "/vehicle/odometry", observer._adapted, 100)]
        if observer.expected_truth_frames:
            subscriptions.extend(((TFMessage, "/ground_truth/poses", lambda message: observer._truth("target", message), 100),
                (TFMessage, "/ground_truth/vehicle_poses", lambda message: observer._truth("vehicle", message), 100)))
        for kind, topic, callback, qos in subscriptions:
            self.subscriptions.append(self.node.create_subscription(kind, topic, callback, qos))
            observer._lifecycle["subscriptions"].append({"topic": topic, "created_utc": utc(), "created_monotonic_s": time.monotonic()})

    def context_ok(self):
        return self.context is not None and self.context.ok()

    def spin_once(self, timeout_sec):
        self.executor.spin_once(timeout_sec=timeout_sec)

    def wake(self):
        if self.executor is not None:
            self.executor.wake()

    def shutdown_executor(self, timeout_sec):
        return self.executor.shutdown(timeout_sec=timeout_sec) if self.executor is not None else True

    def destroy_node(self):
        if self.node is not None:
            self.node.destroy_node()

    def shutdown_context(self):
        if self.context is not None and self.context.ok():
            self.rclpy.shutdown(context=self.context)


class RecordingClosureObserver:
    """Continuously spin an owned collector; construct while physics is paused.

    The runner closes only after physics is paused or its processes stopped.
    Logging-only truth is never returned to the online estimator/controller.
    """
    def __init__(self, *, expected_truth_frames=None, lifecycle_output=None,
                 startup_timeout_wall_s=10., shutdown_timeout_wall_s=2., _runtime_factory=None):
        for value in (startup_timeout_wall_s, shutdown_timeout_wall_s):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid observer startup/shutdown wall budget")
        self.expected_truth_frames = deepcopy(expected_truth_frames or {})
        self.lifecycle_output = Path(lifecycle_output) if lifecycle_output is not None else None
        self.startup_timeout_wall_s = startup_timeout_wall_s
        self.shutdown_timeout_wall_s = shutdown_timeout_wall_s
        self._factory = _runtime_factory or _RosRuntime
        self._state = StreamDrainState(quiet_wall_s=.5, expected_truth_frames=expected_truth_frames)
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._changed = threading.Event()
        self._stop = threading.Event()
        self._thread_ready = threading.Event()
        self._runtime = self._thread = None
        self._worker_error = None
        self._timed_diagnostic_seen = False
        self._startup_untimed = []
        self._started = self._start_attempted = False
        self._cleanup = None
        self._closure_output = self._closure_report = None
        self._drain_passed = False
        self._lifecycle = {"schema_version": 1, "scope": "OWNED_PRECONSTRUCTED_RECORDING_CLOSURE_OBSERVER",
            "status": "CONSTRUCTED", "constructed_utc": utc(), "constructed_monotonic_s": time.monotonic(),
            "owned_context": True, "subscriptions": [],
            "truth_scope": "Offline logging headers only; no pose, identity or association is returned to online tracking/control"}

    def start(self):
        if self._start_attempted or self._cleanup is not None:
            raise RuntimeError("Observer start may be attempted only once")
        if self.lifecycle_output is not None and self.lifecycle_output.exists():
            raise FileExistsError(self.lifecycle_output)
        self._start_attempted = True
        beginning = time.monotonic()
        self._lifecycle.update(start_requested_utc=utc(), start_requested_monotonic_s=beginning, status="STARTING")
        try:
            self._runtime = self._factory(self)
            self._runtime.open()
            self._lifecycle.update(resources_created_utc=utc(), resources_created_monotonic_s=time.monotonic())
            remaining = beginning + self.startup_timeout_wall_s - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Observer construction exceeded its startup wall budget")
            self._thread = threading.Thread(target=self._spin, name="recording-closure-observer", daemon=True)
            self._started = True
            self._thread.start()
            if not self._thread_ready.wait(remaining):
                raise RuntimeError("Observer executor thread did not start within wall budget")
            self.check_alive()
            self._lifecycle["status"] = "SPINNING"
            return self
        except BaseException as error:
            self._lifecycle["start_error"] = f"{type(error).__name__}: {error}"
            self.close()
            raise

    def __enter__(self):
        return self.start()

    def _spin(self):
        with self._lifecycle_lock:
            self._lifecycle.update(spinning_utc=utc(), spinning_monotonic_s=time.monotonic())
        self._thread_ready.set()
        try:
            while not self._stop.is_set():
                if not self._runtime.context_ok():
                    raise RuntimeError("Owned observer ROS context stopped before cleanup")
                self._runtime.spin_once(timeout_sec=.05)
        except BaseException as error:
            # A latched string assignment is independent of the callback state
            # lock, so health checks never wait behind a stuck callback.
            self._worker_error = f"{type(error).__name__}: {error}"
            self._changed.set()
        finally:
            with self._lifecycle_lock:
                self._lifecycle.update(worker_finished_utc=utc(), worker_finished_monotonic_s=time.monotonic())

    def check_alive(self):
        error = self._worker_error
        if error is not None:
            raise RuntimeError("Recording closure observer worker failed: " + error)
        if not self._started or self._thread is None or not self._thread.is_alive() or self._stop.is_set():
            raise RuntimeError("Recording closure observer is not continuously spinning")
        if not self._runtime.context_ok():
            raise RuntimeError("Recording closure observer context is no longer live")

    def _update(self, method, *args, _deadline=None):
        acquired = self._lock.acquire() if _deadline is None else self._lock.acquire(timeout=max(0., _deadline - time.monotonic()))
        if not acquired:
            raise RuntimeError("Observer state update lock exceeded recording closure wall budget")
        try:
            getattr(self._state, method)(*args, time.monotonic())
        finally:
            self._lock.release()
        self._changed.set()

    def _clock(self, message):
        self._update("clock", message.clock.sec * 1_000_000_000 + message.clock.nanosec)

    def _raw(self, message):
        self._update("raw", int(message.timestamp_sample), int(message.timestamp))

    def _timing(self, message):
        try:
            diagnostic = json.loads(message.data)
            if not isinstance(diagnostic, dict):
                raise ValueError("diagnostic must be an object")
            with self._lock:
                receipt = diagnostic.get("receipt_ros_s")
                numeric = lambda value: type(value) in (int, float) and math.isfinite(value)
                if numeric(receipt) and receipt > 0:
                    # Any timed message closes the startup-only audit branch,
                    # including a rejected or otherwise malformed timed row.
                    self._timed_diagnostic_seen = True
                startup_shaped = diagnostic.get("reason") == "ros_clock_not_started" or receipt == 0
                if startup_shaped and self._valid_startup_untimed(diagnostic):
                    now = time.monotonic()
                    self._state.counts["timing"] += 1
                    self._state.last_change["timing"] = now
                    self._startup_untimed.append({"observed_monotonic_s": now, "diagnostic": deepcopy(diagnostic)})
                else:
                    if startup_shaped:
                        self._state.errors.append("invalid_or_late_startup_untimed_diagnostic")
                    self._state.timing(diagnostic, time.monotonic())
            self._changed.set()
        except (ValueError, TypeError) as error:
            with self._lock:
                self._state.errors.append(f"diagnostic_decode: {error}")
            self._changed.set()

    def _valid_startup_untimed(self, diagnostic):
        """Audit only the adapter's exact pre-Clock schema; never a raw pair."""
        if (self._timed_diagnostic_seen or type(diagnostic.get("schema_version")) is not int
                or diagnostic["schema_version"] != 1 or diagnostic.get("mode") != "source_sim"
                or diagnostic.get("reason") != "ros_clock_not_started"
                or diagnostic.get("accepted") is not False or diagnostic.get("source_time_valid") is not False
                or "odometry_header_s" not in diagnostic or diagnostic["odometry_header_s"] is not None):
            return False
        for key in ("receipt_ros_s", "output_s"):
            value = diagnostic.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value != 0:
                return False
        for key in ("source_sample_s", "source_publication_s"):
            if key not in diagnostic:
                return False
            value = diagnostic[key]
            if value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                return False
            scaled = value * 1_000_000
            if not math.isfinite(scaled) or not math.isclose(scaled, round(scaled), rel_tol=0.,
                    abs_tol=max(1e-7, 2 * math.ulp(scaled))):
                return False
        return True

    def _adapted(self, message):
        self._update("adapted", message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec)

    def _truth(self, kind, message):
        self._update("truth", kind, [(transform.child_frame_id,
            transform.header.stamp.sec * 1_000_000_000 + transform.header.stamp.nanosec)
            for transform in message.transforms])

    def snapshot(self, *, readiness=False, timeout_wall_s=1.):
        self.check_alive()
        if not self._lock.acquire(timeout=max(0., timeout_wall_s)):
            raise RuntimeError("Observer state snapshot lock exceeded wall budget")
        try:
            assessment = self._state.ready_to_pause(time.monotonic()) if readiness else self._state.assess(time.monotonic())
            return deepcopy(assessment)
        finally:
            self._lock.release()

    def _check(self, external):
        self.check_alive()
        if external is not None:
            external()
        self.check_alive()

    def _wait(self, deadline):
        self._changed.wait(min(.05, max(0., deadline - time.monotonic())))
        self._changed.clear()

    def pause_and_drain(self, output: Path, *, world: str, env: dict, check_alive=None,
                        timeout_wall_s: float = 10.) -> dict:
        """Reuse existing callbacks; finalize the report during owned close()."""
        output = Path(output)
        if output.exists():
            raise FileExistsError(output)
        if self._closure_report is not None:
            raise RuntimeError("Recording closure may be attempted only once")
        if isinstance(timeout_wall_s, bool) or not isinstance(timeout_wall_s, (int, float)) or not math.isfinite(timeout_wall_s) or timeout_wall_s <= 0:
            raise ValueError("Invalid recording closure wall budget")
        beginning = time.monotonic()
        deadline = beginning + timeout_wall_s
        with self._lifecycle_lock:
            preconstruction = deepcopy(self._lifecycle)
        report = {"schema_version": 1, "status": "FAIL",
            "scope": "WORLD_PAUSE_ACK_AND_OBSERVED_FINAL_SOURCE_CORRESPONDENCE_BEFORE_RECORDER_CLOSE",
            "created_utc": utc(), "world": world, "timeout_wall_s": timeout_wall_s,
            "quiet_wall_s": .5, "observations": [], "expected_truth_frames": self.expected_truth_frames,
            "truth_scope": self._lifecycle["truth_scope"], "observer_cleanup_completed": False,
            "observer_preconstruction": preconstruction,
            "policy": "Recorder and producers remain alive during closure; complete recorded Clock tail and all rows remain in independent evaluation"}
        self._closure_output, self._closure_report = output, report
        try:
            self._check(check_alive)
            readiness = self.snapshot(readiness=True, timeout_wall_s=max(0., deadline - time.monotonic()))
            while not readiness["ready"] and time.monotonic() < deadline:
                self._check(check_alive)
                self._wait(deadline)
                readiness = self.snapshot(readiness=True, timeout_wall_s=max(0., deadline - time.monotonic()))
            report["before_pause"] = {"clock_observed": readiness["clock_observed"],
                "raw_observed": readiness["raw_observed"], "counts": readiness["counts"],
                "elapsed_wall_s": time.monotonic() - beginning, "readiness": readiness}
            if not readiness["ready"]:
                raise RuntimeError("Required source callbacks not ready within recording closure wall budget; world was not paused")
            self._check(check_alive)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Recording closure wall budget expired before pause request")
            paused = subprocess.run(["gz", "service", "-s", f"/world/{world}/control",
                "--reqtype", "gz.msgs.WorldControl", "--reptype", "gz.msgs.Boolean", "--timeout",
                str(min(5000, max(1, int(remaining * 1000)))), "--req", "pause: true"],
                env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=min(5.5, remaining))
            report["pause_request"] = {"command_pause": True, "returncode": paused.returncode, "response": paused.stdout}
            if paused.returncode != 0 or "true" not in paused.stdout:
                raise RuntimeError("Gazebo did not acknowledge recording-closure pause")
            self._update("pause_ack", _deadline=deadline)
            report["pause_ack_elapsed_wall_s"] = time.monotonic() - beginning
            while time.monotonic() < deadline:
                self._check(check_alive)
                assessment = self.snapshot(timeout_wall_s=max(0., deadline - time.monotonic()))
                report["observations"].append({"elapsed_wall_s": time.monotonic() - beginning, **assessment})
                if assessment["ready"]:
                    self._check(check_alive)
                    self._drain_passed = True
                    report.update(status="DRAINED_PENDING_OBSERVER_CLEANUP", closed_streams_elapsed_wall_s=time.monotonic() - beginning)
                    return report
                self._wait(deadline)
            raise RuntimeError("Recording source streams did not become quiet and fully drain within wall budget")
        except BaseException as error:
            report["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            report["drain_finished_utc"] = utc()
            report["elapsed_wall_s"] = time.monotonic() - beginning

    def close(self):
        """Bound executor/worker/owned teardown; return failures without killing."""
        if self._cleanup is not None:
            return self._cleanup
        beginning = time.monotonic()
        deadline = beginning + self.shutdown_timeout_wall_s
        cleanup = {"status": "FAIL", "healthy_cleanup": False, "errors": [],
            "shutdown_timeout_wall_s": self.shutdown_timeout_wall_s,
            "external_context_shutdown": False, "force_kill": False}
        self._cleanup = cleanup
        self._stop.set()
        shutdown = True
        if self._runtime is not None:
            try:
                self._runtime.wake()
            except Exception as error:
                cleanup["errors"].append(f"executor_wake:{type(error).__name__}: {error}")
            try:
                shutdown = self._runtime.shutdown_executor(timeout_sec=max(0., deadline - time.monotonic()))
                if shutdown is not True:
                    cleanup["errors"].append("executor_shutdown_did_not_complete")
            except Exception as error:
                shutdown = False
                cleanup["errors"].append(f"executor_shutdown:{type(error).__name__}: {error}")
        if self._thread is not None:
            try:
                self._thread.join(timeout=max(0., deadline - time.monotonic()))
            except RuntimeError as error:
                cleanup["errors"].append(f"worker_join:{error}")
        alive = self._thread is not None and self._thread.is_alive()
        cleanup["worker_still_alive"] = alive
        if alive:
            cleanup["errors"].append("observer_worker_join_timed_out_resources_retained")
        elif self._runtime is not None:
            # RMW destruction has no timeout API. Keep it on an owned bounded
            # teardown thread so even a stalled RMW cannot block runner cleanup.
            teardown_errors = []
            def teardown():
                for name in ("destroy_node", "shutdown_context"):
                    try:
                        getattr(self._runtime, name)()
                    except Exception as error:
                        teardown_errors.append(f"{name}:{type(error).__name__}: {error}")
            thread = threading.Thread(target=teardown, name="recording-closure-teardown", daemon=True)
            thread.start()
            thread.join(timeout=max(0., deadline - time.monotonic()))
            cleanup["teardown_still_alive"] = thread.is_alive()
            if thread.is_alive():
                cleanup["errors"].append("owned_resource_teardown_timed_out")
            else:
                cleanup["errors"].extend(teardown_errors)
        with self._lifecycle_lock:
            lifecycle = deepcopy(self._lifecycle)
        cleanup["worker_error"] = self._worker_error
        lifecycle.update(stopped_utc=utc(), stopped_monotonic_s=time.monotonic(), worker_error=self._worker_error)
        acquired = self._lock.acquire(timeout=max(0., deadline - time.monotonic()))
        if acquired:
            try:
                lifecycle.update(final_observed_counts=dict(self._state.counts),
                    startup_untimed_audit={"count": len(self._startup_untimed), "diagnostics": deepcopy(self._startup_untimed),
                        "timed_diagnostic_seen": self._timed_diagnostic_seen,
                        "scope": "Original startup diagnostics retained; audit-only, never pause-readiness pairs or positive-clock evidence"})
            finally:
                self._lock.release()
        else:
            cleanup["errors"].append("observer_state_snapshot_lock_timeout")
            lifecycle.update(final_observed_counts=None,
                startup_untimed_audit={"status": "UNAVAILABLE", "reason": "observer_state_snapshot_lock_timeout"})
        if self._worker_error is not None:
            cleanup["errors"].append("observer_worker_failed")
        if lifecycle.get("start_error"):
            cleanup["errors"].append("observer_start_failed")
        cleanup["elapsed_wall_s"] = time.monotonic() - beginning
        cleanup["healthy_cleanup"] = not cleanup["errors"] and not alive and shutdown is True
        cleanup["status"] = "PASS" if cleanup["healthy_cleanup"] else "FAIL"
        lifecycle.update(status="CLOSED" if cleanup["healthy_cleanup"] else "FAIL", cleanup=cleanup)
        # Write lifecycle first: a lifecycle write failure cannot leave a PASS
        # closure report that silently claims complete observer evidence.
        if self.lifecycle_output is not None:
            try:
                self._write_new(self.lifecycle_output, lifecycle)
            except Exception as error:
                cleanup["errors"].append(f"lifecycle_report_write:{type(error).__name__}: {error}")
                cleanup.update(status="FAIL", healthy_cleanup=False)
        if self._closure_report is not None:
            report = self._closure_report
            report.update(finished_utc=utc(), observer_cleanup_completed=cleanup["healthy_cleanup"], observer_cleanup=cleanup)
            report["startup_untimed_audit"] = deepcopy(lifecycle["startup_untimed_audit"])
            report["status"] = "PASS" if self._drain_passed and cleanup["healthy_cleanup"] else "FAIL"
            if not cleanup["healthy_cleanup"]:
                report.setdefault("error", "Recording closure observer cleanup failed")
            try:
                self._write_new(self._closure_output, report)
            except Exception as error:
                cleanup["errors"].append(f"closure_report_write:{type(error).__name__}: {error}")
                cleanup.update(status="FAIL", healthy_cleanup=False)
                report.update(status="FAIL", observer_cleanup_completed=False)
        return cleanup

    @staticmethod
    def _write_new(path, value):
        with Path(path).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")

    def __exit__(self, kind, value, traceback):
        cleanup = self.close()
        if kind is None and not cleanup["healthy_cleanup"]:
            raise RuntimeError("Recording closure observer cleanup failed: " + "; ".join(cleanup["errors"]))
        return False


def pause_and_drain(output: Path, *, world: str, env: dict, expected_truth_frames=None, check_alive=None,
                    timeout_wall_s: float = 10.) -> dict:
    """Historical one-shot API; new runners preconstruct the observer instead."""
    if Path(output).exists():
        raise FileExistsError(output)
    with RecordingClosureObserver(expected_truth_frames=expected_truth_frames) as observer:
        report = observer.pause_and_drain(output, world=world, env=env,
            check_alive=check_alive, timeout_wall_s=timeout_wall_s)
    return report
