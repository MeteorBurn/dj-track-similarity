from dj_track_similarity.runtime import select_torch_device


class FakeCuda:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class FakeTorch:
    def __init__(self, available: bool) -> None:
        self.cuda = FakeCuda(available)


def test_auto_uses_cuda_when_pytorch_can_see_it() -> None:
    assert select_torch_device(FakeTorch(True), "auto") == "cuda"


def test_auto_falls_back_to_cpu_when_cuda_is_not_available() -> None:
    assert select_torch_device(FakeTorch(False), "auto") == "cpu"


def test_explicit_cuda_fails_when_unavailable() -> None:
    try:
        select_torch_device(FakeTorch(False), "cuda")
    except RuntimeError as error:
        assert "CUDA was requested" in str(error)
    else:
        raise AssertionError("explicit cuda should fail when unavailable")
