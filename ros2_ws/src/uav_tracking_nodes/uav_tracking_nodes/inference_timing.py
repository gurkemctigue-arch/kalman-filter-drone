"""Local, bounded timing of one inference job; no ROS or worker ownership."""

from __future__ import annotations

from contextlib import contextmanager
import time


class InferenceTiming:
    """Consecutive stages partition work; lock holds are inclusive metadata.

    The final measurement excludes writing its own timing log. Thread CPU
    time covers only this thread, not all native PyTorch/OpenMP workers.
    """

    def __init__(self, *, wall_clock=None, cpu_clock=None):
        self._wall_clock = wall_clock or time.perf_counter
        self._cpu_clock = cpu_clock or time.thread_time
        self._start_wall = self._last_wall = self._wall_clock()
        self._start_cpu = self._last_cpu = self._cpu_clock()
        self.stages = {}
        self.lock_holds = {}
        self._active_stage = None

    def begin(self, name):
        self.mark("bookkeeping")
        self._active_stage = name

    def end(self):
        self.mark(self._active_stage)
        self._active_stage = None

    def mark(self, name):
        wall, cpu = self._wall_clock(), self._cpu_clock()
        entry = self.stages.setdefault(name, {"wall_s": 0., "thread_cpu_s": 0., "count": 0})
        entry["wall_s"] += wall - self._last_wall
        entry["thread_cpu_s"] += cpu - self._last_cpu
        entry["count"] += 1
        self._last_wall, self._last_cpu = wall, cpu

    @contextmanager
    def stage(self, name):
        self.begin(name)
        try:
            yield
        finally:
            self.end()

    @contextmanager
    def input_lock(self, lock, name):
        self.mark("bookkeeping")
        lock.acquire()
        self.mark(name + "_lock_wait")
        start_wall, start_cpu = self._last_wall, self._last_cpu
        try:
            yield
        finally:
            self.mark(self._active_stage or "bookkeeping")
            self._active_stage = None
            self.lock_holds[name] = {
                "wall_s": self._last_wall - start_wall,
                "thread_cpu_s": self._last_cpu - start_cpu,
                "scope": "inclusive_not_part_of_stage_sum",
            }
            lock.release()

    def snapshot(self, *, final=False):
        """Return detached data; final adds the remaining exclusive stage."""
        if final:
            self.mark(self._active_stage or "bookkeeping")
            self._active_stage = None
        return {
            "schema_version": 1,
            "scope": ("production_work_before_timing_log" if final
                      else "partial_before_diagnostics_encode_and_publish"),
            "production_work_before_timing_log_wall_s": (self._last_wall - self._start_wall if final else None),
            "measured_prefix_wall_s": self._last_wall - self._start_wall,
            "measured_prefix_thread_cpu_s": self._last_cpu - self._start_cpu,
            "stages": {name: dict(values) for name, values in self.stages.items()},
            "input_lock_holds": {name: dict(values) for name, values in self.lock_holds.items()},
            "stage_sum_excludes_inclusive_lock_holds": True,
            "thread_cpu_scope": "calling_worker_thread_only_not_all_native_workers",
        }
