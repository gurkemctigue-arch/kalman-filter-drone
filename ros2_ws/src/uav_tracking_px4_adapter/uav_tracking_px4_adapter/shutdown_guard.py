"""Narrow recognition of the observed Humble subscription-take shutdown race."""
from __future__ import annotations


KNOWN_SUBSCRIPTION_TAKE_ERROR = (
    "Unable to convert call argument to Python object (compile in debug mode for details)"
)


def is_known_shutdown_subscription_error(error: BaseException, *, context_ok: bool | None) -> bool:
    """Require an explicitly closed context, exact message and rclpy take frame.

    An active or unknown context is never treated as shutdown. Runtime errors
    from callbacks, other rclpy operations or message/ABI failures during flight
    are left visible to the caller.
    """
    if context_ok is not False or not isinstance(error, RuntimeError) or str(error) != KNOWN_SUBSCRIPTION_TAKE_ERROR:
        return False
    frame = error.__traceback__
    while frame is not None:
        code = frame.tb_frame.f_code
        if (code.co_name == "_take_subscription"
                and code.co_filename.replace("\\", "/").endswith("/rclpy/executors.py")):
            return True
        frame = frame.tb_next
    return False
