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
import dj_track_similarity.embedding.mulan as embedding_mulan
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
        # State k is a scaled basis vector rotated by k, so every layer differs.
        states = torch.zeros((13, wavs.shape[0], 2, 3), dtype=torch.float32, device=wavs.device)
        for index in range(wavs.shape[0]):
            first = int(wavs[index, 0].item())
            for layer in range(13):
                states[layer, index, :, (first - 1 + layer) % 3] = 1.0 + abs(first) % 7
        return types.SimpleNamespace(last_hidden_state=states[-1], hidden_states=tuple(states))


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
    expected_layers = []
    for windows in expected_track_windows:
        # Each synthetic model output is a scaled basis vector: window L2
        # normalization must remove that scale before track-level averaging.
        counts = np.bincount([(int(window[0]) - 1) % 3 for window in windows], minlength=3).astype(np.float32)
        expected_layers.append([np.roll(counts, layer) / np.linalg.norm(counts) for layer in range(13)])

    reference_layers = None
    for batch_size in (1, 8, 64):
        adapter = SharedAudioMuqAdapter()
        adapter.window_seconds = 10.0
        adapter.inference_batch_size = batch_size
        track_layers = adapter.embed_decoded_layers_batch(decoded)
        actual_windows = [window for batch in adapter.fake_model.audio_calls for window in batch]
        assert len(actual_windows) == 34
        for actual, expected in zip(actual_windows, expected_windows, strict=True):
            torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        assert adapter.fake_model.batch_shapes == [
            (min(batch_size, 34 - start), window_size) for start in range(0, 34, batch_size)
        ]
        assert all(dtype == torch.float32 for dtype in adapter.fake_model.batch_dtypes)
        for layers, expected in zip(track_layers, expected_layers, strict=True):
            assert len(layers) == 13
            for actual, expected_layer in zip(layers, expected, strict=True):
                assert actual.dtype == np.float32
                assert np.linalg.norm(actual) == pytest.approx(1.0)
                np.testing.assert_allclose(actual, expected_layer, rtol=1e-6, atol=1e-7)
        if reference_layers is None:
            reference_layers = track_layers
        else:
            for layers, reference in zip(track_layers, reference_layers, strict=True):
                for actual, expected_layer in zip(layers, reference, strict=True):
                    np.testing.assert_array_equal(actual, expected_layer)

    # The single-vector call returns layer 13, the last hidden state.
    adapter = SharedAudioMuqAdapter()
    adapter.window_seconds = 10.0
    for actual, layers in zip(adapter.embed_decoded_batch(decoded), reference_layers, strict=True):
        np.testing.assert_array_equal(actual, layers[-1])
    adapter = SharedAudioMuqAdapter()
    with pytest.raises(EmbeddingCancelledError):
        adapter.embed_decoded_layers_batch(decoded, cancelled=lambda: bool(adapter.fake_model.audio_calls))
    assert len(adapter.fake_model.audio_calls) == 1


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
        self.text_error = None
        self.text_output = None
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
            if self.text_error is not None:
                raise self.text_error
            if self.text_output is not None:
                return self.text_output
            digest = hashlib.sha256(texts[0].encode()).digest()
            return torch.tensor([[float(value + 1) for value in digest] + [0.0] * 480])
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


def test_job_prepared_audio_is_what_each_adapter_would_resample_itself() -> None:
    """Analysis jobs resample once per rate off the models' thread and hand the
    result to every model reading that rate; each must read the same samples."""
    torchaudio = pytest.importorskip("torchaudio")
    from dj_track_similarity.analysis.job_batch import prepare_model_audio

    seconds = torch.arange(44_100 * 3, dtype=torch.float32) / 44_100
    native = DecodedAudio(
        path="track.wav",
        audio=0.4 * torch.sin(2 * torch.pi * 440 * seconds) + 0.1 * torch.sin(2 * torch.pi * 9_000 * seconds),
        sample_rate=44_100,
        detail="test",
    )
    prepared = prepare_model_audio(native, {16_000, 24_000}).by_rate
    assert (prepared[16_000].sample_rate, prepared[24_000].sample_rate) == (16_000, 24_000)

    maest = MaestEmbeddingAdapter(device="cpu")
    maest._torch, maest._torchaudio = torch, torchaudio
    assert torch.equal(
        maest._prepare_audio_from_decoded(prepared[16_000]),
        maest._prepare_audio_from_decoded(native),
    )

    def muq_windows(decoded: DecodedAudio) -> list:
        return embedding_audio._prepare_windows(
            [decoded],
            target_rate=24_000,
            window_seconds=1.0,
            torch=torch,
            torchaudio=torchaudio,
            model_label="MuQ",
        )[1]

    own = muq_windows(native)
    assert len(own) == 3
    assert all(torch.equal(given, expected) for given, expected in zip(muq_windows(prepared[24_000]), own, strict=True))


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
    expected_text = text_vector.copy()
    text_vector[:] = 0
    bank_vectors = adapter.embed_texts(["rolling techno", "ambient", "rolling techno", "ambient"])

    assert adapter.fake_model.text_calls == [["rolling techno"], ["ambient"]]
    for vector in audio_vectors + bank_vectors:
        assert vector.shape == (512,)
        assert vector.dtype == np.float32
        assert np.linalg.norm(vector) == pytest.approx(1.0)
    for vector in audio_vectors:
        assert np.count_nonzero(vector[2:]) == 0
    np.testing.assert_array_equal(expected_text, bank_vectors[0])
    np.testing.assert_array_equal(expected_text, bank_vectors[2])
    np.testing.assert_array_equal(bank_vectors[1], bank_vectors[3])
    assert not np.array_equal(bank_vectors[0], bank_vectors[1])
    bank_vectors[0][:] = 0
    np.testing.assert_array_equal(expected_text, bank_vectors[2])
    np.testing.assert_array_equal(expected_text, adapter.embed_text("rolling techno"))
    np.testing.assert_array_equal(bank_vectors[1], adapter.embed_texts(["ambient"])[0])

    variants = ["Rolling techno", " rolling techno "]
    for prompt, vector in zip(variants, adapter.embed_texts(variants), strict=True):
        assert not np.array_equal(expected_text, vector)
        assert adapter.fake_model.text_calls.count([prompt]) == 1
    assert adapter.fake_model.text_calls.count(["rolling techno"]) == 1

    with monkeypatch.context() as patch:
        patch.setattr(embedding_mulan, "_TEXT_VECTOR_CACHE_SIZE", 2)
        bounded = SharedAudioMulanAdapter()
        bounded.embed_texts(["A", "B", "A", "C", "A", "B"])
        assert bounded.fake_model.text_calls == [["A"], ["B"], ["C"], ["B"]]

    for prompt, failure in [("failed", RuntimeError("text failed")), ("invalid", None)]:
        adapter.fake_model.text_error = failure
        adapter.fake_model.text_output = torch.zeros((1, 512)) if failure is None else None
        with pytest.raises(RuntimeError if failure is not None else ValueError):
            adapter.embed_text(prompt)
        adapter.fake_model.text_error = adapter.fake_model.text_output = None
        recovered = adapter.embed_text(prompt)
        np.testing.assert_array_equal(recovered, adapter.embed_text(prompt))
        assert adapter.fake_model.text_calls.count([prompt]) == 2
    np.testing.assert_array_equal(expected_text, adapter.embed_text("rolling techno"))
    assert adapter.fake_model.text_calls.count(["rolling techno"]) == 1

    empty = SharedAudioMulanAdapter()
    monkeypatch.setattr(empty, "_load_model", lambda: pytest.fail("Empty text bank loaded a model"))
    assert empty.embed_texts([]) == []


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


class FakeMaestBlock(torch.nn.Module):
    def __init__(self, number: int) -> None:
        super().__init__()
        self.number = number

    def forward(self, tokens):
        # Only patch tokens change, so the head input stays the CLS/DIST mean.
        tokens = tokens.clone()
        tokens[:, 2:, 10 + self.number] += 1.0 + self.number
        return tokens


class FakeMaestModel(torch.nn.Module):
    labels = ["A", "B", "C"] + [f"label-{index}" for index in range(3, 519)]

    def __init__(self) -> None:
        super().__init__()
        self.head = FakeMaestHead()
        self.blocks = torch.nn.Sequential(*(FakeMaestBlock(number) for number in range(1, 13)))
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
        if blocks.ndim != 2:
            return blocks, blocks
        # CLS and DIST carry the head input; the two patch tokens average to twice it.
        tokens = self.blocks(torch.stack((blocks, blocks, blocks, 3 * blocks), dim=1))
        return tokens[:, 0], tokens[:, 1]

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
        assert not any(block._forward_hooks for block in adapter.fake_model.blocks)
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
            # Layers 1-12 are each block's patch-token mean over the track; 13 is the head input.
            assert len(result.layer_embeddings) == 13
            np.testing.assert_array_equal(result.layer_embeddings[-1], result.embedding)
            for number, layer in enumerate(result.layer_embeddings[:-1], start=1):
                expected_block = 2 * mean_embedding
                expected_block[11 : 11 + number] += np.arange(2, number + 2)
                assert layer.shape == (768,) and layer.dtype == np.float32
                np.testing.assert_allclose(layer, expected_block / np.linalg.norm(expected_block), rtol=1e-6)


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


def test_sheetsage2_encoder_pooling_preserves_native_memory_and_bart_cache(monkeypatch, tmp_path) -> None:
    import copy
    import json
    from contextlib import nullcontext
    from safetensors.torch import save_file, save_model
    import dj_track_similarity.embedding.sheetsage2_runtime as runtime
    from dj_track_similarity.embedding.sheetsage2_runtime import (
        SheetSage2Runtime, accepted_frame_weights, sliding_window_plan,
    )

    config = dict(
        backbone_config=dict(hidden_size=4, num_hidden_layers=24), lora_rank=2, lora_alpha=4,
        hidden_size=8, vocab_size=20, max_output_seq_len=32, decoder_layers=1,
        num_attention_heads=2, intermediate_size=16, decoder_dropout=0.0,
        pad_token_id=0, bos_token_id=1, eos_token_id=2, input_audio_length=0.48, sampling_rate=100,
    )
    model = SheetSage2Runtime(config, types.SimpleNamespace(pad_token=0)).eval()

    class Layer(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.attn = torch.nn.Module()
            for name in ("query_proj", "key_proj", "value_proj", "out_proj"):
                setattr(self.attn, name, torch.nn.Linear(4, 4))

        def forward(self, hidden, positions):
            return hidden + 1.0

    class Subsample(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.convnext_layers = [types.SimpleNamespace(
                depthwise_block=[None, types.SimpleNamespace(weight=torch.zeros(1))],
            )]

        def forward(self, mel):
            return mel

    class Encoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.config = types.SimpleNamespace(minimum_input_samples=1, inputs_to_logits_ratio=4)
            self.layers = torch.nn.ModuleList([Layer() for _ in range(24)])
            self.subsampling_module = torch.nn.Sequential(Subsample())
            self.calls = 0
            self.register_buffer("window", torch.arange(9, dtype=torch.float32)[1:])

        def feature_extractor(self, audio):
            self.calls += 1
            assert audio.shape[1] == 48
            assert torch.count_nonzero(audio[:, 43:]) == 0
            return torch.arange(48, dtype=torch.float32).reshape(1, 12, 4).repeat(audio.shape[0], 1, 1)

        def embed_positions(self, hidden):
            return None

    ordinary_mert = Encoder()
    model.encoder = copy.deepcopy(ordinary_mert)
    original_weight = ordinary_mert.layers[0].attn.query_proj.weight.detach().clone()
    expected_delta = (model.adapter.layers[0].attn.query_proj.lora_B.weight
                      @ model.adapter.layers[0].attn.query_proj.lora_A.weight) * 2.0
    model.merge_lora()
    torch.testing.assert_close(model.encoder.layers[0].attn.query_proj.weight, original_weight + expected_delta)
    torch.testing.assert_close(ordinary_mert.layers[0].attn.query_proj.weight, original_weight)
    assert model.adapter is None

    with torch.inference_mode():
        memory, sums, weight = model.encode_and_pool(
            torch.ones(1, 43), window_start=0.0, accept_start=0.015, accept_end=0.415,
        )
        assert model.encoder.calls == 1
        frame_weights = accepted_frame_weights(12, 0.04, 0, 0.015, 0.415, 0.43)
        assert weight == pytest.approx(0.4)
        assert frame_weights[0] == pytest.approx(0.025)
        assert frame_weights[10] == pytest.approx(0.015)
        assert frame_weights[11] == 0
        base = torch.arange(48, dtype=torch.float32).reshape(1, 12, 4)
        states = [base + index for index in range(25)]
        native_mixed = sum(state * part for state, part in zip(states, model.layer_weight.softmax(0)))
        torch.testing.assert_close(memory, model.encoder_projection(native_mixed), rtol=0, atol=0)
        expected = np.stack([((base[0].numpy() + index) * frame_weights[:, None]).sum(0)
                             for index in range(1, 25)])
        np.testing.assert_allclose(sums, expected, rtol=1e-6, atol=1e-6)
        assert sums.shape == (24, 4)
        batch_memory, batch_sums, batch_weights, valid = model.encode_and_pool_batch(
            torch.ones(2, 43), window_starts=[0.0, 0.2], accept_starts=[0.015, 0.415],
            accept_ends=[0.415, 0.63], sample_lengths=[43, 43],
        )
        assert model.encoder.calls == 2
        assert valid.tolist() == [True, True]
        np.testing.assert_allclose(batch_sums[0], sums)
        assert batch_weights.tolist() == pytest.approx([0.4, 0.215])
        torch.testing.assert_close(batch_memory[0], memory[0])
        assert model.token_embedding.weight is model.decoder.embed_tokens.weight
        assert model.token_embedding.weight is model.output_projection.weight
        full, _ = model.decode(memory, torch.tensor([[1, 3, 4]]), use_cache=False)
        native_logits, _ = model.decode(model.encoder_projection(native_mixed), torch.tensor([[1, 3, 4]]), use_cache=False)
        torch.testing.assert_close(full, native_logits, rtol=0, atol=0)
        _, cache = model.decode(memory, torch.tensor([[1, 3]]), use_cache=True)
        assert cache is not None
        last, _ = model.decode(memory, torch.tensor([[4]]), use_cache=True, past_key_values=cache)
        torch.testing.assert_close(last[:, -1], full[:, -1], rtol=1e-5, atol=1e-5)
        # Left-padded prefixes retain each row's native learned positions, including
        # cached advancement after another row has completed and been removed.
        batch_memory = memory.repeat(2, 1, 1)
        ids = torch.tensor([[0, 1, 3], [1, 5, 6]])
        mask = ids != 0
        positions = (mask.long().cumsum(1) - 1).clamp_min(0)
        batched, cache = model.decode(batch_memory, ids, use_cache=True,
                                      attention_mask=mask, position_ids=positions)
        single, _ = model.decode(memory, torch.tensor([[1, 3]]))
        torch.testing.assert_close(batched[0, -1], single[0, -1], rtol=1e-5, atol=1e-5)
        single2, _ = model.decode(memory, torch.tensor([[1, 5, 6]]))
        torch.testing.assert_close(batched[1, -1], single2[0, -1], rtol=1e-5, atol=1e-5)
        mask = torch.cat((mask, torch.ones(2, 1, dtype=torch.bool)), dim=1)
        cached, cache = model.decode(batch_memory, torch.tensor([[4], [7]]), use_cache=True,
                                     past_key_values=cache, attention_mask=mask,
                                     position_ids=mask.long().sum(1, keepdim=True) - 1)
        torch.testing.assert_close(cached[0, -1], full[0, -1], rtol=1e-5, atol=1e-5)
        cache.batch_select_indices(torch.tensor([0]))
        mask = torch.cat((mask[:1], torch.ones(1, 1, dtype=torch.bool)), dim=1)
        pruned, _ = model.decode(memory, torch.tensor([[8]]), use_cache=True, past_key_values=cache,
                                attention_mask=mask, position_ids=torch.tensor([[3]]))
        single, _ = model.decode(memory, torch.tensor([[1, 3, 4, 8]]))
        torch.testing.assert_close(pruned[0, -1], single[0, -1], rtol=1e-5, atol=1e-5)
        last_only, _ = model.decode(memory, torch.tensor([[1, 3, 4, 8]]), last_logits_only=True)
        torch.testing.assert_close(last_only[:, -1], single[:, -1], rtol=1e-5, atol=1e-5)
        class Grammar:
            def __init__(self, tokenizer):
                self.count = 0

            def update(self, token):
                self.count += 1
                return token == 2

            def allowed(self, device):
                allowed = torch.zeros(20, dtype=torch.bool, device=device)
                allowed[10 if self.count == 0 else 5 if self.count == 1 else 2] = True
                return allowed

        model.tokenizer = types.SimpleNamespace(
            pad_token=0, sos_token=1, eos_token=2, out_token=3, time_token_start=10, time_token_end=20,
            time_hz=1, token_to_time_id=lambda token: token - 10,
        )
        generation = types.SimpleNamespace(
            PromptGrammarState=Grammar, inference_autocast=lambda *args: nullcontext(),
            select_cache_batch=lambda cache, indices, size: cache.batch_select_indices(indices) or cache,
        )
        finished = []
        generated = runtime.generate_batch(
            model, generation, batch_memory, (), [[1, 3], [1, 3, 4]], [0.0, None],
            result_callback=lambda index, value: finished.append(index),
        )
        assert finished == [0, 1]
        assert [(tokens.tolist(), reason) for tokens, reason in generated] == [
            ([1, 3, 10, 2], "time_boundary"), ([1, 3, 4, 5, 2], "eos"),
        ]
        with pytest.raises(EmbeddingCancelledError):
            model.encode_and_pool(torch.ones(1, 43), window_start=0, accept_start=0, accept_end=0.43,
                                  cancelled=lambda: True)

    duration = 480.123
    accepted = sum(accepted_frame_weights(7500, 0.04, window["start"], window["accept_start"],
                                         window["accept_end"], window["end"] - window["start"]).sum()
                   for window in sliding_window_plan(duration))
    assert accepted == pytest.approx(duration)

    # A real safetensors round trip includes tied BART weights and a native-style
    # Torchaudio buffer view; neither may be mistaken for an incomplete checkpoint.
    sheet_path, base_path = tmp_path / "sheet", tmp_path / "base"
    sheet_path.mkdir()
    base_path.mkdir()
    local_config = dict(config, weights_format="adapter", sampling_rate=24_000, time_hz=100,
                        tokenizer_schema_version="v1", tokenizer_fingerprint="fixture")
    (sheet_path / "config.json").write_text(json.dumps(local_config), encoding="utf-8")
    (base_path / "config.json").write_text(json.dumps(config["backbone_config"]), encoding="utf-8")
    saved_model = SheetSage2Runtime(local_config, types.SimpleNamespace(pad_token=0))
    save_model(saved_model, str(sheet_path / "model.safetensors"))
    save_file({key: value.clone() for key, value in ordinary_mert.state_dict().items()},
              str(base_path / "model.safetensors"))
    modules = {
        "tokenization_sheetsage2": types.SimpleNamespace(
            SheetSage2Tokenizer=lambda *args, **kwargs: types.SimpleNamespace(pad_token=0, n_tokens=20)),
        "generation_sheetsage2": object(),
        "exports_sheetsage2": object(),
        "configuration_mert2": types.SimpleNamespace(MERT2Config=lambda **kwargs: types.SimpleNamespace(**kwargs)),
        "modeling_mert2": types.SimpleNamespace(MERT2Model=lambda config: Encoder()),
    }
    monkeypatch.setattr(runtime, "_local_modules", lambda *args: nullcontext(modules.__getitem__))
    loaded, _, exports = runtime.load_local_runtime(sheet_path, base_path)
    assert exports is modules["exports_sheetsage2"]
    assert loaded.adapter is None
    assert loaded.decoder.embed_tokens.weight is loaded.output_projection.weight
    torch.testing.assert_close(loaded.token_embedding.weight, saved_model.token_embedding.weight)
    torch.testing.assert_close(loaded.encoder.window, ordinary_mert.window)


def test_sheetsage2_timeline_features_and_layers_reject_incomplete_generation() -> None:
    import copy
    from contextlib import nullcontext
    from dj_track_similarity.analysis.sheetsage2_features import derive_sheetsage2_features
    from dj_track_similarity.embedding.sheetsage2 import SheetSage2Adapter

    times = [0.0, 0.5, 1.0, 1.5, 2.0, 2.25, 2.5]
    raw = []
    for i, time_s in enumerate(times):
        values = {"timestamp": time_s, "rhythm": {"eighth_position": (i * 2) % 8 if i < 4 else i - 4}}
        if i in (0, 4):
            values["rhythm"]["meter"] = (4, 4) if i == 0 else (3, 8)
        if i in (0, 3):
            values.update(chord="C:maj" if i == 0 else "G:maj", key="C:major" if i == 0 else "A:minor",
                          structure="intro" if i == 0 else "chorus")
        raw.append(dict(time=time_s, global_subbeat=i * 4 if i < 4 else (i - 4) * 4,
                        subbeat=i * 4, source_subbeat=i * 4, window_index=0, values=values))
    raw[1]["values"]["chord"] = "C:maj"
    for index, pitch, track, end in ((0, 60, 0, 0.75), (1, 64, 0, 1.0), (3, 67, 0, 2.0),
                                    (0, 72, 1, 1.0), (2, 74, 1, 2.0)):
        raw[index]["values"].setdefault("melody", []).append(dict(
            pitch=pitch, track=track, end_time=end, duration_steps=4, duration_bin=1,
        ))

    class Grammar:
        def __init__(self, tokenizer):
            pass

        def update(self, token):
            return token == 2

        def allowed(self, device):
            return torch.ones(4, dtype=torch.bool, device=device)

    tokenizer = types.SimpleNamespace(pad_token=0, sos_token=1, eos_token=2, out_token=3,
                                     time_token_start=10, time_token_end=20,
                                     normalize_prompts=lambda prompts: prompts, prompt_prefix=lambda prompts: [1, 3])

    class FakeModel:
        max_output_seq_len = 32
        invalid_row = False

        def __init__(self):
            self.tokenizer = tokenizer
            self.calls = 0

        def encode_and_pool_batch(self, segment, **kwargs):
            self.calls += 1
            assert segment.shape[1] == 72_000
            count = segment.shape[0]
            return (torch.zeros(count, 1, 2), np.tile(np.arange(1, 1025, dtype=float), (count, 24, 1)),
                    np.full(count, 3.0), np.ones(count, dtype=bool))

        def decode(self, memory, decoder_input, **kwargs):
            token = 1 if adapter._generation.truncated else 2
            logits = torch.zeros(memory.shape[0], 1, 4)
            logits[:, :, token] = 1
            if self.invalid_row and memory.shape[0] > 1:
                logits[1] = float("nan")
            return logits, None

    class Generation:
        FULL_TASK_PROMPTS = ("timestamp", "downbeat_meter", "structure", "key", "chord_full", "melody_full")
        PromptGrammarState = Grammar
        inference_autocast = staticmethod(lambda *args: nullcontext())
        truncated = False
        anchors = True

        def decode_generated_tokens(self, *args):
            return {"events": [{"subbeat": 0, "values": {"timestamp": 0} if self.anchors else {}}]}, None

        event_time_map = staticmethod(lambda *args: None)
        stitched_window_events = staticmethod(lambda *args, **kwargs: copy.deepcopy(raw))

    def interval_rows(events, field, duration):
        # The native exports_sheetsage2.interval_rows.
        rows = [[e["time"], 0, e["values"][field]] for e in events if field in e["values"]]
        for index, row in enumerate(rows):
            row[1] = rows[index + 1][0] if index + 1 < len(rows) else duration
        return [row for row in rows if row[1] > row[0]]

    adapter = SheetSage2Adapter(device="cpu", inference_batch_size=2)
    adapter.device, adapter._torch, adapter._model, adapter._generation = "cpu", torch, FakeModel(), Generation()
    adapter._exports = types.SimpleNamespace(
        interval_rows=interval_rows,
        normalize_key_name=lambda label: label,
        correct_chord_rows=lambda chords, keys: [list(row) for row in chords],
    )
    decoded = DecodedAudio(path="fixture.wav", audio=torch.ones(72_000), sample_rate=24_000, detail="synthetic")
    completed = []
    result, second = adapter.analyze_decoded_batch([decoded, decoded], result_callback=lambda i, value: completed.append(i))
    assert adapter._model.calls == 1
    assert completed == [0, 1]
    assert not isinstance(second, Exception)
    assert len(result.layer_embeddings) == 24
    for vector in result.layer_embeddings:
        assert vector.shape == (1024,) and vector.dtype == np.float32
        assert np.linalg.norm(vector) == pytest.approx(1)
    features = result.features
    assert features == derive_sheetsage2_features(types.MappingProxyType(result.timeline))
    assert (features["beat_count"], features["downbeat_count"]) == (7, 2)
    assert (features["bpm_min"], features["bpm_max"], features["bpm_std"]) == (120, 120, 0)
    assert features["meter_durations_s"] == {"4/4": 2.0, "3/8": 1.0}
    assert features["meter_change_count"] == 1
    assert (features["chord_segment_count"], features["chord_change_count"]) == (2, 1)
    assert features["dominant_chord"] == "C:maj"
    assert features["major_fraction"] == features["minor_fraction"] == 0.5
    assert features["first_chorus_start_s"] == features["intro_end_s"] == 1.5
    assert features["melody_vocal_coverage_fraction"] == 0.5
    assert features["melody_all_coverage_fraction"] == pytest.approx(2 / 3)
    assert features["melody_all_interval_histogram"] == {"3": 1, "2": 1}
    assert features["melody_all_interval_abs_mean"] == 2.5
    anchor_only = copy.deepcopy(result.timeline)
    for event in anchor_only["events"]:
        event.pop("rhythm", None)
    assert derive_sheetsage2_features(anchor_only)["beat_count"] == 0
    unknown_meter = copy.deepcopy(result.timeline)
    unknown_meter["events"][0]["rhythm"].update(numerator=None, denominator=None)
    unknown_features = derive_sheetsage2_features(unknown_meter)
    assert unknown_features["meter_durations_s"] == {"4/4": 1.5, "3/8": 1.0}
    assert unknown_features["beat_count"] == 6
    empty = copy.deepcopy(result.timeline)
    for event in empty["events"]:
        event.pop("melody", None)
    empty_features = derive_sheetsage2_features(empty)
    assert empty_features["melody_all_event_count"] == empty_features["melody_all_coverage_fraction"] == 0
    assert empty_features["melody_all_pitch_min"] is None
    assert empty_features["melody_all_interval_histogram"] == {}
    invalid = copy.deepcopy(result.timeline)
    invalid["events"][0]["melody"][0]["end_s"] = 10
    with pytest.raises(ValueError, match="melodic intervals"):
        derive_sheetsage2_features(invalid)

    # Raw repeated chords must reach native spelling separately across a key
    # change; zero-length labels must not influence spelling or feature counts.
    original_raw, original_exports = raw, adapter._exports
    raw = [dict(time=time_s, global_subbeat=i, source_subbeat=i, window_index=0,
                values=dict(timestamp=time_s, **labels)) for i, (time_s, labels) in enumerate([
        (0.0, dict(chord="C#:maj", structure="intro")),
        (0.5, dict(key="C#:major")),
        (1.0, dict(chord="C#:maj", key="C#:minor")),
        (1.5, dict(chord="N", key="F#:major", structure="verse")),
        (1.5, dict(chord="N", key="C#:minor", structure="chorus")),
        (2.0, dict(chord="X")),
        (2.5, dict(chord="G#:maj")),
        (3.0, dict(chord="G:maj", key="C:major", structure="outro")),
    ])]
    for index, pitch, track, end in ((0, 60, 0, 4.0), (0, 72, 1, 1.0), (2, 64, 0, 2.0),
                                    (3, 62, 0, 1.5), (3, 63, 0, 1.0), (6, 65, 0, 3.5), (7, 67, 0, 3.0)):
        raw[index]["values"].setdefault("melody", []).append(dict(
            pitch=pitch, track=track, end_time=end, duration_steps=4, duration_bin=1,
        ))
    untouched = copy.deepcopy(raw)

    def correct_chords(chords, keys):
        assert chords == [[0, 1, "C#:maj"], [1, 1.5, "C#:maj"], [1.5, 2, "N"],
                          [2, 2.5, "X"], [2.5, 3, "G#:maj"]]
        assert keys == [[0.5, 1, "Db:major"], [1, 1.5, "C#:minor"], [1.5, 3, "C#:minor"]]
        return [[start, end, label] for (start, end, _), label in
                zip(chords, ("Db:maj", "C#:maj", "N", "X", "G#:maj"), strict=True)]

    adapter._exports = types.SimpleNamespace(
        interval_rows=interval_rows,
        normalize_key_name=lambda label: "Db:major" if label == "C#:major" else label,
        correct_chord_rows=correct_chords,
    )
    corrected = adapter.analyze_decoded_batch([decoded])[0]
    assert not isinstance(corrected, Exception), corrected
    assert raw == untouched
    intervals = {field: [[event["time_s"], event[field]["end_s"], event[field]["label"]]
                         for event in corrected.timeline["events"] if field in event]
                 for field in ("chord", "key", "structure")}
    assert intervals == {
        "chord": [[0, 1, "Db:maj"], [1, 1.5, "C#:maj"], [1.5, 2, "N"],
                  [2, 2.5, "X"], [2.5, 3, "G#:maj"]],
        "key": [[0.5, 1, "Db:major"], [1, 3, "C#:minor"]],
        "structure": [[0, 1.5, "intro"], [1.5, 3, "chorus"]],
    }
    assert corrected.features["chord_segment_count"] == 5
    assert corrected.features["dominant_chord"] == "Db:maj"
    assert corrected.features["key_durations_s"] == {"Db:major": 0.5, "C#:minor": 2.0}
    assert corrected.features["section_count"] == 2
    assert corrected.features["outro_start_s"] is None
    assert corrected.features["melody_vocal_event_count"] == 3
    assert corrected.features["melody_vocal_coverage_fraction"] == 1
    assert corrected.features["melody_vocal_interval_histogram"] == {"1": 1}
    melody = [note for event in corrected.timeline["events"] for note in event.get("melody", [])]
    assert [(note["pitch_midi"], note["start_s"], note["end_s"]) for note in melody] == [
        (60, 0, 3), (72, 0, 1), (64, 1, 2), (65, 2.5, 3),
    ]
    assert all(note["duration_steps"] == 4 and note["duration_bin"] == 1 for note in melody)
    raw, adapter._exports = original_raw, original_exports

    adapter._generation.truncated = True
    error = adapter.analyze_decoded_batch([decoded])[0]
    assert isinstance(error, ValueError) and "token limit" in str(error)
    adapter._generation.truncated = False
    adapter._generation.anchors = False
    error = adapter.analyze_decoded_batch([decoded])[0]
    assert isinstance(error, ValueError) and "timestamp anchors" in str(error)
    adapter._generation.anchors = True
    adapter._model.invalid_row = True
    completed.clear()
    results = adapter.analyze_decoded_batch([decoded, decoded], result_callback=lambda i, value: completed.append(i))
    assert completed == [0, 1]
    assert not isinstance(results[0], Exception)
    assert isinstance(results[1], ValueError) and "logits" in str(results[1])
    adapter._model.invalid_row = False
    completed.clear()
    with pytest.raises(EmbeddingCancelledError):
        adapter.analyze_decoded_batch([decoded, decoded], cancelled=lambda: bool(completed),
                                      result_callback=lambda i, value: completed.append(i))
    assert completed == [0]
    callback_error = ValueError("write callback failed")

    def failed_callback(index, value):
        completed.append(index)
        raise callback_error

    completed.clear()
    with pytest.raises(ValueError) as captured:
        adapter.analyze_decoded_batch([decoded, decoded], result_callback=failed_callback)
    assert captured.value is callback_error
    assert completed == [0]
    adapter._model.calls = 0
    with pytest.raises(EmbeddingCancelledError):
        adapter.analyze_decoded_batch([decoded], cancelled=lambda: adapter._model.calls > 0)
