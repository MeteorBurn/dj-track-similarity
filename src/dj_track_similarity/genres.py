from __future__ import annotations

from collections import defaultdict
import re
from pathlib import Path
import time

import numpy as np

from .audio_loader import load_audio_mono, torch_compatible_audio
from .runtime import select_torch_device


class MaestGenreAdapter:
    embedding_key = "maest"
    model_name = "discogs-maest-30s-pw-129e-519l"
    dim: int | None = None
    analysis_offset_seconds = 60.0
    analysis_window_ratios = (0.38, 0.72)

    def __init__(self, device: str | None = None, top_k: int = 3) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.top_k = max(1, int(top_k))
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self._embeddings_by_path: dict[str, np.ndarray] = {}
        self.last_batch_timing: dict[str, float | int] = {}

    def predict(self, path: str | Path) -> list[dict[str, float | str]]:
        return self.predict_batch([path])[0]

    def predict_batch(self, paths: list[str | Path]) -> list[list[dict[str, float | str]]]:
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None and self._model is not None

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
        device = self._device()
        audio_batch = torch.stack(prepared, dim=0).to(device)
        _move_maest_runtime_modules(self._model, device)

        inference_started = time.perf_counter()
        with torch.inference_mode():
            logits, embeddings = self._model(audio_batch, melspectrogram_input=False)
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "decode_seconds": decode_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(paths),
            "windows": len(prepared),
        }

        activations = torch.sigmoid(logits)
        rows = _to_score_rows(activations, expected_rows=len(prepared))
        embedding_rows = _embedding_rows(embeddings, expected_rows=len(prepared))
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
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None

        decode_started = time.perf_counter()
        audio_values, sample_rate, _decode_detail = load_audio_mono(
            path,
            torchaudio_module=torchaudio,
            target_sample_rate=16000,
        )
        decode_seconds = time.perf_counter() - decode_started
        audio = torch.from_numpy(torch_compatible_audio(audio_values)).unsqueeze(0)
        if sample_rate != 16000:
            audio = torchaudio.transforms.Resample(sample_rate, 16000)(audio)
        audio = audio.squeeze(0)
        target_samples = int(16000 * maest_input_seconds(self.model_name))
        if audio.numel() < target_samples:
            return [torch.nn.functional.pad(audio, (0, target_samples - audio.numel()))], decode_seconds

        starts = _analysis_window_starts(
            audio.numel() / 16000,
            maest_input_seconds(self.model_name),
            self.analysis_offset_seconds,
            self.analysis_window_ratios,
        )
        windows = []
        for start_seconds in starts:
            start = max(0, int(16000 * start_seconds))
            segment = audio[start : start + target_samples]
            if segment.numel() < target_samples:
                segment = torch.nn.functional.pad(segment, (0, target_samples - segment.numel()))
            windows.append(segment)
        return windows or [audio[:target_samples]], decode_seconds

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        from maest_infer import get_maest

        self._torch = torch
        self._torchaudio = torchaudio
        self.device = self._device()
        self._model = get_maest(arch=self.model_name)
        self._model = self._model.to(self.device).eval()
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
            self.dim = int(vector.shape[0])
            embeddings_by_path[str(path)] = vector
        return embeddings_by_path


def genre_adapter_factories():
    return {"maest": MaestGenreAdapter}


def _move_maest_runtime_modules(model: object, device: str) -> None:
    init_melspectrogram = getattr(model, "init_melspectrogram", None)
    if callable(init_melspectrogram):
        init_melspectrogram()
    for attribute in ("melspectrogram",):
        module = getattr(model, attribute, None)
        move = getattr(module, "to", None)
        if callable(move):
            move(device)


def maest_input_seconds(model_name: str) -> float:
    match = re.search(r"-(5|10|20|30)s-", model_name)
    return float(match.group(1)) if match else 30.0


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
