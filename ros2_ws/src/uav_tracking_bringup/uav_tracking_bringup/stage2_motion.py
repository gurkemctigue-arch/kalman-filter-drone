"""Three independent rendered actors; isolated from target estimation.

The scenario owns actor commands and known initial paths. It never publishes
observations, selections, target state, odometry, or flight commands. Model
names exist only in the SDF; runtime tracking sees camera measurements only.
"""

from __future__ import annotations

import json
import math

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from geometry_msgs.msg import Twist
    from rclpy.node import Node
    from std_msgs.msg import String
except ImportError:
    rclpy = None
    Node = object

from .scenario_motion import MotionTimeline


def _smoothstep_derivatives(time_s: float, duration_s: float) -> tuple[float, float]:
    """First and second time derivatives of quintic 0-to-1 travel."""
    if time_s <= 0.0 or time_s >= duration_s:
        return 0.0, 0.0
    u = time_s / duration_s
    return (30 * u * u * (1 - u) ** 2 / duration_s,
            60 * u * (1 - 3 * u + 2 * u * u) / duration_s ** 2)


def stage2_motion_profile(elapsed_s: float, *, target_class: str = "person",
                          scenario_kind: str = "crossing", speed_mps: float = 0.5
                          ) -> tuple[tuple[float, float], ...]:
    """Return body-forward speed and yaw rate for each physical actor.

    ``crossing`` exchanges the lateral lanes of two depth-separated actors;
    their image projections can cross the selected centre actor. ``ambiguity``
    brings actor 1 alongside actor 0, holds for one second, then separates.
    This intentionally tests safe suspension, not appearance-based ReID.
    Actors have no ground-contact dynamics. VelocityControl applies body-frame
    commands; curvature below makes cars turn rather than translate sideways.
    """
    if target_class not in {"person", "car"}:
        raise ValueError("target_class must be person or car")
    if scenario_kind not in {"parallel", "crossing", "ambiguity"}:
        raise ValueError("scenario_kind must be parallel, crossing, or ambiguity")
    if not math.isfinite(elapsed_s) or not math.isfinite(speed_mps) or not 0 < speed_mps <= 1:
        raise ValueError("time and speed must be finite; speed must be in (0, 1]")
    if elapsed_s <= 0:
        return ((0.0, 0.0),) * 3
    vx = speed_mps * min(elapsed_s / 2.0, 1.0)
    # Displacements begin only after the two-second common acceleration and
    # two-second straight segment, giving a zero-heading initial condition.
    t = max(0.0, elapsed_s - 4.0)
    amplitude = 2.0 if target_class == "person" else 4.2
    commands = [(vx, 0.0)]
    for index in (1, 2):
        actor_vx, actor_vy, actor_ax, actor_ay = vx, 0.0, 0.0, 0.0
        if t > 0 and scenario_kind == "crossing":
            sign = 1.0 if index == 1 else -1.0
            omega = 2.0 * math.pi / 30.0
            actor_vy = sign * amplitude * omega * math.sin(omega * t)
            actor_ay = sign * amplitude * omega ** 2 * math.cos(omega * t)
        elif t > 0 and scenario_kind == "ambiguity" and index == 1:
            dx = (3.0 if target_class == "person" else 6.0) - 0.2
            dy = amplitude - 0.05
            # Scale duration with speed so world-forward velocity stays
            # positive even at the fastest quintic closing segment.
            duration = max(16.0 if target_class == "person" else 32.0, 2.2 * dx / speed_mps)
            return_start = duration + 1.0
            if t <= duration:
                derivative, second = _smoothstep_derivatives(t, duration)
            elif t < return_start:
                derivative, second = 0.0, 0.0
            else:
                derivative, second = _smoothstep_derivatives(t - return_start, duration)
                derivative, second = -derivative, -second
            actor_vx -= dx * derivative
            actor_vy = dy * derivative
            actor_ax = -dx * second
            actor_ay = dy * second
        speed = math.hypot(actor_vx, actor_vy)
        yaw_rate = ((actor_vx * actor_ay - actor_vy * actor_ax) / speed ** 2
                    if speed > 1e-9 else 0.0)
        commands.append((speed, yaw_rate))
    return tuple(commands)


class Stage2Motion(Node):
    def __init__(self):
        super().__init__("stage2_scenario_motion")
        self.declare_parameter("target_class", "person")
        self.declare_parameter("scenario_kind", "crossing")
        self.declare_parameter("speed_mps", 0.5)
        if not bool(self.get_parameter("use_sim_time").value):
            raise ValueError("stage-two motion requires use_sim_time=true")
        self._class = str(self.get_parameter("target_class").value)
        self._kind = str(self.get_parameter("scenario_kind").value)
        self._speed = float(self.get_parameter("speed_mps").value)
        stage2_motion_profile(0, target_class=self._class, scenario_kind=self._kind, speed_mps=self._speed)
        self._timeline = MotionTimeline()
        self._publishers = [self.create_publisher(Twist, f"/scenario/target_{index}/cmd_vel", 10)
                            for index in range(3)]
        self._events = self.create_publisher(String, "/scenario/stage2_profile", 10)
        self.create_subscription(String, "/tracking/flight_phase", self._on_phase, 10)
        self.create_timer(0.05, self._tick)

    def _now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_phase(self, message):
        self._timeline.on_phase(message.data, self._now())

    def _tick(self):
        elapsed = (0.0 if self._timeline.started_s is None or self._timeline.aborted
                   else max(0.0, self._now() - self._timeline.started_s))
        commands = stage2_motion_profile(elapsed, target_class=self._class,
                                         scenario_kind=self._kind, speed_mps=self._speed)
        for publisher, (speed, yaw_rate) in zip(self._publishers, commands):
            command = Twist()
            command.linear.x, command.angular.z = speed, yaw_rate
            publisher.publish(command)
        event = String()
        event.data = json.dumps({"time_s": self._now(), "elapsed_s": elapsed,
                                 "scenario_kind": self._kind, "target_class": self._class,
                                 "body_speed_yawrate": commands}, allow_nan=False)
        self._events.publish(event)

    def stop(self):
        for publisher in self._publishers:
            publisher.publish(Twist())


def main(args=None):
    if rclpy is None:
        raise RuntimeError("ROS 2 is required")
    rclpy.init(args=args)
    node = None
    try:
        node = Stage2Motion()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            if node is not None:
                try:
                    if rclpy.ok():
                        node.stop()
                finally:
                    node.destroy_node()
        finally:
            rclpy.try_shutdown()


if __name__ == "__main__":
    main()
