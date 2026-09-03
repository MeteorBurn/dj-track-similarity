"""Keep one loaded text-embedding model per family and device.

Building a fresh adapter per request made every text search verify the pinned
checkpoint digest, bind a private verified copy, and deserialize the weights
again: roughly 35 seconds and several gigabytes of disk traffic for a search
whose actual work is milliseconds. The cache loads an adapter once, hands it to
one caller at a time, and drops it after an idle period so the weights stop
holding device memory that analysis jobs need.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import gc
import logging
import sys
import threading
import time
from typing import Generic, TypeVar

LOGGER = logging.getLogger(__name__)

DEFAULT_IDLE_TTL_SECONDS = 600.0
_MINIMUM_SWEEP_SECONDS = 5.0

AdapterT = TypeVar("AdapterT")


class _CacheEntry(Generic[AdapterT]):
    def __init__(self, adapter: AdapterT, last_used: float) -> None:
        self.adapter = adapter
        self.lock = threading.RLock()
        self.last_used = last_used


class TextEmbeddingAdapterCache(Generic[AdapterT]):
    """Reuse one adapter per ``(family, device)`` across text search requests."""

    def __init__(
        self,
        factory: Callable[..., AdapterT],
        *,
        idle_ttl_seconds: float = DEFAULT_IDLE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        start_sweeper: bool = True,
    ) -> None:
        if idle_ttl_seconds <= 0.0:
            raise ValueError("idle_ttl_seconds must be positive")
        self._factory = factory
        self._idle_ttl_seconds = float(idle_ttl_seconds)
        self._clock = clock
        self._start_sweeper = start_sweeper
        self._entries: dict[tuple[str, str], _CacheEntry[AdapterT]] = {}
        self._guard = threading.Lock()
        self._stop = threading.Event()
        self._sweeper: threading.Thread | None = None

    @contextmanager
    def acquire(self, family: str, *, device: str) -> Iterator[AdapterT]:
        """Yield one adapter, held against eviction and other callers.

        Sync FastAPI endpoints run in a threadpool, so two text searches can
        reach the same model object. Serializing them here keeps one forward
        pass at a time and keeps a sweep from dropping a model mid-request.
        """

        entry = self._checkout(_cache_key(family, device))
        with entry.lock:
            try:
                yield entry.adapter
            finally:
                entry.last_used = self._clock()

    def loaded(self) -> tuple[tuple[str, str], ...]:
        """The ``(family, device)`` keys held right now, in checkout order."""

        with self._guard:
            return tuple(self._entries)

    def evict_idle(self) -> int:
        """Drop adapters nobody has used for longer than the idle TTL."""

        deadline = self._clock() - self._idle_ttl_seconds
        return self._evict(lambda entry: entry.last_used <= deadline)

    def evict_all(self) -> int:
        """Drop every adapter that is not currently in use."""

        return self._evict(lambda _entry: True)

    def close(self) -> None:
        """Stop sweeping and release the adapters this cache still holds."""

        self._stop.set()
        self._sweeper = None
        self.evict_all()

    def _checkout(self, key: tuple[str, str]) -> _CacheEntry[AdapterT]:
        with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                family, device = key
                entry = _CacheEntry(
                    self._factory(family, device=device),
                    self._clock(),
                )
                self._entries[key] = entry
                LOGGER.info(
                    "text embedding adapter created family=%s device=%s",
                    family,
                    device,
                )
            else:
                # Claim the entry before releasing the guard so a concurrent
                # sweep cannot treat it as idle while this request loads it.
                entry.last_used = self._clock()
        self._ensure_sweeper()
        return entry

    def _evict(
        self,
        should_evict: Callable[[_CacheEntry[AdapterT]], bool],
    ) -> int:
        dropped: list[tuple[str, str]] = []
        with self._guard:
            for key in list(self._entries):
                entry = self._entries[key]
                if not should_evict(entry):
                    continue
                if not entry.lock.acquire(blocking=False):
                    # A request holds it; the next sweep can drop it instead.
                    continue
                try:
                    del self._entries[key]
                finally:
                    entry.lock.release()
                dropped.append(key)
                entry = None  # type: ignore[assignment]
        if not dropped:
            return 0
        _release_device_memory()
        for family, device in dropped:
            LOGGER.info(
                "text embedding adapter released family=%s device=%s",
                family,
                device,
            )
        return len(dropped)

    def _ensure_sweeper(self) -> None:
        if (
            not self._start_sweeper
            or self._sweeper is not None
            or self._stop.is_set()
        ):
            return
        with self._guard:
            if self._sweeper is not None:
                return
            interval = max(
                _MINIMUM_SWEEP_SECONDS,
                self._idle_ttl_seconds / 2.0,
            )
            sweeper = threading.Thread(
                target=self._sweep_until_stopped,
                args=(interval,),
                name="text-embedding-adapter-sweeper",
                daemon=True,
            )
            self._sweeper = sweeper
            sweeper.start()

    def _sweep_until_stopped(self, interval: float) -> None:
        while not self._stop.wait(interval):
            try:
                self.evict_idle()
            except Exception:  # pragma: no cover - a sweep must not end the thread.
                LOGGER.exception("text embedding adapter sweep failed")


def _cache_key(family: str, device: str) -> tuple[str, str]:
    return str(family).strip().lower(), str(device).strip().lower()


def _release_device_memory() -> None:
    """Return dropped weights to the CUDA allocator, not just to Python."""

    gc.collect()
    torch = sys.modules.get("torch")
    if torch is None:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # pragma: no cover - depends on the local CUDA runtime.
        LOGGER.debug("CUDA cache release failed", exc_info=True)
