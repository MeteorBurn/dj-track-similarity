import threading

from dj_track_similarity.text_embedding_cache import TextEmbeddingAdapterCache


class _FakeAdapter:
    def __init__(self, family: str, device: str) -> None:
        self.embedding_key = family
        self.device = device


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _recording_factory(created: list[tuple[str, str]]):
    def factory(family: str, *, device: str) -> _FakeAdapter:
        created.append((family, device))
        return _FakeAdapter(family, device)

    return factory


def _cache(created: list[tuple[str, str]], clock: _FakeClock, ttl: float = 10.0):
    return TextEmbeddingAdapterCache(
        _recording_factory(created),
        idle_ttl_seconds=ttl,
        clock=clock,
        start_sweeper=False,
    )


def test_acquire_reuses_one_adapter_per_family_and_device() -> None:
    created: list[tuple[str, str]] = []
    cache = _cache(created, _FakeClock())

    with cache.acquire("clap", device="cpu") as first:
        pass
    with cache.acquire("clap", device="cpu") as second:
        pass

    assert first is second
    assert created == [("clap", "cpu")]


def test_acquire_separates_families_and_devices() -> None:
    created: list[tuple[str, str]] = []
    cache = _cache(created, _FakeClock())

    with cache.acquire("clap", device="cpu"):
        pass
    with cache.acquire("clap", device="cuda"):
        pass
    with cache.acquire("mulan", device="cpu"):
        pass

    assert created == [("clap", "cpu"), ("clap", "cuda"), ("mulan", "cpu")]


def test_acquire_normalizes_family_and_device_keys() -> None:
    created: list[tuple[str, str]] = []
    cache = _cache(created, _FakeClock())

    with cache.acquire("clap", device="cpu"):
        pass
    with cache.acquire(" CLAP ", device=" CPU "):
        pass

    assert created == [("clap", "cpu")]


def test_evict_idle_releases_stale_adapters_only() -> None:
    created: list[tuple[str, str]] = []
    clock = _FakeClock()
    cache = _cache(created, clock)

    with cache.acquire("clap", device="cpu"):
        pass
    clock.advance(5.0)
    with cache.acquire("mulan", device="cpu"):
        pass

    clock.advance(7.0)
    assert cache.evict_idle() == 1

    with cache.acquire("mulan", device="cpu"):
        pass
    with cache.acquire("clap", device="cpu"):
        pass

    assert created == [("clap", "cpu"), ("mulan", "cpu"), ("clap", "cpu")]


def test_evict_idle_keeps_an_adapter_that_is_in_use() -> None:
    created: list[tuple[str, str]] = []
    clock = _FakeClock()
    cache = _cache(created, clock)
    holding = threading.Event()
    release = threading.Event()

    def hold_adapter() -> None:
        with cache.acquire("clap", device="cpu"):
            holding.set()
            release.wait(5.0)

    worker = threading.Thread(target=hold_adapter)
    worker.start()
    try:
        assert holding.wait(5.0)
        clock.advance(60.0)
        assert cache.evict_idle() == 0
    finally:
        release.set()
        worker.join(5.0)

    clock.advance(60.0)
    assert cache.evict_idle() == 1


def test_close_releases_cached_adapters() -> None:
    created: list[tuple[str, str]] = []
    cache = _cache(created, _FakeClock())

    with cache.acquire("clap", device="cpu"):
        pass
    cache.close()
    with cache.acquire("clap", device="cpu"):
        pass

    assert created == [("clap", "cpu"), ("clap", "cpu")]
