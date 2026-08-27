from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import sqlite3
import sys
import time
from typing import Callable, Iterable, Mapping, TypeVar
from xml.sax.saxutils import escape
import zipfile

import numpy as np

from dj_track_similarity.analysis_models import current_embedding_spec
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_tracks import canonical_file_path
from dj_track_similarity.track_models import TrackIdentity

from .fingerprints import (
    FingerprintSketch,
    fingerprint_candidate_pairs,
    fingerprint_match_scores,
    load_fingerprint_sketches,
)
from .spectral import (
    SpectralResult,
    analyze_file,
    ffmpeg_available,
    skipped_result,
)


SCRIPT_DIR = Path(__file__).resolve().parent
TOOL_ROOT = SCRIPT_DIR.parent
REPO_ROOT = TOOL_ROOT.parents[1]
DEFAULT_DB = REPO_ROOT / "database" / "volumes.sqlite"
DEFAULT_RHYTHM_LAB_DB = REPO_ROOT / "tools" / "rhythm-lab" / "database" / "rhythm_lab.sqlite"
DEFAULT_OUT_DIR = TOOL_ROOT / "data" / "reports"
SUPPORTED_EMBEDDINGS = ("mert", "maest", "muq", "clap")
TRACK_LOAD_CHUNK_SIZE = 200
EMBEDDING_LOAD_CHUNK_SIZE = 200
FINGERPRINT_REVIEW_MIN_SIMILARITY = 0.45
MODE_FINGERPRINT = "fingerprint"
MODE_EMBEDDING = "embedding"
SEARCH_MODES = (MODE_FINGERPRINT, MODE_EMBEDDING)
DEFAULT_SOURCE_WEIGHTS = {
    "mert": 0.43,
    "maest": 0.32,
    "muq": 0.12,
    "clap": 0.04,
}
DELETE_SAFETY_EMBEDDINGS = ("mert", "maest")
LEGACY_DELETE_SAFETY_SOURCES = ("mert", "maest", "clap")
LEGACY_DELETE_SAFETY_WEIGHTS = {
    source: DEFAULT_SOURCE_WEIGHTS[source]
    for source in LEGACY_DELETE_SAFETY_SOURCES
}
SCORE_SEMANTICS = {
    "score": {
        "kind": "weighted_duplicate_evidence",
        "range": "0..1",
        "notes": "Overall duplicate score from enabled audio-to-audio embeddings, SONARA features, and duration evidence; weights are renormalized over available evidence.",
    },
    "content_similarity": {
        "kind": "audio_to_audio_embedding_gate",
        "range": "0..1",
        "notes": "Embedding-only gate computed from enabled stored MERT, MAEST, MuQ, and CLAP audio embeddings; MERT plus MAEST remain mandatory for automatic deletion safety.",
    },
    "mert_similarity": {
        "kind": "audio_to_audio_cosine",
        "range": "-1..1",
        "notes": "Cosine similarity between stored MERT audio embeddings.",
    },
    "maest_similarity": {
        "kind": "audio_to_audio_cosine",
        "range": "-1..1",
        "notes": "Cosine similarity between stored MAEST audio embeddings.",
    },
    "muq_similarity": {
        "kind": "audio_to_audio_cosine",
        "range": "-1..1",
        "notes": "Cosine similarity between stored MuQ audio embeddings.",
    },
    "clap_similarity": {
        "kind": "audio_to_audio_cosine",
        "range": "-1..1",
        "text_search_comparable": False,
        "notes": "Cosine similarity between stored CLAP audio embeddings; not comparable to CLAP text-to-audio search scores.",
    },
    "fingerprint_similarity": {
        "kind": "sonara_native_fingerprint_match",
        "range": "0..1",
        "notes": "Exact native SONARA fingerprint comparison, run only after version-separated fingerprint LSH retrieval. A score of 0.45 or above creates a manual-review candidate; it never independently authorizes deletion.",
    },
}
ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]
_T = TypeVar("_T")
LOSSLESS_RANKS = {
    ".flac": 60,
    ".wav": 55,
    ".wave": 55,
    ".aif": 54,
    ".aiff": 54,
    ".aifc": 54,
    ".alac": 53,
    ".m4a": 42,
    ".mp4": 40,
    ".mp3": 25,
    ".aac": 24,
    ".ogg": 23,
    ".oga": 23,
    ".opus": 23,
    ".wma": 20,
}
SONARA_FIELDS = (
    "bpm",
    "danceability",
    "energy",
    "valence",
    "acousticness",
    "spectral_centroid_mean",
    "onset_density",
    "dynamic_range_db",
    "loudness_lufs",
)


class ConsoleProgressReporter:
    def __init__(self, *, refresh_seconds: float = 1.0) -> None:
        self.refresh_seconds = max(0.0, float(refresh_seconds))
        self._last_message: str | None = None
        self._last_rendered_at: float | None = None
        self._has_active_line = False

    def __call__(self, processed: int, total: int, message: str) -> None:
        now = time.monotonic()
        completed = total > 0 and processed >= total
        phase_changed = message != self._last_message
        due = (
            self._last_rendered_at is None
            or now - self._last_rendered_at >= self.refresh_seconds
        )
        if not (phase_changed or completed or due):
            return
        if total > 0:
            percent = max(0.0, min(100.0, (processed / total) * 100.0))
            rendered = f"{message}: {percent:.1f}% ({processed}/{total})"
        else:
            rendered = f"{message}..."
        sys.stdout.write(f"\r{rendered}")
        sys.stdout.flush()
        self._last_message = message
        self._last_rendered_at = now
        self._has_active_line = True

    def finish(self) -> None:
        if self._has_active_line:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._has_active_line = False


@dataclass(frozen=True)
class PresetConfig:
    name: str
    min_score: float
    min_similarity: float
    duration_seconds: float
    duration_ratio: float
    direct_keeper_score: float
    strict_duration_ratio: float


@dataclass(frozen=True)
class SourceConfig:
    sources: tuple[str, ...]
    weights: dict[str, float]


@dataclass(frozen=True)
class TrackRecord:
    track_id: int
    path: str
    size: int
    mtime: float
    artist: str | None
    title: str | None
    album: str | None
    bpm: float | None
    musical_key: str | None
    duration: float | None
    metadata: dict[str, object]
    embeddings: dict[str, np.ndarray]
    catalog_uuid: str = ""
    track_uuid: str = ""
    file_modified_ns: int = 0


@dataclass(frozen=True)
class PairEvidence:
    left_id: int
    right_id: int
    score: float
    content_similarity: float | None
    mert_similarity: float | None
    maest_similarity: float | None
    muq_similarity: float | None
    clap_similarity: float | None
    sonara_similarity: float | None
    duration_diff_seconds: float | None
    duration_diff_ratio: float | None
    blocked_reasons: tuple[str, ...]
    fingerprint_similarity: float | None = None
    candidate_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class DuplicateGroup:
    group_id: int
    track_ids: tuple[int, ...]
    pair_evidence: tuple[PairEvidence, ...]


@dataclass(frozen=True)
class ReportResult:
    json_path: Path
    xlsx_path: Path
    log_path: Path
    payload: dict[str, object]
    groups: int


@dataclass(frozen=True)
class ApplyResult:
    deleted_track_ids: tuple[int, ...]
    deleted_paths: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]
    rhythm_lab_deleted_rows: int = 0


class AudioDedupCancelled(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    progress_reporter = ConsoleProgressReporter()
    try:
        result = run_report(
            db_path=args.db,
            root=args.root,
            path_contains=args.path_contains,
            preset_name=args.preset,
            min_score=args.min_score,
            min_similarity=args.min_similarity,
            limit_groups=args.limit_groups,
            out_dir=args.out_dir,
            sources=args.sources,
            weights=parse_weight_arguments(args.weights),
            mode=args.mode,
            skip_spectral=args.skip_spectral,
            progress_callback=progress_reporter,
        )
        progress_reporter.finish()
        apply_result = None
        if args.apply:
            candidates = safe_delete_candidates(result.payload)
            if not candidates:
                print("Apply requested, but no safe delete candidates were found.")
            elif confirm_apply(candidates, args.db, args.root):
                apply_result = apply_duplicate_deletions(
                    db_path=args.db,
                    root=args.root,
                    payload=result.payload,
                )
                result.payload["mode"] = "apply"
                result.payload["apply_result"] = apply_result_payload(apply_result)
                result.json_path.write_text(json.dumps(result.payload, indent=2, ensure_ascii=False), encoding="utf-8")
                write_text_log(result.log_path, result.payload, apply_result=apply_result)
            else:
                print("Apply cancelled; reports were written but no files or database rows were deleted.")
    except (FileNotFoundError, OSError, ValueError, sqlite3.Error) as error:
        progress_reporter.finish()
        print(f"audio_dedup failed: {error}", file=sys.stderr)
        return 2
    if args.apply and apply_result is not None:
        print(
            "Apply run complete. "
            f"groups={result.groups} deleted={len(apply_result.deleted_track_ids)} "
            f"skipped={len(apply_result.skipped)} failed={len(apply_result.failed)} "
            f"rhythm_lab_deleted_rows={apply_result.rhythm_lab_deleted_rows}"
        )
    else:
        print(
            "Report-only run complete. "
            f"groups={result.groups} safe_candidates={_safe_candidate_count(result.payload)}"
        )
    print(rhythm_lab_cli_summary(result.payload))
    print(f"json={result.json_path.resolve()}")
    print(f"xlsx={result.xlsx_path.resolve()}")
    print(f"log={result.log_path.resolve()}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find likely duplicate audio tracks from an existing dj-track-similarity SQLite database. "
            "By default it is report-only; --apply prompts before deleting safe candidates."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Project SQLite database. Default: <repo>/database/volumes.sqlite.")
    parser.add_argument("--root", type=Path, required=True, help="Only include DB tracks inside this stored path root.")
    parser.add_argument(
        "--path-contains",
        action="append",
        default=[],
        help="Additional case-insensitive substring filter on stored track paths. Can be repeated.",
    )
    parser.add_argument("--preset", choices=("safe", "balanced", "aggressive"), default="safe")
    parser.add_argument("--min-score", type=float, help="Override the preset duplicate score threshold.")
    parser.add_argument("--min-similarity", type=float, help="Override the preset content-similarity threshold.")
    parser.add_argument(
        "--source",
        dest="sources",
        action="append",
        choices=SUPPORTED_EMBEDDINGS,
        help="Enable one embedding family. Can be repeated; default: all families.",
    )
    parser.add_argument(
        "--weight",
        dest="weights",
        action="append",
        default=[],
        metavar="FAMILY=VALUE",
        help="Set every enabled family weight. Repeat once per enabled --source.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--fingerprint",
        dest="mode",
        action="store_const",
        const=MODE_FINGERPRINT,
        default=MODE_FINGERPRINT,
        help=(
            "Primary mode, also the default. Search duplicates exclusively from stored SONARA "
            "fingerprints: no embeddings are loaded, candidates come from fingerprint LSH only, "
            "and only the exact native match score forms groups. Every reported candidate stays "
            "manual-review."
        ),
    )
    mode_group.add_argument(
        "--embedding",
        dest="mode",
        action="store_const",
        const=MODE_EMBEDDING,
        help=(
            "Secondary mode. Score duplicates from the enabled embedding families with the "
            "preset score and similarity gates; exact fingerprint checks still add manual-review "
            "pairs, and this is the only mode that can produce safe delete candidates for "
            "--apply."
        ),
    )
    parser.add_argument(
        "--skip-spectral",
        action="store_true",
        help=(
            "Skip the ffmpeg spectral check of duplicate-group files that flags suspected "
            "transcodes (fake-bitrate copies) and steers keeper choice toward full-band audio."
        ),
    )
    parser.add_argument("--limit-groups", type=int, help="Write at most N duplicate groups.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Report output directory.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="After writing reports, prompt for confirmation and delete safe duplicate candidates plus their database rows.",
    )
    return parser.parse_args(argv)


def parse_weight_arguments(items: Iterable[str]) -> dict[str, float] | None:
    parsed: dict[str, float] = {}
    for raw_item in items:
        family_text, separator, value_text = str(raw_item).partition("=")
        family = family_text.strip().casefold()
        if not separator or not family or not value_text.strip():
            raise ValueError(
                f"Invalid --weight {raw_item!r}; expected FAMILY=VALUE"
            )
        if family in parsed:
            raise ValueError(f"Duplicate --weight for source: {family}")
        try:
            parsed[family] = float(value_text)
        except ValueError as error:
            raise ValueError(
                f"Invalid --weight {raw_item!r}; VALUE must be numeric"
            ) from error
    return parsed or None


def resolve_source_config(
    *,
    sources: Iterable[str] | None = None,
    weights: Mapping[str, float] | None = None,
) -> SourceConfig:
    if isinstance(sources, (str, bytes)):
        raise ValueError("sources must be a collection of embedding family names")
    selected_sources = tuple(
        str(source).strip().casefold()
        for source in (
            SUPPORTED_EMBEDDINGS
            if sources is None
            else sources
        )
    )
    if not selected_sources:
        raise ValueError("sources must enable at least one embedding family")
    if len(set(selected_sources)) != len(selected_sources):
        raise ValueError("sources must contain unique embedding family names")
    unsupported = [
        source
        for source in selected_sources
        if source not in SUPPORTED_EMBEDDINGS
    ]
    if unsupported:
        raise ValueError(
            "Unsupported embedding source(s): "
            + ", ".join(sorted(unsupported))
        )

    if weights is None:
        selected_weights = {
            source: DEFAULT_SOURCE_WEIGHTS[source]
            for source in selected_sources
        }
    else:
        normalized_weights: dict[str, float] = {}
        for raw_family, raw_weight in weights.items():
            family = str(raw_family).strip().casefold()
            if family in normalized_weights:
                raise ValueError(
                    f"weights contains duplicate normalized source: {family}"
                )
            if isinstance(raw_weight, bool):
                raise ValueError(f"Weight for {family} must be numeric")
            try:
                value = float(raw_weight)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Weight for {family} must be numeric"
                ) from error
            normalized_weights[family] = value
        expected = set(selected_sources)
        actual = set(normalized_weights)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("unexpected " + ", ".join(extra))
            raise ValueError(
                "weights must contain exactly the enabled sources"
                + (f" ({'; '.join(details)})" if details else "")
            )
        selected_weights = {
            source: normalized_weights[source]
            for source in selected_sources
        }

    for source, weight in selected_weights.items():
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(
                f"Weight for {source} must be finite and nonnegative"
            )
    if not any(weight > 0 for weight in selected_weights.values()):
        raise ValueError("At least one enabled source weight must be positive")
    return SourceConfig(
        sources=selected_sources,
        weights=selected_weights,
    )


def _uses_legacy_delete_safety_config(
    source_config: SourceConfig,
) -> bool:
    return (
        len(source_config.sources)
        == len(LEGACY_DELETE_SAFETY_SOURCES)
        and set(source_config.sources)
        == set(LEGACY_DELETE_SAFETY_SOURCES)
        and source_config.weights
        == LEGACY_DELETE_SAFETY_WEIGHTS
    )


def run_report(
    *,
    db_path: Path | None = None,
    database: LibraryDatabase | None = None,
    root: Path,
    path_contains: list[str],
    preset_name: str,
    min_score: float | None,
    min_similarity: float | None = None,
    limit_groups: int | None,
    out_dir: Path,
    sources: Iterable[str] | None = None,
    weights: Mapping[str, float] | None = None,
    mode: str = MODE_FINGERPRINT,
    skip_spectral: bool = False,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCheck | None = None,
) -> ReportResult:
    config = resolve_preset(preset_name, min_score=min_score, min_similarity=min_similarity)
    if mode not in SEARCH_MODES:
        raise ValueError(f"Unsupported search mode: {mode}")
    fingerprint_mode = mode == MODE_FINGERPRINT
    if fingerprint_mode:
        if sources is not None or weights is not None:
            raise ValueError(
                "--source and --weight require --embedding"
            )
        source_config = SourceConfig(sources=(), weights={})
    else:
        source_config = resolve_source_config(sources=sources, weights=weights)
    selected_database = _resolve_database(database=database, db_path=db_path)
    selected_db = selected_database.path
    _report_progress(progress_callback, 0, 0, "Reading database")
    _raise_if_cancelled(should_cancel)
    database_track_count = count_database_tracks(selected_database)
    _report_progress(progress_callback, 0, database_track_count, "Loading scoped tracks")
    tracks = load_tracks(
        selected_database,
        root=root,
        path_contains=path_contains,
        sources=source_config.sources,
        progress_callback=progress_callback,
    )
    _raise_if_cancelled(should_cancel)
    _report_progress(progress_callback, 0, max(1, len(tracks)), f"Loaded {len(tracks)} scoped tracks")
    track_uuids = {
        track.track_id: track.track_uuid
        for track in tracks
        if track.track_uuid
    }
    _report_progress(progress_callback, 0, max(1, len(tracks)), "Loading saved SONARA fingerprint sketches")
    connection = selected_database.connect()
    try:
        fingerprint_load = load_fingerprint_sketches(
            connection,
            track_uuids,
            progress_callback=lambda completed, total: _report_progress(
                progress_callback,
                completed,
                total,
                "Loading saved SONARA fingerprint sketches",
            ),
        )
    finally:
        connection.close()
    candidate_sources = _candidate_pair_sources(
        tracks,
        config,
        source_config,
        fingerprint_sketches=fingerprint_load.sketches,
        fingerprint_only=fingerprint_mode,
    )
    fingerprint_lsh_pairs = {
        pair
        for pair, sources_for_pair in candidate_sources.items()
        if "fingerprint_lsh" in sources_for_pair
    }
    fingerprint_exact_pairs = _fingerprint_exact_candidate_pairs(candidate_sources)
    _report_progress(progress_callback, 0, max(1, len(fingerprint_exact_pairs)), "Verifying SONARA fingerprint candidates")
    connection = selected_database.connect()
    try:
        fingerprint_scores = fingerprint_match_scores(
            connection,
            fingerprint_exact_pairs,
            track_uuids,
            progress_callback=lambda completed, total: _report_progress(
                progress_callback,
                completed,
                total,
                "Verifying SONARA fingerprint candidates",
            ),
        )
    finally:
        connection.close()
    fingerprint_retrieval = {
        "valid_stored_fingerprint_count": len(fingerprint_load.sketches),
        "rejected_stored_fingerprint_count": fingerprint_load.rejected_rows,
        "fingerprint_lsh_candidate_pair_count": len(fingerprint_lsh_pairs),
        "fingerprint_exact_candidate_pair_count": len(fingerprint_exact_pairs),
        "exact_fingerprint_pair_count": len(fingerprint_scores),
        "fingerprint_review_pair_count": sum(
            score >= FINGERPRINT_REVIEW_MIN_SIMILARITY
            for score in fingerprint_scores.values()
        ),
        "fingerprint_review_min_similarity": FINGERPRINT_REVIEW_MIN_SIMILARITY,
    }
    groups = find_duplicate_groups(
        tracks,
        config,
        limit_groups=limit_groups,
        source_config=source_config,
        candidate_sources=candidate_sources,
        fingerprint_scores=fingerprint_scores,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
    )
    _raise_if_cancelled(should_cancel)
    spectral_results = _spectral_results_for_groups(
        groups,
        tracks,
        skip_spectral=skip_spectral,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
    )
    _report_progress(progress_callback, 0, 0, "Writing reports")
    payload = build_report(
        groups,
        tracks,
        config,
        db_path=selected_db,
        database_track_count=database_track_count,
        root=root,
        path_contains=path_contains,
        source_config=source_config,
        fingerprint_retrieval=fingerprint_retrieval,
        spectral_results=spectral_results,
    )
    payload["search_mode"] = mode
    payload["rhythm_lab"] = rhythm_lab_impact_payload(
        DEFAULT_RHYTHM_LAB_DB,
        safe_delete_candidates(payload),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = _unique_report_path(out_dir / f"audio_dedup_report_{stamp}.json")
    xlsx_path = json_path.with_suffix(".xlsx")
    log_path = json_path.with_suffix(".log")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_xlsx_report(xlsx_path, payload)
    write_text_log(log_path, payload)
    _report_progress(progress_callback, 1, 1, "Reports written")
    return ReportResult(json_path=json_path, xlsx_path=xlsx_path, log_path=log_path, payload=payload, groups=len(groups))


def resolve_preset(name: str, *, min_score: float | None, min_similarity: float | None = None) -> PresetConfig:
    presets = {
        "safe": PresetConfig(
            name="safe",
            min_score=0.965,
            min_similarity=0.985,
            duration_seconds=2.0,
            duration_ratio=0.01,
            direct_keeper_score=0.98,
            strict_duration_ratio=0.01,
        ),
        "balanced": PresetConfig(
            name="balanced",
            min_score=0.95,
            min_similarity=0.97,
            duration_seconds=5.0,
            duration_ratio=0.025,
            direct_keeper_score=0.97,
            strict_duration_ratio=0.025,
        ),
        "aggressive": PresetConfig(
            name="aggressive",
            min_score=0.925,
            min_similarity=0.94,
            duration_seconds=15.0,
            duration_ratio=0.08,
            direct_keeper_score=0.965,
            strict_duration_ratio=0.08,
        ),
    }
    if name not in presets:
        raise ValueError(f"Unsupported preset: {name}")
    config = presets[name]
    selected_min_score = config.min_score if min_score is None else float(min_score)
    selected_min_similarity = config.min_similarity if min_similarity is None else float(min_similarity)
    if not 0.0 <= selected_min_score <= 1.0:
        raise ValueError("--min-score must be between 0 and 1")
    if not 0.0 <= selected_min_similarity <= 1.0:
        raise ValueError("--min-similarity must be between 0 and 1")
    return PresetConfig(
        name=config.name,
        min_score=selected_min_score,
        min_similarity=selected_min_similarity,
        duration_seconds=config.duration_seconds,
        duration_ratio=config.duration_ratio,
        direct_keeper_score=config.direct_keeper_score,
        strict_duration_ratio=config.strict_duration_ratio,
    )


def load_tracks(
    database: LibraryDatabase | Path,
    *,
    root: Path,
    path_contains: list[str],
    sources: Iterable[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[TrackRecord]:
    selected_database = (
        database
        if isinstance(database, LibraryDatabase)
        else _resolve_database(database=None, db_path=database)
    )
    root_text = canonical_file_path(root)
    contains = [item.casefold() for item in path_contains if item.strip()]
    selected_sources = tuple(SUPPORTED_EMBEDDINGS if sources is None else sources)
    unsupported_sources = set(selected_sources) - set(SUPPORTED_EMBEDDINGS)
    if unsupported_sources:
        raise ValueError(
            "Unsupported embedding source(s): "
            + ", ".join(sorted(unsupported_sources))
        )
    connection = selected_database.connect()
    try:
        active_track_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM tracks WHERE missing_since IS NULL"
            ).fetchone()[0]
        )
        _report_progress(
            progress_callback,
            0,
            active_track_count,
            "Loading scoped tracks",
        )
        cursor = connection.execute(
            """
            SELECT
                t.track_id,
                t.track_uuid,
                t.file_path,
                t.file_size_bytes,
                t.file_modified_ns,
                t.sample_rate_hz,
                t.bit_rate_bps,
                t.audio_duration_seconds,
                ft.artist,
                ft.title,
                ft.album,
                ft.tag_bpm,
                ft.tag_key,
                ft.genres_json,
                s.detected_bpm,
                s.danceability_score,
                s.energy_score,
                s.valence_score,
                s.acousticness_score,
                s.spectral_centroid_hz,
                s.onset_density_per_second,
                s.dynamic_range_db,
                s.integrated_loudness_lufs
            FROM tracks AS t
            LEFT JOIN tags AS ft
              ON ft.track_id = t.track_id
            LEFT JOIN sonara_features AS s
              ON s.track_id = t.track_id
            WHERE t.missing_since IS NULL
            ORDER BY t.track_id
            """,
        )
        tracks: list[TrackRecord] = []
        processed = 0
        while rows := cursor.fetchmany(TRACK_LOAD_CHUNK_SIZE):
            for row in rows:
                if _path_matches(row["file_path"], root_text, contains):
                    tracks.append(
                        _track_from_row(
                            row,
                            catalog_uuid=selected_database.catalog_uuid,
                        )
                    )
            processed += len(rows)
            _report_progress(
                progress_callback,
                processed,
                active_track_count,
                "Loading scoped tracks",
            )
        _attach_embeddings(
            connection,
            tracks,
            sources=selected_sources,
            progress_callback=progress_callback,
        )
    finally:
        connection.close()
    return tracks


def count_database_tracks(database: LibraryDatabase | Path) -> int:
    selected_database = (
        database
        if isinstance(database, LibraryDatabase)
        else _resolve_database(database=None, db_path=database)
    )
    connection = selected_database.connect()
    try:
        return int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
    finally:
        connection.close()


def find_duplicate_groups(
    tracks: list[TrackRecord],
    config: PresetConfig,
    *,
    limit_groups: int | None,
    source_config: SourceConfig | None = None,
    candidate_sources: Mapping[tuple[int, int], tuple[str, ...]] | None = None,
    fingerprint_scores: Mapping[tuple[int, int], float] | None = None,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCheck | None = None,
) -> list[DuplicateGroup]:
    selected_sources = source_config or resolve_source_config()
    if len(tracks) < 2:
        _report_progress(progress_callback, 1, 1, "Not enough scoped tracks")
        return []
    by_id = {track.track_id: track for track in tracks}
    _report_progress(progress_callback, 0, 0, "Building candidate pairs")
    selected_candidate_sources = dict(
        candidate_sources
        if candidate_sources is not None
        else _candidate_pair_sources(tracks, config, selected_sources)
    )
    pair_total = len(selected_candidate_sources)
    if pair_total == 0:
        _report_progress(progress_callback, 1, 1, "No candidate pairs")
        return []
    edges: list[PairEvidence] = []
    selected_fingerprint_scores = fingerprint_scores or {}
    for index, ((left_id, right_id), sources_for_pair) in enumerate(
        sorted(selected_candidate_sources.items()),
        start=1,
    ):
        _raise_if_cancelled(should_cancel)
        left = by_id[left_id]
        right = by_id[right_id]
        fingerprint_similarity = selected_fingerprint_scores.get((left_id, right_id))
        if (
            "fingerprint_lsh" not in sources_for_pair
            and not _candidate_duration_compatible(left, right, config)
        ):
            if index == pair_total or index % 50 == 0:
                _report_progress(progress_callback, index, pair_total, "Searching duplicate pairs")
            continue
        evidence = score_pair(
            left,
            right,
            config,
            source_config=selected_sources,
            fingerprint_similarity=fingerprint_similarity,
            candidate_sources=sources_for_pair,
        )
        conventional_match = (
            _candidate_duration_compatible(left, right, config)
            and evidence.score >= config.min_score
            and _passes_content_similarity(evidence, config)
        )
        fingerprint_match = (
            fingerprint_similarity is not None
            and fingerprint_similarity >= FINGERPRINT_REVIEW_MIN_SIMILARITY
        )
        if conventional_match or fingerprint_match:
            edges.append(evidence)
        if index == pair_total or index % 50 == 0:
            _report_progress(progress_callback, index, pair_total, "Searching duplicate pairs")
    grouped_edges = _connected_components(edges)
    groups: list[DuplicateGroup] = []
    for edge_group in grouped_edges:
        track_ids = tuple(sorted({edge.left_id for edge in edge_group} | {edge.right_id for edge in edge_group}))
        if len(track_ids) < 2 or not all(track_id in by_id for track_id in track_ids):
            continue
        groups.append(DuplicateGroup(len(groups) + 1, track_ids, tuple(sorted(edge_group, key=lambda item: (-item.score, item.left_id, item.right_id)))))
        if limit_groups is not None and len(groups) >= max(0, limit_groups):
            break
    return groups


def _report_progress(callback: ProgressCallback | None, processed: int, total: int, message: str) -> None:
    if callback is not None:
        callback(max(0, int(processed)), max(0, int(total)), message)


def _raise_if_cancelled(should_cancel: CancelCheck | None) -> None:
    if should_cancel is not None and should_cancel():
        raise AudioDedupCancelled("Audio dedup job cancelled")


def _candidate_pair_ids(
    tracks: list[TrackRecord],
    config: PresetConfig,
    source_config: SourceConfig,
    *,
    fingerprint_sketches: Iterable[FingerprintSketch] = (),
) -> list[tuple[int, int]]:
    return sorted(
        _candidate_pair_sources(
            tracks,
            config,
            source_config,
            fingerprint_sketches=fingerprint_sketches,
        )
    )


def _candidate_pair_sources(
    tracks: list[TrackRecord],
    config: PresetConfig,
    source_config: SourceConfig,
    *,
    fingerprint_sketches: Iterable[FingerprintSketch] = (),
    fingerprint_only: bool = False,
) -> dict[tuple[int, int], tuple[str, ...]]:
    sources_by_pair: dict[tuple[int, int], set[str]] = {}
    if not fingerprint_only:
        signature_sources = _signature_candidate_pair_sources(
            tracks,
            config,
            source_config,
        )
        for pair, sources in signature_sources.items():
            sources_by_pair.setdefault(pair, set()).update(sources)
        if not signature_sources:
            for pair in _duration_window_candidate_pairs(tracks, config):
                sources_by_pair.setdefault(pair, set()).add("duration_window")
    for pair in fingerprint_candidate_pairs(list(fingerprint_sketches)):
        sources_by_pair.setdefault(pair, set()).add("fingerprint_lsh")
    return {
        pair: tuple(sorted(sources))
        for pair, sources in sources_by_pair.items()
    }


def _fingerprint_exact_candidate_pairs(
    candidate_sources: Mapping[tuple[int, int], tuple[str, ...]],
) -> set[tuple[int, int]]:
    return {
        pair
        for pair, sources_for_pair in candidate_sources.items()
        if "fingerprint_lsh" in sources_for_pair
        or any(source in {"mert_lsh", "maest_lsh"} for source in sources_for_pair)
    }


def _spectral_results_for_groups(
    groups: list[DuplicateGroup],
    tracks: list[TrackRecord],
    *,
    skip_spectral: bool,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCheck | None = None,
) -> dict[int, SpectralResult]:
    if skip_spectral:
        return {}
    group_track_ids = sorted({track_id for group in groups for track_id in group.track_ids})
    if not group_track_ids:
        return {}
    if not ffmpeg_available():
        return {
            track_id: skipped_result("ffmpeg unavailable")
            for track_id in group_track_ids
        }
    by_id = {track.track_id: track for track in tracks}
    results: dict[int, SpectralResult] = {}
    total = len(group_track_ids)
    message = "Analyzing spectra of duplicate-group files"
    _report_progress(progress_callback, 0, total, message)
    for index, track_id in enumerate(group_track_ids, start=1):
        _raise_if_cancelled(should_cancel)
        track = by_id.get(track_id)
        if track is None:
            results[track_id] = skipped_result("track not loaded")
        elif not Path(track.path).is_file():
            results[track_id] = skipped_result("file not reachable")
        else:
            sample_rate = track.metadata.get("sample_rate_hz")
            bit_rate = track.metadata.get("bit_rate_bps")
            results[track_id] = analyze_file(
                track.path,
                sample_rate=sample_rate if isinstance(sample_rate, int) else None,
                duration_seconds=track.duration,
                declared_bitrate_bps=bit_rate if isinstance(bit_rate, int) else None,
            )
        _report_progress(progress_callback, index, total, message)
    return results


def _duration_window_candidate_pairs(tracks: list[TrackRecord], config: PresetConfig) -> list[tuple[int, int]]:
    sortable = [track for track in tracks if track.duration is not None and track.duration > 0]
    missing_duration = [track for track in tracks if track.duration is None or track.duration <= 0]
    sortable.sort(key=lambda track: (float(track.duration or 0.0), track.track_id))
    pairs: set[tuple[int, int]] = set()
    end = 0
    for start, left in enumerate(sortable):
        if end < start + 1:
            end = start + 1
        tolerance = max(config.duration_seconds, float(left.duration or 0.0) * config.duration_ratio)
        while end < len(sortable) and float(sortable[end].duration or 0.0) - float(left.duration or 0.0) <= tolerance:
            end += 1
        for right in sortable[start + 1 : end]:
            pairs.add(_ordered_pair(left.track_id, right.track_id))
    if len(missing_duration) <= 200:
        for index, left in enumerate(missing_duration):
            for right in missing_duration[index + 1 :]:
                pairs.add(_ordered_pair(left.track_id, right.track_id))
    return sorted(pairs)


def _signature_candidate_pairs(
    tracks: list[TrackRecord],
    config: PresetConfig,
    source_config: SourceConfig,
) -> set[tuple[int, int]]:
    return set(_signature_candidate_pair_sources(tracks, config, source_config))


def _signature_candidate_pair_sources(
    tracks: list[TrackRecord],
    config: PresetConfig,
    source_config: SourceConfig,
) -> dict[tuple[int, int], set[str]]:
    sources_by_pair: dict[tuple[int, int], set[str]] = {}
    for embedding_key in ("mert", "maest"):
        if embedding_key not in source_config.sources:
            continue
        embedding_tracks = [track for track in tracks if embedding_key in track.embeddings]
        if not embedding_tracks:
            continue
        dim = min(int(track.embeddings[embedding_key].shape[0]) for track in embedding_tracks)
        if dim < 96:
            continue
        projection_count = 96
        rng = np.random.default_rng(_projection_seed(embedding_key, dim))
        projection = rng.standard_normal((dim, projection_count), dtype=np.float32)
        matrix = np.vstack([track.embeddings[embedding_key][:dim] for track in embedding_tracks]).astype(np.float32)
        matrix = matrix - matrix.mean(axis=0, keepdims=True)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms
        signatures = (matrix @ projection) >= 0
        buckets: dict[tuple[int, int], list[int]] = {}
        for row_index, track in enumerate(embedding_tracks):
            for band_index in range(8):
                start = band_index * 12
                value = _bits_to_int(signatures[row_index, start : start + 12])
                buckets.setdefault((band_index, value), []).append(track.track_id)
        by_id = {track.track_id: track for track in embedding_tracks}
        for ids in buckets.values():
            if len(ids) < 2:
                continue
            for pair in _duration_window_candidate_pairs(
                [by_id[track_id] for track_id in ids],
                config,
            ):
                sources_by_pair.setdefault(pair, set()).add(f"{embedding_key}_lsh")
    return sources_by_pair


def score_pair(
    left: TrackRecord,
    right: TrackRecord,
    config: PresetConfig,
    *,
    source_config: SourceConfig | None = None,
    fingerprint_similarity: float | None = None,
    candidate_sources: Iterable[str] = (),
) -> PairEvidence:
    selected_sources = source_config or resolve_source_config()
    similarities = {
        source: (
            _embedding_similarity(left, right, source)
            if source in selected_sources.sources
            else None
        )
        for source in SUPPORTED_EMBEDDINGS
    }
    mert = similarities["mert"]
    maest = similarities["maest"]
    muq = similarities["muq"]
    clap = similarities["clap"]
    content_similarity = _content_similarity(
        similarities,
        selected_sources,
    )
    sonara = _sonara_similarity(left, right)
    duration_diff, duration_ratio = _duration_distance(left, right)
    blocked: list[str] = []
    weighted = 0.0
    total = 0.0
    for source in ("mert", "maest"):
        if source not in selected_sources.sources:
            continue
        value = similarities[source]
        if value is None:
            continue
        weight = selected_sources.weights[source]
        weighted += value * weight
        total += weight
    if sonara is not None:
        weighted += sonara * 0.14
        total += 0.14
    for source in ("muq", "clap"):
        if source not in selected_sources.sources:
            continue
        value = similarities[source]
        if value is None:
            continue
        weight = selected_sources.weights[source]
        weighted += value * weight
        total += weight
    if duration_ratio is not None:
        duration_score = max(0.0, 1.0 - min(duration_ratio / max(config.duration_ratio, 0.0001), 1.0))
        weighted += duration_score * 0.05
        total += 0.05
        if duration_diff is not None and duration_diff > max(config.duration_seconds, (min(left.duration or 0, right.duration or 0) * config.duration_ratio)):
            blocked.append("duration mismatch")
    else:
        blocked.append("missing duration")
    for required_source in DELETE_SAFETY_EMBEDDINGS:
        if required_source not in selected_sources.sources:
            blocked.append(f"{required_source.upper()} source disabled")
            continue
        required_similarity = similarities[required_source]
        if required_similarity is None:
            blocked.append(
                f"missing {required_source.upper()} embedding"
            )
    if not _uses_legacy_delete_safety_config(selected_sources):
        corroboration_weighted = 0.0
        corroboration_total = 0.0
        corroboration_available = True
        for required_source in DELETE_SAFETY_EMBEDDINGS:
            if required_source not in selected_sources.sources:
                corroboration_available = False
                continue
            required_weight = selected_sources.weights[required_source]
            if required_weight <= 0:
                blocked.append(
                    f"{required_source.upper()} weight is not positive"
                )
                corroboration_available = False
                continue
            required_similarity = similarities[required_source]
            if required_similarity is None:
                corroboration_available = False
                continue
            corroboration_weighted += (
                required_similarity * required_weight
            )
            corroboration_total += required_weight
        if corroboration_available and corroboration_total > 0:
            corroboration = max(
                0.0,
                min(
                    1.0,
                    corroboration_weighted / corroboration_total,
                ),
            )
            if corroboration < config.min_similarity:
                blocked.append(
                    "MERT+MAEST corroboration below delete safety "
                    f"threshold ({corroboration:.6f} < "
                    f"{config.min_similarity:.6f})"
                )
    if content_similarity is None:
        blocked.append("missing content similarity")
    elif content_similarity < config.min_similarity:
        blocked.append("content similarity below threshold")
    score = (weighted / total) if total else 0.0
    return PairEvidence(
        left_id=left.track_id,
        right_id=right.track_id,
        score=max(0.0, min(1.0, score)),
        content_similarity=content_similarity,
        mert_similarity=mert,
        maest_similarity=maest,
        muq_similarity=muq,
        clap_similarity=clap,
        sonara_similarity=sonara,
        duration_diff_seconds=duration_diff,
        duration_diff_ratio=duration_ratio,
        blocked_reasons=tuple(blocked),
        fingerprint_similarity=fingerprint_similarity,
        candidate_sources=tuple(sorted(set(candidate_sources))),
    )


def build_report(
    groups: list[DuplicateGroup],
    tracks: list[TrackRecord],
    config: PresetConfig,
    *,
    db_path: Path | None = None,
    database_track_count: int | None = None,
    root: Path,
    path_contains: list[str],
    source_config: SourceConfig | None = None,
    fingerprint_retrieval: Mapping[str, int | float] | None = None,
    spectral_results: Mapping[int, SpectralResult] | None = None,
) -> dict[str, object]:
    selected_sources = source_config or resolve_source_config()
    selected_spectral = dict(spectral_results or {})
    by_id = {track.track_id: track for track in tracks}
    report_groups: list[dict[str, object]] = []
    for group in groups:
        group_tracks = [by_id[track_id] for track_id in group.track_ids]
        keeper = choose_keeper(group_tracks, spectral_results=selected_spectral)
        pair_by_ids = {frozenset((pair.left_id, pair.right_id)): pair for pair in group.pair_evidence}
        direct_pairs_from_keeper = {
            track.track_id: pair_by_ids.get(frozenset((keeper.track_id, track.track_id)))
            for track in group_tracks
            if track.track_id != keeper.track_id
        }
        ambiguous = any(pair is None for pair in direct_pairs_from_keeper.values())
        blocked_reasons = sorted({reason for pair in group.pair_evidence for reason in pair.blocked_reasons})
        if ambiguous:
            blocked_reasons.append("ambiguous chain: not every candidate has a direct high-confidence match to keeper")
        keeper_spectral = selected_spectral.get(keeper.track_id)
        if keeper_spectral is not None and keeper_spectral.suspected_transcode:
            blocked_reasons.append("every remaining copy is a suspected transcode; verify spectra by ear")
        candidates = []
        for track in group_tracks:
            if track.track_id == keeper.track_id:
                continue
            direct = direct_pairs_from_keeper[track.track_id]
            safe, reasons = _candidate_safety(direct, config, ambiguous=ambiguous)
            decision = "delete_candidate" if safe else "review"
            candidate_spectral = selected_spectral.get(track.track_id)
            why_lines = _candidate_reason_lines(track, keeper, direct, config, safe=safe, reasons=reasons)
            if candidate_spectral is not None and candidate_spectral.suspected_transcode:
                why_lines.append(
                    f"Candidate spectrum looks transcoded ({candidate_spectral.note}); the keeper holds the wider band."
                )
            candidates.append(
                {
                    "role": "DUPLICATE",
                    "decision": decision,
                    "action": "DELETE CANDIDATE" if safe else "REVIEW MANUALLY",
                    "track_id": track.track_id,
                    "catalog_uuid": track.catalog_uuid,
                    "track_uuid": track.track_uuid,
                    "path": track.path,
                    "size": track.size,
                    "file_modified_ns": track.file_modified_ns,
                    "score_vs_keeper": _round_float(direct.score if direct else None),
                    "content_similarity_vs_keeper": _round_float(direct.content_similarity if direct else None),
                    "safe_to_delete": "true_candidate" if safe else "false",
                    "blocked_reasons": reasons,
                    "why_delete_or_review": why_lines,
                    "format_rank": format_rank(track.path),
                    "size_per_second": _round_float(size_per_second(track)),
                    "metadata_completeness": metadata_completeness(track),
                    "spectral_cutoff_hz": candidate_spectral.cutoff_hz if candidate_spectral else None,
                    "suspected_transcode": candidate_spectral.suspected_transcode if candidate_spectral else None,
                    "spectral_note": candidate_spectral.note if candidate_spectral else None,
                }
            )
        best_score = max((pair.score for pair in group.pair_evidence), default=0.0)
        keeper_payload = track_payload(
            keeper,
            include_keeper_reasons=True,
            role="KEEP",
            decision="keep",
            group_tracks=group_tracks,
            spectral=keeper_spectral,
        )
        suspected_sibling_count = sum(
            1
            for track in group_tracks
            if track.track_id != keeper.track_id
            and (result := selected_spectral.get(track.track_id)) is not None
            and result.suspected_transcode
        )
        if (
            suspected_sibling_count
            and keeper_spectral is not None
            and not keeper_spectral.suspected_transcode
        ):
            keeper_payload["why_keep"].append(
                f"Full-band spectrum while {suspected_sibling_count} duplicate cop"
                f"{'y' if suspected_sibling_count == 1 else 'ies'} look transcoded."
            )
        report_groups.append(
            {
                "group_id": group.group_id,
                "score": _round_float(best_score),
                "confidence": confidence_category(best_score, config),
                "preset": config.name,
                "min_score": config.min_score,
                "min_similarity": config.min_similarity,
                "blocked_reasons": blocked_reasons,
                "suggested_keeper": keeper_payload,
                "candidate_deletes": sorted(candidates, key=lambda item: int(item["track_id"])),
                "tracks": [
                    track_payload(
                        track,
                        include_keeper_reasons=False,
                        role=("KEEP" if track.track_id == keeper.track_id else "DUPLICATE"),
                        spectral=selected_spectral.get(track.track_id),
                    )
                    for track in group_tracks
                ],
                "pairwise_evidence": [pair_payload(pair) for pair in group.pair_evidence],
            }
        )
    stats = report_statistics(report_groups, tracks)
    return {
        "mode": "report-only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database_path": str(db_path) if db_path is not None else None,
        "root": normalize_path_text(root),
        "path_contains": path_contains,
        "sources": list(selected_sources.sources),
        "weights": dict(selected_sources.weights),
        "preset": config.name,
        "min_score": config.min_score,
        "min_similarity": config.min_similarity,
        "score_semantics": score_semantics_payload(),
        "fingerprint_retrieval": dict(fingerprint_retrieval or {}),
        "spectral_analysis": {
            "checked_track_count": len(selected_spectral),
            "analyzed_track_count": sum(
                1 for result in selected_spectral.values() if result.cutoff_hz is not None
            ),
            "skipped_track_count": sum(
                1 for result in selected_spectral.values() if result.cutoff_hz is None
            ),
            "suspected_transcode_count": sum(
                1 for result in selected_spectral.values() if result.suspected_transcode
            ),
        },
        "database_track_count": database_track_count if database_track_count is not None else len(tracks),
        "scoped_track_count": len(tracks),
        "track_count": len(tracks),
        "group_count": len(report_groups),
        "statistics": stats,
        "groups": report_groups,
    }


def choose_keeper(
    tracks: list[TrackRecord],
    *,
    spectral_results: Mapping[int, SpectralResult] | None = None,
) -> TrackRecord:
    if not tracks:
        raise ValueError("Cannot choose a keeper from an empty group")
    selected_spectral = spectral_results or {}

    def full_band_rank(track: TrackRecord) -> int:
        result = selected_spectral.get(track.track_id)
        return 0 if result is not None and result.suspected_transcode else 1

    return max(
        tracks,
        key=lambda track: (
            full_band_rank(track),
            format_rank(track.path),
            size_per_second(track),
            metadata_completeness(track),
            float(track.mtime),
            -int(track.track_id),
        ),
    )


def score_semantics_payload() -> dict[str, dict[str, object]]:
    return {key: dict(value) for key, value in SCORE_SEMANTICS.items()}


def write_xlsx_report(path: Path, payload: dict[str, object]) -> None:
    sheets = [
        ("Summary", _summary_sheet_rows(payload)),
        ("Groups", _groups_sheet_rows(payload)),
        ("Candidates", _candidates_sheet_rows(payload)),
        ("Pair Evidence", _pair_evidence_sheet_rows(payload)),
        ("Rhythm Lab", _rhythm_lab_sheet_rows(payload)),
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types(len(sheets)))
        archive.writestr("_rels/.rels", _xlsx_root_rels())
        archive.writestr("docProps/app.xml", _xlsx_app_props())
        archive.writestr("docProps/core.xml", _xlsx_core_props(str(payload["generated_at"])))
        archive.writestr("xl/workbook.xml", _xlsx_workbook_xml([name for name, _ in sheets]))
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels(len(sheets)))
        archive.writestr("xl/styles.xml", _xlsx_styles_xml())
        for index, (name, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _xlsx_sheet_xml(name, rows))


def _summary_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    stats = payload.get("statistics", {})
    assert isinstance(stats, dict)
    confidence = stats.get("confidence_counts", {})
    embeddings = stats.get("embedding_coverage", {})
    rhythm_lab = payload.get("rhythm_lab", {})
    path_contains = payload.get("path_contains") or []
    path_filter = ", ".join(str(item) for item in path_contains) if isinstance(path_contains, list) else str(path_contains)
    sources = payload.get("sources", list(SUPPORTED_EMBEDDINGS))
    source_text = (
        ", ".join(str(item) for item in sources)
        if isinstance(sources, list)
        else str(sources)
    )
    weights = payload.get("weights", DEFAULT_SOURCE_WEIGHTS)
    weight_text = (
        ", ".join(
            f"{key}={value}"
            for key, value in weights.items()
        )
        if isinstance(weights, dict)
        else str(weights)
    )
    fingerprint_retrieval = payload.get("fingerprint_retrieval", {})
    spectral_analysis = payload.get("spectral_analysis", {})
    rows: list[list[object]] = [
        ["Audio Dedup Report", "", "", "", ""],
        [
            "Review workbook before deleting files. Report mode is read-only; apply mode deletes only safe candidates after exact confirmation.",
            "",
            "",
            "",
            "",
        ],
        [],
        ["Run settings", "Value", "Notes", "", ""],
        ["Generated at", payload["generated_at"], "Local timestamp when this report was written.", "", ""],
        ["Database", payload.get("database_path") or "", "SQLite library that was read for track metadata and embeddings.", "", ""],
        ["Root", payload["root"], "Only stored track paths inside this root were considered.", "", ""],
        ["Path filter", path_filter or "(none)", "Optional case-insensitive path substring filters.", "", ""],
        ["Mode", payload.get("mode", "report-only"), "Report-only writes evidence and does not delete audio.", "", ""],
        ["Search mode", payload.get("search_mode", ""), "fingerprint: exact SONARA matches decide duplicates, everything stays manual-review. embedding: weighted embedding score decides and can mark safe delete candidates.", "", ""],
        ["Preset", payload["preset"], "safe is conservative; balanced/aggressive widen review scope.", "", ""],
        ["Sources", source_text, "Enabled audio embedding families.", "", ""],
        ["Source weights", weight_text, "Raw weights are renormalized over available enabled evidence.", "", ""],
        ["Min score", payload["min_score"], "Overall duplicate score threshold.", "", ""],
        ["Min content similarity", payload["min_similarity"], "Audio-to-audio embedding gate over enabled MERT, MAEST, MuQ, and CLAP sources; not CLAP text-search score.", "", ""],
        ["Fingerprint review threshold", fingerprint_retrieval.get("fingerprint_review_min_similarity", "") if isinstance(fingerprint_retrieval, dict) else "", "Exact SONARA scores at or above this threshold add manual-review candidates only.", "", ""],
        [],
        ["Decision summary", "Count", "Meaning", "Next action", ""],
        [
            "Total tracks in database",
            payload.get("database_track_count", payload["track_count"]),
            "All tracks currently stored in the selected SQLite database.",
            "Reference only.",
            "",
        ],
        [
            "Tracks inside selected root",
            payload.get("scoped_track_count", payload["track_count"]),
            "Tracks that matched root and optional path filters.",
            "This is the search scope.",
            "",
        ],
        ["Duplicate groups", payload["group_count"], "Potential duplicate clusters found.", "Open the Groups sheet.", ""],
        ["Duplicate candidates", stats.get("candidate_count", 0), "Tracks proposed for delete or manual review.", "Open the Candidates sheet.", ""],
        ["Valid stored fingerprints", fingerprint_retrieval.get("valid_stored_fingerprint_count", 0) if isinstance(fingerprint_retrieval, dict) else 0, "Identity-bound SONARA fingerprints used for independent LSH retrieval.", "Reference only.", ""],
        [
            "Suspected transcodes in groups",
            spectral_analysis.get("suspected_transcode_count", 0) if isinstance(spectral_analysis, dict) else 0,
            "Group members whose spectrum ends in a brickwall below 20 kHz (fake-bitrate evidence).",
            "Keeper choice already prefers full-band copies; confirm by ear.",
            "",
        ],
        [
            "Fake-bitrate duplicate candidates",
            stats.get("fake_bitrate_candidate_count", 0),
            (
                "Duplicate copies (not the keeper) that look transcoded, across "
                f"{stats.get('fake_bitrate_group_count', 0)} group(s)."
            ),
            "Open the Groups sheet; those rows are highlighted amber.",
            "",
        ],
        [
            "Spectral checks",
            (
                f"{spectral_analysis.get('analyzed_track_count', 0)}/{spectral_analysis.get('checked_track_count', 0)}"
                if isinstance(spectral_analysis, dict)
                else ""
            ),
            "Duplicate-group files with a measured frequency cutoff.",
            "Unreachable files and decode errors are skipped, never guessed.",
            "",
        ],
        ["Fingerprint review pairs", fingerprint_retrieval.get("fingerprint_review_pair_count", 0) if isinstance(fingerprint_retrieval, dict) else 0, "Exact SONARA matches that met the review threshold.", "Open Pair Evidence.", ""],
        [
            "Safe delete candidates",
            stats.get("safe_candidate_count", 0),
            "Direct high-confidence matches to the suggested keeper.",
            "Open the Candidates sheet and review every row before apply mode.",
            "",
        ],
        [
            "Manual review candidates",
            stats.get("review_candidate_count", 0),
            "Candidates with blockers or weaker evidence.",
            "Do not delete automatically.",
            "",
        ],
    ]
    if isinstance(rhythm_lab, dict):
        rows.extend(
            [
                [],
                ["Rhythm Lab impact", "Value", "Meaning", "", ""],
                ["Database", rhythm_lab.get("database_path", ""), "Lab database checked for labels/predictions on safe candidates.", "", ""],
                ["Database exists", rhythm_lab.get("database_exists", False), "False means no lab rows can be affected.", "", ""],
                ["Affected tracks on apply", rhythm_lab.get("affected_track_count", 0), "Safe candidates with lab rows.", "", ""],
                ["Affected rows on apply", rhythm_lab.get("affected_row_count", 0), "Rows that apply mode would remove after audio deletion.", "", ""],
            ]
        )
    rows.extend(
        [
            [],
            ["Confidence breakdown", "Groups", "Meaning", "", ""],
        ]
    )
    if isinstance(confidence, dict):
        meanings = {
            "high": "Score is strong and has no major blockers.",
            "medium": "Likely duplicate, but review evidence before deletion.",
            "review": "Needs manual inspection.",
        }
        for label in ("high", "medium", "review"):
            rows.append([label, confidence.get(label, 0), meanings[label], "", ""])
    rows.extend([[], ["Embedding coverage", "Tracks", "Meaning", "", ""]])
    if isinstance(embeddings, dict):
        for label in SUPPORTED_EMBEDDINGS:
            rows.append([label.upper(), embeddings.get(label, 0), "Available vectors used by duplicate scoring.", "", ""])
    semantics = payload.get("score_semantics", {})
    if isinstance(semantics, dict):
        rows.extend([[], ["Score semantics", "Kind", "Range", "Notes", ""]])
        for key in (
            "score",
            "content_similarity",
            "mert_similarity",
            "maest_similarity",
            "muq_similarity",
            "clap_similarity",
            "fingerprint_similarity",
        ):
            item = semantics.get(key, {})
            if isinstance(item, dict):
                rows.append([key, item.get("kind", ""), item.get("range", ""), item.get("notes", ""), ""])
    return rows


GROUPS_SHEET_FAKE_BITRATE_COLUMN_INDEX = 8


def _groups_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "group_id",
            "confidence",
            "score",
            "keeper_track_id",
            "keeper_path",
            "candidate_count",
            "safe_candidates",
            "review_candidates",
            "fake_bitrate_candidates",
            "why_keep",
            "blocked_reasons",
        ]
    ]
    assert rows[0][GROUPS_SHEET_FAKE_BITRATE_COLUMN_INDEX] == "fake_bitrate_candidates"
    for group in payload["groups"]:  # type: ignore[index]
        assert isinstance(group, dict)
        keeper = group["suggested_keeper"]
        assert isinstance(keeper, dict)
        candidates = [candidate for candidate in group["candidate_deletes"] if isinstance(candidate, dict)]  # type: ignore[index]
        rows.append(
            [
                group["group_id"],
                group["confidence"],
                group["score"],
                keeper["track_id"],
                keeper["path"],
                len(candidates),
                sum(1 for candidate in candidates if candidate.get("decision") == "delete_candidate"),
                sum(1 for candidate in candidates if candidate.get("decision") != "delete_candidate"),
                sum(1 for candidate in candidates if candidate.get("suspected_transcode")),
                "; ".join(str(item) for item in keeper.get("why_keep", [])),
                "; ".join(str(item) for item in group.get("blocked_reasons", [])),
            ]
        )
    return rows


CANDIDATES_SHEET_SUSPECTED_TRANSCODE_COLUMN = 10
CANDIDATES_SHEET_KEEPER_SUSPECTED_TRANSCODE_COLUMN = 12


def _candidates_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "group_id",
            "action",
            "delete_track_id",
            "delete_path",
            "keeper_track_id",
            "keeper_path",
            "score_vs_keeper",
            "content_similarity_vs_keeper",
            "safe_to_delete",
            "suspected_transcode",
            "spectral_note",
            "keeper_suspected_transcode",
            "keeper_spectral_note",
            "mert_similarity",
            "maest_similarity",
            "muq_similarity",
            "sonara_similarity",
            "fingerprint_similarity",
            "clap_similarity",
            "duration_diff_seconds",
            "duration_diff_ratio",
            "blocked_reasons",
            "why_delete_or_review",
        ]
    ]
    assert rows[0][CANDIDATES_SHEET_SUSPECTED_TRANSCODE_COLUMN - 1] == "suspected_transcode"
    assert rows[0][CANDIDATES_SHEET_KEEPER_SUSPECTED_TRANSCODE_COLUMN - 1] == "keeper_suspected_transcode"
    for group in payload["groups"]:  # type: ignore[index]
        assert isinstance(group, dict)
        keeper = group["suggested_keeper"]
        assert isinstance(keeper, dict)
        evidence_by_candidate = _evidence_by_candidate(group, int(keeper["track_id"]))
        for candidate in group["candidate_deletes"]:  # type: ignore[index]
            assert isinstance(candidate, dict)
            evidence = evidence_by_candidate.get(int(candidate["track_id"]), {})
            rows.append(
                [
                    group["group_id"],
                    candidate["action"],
                    candidate["track_id"],
                    candidate["path"],
                    keeper["track_id"],
                    keeper["path"],
                    candidate["score_vs_keeper"],
                    candidate.get("content_similarity_vs_keeper"),
                    candidate["safe_to_delete"],
                    candidate.get("suspected_transcode"),
                    candidate.get("spectral_note"),
                    keeper.get("suspected_transcode"),
                    keeper.get("spectral_note"),
                    evidence.get("mert_similarity"),
                    evidence.get("maest_similarity"),
                    evidence.get("muq_similarity"),
                    evidence.get("sonara_similarity"),
                    evidence.get("fingerprint_similarity"),
                    evidence.get("clap_similarity"),
                    evidence.get("duration_diff_seconds"),
                    evidence.get("duration_diff_ratio"),
                    "; ".join(str(item) for item in candidate.get("blocked_reasons", [])),
                    "; ".join(str(item) for item in candidate.get("why_delete_or_review", [])),
                ]
            )
    return rows


def _pair_evidence_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "group_id",
            "left_track_id",
            "right_track_id",
            "score",
            "content_similarity",
            "mert_similarity",
            "maest_similarity",
            "muq_similarity",
            "sonara_similarity",
            "fingerprint_similarity",
            "clap_similarity",
            "candidate_sources",
            "duration_diff_seconds",
            "duration_diff_ratio",
            "blocked_reasons",
        ]
    ]
    for group in payload["groups"]:  # type: ignore[index]
        assert isinstance(group, dict)
        for evidence in group["pairwise_evidence"]:  # type: ignore[index]
            assert isinstance(evidence, dict)
            rows.append(
                [
                    group["group_id"],
                    evidence["left_track_id"],
                    evidence["right_track_id"],
                    evidence["score"],
                    evidence["content_similarity"],
                    evidence["mert_similarity"],
                    evidence["maest_similarity"],
                    evidence["muq_similarity"],
                    evidence["sonara_similarity"],
                    evidence.get("fingerprint_similarity"),
                    evidence["clap_similarity"],
                    "; ".join(str(item) for item in evidence.get("candidate_sources", [])),
                    evidence["duration_diff_seconds"],
                    evidence["duration_diff_ratio"],
                    "; ".join(str(item) for item in evidence.get("blocked_reasons", [])),
                ]
            )
    return rows


def _rhythm_lab_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "action",
            "catalog_uuid",
            "track_uuid",
            "table_name",
            "classifier_key",
            "label",
            "path",
            "feature_set",
            "model_artifact",
            "confidence",
        ]
    ]
    rhythm_lab = payload.get("rhythm_lab", {})
    if not isinstance(rhythm_lab, dict):
        return rows
    for row in rhythm_lab.get("affected_rows", []):
        if not isinstance(row, dict):
            continue
        rows.append(
            [
                row.get("action", ""),
                row.get("catalog_uuid", ""),
                row.get("track_uuid", ""),
                row.get("table_name", ""),
                row.get("classifier_key", ""),
                row.get("label", ""),
                row.get("path", ""),
                row.get("feature_set", ""),
                row.get("model_artifact", ""),
                row.get("confidence", ""),
            ]
        )
    return rows


def _xlsx_content_types(sheet_count: int) -> str:
    sheet_overrides = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{sheet_overrides}
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''


def _xlsx_root_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def _xlsx_app_props() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>dj-track-similarity</Application>
</Properties>'''


def _xlsx_core_props(generated_at: str) -> str:
    timestamp = generated_at if generated_at.endswith("Z") else f"{generated_at}Z"
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Audio dedup report</dc:title>
<dc:creator>dj-track-similarity</dc:creator>
<dcterms:created xsi:type="dcterms:W3CDTF">{escape(timestamp)}</dcterms:created>
</cp:coreProperties>'''


def _xlsx_workbook_xml(sheet_names: list[str]) -> str:
    sheets = "\n".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
{sheets}
</sheets>
</workbook>'''


def _xlsx_workbook_rels(sheet_count: int) -> str:
    rels = [
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    ]
    rels.append(
        f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{"".join(rels)}
</Relationships>'''


def _xlsx_styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="8">
<font><sz val="11"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF1B5E20"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFB71C1C"/><name val="Calibri"/></font>
<font><sz val="11"/><color rgb="FF374151"/><name val="Calibri"/></font>
<font><b/><sz val="12"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF92400E"/><name val="Calibri"/></font>
</fonts>
<fills count="11">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF263238"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE8F5E9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFEBEE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE3F2FD"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF111827"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF3F4F6"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE0F2FE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF7ED"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD1D5DB"/></left><right style="thin"><color rgb="FFD1D5DB"/></right><top style="thin"><color rgb="FFD1D5DB"/></top><bottom style="thin"><color rgb="FFD1D5DB"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="11">
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="4" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
<xf numFmtId="0" fontId="5" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
<xf numFmtId="0" fontId="6" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="9" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
<xf numFmtId="0" fontId="0" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
<xf numFmtId="0" fontId="7" fillId="10" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _xlsx_sheet_xml(name: str, rows: list[list[object]]) -> str:
    max_cols = max((len(row) for row in rows), default=1)
    if name == "Summary":
        max_cols = max(5, max_cols)
    col_widths = _xlsx_column_widths(rows, max_cols, sheet_name=name)
    cols_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(col_widths, start=1)
    )
    sheet_views = ""
    if name == "Summary":
        sheet_views = '<sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    elif len(rows) > 1:
        sheet_views = '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    rows_xml = "\n".join(_xlsx_row_xml(row, row_index, name) for row_index, row in enumerate(rows, start=1))
    dimension = f"A1:{_xlsx_col_name(max_cols)}{max(1, len(rows))}"
    auto_filter = f'<autoFilter ref="A1:{_xlsx_col_name(max_cols)}1"/>' if name != "Summary" and len(rows) > 1 else ""
    merge_cells = ""
    if name == "Summary":
        merge_cells = '<mergeCells count="2"><mergeCell ref="A1:E1"/><mergeCell ref="A2:E2"/></mergeCells>'
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="{dimension}"/>
{sheet_views}
<cols>{cols_xml}</cols>
<sheetData>
{rows_xml}
</sheetData>
{merge_cells}
{auto_filter}
</worksheet>'''


def _xlsx_row_xml(row: list[object], row_index: int, sheet_name: str) -> str:
    if sheet_name == "Summary" and row_index == 1:
        height = ' ht="32" customHeight="1"'
    elif sheet_name == "Summary" and row_index == 2:
        height = ' ht="40" customHeight="1"'
    else:
        height = ' ht="26" customHeight="1"' if row_index == 1 else ""
    cells = "".join(
        _xlsx_cell_xml(value, row_index, col_index, _xlsx_style_id(value, row, row_index, col_index, sheet_name))
        for col_index, value in enumerate(row, start=1)
    )
    return f'<row r="{row_index}"{height}>{cells}</row>'


def _xlsx_cell_xml(value: object, row_index: int, col_index: int, style_id: int) -> str:
    ref = f"{_xlsx_col_name(col_index)}{row_index}"
    style = f' s="{style_id}"'
    if value is None:
        return f'<c r="{ref}"{style}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return f'<c r="{ref}"{style}/>'
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{ref}" t="inlineStr"{style}><is><t>{text}</t></is></c>'


def _xlsx_style_id(value: object, row: list[object], row_index: int, col_index: int, sheet_name: str) -> int:
    if sheet_name == "Summary":
        first = str(row[0]) if row else ""
        if row_index == 1:
            return 2
        if row_index == 2:
            return 6
        if first in {"Run settings", "Decision summary", "Rhythm Lab impact", "Confidence breakdown", "Embedding coverage"}:
            return 7
        if first == "Safe delete candidates":
            return 3
        if first == "Manual review candidates":
            return 4
        if first == "Mode" and str(row[1] if len(row) > 1 else "") == "apply":
            return 8
        return 9 if col_index in {3, 4} else 5
    if row_index == 1 and sheet_name == "Summary":
        return 2
    if row_index == 1:
        return 1
    if sheet_name == "Groups":
        fake_bitrate_count = row[GROUPS_SHEET_FAKE_BITRATE_COLUMN_INDEX] if len(row) > GROUPS_SHEET_FAKE_BITRATE_COLUMN_INDEX else 0
        if isinstance(fake_bitrate_count, (int, float)) and fake_bitrate_count > 0:
            return 10
        return 5
    if value == "DELETE CANDIDATE":
        return 3
    if value == "REVIEW MANUALLY":
        return 4
    if sheet_name == "Candidates" and value is True and col_index in {CANDIDATES_SHEET_SUSPECTED_TRANSCODE_COLUMN, CANDIDATES_SHEET_KEEPER_SUSPECTED_TRANSCODE_COLUMN}:
        return 10
    return 5


def _xlsx_column_widths(rows: list[list[object]], max_cols: int, *, sheet_name: str) -> list[int]:
    if sheet_name == "Summary":
        return [28, 24, 54, 44, 14][:max_cols]
    widths: list[int] = []
    for col_index in range(max_cols):
        max_len = 10
        for row in rows:
            if col_index >= len(row):
                continue
            value = row[col_index]
            text = "" if value is None else str(value)
            max_len = max(max_len, min(80, len(text)))
        widths.append(max(12, min(72, max_len + 3)))
    return widths


def _xlsx_col_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def write_text_log(path: Path, payload: dict[str, object], *, apply_result: ApplyResult | None = None) -> None:
    rhythm_lab = payload.get("rhythm_lab", {})
    lines = [
        "audio_dedup apply run" if apply_result is not None else "audio_dedup report-only run",
        f"generated_at={payload['generated_at']}",
        f"database={payload.get('database_path') or ''}",
        f"root={payload['root']}",
        f"search_mode={payload.get('search_mode', '')}",
        f"preset={payload['preset']}",
        "sources=" + ",".join(
            str(item)
            for item in payload.get(
                "sources",
                list(SUPPORTED_EMBEDDINGS),
            )
        ),
        "weights=" + ",".join(
            f"{key}={value}"
            for key, value in dict(
                payload.get("weights", DEFAULT_SOURCE_WEIGHTS)
            ).items()
        ),
        f"min_score={payload['min_score']}",
        f"min_similarity={payload['min_similarity']}",
        "min_similarity_semantics=audio-to-audio content gate over enabled MERT/MAEST/MuQ/CLAP embeddings; not CLAP text-search score",
        "muq_similarity_semantics=audio-to-audio cosine over structurally valid current-generation stored MuQ embeddings",
        f"database_track_count={payload.get('database_track_count', payload['track_count'])}",
        f"scoped_track_count={payload.get('scoped_track_count', payload['track_count'])}",
        f"group_count={payload['group_count']}",
        "suspected_transcodes="
        + str(
            payload.get("spectral_analysis", {}).get("suspected_transcode_count", 0)
            if isinstance(payload.get("spectral_analysis"), dict)
            else 0
        ),
    ]
    if isinstance(rhythm_lab, dict):
        lines.extend(
            [
                f"rhythm_lab_summary={rhythm_lab_summary_text(rhythm_lab)}",
                f"rhythm_lab_database={rhythm_lab.get('database_path', '')}",
                f"rhythm_lab_database_exists={rhythm_lab.get('database_exists', False)}",
                f"rhythm_lab_affected_track_count={rhythm_lab.get('affected_track_count', 0)}",
                f"rhythm_lab_affected_row_count={rhythm_lab.get('affected_row_count', 0)}",
            ]
        )
    if apply_result is None:
        lines.append("no files deleted; no databases mutated")
    else:
        lines.extend(
            [
                f"deleted_track_count={len(apply_result.deleted_track_ids)}",
                f"skipped_count={len(apply_result.skipped)}",
                f"failed_count={len(apply_result.failed)}",
                f"rhythm_lab_deleted_rows={apply_result.rhythm_lab_deleted_rows}",
            ]
        )
        if apply_result.deleted_paths:
            lines.append("deleted_files:")
            lines.extend(f"deleted_file={path}" for path in apply_result.deleted_paths)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def rhythm_lab_impact_payload(
    rhythm_lab_db: Path | None,
    candidates: Iterable[dict[str, object]],
) -> dict[str, object]:
    candidate_rows = tuple(candidates)
    identities = _unique_identities(
        _candidate_identity(candidate)
        for candidate in candidate_rows
    )
    ids = tuple(sorted(identity.track_id for identity in identities))
    selected_db = Path(rhythm_lab_db).expanduser().resolve(strict=False) if rhythm_lab_db is not None else None
    payload: dict[str, object] = {
        "database_path": str(selected_db) if selected_db is not None else None,
        "database_exists": bool(selected_db and selected_db.exists()),
        "safe_candidate_track_ids": list(ids),
        "affected_track_count": 0,
        "affected_row_count": 0,
        "affected_rows": [],
    }
    payload["summary"] = rhythm_lab_summary(payload)
    if not ids or selected_db is None or not selected_db.exists():
        return payload

    affected_rows: list[dict[str, object]] = []
    connection = _connect_readonly(selected_db)
    try:
        table_names = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        ]
        wanted_columns = (
            "catalog_uuid",
            "track_uuid",
            "classifier_key",
            "label",
            "selected_path",
            "feature_set",
            "model_artifact",
            "confidence",
        )
        for table_name in table_names:
            quoted_table = _quote_sqlite_identifier(table_name)
            table_columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()]
            if not _has_identity_columns(table_columns):
                continue
            selected_columns = [column for column in wanted_columns if column in table_columns]
            select_sql = ", ".join(_quote_sqlite_identifier(column) for column in selected_columns)
            for chunk in _chunks(list(identities), 200):
                identity_sql, parameters = _identity_predicate(chunk)
                rows = connection.execute(
                    f"""
                    SELECT {select_sql}
                    FROM {quoted_table}
                    WHERE {identity_sql}
                    ORDER BY catalog_uuid, track_uuid
                    """,
                    parameters,
                ).fetchall()
                for row in rows:
                    affected_rows.append(
                        {
                            "action": "DELETE ON APPLY",
                            "table_name": table_name,
                            "catalog_uuid": str(row["catalog_uuid"]),
                            "track_uuid": str(row["track_uuid"]),
                            "classifier_key": row["classifier_key"] if "classifier_key" in row.keys() else None,
                            "label": row["label"] if "label" in row.keys() else None,
                            "path": row["selected_path"] if "selected_path" in row.keys() else None,
                            "feature_set": row["feature_set"] if "feature_set" in row.keys() else None,
                            "model_artifact": row["model_artifact"] if "model_artifact" in row.keys() else None,
                            "confidence": _round_float(row["confidence"]) if "confidence" in row.keys() else None,
                        }
                    )
    finally:
        connection.close()

    affected_rows.sort(
        key=lambda row: (
            str(row["catalog_uuid"]),
            str(row["track_uuid"]),
            str(row["table_name"]),
            str(row.get("classifier_key") or ""),
            str(row.get("feature_set") or ""),
            str(row.get("model_artifact") or ""),
        )
    )
    payload["affected_rows"] = affected_rows
    payload["affected_track_count"] = len(
        {
            (
                str(row["catalog_uuid"]),
                str(row["track_uuid"]),
            )
            for row in affected_rows
        }
    )
    payload["affected_row_count"] = len(affected_rows)
    payload["summary"] = rhythm_lab_summary(payload)
    return payload


def rhythm_lab_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "safe_candidate_count": len(payload.get("safe_candidate_track_ids", [])),
        "database_exists": bool(payload.get("database_exists", False)),
        "affected_track_count": int(payload.get("affected_track_count", 0) or 0),
        "affected_row_count": int(payload.get("affected_row_count", 0) or 0),
    }


def rhythm_lab_summary_text(payload: dict[str, object]) -> str:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = rhythm_lab_summary(payload)
    return (
        f"safe_candidates={int(summary.get('safe_candidate_count', 0) or 0)} "
        f"database_exists={_bool_text(bool(summary.get('database_exists', False)))} "
        f"affected_tracks={int(summary.get('affected_track_count', 0) or 0)} "
        f"affected_rows={int(summary.get('affected_row_count', 0) or 0)}"
    )


def rhythm_lab_cli_summary(payload: dict[str, object]) -> str:
    rhythm_lab = payload.get("rhythm_lab", {})
    if not isinstance(rhythm_lab, dict):
        return "Rhythm Lab: unavailable"
    return f"Rhythm Lab: {rhythm_lab_summary_text(rhythm_lab)}"


def _safe_candidate_count(payload: dict[str, object]) -> int:
    stats = payload.get("statistics", {})
    if isinstance(stats, dict):
        return int(stats.get("safe_candidate_count", 0) or 0)
    return len(safe_delete_candidates(payload))


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def safe_delete_candidates(payload: dict[str, object]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for group in payload.get("groups", []):
        if not isinstance(group, dict):
            continue
        for candidate in group.get("candidate_deletes", []):
            if not isinstance(candidate, dict):
                continue
            if candidate.get("decision") == "delete_candidate" and candidate.get("safe_to_delete") == "true_candidate":
                candidates.append(candidate)
    return candidates


def confirm_apply(candidates: list[dict[str, object]], db_path: Path, root: Path) -> bool:
    print("")
    print("DESTRUCTIVE APPLY REQUESTED")
    print(f"Database: {db_path}")
    print(f"Root: {root}")
    print(f"Safe duplicate candidates to delete: {len(candidates)}")
    print("This will delete audio files from disk and remove only successfully deleted tracks from SQLite.")
    print('Type exactly "APPLY DELETE" to continue:')
    try:
        response = input("> ")
    except EOFError:
        return False
    return response == "APPLY DELETE"


def apply_duplicate_deletions(
    *,
    db_path: Path | None = None,
    database: LibraryDatabase | None = None,
    root: Path,
    payload: dict[str, object],
    rhythm_lab_db: Path | None = None,
) -> ApplyResult:
    selected_database = _resolve_database(database=database, db_path=db_path)
    root_text = canonical_file_path(root)
    deleted_ids: list[int] = []
    deleted_paths: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    candidates = safe_delete_candidates(payload)
    deleted_identities: list[TrackIdentity] = []
    for candidate in candidates:
        track_id = _candidate_track_id(candidate)
        path_text = str(candidate.get("path", ""))
        if not _path_matches(path_text, root_text, []):
            skipped.append(f"track_id={track_id}: path outside root")
            continue
        try:
            expected = _candidate_identity(candidate)
        except (TypeError, ValueError) as error:
            skipped.append(f"track_id={track_id}: invalid report identity ({error})")
            continue
        try:
            current = selected_database.get_track_file_states_by_ids(
                (track_id,),
                include_missing=True,
            )[0]
        except (IndexError, KeyError):
            skipped.append(f"track_id={track_id}: track identity unavailable")
            continue
        if (
            current.catalog_uuid != expected.catalog_uuid
            or current.track_uuid != expected.track_uuid
            or canonical_file_path(current.file_path)
            != canonical_file_path(path_text)
        ):
            skipped.append(f"track_id={track_id}: report identity is stale")
            continue
        try:
            reported_size = int(candidate["size"])
            reported_modified_ns = int(candidate["file_modified_ns"])
        except (KeyError, TypeError, ValueError):
            skipped.append(f"track_id={track_id}: report file facts are missing")
            continue
        if (
            current.file_size_bytes != reported_size
            or current.file_modified_ns != reported_modified_ns
        ):
            skipped.append(f"track_id={track_id}: report file facts are stale")
            continue
        file_path = Path(path_text)
        if not file_path.exists():
            skipped.append(f"track_id={track_id}: file missing")
            continue
        if not file_path.is_file():
            skipped.append(f"track_id={track_id}: path is not a file")
            continue
        try:
            file_path.unlink()
            removal = selected_database.remove_deleted_track(
                expected=expected,
                file_path=path_text,
            )
            if not removal.removed:
                failed.append(
                    f"track_id={track_id}: exact database row was already absent"
                )
                continue
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            failed.append(f"track_id={track_id}: {error}")
            continue
        deleted_ids.append(track_id)
        deleted_identities.append(expected)
        deleted_paths.append(path_text)
    selected_rhythm_lab_db = DEFAULT_RHYTHM_LAB_DB if rhythm_lab_db is None else rhythm_lab_db
    rhythm_lab_deleted_rows = cleanup_rhythm_lab_database(
        selected_rhythm_lab_db,
        deleted_identities,
    )
    return ApplyResult(
        deleted_track_ids=tuple(deleted_ids),
        deleted_paths=tuple(deleted_paths),
        skipped=tuple(skipped),
        failed=tuple(failed),
        rhythm_lab_deleted_rows=rhythm_lab_deleted_rows,
    )

def cleanup_rhythm_lab_database(
    rhythm_lab_db: Path | None,
    identities: Iterable[TrackIdentity],
) -> int:
    selected_identities = _unique_identities(identities)
    if not selected_identities or rhythm_lab_db is None:
        return 0
    selected_db = Path(rhythm_lab_db).expanduser().resolve(strict=False)
    if not selected_db.exists():
        return 0
    deleted_rows = 0
    connection = sqlite3.connect(selected_db)
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        table_names = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        ]
        for table_name in table_names:
            quoted_table = _quote_sqlite_identifier(table_name)
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()}
            if not _has_identity_columns(columns):
                continue
            for chunk in _chunks(list(selected_identities), 200):
                identity_sql, parameters = _identity_predicate(chunk)
                cursor = connection.execute(
                    f"DELETE FROM {quoted_table} WHERE {identity_sql}",
                    parameters,
                )
                deleted_rows += int(cursor.rowcount if cursor.rowcount is not None else 0)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()
    return deleted_rows


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def apply_result_payload(result: ApplyResult) -> dict[str, object]:
    return {
        "deleted_track_ids": list(result.deleted_track_ids),
        "deleted_paths": list(result.deleted_paths),
        "skipped": list(result.skipped),
        "failed": list(result.failed),
        "rhythm_lab_deleted_rows": result.rhythm_lab_deleted_rows,
    }


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _resolve_database(
    *,
    database: LibraryDatabase | None,
    db_path: Path | None,
) -> LibraryDatabase:
    if database is not None:
        if db_path is not None:
            raise ValueError("Pass either database or db_path, not both")
        return database
    if db_path is None:
        raise ValueError("Database path is required")
    selected = Path(db_path).expanduser().resolve(strict=False)
    if not selected.is_file():
        raise FileNotFoundError(f"Database does not exist: {selected}")
    return LibraryDatabase(selected)


def _candidate_track_id(candidate: dict[str, object]) -> int:
    try:
        return int(candidate["track_id"])
    except (KeyError, TypeError, ValueError):
        return -1


def _candidate_identity(candidate: dict[str, object]) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid=_candidate_text(candidate, "catalog_uuid"),
        track_id=int(candidate["track_id"]),
        track_uuid=_candidate_text(candidate, "track_uuid"),
    )


def _candidate_text(
    candidate: dict[str, object],
    field_name: str,
) -> str:
    value = candidate[field_name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _unique_identities(
    identities: Iterable[TrackIdentity],
) -> tuple[TrackIdentity, ...]:
    return tuple(
        sorted(
            set(identities),
            key=lambda identity: (
                identity.catalog_uuid,
                identity.track_uuid,
                identity.track_id,
            ),
        )
    )


def _has_identity_columns(columns: Iterable[str]) -> bool:
    return {
        "catalog_uuid",
        "track_uuid",
    }.issubset(set(columns))


def _identity_predicate(
    identities: list[TrackIdentity],
) -> tuple[str, tuple[object, ...]]:
    if not identities:
        raise ValueError("At least one identity is required")
    predicates: list[str] = []
    parameters: list[object] = []
    for identity in identities:
        predicates.append(
            "(catalog_uuid = ? AND track_uuid = ?)"
        )
        parameters.extend(
            (
                identity.catalog_uuid,
                identity.track_uuid,
            )
        )
    return " OR ".join(predicates), tuple(parameters)


def normalize_path_text(path: str | Path) -> str:
    text = str(path).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    normalized = text.replace("\\", "/").rstrip("/")
    return normalized or text.replace("\\", "/")


def format_rank(path: str) -> int:
    return LOSSLESS_RANKS.get(Path(path).suffix.casefold(), 0)


def size_per_second(track: TrackRecord) -> float:
    if not track.duration or track.duration <= 0:
        return 0.0
    return float(track.size) / float(track.duration)


def metadata_completeness(track: TrackRecord) -> int:
    count = 0
    for value in (track.artist, track.title, track.album, track.duration):
        if value not in (None, ""):
            count += 1
    if track.metadata.get("genre") or track.metadata.get("genres"):
        count += 1
    return count


def confidence_category(score: float, config: PresetConfig) -> str:
    if score >= max(0.98, config.min_score):
        return "high"
    if score >= max(0.94, config.min_score):
        return "medium"
    return "review"


def track_payload(
    track: TrackRecord,
    *,
    include_keeper_reasons: bool,
    role: str | None = None,
    decision: str | None = None,
    group_tracks: list[TrackRecord] | None = None,
    spectral: SpectralResult | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": role,
        "decision": decision,
        "track_id": track.track_id,
        "catalog_uuid": track.catalog_uuid,
        "track_uuid": track.track_uuid,
        "path": track.path,
        "artist": track.artist,
        "title": track.title,
        "album": track.album,
        "duration": _round_float(track.duration),
        "bpm": _round_float(track.bpm),
        "musical_key": track.musical_key,
        "size": track.size,
        "mtime": track.mtime,
        "file_modified_ns": track.file_modified_ns,
        "format_rank": format_rank(track.path),
        "size_per_second": _round_float(size_per_second(track)),
        "metadata_completeness": metadata_completeness(track),
        "embeddings": sorted(track.embeddings),
        "spectral_cutoff_hz": spectral.cutoff_hz if spectral else None,
        "spectral_sharpness_db": spectral.sharpness_db if spectral else None,
        "suspected_transcode": spectral.suspected_transcode if spectral else None,
        "spectral_note": spectral.note if spectral else None,
    }
    if include_keeper_reasons:
        payload["keeper_reasons"] = {
            "format_rank": format_rank(track.path),
            "size_per_second": _round_float(size_per_second(track)),
            "metadata_completeness": metadata_completeness(track),
            "mtime": track.mtime,
        }
        payload["why_keep"] = _keeper_reason_lines(track, group_tracks or [track])
    return payload


def pair_payload(pair: PairEvidence) -> dict[str, object]:
    return {
        "left_track_id": pair.left_id,
        "right_track_id": pair.right_id,
        "score": _round_float(pair.score),
        "content_similarity": _round_float(pair.content_similarity),
        "mert_similarity": _round_float(pair.mert_similarity),
        "maest_similarity": _round_float(pair.maest_similarity),
        "muq_similarity": _round_float(pair.muq_similarity),
        "clap_similarity": _round_float(pair.clap_similarity),
        "sonara_similarity": _round_float(pair.sonara_similarity),
        "fingerprint_similarity": _round_float(pair.fingerprint_similarity),
        "candidate_sources": list(pair.candidate_sources),
        "duration_diff_seconds": _round_float(pair.duration_diff_seconds),
        "duration_diff_ratio": _round_float(pair.duration_diff_ratio),
        "blocked_reasons": list(pair.blocked_reasons),
    }


def report_statistics(report_groups: list[dict[str, object]], tracks: list[TrackRecord]) -> dict[str, object]:
    confidence_counts = {"high": 0, "medium": 0, "review": 0}
    safe_candidates = 0
    review_candidates = 0
    candidate_count = 0
    fake_bitrate_candidate_count = 0
    duplicate_track_ids: set[int] = set()
    fake_bitrate_group_ids: set[int] = set()
    for group in report_groups:
        confidence = str(group.get("confidence", "review"))
        if confidence in confidence_counts:
            confidence_counts[confidence] += 1
        for candidate in group.get("candidate_deletes", []):  # type: ignore[union-attr]
            if not isinstance(candidate, dict):
                continue
            candidate_count += 1
            duplicate_track_ids.add(int(candidate["track_id"]))
            if candidate.get("decision") == "delete_candidate":
                safe_candidates += 1
            else:
                review_candidates += 1
            if candidate.get("suspected_transcode"):
                fake_bitrate_candidate_count += 1
                fake_bitrate_group_ids.add(int(group["group_id"]))
    embedding_coverage = {
        key: sum(1 for track in tracks if key in track.embeddings)
        for key in SUPPORTED_EMBEDDINGS
    }
    return {
        "candidate_count": candidate_count,
        "duplicate_track_count": len(duplicate_track_ids),
        "safe_candidate_count": safe_candidates,
        "review_candidate_count": review_candidates,
        "fake_bitrate_candidate_count": fake_bitrate_candidate_count,
        "fake_bitrate_group_count": len(fake_bitrate_group_ids),
        "confidence_counts": confidence_counts,
        "embedding_coverage": embedding_coverage,
    }


def _keeper_reason_lines(keeper: TrackRecord, tracks: list[TrackRecord]) -> list[str]:
    reasons = ["Highest keeper ranking inside this duplicate group."]
    if all(format_rank(keeper.path) >= format_rank(track.path) for track in tracks):
        reasons.append(f"Best or tied-best audio format rank in group: {format_rank(keeper.path)}.")
    if all(size_per_second(keeper) >= size_per_second(track) for track in tracks):
        reasons.append(f"Best or tied-best size-per-second quality proxy: {_format_float(size_per_second(keeper))}.")
    if all(metadata_completeness(keeper) >= metadata_completeness(track) for track in tracks):
        reasons.append(f"Best or tied-best metadata completeness: {metadata_completeness(keeper)} fields.")
    return reasons


def _candidate_reason_lines(
    candidate: TrackRecord,
    keeper: TrackRecord,
    pair: PairEvidence | None,
    config: PresetConfig,
    *,
    safe: bool,
    reasons: list[str],
) -> list[str]:
    if not safe:
        return [f"Manual review required: {reason}." for reason in reasons] or ["Manual review required before deleting this file."]
    lines = [
        f"Direct score vs keeper meets threshold: {_format_float(pair.score if pair else None)} >= {_format_float(config.direct_keeper_score)}.",
        f"Content similarity meets threshold: {_format_float(pair.content_similarity if pair else None)} >= {_format_float(config.min_similarity)}.",
        f"Keeper track_id={keeper.track_id} outranks candidate track_id={candidate.track_id} by format, bitrate proxy, metadata, mtime, or id tie-break.",
    ]
    if pair and pair.duration_diff_seconds is not None:
        lines.append(f"Duration difference is {_format_float(pair.duration_diff_seconds)} seconds.")
    return lines


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _track_from_row(
    row: sqlite3.Row,
    *,
    catalog_uuid: str,
) -> TrackRecord:
    genres = _json_string_list(row["genres_json"])
    sonara_features = {
        key: value
        for key, value in {
            "bpm": row["detected_bpm"],
            "danceability": row["danceability_score"],
            "energy": row["energy_score"],
            "valence": row["valence_score"],
            "acousticness": row["acousticness_score"],
            "spectral_centroid_mean": row["spectral_centroid_hz"],
            "onset_density": row["onset_density_per_second"],
            "dynamic_range_db": row["dynamic_range_db"],
            "loudness_lufs": row["integrated_loudness_lufs"],
        }.items()
        if value is not None
    }
    metadata: dict[str, object] = {}
    if genres:
        metadata["genres"] = genres
    if sonara_features:
        metadata["sonara_features"] = sonara_features
    if row["sample_rate_hz"] is not None:
        metadata["sample_rate_hz"] = int(row["sample_rate_hz"])
    if row["bit_rate_bps"] is not None:
        metadata["bit_rate_bps"] = int(row["bit_rate_bps"])
    modified_ns = int(row["file_modified_ns"])
    return TrackRecord(
        track_id=int(row["track_id"]),
        path=str(row["file_path"]),
        size=int(row["file_size_bytes"]),
        mtime=modified_ns / 1_000_000_000,
        artist=_string_or_none(row["artist"]),
        title=_string_or_none(row["title"]),
        album=_string_or_none(row["album"]),
        bpm=_float_or_none(row["tag_bpm"]),
        musical_key=_string_or_none(row["tag_key"]),
        duration=_float_or_none(row["audio_duration_seconds"]),
        metadata=metadata,
        embeddings={},
        catalog_uuid=catalog_uuid,
        track_uuid=str(row["track_uuid"]),
        file_modified_ns=modified_ns,
    )


def _attach_embeddings(
    connection: sqlite3.Connection,
    tracks: list[TrackRecord],
    *,
    sources: Iterable[str] = SUPPORTED_EMBEDDINGS,
    progress_callback: ProgressCallback | None = None,
) -> None:
    if not tracks:
        return
    embeddings_by_track = {track.track_id: {} for track in tracks}
    identity_by_track = {
        track.track_id: track.track_uuid
        for track in tracks
    }
    track_ids = [track.track_id for track in tracks]
    for family in sources:
        if family not in SUPPORTED_EMBEDDINGS:
            raise ValueError(f"Unsupported embedding source: {family}")
        specification = current_embedding_spec(family)
        table = f"{family}_embeddings"
        message = f"Loading {family.upper()} embeddings"
        _report_progress(progress_callback, 0, len(track_ids), message)
        processed = 0
        for chunk in _chunks(track_ids, EMBEDDING_LOAD_CHUNK_SIZE):
            placeholders = ",".join("?" for _ in chunk)
            rows = connection.execute(
                f"""
                SELECT
                    track_id,
                    track_uuid,
                    dim,
                    normalization,
                    embedding_blob
                FROM {table}
                WHERE track_id IN ({placeholders})
                ORDER BY track_id
                """,
                chunk,
            ).fetchall()
            for row in rows:
                track_id = int(row["track_id"])
                expected_identity = identity_by_track.get(track_id)
                if expected_identity != str(row["track_uuid"]):
                    continue
                dim = int(row["dim"])
                if (
                    dim != specification.dimension
                    or str(row["normalization"]) != specification.normalization
                ):
                    continue
                vector = np.frombuffer(
                    row["embedding_blob"],
                    dtype="<f4",
                ).copy()
                if (
                    vector.shape != (dim,)
                    or not np.all(np.isfinite(vector))
                ):
                    continue
                norm = float(np.linalg.norm(vector))
                if not math.isfinite(norm) or norm <= 0:
                    continue
                if (
                    specification.normalization == "l2"
                    and not np.isclose(
                        norm,
                        1.0,
                        rtol=1e-4,
                        atol=1e-5,
                    )
                ):
                    continue
                embeddings_by_track[track_id][family] = (
                    vector / norm
                ).astype(np.float32)
            processed += len(chunk)
            _report_progress(progress_callback, processed, len(track_ids), message)
    for index, track in enumerate(tracks):
        tracks[index] = TrackRecord(
            track_id=track.track_id,
            path=track.path,
            size=track.size,
            mtime=track.mtime,
            artist=track.artist,
            title=track.title,
            album=track.album,
            bpm=track.bpm,
            musical_key=track.musical_key,
            duration=track.duration,
            metadata=track.metadata,
            embeddings=embeddings_by_track[track.track_id],
            catalog_uuid=track.catalog_uuid,
            track_uuid=track.track_uuid,
            file_modified_ns=track.file_modified_ns,
        )

def _path_matches(path: str, root: str, contains: list[str]) -> bool:
    normalized = canonical_file_path(path)
    key = normalized.casefold()
    root_key = canonical_file_path(root).casefold()
    if key != root_key and not key.startswith(root_key + "/"):
        return False
    return all(item in key for item in contains)


def _candidate_duration_compatible(left: TrackRecord, right: TrackRecord, config: PresetConfig) -> bool:
    diff, ratio = _duration_distance(left, right)
    if diff is None or ratio is None:
        return True
    shorter = min(float(left.duration or 0.0), float(right.duration or 0.0))
    return diff <= max(config.duration_seconds, shorter * config.duration_ratio)


def _embedding_similarity(left: TrackRecord, right: TrackRecord, key: str) -> float | None:
    left_vector = left.embeddings.get(key)
    right_vector = right.embeddings.get(key)
    if left_vector is None or right_vector is None or left_vector.shape != right_vector.shape:
        return None
    return max(-1.0, min(1.0, float(left_vector @ right_vector)))


def _content_similarity(
    similarities: Mapping[str, float | None],
    source_config: SourceConfig,
) -> float | None:
    weighted = 0.0
    total = 0.0
    for source in SUPPORTED_EMBEDDINGS:
        if source not in source_config.sources:
            continue
        value = similarities.get(source)
        if value is None:
            continue
        weight = source_config.weights[source]
        weighted += value * weight
        total += weight
    if total == 0.0:
        return None
    return max(0.0, min(1.0, weighted / total))


def _passes_content_similarity(pair: PairEvidence, config: PresetConfig) -> bool:
    return pair.content_similarity is not None and pair.content_similarity >= config.min_similarity


def _sonara_similarity(left: TrackRecord, right: TrackRecord) -> float | None:
    left_features = _sonara_features(left)
    right_features = _sonara_features(right)
    if not left_features or not right_features:
        return None
    diffs: list[float] = []
    for field in SONARA_FIELDS:
        left_value = _float_or_none(left_features.get(field))
        right_value = _float_or_none(right_features.get(field))
        if left_value is None or right_value is None:
            continue
        if field == "bpm":
            diff = min(_bpm_distance(left_value, right_value) or 0.0, 8.0) / 8.0
        elif field == "loudness_lufs":
            diff = min(abs(left_value - right_value), 24.0) / 24.0
        elif field == "dynamic_range_db":
            diff = min(abs(left_value - right_value), 20.0) / 20.0
        else:
            diff = min(abs(left_value - right_value), 1.0)
        diffs.append(diff)
    if not diffs:
        return None
    return max(0.0, min(1.0, 1.0 - float(np.mean(diffs))))


def _sonara_features(track: TrackRecord) -> dict[str, object] | None:
    features = track.metadata.get("sonara_features")
    return features if isinstance(features, dict) else None


def _duration_distance(left: TrackRecord, right: TrackRecord) -> tuple[float | None, float | None]:
    if left.duration is None or right.duration is None or left.duration <= 0 or right.duration <= 0:
        return None, None
    diff = abs(float(left.duration) - float(right.duration))
    return diff, diff / min(float(left.duration), float(right.duration))


def _bpm_distance(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or left <= 0 or right <= 0:
        return None
    variants_left = (left / 2.0, left, left * 2.0)
    variants_right = (right / 2.0, right, right * 2.0)
    return min(abs(a - b) for a in variants_left for b in variants_right)


def _ordered_pair(left_id: int, right_id: int) -> tuple[int, int]:
    return (left_id, right_id) if left_id < right_id else (right_id, left_id)


def _bits_to_int(bits: np.ndarray) -> int:
    value = 0
    for bit in bits.tolist():
        value = (value << 1) | int(bool(bit))
    return value


def _projection_seed(embedding_key: str, dim: int) -> int:
    base = 17_311 if embedding_key == "mert" else 29_327
    return base + int(dim)


def _connected_components(edges: list[PairEvidence]) -> list[list[PairEvidence]]:
    neighbors: dict[int, set[int]] = {}
    edge_by_node: dict[int, list[PairEvidence]] = {}
    for edge in edges:
        neighbors.setdefault(edge.left_id, set()).add(edge.right_id)
        neighbors.setdefault(edge.right_id, set()).add(edge.left_id)
        edge_by_node.setdefault(edge.left_id, []).append(edge)
        edge_by_node.setdefault(edge.right_id, []).append(edge)
    seen: set[int] = set()
    components: list[list[PairEvidence]] = []
    for start in sorted(neighbors):
        if start in seen:
            continue
        stack = [start]
        nodes: set[int] = set()
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            nodes.add(node)
            stack.extend(sorted(neighbors.get(node, ()), reverse=True))
        component_edges = {
            edge
            for node in nodes
            for edge in edge_by_node.get(node, [])
            if edge.left_id in nodes and edge.right_id in nodes
        }
        components.append(sorted(component_edges, key=lambda item: (item.left_id, item.right_id)))
    return components


def _candidate_safety(pair: PairEvidence | None, config: PresetConfig, *, ambiguous: bool) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if ambiguous:
        reasons.append("ambiguous chain")
    if pair is None:
        reasons.append("weak direct keeper match")
    else:
        if pair.candidate_sources == ("fingerprint_lsh",):
            if pair.fingerprint_similarity is not None:
                reasons.append(
                    f"SONARA fingerprint-only candidate: exact fingerprint match "
                    f"{_format_float(pair.fingerprint_similarity)} is strong duplicate evidence, but "
                    "fingerprint evidence alone never authorizes automatic deletion"
                )
            else:
                reasons.append("SONARA fingerprint-only candidate requires manual review")
        if pair.score < config.direct_keeper_score:
            reasons.append("weak direct keeper match")
        if not _passes_content_similarity(pair, config):
            reasons.append("content similarity below threshold")
        if pair.duration_diff_ratio is not None and pair.duration_diff_ratio > config.strict_duration_ratio:
            reasons.append("duration mismatch")
        reasons.extend(pair.blocked_reasons)
    return not reasons, sorted(set(reasons))


def _evidence_by_candidate(group: dict[str, object], keeper_id: int) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for item in group["pairwise_evidence"]:  # type: ignore[index]
        assert isinstance(item, dict)
        left = int(item["left_track_id"])
        right = int(item["right_track_id"])
        if left == keeper_id:
            result[right] = item
        elif right == keeper_id:
            result[left] = item
    return result


def _json_string_list(value: object) -> list[str]:
    if value is None:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        item.strip()
        for item in parsed
        if isinstance(item, str) and item.strip()
    ]


def _float_or_none(value: object) -> float | None:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _round_float(value: object) -> float | None:
    number = _float_or_none(value)
    return None if number is None else round(number, 6)


def _format_float(value: object) -> str:
    number = _float_or_none(value)
    return "" if number is None else f"{number:.6f}"


def _unique_report_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to find unique report path for {path}")


def _chunks(values: list[_T], size: int) -> Iterable[list[_T]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


if __name__ == "__main__":
    raise SystemExit(main())
