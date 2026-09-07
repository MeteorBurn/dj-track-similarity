from __future__ import annotations

import threading
import time

import numpy as np

from ..analysis_models import (
    MERT_ADAPTER_REVISION,
    MERT_CHECKPOINT_ID,
    MERT_MODEL_NAME,
    MERT_MODEL_REVISION,
    MERT_PREPROCESSING,
    MERT_SNAPSHOT_SHA256,
)
from ..audio.loader import DecodedAudio
from .audio import _prepare_windows
from .loading import _download_verified_hf_snapshot
from ..runtime import select_torch_device


class MertEmbeddingAdapter:
    embedding_key = "mert"
    adapter_revision = MERT_ADAPTER_REVISION
    model_name = MERT_MODEL_NAME
    model_revision = MERT_MODEL_REVISION
    model_version = model_revision
    checkpoint_filename = "pytorch_model.bin"
    checkpoint_id = MERT_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    preprocessing = MERT_PREPROCESSING
    dim = 768
    target_rate = 24_000
    hidden_layers = (9, 10, 11, 12)
    pooling = "last-4-layer-mean+masked-time-mean+window-mean+l2"
    encoding = "float32-le"
    normalization = "l2"
    snapshot_files = (
        "config.json",
        "configuration_MERT.py",
        "modeling_MERT.py",
        "preprocessor_config.json",
        checkpoint_filename,
    )
    snapshot_sha256 = MERT_SNAPSHOT_SHA256

    def __init__(
        self,
        device: str | None = None,
        window_seconds: float = 5.0,
        max_windows: int = 5,
        inference_batch_size: int = 16,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.window_seconds = window_seconds
        self.max_windows = max_windows
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._load_lock = threading.RLock()
        self._model = None
        self._processor = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self.last_batch_timing: dict[str, float | int] = {}

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "adapter_revision": self.adapter_revision,
            "sample_rate_hz": self.target_rate,
            "window_seconds": self.window_seconds,
            "max_windows": self.max_windows,
            "hidden_layers": self.hidden_layers,
            "pooling": self.pooling,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "window_selection": "10%-90%-interior-evenly-spaced-rounded",
            "short_audio": "single-variable-length-window",
            "processor_normalization": "wav2vec2-do-normalize",
            "processor_padding": "right-zero-with-attention-mask",
            "dtype": "float32",
            "device_precision": "float32-eval-no-autocast",
            "model_revision": self.model_revision,
            "remote_code_revision": self.model_revision,
            "checkpoint_filename": self.checkpoint_filename,
            "snapshot_files": self.snapshot_files,
            "snapshot_sha256": self.snapshot_sha256,
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def embed_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[np.ndarray]:
        self._load_model()
        assert self._processor is not None
        return self._embed_decoded_items(
            decoded_items,
            target_rate=int(self._processor.sampling_rate),
        )

    def _embed_decoded_items(
        self,
        decoded_items: list[DecodedAudio],
        *,
        target_rate: int,
    ) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None and self._processor is not None
        track_windows, all_windows, prepare_seconds = _prepare_windows(
            decoded_items,
            target_rate=target_rate,
            window_seconds=self.window_seconds,
            max_windows=self.max_windows,
            pad="none",
            torch=torch,
            torchaudio=torchaudio,
            model_label="MERT",
        )

        pooled_windows: list[np.ndarray] = []
        inference_started = time.perf_counter()
        for start in range(0, len(all_windows), self.inference_batch_size):
            window_batch = all_windows[start : start + self.inference_batch_size]
            inputs = self._processor(window_batch, sampling_rate=target_rate, padding=True, return_tensors="pt")
            inputs = {key: value.to(self._device()) for key, value in inputs.items()}
            with torch.inference_mode():
                outputs = self._model(**inputs, output_hidden_states=True)
            hidden = torch.stack(outputs.hidden_states[-4:]).mean(dim=0)
            attention_mask = inputs.get("attention_mask")
            feature_mask_for = getattr(self._model, "_get_feature_vector_attention_mask", None)
            if attention_mask is not None and callable(feature_mask_for):
                feature_mask = feature_mask_for(hidden.shape[1], attention_mask)
                pooled_tensor = _masked_time_mean(hidden, feature_mask)
            else:
                pooled_tensor = hidden.mean(dim=1)
            pooled = pooled_tensor.detach().cpu().numpy().astype(np.float32)
            pooled_windows.extend([pooled[index] for index in range(pooled.shape[0])])
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": len(all_windows),
        }

        vectors = []
        for decoded, indices in zip(decoded_items, track_windows):
            vector = np.mean(np.vstack([pooled_windows[index] for index in indices]), axis=0).astype(np.float32)
            norm = np.linalg.norm(vector)
            if norm == 0:
                raise ValueError(f"Model produced a zero vector: {decoded.path}")
            vectors.append(vector / norm)
        return vectors

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            import torchaudio
            from huggingface_hub import snapshot_download
            from transformers import AutoModel, Wav2Vec2FeatureExtractor

            self._torch = torch
            self._torchaudio = torchaudio
            binding = _download_verified_hf_snapshot(
                snapshot_download,
                repo_id=self.model_name,
                revision=self.model_revision,
                required_files=self.snapshot_files,
                expected_sha256=self.snapshot_sha256,
                checkpoint_filename=self.checkpoint_filename,
                expected_checkpoint_sha256=self.checkpoint_sha256,
            )
            with binding as verified:
                snapshot_path = str(verified.path)
                processor = Wav2Vec2FeatureExtractor.from_pretrained(
                    snapshot_path,
                    local_files_only=True,
                )
                if int(processor.sampling_rate) != self.target_rate:
                    raise RuntimeError(
                        "Local MERT processor sample rate does not match the "
                        "configured adapter input: "
                        f"expected {self.target_rate}, got {processor.sampling_rate}"
                    )
                self.device = self._device()
                model = AutoModel.from_pretrained(
                    snapshot_path,
                    trust_remote_code=True,
                    local_files_only=True,
                    use_safetensors=False,
                )
            to_float = getattr(model, "float", None)
            if callable(to_float):
                model = to_float()
            model = model.to(self.device).eval()
            self._processor = processor
            self._model = model

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)

def _masked_time_mean(hidden, feature_mask):
    if tuple(feature_mask.shape) != tuple(hidden.shape[:2]):
        raise ValueError(
            f"MERT feature mask shape {tuple(feature_mask.shape)} does not match hidden states {tuple(hidden.shape[:2])}"
        )
    mask = feature_mask.to(device=hidden.device, dtype=hidden.dtype).unsqueeze(-1)
    counts = mask.sum(dim=1).clamp_min(1.0)
    return (hidden * mask).sum(dim=1) / counts
