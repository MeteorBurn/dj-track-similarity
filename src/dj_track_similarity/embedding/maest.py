from __future__ import annotations

import importlib
import threading
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from torch import Tensor
from ..analysis_models import (
    MAEST_ADAPTER_REVISION,
    MAEST_CHECKPOINT_ID,
    MAEST_MODEL_NAME,
    MAEST_MODEL_VERSION,
    MAEST_PREPROCESSING,
)
from ..audio.loader import DecodedAudio
from .audio import _resample_to
from .loading import _verify_checkpoint_sha256
from ..genres import rank_maest_genres
from ..maest_windows import (
    MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS,
    MAEST_WINDOW_POSITIONS,
    MaestWindowContext,
    select_maest_window_starts,
)
from ..runtime import select_torch_device
from ..verified_assets import bind_verified_file


_MAEST_CONSTRUCTION_LOCK = threading.RLock()


@dataclass(frozen=True)
class MaestAnalysisResult:
    genres: list[dict[str, float | str]]
    embedding: np.ndarray

class MaestEmbeddingAdapter:
    embedding_key = "maest"
    adapter_revision = MAEST_ADAPTER_REVISION
    model_name = MAEST_MODEL_NAME
    checkpoint_release = "v0.0.0-beta"
    checkpoint_filename = "discogs-maest-30s-pw-129e-519l-swa.ckpt"
    checkpoint_url = (
        "https://github.com/palonso/MAEST/releases/download/"
        f"{checkpoint_release}/{checkpoint_filename}"
    )
    checkpoint_id = MAEST_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    model_version = MAEST_MODEL_VERSION
    preprocessing = MAEST_PREPROCESSING
    dim = 768
    target_rate = 16_000
    input_seconds = 30.0
    analysis_window_positions = MAEST_WINDOW_POSITIONS
    pooling = "distilled-token-mean+window-mean+l2"
    encoding = "float32-le"
    normalization = "l2"

    def __init__(
        self,
        device: str | None = None,
        top_k: int = 3,
        inference_batch_size: int = 8,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = (
            None if self.requested_device == "auto" else self.requested_device
        )
        self.top_k = max(1, int(top_k))
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
            "input_seconds": self.input_seconds,
            "analysis_window_positions": self.analysis_window_positions,
            "top_k": self.top_k,
            "pooling": self.pooling,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "resampler": "torchaudio",
            "window_selection": "structure-aware-main-range-centered-20-50-80",
            "window_context": "sonara-current-generation-optional",
            "window_fallback": "main-range->non-silent-range->full-duration",
            "window_dedup_tolerance_seconds": MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS,
            "short_audio": "right-zero-pad-to-30s",
            "model_input": "raw-waveform-melspectrogram-input-false",
            "score_activation": "sigmoid-logits",
            "score_pooling": "window-mean-then-top-k",
            "dtype": "float32",
            "device_precision": "float32-eval",
            "checkpoint_release": self.checkpoint_release,
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def analyze_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
        *,
        window_contexts: Sequence[MaestWindowContext | None] | None = None,
    ) -> list[MaestAnalysisResult]:
        self._load_model()
        torch = self._torch
        assert torch is not None
        contexts = (
            [None] * len(decoded_items)
            if window_contexts is None
            else list(window_contexts)
        )
        if len(contexts) != len(decoded_items):
            raise ValueError("MAEST window context count does not match track count")

        prepared: list[object] = []
        window_track_indexes: list[int] = []
        prepare_started = time.perf_counter()
        for track_index, (decoded, context) in enumerate(zip(decoded_items, contexts)):
            windows = self._prepare_audio_windows_from_audio(
                decoded.path,
                decoded.audio,
                decoded.sample_rate,
                window_context=context,
            )
            prepared.extend(windows)
            window_track_indexes.extend([track_index] * len(windows))
        prepare_seconds = time.perf_counter() - prepare_started
        return self._analyze_prepared_batch(
            prepared,
            window_track_indexes,
            expected_tracks=len(decoded_items),
            prepare_seconds=prepare_seconds,
        )

    def _analyze_prepared_batch(
        self,
        prepared: Sequence[object],
        window_track_indexes: Sequence[int],
        *,
        expected_tracks: int,
        prepare_seconds: float,
    ) -> list[MaestAnalysisResult]:
        torch = self._torch
        assert torch is not None and self._model is not None
        device = self._device()
        _move_maest_runtime_modules(self._model, device)

        score_rows: list[list[float]] = []
        embedding_rows: list[np.ndarray] = []
        inference_started = time.perf_counter()
        with torch.inference_mode():
            for start in range(0, len(prepared), self.inference_batch_size):
                chunk = prepared[start : start + self.inference_batch_size]
                audio_batch = torch.stack(chunk, dim=0).to(device)
                logits, embeddings = self._model(
                    audio_batch,
                    melspectrogram_input=False,
                )
                score_rows.extend(
                    _maest_score_rows(
                        torch.sigmoid(logits),
                        expected_rows=len(chunk),
                    )
                )
                embedding_rows.extend(
                    _maest_embedding_rows(embeddings, expected_rows=len(chunk))
                )
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": expected_tracks,
            "windows": len(prepared),
        }

        labels = [str(label) for label in getattr(self._model, "labels")]
        genres_by_track = rank_maest_genres(
            labels,
            score_rows,
            window_track_indexes,
            expected_tracks=expected_tracks,
            top_k=self.top_k,
        )
        averaged_embeddings = _average_maest_embeddings(
            embedding_rows,
            window_track_indexes,
            expected_tracks=expected_tracks,
        )
        return [
            MaestAnalysisResult(
                genres=genres,
                embedding=embedding,
            )
            for genres, embedding in zip(genres_by_track, averaged_embeddings)
        ]

    def _prepare_audio_windows_from_audio(
        self,
        path: str | Path,
        audio_values: Tensor,
        sample_rate: int,
        *,
        window_context: MaestWindowContext | None = None,
    ) -> list[object]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None
        audio = audio_values.to(dtype=torch.float32).unsqueeze(0)
        if sample_rate != self.target_rate:
            if torchaudio is None:
                raise RuntimeError(
                    "MAEST shared-audio analysis requires torchaudio resampling: "
                    f"{path}"
                )
            audio = _resample_to(
                audio,
                source_rate=sample_rate,
                target_rate=self.target_rate,
                torchaudio=torchaudio,
            )
        audio = audio.squeeze(0)
        target_samples = int(self.target_rate * self.input_seconds)
        if audio.numel() < target_samples:
            return [
                torch.nn.functional.pad(
                    audio,
                    (0, target_samples - audio.numel()),
                )
            ]

        starts = select_maest_window_starts(
            audio.numel() / self.target_rate,
            self.input_seconds,
            window_context,
        )
        windows: list[object] = []
        for start_seconds in starts:
            start = max(0, int(self.target_rate * start_seconds))
            segment = audio[start : start + target_samples]
            if segment.numel() < target_samples:
                segment = torch.nn.functional.pad(
                    segment,
                    (0, target_samples - segment.numel()),
                )
            windows.append(segment)
        return windows or [audio[:target_samples]]

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            import torchaudio
            from maest_infer import get_maest

            self._torch = torch
            self._torchaudio = torchaudio
            self.device = self._device()
            checkpoint = _ensure_verified_maest_checkpoint(
                torch,
                checkpoint_url=self.checkpoint_url,
                checkpoint_filename=self.checkpoint_filename,
                expected_sha256=self.checkpoint_sha256,
            )
            with bind_verified_file(
                checkpoint,
                expected_sha256=self.checkpoint_sha256,
                description=self.checkpoint_filename,
            ) as verified:
                model = _construct_maest_with_local_checkpoint(
                    get_maest,
                    torch_module=torch,
                    arch=self.model_name,
                    checkpoint_path=verified.path,
                    checkpoint_url=self.checkpoint_url,
                )
            model = model.to(self.device).eval()
            _move_maest_runtime_modules(model, self.device)
            self._model = model

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)

def _ensure_verified_maest_checkpoint(
    torch_module,
    *,
    checkpoint_url: str,
    checkpoint_filename: str,
    expected_sha256: str,
) -> Path:
    """Verify an existing local checkpoint; never populate the cache online."""

    checkpoint_dir = Path(torch_module.hub.get_dir()) / "checkpoints"
    checkpoint_path = checkpoint_dir / checkpoint_filename
    if not checkpoint_path.is_file():
        raise RuntimeError(
            f"Local MAEST checkpoint is missing: {checkpoint_path}. "
            "Automatic model downloads are disabled."
        )
    _verify_checkpoint_sha256(
        checkpoint_path,
        expected_sha256=expected_sha256,
        description=checkpoint_url,
    )
    return checkpoint_path

def _construct_maest_with_local_checkpoint(
    get_maest,
    *,
    torch_module,
    arch: str,
    checkpoint_path: Path,
    checkpoint_url: str,
):
    """Retain MAEST's checkpoint filters while replacing its URL resolver."""

    with _MAEST_CONSTRUCTION_LOCK:
        loaders = importlib.import_module("maest_infer.helpers.vit_helpers")
        original_loader = loaders.load_state_dict_from_url

        def load_local(url, *, map_location, progress, check_hash):
            if url != checkpoint_url or map_location != "cpu":
                raise RuntimeError(f"Unexpected MAEST checkpoint request: {url}")
            return torch_module.load(
                str(checkpoint_path), map_location="cpu", weights_only=True,
            )

        loaders.load_state_dict_from_url = load_local
        try:
            return get_maest(arch=arch)
        finally:
            loaders.load_state_dict_from_url = original_loader


def _move_maest_runtime_modules(model: object, device: str) -> None:
    init_melspectrogram = getattr(model, "init_melspectrogram", None)
    melspectrogram = getattr(model, "melspectrogram", None)
    if melspectrogram is None and callable(init_melspectrogram):
        init_melspectrogram()
    melspectrogram = getattr(model, "melspectrogram", None)
    move = getattr(melspectrogram, "to", None)
    if callable(move):
        move(device)

def _maest_score_rows(values: object, *, expected_rows: int) -> list[list[float]]:
    detach = getattr(values, "detach", None)
    if callable(detach):
        values = detach()
    cpu = getattr(values, "cpu", None)
    if callable(cpu):
        values = cpu()
    numpy = getattr(values, "numpy", None)
    if callable(numpy):
        values = numpy()

    shape = getattr(values, "shape", None)
    if shape is not None and len(shape) >= 2:
        rows = [
            [float(score) for score in row] for row in values  # type: ignore[union-attr]
        ]
        if len(rows) != expected_rows:
            raise ValueError(
                "MAEST batch output shape does not match the requested batch size"
            )
        return rows

    flat = _maest_float_list(values)
    if expected_rows == 1:
        return [flat]
    raise ValueError("MAEST batch output shape does not include per-track rows")

def _maest_float_list(values: object) -> list[float]:
    detach = getattr(values, "detach", None)
    if callable(detach):
        values = detach()
    cpu = getattr(values, "cpu", None)
    if callable(cpu):
        values = cpu()
    numpy = getattr(values, "numpy", None)
    if callable(numpy):
        values = numpy()
    reshape = getattr(values, "reshape", None)
    if callable(reshape):
        values = reshape(-1)
    return [float(value) for value in values]  # type: ignore[union-attr]

def _maest_embedding_rows(
    values: object,
    *,
    expected_rows: int,
) -> list[np.ndarray]:
    if values is None:
        raise ValueError("MAEST model did not return embeddings")
    detach = getattr(values, "detach", None)
    if callable(detach):
        values = detach()
    cpu = getattr(values, "cpu", None)
    if callable(cpu):
        values = cpu()
    numpy = getattr(values, "numpy", None)
    if callable(numpy):
        values = numpy()
    array = np.asarray(values, dtype=np.float32)
    if array.ndim == 3:
        array = array.mean(axis=1)
    if array.ndim != 2:
        raise ValueError(f"Unsupported MAEST embedding shape: {array.shape}")
    if array.shape[0] != expected_rows:
        raise ValueError(
            "MAEST embedding row count does not match audio window count"
        )
    return [array[index].astype(np.float32, copy=True) for index in range(array.shape[0])]

def _average_maest_embeddings(
    rows: Sequence[np.ndarray],
    window_track_indexes: Sequence[int],
    *,
    expected_tracks: int,
) -> list[np.ndarray]:
    grouped: dict[int, list[np.ndarray]] = defaultdict(list)
    for row, track_index in zip(rows, window_track_indexes):
        grouped[track_index].append(row)

    embeddings: list[np.ndarray] = []
    for track_index in range(expected_tracks):
        track_rows = grouped.get(track_index, [])
        if not track_rows:
            raise ValueError("MAEST did not produce embeddings for every track")
        vector = np.mean(np.vstack(track_rows), axis=0).astype(np.float32)
        if not np.isfinite(vector).all():
            raise ValueError("MAEST model produced non-finite embeddings")
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or norm <= 0.0:
            raise ValueError("MAEST model produced a zero embedding")
        embeddings.append(np.asarray(vector / norm, dtype=np.float32))
    return embeddings
