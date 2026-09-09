# ruff: noqa: E402

import logging
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

import dj_track_similarity.embedding.clap as embedding_clap
import dj_track_similarity.embedding.loading as embedding_loading
import dj_track_similarity.embedding.numerics as embedding_numerics
import dj_track_similarity.embedding.audio as embedding_audio
from dj_track_similarity.audio.loader import DecodedAudio
from dj_track_similarity.embedding.clap import ClapEmbeddingAdapter
from dj_track_similarity.embedding.contracts import EmbeddingCancelledError
from dj_track_similarity.embedding.maest import MaestEmbeddingAdapter
from dj_track_similarity.embedding.mert import MertEmbeddingAdapter, _iter_mert_windows
from dj_track_similarity.embedding.muq import MuqEmbeddingAdapter
from dj_track_similarity.embedding.mulan import MuqMulanEmbeddingAdapter
from dj_track_similarity.embedding.maest import _move_maest_runtime_modules
from dj_track_similarity.embedding.numerics import _array_output_to_numpy
from dj_track_similarity.embedding.audio import _pad_or_trim_audio_tensor
from dj_track_similarity.logging_config import configure_logging


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


def test_muq_adapter_uses_official_large_msd_checkpoint() -> None:
    assert MuqEmbeddingAdapter.embedding_key == "muq"
    assert MuqEmbeddingAdapter.model_name == "OpenMuQ/MuQ-large-msd-iter"
    assert MuqEmbeddingAdapter.target_rate == 24_000


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
    models = []
    checkpoint = tmp_path / "models" / "clap" / ClapEmbeddingAdapter.checkpoint_filename
    checkpoint.parent.mkdir(parents=True)
    monkeypatch.setattr(embedding_loading, "_MODELS_ROOT", tmp_path / "models")
    checkpoint.write_bytes(b"stub checkpoint")
    text_snapshot = tmp_path / "models" / "clap-text"
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


def test_clap_model_load_stdout_and_stderr_are_written_to_app_log(
    monkeypatch, tmp_path
) -> None:
    log_path = tmp_path / "app.log"
    checkpoint = tmp_path / "models" / "clap" / ClapEmbeddingAdapter.checkpoint_filename
    checkpoint.parent.mkdir(parents=True)
    monkeypatch.setattr(embedding_loading, "_MODELS_ROOT", tmp_path / "models")
    checkpoint.write_bytes(b"stub checkpoint")
    text_snapshot = tmp_path / "models" / "clap-text"
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
    def forbidden_resolution(*args, **kwargs):
        pytest.fail("CLAP attempted Hub/cache resolution")

    hf_module.hf_hub_download = forbidden_resolution
    hf_module.snapshot_download = forbidden_resolution
    transformers_module = types.ModuleType("transformers")
    transformers_module.RobertaModel = object()
    transformers_module.RobertaTokenizer = object()

    laion_module = types.ModuleType("laion_clap")

    class FakeClapModule:
        def __init__(self, *, enable_fusion, amodel, tmodel, device):
            print(f"Loading CLAP {amodel} on {device}")

        def load_ckpt(self, checkpoint_path, verbose=True):
            print(f"Load the specified checkpoint {checkpoint_path} from users.")
            print("CLAP warning from stderr", file=sys.stderr)

        def get_text_embedding(self, texts, use_tensor=False):
            return _text_embedding_rows(len(texts))

    laion_module.CLAP_Module = FakeClapModule

    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)
    monkeypatch.setitem(sys.modules, "laion_clap", laion_module)
    monkeypatch.setattr(
        embedding_clap,
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
    assert "Loading CLAP " in contents
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
            embedding_numerics._normalize_rows(np.asarray([[1.0, value, 0.0]], dtype=np.float32))


def test_normalize_rows_returns_flat_float32_unit_vectors() -> None:
    vectors = embedding_numerics._normalize_rows(np.asarray([[3.0, 4.0, 0.0]], dtype=np.float64))

    assert len(vectors) == 1
    assert vectors[0].shape == (3,)
    assert vectors[0].dtype == np.float32
    assert float(np.linalg.norm(vectors[0])) == pytest.approx(1.0)
    np.testing.assert_allclose(vectors[0], np.asarray([0.6, 0.8, 0.0], dtype=np.float32))


def test_normalize_rows_rejects_zero_vectors() -> None:
    with pytest.raises(ValueError, match="zero vector"):
        embedding_numerics._normalize_rows(np.asarray([[0.0, 0.0, 0.0]], dtype=np.float32))


def test_pad_or_trim_audio_tensor_returns_fixed_length_float32() -> None:
    assert _pad_or_trim_audio_tensor(torch.tensor([1.0, 2.0]), 4, torch).tolist() == [1.0, 2.0, 0.0, 0.0]
    assert _pad_or_trim_audio_tensor(torch.tensor([1.0, 2.0, 3.0, 4.0]), 2, torch).tolist() == [1.0, 2.0]
    assert _pad_or_trim_audio_tensor(torch.tensor([1, 2]), 2, torch).dtype == torch.float32


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

    for batch_size in (1, 2, 3, 8):
        adapter = SharedAudioClapAdapter()
        adapter.inference_batch_size = batch_size
        adapter.fake_torchaudio = types.SimpleNamespace(transforms=types.SimpleNamespace(Resample=FakeResampler))
        expected_batch_sizes = [min(batch_size, 8 - start) for start in range(0, 8, batch_size)]
        first_vectors = None
        for _ in range(2):
            resample_calls.clear()
            adapter.fake_model.audio_calls.clear()
            vectors = adapter.embed_decoded_batch(decoded)

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
            if first_vectors is None:
                first_vectors = vectors
            else:
                for vector, first in zip(vectors, first_vectors, strict=True):
                    assert vector.tobytes() == first.tobytes()


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

    def __call__(self, wavs, *, output_hidden_states=True):
        assert output_hidden_states is True
        self.batch_shapes.append(tuple(wavs.shape))
        self.batch_dtypes.append(wavs.dtype)
        hidden = torch.zeros((wavs.shape[0], 2, 3), dtype=torch.float32, device=wavs.device)
        for index in range(wavs.shape[0]):
            hidden[index, :, (int(wavs[index, 0].item()) - 1) % hidden.shape[-1]] = 1.0
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


def test_muq_embed_decoded_batch_uses_shared_audio_without_loading_paths() -> None:
    decoded = [
        DecodedAudio(path="a.wav", audio=torch.ones(24_000), sample_rate=24_000, detail="shared"),
        DecodedAudio(path="b.wav", audio=torch.full((24_000,), 2.0), sample_rate=24_000, detail="shared"),
    ]

    for batch_size in (1, 2, 4):
        adapter = SharedAudioMuqAdapter()
        adapter.inference_batch_size = batch_size
        vectors = adapter.embed_decoded_batch(decoded)
        assert [vector.tolist() for vector in vectors] == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        assert adapter.fake_model.batch_shapes == ([(1, 24000), (1, 24000)] if batch_size == 1 else [(2, 24000)])
        assert all(dtype == torch.float32 for dtype in adapter.fake_model.batch_dtypes)


def test_muq_consumes_shared_torchcodec_tensor_without_numpy_round_trip(
    monkeypatch,
) -> None:
    adapter = SharedAudioMuqAdapter()
    decoded = [
        DecodedAudio(
            path="a.wav",
            audio=torch.ones(24_000, dtype=torch.float32),
            sample_rate=24_000,
            detail="shared",
        )
    ]
    monkeypatch.setattr(
        torch,
        "from_numpy",
        lambda _audio: (_ for _ in ()).throw(
            AssertionError("MuQ must keep TorchCodec audio as tensors")
        ),
    )

    vectors = adapter.embed_decoded_batch(decoded)

    assert vectors[0].tolist() == [1.0, 0.0, 0.0]


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


class FakeMertProcessor:
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


class FakeMertModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.feature_mask_calls: list[tuple[int, tuple[int, ...]]] = []
        self.forward_calls = 0
        self.empty_feature_mask = False

    def forward(self, input_values, attention_mask, *, output_hidden_states):
        assert torch.is_inference_mode_enabled()
        assert input_values.dtype == torch.float32
        self.forward_calls += 1
        hidden = torch.zeros((len(input_values), 3, 768), dtype=torch.float32)
        means = input_values.mean(dim=1)
        hidden[:, 0, 0], hidden[:, 1, 0] = means, 2 * means
        hidden[:, 2, 0] = 100_000.0  # Must be excluded by feature-frame pooling.
        hidden[:, :, 1] = 1.0
        states = []
        for index in range(12):
            if output_hidden_states:
                states.append(hidden)
            hidden = hidden.clone()
            hidden[:, :, index + 2] += index + 1
        if output_hidden_states:
            states.append(hidden)
        return types.SimpleNamespace(last_hidden_state=hidden, hidden_states=tuple(states) or None)

    def _get_feature_vector_attention_mask(self, feature_vector_length, attention_mask):
        self.feature_mask_calls.append((feature_vector_length, tuple(attention_mask.shape)))
        mask = torch.zeros((len(attention_mask), feature_vector_length), dtype=torch.bool)
        if not self.empty_feature_mask:
            mask[:, :2] = True
        return mask


class SharedAudioMertAdapter(MertEmbeddingAdapter):
    def __init__(self, inference_batch_size=2) -> None:
        super().__init__(device="cpu", inference_batch_size=inference_batch_size)
        self.fake_model = FakeMertModel()
        self.fake_processor = FakeMertProcessor()
        self.load_calls = 0

    def _load_model(self) -> None:
        self.load_calls += 1
        self._torch = torch
        self._torchaudio = None
        self._processor = self.fake_processor
        self.device = "cpu"
        self._model = self.fake_model


def test_mert_embed_decoded_batch_uses_feature_vector_attention_mask() -> None:
    decoded = [
        DecodedAudio(
            path=f"synthetic-{index}.wav",
            audio=torch.arange(length, dtype=torch.float32) / 120_000 + index,
            sample_rate=24_000,
            detail="shared",
        )
        for index, length in enumerate((7 * 120_000 + 400, 120_399, 400, 719, 720, 120_000))
    ]
    expected = {}
    for item in decoded:
        # Layer outputs 9..12 contain all of layers 1..9, then 3/4, 1/2,
        # and 1/4 of layers 10, 11, and 12. The first two valid frames
        # encode the sample mean, so duration weighting recovers the whole track.
        vector = np.zeros(768, dtype=np.float64)
        vector[:2] = [1.5 * item.audio.double().mean().item(), 1.0]
        vector[2:14] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 7.5, 5.5, 3]
        expected[item.path] = (vector / np.linalg.norm(vector)).astype(np.float32)

    for batch_size in (1, 2, 3, 32):
        for items in (decoded, list(reversed(decoded))):
            adapter = SharedAudioMertAdapter(batch_size)
            vectors = adapter.embed_decoded_batch(items)
            for item, vector in zip(items, vectors, strict=True):
                assert vector.shape == (768,)
                assert vector.dtype == np.float32
                assert np.linalg.norm(vector) == pytest.approx(1.0)
                np.testing.assert_allclose(vector, expected[item.path], rtol=1e-5, atol=1e-6)
            batches = adapter.fake_processor.batches
            assert all(len(batch) <= batch_size for batch in batches)
            assert sum(sum(batch) for batch in batches) == sum(item.audio.numel() for item in items)
            assert adapter.fake_model.feature_mask_calls

    for item in decoded:
        vector = SharedAudioMertAdapter().embed_decoded_batch([item])[0]
        np.testing.assert_allclose(vector, expected[item.path], rtol=1e-5, atol=1e-6)

    for audio in (torch.empty(0), torch.ones(399), torch.full((400,), torch.nan), torch.full((400,), torch.inf)):
        invalid = DecodedAudio(path="invalid.wav", audio=audio, sample_rate=24_000, detail="shared")
        for items in ([invalid], [invalid, decoded[-1]], [decoded[-1], invalid]):
            with pytest.raises(ValueError):
                SharedAudioMertAdapter().embed_decoded_batch(items)

    adapter = SharedAudioMertAdapter()
    adapter.fake_model.empty_feature_mask = True
    with pytest.raises(ValueError):
        adapter.embed_decoded_batch([decoded[-1]])

    adapter = SharedAudioMertAdapter()
    with pytest.raises(EmbeddingCancelledError):
        adapter.embed_decoded_batch(decoded, cancelled=lambda: True)
    assert adapter.load_calls == adapter.fake_model.forward_calls == 0

    for items in ([decoded[0]], [decoded[-1]]):
        adapter = SharedAudioMertAdapter(inference_batch_size=2)
        with pytest.raises(EmbeddingCancelledError):
            adapter.embed_decoded_batch(items, cancelled=lambda: adapter.fake_model.forward_calls >= 1)
        assert adapter.fake_model.forward_calls == 1


def test_mert_windows_cover_every_sample_once_without_padding() -> None:
    for length, expected_lengths in (
        (400, [400]),
        (119_999, [119_999]),
        (120_000, [120_000]),
        (120_001, [120_001]),
        (120_399, [120_399]),
        (120_400, [120_000, 400]),
        (240_399, [120_000, 120_399]),
        (240_400, [120_000, 120_000, 400]),
        (840_400, [120_000] * 7 + [400]),
    ):
        waveform = torch.arange(length, dtype=torch.float32)
        windows = list(_iter_mert_windows(waveform))
        assert [window.numel() for window in windows] == expected_lengths
        torch.testing.assert_close(torch.cat(windows), waveform, rtol=0, atol=0)
        assert all(window.untyped_storage().data_ptr() == waveform.untyped_storage().data_ptr() for window in windows)


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


def test_maest_initializes_only_missing_melspectrogram() -> None:
    model = FakeMaestModel()

    _move_maest_runtime_modules(model, "cuda")

    assert model.init_calls == 1
    assert model.melspectrogram is not None
    assert model.melspectrogram.devices == ["cuda"]

    _move_maest_runtime_modules(model, "cuda")

    assert model.init_calls == 1
    assert model.melspectrogram.devices == ["cuda", "cuda"]


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
