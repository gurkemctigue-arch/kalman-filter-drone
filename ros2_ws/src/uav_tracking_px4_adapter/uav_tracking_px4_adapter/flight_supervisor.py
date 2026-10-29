"""Simulation-only takeoff/handoff and single-source command supervision.

The portable controller stays independent of PX4.  This node is the sole
publisher of ``/tracking/flight_command``: it holds while the adapter streams
Offboard heartbeats, requests Offboard/arm through VehicleCommand, climbs in
ENU with bounded velocity, and finally forwards fresh controller commands.
It never creates target observations or reads simulator ground truth.
"""

from __future__ import annotations

import copy
import json
import math
from numbers import Integral, Real
import time
from typing import Any

from uav_tracking_px4_adapter.source_clock import OdometrySourceClock
from uav_tracking_px4_adapter.supervisor_audit import SupervisorTimingAudit

from uav_tracking.ros_lifecycle import shutdown_requests

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions
    from nav_msgs.msg import Odometry
    from px4_msgs.msg import EstimatorStatusFlags, OffboardControlMode, VehicleCommand, VehicleLocalPosition, VehicleStatus
    from rclpy.clock import Clock, ClockType
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from std_msgs.msg import String
    from uav_tracking_interfaces.msg import TrackingCommand
    from uav_tracking_px4_adapter.startup_readiness import readiness_issues
except ImportError:  # Pure helpers remain testable without ROS.
    rclpy = None
    Node = object  # type: ignore[assignment,misc]


def bounded_takeoff_velocity(
    position: tuple[float, float, float],
    goal: tuple[float, float, float],
    horizontal_limit: float = 0.8,
    vertical_limit: float = 0.7,
    gain: float = 0.8,
) -> tuple[float, float, float]:
    """Position feedback in ENU, with a norm limit on horizontal speed."""

    if not all(math.isfinite(v) for v in (*position, *goal, horizontal_limit, vertical_limit, gain)):
        raise ValueError("takeoff feedback must be finite")
    if min(horizontal_limit, vertical_limit, gain) <= 0.0:
        raise ValueError("takeoff limits and gain must be positive")
    vx, vy = (gain * (goal[i] - position[i]) for i in range(2))
    speed = math.hypot(vx, vy)
    if speed > horizontal_limit:
        vx, vy = vx * horizontal_limit / speed, vy * horizontal_limit / speed
    vz = max(-vertical_limit, min(vertical_limit, gain * (goal[2] - position[2])))
    return vx, vy, vz


def quaternion_yaw(quaternion: Any) -> float:
    values = [float(quaternion.x), float(quaternion.y), float(quaternion.z), float(quaternion.w)]
    norm = math.sqrt(sum(v * v for v in values))
    if norm < 1e-9 or not all(math.isfinite(v) for v in values):
        raise ValueError("odometry quaternion is invalid")
    x, y, z, w = (v / norm for v in values)
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


class FlightSupervisor(Node):
    def __init__(self) -> None:
        super().__init__("uav_tracking_flight_supervisor")
        defaults = {
            "auto_start": False,
            "simulation_only": True,
            "command_topic": "/tracking/command",
            "flight_command_topic": "/tracking/flight_command",
            "vehicle_odom_topic": "/vehicle/odometry",
            "vehicle_status_topic": "/fmu/out/vehicle_status_v1",
            "heartbeat_topic": "/fmu/in/offboard_control_mode",
            "vehicle_command_topic": "/fmu/in/vehicle_command",
            "phase_topic": "/tracking/flight_phase",
            "supervisor_diagnostics_topic": "/tracking/supervisor_diagnostics",
            "takeoff_height_m": 3.0,
            "takeoff_mode": "offboard_velocity",
            "local_position_topic": "/fmu/out/vehicle_local_position_v1",
            "estimator_flags_topic": "/fmu/out/estimator_status_flags",
            "native_settle_s": 1.0,
            "native_settle_speed_mps": 0.20,
            "native_takeoff_timeout_sim_s": 40.0,
            "native_wall_timeout_s": 180.0,
            "takeoff_yaw_rad": 0.0,
            "takeoff_horizontal_limit_mps": 0.8,
            "takeoff_vertical_limit_mps": 0.7,
            "takeoff_gain": 0.8,
            "takeoff_position_tolerance_m": 0.18,
            "takeoff_yaw_tolerance_rad": 0.18,
            "takeoff_settle_s": 1.0,
            "takeoff_timeout_s": 40.0,
            "heartbeat_prestream_s": 1.2,
            "command_timeout_s": 0.5,
            "odometry_timeout_s": 0.5,
            "status_timeout_s": 1.0,
            "status_timestamp_mode": "receipt_wall",
            "status_source_max_age_s": 1.0,
            "status_source_max_future_s": 0.05,
            "requested_simulation_real_time_factor": 1.0,
            "command_retry_s": 1.0,
            "max_command_attempts": 15,
            "publish_rate_hz": 20.0,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        self._auto_start = bool(self.get_parameter("auto_start").value)
        startup_mode = self._p("takeoff_mode")
        if startup_mode not in ("offboard_velocity", "px4_native"):
            raise ValueError("unsupported takeoff_mode")
        self._native_takeoff = startup_mode == "px4_native"
        for budget in ("native_takeoff_timeout_sim_s", "native_wall_timeout_s"):
            if not math.isfinite(self._number(budget)) or self._number(budget) <= 0:
                raise ValueError("native startup budgets must be positive finite durations")
        requested_rtf = self._number("requested_simulation_real_time_factor")
        status_timeout = self._number("status_timeout_s")
        if not (math.isfinite(requested_rtf) and 0 < requested_rtf <= 1
                and math.isfinite(status_timeout) and status_timeout > 0):
            raise ValueError("status wall watchdog and requested simulation RTF must be valid")
        self._status_timestamp_mode = self._p("status_timestamp_mode")
        if self._status_timestamp_mode not in ("receipt_wall", "source_sim"):
            raise ValueError("unsupported status_timestamp_mode")
        self._status_clock = OdometrySourceClock(
            "source_sim" if self._status_timestamp_mode == "source_sim" else "receipt",
            use_sim_time=bool(self.get_parameter("use_sim_time").value),
            max_age_s=self._number("status_source_max_age_s"),
            max_future_s=self._number("status_source_max_future_s"),
        )
        self._status_last_ros_ns: int | None = None
        self._status_ros_regressed = False
        self._status_last_rejection = "none"
        if requested_rtf != 1.0 and not (
            bool(self.get_parameter("simulation_only").value)
            and bool(self.get_parameter("use_sim_time").value)
        ):
            raise RuntimeError("slowed simulation status watchdog requires simulation_only and use_sim_time")
        if self._auto_start and (
            not bool(self.get_parameter("simulation_only").value)
            or not bool(self.get_parameter("use_sim_time").value)
        ):
            raise RuntimeError("auto_start requires simulation_only=true and use_sim_time=true")
        self._odom: Any = None
        self._status: Any = None
        self._controller_command: Any = None
        self._odom_received = self._status_received = self._command_received = 0.0
        self._heartbeat_received = self._heartbeat_started = 0.0
        self._phase = "WAITING" if self._auto_start else "DISABLED"
        self._reason = "waiting for fresh PX4 state and preflight"
        self._goal: tuple[float, float, float] | None = None
        self._request_started = self._takeoff_started = self._settle_started = 0.0
        self._last_request = 0.0
        self._attempts = 0
        self._ever_armed = False
        self._native_local = self._estimator_flags = None
        self._odom_received_source_s: float | None = None
        self._native_local_received_source_s: float | None = None
        self._native_local_received_wall_s: float | None = None
        self._native_goal_anchor: dict[str, Any] | None = None
        self._native_settle_diagnostic: dict[str, Any] | None = None
        self._native_settle_started_s: float | None = None
        self._native_started_source_s = self._native_started_wall_s = None
        self._native_finished_source_s = self._native_finished_wall_s = None
        self._native_last_source_s = None
        self._timing_audit = SupervisorTimingAudit()
        self._yaw = float(self.get_parameter("takeoff_yaw_rad").value)
        self._flight_pub = self.create_publisher(TrackingCommand, self._p("flight_command_topic"), 20)
        self._vehicle_command_pub = self.create_publisher(VehicleCommand, self._p("vehicle_command_topic"), 10)
        self._phase_pub = self.create_publisher(String, self._p("phase_topic"), 10)
        self._diagnostics_pub = self.create_publisher(String, self._p("supervisor_diagnostics_topic"), 10)
        self.create_subscription(Odometry, self._p("vehicle_odom_topic"), self._on_odom, qos_profile_sensor_data)
        self.create_subscription(VehicleStatus, self._p("vehicle_status_topic"), self._on_status, qos_profile_sensor_data)
        self.create_subscription(OffboardControlMode, self._p("heartbeat_topic"), self._on_heartbeat, qos_profile_sensor_data)
        self.create_subscription(TrackingCommand, self._p("command_topic"), self._on_command, 20)
        if self._native_takeoff:
            self.create_subscription(VehicleLocalPosition, self._p("local_position_topic"), self._on_native_local,
                                     qos_profile_sensor_data)
            self.create_subscription(EstimatorStatusFlags, self._p("estimator_flags_topic"), self._on_estimator_flags,
                                     qos_profile_sensor_data)
        self.create_timer(1.0 / float(self.get_parameter("publish_rate_hz").value), self._tick)
        self._create_diagnostics_timer()
        if self._native_takeoff:
            # A ROS-time timer stops when /clock pauses. This independent
            # steady timer must still enforce the native wall-time ceiling.
            self._native_watchdog_clock = Clock(clock_type=ClockType.STEADY_TIME)
            self._native_watchdog_timer = self.create_timer(.10, self._native_wall_watchdog,
                                                           clock=self._native_watchdog_clock)
        self.get_logger().info(f"Flight supervisor: {self._phase}; auto_start={self._auto_start}")
        self.get_logger().info(
            f"PX4 status timing: mode={self._status_timestamp_mode}, "
            f"requested_simulation_rtf={requested_rtf:.3f}, status_timeout_wall_s={status_timeout:.3f}, "
            f"source_max_age_s={self._status_clock.max_age_ns / 1e9:.3f}, "
            f"source_max_future_s={self._status_clock.max_future_ns / 1e9:.3f}; "
            "status wall liveness is checked by ROS-time control ticks"
        )

    def _p(self, name: str) -> str:
        return str(self.get_parameter(name).value)

    def _number(self, name: str) -> float:
        return float(self.get_parameter(name).value)

    def _on_odom(self, message: Any) -> None:
        p = message.pose.pose.position
        if not all(math.isfinite(float(v)) for v in (p.x, p.y, p.z)):
            return
        try:
            quaternion_yaw(message.pose.pose.orientation)
        except ValueError:
            return
        self._odom, self._odom_received = message, time.monotonic()
        self._odom_received_source_s = self.get_clock().now().nanoseconds * 1e-9

    def _on_status(self, message: Any) -> None:
        audit = self._audit()
        callback_wall_s = time.monotonic()
        callback_ros_ns = self.get_clock().now().nanoseconds
        acceptance_ros_ns = callback_ros_ns
        source_ns = OdometrySourceClock._source_ns(getattr(message, "timestamp", None))
        audit.receive(callback_wall_s, callback_ros_ns, source_ns)
        if getattr(self, "_status_timestamp_mode", "receipt_wall") == "source_sim":
            now_ns = self._status_ros_now_ns()
            acceptance_ros_ns = now_ns
            stamp = getattr(message, "timestamp", None)
            result = self._status_clock.resolve(stamp, stamp, now_ns)
            if self._status_ros_regressed or not result.accepted:
                self._status_last_rejection = (
                    "ros_clock_regression_restart_required" if self._status_ros_regressed else result.reason
                )
                audit.reject(callback_wall_s, now_ns, source_ns, self._status_last_rejection)
                return
            self._status_last_rejection = "none"
        self._status, self._status_received = message, time.monotonic()
        audit.accept(self._status_received, acceptance_ros_ns, source_ns)

    def _audit(self) -> SupervisorTimingAudit:
        # Existing pure __new__ fixtures do not run the ROS constructor.
        audit = getattr(self, "_timing_audit", None)
        if audit is None:
            audit = self._timing_audit = SupervisorTimingAudit()
        return audit

    def _create_diagnostics_timer(self) -> None:
        # Independent of ROS /clock, but still serviced by this node's executor.
        # A blocked executor delays diagnostics too; external receipt monitoring
        # is necessary to distinguish callback starvation from transport stalls.
        self._diagnostics_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self._diagnostics_timer = self.create_timer(1.0, self._publish_supervisor_diagnostics,
                                                   clock=self._diagnostics_clock)

    def _publish_supervisor_diagnostics(self) -> None:
        now = time.monotonic()
        ros_ns = self.get_clock().now().nanoseconds
        payload = self._audit().snapshot(wall_s=now, ros_ns=ros_ns, unix_ns=time.time_ns())
        odometry = getattr(self, "_odom", None)
        odom_ns = self._native_odom_stamp_ns(odometry)
        status = getattr(self, "_status", None)
        status_ns = OdometrySourceClock._source_ns(getattr(status, "timestamp", None))
        status_clock = getattr(self, "_status_clock", None)
        source_age_ns = getattr(status_clock, "max_age_ns", None)
        source_future_ns = getattr(status_clock, "max_future_ns", None)
        payload.update(
            phase=getattr(self, "_phase", None), phase_reason=getattr(self, "_reason", None),
            status_timestamp_mode=getattr(self, "_status_timestamp_mode", "receipt_wall"),
            control_last_status_rejection=getattr(self, "_status_last_rejection", None),
            accepted_control_status={"source_stamp_ns": status_ns,
                                     "received_wall_monotonic_s": getattr(self, "_status_received", None) if status is not None else None,
                                     "age_wall_s": now - self._status_received if status is not None else None,
                                     "age_source_s": (ros_ns - status_ns) / 1e9 if status_ns is not None else None},
            odometry={"source_stamp_ns": odom_ns,
                      "received_wall_monotonic_s": getattr(self, "_odom_received", None) if odometry is not None else None,
                      "age_wall_s": now - self._odom_received if odometry is not None else None,
                      "age_source_s": (ros_ns - odom_ns) / 1e9 if odom_ns is not None else None},
            guard_limits={"status_wall_s": self._number("status_timeout_s"),
                          "status_source_age_s": source_age_ns / 1e9 if source_age_ns is not None else None,
                          "status_source_future_s": source_future_ns / 1e9 if source_future_ns is not None else None,
                          "odometry_wall_s": self._number("odometry_timeout_s")},
        )
        message = String()
        message.data = json.dumps(payload, allow_nan=False, separators=(",", ":"))
        self._diagnostics_pub.publish(message)

    def _status_ros_now_ns(self) -> int:
        """Observe ROS time on callbacks and ticks; a regression requires restart."""
        now_ns = self.get_clock().now().nanoseconds
        previous = self._status_last_ros_ns
        if previous is not None and now_ns < previous:
            self._status_ros_regressed = True
        self._status_last_ros_ns = now_ns
        return now_ns

    def _status_timing_issues(self, now: float) -> list[str]:
        if getattr(self, "_status_timestamp_mode", "receipt_wall") == "receipt_wall":
            return ["status_stale"] if now - self._status_received > self._number("status_timeout_s") else []
        now_ns = self._status_ros_now_ns()
        issues = []
        if self._status_ros_regressed or self._status_clock.latched:
            issues.append("status_source_clock_regression_restart_required")
        stamp_ns = OdometrySourceClock._source_ns(getattr(self._status, "timestamp", None))
        if now_ns <= 0 or stamp_ns is None:
            issues.append("status_source_timestamp_invalid")
        else:
            age_ns = now_ns - stamp_ns
            if age_ns > self._status_clock.max_age_ns:
                issues.append("status_source_stale")
            if age_ns < -self._status_clock.max_future_ns:
                issues.append("status_source_future")
        if now - self._status_received > self._number("status_timeout_s"):
            issues.append("status_receipt_wall_stale")
        return issues

    def _on_command(self, message: Any) -> None:
        self._controller_command, self._command_received = message, time.monotonic()

    def _on_native_local(self, message: Any) -> None:
        self._native_local = message
        self._native_local_received_source_s = self.get_clock().now().nanoseconds * 1e-9
        self._native_local_received_wall_s = time.monotonic()

    def _on_estimator_flags(self, message: Any) -> None:
        self._estimator_flags = message

    def _native_readiness_issues(self, *, inflight: bool = False,
                                 source_s: float | None = None) -> list[str]:
        return readiness_issues(self._native_local, self._estimator_flags,
                                self.get_clock().now().nanoseconds * 1e-9 if source_s is None else source_s,
                                require_inflight_alignment=inflight)

    @staticmethod
    def _native_finite(value: Any) -> float | None:
        if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value)):
            return float(value)
        return None

    @staticmethod
    def _native_source_us(value: Any) -> int | None:
        return int(value) if isinstance(value, Integral) and not isinstance(value, bool) and 0 < value < 2**64 else None

    @staticmethod
    def _native_odom_stamp_ns(odometry: Any) -> int | None:
        stamp = getattr(getattr(odometry, "header", None), "stamp", None)
        sec, nsec = getattr(stamp, "sec", None), getattr(stamp, "nanosec", None)
        if any(not isinstance(value, Integral) or isinstance(value, bool) for value in (sec, nsec)):
            return None
        if sec < 0 or not 0 <= nsec < 1_000_000_000:
            return None
        value = int(sec) * 1_000_000_000 + int(nsec)
        return value if value > 0 else None

    def _native_settle_issues(self, *, source_s: float, wall_s: float,
                              require_physical_settle: bool = True) -> list[str]:
        """Check both actual callback caches against one ENU goal; no GT.

        A callback-cache observation does not establish rosbag delivery order.
        All unknown diagnostic values stay null; nothing is inferred from an
        old report. Readiness thresholds and the one-second budget are unchanged.
        The completed native goal's distance/speed limits apply to the settle
        interval and each mode request, not to pending or confirmed Offboard.
        All source, EKF and finite-state checks remain active during handoff.
        """
        issues = list(self._native_readiness_issues(inflight=True, source_s=source_s))
        local, odom = self._native_local, self._odom
        raw_goal = self._goal
        goal = [self._native_finite(value) for value in raw_goal] if raw_goal is not None else None
        if goal is None or len(goal) != 3 or any(value is None for value in goal):
            issues.append("native_goal_invalid")
            goal = None

        def physical(position, velocity, prefix):
            position = [self._native_finite(value) for value in position]
            velocity = [self._native_finite(value) for value in velocity]
            error = speed = None
            if any(value is None for value in (*position, *velocity)):
                issues.append(prefix + "_physical_state_invalid")
            else:
                if goal is not None:
                    error = math.dist(position, goal)
                    if not math.isfinite(error):
                        error = None
                        issues.append(prefix + "_position_error_invalid")
                    elif require_physical_settle and error > self._number("takeoff_position_tolerance_m"):
                        issues.append(prefix + "_position_not_settled")
                speed = math.hypot(*velocity)
                if not math.isfinite(speed):
                    speed = None
                    issues.append(prefix + "_speed_invalid")
                elif require_physical_settle and speed > self._number("native_settle_speed_mps"):
                    issues.append(prefix + "_speed_not_settled")
            return {"position_enu_m": position, "position_error_m": error, "speed_mps": speed}

        lp = [getattr(local, field, None) for field in ("y", "x", "z")]
        lp[2] = -lp[2] if self._native_finite(lp[2]) is not None else None
        local_check = physical(lp, [getattr(local, field, None) for field in ("vx", "vy", "vz")], "native_local")
        pose = getattr(getattr(odom, "pose", None), "pose", None)
        position = getattr(pose, "position", None)
        velocity = getattr(getattr(getattr(odom, "twist", None), "twist", None), "linear", None)
        odom_check = physical([getattr(position, field, None) for field in ("x", "y", "z")],
                              [getattr(velocity, field, None) for field in ("x", "y", "z")], "native_adapted")
        odom_stamp_ns = self._native_odom_stamp_ns(odom)
        if odom_stamp_ns is None:
            issues.append("native_adapted_source_stamp_invalid")
        else:
            age_s = source_s - odom_stamp_ns * 1e-9
            # Same source freshness bounds as the unchanged independent audit.
            if age_s > .50 + 1e-9:
                issues.append("native_adapted_source_stale")
            elif age_s < -.05 - 1e-9:
                issues.append("native_adapted_source_future")
        local_check.update(timestamp_sample_us=self._native_source_us(getattr(local, "timestamp_sample", None)),
                           timestamp_us=self._native_source_us(getattr(local, "timestamp", None)),
                           callback_ros_s=getattr(self, "_native_local_received_source_s", None),
                           callback_wall_s=getattr(self, "_native_local_received_wall_s", None))
        odom_check.update(header_stamp_ns=odom_stamp_ns,
                          callback_ros_s=getattr(self, "_odom_received_source_s", None),
                          callback_wall_s=getattr(self, "_odom_received", None))
        self._native_settle_diagnostic = {
            "scope": "ONLINE_CALLBACK_CACHE_ONLY_NOT_RECORDER_CAUSAL_REPLAY",
            "check_ros_s": source_s, "check_wall_s": wall_s,
            "goal_enu_m": goal, "ground_anchor": getattr(self, "_native_goal_anchor", None),
            "local": local_check, "adapted": odom_check,
            "physical_settle_required": require_physical_settle,
            "issues": issues, "checks_ready": not issues,
        }
        return issues

    def _native_budget_failure(self, source_s: float, wall_s: float, *, check_source: bool = True) -> str | None:
        source_start = self._native_started_source_s
        wall_start = self._native_started_wall_s
        if source_start is None or wall_start is None:
            return "native_startup_budget_origin_missing"
        if check_source:
            if not math.isfinite(source_s) or source_s <= 0:
                return "native_source_clock_invalid"
            previous = self._native_last_source_s
            if source_s < source_start or previous is not None and source_s < previous:
                return "native_source_clock_regressed"
            self._native_last_source_s = source_s
            if source_s-source_start > self._number("native_takeoff_timeout_sim_s"):
                return "native_source_budget_exhausted"
        if wall_s-wall_start > self._number("native_wall_timeout_s"):
            return "native_wall_budget_exhausted"
        return None

    def _publish_phase(self, *, wall_s: float | None = None) -> None:
        source_s = self.get_clock().now().nanoseconds * 1e-9
        wall_s = time.monotonic() if wall_s is None else wall_s
        evidence = f"phase_wall_monotonic_s={wall_s:.9f}; "
        if getattr(self, "_native_takeoff", False) and self._native_started_source_s is not None:
            end_source = self._native_finished_source_s if self._native_finished_source_s is not None else source_s
            end_wall = self._native_finished_wall_s if self._native_finished_wall_s is not None else wall_s
            evidence += (f"native_started_source_s={self._native_started_source_s:.9f}; "
                         f"native_started_wall_s={self._native_started_wall_s:.9f}; "
                         f"native_elapsed_source_s={end_source-self._native_started_source_s:.9f}; "
                         f"native_elapsed_wall_s={end_wall-self._native_started_wall_s:.9f}; ")
        diagnostic = ""
        if (getattr(self, "_native_takeoff", False)
                and self._phase in ("REQUEST_NATIVE_TAKEOFF", "NATIVE_TAKEOFF", "REQUEST_OFFBOARD", "ABORTED")):
            value = getattr(self, "_native_settle_diagnostic", None)
            if value is None:
                value = {"scope": "ACTUAL_ONLINE_ANCHOR_NO_SETTLE_CHECK_YET",
                         "goal_enu_m": [self._native_finite(v) for v in self._goal] if self._goal is not None else None,
                         "ground_anchor": getattr(self, "_native_goal_anchor", None)}
            diagnostic = "native_diag=" + json.dumps(value, separators=(",", ":"), allow_nan=False) + "; "
        state = String()
        state.data = f"{self._phase}: {self._reason}; {evidence}{diagnostic}source_sim_s={source_s:.9f}"
        self._phase_pub.publish(state)

    def _native_wall_watchdog(self) -> None:
        if not self._native_takeoff or self._phase != "NATIVE_TAKEOFF":
            return
        now = time.monotonic()
        source_s = self.get_clock().now().nanoseconds * 1e-9
        reason = self._native_budget_failure(source_s, now, check_source=False)
        if reason is not None:
            self._native_finished_source_s, self._native_finished_wall_s = source_s, now
            self._abort(reason, now)
            outgoing = self._velocity_command()
            outgoing.valid = False
            self._flight_pub.publish(outgoing)
            self._publish_phase(wall_s=now)

    def _on_heartbeat(self, _message: Any) -> None:
        now = time.monotonic()
        if not self._heartbeat_started or now - self._heartbeat_received > 0.4:
            self._heartbeat_started = now
        self._heartbeat_received = now

    def _change_phase(self, phase: str, reason: str) -> None:
        if phase != self._phase or reason != self._reason:
            self.get_logger().info(f"Flight supervisor: {phase}: {reason}")
        self._phase, self._reason = phase, reason

    def _fresh_state(self, now: float) -> bool:
        return bool(
            self._odom is not None
            and self._status is not None
            and now - self._odom_received <= self._number("odometry_timeout_s")
            and not self._status_timing_issues(now)
        )

    def _armed_offboard(self) -> bool:
        return bool(
            self._status is not None
            and self._status.arming_state == VehicleStatus.ARMING_STATE_ARMED
            and self._status.nav_state == VehicleStatus.NAVIGATION_STATE_OFFBOARD
            and not self._status.failsafe
        )

    def _state_guard_issues(self, now: float, require_armed_offboard: bool) -> list[str]:
        """Explain the existing guards without changing their thresholds."""

        issues = []
        if self._odom is None:
            issues.append("odometry_missing")
        elif now - self._odom_received > self._number("odometry_timeout_s"):
            issues.append("odometry_stale")
        if self._status is None:
            issues.append("status_missing")
        else:
            issues.extend(self._status_timing_issues(now))
            if self._status.failsafe:
                issues.append("failsafe")
            if require_armed_offboard:
                if self._status.arming_state != VehicleStatus.ARMING_STATE_ARMED:
                    issues.append("disarmed")
                if self._status.nav_state != VehicleStatus.NAVIGATION_STATE_OFFBOARD:
                    issues.append("offboard_exited")
        return issues

    def _state_snapshot(self, now: float) -> str:
        """Latch ages, source stamps and receive times at the aborting tick."""

        odom_stamp = getattr(getattr(self._odom, "header", None), "stamp", None)
        odom_stamp_ns = (
            int(odom_stamp.sec) * 1_000_000_000 + int(odom_stamp.nanosec)
            if odom_stamp is not None else "missing"
        )
        status = self._status
        source_timing = ""
        mode = getattr(self, "_status_timestamp_mode", "receipt_wall")
        if mode == "source_sim":
            stamp_ns = OdometrySourceClock._source_ns(getattr(status, "timestamp", None))
            age = (self.get_clock().now().nanoseconds - stamp_ns) / 1e9 if stamp_ns is not None else math.nan
            source_timing = (
                f"status_age_source_s={age:.3f}, "
                f"status_source_limit_s={self._status_clock.max_age_ns / 1e9:.3f}, "
                f"status_source_future_limit_s={self._status_clock.max_future_ns / 1e9:.3f}, "
                f"status_last_rejection={self._status_last_rejection}, "
            )
        return (
            f"wall_monotonic_s={now:.6f}, ros_now_ns={self.get_clock().now().nanoseconds}, "
            f"odom_age_wall_s={now - self._odom_received:.3f}, "
            f"odom_limit_s={self._number('odometry_timeout_s'):.3f}, "
            f"odom_received_monotonic_s={self._odom_received:.6f}, odom_stamp_ns={odom_stamp_ns}, "
            f"status_age_wall_s={now - self._status_received:.3f}, "
            f"status_limit_s={self._number('status_timeout_s'):.3f}, "
            f"status_timestamp_mode={mode}, {source_timing}"
            f"status_received_monotonic_s={self._status_received:.6f}, "
            f"status_px4_stamp_us={getattr(status, 'timestamp', 'missing')}, "
            f"arming_state={getattr(status, 'arming_state', 'missing')}, "
            f"nav_state={getattr(status, 'nav_state', 'missing')}, "
            f"failsafe={getattr(status, 'failsafe', 'missing')}, "
            f"preflight_pass={getattr(status, 'pre_flight_checks_pass', 'missing')}"
        )

    def _abort(self, reason: str, now: float) -> None:
        # Kept in the phase message and normal transition log, so the source
        # of a latched abort remains inspectable after the state recovers.
        if (getattr(self, "_native_takeoff", False) and self._phase == "NATIVE_TAKEOFF"
                and self._native_finished_source_s is None):
            self._native_finished_source_s = self.get_clock().now().nanoseconds * 1e-9
            self._native_finished_wall_s = now
        self._change_phase("ABORTED", f"{reason}; {self._state_snapshot(now)}")

    def _position(self) -> tuple[float, float, float]:
        p = self._odom.pose.pose.position
        return float(p.x), float(p.y), float(p.z)

    def _velocity_command(self, velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> Any:
        command = TrackingCommand()
        command.header.stamp = self.get_clock().now().to_msg()
        command.header.frame_id = "map"
        command.mode = TrackingCommand.MODE_VELOCITY
        command.valid = True
        command.linear_mps.x, command.linear_mps.y, command.linear_mps.z = velocity
        command.yaw_rad = self._yaw
        return command

    def _request(self, command_id: int, param1: float, param2: float = 0.0) -> None:
        request = VehicleCommand()
        request.timestamp = self.get_clock().now().nanoseconds // 1000
        request.command = command_id
        request.param1, request.param2 = float(param1), float(param2)
        if command_id == getattr(VehicleCommand, "VEHICLE_CMD_NAV_TAKEOFF", 22):
            # Normal PX4 Navigator chooses current onboard latitude/longitude
            # and current AMSL + MIS_TAKEOFF_ALT. Zero is a real coordinate.
            request.param4 = request.param5 = request.param6 = request.param7 = math.nan
        request.target_system = request.source_system = 1
        request.target_component = request.source_component = 1
        request.from_external = True
        self._vehicle_command_pub.publish(request)

    def _controller_is_fresh(self, now: float) -> bool:
        command = self._controller_command
        if command is None or not command.valid or now - self._command_received > self._number("command_timeout_s"):
            return False
        stamp_ns = command.header.stamp.sec * 1_000_000_000 + command.header.stamp.nanosec
        age_s = (self.get_clock().now().nanoseconds - stamp_ns) * 1e-9
        if stamp_ns <= 0 or age_s < -0.05 or age_s > self._number("command_timeout_s"):
            return False
        if command.mode == TrackingCommand.MODE_VELOCITY:
            values = (command.linear_mps.x, command.linear_mps.y, command.linear_mps.z, command.yaw_rad, command.yaw_rate_radps)
        elif command.mode == TrackingCommand.MODE_POSITION:
            values = (command.position_m.x, command.position_m.y, command.position_m.z, command.yaw_rad, command.yaw_rate_radps)
        else:
            return False
        return all(math.isfinite(float(v)) for v in values)

    def _tick(self) -> None:
        now = time.monotonic()
        self._audit().tick(now)
        outgoing = self._velocity_command()
        fresh = self._fresh_state(now)
        if self._phase == "DISABLED":
            outgoing.valid = False
        elif self._phase == "WAITING":
            if fresh and bool(self._status.pre_flight_checks_pass) and not self._status.failsafe:
                if self._status.arming_state == VehicleStatus.ARMING_STATE_ARMED:
                    self._abort("auto_start requires an initially disarmed SITL vehicle", now)
                elif self._heartbeat_started and now - self._heartbeat_received < 0.4:
                    if now - self._heartbeat_started >= self._number("heartbeat_prestream_s"):
                        startup_issues = self._native_readiness_issues() if getattr(self, "_native_takeoff", False) else []
                        if startup_issues:
                            self._reason = "waiting for native EKF readiness: " + ", ".join(startup_issues)
                            self._flight_pub.publish(outgoing)
                            self._publish_phase(wall_s=now)
                            return
                        x, y, z = self._position()
                        self._goal = (x, y, z + self._number("takeoff_height_m"))
                        if getattr(self, "_native_takeoff", False):
                            self._native_goal_anchor = {
                                "position_enu_m": [x, y, z],
                                "odom_header_stamp_ns": self._native_odom_stamp_ns(self._odom),
                                "odom_callback_ros_s": getattr(self, "_odom_received_source_s", None),
                                "odom_callback_wall_s": self._odom_received,
                                "captured_ros_s": self.get_clock().now().nanoseconds * 1e-9,
                            }
                        self._request_started = now
                        self._change_phase("REQUEST_NATIVE_TAKEOFF" if getattr(self, "_native_takeoff", False)
                                           else "REQUEST_OFFBOARD", "heartbeat prestream complete")
        elif self._phase == "REQUEST_NATIVE_TAKEOFF":
            if not fresh or self._status.failsafe:
                self._abort("native activation guard: " + ", ".join(self._state_guard_issues(now, False)), now)
            elif (self._status.arming_state == VehicleStatus.ARMING_STATE_ARMED
                  and self._status.nav_state == VehicleStatus.NAVIGATION_STATE_AUTO_TAKEOFF):
                self._ever_armed = True
                self._takeoff_started = now
                self._native_started_source_s = self.get_clock().now().nanoseconds * 1e-9
                self._native_started_wall_s = now
                self._native_last_source_s = self._native_started_source_s
                self._change_phase("NATIVE_TAKEOFF", "PX4 owns takeoff and initial in-flight magnetic alignment")
            elif now - self._last_request >= self._number("command_retry_s"):
                if self._attempts >= int(self.get_parameter("max_command_attempts").value):
                    self._abort("native takeoff activation attempts exhausted", now)
                elif not bool(self._status.pre_flight_checks_pass):
                    self._abort("PX4 preflight checks stopped passing", now)
                elif not self._native_readiness_issues():
                    if self._status.nav_state != VehicleStatus.NAVIGATION_STATE_AUTO_TAKEOFF:
                        self._request(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF, 0.0)
                    else:
                        self._request(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0)
                    self._attempts += 1
                    self._last_request = now
        elif self._phase == "NATIVE_TAKEOFF":
            # No Offboard motion is requested here. PX4's native takeoff task
            # handles its documented initial yaw reset above 1.5 m itself.
            if not fresh or self._status.failsafe or self._status.arming_state != VehicleStatus.ARMING_STATE_ARMED:
                self._abort("native takeoff state guard: " + ", ".join(self._state_guard_issues(now, False)), now)
            elif self._status.nav_state not in (VehicleStatus.NAVIGATION_STATE_AUTO_TAKEOFF,
                                                 VehicleStatus.NAVIGATION_STATE_AUTO_LOITER):
                self._abort("native takeoff exited its expected PX4 modes", now)
            elif (native_budget_failure := self._native_budget_failure(
                    self.get_clock().now().nanoseconds * 1e-9, now)) is not None:
                self._native_finished_source_s = self.get_clock().now().nanoseconds * 1e-9
                self._native_finished_wall_s = now
                self._abort(native_budget_failure, now)
            else:
                now_s = self.get_clock().now().nanoseconds * 1e-9
                settle_issues = self._native_settle_issues(source_s=now_s, wall_s=now)
                ready = (self._status.nav_state == VehicleStatus.NAVIGATION_STATE_AUTO_LOITER
                         and not settle_issues)
                if ready:
                    if self._native_settle_started_s is None:
                        self._native_settle_started_s = now_s
                    elif now_s - self._native_settle_started_s >= self._number("native_settle_s"):
                        self._attempts = 0
                        self._request_started = now
                        self._controller_command, self._command_received = None, 0.0
                        self._native_finished_source_s, self._native_finished_wall_s = now_s, now
                        self._change_phase("REQUEST_OFFBOARD", "native takeoff settled with final EKF yaw alignment")
                else:
                    self._native_settle_started_s = None
        elif self._phase == "REQUEST_OFFBOARD":
            if not fresh or self._status.failsafe:
                self._abort("activation guard: " + ", ".join(self._state_guard_issues(now, False)), now)
            elif getattr(self, "_native_takeoff", False) and self._native_settle_issues(
                    source_s=self.get_clock().now().nanoseconds * 1e-9, wall_s=now,
                    require_physical_settle=False):
                self._abort("native final alignment/readiness/state validity lost during Offboard handoff", now)
            elif self._armed_offboard():
                self._ever_armed = True
                self._takeoff_started = now
                self._change_phase("HOLD" if getattr(self, "_native_takeoff", False) else "TAKEOFF",
                                   "armed OFFBOARD confirmed by VehicleStatus")
            elif now - self._last_request >= self._number("command_retry_s"):
                if self._attempts >= int(self.get_parameter("max_command_attempts").value):
                    self._abort("activation attempts exhausted; inspect VehicleCommandAck", now)
                elif not bool(self._status.pre_flight_checks_pass):
                    self._abort("PX4 preflight checks stopped passing", now)
                elif (getattr(self, "_native_takeoff", False)
                      and (self._status.arming_state != VehicleStatus.ARMING_STATE_ARMED
                           or self._status.nav_state != VehicleStatus.NAVIGATION_STATE_AUTO_LOITER)):
                    self._abort("native Offboard mode request requires armed AUTO_LOITER", now)
                elif getattr(self, "_native_takeoff", False) and self._native_settle_issues(
                        source_s=self.get_clock().now().nanoseconds * 1e-9, wall_s=now):
                    self._abort("native physical settle lost before Offboard mode request", now)
                else:
                    # Recheck the original dual-source limits before every
                    # actual mode request. Waiting for a response or observing
                    # armed Offboard is already beyond that native settle gate.
                    if self._status.nav_state != VehicleStatus.NAVIGATION_STATE_OFFBOARD:
                        self._request(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, 1.0, 6.0)
                    else:
                        self._request(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0)
                    self._attempts += 1
                    self._last_request = now
        elif self._phase in ("TAKEOFF", "FOLLOW", "HOLD"):
            if not fresh or not self._armed_offboard():
                self._abort("flight guard: " + ", ".join(self._state_guard_issues(now, True)), now)
            elif self._phase == "TAKEOFF":
                assert self._goal is not None
                position = self._position()
                outgoing = self._velocity_command(bounded_takeoff_velocity(
                    position, self._goal,
                    self._number("takeoff_horizontal_limit_mps"), self._number("takeoff_vertical_limit_mps"),
                    self._number("takeoff_gain"),
                ))
                error = math.sqrt(sum((a - b) ** 2 for a, b in zip(position, self._goal)))
                yaw_error = math.atan2(math.sin(quaternion_yaw(self._odom.pose.pose.orientation) - self._yaw), math.cos(quaternion_yaw(self._odom.pose.pose.orientation) - self._yaw))
                if error <= self._number("takeoff_position_tolerance_m") and abs(yaw_error) <= self._number("takeoff_yaw_tolerance_rad"):
                    self._settle_started = self._settle_started or now
                    if now - self._settle_started >= self._number("takeoff_settle_s"):
                        self._change_phase("HOLD", "takeoff settled; waiting for a fresh visual command")
                else:
                    self._settle_started = 0.0
                if now - self._takeoff_started > self._number("takeoff_timeout_s"):
                    self._abort("takeoff timeout", now)
            elif self._controller_is_fresh(now):
                outgoing = copy.deepcopy(self._controller_command)
                outgoing.header.stamp = self.get_clock().now().to_msg()
                self._yaw = float(outgoing.yaw_rad)
                self._change_phase("FOLLOW", "forwarding fresh visual controller command")
            else:
                self._change_phase("HOLD", "visual command absent, invalid or stale; zero-velocity hover")
        if self._phase == "ABORTED":
            outgoing = self._velocity_command()
            outgoing.valid = False
        self._flight_pub.publish(outgoing)
        self._publish_phase(wall_s=now)


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 and this node's message dependencies are required")
    with shutdown_requests() as requested:
        # The default rclpy signal handler can invalidate the context during
        # subscription.take_message. Stop the executor before the context.
        rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
        node = None
        executor = None
        try:
            node = FlightSupervisor()
            executor = SingleThreadedExecutor(context=node.context)
            executor.add_node(node)
            while node.context.ok() and not requested.is_set():
                executor.spin_once(timeout_sec=0.2)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        finally:
            try:
                try:
                    if executor is not None:
                        executor.shutdown()
                finally:
                    if node is not None:
                        node.destroy_node()
            finally:
                rclpy.try_shutdown()


if __name__ == "__main__":
    main()
