#!/usr/bin/env python3
"""Post an optimized prompt bank to the running dj-track-similarity API.

This helper covers the text-to-track layer only: CLAP and MuQ-MuLan text
search through `POST /api/search/text`. Audio-to-audio seed search belongs to
the seed-search layer and is available through `POST /api/search` and the
SIMILARITY tab.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DB_ENV_VARS = ("DJ_SIM_DB", "DJ_TRACK_SIMILARITY_DB")
TEXT_MODELS = ("clap", "mulan")
MODEL_LABELS = {"clap": "CLAP", "mulan": "MuQ-MuLan"}


def db_path_from_env() -> Path | None:
    for name in DB_ENV_VARS:
        value = os.environ.get(name)
        if value and value.strip():
            return Path(value.strip())
    return None


def read_lines(path: Path | None) -> list[str]:
    if path is None:
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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


def track_label(track: dict[str, Any]) -> str:
    artist = track.get("artist") or ""
    title = track.get("title") or ""
    if artist and title:
        return f"{artist} - {title}"
    return title or artist or "(untitled)"


def print_results(results: list[dict[str, Any]]) -> None:
    """Print the API response using its current field names."""

    for index, item in enumerate(results, start=1):
        track = item.get("track") or {}
        breakdown = item.get("score_breakdown") or {}
        score = float(item.get("score") or 0.0)
        details = ""
        positive = breakdown.get("positive")
        negative = breakdown.get("negative")
        weight = breakdown.get("negative_weight")
        if isinstance(positive, (int, float)) and isinstance(negative, (int, float)):
            details = f" positive={positive:.3f} negative={negative:.3f}"
            if isinstance(weight, (int, float)):
                details += f" w={weight:.2f}"
        print(f"{index:02d}. score={score:.3f}{details} id={track.get('track_id', '?')} {track_label(track)}")
        print(f"    {track.get('file_path', '')}")


def verify_expected_database(base_url: str, expected: Path, timeout: float) -> None:
    current = get_json(base_url + "/api/database/current", timeout=timeout)
    actual = current.get("path") if isinstance(current, dict) else None
    resolved = str(expected.expanduser().resolve(strict=False))
    if str(actual or "").casefold() != resolved.casefold():
        raise SystemExit(f"API is using a different database: actual={actual!r} expected={resolved!r}")


def run_text_search(args: argparse.Namespace) -> int:
    positives = clean_lines(args.positive) + read_lines(args.positive_file)
    negatives = clean_lines(args.negative) + read_lines(args.negative_file)
    query = (args.query or "").strip()
    if query and query not in positives:
        positives.insert(0, query)
    if args.no_negatives:
        negatives = []
    if not positives:
        raise SystemExit("Provide --query or at least one --positive prompt")

    base_url = args.base_url.rstrip("/")
    if not args.no_db_check:
        expected_db = args.expected_db or db_path_from_env()
        if expected_db is not None:
            verify_expected_database(base_url, expected_db, args.timeout)

    payload: dict[str, Any] = {
        "analysis_family": args.model,
        "positive_queries": positives,
        "negative_queries": negatives,
        "limit": args.limit,
        "min_similarity": args.min_similarity,
        "device": args.device,
    }
    if args.negative_weight is not None:
        payload["negative_weight"] = args.negative_weight

    results = post_json(base_url + "/api/search/text", payload, timeout=args.timeout)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    if not isinstance(results, list):
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    print(
        f"model={MODEL_LABELS[args.model]} positives={len(positives)} "
        f"negatives={len(negatives)} results={len(results)}"
    )
    print_results(results)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run text-to-track search through the dj-track-similarity API.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--model",
        choices=TEXT_MODELS,
        default="mulan",
        help="Text embedding family. MuQ-MuLan wins on groove and style, CLAP on voice and instruments.",
    )
    parser.add_argument("--query", default=None, help="Human-readable query label. Used as the fallback positive prompt.")
    parser.add_argument("--positive", action="append", default=[], help="Positive prompt line. Repeat or pass multiline text.")
    parser.add_argument("--positive-file", type=Path, default=None, help="UTF-8 file with one positive prompt per line.")
    parser.add_argument("--negative", action="append", default=[], help="Hard-negative prompt line. Repeat or pass multiline text.")
    parser.add_argument("--negative-file", type=Path, default=None, help="UTF-8 file with one hard-negative prompt per line.")
    parser.add_argument(
        "--negative-weight",
        type=float,
        default=None,
        help="Hard-negative weight 0..2. Omit to use the server default. Raise it only when the negatives name a real competing class.",
    )
    parser.add_argument("--no-negatives", action="store_true", help="Drop the negative bank for this search.")
    parser.add_argument("--expected-db", type=Path, default=None, help="Fail unless the API serves this database.")
    parser.add_argument("--no-db-check", action="store_true", help="Skip the /api/database/current guard.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--min-similarity", type=float, default=None)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--json", action="store_true", help="Emit raw JSON instead of a compact table.")
    args = parser.parse_args()
    return run_text_search(args)


if __name__ == "__main__":
    sys.exit(main())
