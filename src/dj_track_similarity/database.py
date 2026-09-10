from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .analysis_models import AnalysisOutput, AnalysisVectorRow
from .db.analysis_candidates import normalize_analysis_outputs
from .db.analysis import AnalysisRepository
from .db.connection import (
    connect_database,
    connect_database_read_only,
    ensure_database_schema,
    resolve_database_path,
    write_lock_for_path,
)
from .db.evaluation import EvaluationRepository
from .db.evaluation_sidecar import connect_evaluation_sidecar
from .db.library_queries import LibraryQueryRepository
from .db.storage import evaluation_database_path
from .db.text_feedback import TextFeedbackRepository
from .db.tracks import TrackRepository


__all__ = ["LibraryDatabase"]


class LibraryDatabase(
    TrackRepository, AnalysisRepository, LibraryQueryRepository, EvaluationRepository,
    TextFeedbackRepository,
):
    @staticmethod
    def read_text_evaluation_embeddings(
        path: str | Path, output: AnalysisOutput
    ) -> dict[str, Any]:
        """Read a consistent evaluation pool using production eligibility rules.

        No bootstrap, WAL enforcement, FTS refresh, model load or audio access.
        The supplied current output identity describes the consuming model;
        historical encoder provenance cannot be reconstructed from stored rows.
        """
        from .db.analysis import _readonly, _selected_targets
        from .db.embeddings import read_valid_embeddings
        from .db.schema import validate_library_schema

        normalize_analysis_outputs((output,))
        if output.output_kind != "embedding" or output.analysis_family not in ("clap", "mulan"):
            raise ValueError("Text evaluation requires a CLAP or MuLan embedding output")
        with closing(connect_database_read_only(path)) as connection:
            connection.execute("BEGIN")
            catalog_uuid = validate_library_schema(connection)
            selected = _selected_targets(connection, catalog_uuid=catalog_uuid, targets=None)
            vectors = read_valid_embeddings(
                family=output.analysis_family,
                identities={target.track_id: target.track_uuid for target in selected},
                catalog_uuid=catalog_uuid, connection=connection,
            )
            rows = tuple(
                AnalysisVectorRow(target=target, output=output, vector=_readonly(vectors[target.track_id]))
                for target in selected if target.track_id in vectors
            )
            total = int(connection.execute("SELECT count(*) FROM tracks").fetchone()[0])
        return {"catalog_uuid": catalog_uuid, "rows": rows, "total_track_count": total,
                "eligible_count": len(rows), "excluded_count": total - len(rows)}

    def __init__(self, path: str | Path) -> None:
        self.path = resolve_database_path(path)
        self.evaluation_path = evaluation_database_path(self.path)
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
