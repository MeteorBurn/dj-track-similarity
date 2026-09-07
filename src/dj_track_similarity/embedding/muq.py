from __future__ import annotations

import threading
import time
import warnings

import numpy as np

from ..analysis_models import (
    MUQ_ADAPTER_REVISION,
    MUQ_CHECKPOINT_ID,
    MUQ_MODEL_NAME,
    MUQ_MODEL_REVISION,
    MUQ_PREPROCESSING,
    MUQ_SNAPSHOT_SHA256,
)
from ..audio.loader import DecodedAudio
from .audio import _prepare_windows
from .loading import _download_verified_hf_snapshot
from .numerics import _average_l2_window_embeddings, _normalize_rows
from ..runtime import select_torch_device

_MUQ_CONSTRUCTION_LOCK = threading.RLock()

_MUQ_WEIGHT_NORM_WARNING_SILENCED = False

class MuqEmbeddingAdapter:
    embedding_key = "muq"
    adapter_revision = MUQ_ADAPTER_REVISION
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
        window_seconds: float = 10.0,
        max_windows: int = 5,
        inference_batch_size: int = 8,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.window_seconds = window_seconds
        self.max_windows = max_windows
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._load_lock = threading.RLock()
        self._model = None
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
            "pooling": self.pooling,
            "dtype": self.dtype,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "resampler": "torchaudio",
            "window_selection": "10%-90%-interior-evenly-spaced-rounded",
            "short_audio": "right-zero-pad-to-window",
            "device_precision": "float32-eval-no-autocast-no-compile",
            "model_revision": self.model_revision,
            "checkpoint_filename": self.checkpoint_filename,
            "snapshot_files": self.snapshot_files,
            "snapshot_sha256": self.snapshot_sha256,
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def embed_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[np.ndarray]:
        self._load_model()
        return self._embed_decoded_items(decoded_items)

    def _embed_decoded_items(
        self,
        decoded_items: list[DecodedAudio],
    ) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None
        track_windows, all_windows, prepare_seconds = _prepare_windows(
            decoded_items,
            target_rate=self.target_rate,
            window_seconds=self.window_seconds,
            max_windows=self.max_windows,
            pad="zero",
            torch=torch,
            torchaudio=torchaudio,
            model_label="MuQ",
        )

        pooled_windows: list[np.ndarray] = []
        inference_started = time.perf_counter()
        for start in range(0, len(all_windows), self.inference_batch_size):
            wavs = torch.stack(
                all_windows[start : start + self.inference_batch_size],
                dim=0,
            ).to(device=self._device(), dtype=torch.float32)
            with torch.inference_mode():
                outputs = self._model(wavs, output_hidden_states=True)
            hidden = getattr(outputs, "last_hidden_state", None)
            if hidden is None:
                raise ValueError("MuQ model output does not include last_hidden_state")
            pooled_tensor = hidden.mean(dim=1)
            pooled_windows.extend(_normalize_rows(pooled_tensor.detach().cpu().numpy().astype(np.float32)))
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": len(all_windows),
        }

        return _average_l2_window_embeddings(pooled_windows, track_windows)

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            import torchaudio
            from huggingface_hub import snapshot_download
            import muq

            _silence_muq_weight_norm_deprecation()
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
            self._model = model.to(self.device).eval()

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)

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
