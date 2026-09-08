from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

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
from .audio import _resample_to
from .contracts import EmbeddingCancelledError
from .loading import _bind_verified_local_snapshot
from ..runtime import select_torch_device

if TYPE_CHECKING:
    from torch import Tensor

_WINDOW_SAMPLES = 120_000
_MINIMUM_SAMPLES = 400


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
    window_seconds = 5.0
    hidden_layers = (9, 10, 11, 12)
    pooling = "masked-time-mean+last-4-layer-mean+sample-weighted-window-mean+l2"
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
        inference_batch_size: int = 16,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._load_lock = threading.RLock()
        self._inference_lock = threading.Lock()
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
            "hidden_layers": self.hidden_layers,
            "pooling": self.pooling,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "window_selection": "consecutive-full-coverage-no-overlap",
            "short_audio": "single-unpadded-window-minimum-400-samples",
            "tail_policy": "at-least-400-samples-separate-otherwise-merge-into-last-window",
            "processor_normalization": "wav2vec2-do-normalize",
            "processor_padding": "none-equal-length-batches-with-attention-mask",
            "hidden_state_extraction": "native-hidden-states-9-to-12-float32-time-pooling",
            "track_accumulation": "cpu-float64-weighted-by-real-samples",
            "dtype": "float32",
            "device_precision": "cuda-native-bfloat16-forward-autocast-otherwise-float32",
            "model_revision": self.model_revision,
            "remote_code_revision": self.model_revision,
            "checkpoint_filename": self.checkpoint_filename,
            "snapshot_files": self.snapshot_files,
            "snapshot_sha256": self.snapshot_sha256,
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def embed_decoded_batch(
        self,
        decoded_items: list[DecodedAudio],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[np.ndarray]:
        _check_cancelled(cancelled)
        self._load_model()
        assert self._processor is not None
        return self._embed_decoded_items(
            decoded_items,
            target_rate=int(self._processor.sampling_rate),
            cancelled=cancelled,
        )

    def _embed_decoded_items(
        self,
        decoded_items: list[DecodedAudio],
        *,
        target_rate: int,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None and self._processor is not None
        _check_cancelled(cancelled)
        track_sums = np.zeros((len(decoded_items), self.dim), dtype=np.float64)
        track_samples = [0] * len(decoded_items)
        window_batch: list[np.ndarray] = []
        window_owners: list[tuple[int, int]] = []
        prepare_seconds = inference_seconds = 0.0
        window_count = 0

        def flush_batch() -> None:
            nonlocal inference_seconds
            if not window_batch:
                return
            _check_cancelled(cancelled)
            started = time.perf_counter()
            pooled = self._pool_window_batch(window_batch, target_rate)
            inference_seconds += time.perf_counter() - started
            _check_cancelled(cancelled)
            if pooled.shape != (len(window_batch), self.dim) or not np.isfinite(pooled).all():
                raise ValueError("MERT produced invalid window embeddings")
            for vector, (owner, samples) in zip(pooled, window_owners, strict=True):
                track_sums[owner] += vector.astype(np.float64) * samples
                track_samples[owner] += samples
            window_batch.clear()
            window_owners.clear()

        for owner, decoded in enumerate(decoded_items):
            _check_cancelled(cancelled)
            started = time.perf_counter()
            waveform = decoded.audio.to(dtype=torch.float32)
            if waveform.ndim != 1 or waveform.numel() == 0:
                raise ValueError(f"MERT requires nonempty mono audio: {decoded.path}")
            if decoded.sample_rate != target_rate:
                if torchaudio is None:
                    raise RuntimeError(f"MERT shared-audio analysis requires torchaudio resampling: {decoded.path}")
                waveform = _resample_to(
                    waveform.unsqueeze(0),
                    source_rate=decoded.sample_rate,
                    target_rate=target_rate,
                    torchaudio=torchaudio,
                ).squeeze(0).to(dtype=torch.float32)
            if waveform.numel() < _MINIMUM_SAMPLES or not torch.isfinite(waveform).all().item():
                raise ValueError(f"MERT requires at least 400 finite samples at 24000 Hz: {decoded.path}")
            waveform = waveform.cpu()
            prepare_seconds += time.perf_counter() - started
            for window in _iter_mert_windows(waveform):
                _check_cancelled(cancelled)
                samples = window.numel()
                if window_batch and len(window_batch[0]) != samples:
                    flush_batch()
                window_batch.append(window.numpy())
                window_owners.append((owner, samples))
                window_count += 1
                if len(window_batch) == self.inference_batch_size:
                    flush_batch()
        flush_batch()
        _check_cancelled(cancelled)
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": window_count,
        }

        vectors = []
        for decoded, total, samples in zip(decoded_items, track_sums, track_samples, strict=True):
            vector = total / samples
            norm = np.linalg.norm(vector)
            if not np.isfinite(norm) or norm == 0:
                raise ValueError(f"MERT produced a zero or nonfinite vector: {decoded.path}")
            vectors.append((vector / norm).astype(np.float32))
        _check_cancelled(cancelled)
        return vectors

    def _pool_window_batch(self, window_batch: list[np.ndarray], target_rate: int) -> np.ndarray:
        torch = self._torch
        assert torch is not None and self._model is not None and self._processor is not None
        with self._inference_lock, torch.inference_mode():
            inputs = self._processor(window_batch, sampling_rate=target_rate, padding=False, return_tensors="pt")
            inputs = {key: value.to(self._device()) for key, value in inputs.items()}
            attention_mask = inputs["attention_mask"]
            device_type = inputs["input_values"].device.type
            use_bfloat16 = device_type == "cuda" and torch.cuda.is_bf16_supported(including_emulation=False)
            with torch.autocast(device_type=device_type, dtype=torch.bfloat16, enabled=use_bfloat16):
                outputs = self._model(**inputs, output_hidden_states=True)
            with torch.autocast(device_type=device_type, enabled=False):
                feature_mask = self._model._get_feature_vector_attention_mask(
                    outputs.hidden_states[self.hidden_layers[0]].shape[1], attention_mask,
                )
                pooled_layers = [
                    _masked_time_mean(outputs.hidden_states[index].float(), feature_mask)
                    for index in self.hidden_layers
                ]
                del outputs
                pooled = torch.stack(pooled_layers).mean(dim=0)
            return pooled.detach().cpu().numpy().astype(np.float32)

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            import torchaudio
            from transformers import AutoModel, Wav2Vec2FeatureExtractor

            self._torch = torch
            self._torchaudio = torchaudio
            binding = _bind_verified_local_snapshot(
                model_directory="mert",
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
    counts = mask.sum(dim=1)
    if (counts <= 0).any().item():
        raise ValueError("MERT feature mask contains no valid frames")
    return (hidden * mask).sum(dim=1) / counts


def _iter_mert_windows(waveform: Tensor) -> Iterator[Tensor]:
    """Yield consecutive views, merging only a sub-CNN-length final tail."""

    total = waveform.numel()
    if total < _MINIMUM_SAMPLES:
        raise ValueError("MERT requires at least 400 samples per window")
    if total <= _WINDOW_SAMPLES:
        yield waveform
        return
    full_windows, tail = divmod(total, _WINDOW_SAMPLES)
    if 0 < tail < _MINIMUM_SAMPLES:
        full_windows -= 1
    for index in range(full_windows):
        start = index * _WINDOW_SAMPLES
        yield waveform[start : start + _WINDOW_SAMPLES]
    if full_windows * _WINDOW_SAMPLES < total:
        yield waveform[full_windows * _WINDOW_SAMPLES :]


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise EmbeddingCancelledError("MERT embedding cancelled")
