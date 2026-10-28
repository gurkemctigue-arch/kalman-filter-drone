"""Control-tick safety across startup alignment and active source/frame resets."""
from pathlib import Path
import math
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_px4_adapter"))
from uav_tracking_px4_adapter import adapter_node
from uav_tracking_px4_adapter.frame_guard import VehicleFrameGuard
from uav_tracking_px4_adapter.source_clock import OdometrySourceClock


class FrameResetMotionTests(unittest.TestCase):
    constants = NS(MODE_POSITION=1, MODE_VELOCITY=2, MODE_HOLD=3, MODE_FAILSAFE=4)

    def command(self, mode=2):
        return NS(valid=True, mode=mode, linear_mps=NS(x=1., y=2., z=3.),
                  position_m=NS(x=10., y=20., z=30.), yaw_rad=.3, yaw_rate_radps=.1)

    def node(self, ready=True):
        state, heartbeats, setpoints = {"ready": ready}, [], []
        node = NS(_last_command=self.command(), _last_ready_state=True,
                  _frame_guard=VehicleFrameGuard(),
                  get_clock=lambda: NS(now=lambda: NS(nanoseconds=10_100_000_000)),
                  get_parameter=lambda _: NS(value=False),
                  _command_is_fresh=lambda _: True, _vehicle_ready=lambda: state["ready"],
                  _heartbeat_pub=NS(publish=heartbeats.append), _setpoint_pub=NS(publish=setpoints.append))
        return node, state, heartbeats, setpoints

    def publish(self, node):
        with patch.object(adapter_node, "TrackingCommand", self.constants, create=True), \
             patch.object(adapter_node, "OffboardControlMode", NS, create=True), \
             patch.object(adapter_node, "TrajectorySetpoint", NS, create=True):
            adapter_node.Px4AdapterNode._publish(node)

    def assert_hold(self, heartbeat, setpoint):
        self.assertTrue(heartbeat.velocity)
        self.assertFalse(heartbeat.position)
        self.assertEqual(setpoint.velocity, [0., 0., 0.])
        self.assertTrue(all(math.isnan(v) for v in setpoint.position))
        self.assertTrue(math.isnan(setpoint.yaw))
        self.assertEqual(setpoint.yawspeed, 0.)

    def test_disarmed_valid_prestream_does_not_lock_normal_startup_alignment(self):
        node, state, heartbeats, setpoints = self.node(ready=False)
        self.assertTrue(node._frame_guard.observe(0)[0])
        # FlightSupervisor's WAITING output is valid MODE_VELOCITY even while
        # the PX4 motion gate is closed. Receiving it is not flight activation.
        adapter_node.Px4AdapterNode._on_command(node, self.command())
        self.publish(node)
        self.assertFalse(node._frame_guard.locked)
        self.assertTrue(node._frame_guard.observe(1)[0])
        self.assert_hold(heartbeats[-1], setpoints[-1])
        state["ready"] = True
        self.publish(node)
        self.assertTrue(node._frame_guard.locked)
        self.assertEqual(setpoints[-1].velocity, [2., 1., -3.])

    def test_active_frame_reset_holds_immediately_despite_fresh_and_replaced_commands(self):
        node, _, heartbeats, setpoints = self.node()
        node._frame_guard.observe(1)
        self.publish(node)
        self.assertFalse(node._frame_guard.observe(2)[0])
        # No stale-odometry delay is simulated: all old command/state clocks
        # remain fresh. The adapter must still hold on its very next tick.
        for mode in (1, 2):
            adapter_node.Px4AdapterNode._on_command(node, self.command(mode))
            self.publish(node)
            self.assert_hold(heartbeats[-1], setpoints[-1])
        self.assertTrue(node._frame_guard.latched)

    def test_latched_source_clock_regression_holds_even_with_fresh_frame_and_command(self):
        node, _, heartbeats, setpoints = self.node()
        node._frame_guard.observe(1)
        clock = node._odometry_clock = OdometrySourceClock("source_sim", use_sim_time=True)
        self.assertTrue(clock.resolve(10_000_000, 10_000_000, 10_000_000_000).accepted)
        self.assertFalse(clock.resolve(1_000_000, 1_000_000, 10_010_000_000).accepted)
        for mode in (1, 2):
            adapter_node.Px4AdapterNode._on_command(node, self.command(mode))
            self.publish(node)
            self.assert_hold(heartbeats[-1], setpoints[-1])
        self.assertTrue(clock.latched)


if __name__ == "__main__":
    unittest.main()
