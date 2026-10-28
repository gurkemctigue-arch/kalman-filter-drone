"""One inference at a time, with no waiting frame queue."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from threading import Lock
from typing import Any, Callable


class NonQueuingWorker:
    """Drop submit attempts while busy; the caller retains its newest input.

    The executor owns exactly one worker thread. A future is accepted only
    after the prior job has completed, so a slow inference never builds a FIFO
    of stale images. Closing rejects new work and joins any accepted job.
    """

    def __init__(self, process: Callable[[Any], None], on_error: Callable[[Exception], None]) -> None:
        self._process, self._on_error = process, on_error
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yolo_inference")
        self._lock = Lock()
        self._future: Future | None = None
        self._closing = False

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._future is not None and not self._future.done()

    def submit(self, job: Any) -> bool:
        with self._lock:
            if self._closing or (self._future is not None and not self._future.done()):
                return False
            self._future = self._executor.submit(self._run, job)
            return True

    def _run(self, job: Any) -> None:
        try:
            self._process(job)
        except Exception as exc:
            # A bad image/model result cannot strand the busy flag or kill
            # future inference. The node reports the original failure.
            self._on_error(exc)

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Wait for the current job; this does not permit queued work."""

        with self._lock:
            future = self._future
        if future is not None:
            try:
                future.result(timeout=timeout)
            except TimeoutError:
                return False
        return True

    def shutdown(self) -> None:
        with self._lock:
            self._closing = True
        self._executor.shutdown(wait=True, cancel_futures=False)
