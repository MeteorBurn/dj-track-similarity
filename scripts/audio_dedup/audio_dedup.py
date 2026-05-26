from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from typing import Iterable

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DB = Path(r"C:\db\abstracted.sqlite")
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
    bpm_diff: float | None
    key_match: bool | None
    blocked_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateGroup:
    group_id: int
    track_ids: tuple[int, ...]
    pair_evidence: tuple[PairEvidence, ...]


@dataclass(frozen=True)
class ReportResult:
    json_path: Path
    csv_path: Path
    log_path: Path
    groups: int


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
    except (FileNotFoundError, ValueError, sqlite3.Error) as error:
        print(f"audio_dedup failed: {error}", file=sys.stderr)
        return 2
    print(f"Report-only run complete. groups={result.groups}")
    print(f"json={result.json_path}")
    print(f"csv={result.csv_path}")
    print(f"log={result.log_path}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find likely duplicate audio tracks from an existing dj-track-similarity SQLite database. "
            "This v1 is report-only: it never deletes files and never mutates databases."
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
    tracks = load_tracks(db_path, root=root, path_contains=path_contains)
    groups = find_duplicate_groups(tracks, config, limit_groups=limit_groups)
    payload = build_report(groups, tracks, config, root=root, path_contains=path_contains)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = _unique_report_path(out_dir / f"audio_dedup_report_{stamp}.json")
    csv_path = json_path.with_suffix(".csv")
    log_path = json_path.with_suffix(".log")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv_report(csv_path, payload)
    write_text_log(log_path, payload)
    return ReportResult(json_path=json_path, csv_path=csv_path, log_path=log_path, groups=len(groups))


def resolve_preset(name: str, *, min_score: float | None) -> PresetConfig:
    presets = {
        "safe": PresetConfig(
            name="safe",
            min_score=0.965,
            duration_seconds=2.0,
            duration_ratio=0.01,
            direct_keeper_score=0.965,
            strict_duration_ratio=0.01,
        ),
        "balanced": PresetConfig(
            name="balanced",
            min_score=0.925,
            duration_seconds=5.0,
            duration_ratio=0.025,
            direct_keeper_score=0.935,
            strict_duration_ratio=0.025,
        ),
        "aggressive": PresetConfig(
            name="aggressive",
            min_score=0.875,
            duration_seconds=15.0,
            duration_ratio=0.08,
            direct_keeper_score=0.9,
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
    with _connect_readonly(selected) as connection:
        rows = connection.execute(
            """
            SELECT id, path, size, mtime, artist, title, album, bpm, musical_key, duration, metadata_json
            FROM tracks
            ORDER BY id
            """
        ).fetchall()
        tracks = [_track_from_row(row) for row in rows if _path_matches(row["path"], root_text, contains)]
        _attach_embeddings(connection, tracks)
    return tracks


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
    bpm_diff = _bpm_distance(left.bpm, right.bpm)
    key_match = _key_match(left.musical_key, right.musical_key)
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
    if bpm_diff is not None:
        weighted += max(0.0, 1.0 - min(bpm_diff / 3.0, 1.0)) * 0.015
        total += 0.015
    if key_match is not None:
        weighted += (1.0 if key_match else 0.0) * 0.015
        total += 0.015
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
        bpm_diff=bpm_diff,
        key_match=key_match,
        blocked_reasons=tuple(blocked),
    )


def build_report(
    groups: list[DuplicateGroup],
    tracks: list[TrackRecord],
    config: PresetConfig,
    *,
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
            candidates.append(
                {
                    "track_id": track.track_id,
                    "path": track.path,
                    "score_vs_keeper": _round_float(direct.score if direct else None),
                    "safe_to_delete": "true_candidate" if safe else "false",
                    "blocked_reasons": reasons,
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
                "suggested_keeper": track_payload(keeper, include_keeper_reasons=True),
                "candidate_deletes": sorted(candidates, key=lambda item: int(item["track_id"])),
                "tracks": [track_payload(track, include_keeper_reasons=False) for track in group_tracks],
                "pairwise_evidence": [pair_payload(pair) for pair in group.pair_evidence],
            }
        )
    return {
        "mode": "report-only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": normalize_path_text(root),
        "path_contains": path_contains,
        "preset": config.name,
        "min_score": config.min_score,
        "track_count": len(tracks),
        "group_count": len(report_groups),
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


def write_csv_report(path: Path, payload: dict[str, object]) -> None:
    fields = [
        "group_id",
        "confidence",
        "group_score",
        "keeper_track_id",
        "keeper_path",
        "delete_track_id",
        "delete_path",
        "safe_to_delete",
        "score_vs_keeper",
        "mert_similarity",
        "maest_similarity",
        "sonara_similarity",
        "clap_similarity",
        "duration_diff_seconds",
        "duration_diff_ratio",
        "bpm_diff",
        "key_match",
        "blocked_reasons",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for group in payload["groups"]:  # type: ignore[index]
            assert isinstance(group, dict)
            keeper = group["suggested_keeper"]
            assert isinstance(keeper, dict)
            evidence_by_candidate = _evidence_by_candidate(group, int(keeper["track_id"]))
            for candidate in group["candidate_deletes"]:  # type: ignore[index]
                assert isinstance(candidate, dict)
                evidence = evidence_by_candidate.get(int(candidate["track_id"]), {})
                writer.writerow(
                    {
                        "group_id": group["group_id"],
                        "confidence": group["confidence"],
                        "group_score": _format_float(group["score"]),
                        "keeper_track_id": keeper["track_id"],
                        "keeper_path": keeper["path"],
                        "delete_track_id": candidate["track_id"],
                        "delete_path": candidate["path"],
                        "safe_to_delete": candidate["safe_to_delete"],
                        "score_vs_keeper": _format_float(candidate["score_vs_keeper"]),
                        "mert_similarity": _format_float(evidence.get("mert_similarity")),
                        "maest_similarity": _format_float(evidence.get("maest_similarity")),
                        "sonara_similarity": _format_float(evidence.get("sonara_similarity")),
                        "clap_similarity": _format_float(evidence.get("clap_similarity")),
                        "duration_diff_seconds": _format_float(evidence.get("duration_diff_seconds")),
                        "duration_diff_ratio": _format_float(evidence.get("duration_diff_ratio")),
                        "bpm_diff": _format_float(evidence.get("bpm_diff")),
                        "key_match": evidence.get("key_match", ""),
                        "blocked_reasons": "; ".join(candidate.get("blocked_reasons", [])),
                    }
                )


def write_text_log(path: Path, payload: dict[str, object]) -> None:
    lines = [
        "audio_dedup report-only run",
        f"generated_at={payload['generated_at']}",
        f"root={payload['root']}",
        f"preset={payload['preset']}",
        f"min_score={payload['min_score']}",
        f"track_count={payload['track_count']}",
        f"group_count={payload['group_count']}",
        "no files deleted; no databases mutated",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    for value in (track.artist, track.title, track.album, track.bpm, track.musical_key, track.duration):
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


def track_payload(track: TrackRecord, *, include_keeper_reasons: bool) -> dict[str, object]:
    payload: dict[str, object] = {
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
        "bpm_diff": _round_float(pair.bpm_diff),
        "key_match": pair.key_match,
        "blocked_reasons": list(pair.blocked_reasons),
    }


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


def _key_match(left: str | None, right: str | None) -> bool | None:
    if not left or not right:
        return None
    return left.strip().casefold() == right.strip().casefold()


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
