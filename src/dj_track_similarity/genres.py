from __future__ import annotations

from collections import defaultdict
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path
import time

import numpy as np

from .analysis_models import (
    MAEST_ADAPTER_REVISION,
    MAEST_CHECKPOINT_ID,
    MAEST_MODEL_NAME,
    MAEST_MODEL_VERSION,
    MAEST_PREPROCESSING,
)
from .audio_loader import DecodedAudio, load_audio_mono, torch_compatible_audio
from .runtime import select_torch_device
from .verified_assets import VerifiedAssetBinding, bind_verified_file


class MaestGenreAdapter:
    embedding_key = "maest"
    adapter_revision = MAEST_ADAPTER_REVISION
    model_name = MAEST_MODEL_NAME
    package_name = "maest-infer"
    package_version = "0.1.0"
    package_wheel_sha256 = "1638ad5b6590ffecadbd9b71f7d4f0e0a9beb5d3862dde0ee447323a1e693e6e"
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
    analysis_offset_seconds = 60.0
    analysis_window_ratios = (0.38, 0.72)
    pooling = "distilled-token-mean+window-mean+l2"
    encoding = "float32-le"
    normalization = "l2"

    def __init__(self, device: str | None = None, top_k: int = 3, inference_batch_size: int = 8) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.top_k = max(1, int(top_k))
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self._embeddings_by_path: dict[str, np.ndarray] = {}
        self.last_batch_timing: dict[str, float | int] = {}

    def contract_parameters(self) -> dict[str, object]:
        return {
            "adapter_revision": self.adapter_revision,
            "sample_rate_hz": self.target_rate,
            "input_seconds": self.input_seconds,
            "analysis_offset_seconds": self.analysis_offset_seconds,
            "analysis_window_ratios": self.analysis_window_ratios,
            "top_k": self.top_k,
            "pooling": self.pooling,
            "channel_downmix": "arithmetic-mean",
            "decoder": "shared-load-audio-mono-v1",
            "resampler": "torchaudio",
            "window_selection": "offset60s+duration-ratios-0.38,0.72-clamped-dedup-1s",
            "short_audio": "right-zero-pad-to-30s",
            "model_input": "raw-waveform-melspectrogram-input-false",
            "score_activation": "sigmoid-logits",
            "score_pooling": "window-mean-then-top-k",
            "dtype": "float32",
            "device_precision": "float32-eval",
            "loader_package": f"{self.package_name}=={self.package_version}",
            "package_wheel_sha256": self.package_wheel_sha256,
            "checkpoint_release": self.checkpoint_release,
        }

    def predict(self, path: str | Path) -> list[dict[str, float | str]]:
        return self.predict_batch([path])[0]

    def preflight(self) -> None:
        """Verify and construct the pinned loader before contract activation."""

        self._load_model()

    def predict_batch(self, paths: list[str | Path]) -> list[list[dict[str, float | str]]]:
        self._load_model()
        prepared = []
        window_track_indexes: list[int] = []
        decode_seconds = 0.0
        prepare_started = time.perf_counter()
        for track_index, path in enumerate(paths):
            windows, window_decode_seconds = self._prepare_audio_windows_with_timing(path)
            decode_seconds += window_decode_seconds
            prepared.extend(windows)
            window_track_indexes.extend([track_index] * len(windows))
        prepare_seconds = time.perf_counter() - prepare_started
        return self._predict_prepared_batch([str(path) for path in paths], prepared, window_track_indexes, decode_seconds, prepare_seconds)

    def predict_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[list[dict[str, float | str]]]:
        self._load_model()
        prepared = []
        window_track_indexes: list[int] = []
        prepare_started = time.perf_counter()
        for track_index, decoded in enumerate(decoded_items):
            windows = self._prepare_audio_windows_from_audio(decoded.path, decoded.audio, decoded.sample_rate)
            prepared.extend(windows)
            window_track_indexes.extend([track_index] * len(windows))
        prepare_seconds = time.perf_counter() - prepare_started
        return self._predict_prepared_batch(
            [str(decoded.path) for decoded in decoded_items],
            prepared,
            window_track_indexes,
            0.0,
            prepare_seconds,
        )

    def _predict_prepared_batch(
        self,
        paths: list[str],
        prepared: list[object],
        window_track_indexes: list[int],
        decode_seconds: float,
        prepare_seconds: float,
    ) -> list[list[dict[str, float | str]]]:
        torch = self._torch
        assert torch is not None and self._model is not None
        device = self._device()
        _move_maest_runtime_modules(self._model, device)

        inference_started = time.perf_counter()
        rows: list[list[float]] = []
        embedding_rows: list[np.ndarray] = []
        with torch.inference_mode():
            for start in range(0, len(prepared), self.inference_batch_size):
                chunk = prepared[start : start + self.inference_batch_size]
                audio_batch = torch.stack(chunk, dim=0).to(device)
                logits, embeddings = self._model(audio_batch, melspectrogram_input=False)
                activations = torch.sigmoid(logits)
                rows.extend(_to_score_rows(activations, expected_rows=len(chunk)))
                embedding_rows.extend(_embedding_rows(embeddings, expected_rows=len(chunk)))
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "decode_seconds": decode_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(paths),
            "windows": len(prepared),
        }

        self._embeddings_by_path = self._average_embeddings_by_path(paths, embedding_rows, window_track_indexes)
        averaged_rows = _average_window_rows(rows, window_track_indexes, expected_tracks=len(paths))
        label_values = [str(label) for label in getattr(self._model, "labels")]
        return [_rank_genres(label_values, scores, self.top_k) for scores in averaged_rows]

    def embedding_for_path(self, path: str | Path) -> np.ndarray | None:
        return self._embeddings_by_path.get(str(path))

    def _prepare_audio(self, path: str | Path):
        return self._prepare_audio_windows(path)[0]

    def _prepare_audio_windows(self, path: str | Path):
        return self._prepare_audio_windows_with_timing(path)[0]

    def _prepare_audio_windows_with_timing(self, path: str | Path):
        torchaudio = self._torchaudio
        assert torchaudio is not None

        decode_started = time.perf_counter()
        audio_values, sample_rate, _decode_detail = load_audio_mono(
            path,
            torchaudio_module=torchaudio,
        )
        decode_seconds = time.perf_counter() - decode_started
        return self._prepare_audio_windows_from_audio(path, audio_values, sample_rate), decode_seconds

    def _prepare_audio_windows_from_audio(self, path: str | Path, audio_values: np.ndarray, sample_rate: int):
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None
        audio = torch.from_numpy(torch_compatible_audio(audio_values)).unsqueeze(0)
        if sample_rate != self.target_rate:
            if torchaudio is None:
                raise RuntimeError(f"MAEST shared-audio analysis requires torchaudio resampling: {path}")
            audio = torchaudio.transforms.Resample(sample_rate, self.target_rate)(audio)
        audio = audio.squeeze(0)
        target_samples = int(self.target_rate * self.input_seconds)
        if audio.numel() < target_samples:
            return [torch.nn.functional.pad(audio, (0, target_samples - audio.numel()))]

        starts = _analysis_window_starts(
            audio.numel() / self.target_rate,
            self.input_seconds,
            self.analysis_offset_seconds,
            self.analysis_window_ratios,
        )
        windows = []
        for start_seconds in starts:
            start = max(0, int(self.target_rate * start_seconds))
            segment = audio[start : start + target_samples]
            if segment.numel() < target_samples:
                segment = torch.nn.functional.pad(segment, (0, target_samples - segment.numel()))
            windows.append(segment)
        return windows or [audio[:target_samples]]

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        from maest_infer import get_maest

        _require_distribution_version(self.package_name, self.package_version)
        self._torch = torch
        self._torchaudio = torchaudio
        self.device = self._device()
        binding = _verified_maest_checkpoint(
            torch,
            checkpoint_url=self.checkpoint_url,
            checkpoint_filename=self.checkpoint_filename,
            expected_sha256=self.checkpoint_sha256,
        )
        with binding as verified:
            model = get_maest(
                arch=self.model_name,
                pretrained=False,
                checkpoint=str(verified.path),
                checkpoint_swa_weigts=True,
            )
        self._model = model.to(self.device).eval()
        _move_maest_runtime_modules(self._model, self.device)

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)

    def _average_embeddings_by_path(
        self,
        paths: list[str | Path],
        rows: list[np.ndarray],
        window_track_indexes: list[int],
    ) -> dict[str, np.ndarray]:
        grouped: dict[int, list[np.ndarray]] = defaultdict(list)
        for row, track_index in zip(rows, window_track_indexes):
            grouped[track_index].append(row)
        embeddings_by_path: dict[str, np.ndarray] = {}
        for track_index, path in enumerate(paths):
            track_rows = grouped.get(track_index, [])
            if not track_rows:
                continue
            vector = np.mean(np.vstack(track_rows), axis=0).astype(np.float32)
            if not np.isfinite(vector).all():
                raise ValueError(f"MAEST model produced non-finite embeddings: {path}")
            embeddings_by_path[str(path)] = vector
        return embeddings_by_path


def _require_distribution_version(distribution: str, expected: str) -> None:
    try:
        actual = distribution_version(distribution)
    except PackageNotFoundError as error:
        raise RuntimeError(
            f"Pinned model loader is not installed: {distribution}=={expected}"
        ) from error
    if actual != expected:
        raise RuntimeError(
            f"Pinned model loader version mismatch for {distribution}: "
            f"expected {expected}, got {actual}"
        )


def _verified_maest_checkpoint(
    torch_module,
    *,
    checkpoint_url: str,
    checkpoint_filename: str,
    expected_sha256: str,
) -> VerifiedAssetBinding:
    checkpoint_dir = Path(torch_module.hub.get_dir()) / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / checkpoint_filename
    if not checkpoint_path.exists():
        torch_module.hub.download_url_to_file(
            checkpoint_url,
            str(checkpoint_path),
            hash_prefix=expected_sha256,
            progress=True,
        )
    _verify_checkpoint_sha256(
        checkpoint_path,
        expected_sha256=expected_sha256,
        description=checkpoint_url,
    )
    return bind_verified_file(
        checkpoint_path,
        expected_sha256=expected_sha256,
        description=checkpoint_url,
    )


def _verify_checkpoint_sha256(
    path: str | Path,
    *,
    expected_sha256: str,
    description: str,
) -> None:
    checkpoint_path = Path(path)
    if not checkpoint_path.is_file():
        raise RuntimeError(
            f"Pinned checkpoint is unavailable after download: {description} ({checkpoint_path})"
        )
    digest = hashlib.sha256()
    with checkpoint_path.open("rb") as checkpoint:
        for chunk in iter(lambda: checkpoint.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"Pinned checkpoint SHA-256 mismatch for {description}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )


def _move_maest_runtime_modules(model: object, device: str) -> None:
    init_melspectrogram = getattr(model, "init_melspectrogram", None)
    if callable(init_melspectrogram):
        init_melspectrogram()
    for attribute in ("melspectrogram",):
        module = getattr(model, attribute, None)
        move = getattr(module, "to", None)
        if callable(move):
            move(device)


def _analysis_window_starts(
    duration_seconds: float,
    input_seconds: float,
    offset_seconds: float,
    ratios: tuple[float, ...],
) -> list[float]:
    max_start = max(0.0, duration_seconds - input_seconds)
    requested = [offset_seconds, *(duration_seconds * ratio for ratio in ratios)]
    starts: list[float] = []
    for value in requested:
        start = min(max(0.0, value), max_start)
        if not any(abs(start - existing) < 1.0 for existing in starts):
            starts.append(start)
    return starts or [0.0]


def _average_window_rows(
    rows: list[list[float]],
    window_track_indexes: list[int],
    *,
    expected_tracks: int,
) -> list[list[float]]:
    grouped: dict[int, list[list[float]]] = defaultdict(list)
    for row, track_index in zip(rows, window_track_indexes):
        grouped[track_index].append(row)

    averaged: list[list[float]] = []
    for track_index in range(expected_tracks):
        track_rows = grouped.get(track_index, [])
        if not track_rows:
            averaged.append([])
            continue
        columns = zip(*track_rows)
        averaged.append([sum(values) / len(track_rows) for values in columns])
    return averaged


def _to_float_list(values: object) -> list[float]:
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


def _to_score_rows(values: object, *, expected_rows: int) -> list[list[float]]:
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
        rows = [[float(score) for score in row] for row in values]  # type: ignore[union-attr]
        if len(rows) != expected_rows:
            raise ValueError("MAEST batch output shape does not match the requested batch size")
        return rows

    flat = _to_float_list(values)
    if expected_rows == 1:
        return [flat]
    raise ValueError("MAEST batch output shape does not include per-track rows")


def _embedding_rows(values: object, *, expected_rows: int) -> list[np.ndarray]:
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
        raise ValueError("MAEST embedding row count does not match audio window count")
    return [array[index].astype(np.float32, copy=True) for index in range(array.shape[0])]


def _rank_genres(labels: list[str], scores: list[float], top_k: int) -> list[dict[str, float | str]]:
    ranked = sorted(zip(labels, scores), key=lambda item: item[1], reverse=True)
    return [{"label": label, "score": float(score)} for label, score in ranked[:top_k]]
