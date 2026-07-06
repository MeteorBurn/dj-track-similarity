from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol, cast

import numpy as np

from .analysis_job_batch import AnalysisBatchItem
from .audio_loader import DecodedAudio
from .database import LibraryDatabase
from .embedding import ClapEmbeddingAdapter, MertEmbeddingAdapter, MuqEmbeddingAdapter
from .genres import MaestGenreAdapter
from .sonara_features import analyze_and_store_sonara_features_from_audio


class AnalysisModelRunner(Protocol):
    model: str
    model_name: str
    device: str | None

    def analyze_batch(self, db: LibraryDatabase, items: Sequence[AnalysisBatchItem]) -> None:
        ...


RunnerFactory = Callable[[str, str, int, int, tuple[str, ...]], AnalysisModelRunner]


class SonaraModelRunner:
    model = "sonara"
    model_name = "sonara-playlist-lab"
    device = "cpu"

    def __init__(self, *, feature_families: tuple[str, ...] = ()) -> None:
        self.feature_families = tuple(feature_families)

    def analyze_batch(self, db: LibraryDatabase, items: Sequence[AnalysisBatchItem]) -> None:
        for item in items:
            analyze_and_store_sonara_features_from_audio(
                db,
                item.track,
                cast(DecodedAudio, item.decoded),
                feature_families=self.feature_families,
            )


class MaestModelRunner:
    model = "maest"

    def __init__(self, *, device: str, top_k: int, inference_batch_size: int) -> None:
        self.adapter = MaestGenreAdapter(device=device, top_k=top_k, inference_batch_size=inference_batch_size)

    @property
    def model_name(self) -> str:
        return self.adapter.model_name

    @property
    def device(self) -> str | None:
        return self.adapter.device

    def analyze_batch(self, db: LibraryDatabase, items: Sequence[AnalysisBatchItem]) -> None:
        tracks = [item.track for item in items]
        decoded_items = [cast(DecodedAudio, item.decoded) for item in items]
        genres_by_track = self.adapter.predict_decoded_batch(decoded_items)
        if len(genres_by_track) != len(tracks):
            raise ValueError("MAEST batch result count does not match track count")
        for track, decoded, genres in zip(tracks, decoded_items, genres_by_track):
            db.save_genres(track.id, genres, model_name=self.adapter.model_name)
            embedding = _embedding_for_path(self.adapter, decoded.path)
            if embedding is not None:
                db.save_embedding(
                    track.id,
                    embedding,
                    self.adapter.model_name,
                    getattr(self.adapter, "dim", None),
                    embedding_key="maest",
                )


class EmbeddingModelRunner:
    def __init__(self, model: str, *, device: str, inference_batch_size: int) -> None:
        self.model = model
        adapter_classes = {
            "mert": MertEmbeddingAdapter,
            "muq": MuqEmbeddingAdapter,
            "clap": ClapEmbeddingAdapter,
        }
        adapter_class = adapter_classes[model]
        self.adapter = adapter_class(device=device, inference_batch_size=inference_batch_size)

    @property
    def model_name(self) -> str:
        return self.adapter.model_name

    @property
    def device(self) -> str | None:
        return self.adapter.device

    def analyze_batch(self, db: LibraryDatabase, items: Sequence[AnalysisBatchItem]) -> None:
        tracks = [item.track for item in items]
        vectors = self.adapter.embed_decoded_batch([cast(DecodedAudio, item.decoded) for item in items])
        if len(vectors) != len(tracks):
            raise ValueError(f"{self.model.upper()} batch result count does not match track count")
        for track, vector in zip(tracks, vectors):
            db.save_embedding(
                track.id,
                vector,
                self.adapter.model_name,
                getattr(self.adapter, "dim", None),
                embedding_key=self.model,
            )


def _default_model_runners(
    model: str,
    device: str,
    inference_batch_size: int,
    top_k: int,
    sonara_features: tuple[str, ...] = (),
) -> AnalysisModelRunner:
    if model == "sonara":
        return SonaraModelRunner(feature_families=sonara_features)
    if model == "maest":
        return MaestModelRunner(device=device, top_k=top_k, inference_batch_size=inference_batch_size)
    if model in {"mert", "muq", "clap"}:
        return EmbeddingModelRunner(model, device=device, inference_batch_size=inference_batch_size)
    raise ValueError(f"No analysis runner configured for: {model}")


def _embedding_for_path(adapter: object, path: str) -> np.ndarray | None:
    getter = getattr(adapter, "embedding_for_path", None)
    if not callable(getter):
        return None
    vector = getter(path)
    if vector is None:
        return None
    return np.asarray(vector, dtype=np.float32)
