# ruff: noqa: E402

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import types

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytestmark = pytest.mark.ml

import dj_track_similarity.embedding.loading as embedding_loading
import dj_track_similarity.embedding.numerics as embedding_numerics
import dj_track_similarity.embedding.audio as embedding_audio
import dj_track_similarity.embedding.mert_v2 as embedding_mert_v2
from dj_track_similarity.audio.loader import DecodedAudio
from dj_track_similarity.embedding.clap import ClapEmbeddingAdapter
from dj_track_similarity.embedding.contracts import EmbeddingCancelledError
from dj_track_similarity.embedding.maest import MaestEmbeddingAdapter
from dj_track_similarity.embedding.mert_v2 import MertV2EmbeddingAdapter
from dj_track_similarity.embedding.muq import MuqEmbeddingAdapter
from dj_track_similarity.embedding.mulan import MuqMulanEmbeddingAdapter


def _text_embedding_rows(rows: int) -> np.ndarray:
    """Stand in for the CLAP text branch, which always returns 512 columns."""

    matrix = np.zeros((rows, ClapEmbeddingAdapter.dim), dtype=np.float32)
    matrix[:, 1] = 2.0
    return matrix


def test_clap_first_import_needs_no_training_tokenizers_or_network(tmp_path) -> None:
    script = textwrap.dedent("""
        from contextlib import nullcontext
        import importlib
        import os
        from pathlib import Path
        import socket
        import sys
        from types import SimpleNamespace

        attempts = []
        original_numba_cache = os.environ.get("NUMBA_CACHE_DIR")

        def forbidden_network(*args, **kwargs):
            attempts.append("network")
            raise AssertionError("CLAP import attempted network access")

        socket.socket.connect = forbidden_network
        socket.create_connection = forbidden_network
        socket.getaddrinfo = forbidden_network

        import transformers
        import dj_track_similarity.embedding.clap as clap

        assert "laion_clap" not in sys.modules
        tokenizer_types = {
            name: getattr(transformers, name)
            for name in ("BertTokenizer", "RobertaTokenizer", "BartTokenizer")
        }

        def forbidden_pretrained(cls, *args, **kwargs):
            attempts.append(cls.__name__)
            raise AssertionError("CLAP import attempted a pretrained asset load")

        transformers.PreTrainedTokenizerBase.from_pretrained = classmethod(forbidden_pretrained)
        transformers.PreTrainedModel.from_pretrained = classmethod(forbidden_pretrained)
        binding = SimpleNamespace(path=Path.cwd())
        clap._bind_verified_local_checkpoint = lambda *a, **kw: nullcontext(binding)
        clap._bind_verified_local_snapshot = lambda *a, **kw: nullcontext(binding)
        constructed = []

        class ModelStub:
            def load_ckpt(self, path, verbose):
                self.loaded = True

        def construct(module_type, **kwargs):
            assert module_type is sys.modules["laion_clap.hook"].CLAP_Module
            model = ModelStub()
            constructed.append(model)
            return model

        clap._construct_clap_module_with_pinned_text_model = construct
        real_import = importlib.import_module
        first_import = True

        def fail_after_first_import(name, *args, **kwargs):
            global first_import
            module = real_import(name, *args, **kwargs)
            if name == "laion_clap" and first_import:
                first_import = False
                raise RuntimeError("injected CLAP import failure")
            return module

        importlib.import_module = fail_after_first_import
        adapter = clap.ClapEmbeddingAdapter(device="cpu")
        try:
            adapter.preflight()
        except RuntimeError as error:
            assert str(error) == "injected CLAP import failure", str(error)
        else:
            raise AssertionError("Import failure was not propagated")
        assert adapter._model is None
        assert os.environ.get("NUMBA_CACHE_DIR") == original_numba_cache
        assert not constructed
        for name, original in tokenizer_types.items():
            assert getattr(transformers, name) is original
            assert getattr(sys.modules["laion_clap.training.data"], name) is original
        assert sys.modules["laion_clap.hook"].RobertaTokenizer is tokenizer_types["RobertaTokenizer"]

        adapter.preflight()
        assert len(constructed) == 1
        assert adapter._model is constructed[0]
        assert adapter._model.loaded
        assert os.environ.get("NUMBA_CACHE_DIR") == original_numba_cache
        assert attempts == [], attempts
        assert not any(Path("hf-cache").rglob("*"))
        print("CLAP cold import and failure restoration passed")
    """)
    environment = os.environ.copy()
    for name in (
        "HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE",
        "HF_ASSETS_CACHE", "HF_DATASETS_CACHE",
    ):
        environment[name] = str(tmp_path / "hf-cache")
    for name in ("TEMP", "TMP", "XDG_CACHE_HOME", "TORCH_HOME", "NUMBA_CACHE_DIR", "MPLCONFIGDIR"):
        environment[name] = str(tmp_path / "runtime-cache")
    (tmp_path / "runtime-cache").mkdir()
    environment["HF_HUB_OFFLINE"] = "0"
    environment["TRANSFORMERS_OFFLINE"] = "0"
    environment["DJ_TRACK_SIMILARITY_LOG"] = str(tmp_path / "app.log")
    for cache_configured in (True, False):
        if not cache_configured:
            environment.pop("NUMBA_CACHE_DIR")
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "CLAP cold import and failure restoration passed" in result.stdout


def test_mulan_local_safetensors_uses_strict_weight_norm_compatibility(tmp_path) -> None:
    from safetensors.torch import save_file
    from dj_track_similarity.embedding.mulan import _load_local_mulan_checkpoint

    class TinyMuLan(torch.nn.Module):
        def __init__(self, *, config):
            super().__init__()
            assert config == {"channels": 2}
            self.conv = torch.nn.utils.parametrizations.weight_norm(
                torch.nn.Conv1d(2, 2, 3), dim=2,
            )

        @classmethod
        def from_pretrained(cls, *_args, **_kwargs):
            pytest.fail("MuLan checkpoint loading reached the Hub mixin")

    expected = {
        name: torch.full_like(value, 0.125)
        for name, value in TinyMuLan(config={"channels": 2}).state_dict().items()
    }
    legacy_state = {
        name.replace("parametrizations.weight.original0", "weight_g")
            .replace("parametrizations.weight.original1", "weight_v"): value
        for name, value in expected.items()
    }
    (tmp_path / "config.json").write_text('{"channels": 2}', encoding="utf-8")
    checkpoint = tmp_path / "model.safetensors"
    save_file(legacy_state, str(checkpoint))
    restored = _load_local_mulan_checkpoint(TinyMuLan, tmp_path)
    assert not restored.training
    assert restored.state_dict().keys() == expected.keys()
    for name, value in restored.state_dict().items():
        assert torch.equal(value, expected[name]), name

    del legacy_state["conv.bias"]
    save_file(legacy_state, str(checkpoint))
    with pytest.raises(RuntimeError, match="conv.bias"):
        _load_local_mulan_checkpoint(TinyMuLan, tmp_path)


def test_clap_text_embedding_preflights_pinned_verified_checkpoint_once(
    monkeypatch, tmp_path
) -> None:
    calls: dict[str, object] = {}
    models = []
    checkpoint = tmp_path / "models" / "clap" / ClapEmbeddingAdapter.checkpoint_filename
    checkpoint.parent.mkdir(parents=True)
    monkeypatch.setattr(embedding_loading, "_MODELS_ROOT", tmp_path / "models")
    checkpoint.write_bytes(b"stub checkpoint")
    text_snapshot = tmp_path / "models" / "clap" / "text"
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

    def forbidden_resolution(*args, **kwargs):
        pytest.fail("CLAP attempted Hub/cache resolution")

    hf_module.hf_hub_download = forbidden_resolution
    hf_module.snapshot_download = forbidden_resolution

    class ExactTokenizerLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["tokenizer_load"] = (source, kwargs)
            if len(models) == 2:
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
            models.append(self)
            assert hook_module.RobertaTokenizer is not FloatingTokenizerLoader
            assert clap_model_module.RobertaModel is not FloatingModelLoader
            hook_module.RobertaTokenizer.from_pretrained("roberta-base")
            clap_model_module.RobertaModel.from_pretrained("roberta-base")
            if len(models) == 1:
                raise RuntimeError("CLAP constructor failed with text bindings active")

        def load_ckpt(self, checkpoint_path, verbose=True):
            calls["checkpoint"] = checkpoint_path

        def get_text_embedding(self, texts, use_tensor=False):
            calls["texts"] = (texts, use_tensor)
            return _text_embedding_rows(len(texts))

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
    original_verify = embedding_loading._verify_checkpoint_sha256

    def verify(path, *, expected_sha256, description):
        original_verify(path, expected_sha256=expected_sha256, description=description)
        calls["verify"] = (path, expected_sha256, description)

    monkeypatch.setattr(embedding_loading, "_verify_checkpoint_sha256", verify)

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
    with pytest.raises(RuntimeError, match="CLAP constructor failed"):
        adapter.preflight()
    assert len(models) == 1
    assert adapter._model is None
    assert hook_module.RobertaTokenizer is FloatingTokenizerLoader
    assert clap_model_module.RobertaModel is FloatingModelLoader
    assert not Path(calls["tokenizer_load"][0]).exists()

    adapter.preflight()
    adapter.preflight()
    vector = adapter.embed_text("warm minimal house")
    assert len(models) == 2
    assert models[0] is not models[1]
    assert adapter._model is models[1]

    assert calls["verify"] == (
        text_snapshot / adapter.text_checkpoint_filename,
        adapter.text_checkpoint_sha256,
        (
            "roberta-base@"
            "e2da8e2f811d1448a5b465c236feacd80ffbac7b/"
            "model.safetensors"
        ),
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
    expected = np.zeros(ClapEmbeddingAdapter.dim, dtype=np.float32)
    expected[1] = 1.0
    assert vector.tolist() == expected.tolist()


def test_normalize_rows_rejects_non_finite_vectors() -> None:
    for value in (np.nan, np.inf, -np.inf):
        with pytest.raises(ValueError, match="non-finite"):
            embedding_numerics._normalize_rows(np.asarray([[1.0, value, 0.0]], dtype=np.float32))


def test_normalize_rows_rejects_zero_vectors() -> None:
    with pytest.raises(ValueError, match="zero vector"):
        embedding_numerics._normalize_rows(np.asarray([[0.0, 0.0, 0.0]], dtype=np.float32))


class FakeClapAudioModel:
    def __init__(self) -> None:
        self.audio_calls: list[list[np.ndarray]] = []
        self.output = None

    def get_audio_embedding_from_data(self, x, use_tensor=False):
        assert use_tensor is False
        self.audio_calls.append([waveform.copy() for waveform in x])
        if self.output is not None:
            return self.output
        rows = np.zeros((len(x), 512), dtype=np.float32)
        rows[:, 0] = [waveform[0] + 3.0 for waveform in x]
        rows[:, 1] = 4.0
        return rows


class SharedAudioClapAdapter(ClapEmbeddingAdapter):
    def __init__(self) -> None:
        super().__init__(device="cpu")
        self.fake_model = FakeClapAudioModel()
        self.fake_torchaudio = None

    def _load_model(self) -> None:
        self._torch = torch
        self._torchaudio = self.fake_torchaudio
        self.device = "cpu"
        self._model = self.fake_model


def test_clap_covers_each_track_with_deterministic_consecutive_windows(monkeypatch) -> None:
    resample_calls = []

    class FakeResampler:
        def __init__(self, source_rate, target_rate):
            assert (source_rate, target_rate) == (24_000, 48_000)

        def __call__(self, waveform):
            resample_calls.append(waveform.clone())
            return waveform.repeat_interleave(2, dim=-1)

    monkeypatch.setattr(embedding_audio, "_RESAMPLERS", {})
    long_audio = torch.linspace(-1.2, 1.2, 1_278_000, dtype=torch.float64)
    short_audio = torch.linspace(0.0, 0.5, 48_001, dtype=torch.float32)
    decoded = [
        DecodedAudio(path="long.wav", audio=long_audio, sample_rate=24_000, detail="shared"),
        DecodedAudio(path="short.wav", audio=short_audio, sample_rate=48_000, detail="shared"),
        DecodedAudio(path="last.wav", audio=torch.ones(48_007), sample_rate=48_000, detail="shared"),
    ]
    expected_audio = [long_audio.float().repeat_interleave(2).numpy(), short_audio.numpy(), decoded[-1].audio.numpy()]
    long_bounds = [
        (0, 480_000),
        (480_000, 960_000),
        (960_000, 1_440_000),
        (1_440_000, 1_920_000),
        (1_920_000, 2_400_000),
        (2_076_000, 2_556_000),
    ]
    expected_track_windows = [
        [expected_audio[0][start:end] for start, end in long_bounds],
        [expected_audio[1]],
        [expected_audio[2]],
    ]
    expected_windows = [window for windows in expected_track_windows for window in windows]
    expected_vectors = []
    for windows in expected_track_windows:
        rows = np.zeros((len(windows), 512), dtype=np.float64)
        rows[:, 0] = [float(window[0]) + 3.0 for window in windows]
        rows[:, 1] = 4.0
        normalized_rows = rows / np.linalg.norm(rows, axis=1, keepdims=True)
        mean = normalized_rows.mean(axis=0)
        expected_vectors.append(mean / np.linalg.norm(mean))

    reference_vectors = None
    for batch_size in (1, 2, 3, 8):
        adapter = SharedAudioClapAdapter()
        adapter.inference_batch_size = batch_size
        adapter.fake_torchaudio = types.SimpleNamespace(transforms=types.SimpleNamespace(Resample=FakeResampler))
        expected_batch_sizes = [min(batch_size, 8 - start) for start in range(0, 8, batch_size)]
        for cancelled in (None, lambda: False):
            resample_calls.clear()
            adapter.fake_model.audio_calls.clear()
            if cancelled is None:
                vectors = adapter.embed_decoded_batch(decoded)
            else:
                vectors = adapter.embed_decoded_batch(decoded, cancelled=cancelled)

            assert len(resample_calls) == 1
            assert resample_calls[0].dtype == torch.float32
            torch.testing.assert_close(resample_calls[0], long_audio.float().unsqueeze(0))
            calls = adapter.fake_model.audio_calls
            assert [len(call) for call in calls] == expected_batch_sizes
            actual_windows = [waveform for call in calls for waveform in call]
            assert len(actual_windows) == 8
            for window, expected in zip(actual_windows, expected_windows, strict=True):
                # Staying within one native clip keeps upstream random cropping off.
                assert len(window) <= 480_000
                assert window.dtype == np.float32
                np.testing.assert_array_equal(window, expected)
            for vector, expected in zip(vectors, expected_vectors, strict=True):
                assert vector.shape == (512,)
                assert vector.dtype == np.float32
                assert np.linalg.norm(vector) == pytest.approx(1.0)
                np.testing.assert_allclose(vector, expected, rtol=1e-6, atol=1e-7)
                assert np.count_nonzero(vector[2:]) == 0
            assert adapter.last_batch_timing["windows"] == 8
            assert adapter.last_batch_timing["tracks"] == 3
            if reference_vectors is None:
                reference_vectors = vectors
            else:
                for vector, first in zip(vectors, reference_vectors, strict=True):
                    assert vector.tobytes() == first.tobytes()

        individual_vectors = [adapter.embed_decoded_batch([item])[0] for item in decoded]
        for vector, first in zip(individual_vectors, reference_vectors, strict=True):
            assert vector.tobytes() == first.tobytes()

    adapter = SharedAudioClapAdapter()
    monkeypatch.setattr(adapter, "_load_model", lambda: pytest.fail("Cancelled CLAP work loaded the model"))
    with pytest.raises(EmbeddingCancelledError):
        adapter.embed_decoded_batch(decoded, cancelled=lambda: True)
    assert not adapter.fake_model.audio_calls

    for batch_size, stop_after in ((2, 1), (2, 4), (8, 1)):
        adapter = SharedAudioClapAdapter()
        adapter.inference_batch_size = batch_size
        adapter.fake_torchaudio = types.SimpleNamespace(transforms=types.SimpleNamespace(Resample=FakeResampler))
        with pytest.raises(EmbeddingCancelledError):
            adapter.embed_decoded_batch(
                decoded,
                cancelled=lambda: len(adapter.fake_model.audio_calls) >= stop_after,
            )
        assert len(adapter.fake_model.audio_calls) == stop_after


def test_clap_rejects_native_audio_output_with_wrong_shape() -> None:
    adapter = SharedAudioClapAdapter()
    decoded = [
        DecodedAudio(
            path="a.wav",
            audio=torch.ones(48_000, dtype=torch.float32),
            sample_rate=48_000,
            detail="shared",
        )
    ]
    for shape in ((1, 3), (2, 512)):
        adapter.fake_model.output = np.ones(shape, dtype=np.float32)
        with pytest.raises(ValueError):
            adapter.embed_decoded_batch(decoded)


class FakeMuqAudioModel:
    def __init__(self) -> None:
        self.batch_shapes: list[tuple[int, ...]] = []
        self.batch_dtypes: list[torch.dtype] = []
        self.audio_calls: list[torch.Tensor] = []

    def __call__(self, wavs, *, output_hidden_states=True):
        assert output_hidden_states is True
        self.batch_shapes.append(tuple(wavs.shape))
        self.batch_dtypes.append(wavs.dtype)
        self.audio_calls.append(wavs.detach().cpu().clone())
        hidden = torch.zeros((wavs.shape[0], 2, 3), dtype=torch.float32, device=wavs.device)
        for index in range(wavs.shape[0]):
            first = int(wavs[index, 0].item())
            hidden[index, :, (first - 1) % hidden.shape[-1]] = 1.0 + abs(first) % 7
        return types.SimpleNamespace(last_hidden_state=hidden)


class SharedAudioMuqAdapter(MuqEmbeddingAdapter):
    def __init__(self, torchaudio_module=None) -> None:
        super().__init__(device="cpu", window_seconds=1.0, inference_batch_size=4)
        self.fake_model = FakeMuqAudioModel()
        self.fake_torchaudio = torchaudio_module

    def _load_model(self) -> None:
        self._torch = torch
        self._torchaudio = self.fake_torchaudio
        self.device = "cpu"
        self._model = self.fake_model


def test_muq_covers_each_track_with_consecutive_windows_and_preserves_pooling() -> None:
    sample_rate = 24_000
    window_size = sample_rate * 10
    long_audio = torch.arange(sample_rate * 301, dtype=torch.float64) / sample_rate + 1
    exact_audio = torch.arange(window_size * 2, dtype=torch.float32) / sample_rate + 100
    short_audio = torch.full((sample_rate // 2,), 2.0)
    decoded = [
        DecodedAudio(path="long.wav", audio=long_audio, sample_rate=sample_rate, detail="shared"),
        DecodedAudio(path="exact.wav", audio=exact_audio, sample_rate=sample_rate, detail="shared"),
        DecodedAudio(path="short.wav", audio=short_audio, sample_rate=sample_rate, detail="shared"),
    ]
    expected_track_windows = [
        [long_audio[start : start + window_size].float() for start in range(0, sample_rate * 300, window_size)]
        + [long_audio[-window_size:].float()],
        [exact_audio[:window_size], exact_audio[window_size:]],
        [torch.cat((short_audio, torch.zeros(window_size - short_audio.numel())))],
    ]
    expected_windows = [window for windows in expected_track_windows for window in windows]
    expected_vectors = []
    for windows in expected_track_windows:
        # Each synthetic model output is a scaled basis vector: window L2
        # normalization must remove that scale before track-level averaging.
        counts = np.bincount([(int(window[0]) - 1) % 3 for window in windows], minlength=3).astype(np.float32)
        expected_vectors.append(counts / np.linalg.norm(counts))

    reference_vectors = None
    for batch_size in (1, 8, 64):
        adapter = SharedAudioMuqAdapter()
        adapter.window_seconds = 10.0
        adapter.inference_batch_size = batch_size
        vectors = adapter.embed_decoded_batch(decoded)
        actual_windows = [window for batch in adapter.fake_model.audio_calls for window in batch]
        assert len(actual_windows) == 34
        for actual, expected in zip(actual_windows, expected_windows, strict=True):
            torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        assert adapter.fake_model.batch_shapes == [
            (min(batch_size, 34 - start), window_size) for start in range(0, 34, batch_size)
        ]
        assert all(dtype == torch.float32 for dtype in adapter.fake_model.batch_dtypes)
        for actual, expected in zip(vectors, expected_vectors, strict=True):
            assert actual.dtype == np.float32
            assert np.linalg.norm(actual) == pytest.approx(1.0)
            np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-7)
        if reference_vectors is None:
            reference_vectors = vectors
        else:
            for actual, reference in zip(vectors, reference_vectors, strict=True):
                np.testing.assert_array_equal(actual, reference)


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
        DecodedAudio(path="a.wav", audio=torch.ones(12_000), sample_rate=12_000, detail="shared"),
    ]

    vectors = adapter.embed_decoded_batch(decoded)

    assert vectors[0].tolist() == [1.0, 0.0, 0.0]
    assert resample_calls == [(12_000, 24_000, (1, 12000), torch.float32)]
    assert adapter.fake_model.batch_shapes == [(1, 24000)]
    assert adapter.fake_model.batch_dtypes == [torch.float32]


class FakeMulanModel:
    def __init__(self):
        self.audio_calls = []
        self.latent_calls = []
        self.text_calls = []
        self.sr, self.clip_secs, self.device = 24_000, 10, "cpu"
        self.mulan_module = self

    def _get_all_clips(self, audio):
        from muq import MuQMuLan

        self.audio_calls.append(audio.clone())
        return MuQMuLan._get_all_clips(self, audio)

    def get_audio_latents(self, wavs):
        self.latent_calls.append(wavs.clone())
        vector = torch.zeros((len(wavs), 512), dtype=torch.float32, device=wavs.device)
        vector[:, 0] = wavs[:, 0] * 9 + 2
        vector[:, 1] = wavs.mean(dim=1) + 5
        return torch.nn.functional.normalize(vector, dim=1)

    def __call__(self, *, wavs=None, texts=None, parallel_processing=None):
        if wavs is not None:
            from muq import MuQMuLan

            return MuQMuLan.extract_audio_latents(self, wavs, parallel_processing=parallel_processing)
        if texts is not None:
            assert len(texts) == 1
            self.text_calls.append(list(texts))
            return torch.tensor([[5.0] + [0.0] * 511], dtype=torch.float32)
        raise AssertionError("MuQ-MuLan adapter must provide audio or text input")


class SharedAudioMulanAdapter(MuqMulanEmbeddingAdapter):
    def __init__(self):
        super().__init__(device="cpu")
        self.fake_model = FakeMulanModel()
        self.fake_torchaudio = None

    def _load_model(self) -> None:
        self._torch = torch
        self._torchaudio = self.fake_torchaudio
        self.device = "cpu"
        self._model = self.fake_model


def test_mulan_adapter_forwards_full_tracks_and_normalizes_audio_and_text(monkeypatch) -> None:
    adapter = SharedAudioMulanAdapter()
    resample_calls = []

    class FakeResampler:
        def __init__(self, source_rate, target_rate):
            assert (source_rate, target_rate) == (12_000, 24_000)

        def __call__(self, waveform):
            resample_calls.append(waveform.clone())
            return waveform.repeat_interleave(2, dim=-1)

    adapter.fake_torchaudio = types.SimpleNamespace(
        transforms=types.SimpleNamespace(Resample=FakeResampler),
    )
    monkeypatch.setattr(embedding_audio, "_RESAMPLERS", {})
    monkeypatch.setattr(
        torch,
        "from_numpy",
        lambda _audio: (_ for _ in ()).throw(
            AssertionError("MuQ-MuLan must keep TorchCodec audio as tensors")
        ),
    )

    long_audio = torch.linspace(-1.0, 1.0, 639_000, dtype=torch.float64)
    short_audio = torch.linspace(0.0, 0.5, 24_001, dtype=torch.float32)
    decoded = [
        DecodedAudio(
            path="long-mulan.wav",
            audio=long_audio,
            sample_rate=12_000,
            detail="shared",
        ),
        DecodedAudio(
            path="short-mulan.wav",
            audio=short_audio,
            sample_rate=24_000,
            detail="shared",
        ),
    ]
    reference = FakeMulanModel()
    expected_audio = [long_audio.float().repeat_interleave(2), short_audio]
    with torch.inference_mode():
        expected_vectors = [reference(wavs=waveform.unsqueeze(0), parallel_processing=False)[0].numpy() for waveform in expected_audio]
    expected_vectors = [vector / np.linalg.norm(vector) for vector in expected_vectors]
    for batch_size in (1, 2, 4, 16):
        adapter.inference_batch_size = batch_size
        adapter.fake_model = FakeMulanModel()
        resample_calls.clear()
        audio_vectors = adapter.embed_decoded_batch(decoded)
        assert len(resample_calls) == 1
        torch.testing.assert_close(resample_calls[0], long_audio.float().unsqueeze(0))
        expected_sizes = {1: [1] * 7, 2: [2, 2, 2, 1], 4: [4, 2, 1], 16: [6, 1]}
        assert [len(batch) for batch in adapter.fake_model.latent_calls] == expected_sizes[batch_size]
        for actual, full in zip(adapter.fake_model.audio_calls, expected_audio, strict=True):
            torch.testing.assert_close(actual, full)
        for actual, expected in zip(audio_vectors, expected_vectors, strict=True):
            np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-6)
    text_vector = adapter.embed_text("rolling techno")
    bank_vectors = adapter.embed_texts(["rolling techno", "ambient"])

    assert adapter.fake_model.text_calls == [["rolling techno"], ["rolling techno"], ["ambient"]]
    for vector in audio_vectors + [text_vector] + bank_vectors:
        assert vector.shape == (512,)
        assert vector.dtype == np.float32
        assert np.linalg.norm(vector) == pytest.approx(1.0)
    for vector in audio_vectors:
        assert np.count_nonzero(vector[2:]) == 0
    np.testing.assert_array_equal(text_vector, bank_vectors[0])


class FakeMertV2Processor:
    sampling_rate = 24_000

    def __init__(self) -> None:
        self.batches: list[list[int]] = []

    def __call__(self, window_batch, *, sampling_rate, padding, return_tensors):
        assert sampling_rate == self.sampling_rate
        assert padding is False
        assert return_tensors == "pt"
        assert len({len(window) for window in window_batch}) == 1
        self.batches.append([len(window) for window in window_batch])
        values = torch.from_numpy(np.stack(window_batch))
        return {
            "input_values": values,
            "attention_mask": torch.ones_like(values, dtype=torch.long),
        }


def test_mert_v2_full_coverage_pools_all_valid_layer_frames(monkeypatch) -> None:
    chunk_samples = 9600
    monkeypatch.setattr(embedding_mert_v2, "_CHUNK_SAMPLES", chunk_samples)
    monkeypatch.setattr(embedding_audio, "_RESAMPLERS", {})
    resample_calls = []

    class FakeResampler:
        def __init__(self, source_rate, target_rate):
            assert (source_rate, target_rate) == (12_000, 24_000)

        def __call__(self, waveform):
            resample_calls.append(waveform.clone())
            return waveform.repeat_interleave(2, dim=-1)

    class FakeModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.calls = []
            self.empty_mask = False
            self.invalid_output = None

        def forward(self, input_values, attention_mask, *, output_hidden_states, return_dict):
            assert torch.is_inference_mode_enabled()
            assert input_values.dtype == torch.float32
            assert output_hidden_states is True and return_dict is True
            assert torch.all(attention_mask == 1)
            self.calls.append(input_values.clone())
            frames = input_values.shape[1] // 960
            hidden = torch.zeros((len(input_values), frames + 1, 1024))
            hidden[:, :frames, 0] = input_values.mean(dim=1)[:, None]
            hidden[:, :frames, 1] = 1.0
            hidden[:, frames, :] = 100_000.0  # Poison the padded output frame.
            mask = torch.zeros(hidden.shape[:2], dtype=torch.bool)
            if not self.empty_mask:
                mask[:, :frames] = True
            states = [hidden.clone() for _ in range(23)] + [hidden]
            for layer, state in enumerate(states[:-1], 1):
                state[:, :frames, 2] = (24 - layer) / 24
            if self.invalid_output == "nonfinite":
                states[0][:, 0, 0] = torch.nan
            elif self.invalid_output == "zero":
                states[0][:, :frames, :] = 0
            elif self.invalid_output == "missing_layer":
                states.pop(0)
            elif self.invalid_output == "wrong_layer_shape":
                states[0] = states[0][:, :, :768]
            return types.SimpleNamespace(
                last_hidden_state=hidden,
                hidden_states=tuple(states),
                feature_attention_mask=mask,
            )

    def make_adapter():
        adapter = MertV2EmbeddingAdapter(device="cpu", inference_batch_size=2)
        adapter.load_calls = 0
        model = FakeModel()

        def load():
            adapter.load_calls += 1
            adapter._torch = torch
            adapter._torchaudio = types.SimpleNamespace(transforms=types.SimpleNamespace(Resample=FakeResampler))
            adapter._model = model
            adapter._processor = FakeMertV2Processor()
            adapter.device = "cpu"

        monkeypatch.setattr(adapter, "_load_model", load)
        return adapter, model

    long_audio = torch.linspace(-0.5, 0.9, 2 * chunk_samples + 1)
    resample_audio = torch.linspace(0.2, 0.6, 1700, dtype=torch.float64)
    short_audio = torch.full((1025,), 0.3)
    decoded = [
        DecodedAudio(path="long.wav", audio=long_audio, sample_rate=24_000, detail="shared"),
        DecodedAudio(path="resampled.wav", audio=resample_audio, sample_rate=12_000, detail="shared"),
        DecodedAudio(path="short.wav", audio=short_audio, sample_rate=24_000, detail="shared"),
    ]
    expected_chunks = [
        [long_audio[:chunk_samples], long_audio[chunk_samples:-1025], long_audio[-1025:]],
        [resample_audio.float().repeat_interleave(2)],
        [short_audio],
    ]
    adapter, model = make_adapter()
    layer_vectors = adapter.embed_decoded_layers_batch(decoded)
    vectors = [layers[-1] for layers in layer_vectors]
    assert len(vectors) == len(decoded)
    assert len(resample_calls) == 1
    torch.testing.assert_close(resample_calls[0], resample_audio.float().unsqueeze(0), rtol=0, atol=0)
    observed_chunks = [chunk for batch in model.calls for chunk in batch]
    expected_flat = [chunk for chunks in expected_chunks for chunk in chunks]
    assert all(1025 <= chunk.numel() <= chunk_samples for chunk in observed_chunks)
    assert len(observed_chunks) == len(expected_flat)
    for actual, expected in zip(observed_chunks, expected_flat, strict=True):
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)
    for layers, chunks in zip(layer_vectors, expected_chunks, strict=True):
        counts = [chunk.numel() // 960 for chunk in chunks]
        assert len(layers) == 24
        for layer, vector in enumerate(layers, 1):
            expected = np.zeros(1024, dtype=np.float64)
            expected[0] = np.average([chunk.double().mean().item() for chunk in chunks], weights=counts)
            expected[1] = 1.0
            expected[2] = (24 - layer) / 24
            expected /= np.linalg.norm(expected)
            assert vector.dtype == np.float32
            np.testing.assert_allclose(vector, expected, rtol=1e-5, atol=1e-6)
            assert np.linalg.norm(vector) == pytest.approx(1.0)

    legacy_adapter, _ = make_adapter()
    legacy_vector = legacy_adapter.embed_decoded_batch([decoded[-1]])[0]
    np.testing.assert_array_equal(legacy_vector, vectors[-1])

    for audio in (torch.empty(0), torch.ones(1024), torch.full((1025,), torch.nan)):
        invalid = DecodedAudio(path="invalid.wav", audio=audio, sample_rate=24_000, detail="shared")
        with pytest.raises(ValueError):
            adapter.embed_decoded_batch([invalid])
    model.empty_mask = True
    with pytest.raises(ValueError, match="no valid frames"):
        adapter.embed_decoded_batch([decoded[-1]])
    model.empty_mask = False
    for model.invalid_output in ("nonfinite", "zero", "missing_layer", "wrong_layer_shape"):
        with pytest.raises(ValueError):
            adapter.embed_decoded_batch([decoded[-1]])

    adapter, model = make_adapter()
    with pytest.raises(EmbeddingCancelledError):
        adapter.embed_decoded_batch(decoded, cancelled=lambda: True)
    assert adapter.load_calls == 0 and not model.calls
    with pytest.raises(EmbeddingCancelledError):
        adapter.embed_decoded_batch([decoded[0]], cancelled=lambda: bool(model.calls))
    assert len(model.calls) == 1
    adapter, model = make_adapter()
    resample_calls.clear()
    with pytest.raises(EmbeddingCancelledError):
        adapter.embed_decoded_batch([decoded[1]], cancelled=lambda: bool(resample_calls))
    assert len(resample_calls) == 1 and not model.calls


class MovableModule(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.devices: list[str] = []

    def to(self, device: str):
        self.devices.append(device)
        return self


class FakeMaestHead(torch.nn.Module):
    def forward(self, embeddings):
        return self.logits


class FakeMaestModel(torch.nn.Module):
    labels = ["A", "B", "C"] + [f"label-{index}" for index in range(3, 519)]

    def __init__(self) -> None:
        super().__init__()
        self.head = FakeMaestHead()
        self.audio_calls = []
        self.predict_calls = 0
        self.feature_calls = []
        self.feature_error = None
        self.prediction_error = None
        self.prediction_labels = list(self.labels)
        self.melspectrogram: MovableModule | None = None
        self.init_calls = 0
        self.outputs = []
        self.predictions = []
        for logits, embeddings in (
            ([[0., 4., 1.], [1., 0., 2.]], [[3., 0.], [0., 4.]]),
            ([[3., 1., 0.], [2., 1., 0.], [1., 1., 0.]], [[1., 0.], [2., 4.], [3., 2.]]),
            ([[1., 0., 0.]] * 4, [[1., 2.], [2., 1.], [1., 3.], [3., 2.]]),
        ):
            scores = torch.full((len(logits), 519), -10., dtype=torch.float32)
            scores[:, :3] = torch.tensor(logits)
            vectors = torch.zeros((len(embeddings), 768), dtype=torch.float32)
            vectors[:, :2] = torch.tensor(embeddings)
            self.outputs.append((scores, vectors))
        self.predictions = [torch.sigmoid(scores).mean(dim=0).numpy() for scores, _ in self.outputs]

    def init_melspectrogram(self) -> None:
        self.init_calls += 1
        self.melspectrogram = MovableModule()

    def forward(self, audio, *, melspectrogram_input=False):
        assert audio.ndim == 1, "MAEST native API requires one full 1D waveform"
        assert audio.dtype == torch.float32
        assert melspectrogram_input is False
        assert torch.is_inference_mode_enabled()
        logits, embeddings = self.outputs[len(self.audio_calls)]
        self.audio_calls.append(audio.clone())
        cls, dist = self.forward_features(embeddings, transformer_block=-1, return_self_attention=False)
        embeddings = (cls + dist) / 2
        self.head.logits = logits
        return self.head(embeddings), embeddings

    def forward_features(self, blocks, *, transformer_block, return_self_attention):
        assert transformer_block == -1 and return_self_attention is False
        self.feature_calls.append(len(blocks))
        if self.feature_error is not None:
            raise self.feature_error
        return blocks, blocks

    def predict_labels(self, audio):
        self.predict_calls += 1
        self.forward(audio)
        if self.prediction_error is not None:
            raise self.prediction_error
        return self.predictions[len(self.audio_calls) - 1], self.prediction_labels


class BatchMaestAdapter(MaestEmbeddingAdapter):
    def __init__(self) -> None:
        super().__init__(device="cpu", top_k=2)
        self.fake_model = FakeMaestModel()
        self.fake_torchaudio = None

    def _load_model(self) -> None:
        self._torch = torch
        self._torchaudio = self.fake_torchaudio
        self.device = "cpu"
        self._model = self.fake_model


def test_maest_analyze_decoded_batch_returns_genres_and_embeddings() -> None:
    decoded = [
        DecodedAudio(path="a.wav", audio=torch.ones(16_000 * 6), sample_rate=16_000, detail="shared"),
        DecodedAudio(path="b.wav", audio=torch.ones(16_000 * 65), sample_rate=16_000, detail="shared"),
    ]

    for batch_size in (1, 2, 8):
        adapter = BatchMaestAdapter()
        adapter.inference_batch_size = batch_size
        original_features = adapter.fake_model.forward_features
        results = adapter.analyze_decoded_batch(decoded)

        assert len(results) == 2
        assert [[genre["label"] for genre in result.genres] for result in results] == [["C", "B"], ["A", "B"]]
        assert adapter.fake_model.predict_calls == len(adapter.fake_model.audio_calls) == 2
        assert max(adapter.fake_model.feature_calls) <= batch_size
        assert sum(adapter.fake_model.feature_calls) == 5
        assert adapter.fake_model.forward_features == original_features
        assert not adapter.fake_model.head._forward_hooks
        for result, (_, embeddings), expected_scores in zip(
            results, adapter.fake_model.outputs, adapter.fake_model.predictions,
        ):
            for genre in result.genres:
                assert genre["score"] == pytest.approx(expected_scores[adapter.fake_model.labels.index(genre["label"])])
            mean_embedding = embeddings.mean(dim=0).numpy()
            expected_embedding = mean_embedding / np.linalg.norm(mean_embedding)
            assert result.embedding.shape == (768,)
            assert result.embedding.dtype == np.float32
            np.testing.assert_allclose(result.embedding, expected_embedding)


def test_maest_analyze_decoded_batch_rejects_invalid_native_outputs(monkeypatch) -> None:
    decoded = [DecodedAudio(path="invalid.wav", audio=torch.ones(16_000 * 6), sample_rate=16_000, detail="shared")]
    invalid_outputs = [
        (torch.ones(519), torch.ones(768)),
        (torch.ones((1, 2, 519)), torch.ones((1, 2, 768))),
        (torch.ones((2, 519)), torch.ones((2, 767))),
        (torch.ones((2, 518)), torch.ones((2, 768))),
        (torch.ones((2, 519)), torch.ones((3, 768))),
        (torch.ones((0, 519)), torch.ones((0, 768))),
        (torch.full((2, 519), torch.nan), torch.ones((2, 768))),
        (torch.ones((2, 519)), torch.full((2, 768), torch.inf)),
        (torch.ones((2, 519)), torch.zeros((2, 768))),
    ]
    for output in invalid_outputs:
        adapter = BatchMaestAdapter()
        adapter.fake_model.outputs = [output]
        with pytest.raises(ValueError):
            adapter.analyze_decoded_batch(decoded)
        assert not adapter.fake_model.head._forward_hooks

    for scores in (
        np.ones((1, 519)), np.ones(518), np.full(519, np.nan),
        np.full(519, np.inf), np.full(519, 1.1), np.full(519, -0.1),
    ):
        adapter = BatchMaestAdapter()
        adapter.fake_model.predictions[0] = scores
        with pytest.raises(ValueError):
            adapter.analyze_decoded_batch(decoded)
        assert not adapter.fake_model.head._forward_hooks

    for labels in (FakeMaestModel.labels[:-1], list(reversed(FakeMaestModel.labels))):
        adapter = BatchMaestAdapter()
        adapter.fake_model.prediction_labels = labels
        with pytest.raises(ValueError):
            adapter.analyze_decoded_batch(decoded)
        assert not adapter.fake_model.head._forward_hooks

    adapter = BatchMaestAdapter()
    original_features = adapter.fake_model.forward_features
    adapter.fake_model.feature_error = RuntimeError("native features failed")
    with pytest.raises(RuntimeError, match="native features failed"):
        adapter.analyze_decoded_batch(decoded)
    assert adapter.fake_model.forward_features == original_features
    assert not adapter.fake_model.head._forward_hooks

    adapter = BatchMaestAdapter()
    original_features = adapter.fake_model.forward_features
    adapter.fake_model.prediction_error = RuntimeError("native prediction failed")
    with pytest.raises(RuntimeError, match="native prediction failed"):
        adapter.analyze_decoded_batch(decoded, include_mel_spectrogram=True)
    assert not adapter.fake_model.head._forward_hooks
    assert not adapter.fake_model.melspectrogram._forward_hooks
    assert adapter.fake_model.forward_features == original_features
    adapter.fake_model.prediction_error = None
    assert len(adapter.analyze_decoded_batch(decoded)) == 1
    assert adapter.fake_model.predict_calls == len(adapter.fake_model.audio_calls) == 2
    assert not adapter.fake_model.head._forward_hooks

    def registration_failed(*args, **kwargs):
        raise RuntimeError("mel hook registration failed")

    with monkeypatch.context() as patch:
        patch.setattr(adapter.fake_model.melspectrogram, "register_forward_hook", registration_failed)
        with pytest.raises(RuntimeError, match="mel hook registration failed"):
            adapter.analyze_decoded_batch(decoded, include_mel_spectrogram=True)
    assert not adapter.fake_model.head._forward_hooks
    assert not adapter.fake_model.melspectrogram._forward_hooks
    assert adapter.fake_model.forward_features == original_features


def test_maest_analyze_decoded_batch_forwards_full_resampled_audio(monkeypatch) -> None:
    adapter = BatchMaestAdapter()
    resample_calls = []

    class FakeResampler:
        def __init__(self, source_rate, target_rate):
            assert (source_rate, target_rate) == (8_000, 16_000)

        def __call__(self, waveform):
            resample_calls.append(waveform.clone())
            return waveform.repeat_interleave(2, dim=-1)

    adapter.fake_torchaudio = types.SimpleNamespace(transforms=types.SimpleNamespace(Resample=FakeResampler))
    monkeypatch.setattr(embedding_audio, "_RESAMPLERS", {})
    inputs = [
        torch.linspace(-0.3, 0.4, 8_000 * 6, dtype=torch.float64),
        torch.linspace(-0.5, 0.6, 16_000 * 30),
        torch.linspace(-0.7, 0.8, 16_000 * 65),
    ]
    decoded = [
        DecodedAudio(path=f"{index}.wav", audio=audio, sample_rate=rate, detail="shared")
        for index, (audio, rate) in enumerate(zip(inputs, [8_000, 16_000, 16_000]))
    ]

    results = adapter.analyze_decoded_batch(decoded)

    assert len(resample_calls) == 1
    torch.testing.assert_close(resample_calls[0].reshape(-1), inputs[0].float())
    assert len(adapter.fake_model.audio_calls) == len(results) == 3
    expected = [inputs[0].float().repeat_interleave(2), inputs[1], inputs[2]]
    for actual, full in zip(adapter.fake_model.audio_calls, expected):
        torch.testing.assert_close(actual, full)
