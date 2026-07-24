from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable


LOGGER = logging.getLogger(__name__)


class AnalysisStageQueue:
    """One in-memory worker shared by SONARA, ML, and classifier stages."""

    def __init__(self) -> None:
        self._items: queue.Queue[Callable[[], object]] = queue.Queue()
        self._thread = threading.Thread(
            target=self._work, name="analysis-stage-queue", daemon=True
        )
        self._thread.start()

    def submit(self, callback: Callable[[], object]) -> None:
        self._items.put(callback)

    def _work(self) -> None:
        while True:
            callback = self._items.get()
            try:
                callback()
            except Exception:
                LOGGER.exception("Queued analysis stage crashed")
            finally:
                self._items.task_done()
