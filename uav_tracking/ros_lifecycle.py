"""Signal requests without asynchronously invalidating a live ROS context.

This module has no ROS dependency. Each adapter owns its executor and closes
it, its node (including native workers), then its ROS context on the main
thread. SIGINT/SIGTERM handlers remain installed throughout that cleanup.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import signal


@dataclass
class ShutdownRequest:
    value: bool = False

    def is_set(self) -> bool:
        return self.value


@contextmanager
def shutdown_requests():
    """Convert repeated stop signals into one idempotent boolean request.

    A signal handler must not acquire a non-reentrant Event lock, raise into
    an in-progress native call, or shut down a context still used by a take.
    Restore an embedding caller's handlers only after ordered cleanup.
    """
    requested = ShutdownRequest()
    previous = {}

    def request_stop(_signal_number, _frame):
        requested.value = True

    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, request_stop)
        yield requested
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
