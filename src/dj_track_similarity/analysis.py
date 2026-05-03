from __future__ import annotations

from .database import LibraryDatabase
from .embedding import EmbeddingAdapter
from .models import AnalyzeStats


def analyze_missing(db: LibraryDatabase, adapter: EmbeddingAdapter, limit: int | None = None) -> AnalyzeStats:
    tracks = db.list_tracks(with_embeddings=False)
    if limit is not None:
        tracks = tracks[:limit]
    analyzed = 0
    failed = 0
    for track in tracks:
        try:
            embedding = adapter.embed(track.path)
            db.save_embedding(track.id, embedding, adapter.model_name, adapter.dim)
            analyzed += 1
        except Exception:
            failed += 1
    return AnalyzeStats(analyzed=analyzed, failed=failed)
