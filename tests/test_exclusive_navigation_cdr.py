"""Real generated transport for the complete bounded native exclusive cloud."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class ExclusiveNavigationCDRTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Requires Linux ROS 2 generated messages after colcon build")
    def test_real_cdr_retains_complete_native_cloud_and_independent_invalid_candidate(self):
        # A fresh interpreter avoids Python ROS test doubles installed by other
        # pure unit modules. The frozen validation environment supplies the
        # actual generated interfaces and their native type-support libraries.
        code = r'''
import importlib
from pathlib import Path
import numpy as np
from rclpy.serialization import serialize_message, deserialize_message
from uav_tracking_interfaces.msg import TargetObservation, TargetObservationArray
from uav_tracking.core.exclusive_navigation import MAX_EXCLUSIVE_PIXELS

root = Path.cwd().resolve()
module = importlib.import_module(TargetObservation.__module__)
assert Path(module.__file__).resolve().is_relative_to(root/'ros2_ws')
source = TargetObservation()
source.header.stamp.sec = 12
source.header.stamp.nanosec = 300000000
source.header.frame_id = 'camera_optical_frame'
source.candidate_id = 7
source.class_name = 'car'
source.camera_frame = source.header.frame_id
source.navigation_exclusive_depth_complete = True
source.navigation_exclusive_expected_pixel_count = MAX_EXCLUSIVE_PIXELS
source.navigation_exclusive_valid_pixel_count = MAX_EXCLUSIVE_PIXELS
source.navigation_exclusive_reason = 'complete_native_exclusive'
points = np.column_stack((np.linspace(-1., 1., MAX_EXCLUSIVE_PIXELS),
                          np.linspace(-.5, .5, MAX_EXCLUSIVE_PIXELS),
                          np.full(MAX_EXCLUSIVE_PIXELS, 5.))).astype(np.float32)
source.navigation_exclusive_points_camera_m = points.ravel().tolist()
source.navigation_points_camera_m = [0., 0., 10.]
source.navigation_visibility_support_camera_m = [.1, .2, 5.]
other = TargetObservation()
other.header = source.header
other.candidate_id = 8
other.navigation_exclusive_depth_complete = False
other.navigation_exclusive_expected_pixel_count = 20
other.navigation_exclusive_valid_pixel_count = 19
other.navigation_exclusive_reason = 'exclusive_native_depth_incomplete'
frame = TargetObservationArray()
frame.header = source.header
frame.observations = [source, other]
wire = serialize_message(frame)
assert 0 < len(wire) < 1024*1024
decoded = deserialize_message(wire, TargetObservationArray)
a, b = decoded.observations
assert decoded.header == frame.header and a.header == source.header
assert a.candidate_id == 7 and a.navigation_exclusive_depth_complete is True
assert a.navigation_exclusive_expected_pixel_count == MAX_EXCLUSIVE_PIXELS
assert a.navigation_exclusive_valid_pixel_count == MAX_EXCLUSIVE_PIXELS
assert a.navigation_exclusive_reason == source.navigation_exclusive_reason
np.testing.assert_array_equal(np.asarray(a.navigation_exclusive_points_camera_m).reshape(-1, 3), points)
assert list(a.navigation_points_camera_m) == [0., 0., 10.]
np.testing.assert_array_equal(np.asarray(a.navigation_visibility_support_camera_m, dtype=np.float32), np.array([.1, .2, 5.], dtype=np.float32))
assert b.candidate_id == 8 and b.navigation_exclusive_depth_complete is False
assert b.navigation_exclusive_expected_pixel_count == 20 and b.navigation_exclusive_valid_pixel_count == 19
assert b.navigation_exclusive_reason == 'exclusive_native_depth_incomplete'
assert len(b.navigation_exclusive_points_camera_m) == 0
print('ACTUAL_EXCLUSIVE_NATIVE_CLOUD_CDR_PASS', MAX_EXCLUSIVE_PIXELS, len(wire))
'''
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ACTUAL_EXCLUSIVE_NATIVE_CLOUD_CDR_PASS 16384", result.stdout)


if __name__ == "__main__":
    unittest.main()
