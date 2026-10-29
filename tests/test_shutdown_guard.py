"""A shutdown-only take race must never hide a live-flight RuntimeError."""
import unittest
from tests import test_ros_node_shutdown as lifecycle_fixtures
from tests import test_flight_supervisor as adapter_fixtures  # Installs the ROS source package path.
from uav_tracking_px4_adapter.shutdown_guard import (
    KNOWN_SUBSCRIPTION_TAKE_ERROR, is_known_shutdown_subscription_error,
)


def recorded_error(message=KNOWN_SUBSCRIPTION_TAKE_ERROR, *, filename="/opt/ros/humble/rclpy/executors.py",
                   function="_take_subscription"):
    namespace = {}
    exec(compile("def " + function + "():\n    raise RuntimeError(message)\n", filename, "exec"),
         {"message":message}, namespace)
    try:
        namespace[function]()
    except RuntimeError as error:
        return error


class ShutdownGuardTests(unittest.TestCase):
    def test_requires_closed_context_exact_message_and_correct_subscription_frame(self):
        self.assertTrue(is_known_shutdown_subscription_error(recorded_error(), context_ok=False))
        for context_ok in (True, None, 0, "false"):
            self.assertFalse(is_known_shutdown_subscription_error(recorded_error(), context_ok=context_ok))
        for error in (recorded_error("other runtime failure"), recorded_error(function="user_callback"),
                      recorded_error(filename="/project/rclpy_alias.py"),
                      RuntimeError(KNOWN_SUBSCRIPTION_TAKE_ERROR), ValueError(KNOWN_SUBSCRIPTION_TAKE_ERROR)):
            self.assertFalse(is_known_shutdown_subscription_error(error, context_ok=False))

    def test_main_preserves_runtime_errors_after_replacing_async_signal_shutdown(self):
        for context_ok, message in ((False, KNOWN_SUBSCRIPTION_TAKE_ERROR),
                (True, KNOWN_SUBSCRIPTION_TAKE_ERROR), (False, "actual controller failure")):
            with self.subTest(context_ok=context_ok, message=message):
                error = recorded_error(message)
                main,events,_=lifecycle_fixtures.RosNodeShutdownTests().invoke(
                    "uav_tracking_px4_adapter/uav_tracking_px4_adapter/flight_supervisor.py",
                    "FlightSupervisor",spin_error=error,already_closed=not context_ok)
                with self.assertRaises(RuntimeError) as caught:
                    main([])
                self.assertIs(caught.exception,error)
                self.assertEqual(events[-3:], ["executor_shutdown","destroy","try_shutdown"])


if __name__ == "__main__":
    unittest.main()
