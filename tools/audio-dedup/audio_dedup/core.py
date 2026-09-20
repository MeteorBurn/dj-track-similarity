from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase

from .fingerprints import (
    fingerprint_candidate_pairs,
    fingerprint_match_scores,
    load_fingerprint_sketches,
    sonara_duplicate_clusters,
)
from .spectral import (
    SpectralResult,
    analyze_file,
    ffmpeg_available,
    skipped_result,
)

from . import config as config_module
from . import models as models_module
from . import progress as progress_module
from . import report_files as report_files_module
from . import report_payload as report_payload_module
from . import scoring as scoring_module
from . import track_loading as track_loading_module


def run_report(
    *,
    db_path: Path | None = None,
    database: LibraryDatabase | None = None,
    path_contains: list[str],
    limit_groups: int | None,
    out_dir: Path,
    mode: str = config_module.MODE_FINGERPRINT_SCAN,
    detect_fake_bitrate: bool = False,
    progress_callback: models_module.ProgressCallback | None = None,
    should_cancel: models_module.CancelCheck | None = None,
) -> models_module.ReportResult:
    if mode not in config_module.SEARCH_MODES:
        raise ValueError(f"Unsupported search mode: {mode}")
    scan_mode = mode == config_module.MODE_FINGERPRINT_SCAN

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
        path_contains=path_contains,
        progress_callback=progress_callback,
    )
    progress_module._raise_if_cancelled(should_cancel)
    progress_module._report_progress(progress_callback, 0, max(1, len(tracks)), f"Loaded {len(tracks)} scoped tracks")
    track_uuids = {
        track.track_id: track.track_uuid
        for track in tracks
        if track.track_uuid
    }
    if scan_mode:
        progress_module._report_progress(progress_callback, 0, max(1, len(tracks)), "Matching SONARA fingerprints")
        connection = selected_database.connect()
        try:
            scan = sonara_duplicate_clusters(
                connection,
                track_uuids,
                {track.track_id: track.analyzed_duration for track in tracks},
                progress_callback=lambda completed, total: progress_module._report_progress(
                    progress_callback,
                    completed,
                    total,
                    "Matching SONARA fingerprints",
                ),
                cancel_hook=cancel_hook,
            )
        finally:
            connection.close()
        progress_module._raise_if_cancelled(should_cancel)
        fingerprint_retrieval = {
            "valid_stored_fingerprint_count": scan.valid_fingerprint_count,
            "rejected_stored_fingerprint_count": scan.rejected_rows,
            "scan_duration_bucket_count": scan.duration_bucket_count,
            "scan_comparison_count": scan.comparison_count,
            "fingerprint_review_pair_count": sum(
                len(cluster.pair_scores) for cluster in scan.clusters
            ),
            "fingerprint_review_min_similarity": config_module.SONARA_DUPLICATE_MIN_SIMILARITY,
            # The bands this mode reads group confidence from, so the review can
            # show them without keeping its own copy of the numbers.
            "fingerprint_confidence_high": config_module.FINGERPRINT_CONFIDENCE_HIGH,
            "fingerprint_confidence_medium": config_module.FINGERPRINT_CONFIDENCE_MEDIUM,
        }
        groups = scoring_module.groups_from_fingerprint_clusters(
            scan.clusters,
            tracks,
            limit_groups=limit_groups,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )
    else:
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
        candidate_pairs = fingerprint_candidate_pairs(list(fingerprint_load.sketches))
        progress_module._raise_if_cancelled(should_cancel)
        progress_module._report_progress(progress_callback, 0, max(1, len(candidate_pairs)), "Verifying SONARA fingerprint candidates")
        connection = selected_database.connect()
        try:
            fingerprint_scores = fingerprint_match_scores(
                connection,
                candidate_pairs,
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
            "fingerprint_lsh_candidate_pair_count": len(candidate_pairs),
            "exact_fingerprint_pair_count": len(fingerprint_scores),
            "fingerprint_review_pair_count": sum(
                score >= config_module.FINGERPRINT_REVIEW_MIN_SIMILARITY
                for score in fingerprint_scores.values()
            ),
            "fingerprint_review_min_similarity": config_module.FINGERPRINT_REVIEW_MIN_SIMILARITY,
            "fingerprint_confidence_high": config_module.FINGERPRINT_CONFIDENCE_HIGH,
            "fingerprint_confidence_medium": config_module.FINGERPRINT_CONFIDENCE_MEDIUM,
        }
        groups = scoring_module.groups_from_fingerprint_pairs(
            tracks,
            fingerprint_scores,
            limit_groups=limit_groups,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )
    progress_module._raise_if_cancelled(should_cancel)
    spectral_results = _spectral_results_for_groups(
        groups,
        tracks,
        detect_fake_bitrate=detect_fake_bitrate,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
    )
    progress_module._report_progress(progress_callback, 0, 0, "Writing reports")
    payload = report_payload_module.build_report(
        groups,
        tracks,
        mode=mode,
        db_path=selected_db,
        database_track_count=database_track_count,
        path_contains=path_contains,
        fingerprint_retrieval=fingerprint_retrieval,
        spectral_results=spectral_results,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # One directory per report keeps its JSON, workbook and log together, and
    # the files keep the report id in their names so each one stays readable
    # once it is downloaded or moved out on its own.
    report_dir = report_files_module._unique_report_dir(out_dir / f"audio_dedup_report_{stamp}")
    report_dir.mkdir(parents=True)
    json_path = report_dir / f"{report_dir.name}.json"
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
    detect_fake_bitrate: bool,
    progress_callback: models_module.ProgressCallback | None = None,
    should_cancel: models_module.CancelCheck | None = None,
) -> dict[int, SpectralResult]:
    if not detect_fake_bitrate:
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
