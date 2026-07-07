import logging
import sys
import types

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytestmark = pytest.mark.ml

import dj_track_similarity.embedding as embedding
from dj_track_similarity.audio_loader import DecodedAudio
from dj_track_similarity.embedding import (
    ClapEmbeddingAdapter,
    MertEmbeddingAdapter,
    MuqEmbeddingAdapter,
    _array_output_to_numpy,
    _pad_or_trim_audio_window,
    adapter_factories,
)
from dj_track_similarity.logging_config import configure_logging


def test_clap_adapter_uses_music_checkpoint() -> None:
    assert ClapEmbeddingAdapter.embedding_key == "clap"
    assert ClapEmbeddingAdapter.checkpoint_repo == "lukewys/laion_clap"
    assert ClapEmbeddingAdapter.checkpoint_filename == "music_audioset_epoch_15_esc_90.14.pt"
    assert ClapEmbeddingAdapter.model_name == "lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt"


def test_muq_adapter_uses_official_large_msd_checkpoint() -> None:
    assert MuqEmbeddingAdapter.embedding_key == "muq"
    assert MuqEmbeddingAdapter.model_name == "OpenMuQ/MuQ-large-msd-iter"
    assert MuqEmbeddingAdapter.target_rate == 24_000


def test_product_embedding_adapters_do_not_expose_removed_fake_adapter() -> None:
    assert set(adapter_factories()) == {"mert", "muq", "clap"}


@pytest.mark.parametrize(
    ("requested", "cuda_available", "expected"),
    [
        ("cpu", False, "cpu"),
        ("cuda", True, "cuda"),
        ("auto", True, "cuda"),
        ("auto", False, "cpu"),
    ],
)
def test_muq_adapter_uses_shared_torch_device_selection(requested: str, cuda_available: bool, expected: str) -> None:
    adapter = MuqEmbeddingAdapter(device=requested)
    adapter._torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: cuda_available))

    assert adapter._device() == expected


def test_muq_adapter_rejects_requested_cuda_when_unavailable() -> None:
    adapter = MuqEmbeddingAdapter(device="cuda")
    adapter._torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))

    with pytest.raises(RuntimeError, match="CUDA was requested"):
        adapter._device()


def test_clap_text_embedding_loads_laion_music_checkpoint(monkeypatch) -> None:
    calls: dict[str, object] = {}

    torch_module = types.ModuleType("torch")

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class FakeInferenceMode:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, traceback):
            return False

    torch_module.cuda = FakeCuda()
    torch_module.device = lambda name: f"device:{name}"
    torch_module.inference_mode = FakeInferenceMode

    torchaudio_module = types.ModuleType("torchaudio")
    hf_module = types.ModuleType("huggingface_hub")

    def fake_hf_hub_download(repo_id, filename):
        calls["download"] = (repo_id, filename)
        return "checkpoint.pt"

    hf_module.hf_hub_download = fake_hf_hub_download

    laion_module = types.ModuleType("laion_clap")

    class FakeClapModule:
        def __init__(self, *, enable_fusion, amodel, device):
            calls["module"] = (enable_fusion, amodel, device)

        def load_ckpt(self, checkpoint_path):
            calls["checkpoint"] = checkpoint_path

        def get_text_embedding(self, texts, use_tensor=False):
            calls["texts"] = (texts, use_tensor)
            return np.array([[0.0, 2.0, 0.0]], dtype=np.float32)

    laion_module.CLAP_Module = FakeClapModule

    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "laion_clap", laion_module)

    vector = ClapEmbeddingAdapter(device="cpu").embed_text("warm minimal house")

    assert calls["download"] == ("lukewys/laion_clap", "music_audioset_epoch_15_esc_90.14.pt")
    assert calls["module"] == (False, "HTSAT-base", "device:cpu")
    assert calls["checkpoint"] == "checkpoint.pt"
    assert calls["texts"] == (["warm minimal house"], False)
    assert vector.tolist() == [0.0, 1.0, 0.0]


def test_clap_model_load_stdout_and_stderr_are_written_to_app_log(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "app.log"
    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LOG", str(log_path))
    configure_logging()

    torch_module = types.ModuleType("torch")

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class FakeInferenceMode:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, traceback):
            return False

    torch_module.cuda = FakeCuda()
    torch_module.device = lambda name: f"device:{name}"
    torch_module.inference_mode = FakeInferenceMode

    torchaudio_module = types.ModuleType("torchaudio")
    hf_module = types.ModuleType("huggingface_hub")
    hf_module.hf_hub_download = lambda repo_id, filename: "checkpoint.pt"

    laion_module = types.ModuleType("laion_clap")

    class FakeClapModule:
        def __init__(self, *, enable_fusion, amodel, device):
            print("[transformers] RobertaModel LOAD REPORT from: roberta-base")

        def load_ckpt(self, checkpoint_path):
            print(f"Load the specified checkpoint {checkpoint_path} from users.")
            print("CLAP warning from stderr", file=sys.stderr)

        def get_text_embedding(self, texts, use_tensor=False):
            return np.array([[0.0, 2.0, 0.0]], dtype=np.float32)

    laion_module.CLAP_Module = FakeClapModule

    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "laion_clap", laion_module)

    ClapEmbeddingAdapter(device="cpu").embed_text("warm minimal house")

    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()
    contents = log_path.read_text(encoding="utf-8")
    assert "[transformers] RobertaModel LOAD REPORT from: roberta-base" in contents
    assert "Load the specified checkpoint checkpoint.pt from users." in contents
    assert "CLAP warning from stderr" in contents


def test_array_output_to_numpy_accepts_tensor_like_output() -> None:
    class TensorLike:
        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return np.array([[0.0, 1.0, 0.0]], dtype=np.float32)

    result = _array_output_to_numpy(TensorLike())

    assert result.tolist() == [[0.0, 1.0, 0.0]]


def test_normalize_rows_rejects_non_finite_vectors() -> None:
    for value in (np.nan, np.inf, -np.inf):
        with pytest.raises(ValueError, match="non-finite"):
            embedding._normalize_rows(np.asarray([[1.0, value, 0.0]], dtype=np.float32))


def test_normalize_rows_returns_flat_float32_unit_vectors() -> None:
    vectors = embedding._normalize_rows(np.asarray([[3.0, 4.0, 0.0]], dtype=np.float64))

    assert len(vectors) == 1
    assert vectors[0].shape == (3,)
    assert vectors[0].dtype == np.float32
    assert float(np.linalg.norm(vectors[0])) == pytest.approx(1.0)
    np.testing.assert_allclose(vectors[0], np.asarray([0.6, 0.8, 0.0], dtype=np.float32))


def test_normalize_rows_rejects_zero_vectors() -> None:
    with pytest.raises(ValueError, match="zero vector"):
        embedding._normalize_rows(np.asarray([[0.0, 0.0, 0.0]], dtype=np.float32))


def test_pad_or_trim_audio_window_returns_fixed_length_float32() -> None:
    assert _pad_or_trim_audio_window(np.array([1.0, 2.0]), 4).tolist() == [1.0, 2.0, 0.0, 0.0]
    assert _pad_or_trim_audio_window(np.array([1.0, 2.0, 3.0, 4.0]), 2).tolist() == [1.0, 2.0]
    assert _pad_or_trim_audio_window(np.array([1, 2], dtype=np.int16), 2).dtype == np.float32


def test_clap_repeatpad_or_trim_audio_window_matches_laion_short_audio_fill() -> None:
    assert embedding._repeatpad_or_trim_audio_window(np.array([1.0, 2.0]), 5).tolist() == [1.0, 2.0, 1.0, 2.0, 0.0]
    assert embedding._repeatpad_or_trim_audio_window(np.array([1.0, 2.0]), 4).tolist() == [1.0, 2.0, 1.0, 2.0]
    assert embedding._repeatpad_or_trim_audio_window(np.array([1.0, 2.0, 3.0]), 2).tolist() == [1.0, 2.0]
    assert embedding._repeatpad_or_trim_audio_window(np.array([1, 2], dtype=np.int16), 2).dtype == np.float32


class FakeClapAudioModel:
    def __init__(self) -> None:
        self.batch_shapes: list[tuple[int, ...]] = []

    def get_audio_embedding_from_data(self, x, use_tensor=False):
        self.batch_shapes.append(tuple(x.shape))
        return np.asarray([[1.0, 0.0, 0.0] for _ in range(x.shape[0])], dtype=np.float32)


class SharedAudioClapAdapter(ClapEmbeddingAdapter):
    def __init__(self) -> None:
        super().__init__(device="cpu", window_seconds=1.0, max_windows=1, inference_batch_size=4)
        self.fake_model = FakeClapAudioModel()

    def _load_model(self) -> None:
        self._torch = torch
        self._torchaudio = None
        self.device = "cpu"
        self._model = self.fake_model


def test_clap_embed_decoded_batch_uses_shared_audio_without_loading_paths(monkeypatch) -> None:
    def fail_load_audio(*_args, **_kwargs):
        raise AssertionError("shared multi-model analysis must not reload paths for CLAP")

    monkeypatch.setattr(embedding, "load_audio_mono", fail_load_audio)
    adapter = SharedAudioClapAdapter()
    decoded = [
        DecodedAudio(path="a.wav", audio=np.ones(48_000, dtype=np.float32), sample_rate=48_000, detail="shared"),
        DecodedAudio(path="b.wav", audio=np.ones(48_000, dtype=np.float32), sample_rate=48_000, detail="shared"),
    ]

    vectors = adapter.embed_decoded_batch(decoded)

    assert [vector.tolist() for vector in vectors] == [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    assert adapter.fake_model.batch_shapes == [(2, 48000)]


class FakeMuqAudioModel:
    def __init__(self) -> None:
        self.batch_shapes: list[tuple[int, ...]] = []
        self.batch_dtypes: list[torch.dtype] = []

    def __call__(self, wavs, *, output_hidden_states=True):
        assert output_hidden_states is True
        self.batch_shapes.append(tuple(wavs.shape))
        self.batch_dtypes.append(wavs.dtype)
        hidden = torch.zeros((wavs.shape[0], 2, 3), dtype=torch.float32, device=wavs.device)
        for index in range(wavs.shape[0]):
            hidden[index, :, index % hidden.shape[-1]] = 1.0
        return types.SimpleNamespace(last_hidden_state=hidden)


class SharedAudioMuqAdapter(MuqEmbeddingAdapter):
    def __init__(self, torchaudio_module=None) -> None:
        super().__init__(device="cpu", window_seconds=1.0, max_windows=1, inference_batch_size=4)
        self.fake_model = FakeMuqAudioModel()
        self.fake_torchaudio = torchaudio_module

    def _load_model(self) -> None:
        self._torch = torch
        self._torchaudio = self.fake_torchaudio
        self.device = "cpu"
        self._model = self.fake_model


def test_muq_embed_decoded_batch_uses_shared_audio_without_loading_paths(monkeypatch) -> None:
    def fail_load_audio(*_args, **_kwargs):
        raise AssertionError("shared multi-model analysis must not reload paths for MuQ")

    monkeypatch.setattr(embedding, "load_audio_mono", fail_load_audio)
    adapter = SharedAudioMuqAdapter()
    decoded = [
        DecodedAudio(path="a.wav", audio=np.ones(24_000, dtype=np.float32), sample_rate=24_000, detail="shared"),
        DecodedAudio(path="b.wav", audio=np.ones(24_000, dtype=np.float32), sample_rate=24_000, detail="shared"),
    ]

    vectors = adapter.embed_decoded_batch(decoded)

    assert [vector.tolist() for vector in vectors] == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert adapter.fake_model.batch_shapes == [(2, 24000)]
    assert adapter.fake_model.batch_dtypes == [torch.float32]


def test_muq_embed_decoded_batch_resamples_to_strict_24khz_float32() -> None:
    resample_calls: list[tuple[int, int, tuple[int, ...], torch.dtype]] = []

    class FakeResample:
        def __init__(self, sample_rate: int, target_rate: int) -> None:
            self.sample_rate = sample_rate
            self.target_rate = target_rate

        def __call__(self, waveform):
            resample_calls.append((self.sample_rate, self.target_rate, tuple(waveform.shape), waveform.dtype))
            return torch.ones((waveform.shape[0], self.target_rate), dtype=torch.float32)

    fake_torchaudio = types.SimpleNamespace(transforms=types.SimpleNamespace(Resample=FakeResample))
    adapter = SharedAudioMuqAdapter(torchaudio_module=fake_torchaudio)
    decoded = [
        DecodedAudio(path="a.wav", audio=np.ones(12_000, dtype=np.float32), sample_rate=12_000, detail="shared"),
    ]

    vectors = adapter.embed_decoded_batch(decoded)

    assert vectors[0].tolist() == [1.0, 0.0, 0.0]
    assert resample_calls == [(12_000, 24_000, (1, 12000), torch.float32)]
    assert adapter.fake_model.batch_shapes == [(1, 24000)]
    assert adapter.fake_model.batch_dtypes == [torch.float32]


class FakeMertProcessor:
    sampling_rate = 2

    def __call__(self, window_batch, *, sampling_rate, padding, return_tensors):
        assert sampling_rate == self.sampling_rate
        assert padding is True
        assert return_tensors == "pt"
        return {
            "input_values": torch.zeros((2, 4), dtype=torch.float32),
            "attention_mask": torch.tensor([[1, 1, 0, 0], [1, 1, 1, 1]], dtype=torch.long),
        }


class FakeMertModel:
    def __init__(self) -> None:
        self.feature_mask_calls: list[tuple[int, tuple[int, ...]]] = []

    def __call__(self, **kwargs):
        hidden = torch.tensor(
            [
                [[1.0, 0.0], [0.0, 100.0]],
                [[0.0, 1.0], [0.0, 1.0]],
            ],
            dtype=torch.float32,
        )
        return types.SimpleNamespace(hidden_states=[hidden, hidden, hidden, hidden])

    def _get_feature_vector_attention_mask(self, feature_vector_length, attention_mask):
        self.feature_mask_calls.append((feature_vector_length, tuple(attention_mask.shape)))
        return torch.tensor([[1, 0], [1, 1]], dtype=torch.long)


class SharedAudioMertAdapter(MertEmbeddingAdapter):
    def __init__(self) -> None:
        super().__init__(device="cpu", window_seconds=5.0, max_windows=1, inference_batch_size=2)
        self.fake_model = FakeMertModel()

    def _load_model(self) -> None:
        self._torch = torch
        self._torchaudio = None
        self._processor = FakeMertProcessor()
        self.device = "cpu"
        self._model = self.fake_model


def test_mert_embed_decoded_batch_uses_feature_vector_attention_mask() -> None:
    adapter = SharedAudioMertAdapter()
    decoded = [
        DecodedAudio(path="short.wav", audio=np.ones(2, dtype=np.float32), sample_rate=2, detail="shared"),
        DecodedAudio(path="full.wav", audio=np.ones(4, dtype=np.float32), sample_rate=2, detail="shared"),
    ]

    vectors = adapter.embed_decoded_batch(decoded)

    np.testing.assert_allclose(vectors[0], np.asarray([1.0, 0.0], dtype=np.float32))
    np.testing.assert_allclose(vectors[1], np.asarray([0.0, 1.0], dtype=np.float32))
    assert adapter.fake_model.feature_mask_calls == [(2, (2, 4))]
