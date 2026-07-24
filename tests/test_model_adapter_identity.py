import hashlib
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

import dj_track_similarity.embedding as embedding
import dj_track_similarity.genres as genres
from dj_track_similarity.analysis_contracts import ContractIdentity
from dj_track_similarity.analysis_model_runners import (
    MaestModelRunner,
    current_embedding_analysis_output,
    embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    validate_production_contract,
)
from dj_track_similarity.embedding import (
    ClapEmbeddingAdapter,
    MertEmbeddingAdapter,
    MuqEmbeddingAdapter,
)
from dj_track_similarity.genres import MaestGenreAdapter


def test_adapter_identities_are_available_before_model_load() -> None:
    adapters = (
        MaestGenreAdapter(device="cpu"),
        MertEmbeddingAdapter(device="cpu"),
        MuqEmbeddingAdapter(device="cpu"),
        ClapEmbeddingAdapter(device="cpu"),
    )

    assert [adapter.dim for adapter in adapters] == [768, 768, 1024, 512]
    assert [adapter.adapter_revision for adapter in adapters] == [
        "maest-adapter-v1",
        "mert-adapter-v1",
        "muq-adapter-v1",
        "clap-adapter-v2",
    ]
    for adapter in adapters:
        assert adapter._model is None
        assert adapter.model_version
        assert adapter.preprocessing
        assert adapter.checkpoint_id == f"sha256:{adapter.checkpoint_sha256}"
        assert len(adapter.checkpoint_sha256) == 64
        assert set(adapter.checkpoint_sha256) <= set("0123456789abcdef")
        assert adapter.contract_parameters()


def test_current_maest_identity_is_identical_for_runner_and_consumers() -> None:
    runner = MaestModelRunner(
        device="cpu",
        top_k=3,
        inference_batch_size=1,
    )

    assert (
        runner.active_outputs[1].contract_hash
        == current_embedding_analysis_output("maest").contract_hash
    )


@pytest.mark.parametrize(
    ("family", "field_name", "replacement"),
    (
        ("maest", "model_name", "not/maest"),
        ("mert", "model_version", "f" * 40),
        ("muq", "checkpoint_id", "sha256:" + "0" * 64),
        ("clap", "preprocessing", "different-preprocessing"),
        ("mert", "normalization", "none"),
        ("muq", "dim", 1),
        ("clap", "encoding", "float64-le"),
    ),
)
def test_current_ml_contract_rejects_mutated_top_level_identity(
    family: str,
    field_name: str,
    replacement: object,
) -> None:
    current = current_embedding_analysis_output(family)

    with pytest.raises(ValueError, match=field_name):
        mutated = replace(current.contract, **{field_name: replacement})
        validate_production_contract(mutated)


@pytest.mark.parametrize(
    ("family", "parameter_name", "replacement"),
    (
        ("maest", "adapter_revision", "maest-adapter-v2"),
        ("mert", "loader_package", "transformers==0.0.0"),
        ("mert", "hub_package", "huggingface-hub==0.0.0"),
        ("mert", "model_revision", "f" * 40),
        ("mert", "snapshot_sha256", (("config.json", "0" * 64),)),
        ("mert", "pooling", "different-pooling"),
        ("mert", "dtype", "float16"),
        ("muq", "device_precision", "float16-eval"),
        ("muq", "window_seconds", 9.0),
        ("clap", "amodel", "different-architecture"),
        ("clap", "text_model_revision", "f" * 40),
        (
            "clap",
            "text_snapshot_sha256",
            (("config.json", "0" * 64),),
        ),
        ("clap", "enable_fusion", True),
        ("clap", "input_quantization", "different-quantization"),
    ),
)
def test_current_ml_contract_rejects_mutated_runtime_identity(
    family: str,
    parameter_name: str,
    replacement: object,
) -> None:
    current = current_embedding_analysis_output(family)
    parameters = dict(current.contract.parameters)
    parameters[parameter_name] = replacement
    mutated = replace(current.contract, parameters=parameters)

    with pytest.raises(ValueError, match=parameter_name):
        validate_production_contract(mutated)


def test_behavior_subclass_requires_an_explicit_allowlisted_revision_bump() -> None:
    class BehaviorV2(MertEmbeddingAdapter):
        adapter_revision = "mert-adapter-v2"

        def embed_decoded_batch(self, decoded_items):
            return ["behavior-v2" for _item in decoded_items]

    current = current_embedding_analysis_output("mert")
    parameters = dict(current.contract.parameters)
    parameters["adapter_revision"] = BehaviorV2.adapter_revision
    drifted = AnalysisOutput(replace(current.contract, parameters=parameters))

    assert drifted.contract_hash != current.contract_hash
    with pytest.raises(ValueError, match="adapter_revision"):
        embedding_analysis_output("mert", BehaviorV2(device="cpu"))


def test_contract_parameters_expose_every_production_factory_field() -> None:
    maest = MaestGenreAdapter(top_k=7).contract_parameters()
    assert maest["sample_rate_hz"] == 16_000
    assert maest["input_seconds"] == 30.0
    assert maest["analysis_offset_seconds"] == 60.0
    assert maest["analysis_window_ratios"] == (0.38, 0.72)
    assert maest["top_k"] == 7
    assert maest["pooling"] == "distilled-token-mean+window-mean+l2"

    mert = MertEmbeddingAdapter(window_seconds=4.0, max_windows=3).contract_parameters()
    assert mert["sample_rate_hz"] == 24_000
    assert mert["window_seconds"] == 4.0
    assert mert["max_windows"] == 3
    assert mert["hidden_layers"] == (9, 10, 11, 12)
    assert mert["pooling"] == "last-4-layer-mean+masked-time-mean+window-mean+l2"
    assert mert["dtype"] == "float32"
    assert mert["loader_package"] == "transformers==5.13.0"
    assert mert["hub_package"] == "huggingface-hub==1.22.0"
    assert mert["checkpoint_filename"] == "pytorch_model.bin"
    assert mert["snapshot_files"] == (
        "config.json",
        "configuration_MERT.py",
        "modeling_MERT.py",
        "preprocessor_config.json",
        "pytorch_model.bin",
    )
    assert dict(mert["snapshot_sha256"])["pytorch_model.bin"] == (
        MertEmbeddingAdapter.checkpoint_sha256
    )

    muq = MuqEmbeddingAdapter(window_seconds=8.0, max_windows=4).contract_parameters()
    assert muq["sample_rate_hz"] == 24_000
    assert muq["window_seconds"] == 8.0
    assert muq["max_windows"] == 4
    assert muq["pooling"] == "last-hidden-time-mean+per-window-l2+window-mean+l2"
    assert muq["dtype"] == "float32"
    assert muq["loader_package"] == "muq==0.1.0"
    assert muq["hub_package"] == "huggingface-hub==1.22.0"
    assert muq["checkpoint_filename"] == "model.safetensors"
    assert muq["snapshot_files"] == ("config.json", "model.safetensors")
    assert dict(muq["snapshot_sha256"])["model.safetensors"] == (
        MuqEmbeddingAdapter.checkpoint_sha256
    )

    clap = ClapEmbeddingAdapter(window_seconds=6.0, max_windows=2).contract_parameters()
    assert clap["sample_rate_hz"] == 48_000
    assert clap["window_seconds"] == 6.0
    assert clap["max_windows"] == 2
    assert clap["pooling"] == "clap-audio+per-window-l2+window-mean+l2"
    assert clap["amodel"] == "HTSAT-base"
    assert clap["tmodel"] == "roberta"
    assert clap["enable_fusion"] is False
    assert clap["dtype"] == "float32"
    assert clap["loader_package"] == "laion-clap==1.1.7"
    assert clap["text_loader_package"] == "transformers==5.13.0"
    assert clap["hub_package"] == "huggingface-hub==1.22.0"
    assert clap["text_model_name"] == "roberta-base"
    assert (
        clap["text_model_revision"]
        == "e2da8e2f811d1448a5b465c236feacd80ffbac7b"
    )
    assert clap["text_snapshot_files"] == (
        "config.json",
        "merges.txt",
        "model.safetensors",
        "tokenizer_config.json",
        "tokenizer.json",
        "vocab.json",
    )
    assert dict(clap["text_snapshot_sha256"])["model.safetensors"] == (
        ClapEmbeddingAdapter.text_checkpoint_sha256
    )
    assert (
        clap["checkpoint_filename"]
        == "music_audioset_epoch_15_esc_90.14.pt"
    )


@pytest.mark.parametrize(
    "verify",
    (embedding._verify_checkpoint_sha256, genres._verify_checkpoint_sha256),
)
def test_checkpoint_verification_rejects_wrong_bytes(tmp_path, verify) -> None:
    checkpoint = tmp_path / "checkpoint.bin"
    checkpoint.write_bytes(b"not the pinned checkpoint")

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        verify(
            checkpoint,
            expected_sha256="0" * 64,
            description="test checkpoint",
        )


def test_hf_checkpoint_download_is_revision_pinned_and_hash_checked(
    monkeypatch,
    tmp_path,
) -> None:
    checkpoint = tmp_path / "checkpoint.bin"
    checkpoint.write_bytes(b"checkpoint")
    expected = hashlib.sha256(b"checkpoint").hexdigest()
    calls: dict[str, object] = {}

    def download(*, repo_id, filename, revision):
        calls["download"] = (repo_id, filename, revision)
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
    assert calls["download"] == ("owner/model", "model.bin", "a" * 40)
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

    def download(*, repo_id, revision, allow_patterns):
        calls["download"] = (repo_id, revision, allow_patterns)
        return str(snapshot)

    hf_module.snapshot_download = download
    transformers_module = types.ModuleType("transformers")
    transformers_module.AutoModel = FakeAutoModel
    transformers_module.Wav2Vec2FeatureExtractor = FakeFeatureExtractor
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)
    monkeypatch.setattr(
        embedding,
        "_require_distribution_version",
        lambda *args: None,
    )
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

    assert calls["download"] == (
        adapter.model_name,
        adapter.model_revision,
        list(adapter.snapshot_files),
    )
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

    def download(*, repo_id, revision, allow_patterns):
        calls["download"] = (repo_id, revision, allow_patterns)
        return str(snapshot)

    hf_module.snapshot_download = download
    muq_module = types.ModuleType("muq")
    muq_module.MuQ = FakeMuQ
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "muq", muq_module)
    monkeypatch.setattr(
        embedding,
        "_require_distribution_version",
        lambda *args: None,
    )
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

    assert calls["download"] == (
        adapter.model_name,
        adapter.model_revision,
        list(adapter.snapshot_files),
    )
    model_path, model_kwargs = calls["model"]
    assert model_path != str(snapshot)
    assert not Path(model_path).exists()
    assert model_kwargs == {"local_files_only": True}
    assert calls["float"] is True


def test_clap_loader_pins_checkpoint_revision_and_sha(
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

    def download(*, repo_id, filename, revision):
        calls["download"] = (repo_id, filename, revision)
        return str(checkpoint)

    hf_module.hf_hub_download = download

    def snapshot_download(*, repo_id, revision, allow_patterns):
        calls["text_download"] = (repo_id, revision, allow_patterns)
        return str(text_snapshot)

    hf_module.snapshot_download = snapshot_download
    transformers_module = types.ModuleType("transformers")
    transformers_module.RobertaModel = object()
    transformers_module.RobertaTokenizer = object()

    class FakeClap:
        def __init__(self, *, enable_fusion, amodel, tmodel, device):
            calls["module"] = (enable_fusion, amodel, tmodel, device)

        def load_ckpt(self, path):
            calls["checkpoint"] = path

    clap_module = types.ModuleType("laion_clap")
    clap_module.CLAP_Module = FakeClap
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)
    monkeypatch.setitem(sys.modules, "laion_clap", clap_module)
    monkeypatch.setattr(
        embedding,
        "_require_distribution_version",
        lambda *args: None,
    )
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

    assert calls["download"] == (
        adapter.checkpoint_repo,
        adapter.checkpoint_filename,
        adapter.model_revision,
    )
    assert calls["text_download"] == (
        adapter.text_model_name,
        adapter.text_model_revision,
        list(adapter.text_snapshot_files),
    )
    assert calls["module"] == (
        False,
        "HTSAT-base",
        "roberta",
        "device:cpu",
    )
    loaded_path = Path(calls["checkpoint"])
    assert loaded_path != checkpoint
    assert not loaded_path.exists()


@pytest.mark.parametrize(
    ("family", "parameters", "missing_key"),
    (
        (
            "mert",
            MertEmbeddingAdapter().contract_parameters(),
            "loader_package",
        ),
        (
            "mert",
            MertEmbeddingAdapter().contract_parameters(),
            "dtype",
        ),
        (
            "clap",
            ClapEmbeddingAdapter().contract_parameters(),
            "loader_package",
        ),
        (
            "clap",
            ClapEmbeddingAdapter().contract_parameters(),
            "dtype",
        ),
        (
            "muq",
            MuqEmbeddingAdapter().contract_parameters(),
            "loader_package",
        ),
    ),
)
def test_production_contract_rejects_underspecified_loader_identity(
    family,
    parameters,
    missing_key,
) -> None:
    adapter = {
        "mert": MertEmbeddingAdapter(),
        "muq": MuqEmbeddingAdapter(),
        "clap": ClapEmbeddingAdapter(),
    }[family]
    incomplete = dict(parameters)
    incomplete.pop(missing_key)
    contract = ContractIdentity(
        analysis_family=family,
        output_kind="embedding",
        model_name=adapter.model_name,
        model_version=adapter.model_version,
        dim=adapter.dim,
        encoding=adapter.encoding,
        normalization=adapter.normalization,
        checkpoint_id=adapter.checkpoint_id,
        preprocessing=adapter.preprocessing,
        parameters=incomplete,
    )

    with pytest.raises(ValueError, match=missing_key):
        validate_production_contract(contract)


def test_loader_version_mismatch_fails_before_import_or_deserialization(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        embedding,
        "distribution_version",
        lambda name: "0.0.0",
    )

    with pytest.raises(
        RuntimeError,
        match="Pinned model loader version mismatch for transformers",
    ):
        MertEmbeddingAdapter(device="cpu")._load_model()


def test_maest_loader_verifies_asset_before_deserialization(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {}

    class FakeHub:
        @staticmethod
        def get_dir():
            return str(tmp_path)

        @staticmethod
        def download_url_to_file(url, destination, *, hash_prefix, progress):
            calls["download"] = (url, destination, hash_prefix, progress)
            with open(destination, "wb") as checkpoint:
                checkpoint.write(b"checkpoint")

    class FakeModel:
        def to(self, device):
            calls["device"] = device
            return self

        def eval(self):
            calls["eval"] = True
            return self

    def get_maest(**kwargs):
        calls["get_maest"] = kwargs
        return FakeModel()

    torch_module = types.ModuleType("torch")
    torch_module.hub = FakeHub()
    torchaudio_module = types.ModuleType("torchaudio")
    maest_module = types.ModuleType("maest_infer")
    maest_module.get_maest = get_maest
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", torchaudio_module)
    monkeypatch.setitem(sys.modules, "maest_infer", maest_module)
    monkeypatch.setattr(genres, "_require_distribution_version", lambda *args: None)
    monkeypatch.setattr(genres, "_verify_checkpoint_sha256", lambda *args, **kwargs: None)

    adapter = MaestGenreAdapter(device="cpu")
    adapter.checkpoint_sha256 = hashlib.sha256(b"checkpoint").hexdigest()
    adapter._load_model()

    checkpoint_path = tmp_path / "checkpoints" / adapter.checkpoint_filename
    assert calls["download"] == (
        adapter.checkpoint_url,
        str(checkpoint_path),
        adapter.checkpoint_sha256,
        True,
    )
    get_maest_call = calls["get_maest"]
    assert get_maest_call["arch"] == adapter.model_name
    assert get_maest_call["pretrained"] is False
    assert Path(get_maest_call["checkpoint"]) != checkpoint_path
    assert not Path(get_maest_call["checkpoint"]).exists()
    assert get_maest_call["checkpoint_swa_weigts"] is True


def test_maest_cached_asset_hash_is_checked_before_use(tmp_path) -> None:
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    checkpoint = checkpoint_dir / MaestGenreAdapter.checkpoint_filename
    checkpoint.write_bytes(b"wrong checkpoint")

    fake_torch = types.SimpleNamespace(
        hub=types.SimpleNamespace(get_dir=lambda: str(tmp_path))
    )
    expected = hashlib.sha256(b"expected checkpoint").hexdigest()

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        genres._verified_maest_checkpoint(
            fake_torch,
            checkpoint_url=MaestGenreAdapter.checkpoint_url,
            checkpoint_filename=MaestGenreAdapter.checkpoint_filename,
            expected_sha256=expected,
        )
