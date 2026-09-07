from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable


LOGGER = logging.getLogger(__name__)


class AnalysisStageQueue:
    """One in-memory worker shared by SONARA, ML, and classifier stages."""

    def __init__(self) -> None:
        self._items: queue.Queue[Callable[[], object] | None] = queue.Queue()
        self._admission_lock = threading.Lock()
        self._closing = False
        self._thread = threading.Thread(
            target=self._work, name="analysis-stage-queue", daemon=True
        )
        self._thread.start()

    def submit(self, callback: Callable[[], object]) -> None:
        with self._admission_lock:
            if self._closing:
                raise RuntimeError("Analysis queue is closed")
            self._items.put(callback)

    def close(self) -> None:
        """Reject new work, drain accepted callbacks and stop the owned worker."""
        self.check_close_allowed()
        with self._admission_lock:
            if not self._closing:
                self._closing = True
                self._items.put(None)
        self._thread.join()

    def check_close_allowed(self) -> None:
        """Let composition owners reject self-close before detaching resources."""
        if threading.current_thread() is self._thread:
            raise RuntimeError("Analysis queue cannot close from its worker")

    def _work(self) -> None:
        while True:
            callback = self._items.get()
            try:
                if callback is None:
                    return
                callback()
            except BaseException:
                LOGGER.exception("Queued analysis stage crashed")
            finally:
                callback = None
                self._items.task_done()
