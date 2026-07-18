from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from .metadata_payload import metadata_from_json
from .models import AnalysisCandidate
from .sonara_contract import sonara_analysis_is_compatible


def clean_analysis_models(models: Iterable[str]) -> list[str]:
    allowed = {"sonara", "maest", "mert", "muq", "clap"}
    selected: list[str] = []
    for model in models:
        text = str(model).strip().lower()
        if text not in allowed or text in selected:
            continue
        selected.append(text)
    return selected


def missing_analysis_ids_sql(model: str, limit_sql: str, *, sonara_signature_id: str | None = None) -> str:
    if model == "sonara":
        where_sql = "t.has_sonara_analysis = 0"
        if sonara_signature_id is not None:
            where_sql = (
                "(t.has_sonara_analysis = 0 "
                "OR sonara_analysis_is_current(t.metadata_json) != 1 "
                "OR json_extract(t.metadata_json, '$.sonara_analysis_signature.signature_id') IS NULL "
                "OR json_extract(t.metadata_json, '$.sonara_analysis_signature.signature_id') != ?)"
            )
    elif model in {"maest", "mert", "muq", "clap"}:
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


def missing_analysis_ids_params(
    model: str,
    limit_params: tuple[int, ...],
    *,
    sonara_signature_id: str | None = None,
) -> tuple[object, ...]:
    signature_params: tuple[object, ...] = (
        (sonara_signature_id,) if model == "sonara" and sonara_signature_id is not None else ()
    )
    return (*signature_params, *limit_params)


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
            t.has_muq_embedding = 1 AS has_muq,
            t.has_clap_embedding = 1 AS has_clap,
            t.metadata_json
        FROM tracks t
        WHERE t.id IN ({placeholders})
        """


def row_to_analysis_candidate(
    row: sqlite3.Row,
    selected: Iterable[str],
    *,
    expected_sonara_signature: dict[str, object] | None = None,
) -> AnalysisCandidate:
    has_sonara = bool(row["has_sonara"])
    if has_sonara and expected_sonara_signature is not None:
        has_sonara = sonara_analysis_is_compatible(
            metadata_from_json(row["metadata_json"]),
            expected_sonara_signature,
        )
    analyses = tuple(
        model
        for model in ("sonara", "maest", "mert", "muq", "clap")
        if (has_sonara if model == "sonara" else bool(row[f"has_{model}"]))
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
