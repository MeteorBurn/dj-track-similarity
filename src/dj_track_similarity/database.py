from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterable

import numpy as np

from .db_analysis import AnalysisRepository
from .db_connection import connect_database, ensure_database_schema, resolve_database_path, write_lock_for_path
from .db_repository_utils import DEFAULT_EMBEDDING_KEY, MAEST_EMBEDDING_KEY, normalize_path
from .db_summary import SummaryRepository
from .db_tracks import TrackRepository
from .metadata_payload import metadata_from_json
from .models import Track


__all__ = [
    "DEFAULT_EMBEDDING_KEY",
    "LibraryDatabase",
    "MAEST_EMBEDDING_KEY",
    "metadata_from_json",
    "normalize_path",
]


class LibraryDatabase(TrackRepository, AnalysisRepository, SummaryRepository):
    def __init__(self, path: str | Path) -> None:
        self.path = resolve_database_path(path)
        self._write_lock = write_lock_for_path(self.path)
        self._cache_lock = threading.Lock()
        self._embedding_matrix_cache: dict[str, tuple[list[Track], np.ndarray]] = {}
        self._sonara_feature_row_cache: tuple[list[Track], list[dict[str, object]]] | None = None
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        return connect_database(self.path)

    def _ensure_schema(self) -> None:
        ensure_database_schema(self.path, self._write_lock)

    def _invalidate_embedding_cache(self, embedding_key: str | None = None) -> None:
        with self._cache_lock:
            if embedding_key is None:
                self._embedding_matrix_cache.clear()
            else:
                self._embedding_matrix_cache.pop(embedding_key, None)

    def _invalidate_embedding_cache_keys(self, embedding_keys: Iterable[str]) -> None:
        keys = tuple(dict.fromkeys(key for key in embedding_keys if key))
        if not keys:
            return
        with self._cache_lock:
            for key in keys:
                self._embedding_matrix_cache.pop(key, None)

    def _invalidate_sonara_feature_cache(self) -> None:
        with self._cache_lock:
            self._sonara_feature_row_cache = None
