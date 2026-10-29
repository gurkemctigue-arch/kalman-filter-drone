"""Repeated stop requests leave active native/ROS calls to finish first."""
import signal
import unittest
from unittest.mock import patch

from uav_tracking.ros_lifecycle import shutdown_requests


class SignalRequestTests(unittest.TestCase):
    def test_repeated_signals_only_request_stop_and_restore_original_handlers(self):
        prior={signal.SIGINT:object(),signal.SIGTERM:object()}
        installed=dict(prior)

        def install(number,handler):
            previous=installed[number]
            installed[number]=handler
            return previous

        events=[]
        with patch("uav_tracking.ros_lifecycle.signal.signal",side_effect=install):
            with shutdown_requests() as requested:
                self.assertFalse(requested.is_set())
                for number in (signal.SIGINT,signal.SIGINT,signal.SIGTERM):
                    installed[number](number,None)
                self.assertTrue(requested.is_set())
                events.append("native call completed")
                self.assertNotEqual(installed,prior)
                events.append("executor stopped")
                # Signals remain requests while nodes and context close.
                installed[signal.SIGINT](signal.SIGINT,None)
                events.extend(("node destroyed","context closed"))
            self.assertEqual(installed,prior)
        self.assertEqual(events,["native call completed","executor stopped","node destroyed","context closed"])

    def test_callback_failure_is_preserved_and_handlers_are_restored(self):
        prior={number:signal.getsignal(number) for number in (signal.SIGINT,signal.SIGTERM)}
        failure=RuntimeError("actual callback failure")
        with self.assertRaises(RuntimeError) as caught:
            with shutdown_requests():
                raise failure
        self.assertIs(caught.exception,failure)
        self.assertEqual({number:signal.getsignal(number) for number in prior},prior)


if __name__=="__main__":
    unittest.main()
