from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping

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


def missing_analysis_ids_sql(
    model: str,
    limit_sql: str,
    *,
    sonara_signature_ids: Mapping[str, str] | None = None,
) -> str:
    if model == "sonara":
        signature_ids = dict(sonara_signature_ids or {})
        conditions: list[str] = []
        if "core" in signature_ids:
            conditions.append(
                "(t.has_sonara_analysis = 0 "
                "OR sonara_analysis_is_current(t.metadata_json) != 1 "
                "OR json_extract(t.metadata_json, '$.sonara_analysis_signature.signature_id') IS NULL "
                "OR json_extract(t.metadata_json, '$.sonara_analysis_signature.signature_id') != ?)"
            )
        if "timeline" in signature_ids:
            conditions.append(
                "NOT EXISTS ("
                "SELECT 1 FROM timeline.sonara_timeline st "
                "WHERE st.track_id = t.id AND st.analysis_signature_id = ?"
                ")"
            )
        if "representations" in signature_ids:
            conditions.extend(
                (
                    "NOT EXISTS ("
                    "SELECT 1 FROM representations.embeddings se "
                    "WHERE se.track_id = t.id AND se.embedding_key = 'sonara' "
                    "AND se.analysis_signature_id = ?"
                    ")",
                    "NOT EXISTS ("
                    "SELECT 1 FROM representations.fingerprints sf "
                    "WHERE sf.track_id = t.id AND sf.fingerprint_key = 'fingerprint' "
                    "AND sf.analysis_signature_id = ?"
                    ")",
                )
            )
        if not conditions:
            raise ValueError("SONARA candidate query requires at least one output signature")
        where_sql = f"({' OR '.join(conditions)})"
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
    sonara_signature_ids: Mapping[str, str] | None = None,
) -> tuple[object, ...]:
    signature_params: tuple[object, ...] = ()
    if model == "sonara":
        signature_ids = dict(sonara_signature_ids or {})
        values: list[str] = []
        for output in ("core", "timeline", "representations"):
            signature_id = signature_ids.get(output)
            if signature_id is None:
                continue
            values.append(signature_id)
            if output == "representations":
                values.append(signature_id)
        signature_params = tuple(values)
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
    force_missing_sonara: bool = False,
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
    missing = tuple(
        model
        for model in selected
        if model not in analyses or (model == "sonara" and force_missing_sonara)
    )
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
