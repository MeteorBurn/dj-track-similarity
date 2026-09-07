from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from dj_track_similarity.database import LibraryDatabase

from .fingerprints import (
    fingerprint_match_scores,
    load_fingerprint_sketches,
)
from .spectral import (
    SpectralResult,
    analyze_file,
    ffmpeg_available,
    skipped_result,
)

from . import candidates as candidates_module
from . import config as config_module
from . import models as models_module
from . import progress as progress_module
from . import report_files as report_files_module
from . import report_payload as report_payload_module
from . import report_selection as report_selection_module
from . import rhythm_lab as rhythm_lab_module
from . import scoring as scoring_module
from . import track_loading as track_loading_module


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
    mode: str = config_module.MODE_FINGERPRINT,
    skip_spectral: bool = False,
    progress_callback: models_module.ProgressCallback | None = None,
    should_cancel: models_module.CancelCheck | None = None,
) -> models_module.ReportResult:
    config = config_module.resolve_preset(preset_name, min_score=min_score, min_similarity=min_similarity)
    if mode not in config_module.SEARCH_MODES:
        raise ValueError(f"Unsupported search mode: {mode}")
    fingerprint_mode = mode == config_module.MODE_FINGERPRINT
    if fingerprint_mode:
        if sources is not None or weights is not None:
            raise ValueError(
                "--source and --weight require --embedding"
            )
        source_config = models_module.SourceConfig(sources=(), weights={})
    else:
        source_config = config_module.resolve_source_config(sources=sources, weights=weights)

    def cancel_hook() -> None:
        progress_module._raise_if_cancelled(should_cancel)

    selected_database = track_loading_module._resolve_database(database=database, db_path=db_path)
    selected_db = selected_database.path
    progress_module._report_progress(progress_callback, 0, 0, "Reading database")
    progress_module._raise_if_cancelled(should_cancel)
    database_track_count = track_loading_module.count_database_tracks(selected_database)
    progress_module._report_progress(progress_callback, 0, database_track_count, "Loading scoped tracks")
    tracks = track_loading_module.load_tracks(
        selected_database,
        root=root,
        path_contains=path_contains,
        sources=source_config.sources,
        progress_callback=progress_callback,
    )
    progress_module._raise_if_cancelled(should_cancel)
    progress_module._report_progress(progress_callback, 0, max(1, len(tracks)), f"Loaded {len(tracks)} scoped tracks")
    track_uuids = {
        track.track_id: track.track_uuid
        for track in tracks
        if track.track_uuid
    }
    progress_module._report_progress(progress_callback, 0, max(1, len(tracks)), "Loading saved SONARA fingerprint sketches")
    connection = selected_database.connect()
    try:
        fingerprint_load = load_fingerprint_sketches(
            connection,
            track_uuids,
            progress_callback=lambda completed, total: progress_module._report_progress(
                progress_callback,
                completed,
                total,
                "Loading saved SONARA fingerprint sketches",
            ),
            cancel_hook=cancel_hook,
        )
    finally:
        connection.close()
    candidate_sources = candidates_module._candidate_pair_sources(
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
    fingerprint_exact_pairs = candidates_module._fingerprint_exact_candidate_pairs(candidate_sources)
    progress_module._raise_if_cancelled(should_cancel)
    progress_module._report_progress(progress_callback, 0, max(1, len(fingerprint_exact_pairs)), "Verifying SONARA fingerprint candidates")
    connection = selected_database.connect()
    try:
        fingerprint_scores = fingerprint_match_scores(
            connection,
            fingerprint_exact_pairs,
            track_uuids,
            progress_callback=lambda completed, total: progress_module._report_progress(
                progress_callback,
                completed,
                total,
                "Verifying SONARA fingerprint candidates",
            ),
            cancel_hook=cancel_hook,
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
            score >= config_module.FINGERPRINT_REVIEW_MIN_SIMILARITY
            for score in fingerprint_scores.values()
        ),
        "fingerprint_review_min_similarity": config_module.FINGERPRINT_REVIEW_MIN_SIMILARITY,
    }
    groups = scoring_module.find_duplicate_groups(
        tracks,
        config,
        limit_groups=limit_groups,
        source_config=source_config,
        candidate_sources=candidate_sources,
        fingerprint_scores=fingerprint_scores,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
    )
    progress_module._raise_if_cancelled(should_cancel)
    spectral_results = _spectral_results_for_groups(
        groups,
        tracks,
        skip_spectral=skip_spectral,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
    )
    progress_module._report_progress(progress_callback, 0, 0, "Writing reports")
    payload = report_payload_module.build_report(
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
    payload["rhythm_lab"] = rhythm_lab_module.rhythm_lab_impact_payload(
        config_module.DEFAULT_RHYTHM_LAB_DB,
        report_selection_module.safe_delete_candidates(payload),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = report_files_module._unique_report_path(out_dir / f"audio_dedup_report_{stamp}.json")
    xlsx_path = json_path.with_suffix(".xlsx")
    log_path = json_path.with_suffix(".log")
    result = models_module.ReportResult(json_path=json_path, xlsx_path=xlsx_path, log_path=log_path, payload=payload, groups=len(groups))
    report_files_module._write_report_files(result)
    progress_module._report_progress(progress_callback, 1, 1, "Reports written")
    return result


def _spectral_results_for_groups(
    groups: list[models_module.DuplicateGroup],
    tracks: list[models_module.TrackRecord],
    *,
    skip_spectral: bool,
    progress_callback: models_module.ProgressCallback | None = None,
    should_cancel: models_module.CancelCheck | None = None,
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
    progress_module._report_progress(progress_callback, 0, total, message)
    for index, track_id in enumerate(group_track_ids, start=1):
        progress_module._raise_if_cancelled(should_cancel)
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
        progress_module._report_progress(progress_callback, index, total, message)
    return results
