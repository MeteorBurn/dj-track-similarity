"""Bounded, application-owned admission cache for completed search arms."""

from collections import OrderedDict
from collections.abc import Callable
import threading
import time

from ..text_search_models import TextSearchRun


class TextSearchRunCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 1800,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._maximum = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._runs: OrderedDict[str, tuple[float, TextSearchRun]] = OrderedDict()

    def put(self, run: TextSearchRun) -> None:
        with self._lock:
            self._expire()
            self._runs[run.to_dict()["run_id"]] = (self._clock(), run)
            while len(self._runs) > self._maximum:
                self._runs.popitem(last=False)

    def get(self, run_id: str) -> TextSearchRun | None:
        with self._lock:
            self._expire()
            entry = self._runs.get(run_id)
            return entry[1] if entry else None

    def _expire(self) -> None:
        now = self._clock()
        while self._runs and now - next(iter(self._runs.values()))[0] >= self._ttl:
            self._runs.popitem(last=False)
