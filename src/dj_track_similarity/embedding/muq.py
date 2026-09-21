from __future__ import annotations

import threading
import time
import warnings
from collections.abc import Callable

import numpy as np

from ..analysis_models import (
    EMBEDDING_LAYERS,
    MUQ_CHECKPOINT_ID,
    MUQ_MODEL_NAME,
    MUQ_MODEL_REVISION,
    MUQ_PREPROCESSING,
    MUQ_SNAPSHOT_SHA256,
)
from ..audio.loader import DecodedAudio
from .audio import _prepare_windows
from .contracts import EmbeddingCancelledError
from .loading import _bind_verified_local_snapshot
from .numerics import _average_l2_window_embeddings, _normalize_rows
from ..runtime import select_torch_device

_MUQ_CONSTRUCTION_LOCK = threading.RLock()
# Layer 1 is hidden_states[0], the conv front end; layer k + 1 follows
# conformer block k; layer 13 is hidden_states[12], the last hidden state.
_LAYERS = EMBEDDING_LAYERS["muq"]

_MUQ_WEIGHT_NORM_WARNING_SILENCED = False

class MuqEmbeddingAdapter:
    embedding_key = "muq"
    model_name = MUQ_MODEL_NAME
    model_revision = MUQ_MODEL_REVISION
    model_version = model_revision
    checkpoint_filename = "model.safetensors"
    checkpoint_id = MUQ_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    preprocessing = MUQ_PREPROCESSING
    dim = 1024
    target_rate = 24_000
    pooling = "last-hidden-time-mean+per-window-l2+window-mean+l2"
    dtype = "float32"
    encoding = "float32-le"
    normalization = "l2"
    snapshot_files = ("config.json", checkpoint_filename)
    snapshot_sha256 = MUQ_SNAPSHOT_SHA256

    def __init__(
        self,
        device: str | None = None,
        window_seconds: float = 30.0,
        inference_batch_size: int = 8,
    ) -> None:
        self.requested_device = device or "auto"
        self.window_seconds = window_seconds
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._load_lock = threading.RLock()
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self.last_batch_timing: dict[str, float | int] = {}

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "sample_rate_hz": self.target_rate,
            "window_seconds": self.window_seconds,
            "pooling": self.pooling,
            "dtype": self.dtype,
            "channel_downmix": "arithmetic-mean",
            "decoder": "shared-torchcodec-0.16",
            "resampler": "torchaudio",
            "window_selection": "consecutive-full-coverage-end-aligned-tail",
            "short_audio": "right-zero-pad-to-window",
            "hidden_state_extraction": "all-13-hidden-states-conv-front-end-then-12-conformer-blocks",
            "layer_pooling": "time-mean+per-window-l2+window-mean+per-layer-l2",
            "embedding_layers": list(range(1, _LAYERS.count + 1)),
            "device_precision": "cuda-float16-autocast-float32-mel-otherwise-float32-eval-no-compile",
            "model_revision": self.model_revision,
            "checkpoint_filename": self.checkpoint_filename,
            "snapshot_files": self.snapshot_files,
            "snapshot_sha256": self.snapshot_sha256,
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def embed_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[np.ndarray]:
        return [
            layers[_LAYERS.default - 1]
            for layers in self.embed_decoded_layers_batch(decoded_items)
        ]

    def embed_decoded_layers_batch(
        self,
        decoded_items: list[DecodedAudio],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[tuple[np.ndarray, ...]]:
        """Return layers 1..13 per track from one forward pass per window batch."""

        _check_cancelled(cancelled)
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None
        track_windows, all_windows, prepare_seconds = _prepare_windows(
            decoded_items,
            target_rate=self.target_rate,
            window_seconds=self.window_seconds,
            torch=torch,
            torchaudio=torchaudio,
            model_label="MuQ",
        )

        pooled_windows: list[list[np.ndarray]] = [[] for _ in range(_LAYERS.count)]
        inference_started = time.perf_counter()
        for start in range(0, len(all_windows), self.inference_batch_size):
            _check_cancelled(cancelled)
            wavs = torch.stack(
                all_windows[start : start + self.inference_batch_size],
                dim=0,
            ).to(device=self._device(), dtype=torch.float32)
            for layer_windows, rows in zip(
                pooled_windows, self._pooled_hidden_states(wavs), strict=True,
            ):
                layer_windows.extend(rows)
        inference_seconds = time.perf_counter() - inference_started
        _check_cancelled(cancelled)
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": len(all_windows),
        }

        layer_tracks = [
            _average_l2_window_embeddings(layer_windows, track_windows)
            for layer_windows in pooled_windows
        ]
        return [tuple(track_layers) for track_layers in zip(*layer_tracks)]

    def _pooled_hidden_states(self, wavs) -> list[list[np.ndarray]]:
        """L2 window rows of every hidden state's time mean, one list per layer.

        Only pooled rows leave this call, so a batch's 13 hidden states are
        freed before the next forward pass instead of staying alive through it.
        """

        torch = self._torch
        assert torch is not None and self._model is not None
        # Float16 halves the conv and conformer activations of 30 s windows;
        # the mel front end stays float32 (see _load_model).
        with torch.inference_mode(), torch.autocast(
            device_type="cuda",
            dtype=torch.float16,
            enabled=self._device().startswith("cuda"),
        ):
            outputs = self._model(wavs, output_hidden_states=True)
        states = getattr(outputs, "hidden_states", None)
        if not isinstance(states, (tuple, list)) or len(states) != _LAYERS.count:
            raise ValueError(f"MuQ must return exactly {_LAYERS.count} hidden states")
        return [
            _normalize_rows(hidden.mean(dim=1).float().detach().cpu().numpy().astype(np.float32))
            for hidden in states
        ]

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            import torchaudio
            import muq

            _silence_muq_weight_norm_deprecation()
            self._torch = torch
            self._torchaudio = torchaudio
            binding = _bind_verified_local_snapshot(
                model_directory="muq",
                repo_id=self.model_name,
                revision=self.model_revision,
                required_files=self.snapshot_files,
                expected_sha256=self.snapshot_sha256,
                checkpoint_filename=self.checkpoint_filename,
                expected_checkpoint_sha256=self.checkpoint_sha256,
            )
            with binding as verified, _MUQ_CONSTRUCTION_LOCK:
                # Read under the lock: MuQ-MuLan construction rebinds this
                # attribute to a proxy that only accepts its own snapshot.
                MuQ = muq.MuQ
                self.device = self._device()
                model = MuQ.from_pretrained(
                    str(verified.path),
                    local_files_only=True,
                )
            to_float = getattr(model, "float", None)
            if callable(to_float):
                model = to_float()
            _keep_mel_in_float32(model, torch)
            self._model = model.to(self.device).eval()

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)

def _keep_mel_in_float32(model, torch) -> None:
    """Run MuQ's mel front end outside autocast.

    Its mel filterbank product is autocast to float16 even though the input is
    cast to float32, and the power spectrum overflows float16 (max 65504) into
    non-finite features. Only the conv and conformer run in reduced precision.
    """

    inner = model.model
    preprocessing = inner.preprocessing

    def float32_preprocessing(x, features):
        with torch.autocast(device_type="cuda", enabled=False):
            return preprocessing(x, features)

    inner.preprocessing = float32_preprocessing


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise EmbeddingCancelledError("MuQ embedding cancelled")


def _silence_muq_weight_norm_deprecation() -> None:
    """muq builds its conformer with the deprecated torch weight_norm helper."""

    global _MUQ_WEIGHT_NORM_WARNING_SILENCED
    if _MUQ_WEIGHT_NORM_WARNING_SILENCED:
        return
    warnings.filterwarnings(
        "ignore",
        message=r".*torch\.nn\.utils\.weight_norm.* is deprecated.*",
        category=FutureWarning,
    )
    _MUQ_WEIGHT_NORM_WARNING_SILENCED = True
