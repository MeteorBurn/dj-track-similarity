from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
import numpy as np

from .analysis_models import EmbeddingOutput
from .db_analysis import AnalysisRepository
from .db_embeddings import (
    EmbeddingTrackIdentity,
    read_valid_embedding,
    write_valid_embedding,
)
from .db_connection import (
    connect_database,
    ensure_database_schema,
    resolve_database_path,
    write_lock_for_path,
)
from .db_evaluation import EvaluationRepository
from .db_evaluation_sidecar import connect_evaluation_sidecar
from .db_storage import storage_database_paths
from .db_summary import SummaryRepository
from .db_tracks import TrackRepository
from .track_models import TrackIdentity


__all__ = ["LibraryDatabase"]


class LibraryDatabase(
    TrackRepository, AnalysisRepository, SummaryRepository, EvaluationRepository
):
    def __init__(self, path: str | Path) -> None:
        self.path = resolve_database_path(path)
        storage_paths = storage_database_paths(self.path)
        self.evaluation_path = storage_paths.evaluation
        self._write_lock = write_lock_for_path(self.path)
        self.catalog_uuid = self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        return connect_database(
            self.path,
            expected_catalog_uuid=self.catalog_uuid,
        )

    def connect_evaluation(
        self,
        *,
        create: bool = False,
    ) -> sqlite3.Connection | None:
        if create:
            with self._write_lock:
                return connect_evaluation_sidecar(
                    self.evaluation_path,
                    create=True,
                )
        return connect_evaluation_sidecar(
            self.evaluation_path,
            create=False,
        )

    def _ensure_schema(self) -> str:
        return ensure_database_schema(
            self.path,
            self._write_lock,
        )

    def read_embedding(
        self,
        *,
        family: str,
        track_id: int,
    ) -> np.ndarray | None:
        with self._write_lock:
            with closing(self.connect()) as connection:
                return read_valid_embedding(
                    family=family,
                    track_id=track_id,
                    connection=connection,
                )

    def write_embedding(
        self,
        *,
        track: TrackIdentity | EmbeddingTrackIdentity,
        output: EmbeddingOutput,
    ) -> None:
        with self._write_lock:
            with closing(self.connect()) as connection:
                write_valid_embedding(
                    connection=connection,
                    track=track,
                    family=output.family,
                    embedding=output.vector,
                    analyzed_at=output.analyzed_at,
                )
