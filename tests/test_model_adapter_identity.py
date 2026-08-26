import hashlib
import sys
import types
from pathlib import Path

import pytest

import dj_track_similarity.embedding as embedding
from dj_track_similarity.embedding import (
    ClapEmbeddingAdapter,
    MaestEmbeddingAdapter,
    MertEmbeddingAdapter,
    MuqEmbeddingAdapter,
    MuqMulanEmbeddingAdapter,
)


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


def test_model_adapters_do_not_expose_legacy_path_decoders() -> None:
    maest = MaestEmbeddingAdapter(device="cpu")
    assert not hasattr(maest, "analyze_batch")

    for adapter in (
        MertEmbeddingAdapter(device="cpu"),
        MuqEmbeddingAdapter(device="cpu"),
        MuqMulanEmbeddingAdapter(device="cpu"),
        ClapEmbeddingAdapter(device="cpu"),
    ):
        assert not hasattr(adapter, "embed")
        assert not hasattr(adapter, "embed_batch")


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
        embedding._verify_checkpoint_sha256(
            checkpoint,
            expected_sha256="0" * 64,
            description="test checkpoint",
        )


def test_hf_checkpoint_download_creates_immutable_verified_binding(
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

    monkeypatch.setattr(embedding, "_verify_checkpoint_sha256", verify)

    resolved = embedding._download_verified_hf_checkpoint(
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
    assert calls["download"][3] is False
    assert calls["verify"] == (
        checkpoint,
        expected,
        f"owner/model@{'a' * 40}/model.bin",
    )


def test_mert_loader_deserializes_only_verified_local_snapshot(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {}
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
            return self

    class FakeProcessor:
        sampling_rate = 24_000

    class FakeFeatureExtractor:
        @staticmethod
        def from_pretrained(model_name, **kwargs):
            calls["processor"] = (model_name, kwargs)
            return FakeProcessor()

    class FakeAutoModel:
        @staticmethod
        def from_pretrained(model_name, **kwargs):
            calls["model"] = (model_name, kwargs)
            return FakeModel()

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
    monkeypatch.setattr(embedding, "_verify_checkpoint_sha256", lambda *args, **kwargs: None)

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
    adapter._load_model()

    assert calls["download"][0] == adapter.model_name
    assert calls["download"][2] == list(adapter.snapshot_files)
    assert calls["download"][3] is False
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
            return self

    class FakeMuQ:
        @staticmethod
        def from_pretrained(model_name, **kwargs):
            calls["model"] = (model_name, kwargs)
            return FakeModel()

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
    monkeypatch.setattr(embedding, "_verify_checkpoint_sha256", lambda *args, **kwargs: None)

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
    adapter._load_model()

    assert calls["download"][0] == adapter.model_name
    assert calls["download"][2] == list(adapter.snapshot_files)
    assert calls["download"][3] is False
    model_path, model_kwargs = calls["model"]
    assert model_path != str(snapshot)
    assert not Path(model_path).exists()
    assert model_kwargs == {"local_files_only": True}
    assert calls["float"] is True


def test_mulan_loader_fetches_a_missing_pinned_snapshot_before_local_deserialization(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {"downloads": []}
    snapshot = tmp_path / "mulan-snapshot"
    snapshot.mkdir()
    for file_name in MuqMulanEmbeddingAdapter.snapshot_files:
        (snapshot / file_name).write_bytes(file_name.encode())
    text_snapshot = tmp_path / "xlm-roberta-snapshot"
    text_snapshot.mkdir()
    for file_name in MuqMulanEmbeddingAdapter.text_snapshot_files:
        (text_snapshot / file_name).write_bytes(file_name.encode())

    text_module = types.ModuleType("muq.muq_mulan.models.text")

    class VerifiedTokenizerLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["tokenizer_load"] = (source, kwargs)
            assert (Path(source) / "tokenizer.json").read_bytes() == b"tokenizer.json"
            return object()

    class VerifiedEncoderLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["encoder_load"] = (source, kwargs)
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

        def float(self):
            return self

        def to(self, _device):
            return self

        def eval(self):
            return self

    class FakeMuQMuLan:
        @staticmethod
        def from_pretrained(model_path, **kwargs):
            calls["model"] = (model_path, kwargs)
            text_module.XLMRobertaModel.from_pretrained(
                MuqMulanEmbeddingAdapter.text_model_name,
            )
            return FakeModel()

    hf_module = types.ModuleType("huggingface_hub")

    def download(*, repo_id, revision, allow_patterns, local_files_only):
        calls["downloads"].append(
            (repo_id, revision, allow_patterns, local_files_only)
        )
        if repo_id == MuqMulanEmbeddingAdapter.text_model_name:
            return str(text_snapshot)
        return str(snapshot)

    hf_module.snapshot_download = download
    muq_module = types.ModuleType("muq")
    muq_module.MuQMuLan = FakeMuQMuLan
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    monkeypatch.setitem(sys.modules, "torchaudio", types.ModuleType("torchaudio"))
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "muq", muq_module)
    monkeypatch.setitem(sys.modules, "muq.muq_mulan.models.text", text_module)
    monkeypatch.setattr(
        embedding,
        "_verify_checkpoint_sha256",
        lambda *args, **kwargs: None,
    )

    adapter = MuqMulanEmbeddingAdapter(device="cpu")
    adapter.snapshot_sha256 = tuple(
        (file_name, hashlib.sha256(file_name.encode()).hexdigest())
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
    adapter._load_model()

    assert calls["downloads"] == [
        (
            adapter.model_name,
            adapter.model_revision,
            list(adapter.snapshot_files),
            False,
        ),
        (
            adapter.text_model_name,
            adapter.text_model_revision,
            list(adapter.text_snapshot_files),
            False,
        ),
    ]
    model_path, model_kwargs = calls["model"]
    assert model_path != str(snapshot)
    assert not Path(model_path).exists()
    assert model_kwargs == {"local_files_only": True}
    tokenizer_path, tokenizer_kwargs = calls["tokenizer_load"]
    encoder_path, encoder_kwargs = calls["encoder_load"]
    assert tokenizer_path == encoder_path
    assert tokenizer_path != str(text_snapshot)
    assert not Path(tokenizer_path).exists()
    assert tokenizer_kwargs == {"local_files_only": True}
    assert encoder_kwargs == {"local_files_only": True}
    assert text_module.AutoTokenizer is VerifiedTokenizerLoader
    assert text_module.XLMRobertaModel is VerifiedEncoderLoader


def test_clap_loader_uses_verified_checkpoint_and_text_assets(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {}
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

        def load_ckpt(self, path, verbose=True):
            calls["checkpoint"] = path

    clap_module = types.ModuleType("laion_clap")
    clap_module.CLAP_Module = FakeClap
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)
    monkeypatch.setitem(sys.modules, "laion_clap", clap_module)
    monkeypatch.setattr(embedding, "_verify_checkpoint_sha256", lambda *args, **kwargs: None)
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
    adapter._load_model()

    assert calls["download"][:2] == (
        adapter.checkpoint_repo,
        adapter.checkpoint_filename,
    )
    assert calls["text_download"][0] == adapter.text_model_name
    assert calls["text_download"][2] == list(adapter.text_snapshot_files)
    assert calls["download"][3] is False
    assert calls["text_download"][3] is False
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
) -> None:
    calls: dict[str, object] = {}
    order: list[str] = []

    class FakeModel:
        def to(self, device):
            calls["device"] = device
            return self

        def eval(self):
            calls["eval"] = True
            return self

    def get_maest(**kwargs):
        assert order == ["verify"]
        order.append("load")
        calls["get_maest"] = kwargs
        return FakeModel()

    torch_module = types.ModuleType("torch")
    torchaudio_module = types.ModuleType("torchaudio")
    maest_module = types.ModuleType("maest_infer")
    maest_module.get_maest = get_maest
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "maest_infer", maest_module)
    monkeypatch.setattr(
        embedding,
        "_ensure_verified_maest_checkpoint",
        lambda *args, **kwargs: order.append("verify"),
    )

    adapter = MaestEmbeddingAdapter(device="cpu")
    adapter._load_model()

    assert order == ["verify", "load"]
    assert calls["get_maest"] == {"arch": adapter.model_name}
    assert calls["device"] == "cpu"
    assert calls["eval"] is True


def test_maest_checkpoint_is_downloaded_and_verified_before_use(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {}
    checkpoint_bytes = b"checkpoint"
    expected_sha256 = hashlib.sha256(checkpoint_bytes).hexdigest()

    class FakeHub:
        @staticmethod
        def get_dir():
            return str(tmp_path)

        @staticmethod
        def download_url_to_file(url, destination, *, hash_prefix, progress):
            calls["download"] = (url, destination, hash_prefix, progress)
            Path(destination).write_bytes(checkpoint_bytes)

    fake_torch = types.SimpleNamespace(hub=FakeHub())
    checkpoint = embedding._ensure_verified_maest_checkpoint(
        fake_torch,
        checkpoint_url=MaestEmbeddingAdapter.checkpoint_url,
        checkpoint_filename=MaestEmbeddingAdapter.checkpoint_filename,
        expected_sha256=expected_sha256,
    )

    expected_path = (
        tmp_path / "checkpoints" / MaestEmbeddingAdapter.checkpoint_filename
    )
    assert checkpoint == expected_path
    assert calls["download"] == (
        MaestEmbeddingAdapter.checkpoint_url,
        str(expected_path),
        expected_sha256,
        True,
    )


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
        embedding._ensure_verified_maest_checkpoint(
            fake_torch,
            checkpoint_url=MaestEmbeddingAdapter.checkpoint_url,
            checkpoint_filename=MaestEmbeddingAdapter.checkpoint_filename,
            expected_sha256=expected,
        )
