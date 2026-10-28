"""A shutdown-only take race must never hide a live-flight RuntimeError."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.test_flight_supervisor import flight
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

    def test_main_suppresses_only_matching_shutdown_race_and_always_cleans_up(self):
        for context_ok, message, suppressed in ((False, KNOWN_SUBSCRIPTION_TAKE_ERROR, True),
                (True, KNOWN_SUBSCRIPTION_TAKE_ERROR, False), (None, KNOWN_SUBSCRIPTION_TAKE_ERROR, False),
                (False, "actual controller failure", False)):
            with self.subTest(context_ok=context_ok, message=message):
                events = []
                error = recorded_error(message)
                node = SimpleNamespace(context=SimpleNamespace(ok=lambda:context_ok),
                                       destroy_node=lambda:events.append("destroy"))
                def spin(_node):
                    raise error
                ros = SimpleNamespace(init=lambda **kw:None, spin=spin,
                                      try_shutdown=lambda:events.append("shutdown"))
                class ExternalShutdown(Exception):
                    pass
                with patch.object(flight, "rclpy", ros), patch.object(flight, "FlightSupervisor", return_value=node), \
                        patch.object(flight, "ExternalShutdownException", ExternalShutdown, create=True):
                    if suppressed:
                        with patch("builtins.print"):
                            flight.main([])
                    else:
                        with self.assertRaises(RuntimeError) as caught:
                            flight.main([])
                        self.assertIs(caught.exception, error)
                self.assertEqual(events, ["destroy", "shutdown"])


if __name__ == "__main__":
    unittest.main()
