"""Simulation-only takeoff/handoff and single-source command supervision.

The portable controller stays independent of PX4.  This node is the sole
publisher of ``/tracking/flight_command``: it holds while the adapter streams
Offboard heartbeats, requests Offboard/arm through VehicleCommand, climbs in
ENU with bounded velocity, and finally forwards fresh controller commands.
It never creates target observations or reads simulator ground truth.
"""

from __future__ import annotations

import copy
import math
import time
from typing import Any

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from nav_msgs.msg import Odometry
    from px4_msgs.msg import EstimatorStatusFlags, OffboardControlMode, VehicleCommand, VehicleLocalPosition, VehicleStatus
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
            "takeoff_height_m": 3.0,
            "takeoff_mode": "offboard_velocity",
            "local_position_topic": "/fmu/out/vehicle_local_position_v1",
            "estimator_flags_topic": "/fmu/out/estimator_status_flags",
            "native_settle_s": 1.0,
            "native_settle_speed_mps": 0.20,
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
        requested_rtf = self._number("requested_simulation_real_time_factor")
        status_timeout = self._number("status_timeout_s")
        if not (math.isfinite(requested_rtf) and 0 < requested_rtf <= 1
                and math.isfinite(status_timeout) and status_timeout > 0):
            raise ValueError("status wall watchdog and requested simulation RTF must be valid")
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
        self._native_settle_started_s: float | None = None
        self._yaw = float(self.get_parameter("takeoff_yaw_rad").value)
        self._flight_pub = self.create_publisher(TrackingCommand, self._p("flight_command_topic"), 20)
        self._vehicle_command_pub = self.create_publisher(VehicleCommand, self._p("vehicle_command_topic"), 10)
        self._phase_pub = self.create_publisher(String, self._p("phase_topic"), 10)
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
        self.get_logger().info(f"Flight supervisor: {self._phase}; auto_start={self._auto_start}")
        self.get_logger().info(
            f"PX4 status watchdog: requested_simulation_rtf={requested_rtf:.3f}, "
            f"status_timeout_wall_s={status_timeout:.3f}; PX4 Commander nominal source period=0.500 sim s"
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

    def _on_status(self, message: Any) -> None:
        self._status, self._status_received = message, time.monotonic()

    def _on_command(self, message: Any) -> None:
        self._controller_command, self._command_received = message, time.monotonic()

    def _on_native_local(self, message: Any) -> None:
        self._native_local = message

    def _on_estimator_flags(self, message: Any) -> None:
        self._estimator_flags = message

    def _native_readiness_issues(self, *, inflight: bool = False) -> list[str]:
        return readiness_issues(self._native_local, self._estimator_flags,
                                self.get_clock().now().nanoseconds * 1e-9,
                                require_inflight_alignment=inflight)

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
            and now - self._status_received <= self._number("status_timeout_s")
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
            if now - self._status_received > self._number("status_timeout_s"):
                issues.append("status_stale")
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
        return (
            f"wall_monotonic_s={now:.6f}, ros_now_ns={self.get_clock().now().nanoseconds}, "
            f"odom_age_wall_s={now - self._odom_received:.3f}, "
            f"odom_limit_s={self._number('odometry_timeout_s'):.3f}, "
            f"odom_received_monotonic_s={self._odom_received:.6f}, odom_stamp_ns={odom_stamp_ns}, "
            f"status_age_wall_s={now - self._status_received:.3f}, "
            f"status_limit_s={self._number('status_timeout_s'):.3f}, "
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
                            state = String()
                            state.data = f"{self._phase}: {self._reason}"
                            self._phase_pub.publish(state)
                            return
                        x, y, z = self._position()
                        self._goal = (x, y, z + self._number("takeoff_height_m"))
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
            else:
                position = self._position()
                error = math.sqrt(sum((a - b) ** 2 for a, b in zip(position, self._goal)))
                velocity = self._odom.twist.twist.linear
                speed = math.sqrt(sum(float(value) ** 2 for value in (velocity.x, velocity.y, velocity.z)))
                ready = (self._status.nav_state == VehicleStatus.NAVIGATION_STATE_AUTO_LOITER
                         and not self._native_readiness_issues(inflight=True)
                         and error <= self._number("takeoff_position_tolerance_m")
                         and math.isfinite(speed) and speed <= self._number("native_settle_speed_mps"))
                now_s = self.get_clock().now().nanoseconds * 1e-9
                if ready:
                    if self._native_settle_started_s is None:
                        self._native_settle_started_s = now_s
                    elif now_s - self._native_settle_started_s >= self._number("native_settle_s"):
                        self._attempts = 0
                        self._request_started = now
                        self._controller_command, self._command_received = None, 0.0
                        self._change_phase("REQUEST_OFFBOARD", "native takeoff settled with final EKF yaw alignment")
                else:
                    self._native_settle_started_s = None
                if now - self._takeoff_started > self._number("takeoff_timeout_s"):
                    self._abort("native takeoff/alignment timeout", now)
        elif self._phase == "REQUEST_OFFBOARD":
            if not fresh or self._status.failsafe:
                self._abort("activation guard: " + ", ".join(self._state_guard_issues(now, False)), now)
            elif getattr(self, "_native_takeoff", False) and self._native_readiness_issues(inflight=True):
                self._abort("native final alignment/readiness lost during Offboard handoff", now)
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
                else:
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
        state = String()
        state.data = f"{self._phase}: {self._reason}"
        self._phase_pub.publish(state)


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 and px4_msgs are required")
    rclpy.init(args=args)
    node = None
    try:
        node = FlightSupervisor()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            if node is not None:
                node.destroy_node()
        finally:
            rclpy.try_shutdown()


if __name__ == "__main__":
    main()
