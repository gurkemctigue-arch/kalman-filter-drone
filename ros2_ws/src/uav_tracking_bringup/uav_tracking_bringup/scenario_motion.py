"""Simulation-only repeatable target motion, isolated from the tracking graph.

The scenario driver reads flight phase and simulation time only. It never
provides target observations or consumes target/vehicle ground truth.
"""

from __future__ import annotations

import math

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from geometry_msgs.msg import Twist
    from rclpy.node import Node
    from std_msgs.msg import String
except ImportError:
    rclpy = None
    Node = object  # type: ignore[assignment,misc]


def motion_profile(elapsed_s: float, speed_mps: float = 0.5, motion_profile_kind: str = "standard") -> tuple[float, float]:
    """Body-forward velocity and yaw rate: accelerate, straight, gentle S turn.

    The 50-second repeating path starts with 10 seconds straight, turns left
    for 10 seconds, goes straight for 10, turns right for 10, then straight.
    A raised-cosine yaw-rate ramp avoids velocity discontinuities at turns.
    """

    if not all(math.isfinite(value) for value in (elapsed_s, speed_mps)) or speed_mps < 0.0:
        raise ValueError("motion time and nonnegative speed must be finite")
    if motion_profile_kind not in {"standard","speed_changes"}:
        raise ValueError("motion_profile_kind must be standard or speed_changes")
    if elapsed_s <= 0.0:
        return 0.0, 0.0
    speed = speed_mps * min(elapsed_s / 2.0, 1.0)
    cycle = elapsed_s % 50.0
    if motion_profile_kind == "speed_changes":
        # Pre-registered C1 raised-cosine speed transitions. The same gentle
        # S path remains; speed never reverses, jumps, or exceeds speed_mps.
        knots=((0.,1.),(8.,1.),(12.,.35),(18.,.35),(22.,1.),(28.,1.),
               (32.,.60),(36.,.60),(40.,1.),(50.,1.))
        for (ta,va),(tb,vb) in zip(knots,knots[1:]):
            if ta <= cycle < tb:
                phase=(cycle-ta)/(tb-ta)
                blend=.5-.5*math.cos(math.pi*phase)
                speed *= va+(vb-va)*blend
                break
    turn_elapsed, direction = (-1.0, 0.0)
    if 10.0 <= cycle < 20.0:
        turn_elapsed, direction = cycle - 10.0, 1.0
    elif 30.0 <= cycle < 40.0:
        turn_elapsed, direction = cycle - 30.0, -1.0
    ramp = min(turn_elapsed, 10.0 - turn_elapsed, 1.0)
    yaw_rate = direction * 0.07 * (0.5 - 0.5 * math.cos(math.pi * max(ramp, 0.0)))
    return speed, yaw_rate


class MotionTimeline:
    """Start once on FOLLOW; continue through visual HOLD, latch on ABORTED."""

    def __init__(self) -> None:
        self.started_s: float | None = None
        self.aborted = False

    def on_phase(self, phase: str, now_s: float) -> None:
        phase = phase.split(":", 1)[0].strip()
        if phase == "ABORTED":
            self.aborted = True
        elif phase == "FOLLOW" and self.started_s is None and not self.aborted:
            self.started_s = now_s

    def command(self, now_s: float, speed_mps: float = 0.5, motion_profile_kind: str = "standard") -> tuple[float, float]:
        if self.started_s is None or self.aborted:
            return 0.0, 0.0
        return motion_profile(max(now_s - self.started_s, 0.0), speed_mps,motion_profile_kind)


class ScenarioMotion(Node):
    def __init__(self) -> None:
        super().__init__("stage1_scenario_motion")
        self.declare_parameter("speed_mps", 0.5)
        self.declare_parameter("motion_profile_kind", "standard")
        if not bool(self.get_parameter("use_sim_time").value):
            raise ValueError("scenario motion requires use_sim_time=true")
        speed = float(self.get_parameter("speed_mps").value)
        if not 0.0 < speed <= 1.0:
            raise ValueError("scenario speed must be in (0, 1] m/s")
        self._speed = speed
        self._motion_profile_kind=str(self.get_parameter("motion_profile_kind").value)
        motion_profile(0,speed,self._motion_profile_kind)
        self._timeline = MotionTimeline()
        self._publisher = self.create_publisher(Twist, "/scenario/target/cmd_vel", 10)
        self.create_subscription(String, "/tracking/flight_phase", self._on_phase, 10)
        self.create_timer(0.05, self._tick)

    def _now(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_phase(self, message: "String") -> None:
        self._timeline.on_phase(message.data, self._now())

    def _tick(self) -> None:
        speed, yaw_rate = self._timeline.command(self._now(), self._speed,self._motion_profile_kind)
        message = Twist()
        message.linear.x, message.angular.z = speed, yaw_rate
        self._publisher.publish(message)

    def stop(self) -> None:
        self._publisher.publish(Twist())


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 is required")
    rclpy.init(args=args)
    node = None
    try:
        node = ScenarioMotion()
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
