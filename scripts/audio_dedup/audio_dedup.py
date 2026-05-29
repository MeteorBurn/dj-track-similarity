from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import sqlite3
import sys
from typing import Iterable
from xml.sax.saxutils import escape
import zipfile

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DB = Path(r"C:\db\abstracted.sqlite")
DEFAULT_RHYTHM_LAB_DB = REPO_ROOT / "tools" / "rhythm-lab" / "data" / "rhythm_lab.sqlite"
DEFAULT_OUT_DIR = SCRIPT_DIR / "reports"
SUPPORTED_EMBEDDINGS = ("mert", "maest", "clap")
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


@dataclass(frozen=True)
class PresetConfig:
    name: str
    min_score: float
    duration_seconds: float
    duration_ratio: float
    direct_keeper_score: float
    strict_duration_ratio: float


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


@dataclass(frozen=True)
class PairEvidence:
    left_id: int
    right_id: int
    score: float
    mert_similarity: float | None
    maest_similarity: float | None
    clap_similarity: float | None
    sonara_similarity: float | None
    duration_diff_seconds: float | None
    duration_diff_ratio: float | None
    blocked_reasons: tuple[str, ...]


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


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    try:
        result = run_report(
            db_path=args.db,
            root=args.root,
            path_contains=args.path_contains,
            preset_name=args.preset,
            min_score=args.min_score,
            limit_groups=args.limit_groups,
            out_dir=args.out_dir,
        )
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
    print(f"json={result.json_path}")
    print(f"xlsx={result.xlsx_path}")
    print(f"log={result.log_path}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find likely duplicate audio tracks from an existing dj-track-similarity SQLite database. "
            "By default it is report-only; --apply prompts before deleting safe candidates."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=r"Project SQLite database. Default: C:\db\abstracted.sqlite.")
    parser.add_argument("--root", type=Path, required=True, help="Only include DB tracks inside this stored path root.")
    parser.add_argument(
        "--path-contains",
        action="append",
        default=[],
        help="Additional case-insensitive substring filter on stored track paths. Can be repeated.",
    )
    parser.add_argument("--preset", choices=("safe", "balanced", "aggressive"), default="safe")
    parser.add_argument("--min-score", type=float, help="Override the preset duplicate score threshold.")
    parser.add_argument("--limit-groups", type=int, help="Write at most N duplicate groups.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Report output directory.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="After writing reports, prompt for confirmation and delete safe duplicate candidates plus their database rows.",
    )
    return parser.parse_args(argv)


def run_report(
    *,
    db_path: Path,
    root: Path,
    path_contains: list[str],
    preset_name: str,
    min_score: float | None,
    limit_groups: int | None,
    out_dir: Path,
) -> ReportResult:
    config = resolve_preset(preset_name, min_score=min_score)
    selected_db = Path(db_path).expanduser().resolve(strict=False)
    database_track_count = count_database_tracks(selected_db)
    tracks = load_tracks(db_path, root=root, path_contains=path_contains)
    groups = find_duplicate_groups(tracks, config, limit_groups=limit_groups)
    payload = build_report(
        groups,
        tracks,
        config,
        db_path=selected_db,
        database_track_count=database_track_count,
        root=root,
        path_contains=path_contains,
    )
    payload["rhythm_lab"] = rhythm_lab_impact_payload(
        DEFAULT_RHYTHM_LAB_DB,
        [int(candidate["track_id"]) for candidate in safe_delete_candidates(payload)],
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = _unique_report_path(out_dir / f"audio_dedup_report_{stamp}.json")
    xlsx_path = json_path.with_suffix(".xlsx")
    log_path = json_path.with_suffix(".log")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_xlsx_report(xlsx_path, payload)
    write_text_log(log_path, payload)
    return ReportResult(json_path=json_path, xlsx_path=xlsx_path, log_path=log_path, payload=payload, groups=len(groups))


def resolve_preset(name: str, *, min_score: float | None) -> PresetConfig:
    presets = {
        "safe": PresetConfig(
            name="safe",
            min_score=0.965,
            duration_seconds=2.0,
            duration_ratio=0.01,
            direct_keeper_score=0.98,
            strict_duration_ratio=0.01,
        ),
        "balanced": PresetConfig(
            name="balanced",
            min_score=0.95,
            duration_seconds=5.0,
            duration_ratio=0.025,
            direct_keeper_score=0.97,
            strict_duration_ratio=0.025,
        ),
        "aggressive": PresetConfig(
            name="aggressive",
            min_score=0.925,
            duration_seconds=15.0,
            duration_ratio=0.08,
            direct_keeper_score=0.965,
            strict_duration_ratio=0.08,
        ),
    }
    if name not in presets:
        raise ValueError(f"Unsupported preset: {name}")
    config = presets[name]
    if min_score is None:
        return config
    if not 0.0 <= min_score <= 1.0:
        raise ValueError("--min-score must be between 0 and 1")
    return PresetConfig(
        name=config.name,
        min_score=float(min_score),
        duration_seconds=config.duration_seconds,
        duration_ratio=config.duration_ratio,
        direct_keeper_score=config.direct_keeper_score,
        strict_duration_ratio=config.strict_duration_ratio,
    )


def load_tracks(db_path: Path, *, root: Path, path_contains: list[str]) -> list[TrackRecord]:
    selected = Path(db_path).expanduser().resolve(strict=False)
    if not selected.exists():
        raise FileNotFoundError(f"Database does not exist: {selected}")
    root_text = normalize_path_text(root)
    contains = [item.casefold() for item in path_contains if item.strip()]
    connection = _connect_readonly(selected)
    try:
        rows = connection.execute(
            """
            SELECT id, path, size, mtime, artist, title, album, bpm, musical_key, duration, metadata_json
            FROM tracks
            ORDER BY id
            """
        ).fetchall()
        tracks = [_track_from_row(row) for row in rows if _path_matches(row["path"], root_text, contains)]
        _attach_embeddings(connection, tracks)
    finally:
        connection.close()
    return tracks


def count_database_tracks(db_path: Path) -> int:
    selected = Path(db_path).expanduser().resolve(strict=False)
    if not selected.exists():
        raise FileNotFoundError(f"Database does not exist: {selected}")
    connection = _connect_readonly(selected)
    try:
        return int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
    finally:
        connection.close()


def find_duplicate_groups(
    tracks: list[TrackRecord],
    config: PresetConfig,
    *,
    limit_groups: int | None,
) -> list[DuplicateGroup]:
    if len(tracks) < 2:
        return []
    by_id = {track.track_id: track for track in tracks}
    candidate_pairs = _candidate_pair_ids(tracks, config)
    edges: list[PairEvidence] = []
    for left_id, right_id in candidate_pairs:
        left = by_id[left_id]
        right = by_id[right_id]
        if not _candidate_duration_compatible(left, right, config):
            continue
        evidence = score_pair(left, right, config)
        if evidence.score >= config.min_score:
            edges.append(evidence)
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


def _candidate_pair_ids(tracks: list[TrackRecord], config: PresetConfig) -> list[tuple[int, int]]:
    high_dim_pairs = _signature_candidate_pairs(tracks, config)
    if high_dim_pairs:
        return sorted(high_dim_pairs)
    return _duration_window_candidate_pairs(tracks, config)


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


def _signature_candidate_pairs(tracks: list[TrackRecord], config: PresetConfig) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for embedding_key in ("mert", "maest"):
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
            pairs.update(_duration_window_candidate_pairs([by_id[track_id] for track_id in ids], config))
    return pairs


def score_pair(left: TrackRecord, right: TrackRecord, config: PresetConfig) -> PairEvidence:
    mert = _embedding_similarity(left, right, "mert")
    maest = _embedding_similarity(left, right, "maest")
    clap = _embedding_similarity(left, right, "clap")
    sonara = _sonara_similarity(left, right)
    duration_diff, duration_ratio = _duration_distance(left, right)
    blocked: list[str] = []
    weighted = 0.0
    total = 0.0
    for value, weight in ((mert, 0.43), (maest, 0.32), (sonara, 0.14), (clap, 0.04)):
        if value is None:
            continue
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
    if mert is None:
        blocked.append("missing MERT embedding")
    if maest is None:
        blocked.append("missing MAEST embedding")
    score = (weighted / total) if total else 0.0
    return PairEvidence(
        left_id=left.track_id,
        right_id=right.track_id,
        score=max(0.0, min(1.0, score)),
        mert_similarity=mert,
        maest_similarity=maest,
        clap_similarity=clap,
        sonara_similarity=sonara,
        duration_diff_seconds=duration_diff,
        duration_diff_ratio=duration_ratio,
        blocked_reasons=tuple(blocked),
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
) -> dict[str, object]:
    by_id = {track.track_id: track for track in tracks}
    report_groups: list[dict[str, object]] = []
    for group in groups:
        group_tracks = [by_id[track_id] for track_id in group.track_ids]
        keeper = choose_keeper(group_tracks)
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
        candidates = []
        for track in group_tracks:
            if track.track_id == keeper.track_id:
                continue
            direct = direct_pairs_from_keeper[track.track_id]
            safe, reasons = _candidate_safety(direct, config, ambiguous=ambiguous)
            decision = "delete_candidate" if safe else "review"
            candidates.append(
                {
                    "role": "DUPLICATE",
                    "decision": decision,
                    "action": "DELETE CANDIDATE" if safe else "REVIEW MANUALLY",
                    "track_id": track.track_id,
                    "path": track.path,
                    "score_vs_keeper": _round_float(direct.score if direct else None),
                    "safe_to_delete": "true_candidate" if safe else "false",
                    "blocked_reasons": reasons,
                    "why_delete_or_review": _candidate_reason_lines(track, keeper, direct, config, safe=safe, reasons=reasons),
                    "format_rank": format_rank(track.path),
                    "size_per_second": _round_float(size_per_second(track)),
                    "metadata_completeness": metadata_completeness(track),
                }
            )
        best_score = max((pair.score for pair in group.pair_evidence), default=0.0)
        report_groups.append(
            {
                "group_id": group.group_id,
                "score": _round_float(best_score),
                "confidence": confidence_category(best_score, config),
                "preset": config.name,
                "min_score": config.min_score,
                "blocked_reasons": blocked_reasons,
                "suggested_keeper": track_payload(keeper, include_keeper_reasons=True, role="KEEP", decision="keep", group_tracks=group_tracks),
                "candidate_deletes": sorted(candidates, key=lambda item: int(item["track_id"])),
                "tracks": [track_payload(track, include_keeper_reasons=False, role=("KEEP" if track.track_id == keeper.track_id else "DUPLICATE")) for track in group_tracks],
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
        "preset": config.name,
        "min_score": config.min_score,
        "database_track_count": database_track_count if database_track_count is not None else len(tracks),
        "scoped_track_count": len(tracks),
        "track_count": len(tracks),
        "group_count": len(report_groups),
        "statistics": stats,
        "groups": report_groups,
    }


def choose_keeper(tracks: list[TrackRecord]) -> TrackRecord:
    if not tracks:
        raise ValueError("Cannot choose a keeper from an empty group")
    return max(
        tracks,
        key=lambda track: (
            format_rank(track.path),
            size_per_second(track),
            metadata_completeness(track),
            float(track.mtime),
            -int(track.track_id),
        ),
    )


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
    rows: list[list[object]] = [
        ["Duplicate audio summary"],
        ["Generated at", payload["generated_at"]],
        ["Database", payload.get("database_path") or ""],
        ["Root", payload["root"]],
        ["Preset", payload["preset"]],
        ["Min score", payload["min_score"]],
        ["Total tracks in database", payload.get("database_track_count", payload["track_count"])],
        ["Tracks inside selected root", payload.get("scoped_track_count", payload["track_count"])],
        ["Duplicate groups", payload["group_count"]],
        ["Duplicate candidates", stats.get("candidate_count", 0)],
        ["Safe delete candidates", stats.get("safe_candidate_count", 0)],
        ["Manual review candidates", stats.get("review_candidate_count", 0)],
        [],
        ["Rhythm Lab", "Rows"],
    ]
    rhythm_lab = payload.get("rhythm_lab", {})
    if isinstance(rhythm_lab, dict):
        rows.extend(
            [
                ["Database", rhythm_lab.get("database_path", "")],
                ["Database exists", rhythm_lab.get("database_exists", False)],
                ["Affected tracks on apply", rhythm_lab.get("affected_track_count", 0)],
                ["Affected rows on apply", rhythm_lab.get("affected_row_count", 0)],
            ]
        )
    rows.extend(
        [
            [],
            ["Confidence", "Groups"],
        ]
    )
    if isinstance(confidence, dict):
        for label in ("high", "medium", "review"):
            rows.append([label, confidence.get(label, 0)])
    rows.extend([[], ["Embedding", "Tracks with embedding"]])
    if isinstance(embeddings, dict):
        for label in SUPPORTED_EMBEDDINGS:
            rows.append([label, embeddings.get(label, 0)])
    return rows


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
            "why_keep",
            "blocked_reasons",
        ]
    ]
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
                "; ".join(str(item) for item in keeper.get("why_keep", [])),
                "; ".join(str(item) for item in group.get("blocked_reasons", [])),
            ]
        )
    return rows


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
            "safe_to_delete",
            "mert_similarity",
            "maest_similarity",
            "sonara_similarity",
            "clap_similarity",
            "duration_diff_seconds",
            "duration_diff_ratio",
            "blocked_reasons",
            "why_delete_or_review",
        ]
    ]
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
                    candidate["safe_to_delete"],
                    evidence.get("mert_similarity"),
                    evidence.get("maest_similarity"),
                    evidence.get("sonara_similarity"),
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
            "mert_similarity",
            "maest_similarity",
            "sonara_similarity",
            "clap_similarity",
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
                    evidence["mert_similarity"],
                    evidence["maest_similarity"],
                    evidence["sonara_similarity"],
                    evidence["clap_similarity"],
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
            "source_track_id",
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
                row.get("source_track_id", ""),
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
<fonts count="5">
<font><sz val="11"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="16"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF1B5E20"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFB71C1C"/><name val="Calibri"/></font>
</fonts>
<fills count="6">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF263238"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE8F5E9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFEBEE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE3F2FD"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD1D5DB"/></left><right style="thin"><color rgb="FFD1D5DB"/></right><top style="thin"><color rgb="FFD1D5DB"/></top><bottom style="thin"><color rgb="FFD1D5DB"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="4" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _xlsx_sheet_xml(name: str, rows: list[list[object]]) -> str:
    max_cols = max((len(row) for row in rows), default=1)
    col_widths = _xlsx_column_widths(rows, max_cols)
    cols_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(col_widths, start=1)
    )
    sheet_views = ""
    if len(rows) > 1:
        sheet_views = '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    rows_xml = "\n".join(_xlsx_row_xml(row, row_index, name) for row_index, row in enumerate(rows, start=1))
    dimension = f"A1:{_xlsx_col_name(max_cols)}{max(1, len(rows))}"
    auto_filter = f'<autoFilter ref="A1:{_xlsx_col_name(max_cols)}1"/>' if len(rows) > 1 else ""
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="{dimension}"/>
{sheet_views}
<cols>{cols_xml}</cols>
<sheetData>
{rows_xml}
</sheetData>
{auto_filter}
</worksheet>'''


def _xlsx_row_xml(row: list[object], row_index: int, sheet_name: str) -> str:
    height = ' ht="26" customHeight="1"' if row_index == 1 else ""
    cells = "".join(_xlsx_cell_xml(value, row_index, col_index, _xlsx_style_id(value, row_index, sheet_name)) for col_index, value in enumerate(row, start=1))
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


def _xlsx_style_id(value: object, row_index: int, sheet_name: str) -> int:
    if row_index == 1 and sheet_name == "Summary":
        return 2
    if row_index == 1:
        return 1
    if value == "DELETE CANDIDATE":
        return 3
    if value == "REVIEW MANUALLY":
        return 4
    return 5


def _xlsx_column_widths(rows: list[list[object]], max_cols: int) -> list[int]:
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
        f"preset={payload['preset']}",
        f"min_score={payload['min_score']}",
        f"database_track_count={payload.get('database_track_count', payload['track_count'])}",
        f"scoped_track_count={payload.get('scoped_track_count', payload['track_count'])}",
        f"group_count={payload['group_count']}",
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


def rhythm_lab_impact_payload(rhythm_lab_db: Path | None, track_ids: Iterable[int]) -> dict[str, object]:
    ids = tuple(sorted({int(track_id) for track_id in track_ids}))
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
            "source_track_id",
            "classifier_key",
            "label",
            "path",
            "feature_set",
            "model_artifact",
            "confidence",
        )
        for table_name in table_names:
            quoted_table = _quote_sqlite_identifier(table_name)
            table_columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()]
            if "source_track_id" not in table_columns:
                continue
            selected_columns = [column for column in wanted_columns if column in table_columns]
            select_sql = ", ".join(_quote_sqlite_identifier(column) for column in selected_columns)
            for chunk in _chunks(list(ids), 800):
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT {select_sql}
                    FROM {quoted_table}
                    WHERE source_track_id IN ({placeholders})
                    ORDER BY source_track_id
                    """,
                    tuple(chunk),
                ).fetchall()
                for row in rows:
                    affected_rows.append(
                        {
                            "action": "DELETE ON APPLY",
                            "table_name": table_name,
                            "source_track_id": int(row["source_track_id"]),
                            "classifier_key": row["classifier_key"] if "classifier_key" in row.keys() else None,
                            "label": row["label"] if "label" in row.keys() else None,
                            "path": row["path"] if "path" in row.keys() else None,
                            "feature_set": row["feature_set"] if "feature_set" in row.keys() else None,
                            "model_artifact": row["model_artifact"] if "model_artifact" in row.keys() else None,
                            "confidence": _round_float(row["confidence"]) if "confidence" in row.keys() else None,
                        }
                    )
    finally:
        connection.close()

    affected_rows.sort(
        key=lambda row: (
            int(row["source_track_id"]),
            str(row["table_name"]),
            str(row.get("classifier_key") or ""),
            str(row.get("feature_set") or ""),
            str(row.get("model_artifact") or ""),
        )
    )
    payload["affected_rows"] = affected_rows
    payload["affected_track_count"] = len({int(row["source_track_id"]) for row in affected_rows})
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
    return response.strip() == "APPLY DELETE"


def apply_duplicate_deletions(
    *,
    db_path: Path,
    root: Path,
    payload: dict[str, object],
    rhythm_lab_db: Path | None = None,
) -> ApplyResult:
    selected_db = Path(db_path).expanduser().resolve(strict=False)
    if not selected_db.exists():
        raise FileNotFoundError(f"Database does not exist: {selected_db}")
    root_text = normalize_path_text(root)
    deleted_ids: list[int] = []
    deleted_paths: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    candidates = safe_delete_candidates(payload)
    connection = sqlite3.connect(selected_db)
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        for candidate in candidates:
            track_id = int(candidate["track_id"])
            path_text = str(candidate["path"])
            if not _path_matches(path_text, root_text, []):
                skipped.append(f"track_id={track_id}: path outside root")
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
                _delete_track_from_database(connection, track_id)
                connection.commit()
            except OSError as error:
                connection.rollback()
                failed.append(f"track_id={track_id}: {error}")
                continue
            except sqlite3.Error:
                connection.rollback()
                raise
            deleted_ids.append(track_id)
            deleted_paths.append(path_text)
    finally:
        connection.close()
    selected_rhythm_lab_db = DEFAULT_RHYTHM_LAB_DB if rhythm_lab_db is None else rhythm_lab_db
    rhythm_lab_deleted_rows = cleanup_rhythm_lab_database(selected_rhythm_lab_db, deleted_ids)
    return ApplyResult(
        deleted_track_ids=tuple(deleted_ids),
        deleted_paths=tuple(deleted_paths),
        skipped=tuple(skipped),
        failed=tuple(failed),
        rhythm_lab_deleted_rows=rhythm_lab_deleted_rows,
    )


def _delete_track_from_database(connection: sqlite3.Connection, track_id: int) -> None:
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
        if table_name != "tracks" and "track_id" in columns:
            connection.execute(f"DELETE FROM {quoted_table} WHERE track_id = ?", (track_id,))
    connection.execute("DELETE FROM tracks WHERE id = ?", (track_id,))


def cleanup_rhythm_lab_database(rhythm_lab_db: Path | None, track_ids: Iterable[int]) -> int:
    ids = tuple(sorted({int(track_id) for track_id in track_ids}))
    if not ids or rhythm_lab_db is None:
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
            if "source_track_id" not in columns:
                continue
            for chunk in _chunks(list(ids), 800):
                placeholders = ",".join("?" for _ in chunk)
                cursor = connection.execute(
                    f"DELETE FROM {quoted_table} WHERE source_track_id IN ({placeholders})",
                    tuple(chunk),
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
) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": role,
        "decision": decision,
        "track_id": track.track_id,
        "path": track.path,
        "artist": track.artist,
        "title": track.title,
        "album": track.album,
        "duration": _round_float(track.duration),
        "bpm": _round_float(track.bpm),
        "musical_key": track.musical_key,
        "size": track.size,
        "mtime": track.mtime,
        "format_rank": format_rank(track.path),
        "size_per_second": _round_float(size_per_second(track)),
        "metadata_completeness": metadata_completeness(track),
        "embeddings": sorted(track.embeddings),
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
        "mert_similarity": _round_float(pair.mert_similarity),
        "maest_similarity": _round_float(pair.maest_similarity),
        "clap_similarity": _round_float(pair.clap_similarity),
        "sonara_similarity": _round_float(pair.sonara_similarity),
        "duration_diff_seconds": _round_float(pair.duration_diff_seconds),
        "duration_diff_ratio": _round_float(pair.duration_diff_ratio),
        "blocked_reasons": list(pair.blocked_reasons),
    }


def report_statistics(report_groups: list[dict[str, object]], tracks: list[TrackRecord]) -> dict[str, object]:
    confidence_counts = {"high": 0, "medium": 0, "review": 0}
    safe_candidates = 0
    review_candidates = 0
    candidate_count = 0
    duplicate_track_ids: set[int] = set()
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
    embedding_coverage = {
        key: sum(1 for track in tracks if key in track.embeddings)
        for key in SUPPORTED_EMBEDDINGS
    }
    return {
        "candidate_count": candidate_count,
        "duplicate_track_count": len(duplicate_track_ids),
        "safe_candidate_count": safe_candidates,
        "review_candidate_count": review_candidates,
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


def _track_from_row(row: sqlite3.Row) -> TrackRecord:
    metadata = _metadata_from_json(row["metadata_json"])
    return TrackRecord(
        track_id=int(row["id"]),
        path=str(row["path"]),
        size=int(row["size"]),
        mtime=float(row["mtime"]),
        artist=_string_or_none(row["artist"]),
        title=_string_or_none(row["title"]),
        album=_string_or_none(row["album"]),
        bpm=_float_or_none(row["bpm"]),
        musical_key=_string_or_none(row["musical_key"]),
        duration=_float_or_none(row["duration"]),
        metadata=metadata,
        embeddings={},
    )


def _attach_embeddings(connection: sqlite3.Connection, tracks: list[TrackRecord]) -> None:
    if not tracks:
        return
    embeddings_by_track = {track.track_id: {} for track in tracks}
    track_ids = [track.track_id for track in tracks]
    for chunk in _chunks(track_ids, 800):
        placeholders = ",".join("?" for _ in chunk)
        key_placeholders = ",".join("?" for _ in SUPPORTED_EMBEDDINGS)
        rows = connection.execute(
            f"""
            SELECT track_id, embedding_key, vector
            FROM embeddings
            WHERE track_id IN ({placeholders})
              AND embedding_key IN ({key_placeholders})
            """,
            (*chunk, *SUPPORTED_EMBEDDINGS),
        ).fetchall()
        for row in rows:
            vector = np.frombuffer(row["vector"], dtype=np.float32).copy()
            if vector.size == 0:
                continue
            norm = float(np.linalg.norm(vector))
            if norm == 0:
                continue
            embeddings_by_track[int(row["track_id"])][str(row["embedding_key"])] = (vector / norm).astype(np.float32)
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
        )


def _path_matches(path: str, root: str, contains: list[str]) -> bool:
    normalized = normalize_path_text(path)
    key = normalized.casefold()
    root_key = root.casefold()
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
        if pair.score < config.direct_keeper_score:
            reasons.append("weak direct keeper match")
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


def _metadata_from_json(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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


def _chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


if __name__ == "__main__":
    raise SystemExit(main())
