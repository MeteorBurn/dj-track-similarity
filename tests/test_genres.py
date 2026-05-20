from pathlib import Path

import numpy as np
import pytest
import torch

import dj_track_similarity.genres as genres
from dj_track_similarity.genres import MaestGenreAdapter, _move_maest_runtime_modules


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


class BatchMaestModel:
    labels = ["A", "B", "C"]

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[int, ...], bool]] = []
        self.melspectrogram = MovableModule()

    def init_melspectrogram(self):
        return None

    def __call__(self, audio, *, melspectrogram_input=False):
        self.calls.append((tuple(audio.shape), melspectrogram_input))
        rows = [
            [0.0, 2.0, 1.0],
            [0.5, 1.5, 1.0],
            [1.0, 1.0, 1.0],
            [3.0, 1.0, 0.0],
            [2.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ]
        return torch.tensor(rows[: audio.shape[0]]), None

    def predict_labels(self, audio):
        raise AssertionError("MAEST batch inference must not use predict_labels")


class BatchMaestAdapter(MaestGenreAdapter):
    def __init__(self) -> None:
        super().__init__(device="cpu", top_k=2)
        self.fake_model = BatchMaestModel()

    def _load_model(self) -> None:
        self._torch = torch
        self._torchaudio = object()
        self.device = "cpu"
        self._model = self.fake_model


def test_maest_predict_batch_uses_model_logits_per_track(monkeypatch) -> None:
    def fake_load_audio(path, *, torchaudio_module=None, target_sample_rate=None):
        value = 1.0 if Path(path).name == "a.wav" else 2.0
        return np.full(16000 * 120, value, dtype=np.float32), 16000, "fake"

    monkeypatch.setattr(genres, "load_audio_mono", fake_load_audio)
    adapter = BatchMaestAdapter()

    batches = adapter.predict_batch(["a.wav", "b.wav"])

    assert adapter.fake_model.calls == [((6, 480000), False)]
    assert batches[0][0]["label"] == "B"
    assert batches[0][0]["score"] == pytest.approx(torch.sigmoid(torch.tensor([2.0, 1.5, 1.0])).mean().item())
    assert batches[0][1]["label"] == "C"
    assert batches[0][1]["score"] == pytest.approx(torch.sigmoid(torch.tensor([1.0, 1.0, 1.0])).mean().item())
    assert batches[1][0]["label"] == "A"
    assert batches[1][0]["score"] == pytest.approx(torch.sigmoid(torch.tensor([3.0, 2.0, 1.0])).mean().item())
    assert batches[1][1]["label"] == "B"
    assert batches[1][1]["score"] == pytest.approx(torch.sigmoid(torch.tensor([1.0, 1.0, 1.0])).mean().item())
    assert [[item["label"] for item in row] for row in batches] == [["B", "C"], ["A", "B"]]


def test_maest_prepares_three_30_second_windows(monkeypatch) -> None:
    sample_rate = 16000
    audio = np.arange(sample_rate * 200, dtype=np.float32)

    def fake_load_audio(path, *, torchaudio_module=None, target_sample_rate=None):
        return audio, sample_rate, "fake"

    monkeypatch.setattr(genres, "load_audio_mono", fake_load_audio)
    adapter = BatchMaestAdapter()
    adapter._load_model()

    prepared = adapter._prepare_audio_windows("long.wav")

    assert [window.numel() for window in prepared] == [sample_rate * 30, sample_rate * 30, sample_rate * 30]
    assert prepared[0][0].item() == sample_rate * 60
    assert prepared[0][-1].item() == sample_rate * 90 - 1
    assert prepared[1][0].item() == sample_rate * 76
    assert prepared[1][-1].item() == sample_rate * 106 - 1
    assert prepared[2][0].item() == sample_rate * 144
    assert prepared[2][-1].item() == sample_rate * 174 - 1
