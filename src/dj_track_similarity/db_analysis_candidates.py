from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from .models import AnalysisCandidate


def clean_analysis_models(models: Iterable[str]) -> list[str]:
    allowed = {"sonara", "maest", "mert", "clap"}
    selected: list[str] = []
    for model in models:
        text = str(model).strip().lower()
        if text not in allowed or text in selected:
            continue
        selected.append(text)
    return selected


def missing_analysis_ids_sql(model: str, limit_sql: str) -> str:
    if model == "sonara":
        where_sql = "t.has_sonara_analysis = 0"
    elif model in {"maest", "mert", "clap"}:
        where_sql = f"t.has_{model}_embedding = 0"
    else:
        raise ValueError(f"Unknown analysis model: {model}")
    return f"""
        SELECT t.id
        FROM tracks t
        WHERE {where_sql}
        ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
        {limit_sql}
        """


def missing_analysis_ids_params(model: str, limit_params: tuple[int, ...]) -> tuple[object, ...]:
    return limit_params


def chunk_ids(items: tuple[int, ...], size: int) -> Iterable[tuple[int, ...]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def analysis_candidate_select_sql(placeholders: str) -> str:
    return f"""
        SELECT
            t.id, t.path, t.size, t.mtime, t.artist, t.title, t.album,
            t.bpm, t.musical_key, t.energy, t.duration,
            t.has_sonara_analysis = 1 AS has_sonara,
            t.has_maest_embedding = 1 AS has_maest,
            t.has_mert_embedding = 1 AS has_mert,
            t.has_clap_embedding = 1 AS has_clap
        FROM tracks t
        WHERE t.id IN ({placeholders})
        """


def row_to_analysis_candidate(row: sqlite3.Row, selected: Iterable[str]) -> AnalysisCandidate:
    analyses = tuple(
        model
        for model in ("sonara", "maest", "mert", "clap")
        if bool(row[f"has_{model}"])
    )
    missing = tuple(model for model in selected if model not in analyses)
    return AnalysisCandidate(
        id=int(row["id"]),
        path=str(row["path"]),
        size=int(row["size"]),
        mtime=float(row["mtime"]),
        artist=row["artist"],
        title=row["title"],
        album=row["album"],
        bpm=row["bpm"],
        musical_key=row["musical_key"],
        energy=row["energy"],
        duration=row["duration"],
        analyses=analyses,
        missing_models=missing,
    )
