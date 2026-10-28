"""Protect the local tracking frame from an in-flight PX4 estimator reset."""
from numbers import Integral


class VehicleFrameGuard:
    def __init__(self) -> None:
        self.locked = False
        self.counter: int | None = None
        self._latched = False

    def lock(self) -> None:
        # Startup alignment/reset can settle before any active flight command.
        self.locked = True

    @property
    def latched(self) -> bool:
        return self._latched

    def observe(self, reset_counter) -> tuple[bool, str]:
        if self._latched:
            return False, "vehicle_frame_reset_restart_required"
        if isinstance(reset_counter, bool) or not isinstance(reset_counter, Integral) or not 0 <= reset_counter <= 255:
            return False, "invalid_vehicle_reset_counter"
        reset_counter = int(reset_counter)
        if self.counter is not None and reset_counter != self.counter and self.locked:
            self._latched = True
            return False, "vehicle_frame_reset_restart_required"
        self.counter = reset_counter
        return True, "vehicle_frame_valid"
