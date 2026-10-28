from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "ros2_ws/src/uav_tracking_nodes"))
from uav_tracking_nodes.controller_node import fresh_gimbal_yaw


class GimbalYawReferenceTests(unittest.TestCase):
    def test_valid_current_world_reference(self):
        reference = SimpleNamespace(header=SimpleNamespace(frame_id="map", stamp=SimpleNamespace(sec=10, nanosec=0)),
                                    vector=SimpleNamespace(z=.4))
        self.assertEqual(fresh_gimbal_yaw(reference, 10_100_000_000, "map"), .4)
        self.assertIsNone(fresh_gimbal_yaw(reference, 10_400_000_000, "map"))
        self.assertIsNone(fresh_gimbal_yaw(reference, 9_900_000_000, "map"))
        self.assertIsNone(fresh_gimbal_yaw(reference, 10_100_000_000, "odom"))
        reference.vector.z = float("nan")
        self.assertIsNone(fresh_gimbal_yaw(reference, 10_100_000_000, "map"))
