from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Mapping

from .spectral import (
    SpectralResult,
)

from . import config as config_module
from . import keeper as keeper_module
from . import models as models_module
from . import values as values_module


def build_report(
    groups: list[models_module.DuplicateGroup],
    tracks: list[models_module.TrackRecord],
    config: models_module.PresetConfig,
    *,
    db_path: Path | None = None,
    database_track_count: int | None = None,
    root: Path,
    path_contains: list[str],
    source_config: models_module.SourceConfig | None = None,
    fingerprint_retrieval: Mapping[str, int | float] | None = None,
    spectral_results: Mapping[int, SpectralResult] | None = None,
) -> dict[str, object]:
    selected_sources = source_config or config_module.resolve_source_config()
    selected_spectral = dict(spectral_results or {})
    by_id = {track.track_id: track for track in tracks}
    report_groups: list[dict[str, object]] = []
    for group in groups:
        group_tracks = [by_id[track_id] for track_id in group.track_ids]
        keeper = keeper_module.choose_keeper(group_tracks, spectral_results=selected_spectral)
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
        master_reasons = keeper_module.master_difference_reasons(group_tracks)
        comparison_review_reasons = keeper_module.keeper_review_reasons(group_tracks)
        blocked_reasons.extend(comparison_review_reasons)
        candidates = []
        for track in group_tracks:
            if track.track_id == keeper.track_id:
                continue
            direct = direct_pairs_from_keeper[track.track_id]
            safe, reasons = keeper_module._candidate_safety(direct, config, ambiguous=ambiguous)
            if comparison_review_reasons:
                # The comparator could not judge this group on measurements
                # alone, so which copy to keep is the reviewer's call and
                # nothing here is deletable.
                safe = False
                reasons = sorted({*reasons, *comparison_review_reasons})
            decision = "delete_candidate" if safe else "review"
            candidate_spectral = selected_spectral.get(track.track_id)
            why_lines = keeper_module._candidate_reason_lines(track, keeper, direct, config, safe=safe, reasons=reasons)
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
                    "score_vs_keeper": values_module._round_float(direct.score if direct else None),
                    "content_similarity_vs_keeper": values_module._round_float(direct.content_similarity if direct else None),
                    "safe_to_delete": "true_candidate" if safe else "false",
                    "blocked_reasons": reasons,
                    "why_delete_or_review": why_lines,
                    "format_rank": keeper_module.format_rank(track.path),
                    "size_per_second": values_module._round_float(keeper_module.size_per_second(track)),
                    "metadata_completeness": keeper_module.metadata_completeness(track),
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
            group_spectral=selected_spectral,
        )
        report_groups.append(
            {
                "group_id": group.group_id,
                "score": values_module._round_float(best_score),
                "confidence": keeper_module.confidence_category(best_score, config),
                "preset": config.name,
                "min_score": config.min_score,
                "min_similarity": config.min_similarity,
                "blocked_reasons": blocked_reasons,
                "possible_different_master": bool(master_reasons),
                "quality_comparison_requires_review": bool(comparison_review_reasons),
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
        "root": values_module.normalize_path_text(root),
        "path_contains": path_contains,
        "sources": list(selected_sources.sources),
        "weights": dict(selected_sources.weights),
        "preset": config.name,
        "min_score": config.min_score,
        "min_similarity": config.min_similarity,
        "score_semantics": config_module.score_semantics_payload(),
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


def track_payload(
    track: models_module.TrackRecord,
    *,
    include_keeper_reasons: bool,
    role: str | None = None,
    decision: str | None = None,
    group_tracks: list[models_module.TrackRecord] | None = None,
    spectral: SpectralResult | None = None,
    group_spectral: Mapping[int, SpectralResult] | None = None,
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
        "duration": values_module._round_float(track.duration),
        "bpm": values_module._round_float(track.bpm),
        "musical_key": track.musical_key,
        "size": track.size,
        "mtime": track.mtime,
        "file_modified_ns": track.file_modified_ns,
        "format_rank": keeper_module.format_rank(track.path),
        "size_per_second": values_module._round_float(keeper_module.size_per_second(track)),
        "metadata_completeness": keeper_module.metadata_completeness(track),
        # The spectral verdict is judged against the declared bitrate, so the
        # report carries it: a wall far below what the bitrate promises is the
        # fake-bitrate evidence, and it is unreadable without this number.
        "bit_rate_bps": keeper_module._optional_metadata_int(track, "bit_rate_bps"),
        "sample_rate_hz": keeper_module._optional_metadata_int(track, "sample_rate_hz"),
        "bit_depth": keeper_module._optional_metadata_int(track, "bit_depth"),
        "integrated_loudness_lufs": values_module._round_float(keeper_module._sonara_float(track, "loudness_lufs")),
        "true_peak_dbtp": values_module._round_float(keeper_module._sonara_float(track, "true_peak_dbtp")),
        "dynamic_range_db": values_module._round_float(keeper_module._sonara_float(track, "dynamic_range_db")),
        "loudness_range_lu": values_module._round_float(keeper_module._sonara_float(track, "loudness_range_lu")),
        "channel_count": keeper_module._optional_metadata_int(track, "channel_count"),
        "embeddings": sorted(track.embeddings),
        "spectral_cutoff_hz": spectral.cutoff_hz if spectral else None,
        "spectral_sharpness_db": spectral.sharpness_db if spectral else None,
        "suspected_transcode": spectral.suspected_transcode if spectral else None,
        "spectral_note": spectral.note if spectral else None,
    }
    if include_keeper_reasons:
        payload["keeper_reasons"] = {
            "format_rank": keeper_module.format_rank(track.path),
            "size_per_second": values_module._round_float(keeper_module.size_per_second(track)),
            "metadata_completeness": keeper_module.metadata_completeness(track),
            "mtime": track.mtime,
        }
        payload["why_keep"] = keeper_module._keeper_reason_lines(
            track,
            group_tracks or [track],
            group_spectral,
        )
    return payload


def pair_payload(pair: models_module.PairEvidence) -> dict[str, object]:
    return {
        "left_track_id": pair.left_id,
        "right_track_id": pair.right_id,
        "score": values_module._round_float(pair.score),
        "content_similarity": values_module._round_float(pair.content_similarity),
        "mert_similarity": values_module._round_float(pair.mert_similarity),
        "maest_similarity": values_module._round_float(pair.maest_similarity),
        "muq_similarity": values_module._round_float(pair.muq_similarity),
        "clap_similarity": values_module._round_float(pair.clap_similarity),
        "sonara_similarity": values_module._round_float(pair.sonara_similarity),
        "fingerprint_similarity": values_module._round_float(pair.fingerprint_similarity),
        "candidate_sources": list(pair.candidate_sources),
        "duration_diff_seconds": values_module._round_float(pair.duration_diff_seconds),
        "duration_diff_ratio": values_module._round_float(pair.duration_diff_ratio),
        "blocked_reasons": list(pair.blocked_reasons),
    }


def report_statistics(report_groups: list[dict[str, object]], tracks: list[models_module.TrackRecord]) -> dict[str, object]:
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
        for key in config_module.SUPPORTED_EMBEDDINGS
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
