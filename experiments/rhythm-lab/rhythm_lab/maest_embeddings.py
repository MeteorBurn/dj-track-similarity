from __future__ import annotations

from pathlib import Path

import numpy as np

from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.audio_loader import load_audio_mono, torch_compatible_audio
from dj_track_similarity.database import DEFAULT_EMBEDDING_KEY, LibraryDatabase
from dj_track_similarity.genres import (
    _analysis_window_starts,
    _average_window_rows,
    _move_maest_runtime_modules,
    _rank_genres,
    _to_score_rows,
    maest_input_seconds,
)
from dj_track_similarity.models import Track
from dj_track_similarity.runtime import select_torch_device


class MaestEmbeddingAdapter:
    embedding_key = "maest"
    model_name = "discogs-maest-30s-pw-129e-519l"
    dim: int | None = None
    analysis_offset_seconds = 60.0
    analysis_window_ratios = (0.38, 0.72)

    def __init__(
        self,
        device: str | None = None,
        inference_batch_size: int = 4,
        top_k: int = 3,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.inference_batch_size = max(1, int(inference_batch_size))
        self.top_k = max(1, int(top_k))
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self._genres_by_path: dict[str, list[dict[str, float | str]]] = {}

    def embed(self, path: str | Path) -> np.ndarray:
        return self.embed_batch([path])[0]

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None and self._model is not None

        all_windows = []
        window_track_indexes: list[int] = []
        for track_index, path in enumerate(paths):
            windows = self._prepare_audio_windows(path)
            all_windows.extend(windows)
            window_track_indexes.extend([track_index] * len(windows))
        if not all_windows:
            raise ValueError("No MAEST audio windows could be extracted")

        pooled_rows: list[np.ndarray] = []
        score_rows: list[list[float]] = []
        for start in range(0, len(all_windows), self.inference_batch_size):
            prepared = all_windows[start : start + self.inference_batch_size]
            audio_batch = torch.stack(prepared, dim=0).to(self._device())
            _move_maest_runtime_modules(self._model, self._device())
            with torch.inference_mode():
                logits, embeddings = self._model(audio_batch, melspectrogram_input=False)
            pooled_rows.extend(_embedding_rows(embeddings, expected_rows=len(prepared)))
            score_rows.extend(_to_score_rows(torch.sigmoid(logits), expected_rows=len(prepared)))

        grouped: dict[int, list[np.ndarray]] = {}
        for row, track_index in zip(pooled_rows, window_track_indexes):
            grouped.setdefault(track_index, []).append(row)
        self._genres_by_path = self._rank_genres_by_path(paths, score_rows, window_track_indexes)

        vectors: list[np.ndarray] = []
        for track_index, path in enumerate(paths):
            rows = grouped.get(track_index, [])
            if not rows:
                raise ValueError(f"Model produced no MAEST embeddings: {path}")
            vector = np.mean(np.vstack(rows), axis=0).astype(np.float32)
            if not np.isfinite(vector).all():
                raise ValueError(f"Model produced non-finite MAEST embeddings: {path}")
            self.dim = int(vector.shape[0])
            vectors.append(vector)
        return vectors

    def genres_for_path(self, path: str | Path) -> list[dict[str, float | str]] | None:
        return self._genres_by_path.get(str(path))

    def _prepare_audio_windows(self, path: str | Path):
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None

        audio_values, sample_rate, _decode_detail = load_audio_mono(
            path,
            torchaudio_module=torchaudio,
            target_sample_rate=16000,
        )
        audio = torch.from_numpy(torch_compatible_audio(audio_values)).unsqueeze(0)
        if sample_rate != 16000:
            audio = torchaudio.transforms.Resample(sample_rate, 16000)(audio)
        audio = audio.squeeze(0)
        target_samples = int(16000 * maest_input_seconds(self.model_name))
        if audio.numel() < target_samples:
            return [torch.nn.functional.pad(audio, (0, target_samples - audio.numel()))]

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
        return windows or [audio[:target_samples]]

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

    def _rank_genres_by_path(
        self,
        paths: list[str | Path],
        score_rows: list[list[float]],
        window_track_indexes: list[int],
    ) -> dict[str, list[dict[str, float | str]]]:
        labels = [str(label) for label in getattr(self._model, "labels", [])]
        if not labels or not score_rows:
            return {}
        averaged_rows = _average_window_rows(score_rows, window_track_indexes, expected_tracks=len(paths))
        return {
            str(path): _rank_genres(labels, scores, self.top_k)
            for path, scores in zip(paths, averaged_rows)
            if scores
        }


class LabMaestAnalysisJobManager(AnalysisJobManager):
    def __init__(
        self,
        db: LibraryDatabase,
        adapter_factories: dict[str, object] | None = None,
        *,
        batch_size: int = 4,
    ) -> None:
        super().__init__(db, adapter_factories or {"maest": MaestEmbeddingAdapter}, batch_size=batch_size)

    def _save_success(self, job_id: str, adapter: object, track: Track, vector: np.ndarray) -> None:
        embedding_key = getattr(adapter, "embedding_key", DEFAULT_EMBEDDING_KEY)
        model_name = str(getattr(adapter, "model_name", "maest"))
        self.db.save_embedding(track.id, vector, model_name, getattr(adapter, "dim", None), embedding_key=embedding_key)
        genres_for_path = getattr(adapter, "genres_for_path", None)
        if callable(genres_for_path):
            genres = genres_for_path(track.path)
            if genres is not None:
                self.db.save_genres(track.id, genres, model_name=model_name)
        self._update_progress(job_id, track.path, analyzed_delta=1)
        self._append_event(job_id, "ok", "Track analyzed", path=track.path, track_id=track.id)


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
