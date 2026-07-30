from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytestmark = pytest.mark.ml

import dj_track_similarity.genres as genres  # noqa: E402
from dj_track_similarity.audio_loader import DecodedAudio  # noqa: E402
from dj_track_similarity.genres import (  # noqa: E402
    MaestGenreAdapter,
    _move_maest_runtime_modules,
)
from dj_track_similarity.maest_windows import MaestWindowContext  # noqa: E402


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
        self.first_samples: list[float] = []
        self.melspectrogram = MovableModule()
        self.offset = 0

    def init_melspectrogram(self):
        return None

    def __call__(self, audio, *, melspectrogram_input=False):
        self.calls.append((tuple(audio.shape), melspectrogram_input))
        self.first_samples.extend(float(row[0].item()) for row in audio)
        rows = [
            [0.0, 2.0, 1.0],
            [0.5, 1.5, 1.0],
            [1.0, 1.0, 1.0],
            [3.0, 1.0, 0.0],
            [2.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ]
        embedding_rows = [
            [1.0, 10.0],
            [2.0, 20.0],
            [3.0, 30.0],
            [4.0, 40.0],
            [5.0, 50.0],
            [6.0, 60.0],
        ]
        start = self.offset
        end = start + audio.shape[0]
        self.offset = end
        return torch.tensor(rows[start:end]), torch.tensor(embedding_rows[start:end])

    def predict_labels(self, audio):
        raise AssertionError("MAEST batch inference must not use predict_labels")


class BatchMaestAdapter(MaestGenreAdapter):
    def __init__(self, *, inference_batch_size: int = 32) -> None:
        super().__init__(device="cpu", top_k=2, inference_batch_size=inference_batch_size)
        self.fake_model = BatchMaestModel()

    def _load_model(self) -> None:
        self._torch = torch
        self._torchaudio = object()
        self.device = "cpu"
        self._model = self.fake_model


def test_maest_predict_batch_uses_model_logits_per_track(monkeypatch) -> None:
    def fake_load_audio(path, *, torchaudio_module=None):
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
    np.testing.assert_allclose(
        adapter.embedding_for_path("a.wav"),
        np.asarray([2.0, 20.0], dtype=np.float32) / np.linalg.norm([2.0, 20.0]),
    )
    np.testing.assert_allclose(
        adapter.embedding_for_path("b.wav"),
        np.asarray([5.0, 50.0], dtype=np.float32) / np.linalg.norm([5.0, 50.0]),
    )


def test_maest_predict_batch_chunks_prepared_windows(monkeypatch) -> None:
    def fake_load_audio(path, *, torchaudio_module=None):
        return np.full(16000 * 120, 1.0, dtype=np.float32), 16000, "fake"

    monkeypatch.setattr(genres, "load_audio_mono", fake_load_audio)
    adapter = BatchMaestAdapter(inference_batch_size=2)

    batches = adapter.predict_batch(["a.wav", "b.wav"])

    assert adapter.fake_model.calls == [((2, 480000), False), ((2, 480000), False), ((2, 480000), False)]
    assert [[item["label"] for item in row] for row in batches] == [["B", "C"], ["A", "B"]]
    np.testing.assert_allclose(
        adapter.embedding_for_path("a.wav"),
        np.asarray([2.0, 20.0], dtype=np.float32) / np.linalg.norm([2.0, 20.0]),
    )
    np.testing.assert_allclose(
        adapter.embedding_for_path("b.wav"),
        np.asarray([5.0, 50.0], dtype=np.float32) / np.linalg.norm([5.0, 50.0]),
    )


def test_maest_predict_decoded_batch_uses_shared_audio_without_loading_paths(monkeypatch) -> None:
    def fail_load_audio(*_args, **_kwargs):
        raise AssertionError("shared multi-model analysis must not reload paths for MAEST")

    monkeypatch.setattr(genres, "load_audio_mono", fail_load_audio)
    adapter = BatchMaestAdapter()
    decoded = [
        DecodedAudio(path="a.wav", audio=np.full(16000 * 120, 1.0, dtype=np.float32), sample_rate=16000, detail="shared"),
        DecodedAudio(path="b.wav", audio=np.full(16000 * 120, 2.0, dtype=np.float32), sample_rate=16000, detail="shared"),
    ]

    batches = adapter.predict_decoded_batch(decoded)

    assert adapter.fake_model.calls == [((6, 480000), False)]
    assert [[item["label"] for item in row] for row in batches] == [["B", "C"], ["A", "B"]]
    np.testing.assert_allclose(
        adapter.embedding_for_path("a.wav"),
        np.asarray([2.0, 20.0], dtype=np.float32) / np.linalg.norm([2.0, 20.0]),
    )
    np.testing.assert_allclose(
        adapter.embedding_for_path("b.wav"),
        np.asarray([5.0, 50.0], dtype=np.float32) / np.linalg.norm([5.0, 50.0]),
    )


def test_maest_decoded_batch_rejects_context_count_mismatch() -> None:
    adapter = BatchMaestAdapter()
    decoded = [
        DecodedAudio(
            path="a.wav",
            audio=np.zeros(16_000 * 60, dtype=np.float32),
            sample_rate=16_000,
            detail="test",
        )
    ]

    with pytest.raises(ValueError, match="window context count"):
        adapter.predict_decoded_batch(decoded, window_contexts=[])


def test_maest_decoded_batch_applies_context_per_track() -> None:
    sample_rate = 16_000
    base = np.arange(sample_rate * 200, dtype=np.float32)
    adapter = BatchMaestAdapter()
    structured = MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=40.0,
        outro_start_seconds=170.0,
    )
    decoded = [
        DecodedAudio(
            path="structured.wav",
            audio=base,
            sample_rate=sample_rate,
            detail="test",
        ),
        DecodedAudio(
            path="fallback.wav",
            audio=base + 10_000_000.0,
            sample_rate=sample_rate,
            detail="test",
        ),
    ]

    adapter.predict_decoded_batch(
        decoded,
        window_contexts=[structured, None],
    )

    assert adapter.fake_model.first_samples == [
        float(sample_rate * 51),
        float(sample_rate * 90),
        float(sample_rate * 129),
        float(10_000_000 + sample_rate * 25),
        float(10_000_000 + sample_rate * 85),
        float(10_000_000 + sample_rate * 145),
    ]


def test_maest_embedding_matches_declared_l2_normalization() -> None:
    adapter = BatchMaestAdapter()

    embeddings = adapter._average_embeddings_by_path(
        ["a.wav"],
        [np.asarray([3.0, 4.0], dtype=np.float32)],
        [0],
    )

    np.testing.assert_allclose(
        embeddings["a.wav"],
        np.asarray([0.6, 0.8], dtype=np.float32),
    )


def test_maest_prepares_three_30_second_windows(monkeypatch) -> None:
    sample_rate = 16000
    audio = np.arange(sample_rate * 200, dtype=np.float32)

    def fake_load_audio(path, *, torchaudio_module=None):
        return audio, sample_rate, "fake"

    monkeypatch.setattr(genres, "load_audio_mono", fake_load_audio)
    adapter = BatchMaestAdapter()
    adapter._load_model()

    prepared = adapter._prepare_audio_windows("long.wav")

    assert [window.numel() for window in prepared] == [sample_rate * 30, sample_rate * 30, sample_rate * 30]
    assert prepared[0][0].item() == sample_rate * 25
    assert prepared[0][-1].item() == sample_rate * 55 - 1
    assert prepared[1][0].item() == sample_rate * 85
    assert prepared[1][-1].item() == sample_rate * 115 - 1
    assert prepared[2][0].item() == sample_rate * 145
    assert prepared[2][-1].item() == sample_rate * 175 - 1


def test_maest_windows_use_sonara_main_range() -> None:
    sample_rate = 16_000
    audio = np.arange(sample_rate * 200, dtype=np.float32)
    adapter = BatchMaestAdapter()
    adapter._load_model()
    context = MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=40.0,
        outro_start_seconds=170.0,
    )

    prepared = adapter._prepare_audio_windows_from_audio(
        "structured.wav",
        audio,
        sample_rate,
        window_context=context,
    )

    assert [window[0].item() for window in prepared] == [
        sample_rate * 51,
        sample_rate * 90,
        sample_rate * 129,
    ]
    assert all(window.numel() == sample_rate * 30 for window in prepared)


def test_maest_short_track_remains_right_zero_padded() -> None:
    sample_rate = 16_000
    audio = np.ones(sample_rate * 10, dtype=np.float32)
    adapter = BatchMaestAdapter()
    adapter._load_model()

    prepared = adapter._prepare_audio_windows_from_audio(
        "short.wav",
        audio,
        sample_rate,
    )

    assert len(prepared) == 1
    assert prepared[0].numel() == sample_rate * 30
    assert torch.all(prepared[0][: sample_rate * 10] == 1.0)
    assert torch.all(prepared[0][sample_rate * 10 :] == 0.0)
