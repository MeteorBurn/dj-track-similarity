from dj_track_similarity.genres import _move_maest_runtime_modules


class MovableModule:
    def __init__(self) -> None:
        self.devices: list[str] = []

    def to(self, device: str):
        self.devices.append(device)
        return self


class FakeMaestModel:
    def __init__(self) -> None:
        self.melspectrogram = MovableModule()
        self.init_calls = 0

    def init_melspectrogram(self):
        self.init_calls += 1


def test_moves_lazy_maest_melspectrogram_to_selected_device() -> None:
    model = FakeMaestModel()

    _move_maest_runtime_modules(model, "cuda")

    assert model.init_calls == 1
    assert model.melspectrogram.devices == ["cuda"]
