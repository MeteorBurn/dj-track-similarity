import hashlib
import sys
import threading
import types
from pathlib import Path

import pytest

import dj_track_similarity.embedding.clap as embedding_clap
import dj_track_similarity.embedding.loading as embedding_loading
import dj_track_similarity.embedding.maest as embedding_maest
from dj_track_similarity.embedding.clap import ClapEmbeddingAdapter
from dj_track_similarity.embedding.maest import MaestEmbeddingAdapter
from dj_track_similarity.embedding.mert import MertEmbeddingAdapter
from dj_track_similarity.embedding.muq import MuqEmbeddingAdapter
from dj_track_similarity.embedding.mulan import MuqMulanEmbeddingAdapter


def _retry_loader_concurrently(adapter, monkeypatch) -> None:
    """Hold the first real lock acquisition until a second caller contends."""

    original_lock = getattr(adapter, "_load_lock", threading.RLock())
    entered = threading.Event()
    contended = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    class ObservedLoadLock:
        def __enter__(self):
            if not original_lock.acquire(blocking=False):
                contended.set()
                assert original_lock.acquire(timeout=5), "Load lock was not released"
            entered.set()
            if not release.wait(5):
                original_lock.release()
                raise AssertionError("Timed out releasing the first loader")

        def __exit__(self, *_exc):
            original_lock.release()

    def load():
        try:
            adapter._load_model()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=load) for _ in range(2)]
    started = []
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "_load_lock", ObservedLoadLock(), raising=False)
        try:
            threads[0].start()
            started.append(threads[0])
            assert entered.wait(5), "Loader did not acquire its instance lock"
            threads[1].start()
            started.append(threads[1])
            assert contended.wait(5), "Second caller did not contend on the load lock"
            assert adapter._model is None
        finally:
            release.set()
            for thread in started:
                thread.join(5)
        assert all(not thread.is_alive() for thread in started)
        assert not errors, errors
    adapter._load_model()


def test_adapters_expose_dimensions_and_normalization_before_model_load() -> None:
    adapters = (
        MaestEmbeddingAdapter(device="cpu"),
        MertEmbeddingAdapter(device="cpu"),
        MuqEmbeddingAdapter(device="cpu"),
        MuqMulanEmbeddingAdapter(device="cpu"),
        ClapEmbeddingAdapter(device="cpu"),
    )

    assert [adapter.dim for adapter in adapters] == [768, 768, 1024, 512, 512]
    assert [adapter.normalization for adapter in adapters] == ["l2", "l2", "l2", "l2", "l2"]
    for adapter in adapters:
        assert adapter._model is None


def test_every_adapter_declares_a_pinned_immutable_identity() -> None:
    """Each adapter must name its model, version, preprocessing and checkpoint.

    ``_adapter_identity`` enforces this whenever analysis builds an output, and
    a search no longer builds one, so the contract is pinned here instead of
    being re-derived per request from constants that cannot change at runtime.
    """

    adapters = (
        MaestEmbeddingAdapter(device="cpu"),
        MertEmbeddingAdapter(device="cpu"),
        MuqEmbeddingAdapter(device="cpu"),
        MuqMulanEmbeddingAdapter(device="cpu"),
        ClapEmbeddingAdapter(device="cpu"),
    )

    for adapter in adapters:
        for field in ("model_name", "model_version", "checkpoint_id", "preprocessing"):
            value = getattr(adapter, field, None)
            assert isinstance(value, str) and value.strip(), (
                f"{type(adapter).__name__}.{field}"
            )
        digest = adapter.checkpoint_id.removeprefix("sha256:")
        assert len(digest) == 64 and digest == digest.lower(), (
            f"{type(adapter).__name__}.checkpoint_id is not a lowercase sha256 digest"
        )
        int(digest, 16)


def test_adapter_identity_rejects_an_adapter_with_a_blank_field() -> None:
    """The check that stayed in the analysis path still refuses a bad adapter."""

    from dj_track_similarity.analysis.model_runners import _adapter_identity

    class _Blank:
        model_name = "x"
        model_version = "  "
        checkpoint_id = "sha256:" + "a" * 64
        preprocessing = "y"

    with pytest.raises(RuntimeError, match="model_version"):
        _adapter_identity(_Blank())


def test_adapter_runtime_parameters_do_not_encode_loader_package_identity() -> None:
    forbidden = {
        "loader_package",
        "text_loader_package",
        "hub_package",
        "package_wheel_sha256",
    }

    for adapter in (
        MaestEmbeddingAdapter(device="cpu"),
        MertEmbeddingAdapter(device="cpu"),
        MuqEmbeddingAdapter(device="cpu"),
        MuqMulanEmbeddingAdapter(device="cpu"),
        ClapEmbeddingAdapter(device="cpu"),
    ):
        assert forbidden.isdisjoint(adapter.runtime_parameters())


def test_adapters_declare_the_shared_torchcodec_decoder() -> None:
    for adapter in (
        MaestEmbeddingAdapter(device="cpu"),
        MertEmbeddingAdapter(device="cpu"),
        MuqEmbeddingAdapter(device="cpu"),
        MuqMulanEmbeddingAdapter(device="cpu"),
        ClapEmbeddingAdapter(device="cpu"),
    ):
        parameters = adapter.runtime_parameters()
        assert parameters["decoder"] == "shared-torchcodec-0.16"
        assert parameters["channel_downmix"] == "torchcodec-num-channels-1"


def test_maest_runtime_parameters_describe_structure_aware_windows() -> None:
    parameters = MaestEmbeddingAdapter(device="cpu").runtime_parameters()

    assert parameters["analysis_window_positions"] == (0.2, 0.5, 0.8)
    assert (
        parameters["window_selection"]
        == "structure-aware-main-range-centered-20-50-80"
    )
    assert parameters["window_context"] == "sonara-current-generation-optional"
    assert (
        parameters["window_fallback"]
        == "main-range->non-silent-range->full-duration"
    )
    assert parameters["window_dedup_tolerance_seconds"] == 1.0
    assert "analysis_offset_seconds" not in parameters
    assert "analysis_window_ratios" not in parameters


def test_checkpoint_verification_rejects_wrong_bytes(tmp_path) -> None:
    checkpoint = tmp_path / "checkpoint.bin"
    checkpoint.write_bytes(b"not the pinned checkpoint")

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        embedding_loading._verify_checkpoint_sha256(
            checkpoint,
            expected_sha256="0" * 64,
            description="test checkpoint",
        )


def test_local_checkpoint_resolution_creates_immutable_verified_binding(
    monkeypatch,
    tmp_path,
) -> None:
    checkpoint = tmp_path / "checkpoint.bin"
    checkpoint.write_bytes(b"checkpoint")
    expected = hashlib.sha256(b"checkpoint").hexdigest()
    calls: dict[str, object] = {}

    def download(*, repo_id, filename, revision, local_files_only):
        calls["download"] = (repo_id, filename, revision, local_files_only)
        return str(checkpoint)

    def verify(path, *, expected_sha256, description):
        calls["verify"] = (path, expected_sha256, description)

    monkeypatch.setattr(embedding_loading, "_verify_checkpoint_sha256", verify)

    resolved = embedding_loading._download_verified_hf_checkpoint(
        download,
        repo_id="owner/model",
        filename="model.bin",
        revision="a" * 40,
        expected_sha256=expected,
    )

    checkpoint.write_bytes(b"mutated after binding")
    with resolved as binding:
        assert binding.path != checkpoint
        assert binding.path.read_bytes() == b"checkpoint"
        with pytest.raises(OSError):
            binding.path.write_bytes(b"different deserializer input")
        assert binding.path.read_bytes() == b"checkpoint"
    assert calls["download"][:2] == ("owner/model", "model.bin")
    assert calls["download"][3] is True
    assert calls["verify"] == (
        checkpoint,
        expected,
        f"owner/model@{'a' * 40}/model.bin",
    )

    def missing_file(**kwargs):
        assert kwargs["local_files_only"] is True
        raise FileNotFoundError("not cached")

    calls.clear()
    with pytest.raises(RuntimeError, match="Automatic model downloads are disabled") as error:
        embedding_loading._download_verified_hf_checkpoint(
            missing_file,
            repo_id="owner/model",
            filename="model.bin",
            revision="a" * 40,
            expected_sha256=expected,
        )
    assert "owner/model@" in str(error.value) and "model.bin" in str(error.value)
    assert not calls


def test_mert_loader_deserializes_only_verified_local_snapshot(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {}
    models = []
    processors = []
    snapshot = tmp_path / "mert-snapshot"
    snapshot.mkdir()
    for file_name in MertEmbeddingAdapter.snapshot_files:
        (snapshot / file_name).write_bytes(file_name.encode())

    class FakeModel:
        def float(self):
            calls["float"] = True
            return self

        def to(self, device):
            calls["device"] = device
            return self

        def eval(self):
            calls["eval"] = True
            if self is models[0]:
                raise RuntimeError("MERT final preparation failed")
            return self

    class FakeProcessor:
        sampling_rate = 24_000

    class FakeFeatureExtractor:
        @staticmethod
        def from_pretrained(model_name, **kwargs):
            calls["processor"] = (model_name, kwargs)
            processor = FakeProcessor()
            processors.append(processor)
            return processor

    class FakeAutoModel:
        @staticmethod
        def from_pretrained(model_name, **kwargs):
            calls["model"] = (model_name, kwargs)
            model = FakeModel()
            models.append(model)
            return model

    torch_module = types.ModuleType("torch")
    torchaudio_module = types.ModuleType("torchaudio")
    hf_module = types.ModuleType("huggingface_hub")

    def download(*, repo_id, revision, allow_patterns, local_files_only):
        calls["download"] = (repo_id, revision, allow_patterns, local_files_only)
        return str(snapshot)

    hf_module.snapshot_download = download
    transformers_module = types.ModuleType("transformers")
    transformers_module.AutoModel = FakeAutoModel
    transformers_module.Wav2Vec2FeatureExtractor = FakeFeatureExtractor
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)
    monkeypatch.setattr(embedding_loading, "_verify_checkpoint_sha256", lambda *args, **kwargs: None)

    adapter = MertEmbeddingAdapter(device="cpu")
    adapter.snapshot_sha256 = tuple(
        (
            file_name,
            hashlib.sha256(file_name.encode()).hexdigest(),
        )
        for file_name in adapter.snapshot_files
    )
    adapter.checkpoint_sha256 = dict(adapter.snapshot_sha256)[
        adapter.checkpoint_filename
    ]
    def missing_snapshot(**kwargs):
        assert kwargs["local_files_only"] is True
        raise FileNotFoundError("not cached")

    hf_module.snapshot_download = missing_snapshot
    with pytest.raises(RuntimeError, match="Automatic model downloads are disabled") as error:
        adapter._load_model()
    assert adapter.model_revision in str(error.value)
    assert adapter.checkpoint_filename in str(error.value)
    assert not models and not processors
    assert adapter._model is None and adapter._processor is None

    hf_module.snapshot_download = download
    missing_asset = snapshot / adapter.snapshot_files[0]
    missing_asset.unlink()
    with pytest.raises(RuntimeError, match="snapshot is incomplete") as error:
        adapter._load_model()
    assert missing_asset.name in str(error.value)
    assert not models and not processors
    assert adapter._model is None and adapter._processor is None
    missing_asset.write_bytes(missing_asset.name.encode())
    with pytest.raises(RuntimeError, match="MERT final preparation failed"):
        adapter._load_model()
    assert len(models) == len(processors) == 1
    assert adapter._model is None
    assert adapter._processor is None
    assert not Path(calls["model"][0]).exists()

    _retry_loader_concurrently(adapter, monkeypatch)
    assert len(models) == len(processors) == 2
    assert models[0] is not models[1]
    assert processors[0] is not processors[1]
    assert adapter._model is models[1]
    assert adapter._processor is processors[1]

    assert calls["download"][0] == adapter.model_name
    assert calls["download"][2] == list(adapter.snapshot_files)
    assert calls["download"][3] is True
    processor_path, processor_kwargs = calls["processor"]
    model_path, model_kwargs = calls["model"]
    assert processor_path == model_path
    assert processor_path != str(snapshot)
    assert not Path(processor_path).exists()
    assert processor_kwargs == {"local_files_only": True}
    assert model_kwargs == {
        "trust_remote_code": True,
        "local_files_only": True,
        "use_safetensors": False,
    }
    assert calls["float"] is True


def test_muq_loader_deserializes_only_verified_local_snapshot(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {}
    models = []
    snapshot = tmp_path / "muq-snapshot"
    snapshot.mkdir()
    for file_name in MuqEmbeddingAdapter.snapshot_files:
        (snapshot / file_name).write_bytes(file_name.encode())

    class FakeModel:
        def float(self):
            calls["float"] = True
            return self

        def to(self, device):
            calls["device"] = device
            return self

        def eval(self):
            calls["eval"] = True
            if self is models[0]:
                raise RuntimeError("MuQ final preparation failed")
            return self

    class FakeMuQ:
        @staticmethod
        def from_pretrained(model_name, **kwargs):
            calls["model"] = (model_name, kwargs)
            model = FakeModel()
            models.append(model)
            return model

    torch_module = types.ModuleType("torch")
    torchaudio_module = types.ModuleType("torchaudio")
    hf_module = types.ModuleType("huggingface_hub")

    def download(*, repo_id, revision, allow_patterns, local_files_only):
        calls["download"] = (repo_id, revision, allow_patterns, local_files_only)
        return str(snapshot)

    hf_module.snapshot_download = download
    muq_module = types.ModuleType("muq")
    muq_module.MuQ = FakeMuQ
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "muq", muq_module)
    monkeypatch.setattr(embedding_loading, "_verify_checkpoint_sha256", lambda *args, **kwargs: None)

    adapter = MuqEmbeddingAdapter(device="cpu")
    adapter.snapshot_sha256 = tuple(
        (
            file_name,
            hashlib.sha256(file_name.encode()).hexdigest(),
        )
        for file_name in adapter.snapshot_files
    )
    adapter.checkpoint_sha256 = dict(adapter.snapshot_sha256)[
        adapter.checkpoint_filename
    ]
    with pytest.raises(RuntimeError, match="MuQ final preparation failed"):
        adapter._load_model()
    assert len(models) == 1
    assert adapter._model is None
    assert muq_module.MuQ is FakeMuQ
    assert not Path(calls["model"][0]).exists()

    _retry_loader_concurrently(adapter, monkeypatch)
    assert len(models) == 2
    assert models[0] is not models[1]
    assert adapter._model is models[1]
    assert muq_module.MuQ is FakeMuQ

    assert calls["download"][0] == adapter.model_name
    assert calls["download"][2] == list(adapter.snapshot_files)
    assert calls["download"][3] is True
    model_path, model_kwargs = calls["model"]
    assert model_path != str(snapshot)
    assert not Path(model_path).exists()
    assert model_kwargs == {"local_files_only": True}
    assert calls["float"] is True


def test_mulan_loader_deserializes_only_verified_local_towers(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {"downloads": []}
    models = []
    snapshot = tmp_path / "mulan-snapshot"
    snapshot.mkdir()
    for file_name in MuqMulanEmbeddingAdapter.snapshot_files:
        (snapshot / file_name).write_bytes(file_name.encode())
    (snapshot / "config.json").write_text('{"mulan": {"dim_latent": 512}}', encoding="utf-8")
    text_snapshot = tmp_path / "xlm-roberta-snapshot"
    text_snapshot.mkdir()
    for file_name in MuqMulanEmbeddingAdapter.text_snapshot_files:
        (text_snapshot / file_name).write_bytes(file_name.encode())
    audio_snapshot = tmp_path / "muq-audio-snapshot"
    audio_snapshot.mkdir()
    for file_name in MuqMulanEmbeddingAdapter.audio_snapshot_files:
        (audio_snapshot / file_name).write_bytes(file_name.encode())

    text_module = types.ModuleType("muq.muq_mulan.models.text")

    class VerifiedTokenizerLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["tokenizer_load"] = (source, kwargs)
            assert (Path(source) / "tokenizer.json").read_bytes() == b"tokenizer.json"
            assert text_module.AutoTokenizer is not VerifiedTokenizerLoader
            assert text_module.XLMRobertaModel is not VerifiedEncoderLoader
            assert muq_module.MuQ is not VerifiedAudioLoader
            if len(models) == 1:
                raise RuntimeError("MuLan tokenizer preparation failed")
            return object()

    class VerifiedEncoderLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["encoder_load"] = (source, kwargs)
            assert (Path(source) / "config.json").read_bytes() == b"config.json"
            return object()

    class VerifiedAudioLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["audio_load"] = (source, kwargs)
            assert (Path(source) / "config.json").read_bytes() == b"config.json"
            return object()

    text_module.AutoTokenizer = VerifiedTokenizerLoader
    text_module.XLMRobertaModel = VerifiedEncoderLoader

    class FakeTextTower:
        def __init__(self) -> None:
            self.model_name = MuqMulanEmbeddingAdapter.text_model_name
            self._tokenizer = None

        @property
        def tokenizer(self):
            if self._tokenizer is None:
                self._tokenizer = text_module.AutoTokenizer.from_pretrained(
                    self.model_name,
                )
            return self._tokenizer

    class FakeMuLan:
        def __init__(self) -> None:
            self.text = FakeTextTower()

    class FakeModel:
        def __init__(self) -> None:
            self.mulan_module = FakeMuLan()

        def load_state_dict(self, state, *, strict):
            assert state == {"weight": "local safetensors"}
            assert strict is True
            calls["model"] = (str(Path(calls["safetensors_path"]).parent), {"strict": strict})

        def float(self):
            return self

        def to(self, _device):
            return self

        def eval(self):
            return self

    class FakeMuQMuLan:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            pytest.fail("MuLan must not use the Hub model-loading mixin")

        def __new__(cls, *, config):
            assert config == {"mulan": {"dim_latent": 512}}
            text_module.XLMRobertaModel.from_pretrained(
                MuqMulanEmbeddingAdapter.text_model_name,
            )
            # Upstream builds the audio tower through the muq package
            # namespace and forwards its own cache directory.
            muq_module.MuQ.from_pretrained(
                MuqMulanEmbeddingAdapter.audio_model_name,
                cache_dir=None,
            )
            model = FakeModel()
            models.append(model)
            return model

    safetensors_module = types.ModuleType("safetensors.torch")

    def load_file(path, *, device):
        assert device == "cpu"
        assert Path(path).read_bytes() == b"model.safetensors"
        calls["safetensors_path"] = str(path)
        return {"weight": "local safetensors"}

    safetensors_module.load_file = load_file
    monkeypatch.setitem(sys.modules, "safetensors.torch", safetensors_module)
    hf_module = types.ModuleType("huggingface_hub")

    def download(*, repo_id, revision, allow_patterns, local_files_only):
        calls["downloads"].append(
            (repo_id, revision, allow_patterns, local_files_only)
        )
        if repo_id == MuqMulanEmbeddingAdapter.text_model_name:
            return str(text_snapshot)
        if repo_id == MuqMulanEmbeddingAdapter.audio_model_name:
            return str(audio_snapshot)
        return str(snapshot)

    hf_module.snapshot_download = download
    muq_module = types.ModuleType("muq")
    muq_module.MuQMuLan = FakeMuQMuLan
    muq_module.MuQ = VerifiedAudioLoader
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    monkeypatch.setitem(sys.modules, "torchaudio", types.ModuleType("torchaudio"))
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "muq", muq_module)
    monkeypatch.setitem(sys.modules, "muq.muq_mulan.models.text", text_module)
    monkeypatch.setattr(
        embedding_loading,
        "_verify_checkpoint_sha256",
        lambda *args, **kwargs: None,
    )

    adapter = MuqMulanEmbeddingAdapter(device="cpu")
    adapter.snapshot_sha256 = tuple(
        (file_name, hashlib.sha256((snapshot / file_name).read_bytes()).hexdigest())
        for file_name in adapter.snapshot_files
    )
    adapter.checkpoint_sha256 = dict(adapter.snapshot_sha256)[
        adapter.checkpoint_filename
    ]
    adapter.text_snapshot_sha256 = tuple(
        (file_name, hashlib.sha256(file_name.encode()).hexdigest())
        for file_name in adapter.text_snapshot_files
    )
    adapter.text_checkpoint_sha256 = dict(adapter.text_snapshot_sha256)[
        adapter.text_checkpoint_filename
    ]
    adapter.audio_snapshot_sha256 = tuple(
        (file_name, hashlib.sha256(file_name.encode()).hexdigest())
        for file_name in adapter.audio_snapshot_files
    )
    adapter.audio_checkpoint_sha256 = dict(adapter.audio_snapshot_sha256)[
        adapter.audio_checkpoint_filename
    ]
    with pytest.raises(RuntimeError, match="MuLan tokenizer preparation failed"):
        adapter._load_model()
    assert len(models) == 1
    assert adapter._model is None
    assert models[0].mulan_module.text._tokenizer is None
    assert text_module.AutoTokenizer is VerifiedTokenizerLoader
    assert text_module.XLMRobertaModel is VerifiedEncoderLoader
    assert muq_module.MuQ is VerifiedAudioLoader
    assert not Path(calls["model"][0]).exists()
    assert not Path(calls["tokenizer_load"][0]).exists()
    assert not Path(calls["audio_load"][0]).exists()

    _retry_loader_concurrently(adapter, monkeypatch)
    assert len(models) == 2
    assert models[0] is not models[1]
    assert adapter._model is models[1]
    assert models[1].mulan_module.text._tokenizer is not None

    assert calls["downloads"] == [
        (
            adapter.model_name,
            adapter.model_revision,
            list(adapter.snapshot_files),
            True,
        ),
        (
            adapter.text_model_name,
            adapter.text_model_revision,
            list(adapter.text_snapshot_files),
            True,
        ),
        (
            adapter.audio_model_name,
            adapter.audio_model_revision,
            list(adapter.audio_snapshot_files),
            True,
        ),
    ] * 2
    model_path, model_kwargs = calls["model"]
    assert model_path != str(snapshot)
    assert not Path(model_path).exists()
    assert model_kwargs == {"strict": True}
    tokenizer_path, tokenizer_kwargs = calls["tokenizer_load"]
    encoder_path, encoder_kwargs = calls["encoder_load"]
    assert tokenizer_path == encoder_path
    assert tokenizer_path != str(text_snapshot)
    assert not Path(tokenizer_path).exists()
    assert tokenizer_kwargs == {"local_files_only": True}
    assert encoder_kwargs == {"local_files_only": True}
    audio_path, audio_kwargs = calls["audio_load"]
    assert audio_path != str(audio_snapshot)
    assert not Path(audio_path).exists()
    assert audio_kwargs == {"cache_dir": None, "local_files_only": True}
    assert text_module.AutoTokenizer is VerifiedTokenizerLoader
    assert text_module.XLMRobertaModel is VerifiedEncoderLoader
    assert muq_module.MuQ is VerifiedAudioLoader


def test_clap_loader_uses_verified_checkpoint_and_text_assets(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {}
    models = []
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"checkpoint")
    text_snapshot = tmp_path / "roberta-snapshot"
    text_snapshot.mkdir()
    for file_name in ClapEmbeddingAdapter.text_snapshot_files:
        (text_snapshot / file_name).write_bytes(file_name.encode())

    torch_module = types.ModuleType("torch")
    torch_module.device = lambda device: f"device:{device}"
    torchaudio_module = types.ModuleType("torchaudio")
    hf_module = types.ModuleType("huggingface_hub")

    def download(*, repo_id, filename, revision, local_files_only):
        calls["download"] = (repo_id, filename, revision, local_files_only)
        return str(checkpoint)

    hf_module.hf_hub_download = download

    def snapshot_download(*, repo_id, revision, allow_patterns, local_files_only):
        calls["text_download"] = (repo_id, revision, allow_patterns, local_files_only)
        return str(text_snapshot)

    hf_module.snapshot_download = snapshot_download
    transformers_module = types.ModuleType("transformers")
    transformers_module.RobertaModel = object()
    transformers_module.RobertaTokenizer = object()

    class FakeClap:
        def __init__(self, *, enable_fusion, amodel, tmodel, device):
            calls["module"] = (enable_fusion, amodel, tmodel, device)
            models.append(self)

        def load_ckpt(self, path, verbose=True):
            calls["checkpoint"] = path
            if self is models[0]:
                raise RuntimeError("CLAP checkpoint preparation failed")

    clap_module = types.ModuleType("laion_clap")
    clap_module.CLAP_Module = FakeClap
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)
    monkeypatch.setitem(sys.modules, "laion_clap", clap_module)
    monkeypatch.setattr(embedding_loading, "_verify_checkpoint_sha256", lambda *args, **kwargs: None)
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
    adapter.checkpoint_sha256 = hashlib.sha256(b"checkpoint").hexdigest()
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
    with pytest.raises(RuntimeError, match="CLAP checkpoint preparation failed"):
        adapter._load_model()
    assert len(models) == 1
    assert adapter._model is None
    assert not Path(calls["checkpoint"]).exists()

    _retry_loader_concurrently(adapter, monkeypatch)
    assert len(models) == 2
    assert models[0] is not models[1]
    assert adapter._model is models[1]

    assert calls["download"][:2] == (
        adapter.checkpoint_repo,
        adapter.checkpoint_filename,
    )
    assert calls["text_download"][0] == adapter.text_model_name
    assert calls["text_download"][2] == list(adapter.text_snapshot_files)
    assert calls["download"][3] is True
    assert calls["text_download"][3] is True
    assert calls["module"] == (
        False,
        "HTSAT-base",
        "roberta",
        "device:cpu",
    )
    loaded_path = Path(calls["checkpoint"])
    assert loaded_path != checkpoint
    assert not loaded_path.exists()


def test_maest_loader_verifies_checkpoint_before_public_discogs_path(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {}
    order: list[str] = []
    models = []
    checkpoint = tmp_path / "maest.ckpt"
    checkpoint.write_bytes(b"maest weights")

    def forbidden_download(*args, **kwargs):
        pytest.fail("MAEST attempted URL-based checkpoint resolution")

    loader_module = types.ModuleType("maest_infer.helpers.vit_helpers")
    loader_module.load_state_dict_from_url = forbidden_download

    def load_local(path, **kwargs):
        assert Path(path) != checkpoint
        assert Path(path).read_bytes() == b"maest weights"
        assert kwargs == {"map_location": "cpu", "weights_only": True}
        calls["local_checkpoint"] = path
        return {"weight": "loaded locally"}

    class FakeMel:
        def __init__(self, model):
            self.model = model

        def to(self, device):
            order.append("mel-to")
            assert device == "cpu"
            if self.model is models[0]:
                raise RuntimeError("MAEST mel preparation failed")

    class FakeModel:
        melspectrogram = None

        def to(self, device):
            order.append("to")
            calls["device"] = device
            return self

        def eval(self):
            order.append("eval")
            calls["eval"] = True
            return self

        def init_melspectrogram(self):
            order.append("mel-init")
            self.melspectrogram = FakeMel(self)

    def get_maest(**kwargs):
        assert order[-1] == "verify"
        order.append("load")
        calls["get_maest"] = kwargs
        assert loader_module.load_state_dict_from_url(
            MaestEmbeddingAdapter.checkpoint_url,
            map_location="cpu", progress=False, check_hash=False,
        ) == {"weight": "loaded locally"}
        model = FakeModel()
        models.append(model)
        return model

    torch_module = types.ModuleType("torch")
    torch_module.load = load_local
    torchaudio_module = types.ModuleType("torchaudio")
    maest_module = types.ModuleType("maest_infer")
    maest_module.get_maest = get_maest
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "maest_infer", maest_module)
    monkeypatch.setitem(sys.modules, "maest_infer.helpers.vit_helpers", loader_module)
    monkeypatch.setattr(
        embedding_maest,
        "_ensure_verified_maest_checkpoint",
        lambda *args, **kwargs: (order.append("verify"), checkpoint)[1],
    )

    adapter = MaestEmbeddingAdapter(device="cpu")
    adapter.checkpoint_sha256 = hashlib.sha256(b"maest weights").hexdigest()
    with pytest.raises(RuntimeError, match="MAEST mel preparation failed"):
        adapter._load_model()
    assert len(models) == 1
    assert adapter._model is None
    assert loader_module.load_state_dict_from_url is forbidden_download
    assert not Path(calls["local_checkpoint"]).exists()

    _retry_loader_concurrently(adapter, monkeypatch)
    assert len(models) == 2
    assert models[0] is not models[1]
    assert adapter._model is models[1]
    assert order == ["verify", "load", "to", "eval", "mel-init", "mel-to"] * 2
    assert calls["get_maest"] == {"arch": adapter.model_name}
    assert calls["device"] == "cpu"
    assert calls["eval"] is True
    assert loader_module.load_state_dict_from_url is forbidden_download
    assert not Path(calls["local_checkpoint"]).exists()


def test_maest_checkpoint_must_exist_locally_before_use(tmp_path) -> None:
    checkpoint_bytes = b"checkpoint"
    expected_sha256 = hashlib.sha256(checkpoint_bytes).hexdigest()

    class FakeHub:
        @staticmethod
        def get_dir():
            return str(tmp_path)

        @staticmethod
        def download_url_to_file(*args, **kwargs):
            pytest.fail("MAEST attempted a network download")

    fake_torch = types.SimpleNamespace(hub=FakeHub())
    expected_path = tmp_path / "checkpoints" / MaestEmbeddingAdapter.checkpoint_filename
    kwargs = dict(
        checkpoint_url=MaestEmbeddingAdapter.checkpoint_url,
        checkpoint_filename=MaestEmbeddingAdapter.checkpoint_filename,
        expected_sha256=expected_sha256,
    )
    with pytest.raises(RuntimeError, match="Automatic model downloads are disabled") as error:
        embedding_maest._ensure_verified_maest_checkpoint(fake_torch, **kwargs)
    assert str(expected_path) in str(error.value)
    assert not expected_path.parent.exists()
    expected_path.parent.mkdir()
    expected_path.write_bytes(checkpoint_bytes)
    assert embedding_maest._ensure_verified_maest_checkpoint(fake_torch, **kwargs) == expected_path



def test_maest_cached_checkpoint_hash_is_checked_before_use(tmp_path) -> None:
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    checkpoint = checkpoint_dir / MaestEmbeddingAdapter.checkpoint_filename
    checkpoint.write_bytes(b"wrong checkpoint")
    fake_torch = types.SimpleNamespace(
        hub=types.SimpleNamespace(get_dir=lambda: str(tmp_path))
    )
    expected = hashlib.sha256(b"expected checkpoint").hexdigest()

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        embedding_maest._ensure_verified_maest_checkpoint(
            fake_torch,
            checkpoint_url=MaestEmbeddingAdapter.checkpoint_url,
            checkpoint_filename=MaestEmbeddingAdapter.checkpoint_filename,
            expected_sha256=expected,
        )
