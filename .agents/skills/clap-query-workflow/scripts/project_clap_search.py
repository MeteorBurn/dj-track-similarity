#!/usr/bin/env python3
"""Run CLAP searches for the local dj-track-similarity project.

Text prompt mode posts optimized prompt banks to the running local API.
Source-file DB mode searches directly from stored SQLite CLAP embeddings.
Source-file analyze mode computes temporary CLAP embeddings for input files,
compares them to stored SQLite CLAP embeddings, and never saves them.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def read_lines(path: Path | None) -> list[str]:
    if path is None:
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "src" / "dj_track_similarity").is_dir():
            return parent
    raise SystemExit("Could not find dj-track-similarity repo root from script path")


def add_repo_src_to_path() -> Path:
    repo_root = find_repo_root()
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return repo_root


def clean_lines(values: list[str]) -> list[str]:
    lines: list[str] = []
    for value in values:
        lines.extend(line.strip() for line in value.splitlines() if line.strip())
    return lines


def post_json(url: str, payload: dict[str, Any], timeout: float) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"Failed to connect to {url}: {error.reason}") from error
    return json.loads(text)


def get_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"Failed to connect to {url}: {error.reason}") from error
    return json.loads(text)


def normalize_path_for_db(path: str | Path) -> str:
    return Path(path).as_posix()


def track_label(track: dict[str, Any]) -> str:
    artist = track.get("artist") or ""
    title = track.get("title") or ""
    if artist and title:
        return f"{artist} - {title}"
    return title or artist or "(untitled)"


def print_results(results: list[dict[str, Any]]) -> None:
    for index, item in enumerate(results, start=1):
        track = item.get("track") or {}
        breakdown = item.get("score_breakdown") or {}
        score = float(item.get("score") or 0.0)
        track_id = track.get("id", "?")
        path = track.get("path", "")
        details = ""
        if breakdown:
            positive = breakdown.get("positive")
            negative = breakdown.get("negative")
            if isinstance(positive, (int, float)) and isinstance(negative, (int, float)):
                details = f" positive={positive:.3f} negative={negative:.3f}"
        print(f"{index:02d}. score={score:.3f}{details} id={track_id} {track_label(track)}")
        print(f"    {path}")


def print_source_results(results: list[Any]) -> None:
    for index, item in enumerate(results, start=1):
        track = item.track
        label = track_label(
            {
                "artist": track.artist,
                "title": track.title,
            }
        )
        print(f"{index:02d}. score={item.score:.3f} id={track.id} {label}")
        print(f"    {track.path}")


def normalize_vector(vector: Any) -> Any:
    import numpy as np

    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise ValueError("Cannot normalize zero vector")
    return (vector / norm).astype(np.float32)


def source_files_from_args(values: list[str], list_path: Path | None) -> list[str]:
    files = clean_lines(values)
    files.extend(read_lines(list_path))
    return list(dict.fromkeys(files))


def resolve_source_track_ids(db: Any, source_files: list[str], embedding_key: str) -> list[int]:
    tracks, _matrix = db.load_embedding_matrix(embedding_key)
    by_path = {track.path.casefold(): track for track in tracks}
    source_ids: list[int] = []
    missing: list[str] = []
    for source in source_files:
        normalized = normalize_path_for_db(source)
        track = by_path.get(normalized.casefold())
        if track is None:
            missing.append(normalized)
            continue
        source_ids.append(int(track.id))
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise SystemExit(
            f"Source file(s) were not found with stored {embedding_key} embeddings in the selected DB:\n{formatted}"
        )
    return list(dict.fromkeys(source_ids))


def matching_source_track_ids(db: Any, source_files: list[str], embedding_key: str) -> set[int]:
    tracks, _matrix = db.load_embedding_matrix(embedding_key)
    by_path = {track.path.casefold(): track for track in tracks}
    ids: set[int] = set()
    for source in source_files:
        track = by_path.get(normalize_path_for_db(source).casefold())
        if track is not None:
            ids.add(int(track.id))
    return ids


def resolved_existing_audio_files(source_files: list[str]) -> list[Path]:
    existing: list[Path] = []
    missing: list[str] = []
    for source in source_files:
        path = Path(source).expanduser().resolve(strict=False)
        if not path.is_file():
            missing.append(str(path))
            continue
        existing.append(path)
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise SystemExit(f"Source audio file(s) do not exist for analyze mode:\n{formatted}")
    return existing


def run_source_file_db_search(args: argparse.Namespace, source_files: list[str], db: Any) -> int:
    from dj_track_similarity.search import SearchFilters, SimilaritySearch

    source_track_ids = resolve_source_track_ids(db, source_files, args.embedding_key)
    results = SimilaritySearch(db, embedding_key=args.embedding_key).search(
        source_track_ids,
        filters=SearchFilters(min_similarity=args.min_similarity),
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(source_results_payload(results), ensure_ascii=False, indent=2))
        return 0
    print(f"source_mode=db source_track_ids={','.join(str(track_id) for track_id in source_track_ids)} db={db.path}")
    print_source_results(results)
    return 0


def run_source_file_analyze_search(args: argparse.Namespace, source_files: list[str], db: Any) -> int:
    if args.embedding_key != "clap":
        raise SystemExit("--source-mode analyze computes CLAP embeddings, so --embedding-key must be clap")

    import numpy as np

    from dj_track_similarity.embedding import ClapEmbeddingAdapter
    from dj_track_similarity.search import SearchFilters, SimilaritySearch

    audio_files = resolved_existing_audio_files(source_files)
    adapter = ClapEmbeddingAdapter(device=args.device)
    source_vectors = adapter.embed_batch(audio_files)
    query_vector = normalize_vector(np.mean(np.vstack(source_vectors), axis=0))
    excluded_track_ids = matching_source_track_ids(
        db,
        source_files + [str(path) for path in audio_files],
        args.embedding_key,
    )
    results = SimilaritySearch(db, embedding_key=args.embedding_key).search_vector(
        query_vector,
        filters=SearchFilters(min_similarity=args.min_similarity),
        limit=args.limit + len(excluded_track_ids),
    )
    results = [result for result in results if result.track.id not in excluded_track_ids][: args.limit]
    if args.json:
        payload = source_results_payload(results)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"source_mode=analyze analyzed_files={len(audio_files)} excluded_track_ids={','.join(str(track_id) for track_id in sorted(excluded_track_ids)) or '-'} db={db.path}")
    print_source_results(results)
    return 0


def source_results_payload(results: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "score": result.score,
            "track": {
                "id": result.track.id,
                "path": result.track.path,
                "artist": result.track.artist,
                "title": result.track.title,
                "album": result.track.album,
                "bpm": result.track.bpm,
                "musical_key": result.track.musical_key,
            },
        }
        for result in results
    ]


def run_source_file_search(args: argparse.Namespace) -> int:
    add_repo_src_to_path()
    from dj_track_similarity.database import LibraryDatabase

    source_files = source_files_from_args(args.source_file, args.source_file_list)
    if not source_files:
        raise SystemExit("At least one --source-file or --source-file-list entry is required for source-file search")

    db_path = Path(args.db).expanduser().resolve(strict=False)
    if not db_path.is_file():
        raise SystemExit(f"SQLite DB does not exist: {db_path}")

    db = LibraryDatabase(db_path)
    if args.source_mode == "db":
        return run_source_file_db_search(args, source_files, db)
    return run_source_file_analyze_search(args, source_files, db)


def run_text_search(args: argparse.Namespace) -> int:
    if not args.query or not args.query.strip():
        raise SystemExit("--query is required for text prompt search")

    base_url = args.base_url.rstrip("/")
    if not args.no_db_check:
        expected_db = args.expected_db or Path("C:/db/abstracted.sqlite")
        current = get_json(base_url + "/api/database/current", timeout=args.timeout)
        actual = current.get("path") if isinstance(current, dict) else None
        expected = str(Path(expected_db).expanduser().resolve(strict=False))
        if str(actual or "").casefold() != expected.casefold():
            raise SystemExit(f"API is using a different database: actual={actual!r} expected={expected!r}")

    positives = clean_lines(args.positive) + read_lines(args.positive_file)
    negatives = clean_lines(args.negative) + read_lines(args.negative_file)

    payload: dict[str, Any] = {
        "query": args.query.strip(),
        "positive_queries": positives,
        "negative_queries": negatives,
        "adaptive_contrast": not args.no_adaptive_contrast,
        "preset": args.preset,
        "limit": args.limit,
        "min_similarity": args.min_similarity,
        "device": args.device,
    }
    results = post_json(base_url + "/api/search/text", payload, timeout=args.timeout)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    if not isinstance(results, list):
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    print_results(results)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CLAP search through dj-track-similarity project data.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--query", default=None, help="Human-readable query label. Used as fallback positive query.")
    parser.add_argument("--positive", action="append", default=[], help="Positive prompt line. Repeat or pass multiline text.")
    parser.add_argument("--positive-file", type=Path, default=None, help="UTF-8 file with one positive prompt per line.")
    parser.add_argument("--negative", action="append", default=[], help="Hard-negative prompt line. Repeat or pass multiline text.")
    parser.add_argument("--negative-file", type=Path, default=None, help="UTF-8 file with one hard-negative prompt per line.")
    parser.add_argument("--source-file", action="append", default=[], help="Audio source file path. Repeat for multiple source files.")
    parser.add_argument("--source-file-list", type=Path, default=None, help="UTF-8 file with one source audio path per line.")
    parser.add_argument("--source-mode", choices=("db", "analyze"), default="db", help="db: use stored source CLAP embeddings from SQLite. analyze: compute temporary source CLAP embeddings from files and search stored DB embeddings without saving.")
    parser.add_argument("--db", type=Path, default=Path("C:/db/abstracted.sqlite"), help="SQLite DB for source-file search.")
    parser.add_argument("--embedding-key", default="clap", help="Stored embedding key for source-file search. Defaults to clap.")
    parser.add_argument("--expected-db", type=Path, default=None, help="For API text mode, require /api/database/current to match this DB path. Defaults to C:/db/abstracted.sqlite.")
    parser.add_argument("--no-db-check", action="store_true", help="Skip /api/database/current check for API text mode.")
    parser.add_argument("--preset", default=None)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--min-similarity", type=float, default=None)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--no-adaptive-contrast", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON instead of a compact table.")
    args = parser.parse_args()

    if args.source_file or args.source_file_list:
        return run_source_file_search(args)
    return run_text_search(args)


if __name__ == "__main__":
    sys.exit(main())
