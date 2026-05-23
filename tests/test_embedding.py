import sys
import types

import numpy as np

from dj_track_similarity.embedding import ClapEmbeddingAdapter, _array_output_to_numpy, _pad_or_trim_audio_window, adapter_factories


def test_clap_adapter_uses_music_checkpoint() -> None:
    assert ClapEmbeddingAdapter.embedding_key == "clap"
    assert ClapEmbeddingAdapter.checkpoint_repo == "lukewys/laion_clap"
    assert ClapEmbeddingAdapter.checkpoint_filename == "music_audioset_epoch_15_esc_90.14.pt"
    assert ClapEmbeddingAdapter.model_name == "lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt"


def test_product_embedding_adapters_do_not_expose_removed_fake_adapter() -> None:
    assert set(adapter_factories()) == {"mert", "clap"}


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


def test_pad_or_trim_audio_window_returns_fixed_length_float32() -> None:
    assert _pad_or_trim_audio_window(np.array([1.0, 2.0]), 4).tolist() == [1.0, 2.0, 0.0, 0.0]
    assert _pad_or_trim_audio_window(np.array([1.0, 2.0, 3.0, 4.0]), 2).tolist() == [1.0, 2.0]
    assert _pad_or_trim_audio_window(np.array([1, 2], dtype=np.int16), 2).dtype == np.float32
