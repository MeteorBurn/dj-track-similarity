# ruff: noqa: E402

import logging
import hashlib
from pathlib import Path
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


def test_clap_adapter_uses_immutable_music_checkpoint_identity() -> None:
    assert ClapEmbeddingAdapter.embedding_key == "clap"
    assert ClapEmbeddingAdapter.checkpoint_repo == "lukewys/laion_clap"
    assert (
        ClapEmbeddingAdapter.checkpoint_filename
        == "music_audioset_epoch_15_esc_90.14.pt"
    )
    assert (
        ClapEmbeddingAdapter.model_name
        == "lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt"
    )
    assert (
        ClapEmbeddingAdapter.model_revision
        == "b3708341862f581175dba5c356a4ebf74a9b6651"
    )
    assert (
        ClapEmbeddingAdapter.checkpoint_sha256
        == "fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd"
    )
    assert ClapEmbeddingAdapter.loader_version == "1.1.7"
    assert ClapEmbeddingAdapter.hub_version == "1.22.0"


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


def test_clap_text_embedding_preflights_pinned_verified_checkpoint_once(
    monkeypatch, tmp_path
) -> None:
    calls: dict[str, object] = {}
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"stub checkpoint")
    text_snapshot = tmp_path / "roberta-snapshot"
    text_snapshot.mkdir()
    for file_name in ClapEmbeddingAdapter.text_snapshot_files:
        (text_snapshot / file_name).write_bytes(file_name.encode())

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

    def fake_hf_hub_download(*, repo_id, filename, revision):
        calls.setdefault("downloads", []).append((repo_id, filename, revision))
        return str(checkpoint)

    hf_module.hf_hub_download = fake_hf_hub_download

    def fake_snapshot_download(*, repo_id, revision, allow_patterns):
        calls["text_download"] = (repo_id, revision, allow_patterns)
        return str(text_snapshot)

    hf_module.snapshot_download = fake_snapshot_download

    class ExactTokenizerLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["tokenizer_load"] = (source, kwargs)
            (text_snapshot / "config.json").write_bytes(b"mutated source")
            assert (Path(source) / "config.json").read_bytes() == b"config.json"
            return object()

    class ExactModelLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["model_load"] = (source, kwargs)
            assert (Path(source) / "config.json").read_bytes() == b"config.json"
            return object()

    transformers_module = types.ModuleType("transformers")
    transformers_module.RobertaTokenizer = ExactTokenizerLoader
    transformers_module.RobertaModel = ExactModelLoader

    laion_module = types.ModuleType("laion_clap")
    hook_module = types.ModuleType("laion_clap.hook")
    clap_model_module = types.ModuleType("clap_module.model")

    class FloatingTokenizerLoader:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            raise AssertionError("floating tokenizer load was not redirected")

    class FloatingModelLoader:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            raise AssertionError("floating model load was not redirected")

    class FakeInternalClap:
        pass

    FakeInternalClap.__module__ = "clap_module.model"

    def create_model_template():
        return None

    hook_module.create_model = types.FunctionType(
        create_model_template.__code__,
        {"CLAP": FakeInternalClap},
    )
    hook_module.RobertaTokenizer = FloatingTokenizerLoader
    clap_model_module.RobertaModel = FloatingModelLoader

    class FakeClapModule:
        def __init__(self, *, enable_fusion, amodel, tmodel, device):
            calls["module"] = (enable_fusion, amodel, tmodel, device)
            hook_module.RobertaTokenizer.from_pretrained("roberta-base")
            clap_model_module.RobertaModel.from_pretrained("roberta-base")

        def load_ckpt(self, checkpoint_path):
            calls["checkpoint"] = checkpoint_path

        def get_text_embedding(self, texts, use_tensor=False):
            calls["texts"] = (texts, use_tensor)
            return np.array([[0.0, 2.0, 0.0]], dtype=np.float32)

    FakeClapModule.__module__ = "laion_clap.hook"
    hook_module.CLAP_Module = FakeClapModule
    laion_module.CLAP_Module = FakeClapModule

    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)
    monkeypatch.setitem(sys.modules, "laion_clap", laion_module)
    monkeypatch.setitem(sys.modules, "laion_clap.hook", hook_module)
    monkeypatch.setitem(sys.modules, "clap_module.model", clap_model_module)
    monkeypatch.setattr(
        embedding,
        "_require_distribution_version",
        lambda distribution, version: calls.setdefault("versions", []).append(
            (distribution, version)
        ),
    )

    def verify(path, *, expected_sha256, description):
        calls["verify"] = (path, expected_sha256, description)

    monkeypatch.setattr(embedding, "_verify_checkpoint_sha256", verify)

    adapter = ClapEmbeddingAdapter(device="cpu")
    adapter.checkpoint_sha256 = hashlib.sha256(b"stub checkpoint").hexdigest()
    adapter.text_snapshot_sha256 = tuple(
        (
            file_name,
            hashlib.sha256(file_name.encode()).hexdigest(),
        )
        for file_name in adapter.text_snapshot_files
    )
    adapter.text_checkpoint_sha256 = dict(adapter.text_snapshot_sha256)[
        adapter.text_checkpoint_filename
    ]
    adapter.preflight()
    adapter.preflight()
    vector = adapter.embed_text("warm minimal house")

    assert calls["versions"] == [
        ("laion-clap", "1.1.7"),
        ("transformers", "5.13.0"),
        ("huggingface-hub", "1.22.0"),
    ]
    assert calls["downloads"] == [
        (
            "lukewys/laion_clap",
            "music_audioset_epoch_15_esc_90.14.pt",
            "b3708341862f581175dba5c356a4ebf74a9b6651",
        )
    ]
    assert calls["verify"] == (
        text_snapshot / adapter.text_checkpoint_filename,
        adapter.text_checkpoint_sha256,
        (
            "roberta-base@"
            "e2da8e2f811d1448a5b465c236feacd80ffbac7b/"
            "model.safetensors"
        ),
    )
    assert calls["text_download"] == (
        "roberta-base",
        "e2da8e2f811d1448a5b465c236feacd80ffbac7b",
        list(adapter.text_snapshot_files),
    )
    assert calls["module"] == (
        False,
        "HTSAT-base",
        "roberta",
        "device:cpu",
    )
    assert calls["checkpoint"] != str(checkpoint)
    tokenizer_path, tokenizer_kwargs = calls["tokenizer_load"]
    model_path, model_kwargs = calls["model_load"]
    assert tokenizer_path == model_path
    assert tokenizer_path != "roberta-base"
    assert not Path(tokenizer_path).exists()
    assert tokenizer_kwargs == {"local_files_only": True}
    assert model_kwargs == {"local_files_only": True}
    assert hook_module.RobertaTokenizer is FloatingTokenizerLoader
    assert clap_model_module.RobertaModel is FloatingModelLoader
    assert calls["texts"] == (["warm minimal house"], False)
    assert vector.tolist() == [0.0, 1.0, 0.0]


def test_clap_model_load_stdout_and_stderr_are_written_to_app_log(
    monkeypatch, tmp_path
) -> None:
    log_path = tmp_path / "app.log"
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"stub checkpoint")
    text_snapshot = tmp_path / "roberta-snapshot"
    text_snapshot.mkdir()
    for file_name in ClapEmbeddingAdapter.text_snapshot_files:
        (text_snapshot / file_name).write_bytes(file_name.encode())
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
    hf_module.hf_hub_download = lambda *, repo_id, filename, revision: str(checkpoint)
    hf_module.snapshot_download = (
        lambda *, repo_id, revision, allow_patterns: str(text_snapshot)
    )
    transformers_module = types.ModuleType("transformers")
    transformers_module.RobertaModel = object()
    transformers_module.RobertaTokenizer = object()

    laion_module = types.ModuleType("laion_clap")

    class FakeClapModule:
        def __init__(self, *, enable_fusion, amodel, tmodel, device):
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
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)
    monkeypatch.setitem(sys.modules, "laion_clap", laion_module)
    monkeypatch.setattr(
        embedding,
        "_require_distribution_version",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        embedding,
        "_verify_checkpoint_sha256",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        embedding,
        "_construct_clap_module_with_pinned_text_model",
        lambda clap_module_type, **kwargs: clap_module_type(
            enable_fusion=kwargs["enable_fusion"],
            amodel=kwargs["amodel"],
            tmodel=kwargs["tmodel"],
            device=kwargs["device"],
        ),
    )

    adapter = ClapEmbeddingAdapter(device="cpu")
    adapter.checkpoint_sha256 = hashlib.sha256(b"stub checkpoint").hexdigest()
    adapter.text_snapshot_sha256 = tuple(
        (
            file_name,
            hashlib.sha256(file_name.encode()).hexdigest(),
        )
        for file_name in adapter.text_snapshot_files
    )
    adapter.text_checkpoint_sha256 = dict(adapter.text_snapshot_sha256)[
        adapter.text_checkpoint_filename
    ]
    adapter.embed_text("warm minimal house")

    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()
    contents = log_path.read_text(encoding="utf-8")
    assert "[transformers] RobertaModel LOAD REPORT from: roberta-base" in contents
    assert "Load the specified checkpoint " in contents
    assert "djts-verified-model-" in contents
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
