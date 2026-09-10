from __future__ import annotations

import importlib
import threading
import time
from collections import defaultdict
from collections.abc import Sequence
from contextlib import ExitStack, contextmanager
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
from .loading import _local_model_path, _verify_checkpoint_sha256
from ..genres import rank_genres
from ..runtime import select_torch_device
from ..verified_assets import bind_verified_file


_MAEST_CONSTRUCTION_LOCK = threading.RLock()


@dataclass(frozen=True)
class MaestAnalysisResult:
    genres: list[dict[str, float | str]]
    embedding: np.ndarray
    mel_spectrogram: MaestMelSpectrogram | None = None


@dataclass(frozen=True)
class MaestMelSpectrogram:
    values: np.ndarray
    metadata: dict[str, object]

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
    pooling = "native-distilled-token-mean+storage-block-mean+l2"
    encoding = "float32-le"
    normalization = "l2"

    def __init__(
        self,
        device: str | None = None,
        top_k: int = 3,
        inference_batch_size: int = 16,
    ) -> None:
        self.requested_device = device or "auto"
        self.top_k = max(1, int(top_k))
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._load_lock = threading.RLock()
        self._inference_lock = threading.RLock()
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self.last_batch_timing: dict[str, float | int] = {}

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "adapter_revision": self.adapter_revision,
            "sample_rate_hz": self.target_rate,
            "audio_input": "full-track",
            "top_k": self.top_k,
            "inference_batch_size": self.inference_batch_size,
            "pooling": self.pooling,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "resampler": "torchaudio",
            "block_selection": "upstream-mel-contiguous-blocks",
            "tail_handling": "upstream-trim-incomplete-mel-block",
            "short_audio": "upstream-variable-length-mel",
            "model_input": "1d-raw-waveform-melspectrogram-input-false",
            "score_activation": "sigmoid-logits",
            "score_pooling": "upstream-sigmoid-then-block-mean-then-top-k",
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
        include_mel_spectrogram: bool = False,
    ) -> list[MaestAnalysisResult]:
        with self._inference_lock:
            return self._analyze_decoded_batch(
                decoded_items, include_mel_spectrogram=include_mel_spectrogram,
            )

    def _analyze_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
        *,
        include_mel_spectrogram: bool,
    ) -> list[MaestAnalysisResult]:
        self._load_model()
        torch = self._torch
        assert torch is not None and self._model is not None
        device = self._device()
        _move_maest_runtime_modules(self._model, device)
        expected_labels = list(self._model.labels)
        genres_by_track: list[list[dict[str, float | str]]] = []
        embedding_rows: list[np.ndarray] = []
        block_track_indexes: list[int] = []
        spectrograms: list[MaestMelSpectrogram | None] = []
        prepare_seconds = 0.0
        inference_seconds = 0.0
        for track_index, decoded in enumerate(decoded_items):
            prepare_started = time.perf_counter()
            waveform = self._prepare_audio_from_decoded(decoded).to(device)
            prepare_seconds += time.perf_counter() - prepare_started
            inference_started = time.perf_counter()
            with torch.inference_mode():
                captured: list[np.ndarray] = []
                head_outputs: list[tuple[Tensor, Tensor]] = []

                def capture_head(_module, args, output):
                    if len(args) != 1:
                        raise ValueError("Unexpected MAEST classification head input")
                    # The mean-distilled head receives the native block embeddings.
                    head_outputs.append((args[0], output))

                with ExitStack() as hooks:
                    hooks.enter_context(_maest_feature_batches(self._model, self.inference_batch_size, torch))
                    head_handle = self._model.head.register_forward_hook(capture_head)
                    hooks.callback(head_handle.remove)
                    if include_mel_spectrogram:
                        def capture_mel(_module, _args, output):
                            captured.append(output.detach().cpu().numpy().copy())

                        mel_handle = self._model.melspectrogram.register_forward_hook(capture_mel)
                        hooks.callback(mel_handle.remove)
                    scores, labels = self._model.predict_labels(waveform)
                if len(head_outputs) != 1:
                    raise ValueError("MAEST must produce exactly one classification head output")
                embeddings, logits = head_outputs[0]
                block_count = _validate_maest_output(
                    logits, name="logits", width=519,
                )
                _validate_maest_output(
                    embeddings, name="embeddings", width=self.dim,
                    expected_rows=block_count,
                )
                _validate_maest_predictions(scores, labels, expected_labels)
                embedding_rows.extend(
                    np.array(
                        embeddings.detach().cpu().numpy(), dtype=np.float32, copy=True,
                    )
                )
                spectrograms.append(
                    _maest_mel_spectrogram(self._model, captured, block_count)
                    if include_mel_spectrogram else None
                )
            inference_seconds += time.perf_counter() - inference_started
            genres_by_track.append(rank_genres(labels, scores.tolist(), self.top_k))
            block_track_indexes.extend([track_index] * block_count)
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": len(block_track_indexes),
        }

        # Storage needs one unit vector; native inference returns block embeddings.
        averaged_embeddings = _average_maest_embeddings(
            embedding_rows,
            block_track_indexes,
            expected_tracks=len(decoded_items),
        )
        return [
            MaestAnalysisResult(
                genres=genres,
                embedding=embedding,
                mel_spectrogram=spectrogram,
            )
            for genres, embedding, spectrogram in zip(
                genres_by_track, averaged_embeddings, spectrograms,
            )
        ]

    def _prepare_audio_from_decoded(self, decoded: DecodedAudio) -> Tensor:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None
        audio = decoded.audio.to(dtype=torch.float32)
        if audio.ndim != 1 or audio.numel() == 0:
            raise ValueError(f"MAEST requires non-empty mono audio: {decoded.path}")
        if decoded.sample_rate != self.target_rate:
            if torchaudio is None:
                raise RuntimeError(
                    "MAEST shared-audio analysis requires torchaudio resampling: "
                    f"{decoded.path}"
                )
            audio = _resample_to(
                audio.unsqueeze(0),
                source_rate=decoded.sample_rate,
                target_rate=self.target_rate,
                torchaudio=torchaudio,
            ).squeeze(0)
        return audio.to(dtype=torch.float32)

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
                )
            model = model.to(self.device).eval()
            _move_maest_runtime_modules(model, self.device)
            self._model = model

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)

@contextmanager
def _maest_feature_batches(model, batch_size: int, torch):
    """Bound native mel-block inference while preserving predict_labels/head pooling."""

    original = model.forward_features
    missing = object()
    original_binding = vars(model).get("forward_features", missing)

    def forward_features(blocks, **kwargs):
        if len(blocks) <= batch_size:
            return original(blocks, **kwargs)
        chunks = [original(batch, **kwargs) for batch in blocks.split(batch_size)]
        if any(not isinstance(chunk, tuple) or len(chunk) != 2 for chunk in chunks):
            raise ValueError("MAEST native features must contain CLS and distillation tokens")
        return tuple(torch.cat([chunk[index] for chunk in chunks], dim=0) for index in (0, 1))

    model.forward_features = forward_features
    try:
        yield
    finally:
        if original_binding is missing:
            del model.forward_features
        else:
            model.forward_features = original_binding


def _ensure_verified_maest_checkpoint(
    *,
    checkpoint_url: str,
    checkpoint_filename: str,
    expected_sha256: str,
) -> Path:
    """Verify the checkpoint in the repository's local model store."""

    checkpoint_path = _local_model_path("maest", checkpoint_filename)
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
):
    """Apply MAEST's native checkpoint adaptation without its cache resolver."""

    with _MAEST_CONSTRUCTION_LOCK:
        loaders = importlib.import_module("maest_infer.loading")
        model = get_maest(arch=arch, pretrained=False)
        state_dict = torch_module.load(
            str(checkpoint_path), map_location="cpu", weights_only=True,
        )
        state_dict = loaders.checkpoint_filter_fn(state_dict, model)
        first_conv = model.pretrained_cfg["first_conv"]
        weight_name = f"{first_conv}.weight"
        state_dict[weight_name] = loaders.adapt_input_conv(
            1, state_dict[weight_name],
        )
        model.load_state_dict(state_dict, strict=True)
        return model


def _move_maest_runtime_modules(model: object, device: str) -> None:
    init_melspectrogram = getattr(model, "init_melspectrogram", None)
    melspectrogram = getattr(model, "melspectrogram", None)
    if melspectrogram is None and callable(init_melspectrogram):
        init_melspectrogram()
    melspectrogram = getattr(model, "melspectrogram", None)
    move = getattr(melspectrogram, "to", None)
    if callable(move):
        move(device)

def _maest_mel_spectrogram(model, captured: list[np.ndarray], block_count: int) -> MaestMelSpectrogram:
    if len(captured) != 1:
        raise RuntimeError("MAEST must produce exactly one full-track mel spectrogram")
    values = captured[0]
    frontend = model.melspectrogram
    if values.dtype != np.float32 or values.ndim != 2 or values.shape[0] != frontend.n_mel:
        raise ValueError("Unexpected MAEST mel spectrogram shape or dtype")
    if not np.isfinite(values).all():
        raise ValueError("MAEST mel spectrogram contains non-finite values")
    values.setflags(write=False)
    frames_per_block = int(model.img_size[1])
    used_frames = min(values.shape[1], block_count * frames_per_block)
    return MaestMelSpectrogram(values, {
        "representation": "maest-normalized-log-mel",
        "axes": ["mel_band", "time_frame"],
        "sample_rate_hz": int(frontend.sr),
        "hop_length_samples": int(frontend.hop_len),
        "fft_size": int(frontend.win_len),
        "window_length_samples": int(frontend.spec.win_length),
        "center": bool(frontend.spec.center),
        "pad_mode": str(frontend.spec.pad_mode),
        "power": float(frontend.power),
        "mel_bands": int(frontend.n_mel),
        "mel_scale": str(frontend.mel_scale_type),
        "mel_norm": str(frontend.norm),
        "normalization": "(log10(1 + mel * 10000) - mean) / (2 * std)",
        "normalization_mean": float(frontend.norm_mean),
        "normalization_std": float(frontend.norm_std),
        "frames_per_native_block": frames_per_block,
        "native_blocks": block_count,
        "used_frames": used_frames,
        "discarded_tail_frames": values.shape[1] - used_frames,
        "includes_discarded_tail": True,
    })


def _validate_maest_output(
    values: Tensor | None,
    *,
    name: str,
    width: int,
    expected_rows: int | None = None,
) -> int:
    from torch import Tensor

    if values is None:
        raise ValueError(f"MAEST model did not return {name}")
    if not isinstance(values, Tensor):
        raise ValueError(f"MAEST model did not return tensor {name}")
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] != width:
        raise ValueError(f"Unsupported MAEST {name} shape: {tuple(values.shape)}")
    if expected_rows is not None and values.shape[0] != expected_rows:
        raise ValueError(
            "MAEST embedding row count does not match native logit block count"
        )
    if not values.isfinite().all():
        raise ValueError(f"MAEST model produced non-finite {name}")
    return int(values.shape[0])


def _validate_maest_predictions(scores, labels, expected_labels: list[str]) -> None:
    try:
        returned_labels = list(labels)
    except TypeError as exc:
        raise ValueError("MAEST predictions did not return ordered labels") from exc
    if len(expected_labels) != 519 or returned_labels != expected_labels:
        raise ValueError("MAEST predictions do not match the ordered Discogs-519 labels")
    if (
        not isinstance(scores, np.ndarray)
        or scores.shape != (519,)
        or not np.issubdtype(scores.dtype, np.floating)
    ):
        raise ValueError("MAEST predictions must contain 519 floating-point scores")
    if not np.isfinite(scores).all() or np.any(scores < 0.0) or np.any(scores > 1.0):
        raise ValueError("MAEST predictions must be finite probabilities in [0, 1]")


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
