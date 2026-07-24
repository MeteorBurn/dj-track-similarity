from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Sequence

import numpy as np

from .analysis_contracts import ContractIdentity
from .db_analysis import AnalysisRepository
from .db_artifacts import (
    ArtifactTrackIdentity,
    read_valid_embedding,
    write_valid_embedding,
)
from .db_connection import (
    BundleValidationState,
    connect_artifacts_database,
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


__all__ = ["LibraryDatabase"]


class LibraryDatabase(
    TrackRepository, AnalysisRepository, SummaryRepository, EvaluationRepository
):
    def __init__(self, path: str | Path) -> None:
        self.path = resolve_database_path(path)
        storage_paths = storage_database_paths(self.path)
        self.artifacts_path = storage_paths.artifacts
        self.evaluation_path = storage_paths.evaluation
        self._write_lock = write_lock_for_path(self.path)
        self._validation_state = BundleValidationState(
            self.path,
            self.artifacts_path,
        )
        self.catalog_uuid = self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        return connect_database(
            self.path,
            expected_catalog_uuid=self.catalog_uuid,
            validation_state=self._validation_state,
        )

    def connect_artifacts(self) -> sqlite3.Connection:
        return connect_artifacts_database(
            self.artifacts_path,
            expected_catalog_uuid=self.catalog_uuid,
            validation_state=self._validation_state,
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
                    expected_catalog_uuid=self.catalog_uuid,
                    create=True,
                )
        return connect_evaluation_sidecar(
            self.evaluation_path,
            expected_catalog_uuid=self.catalog_uuid,
            create=False,
        )

    def _ensure_schema(self) -> str:
        return ensure_database_schema(
            self.path,
            self._write_lock,
            validation_state=self._validation_state,
        )

    def read_artifact_embedding(
        self,
        *,
        family: str,
        track_id: int,
        expected_contract: ContractIdentity,
    ) -> np.ndarray | None:
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                return read_valid_embedding(
                    family=family,
                    track_id=track_id,
                    core_connection=core_connection,
                    artifacts_connection=artifacts_connection,
                    expected_contract=expected_contract,
                )

    def write_artifact_embedding(
        self,
        *,
        track: ArtifactTrackIdentity,
        contract: ContractIdentity,
        embedding: Sequence[float] | np.ndarray,
        analyzed_at: str,
    ) -> None:
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                write_valid_embedding(
                    core_connection=core_connection,
                    artifacts_connection=artifacts_connection,
                    track=track,
                    contract=contract,
                    embedding=embedding,
                    analyzed_at=analyzed_at,
                )
