from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

import numpy as np

from ..analysis_models import (
    MERT_V2_CHECKPOINT_ID,
    MERT_V2_EMBEDDING_DIM,
    MERT_V2_MODEL_NAME,
    MERT_V2_MODEL_REVISION,
    MERT_V2_PREPROCESSING,
    MERT_V2_SNAPSHOT_SHA256,
)
from ..audio.loader import DecodedAudio
from ..runtime import select_torch_device
from .audio import _resample_to
from .contracts import EmbeddingCancelledError
from .loading import _bind_verified_local_snapshot

if TYPE_CHECKING:
    from torch import Tensor

_CHUNK_SAMPLES = 360 * 24_000
_MINIMUM_SAMPLES = 1025
_LAYER_COUNT = 24


class MertV2EmbeddingAdapter:
    embedding_key = "mert_v2"
    model_name = MERT_V2_MODEL_NAME
    model_revision = MERT_V2_MODEL_REVISION
    model_version = model_revision
    checkpoint_filename = "model.safetensors"
    checkpoint_id = MERT_V2_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    preprocessing = MERT_V2_PREPROCESSING
    dim = MERT_V2_EMBEDDING_DIM
    target_rate = 24_000
    chunk_seconds = 360.0
    pooling = "last-hidden-state+masked-time-mean+valid-frame-weighted-chunk-mean+l2"
    encoding = "float32-le"
    normalization = "l2"
    snapshot_files = (
        "config.json",
        "configuration_mert2.py",
        "modeling_mert2.py",
        "preprocessor_config.json",
        checkpoint_filename,
    )
    snapshot_sha256 = MERT_V2_SNAPSHOT_SHA256

    def __init__(
        self,
        device: str | None = None,
        inference_batch_size: int = 1,
    ) -> None:
        self.requested_device = device or "auto"
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
            "sample_rate_hz": self.target_rate,
            "chunk_seconds": self.chunk_seconds,
            "pooling": self.pooling,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "chunk_selection": "consecutive-full-coverage-no-overlap",
            "short_audio": "single-unpadded-chunk-minimum-1025-samples",
            "tail_policy": "shift-previous-boundary-to-retain-at-least-1025-samples",
            "processor_normalization": "none-preserve-waveform-amplitude",
            "processor_padding": "none-equal-length-batches-with-attention-mask",
            "hidden_state_extraction": "all-24-conformer-blocks-native-feature-attention-mask",
            "layer_pooling": "masked-time-mean+valid-frame-weighted-chunk-mean+per-layer-l2",
            "embedding_layers": list(range(1, _LAYER_COUNT + 1)),
            "track_accumulation": "cpu-float64-weighted-by-valid-output-frames",
            "dtype": "float32",
            "device_precision": "cuda-native-bfloat16-forward-autocast-otherwise-float32",
            "attn_implementation": "sdpa",
            "model_revision": self.model_revision,
            "remote_code_revision": self.model_revision,
            "checkpoint_filename": self.checkpoint_filename,
            "snapshot_files": self.snapshot_files,
            "snapshot_sha256": self.snapshot_sha256,
        }

    def preflight(self) -> None:
        self._load_model()

    def embed_decoded_batch(
        self,
        decoded_items: list[DecodedAudio],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[np.ndarray]:
        return [
            layers[-1]
            for layers in self.embed_decoded_layers_batch(decoded_items, cancelled=cancelled)
        ]

    def embed_decoded_layers_batch(
        self,
        decoded_items: list[DecodedAudio],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[tuple[np.ndarray, ...]]:
        """Return L1..L24 track vectors from one forward pass per audio chunk."""
        _check_cancelled(cancelled)
        self._load_model()
        torch = self._torch
        assert torch is not None and self._model is not None and self._processor is not None
        _check_cancelled(cancelled)
        track_sums = np.zeros((len(decoded_items), _LAYER_COUNT, self.dim), dtype=np.float64)
        track_frames = np.zeros(len(decoded_items), dtype=np.int64)
        chunk_batch: list[np.ndarray] = []
        chunk_owners: list[int] = []
        prepare_seconds = inference_seconds = 0.0
        chunk_count = 0

        def flush_batch() -> None:
            nonlocal inference_seconds
            if not chunk_batch:
                return
            _check_cancelled(cancelled)
            started = time.perf_counter()
            pooled, frame_counts = self._pool_chunk_batch(chunk_batch, cancelled=cancelled)
            inference_seconds += time.perf_counter() - started
            _check_cancelled(cancelled)
            if pooled.shape != (len(chunk_batch), _LAYER_COUNT, self.dim) or not np.isfinite(pooled).all():
                raise ValueError("MERT-v2 produced invalid chunk embeddings")
            for vector, frames, owner in zip(pooled, frame_counts, chunk_owners, strict=True):
                track_sums[owner] += vector.astype(np.float64) * frames
                track_frames[owner] += frames
            chunk_batch.clear()
            chunk_owners.clear()

        for owner, decoded in enumerate(decoded_items):
            _check_cancelled(cancelled)
            started = time.perf_counter()
            waveform = decoded.audio.to(dtype=torch.float32)
            if waveform.ndim != 1 or waveform.numel() == 0:
                raise ValueError(f"MERT-v2 requires nonempty mono audio: {decoded.path}")
            if decoded.sample_rate != self.target_rate:
                if self._torchaudio is None:
                    raise RuntimeError(f"MERT-v2 requires torchaudio resampling: {decoded.path}")
                _check_cancelled(cancelled)
                waveform = _resample_to(
                    waveform.unsqueeze(0),
                    source_rate=decoded.sample_rate,
                    target_rate=self.target_rate,
                    torchaudio=self._torchaudio,
                ).squeeze(0).to(dtype=torch.float32)
                _check_cancelled(cancelled)
            if waveform.numel() < _MINIMUM_SAMPLES or not torch.isfinite(waveform).all().item():
                raise ValueError(f"MERT-v2 requires at least 1025 finite samples at 24000 Hz: {decoded.path}")
            waveform = waveform.cpu()
            prepare_seconds += time.perf_counter() - started
            for chunk in _iter_mert_v2_chunks(waveform):
                _check_cancelled(cancelled)
                if chunk_batch and len(chunk_batch[0]) != chunk.numel():
                    flush_batch()
                chunk_batch.append(chunk.numpy())
                chunk_owners.append(owner)
                chunk_count += 1
                if len(chunk_batch) == self.inference_batch_size:
                    flush_batch()
        flush_batch()
        _check_cancelled(cancelled)
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "chunks": chunk_count,
        }
        vectors = []
        for decoded, total, frames in zip(decoded_items, track_sums, track_frames, strict=True):
            if frames <= 0:
                raise ValueError(f"MERT-v2 produced no valid frames: {decoded.path}")
            vector = total / frames
            norms = np.linalg.norm(vector, axis=1, keepdims=True)
            if not np.isfinite(norms).all() or np.any(norms == 0):
                raise ValueError(f"MERT-v2 produced a zero or nonfinite vector: {decoded.path}")
            vectors.append(tuple((vector / norms).astype(np.float32)))
        _check_cancelled(cancelled)
        return vectors

    def _pool_chunk_batch(
        self,
        chunks: list[np.ndarray],
        *,
        cancelled: Callable[[], bool] | None,
    ) -> tuple[np.ndarray, np.ndarray]:
        torch = self._torch
        assert torch is not None and self._model is not None and self._processor is not None
        with self._inference_lock, torch.inference_mode():
            _check_cancelled(cancelled)
            inputs = self._processor(chunks, sampling_rate=self.target_rate, padding=False, return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            device_type = inputs["input_values"].device.type
            use_bfloat16 = device_type == "cuda" and torch.cuda.is_bf16_supported(including_emulation=False)
            with torch.autocast(device_type=device_type, dtype=torch.bfloat16, enabled=use_bfloat16):
                outputs = self._model(**inputs, output_hidden_states=True, return_dict=True)
            _check_cancelled(cancelled)
            states = outputs.hidden_states
            mask = outputs.feature_attention_mask
            if not isinstance(states, (tuple, list)) or len(states) != _LAYER_COUNT:
                raise ValueError("MERT-v2 must return exactly 24 hidden-state layers")
            if mask is None or mask.dtype != torch.bool or mask.ndim != 2:
                raise ValueError("MERT-v2 returned an invalid feature mask")
            frame_counts = mask.sum(dim=1)
            if (frame_counts <= 0).any().item():
                raise ValueError("MERT-v2 feature mask contains no valid frames")
            layers = []
            for hidden in states:
                _check_cancelled(cancelled)
                if hidden.ndim != 3 or hidden.shape[2] != self.dim or tuple(hidden.shape[:2]) != tuple(mask.shape):
                    raise ValueError("MERT-v2 feature mask does not match hidden states")
                pooled = hidden.masked_fill(~mask.unsqueeze(-1), 0).sum(dim=1, dtype=torch.float32)
                pooled = pooled / frame_counts.unsqueeze(-1)
                layers.append(pooled.detach().cpu().numpy())
            return np.stack(layers, axis=1), frame_counts.cpu().numpy()

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            import torchaudio
            from transformers import AutoModel, Wav2Vec2FeatureExtractor

            device = select_torch_device(torch, self.requested_device)
            binding = _bind_verified_local_snapshot(
                model_directory="mert-v2",
                repo_id=self.model_name,
                revision=self.model_revision,
                required_files=self.snapshot_files,
                expected_sha256=self.snapshot_sha256,
                checkpoint_filename=self.checkpoint_filename,
                expected_checkpoint_sha256=self.checkpoint_sha256,
            )
            with binding as verified:
                snapshot_path = str(verified.path)
                processor = Wav2Vec2FeatureExtractor.from_pretrained(snapshot_path, local_files_only=True)
                if int(processor.sampling_rate) != self.target_rate or processor.do_normalize:
                    raise RuntimeError("Local MERT-v2 processor must preserve amplitude at 24000 Hz")
                model = AutoModel.from_pretrained(
                    snapshot_path,
                    trust_remote_code=True,
                    local_files_only=True,
                    use_safetensors=True,
                    attn_implementation="sdpa",
                )
                model = model.float().to(device).eval()
            self._torch = torch
            self._torchaudio = torchaudio
            self.device = device
            self._processor = processor
            self._model = model


def _iter_mert_v2_chunks(waveform: Tensor) -> Iterator[Tensor]:
    """Keep the full signal within 360-second contexts, without padding or overlap."""

    total = waveform.numel()
    if total < _MINIMUM_SAMPLES:
        raise ValueError("MERT-v2 requires at least 1025 samples per chunk")
    start = 0
    while start < total:
        end = min(start + _CHUNK_SAMPLES, total)
        if 0 < total - end < _MINIMUM_SAMPLES:
            end = total - _MINIMUM_SAMPLES
        yield waveform[start:end]
        start = end


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise EmbeddingCancelledError("MERT-v2 embedding cancelled")
