#!/usr/bin/env python3
"""Post a manual prompt bank to the running dj-track-similarity API.

This helper covers the text-to-track layer only: CLAP and MuQ-MuLan text
search through `POST /api/search/text`. Audio-to-audio seed search belongs to
the seed-search layer and is available through `POST /api/search` and the
SIMILARITY tab.
"""

from __future__ import annotations

import argparse
import json
import math
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
    try:
        return clean_lines([path.read_text(encoding="utf-8")])
    except (OSError, UnicodeError) as error:
        raise SystemExit(f"Cannot read prompt file {path}: {error}") from error


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
    return decode_response(text, url)


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
    return decode_response(text, url)


def decode_response(text: str, url: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON response from {url}: {error}") from error


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


def verify_expected_database(base_url: str, expected: Path, timeout: float) -> str:
    """Check the selected path and retain its catalog identity without opening it."""

    try:
        resolved = expected.expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("expected an existing database file")
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Invalid expected database {expected}: {error}") from error

    current = get_json(base_url + "/api/database/current", timeout=timeout)
    if not isinstance(current, dict) or current.get("selected") is not True:
        raise SystemExit("API has no selected database or returned an invalid database state")
    actual = current.get("path")
    if not isinstance(actual, str) or not actual.strip():
        raise SystemExit("Invalid database state: path must be a non-empty string")
    try:
        actual_path = Path(actual).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Invalid selected database path {actual!r}: {error}") from error
    if actual_path != resolved:
        raise SystemExit(f"API is using a different database: actual={actual!r} expected={str(resolved)!r}")
    catalog_uuid = current.get("catalog_uuid")
    if not isinstance(catalog_uuid, str) or not catalog_uuid.strip():
        raise SystemExit("Invalid database state: catalog_uuid must be a non-empty string")
    return catalog_uuid


def validate_search_response(
    response: Any, *, model: str, catalog_uuid: str | None
) -> dict[str, Any]:
    """Validate the envelope fields used by this client; preserve all server metadata."""

    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        raise SystemExit("Invalid text-search response: expected results/execution envelope")
    for index, item in enumerate(response["results"], start=1):
        if not isinstance(item, dict) or not isinstance(item.get("track"), dict):
            raise SystemExit(f"Invalid text-search result #{index}: expected an object with a track")
        score = item.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise SystemExit(f"Invalid text-search result #{index}: score must be finite")
        if item.get("score_breakdown") is not None and not isinstance(item["score_breakdown"], dict):
            raise SystemExit(f"Invalid text-search result #{index}: score_breakdown must be an object")
    execution = response.get("execution")
    if not isinstance(execution, dict):
        raise SystemExit("Invalid text-search response: execution must be an object")
    for key in ("run_id", "query_key"):
        if not isinstance(execution.get(key), str) or not execution[key].strip():
            raise SystemExit(f"Invalid text-search execution: {key} must be a non-empty string")
    context = execution.get("query_context")
    if not isinstance(context, dict):
        raise SystemExit("Invalid text-search execution: query_context must be an object")
    if context.get("analysis_family") != model:
        raise SystemExit(f"Text-search response family does not match requested model {model!r}")
    returned_catalog = context.get("catalog_uuid")
    if not isinstance(returned_catalog, str) or not returned_catalog.strip():
        raise SystemExit("Invalid text-search query_context: catalog_uuid must be a non-empty string")
    if catalog_uuid is not None and returned_catalog != catalog_uuid:
        raise SystemExit(
            f"Database catalog changed during search: actual={returned_catalog!r} expected={catalog_uuid!r}"
        )
    feedback = execution.get("feedback")
    if (
        not isinstance(feedback, dict)
        or not isinstance(feedback.get("requested"), bool)
        or not isinstance(feedback.get("applied"), bool)
        or not isinstance(feedback.get("reason"), str)
        or not feedback["reason"].strip()
        or execution.get("feedback_capability") not in ("ready", "absent", "incompatible")
    ):
        raise SystemExit("Invalid text-search execution: feedback status is missing or malformed")
    return response


def run_text_search(args: argparse.Namespace) -> int:
    positives = clean_lines(args.positive) + read_lines(args.positive_file)
    negatives = clean_lines(args.negative) + read_lines(args.negative_file)
    for query in reversed(clean_lines([args.query or ""])):
        if query not in positives:
            positives.insert(0, query)
    if args.no_negatives:
        negatives = []
    if not positives:
        raise SystemExit("Provide --query or at least one --positive prompt")

    base_url = args.base_url.rstrip("/")
    catalog_uuid = None
    if not args.no_db_check:
        expected_db = args.expected_db or db_path_from_env()
        if expected_db is None:
            raise SystemExit(
                "Provide --expected-db or set DJ_SIM_DB / DJ_TRACK_SIMILARITY_DB; "
                "use --no-db-check only to explicitly bypass database verification"
            )
        catalog_uuid = verify_expected_database(base_url, expected_db, args.timeout)

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

    response = validate_search_response(
        post_json(base_url + "/api/search/text", payload, timeout=args.timeout),
        model=args.model,
        catalog_uuid=catalog_uuid,
    )
    results = response["results"]
    if args.json:
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0
    execution = response["execution"]
    context = execution["query_context"]
    feedback = execution["feedback"]
    print(
        f"model={MODEL_LABELS[args.model]} analysis_family={context['analysis_family']} positives={len(positives)} "
        f"negatives={len(negatives)} results={len(results)}"
    )
    print(
        f"run_id={execution['run_id']} query_key={execution['query_key']} "
        f"catalog_uuid={context['catalog_uuid']}"
    )
    print(
        f"feedback: requested={feedback['requested']} applied={feedback['applied']} "
        f"reason={feedback['reason']} capability={execution['feedback_capability']}"
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
        help="Text embedding family. Compare CLAP and MuQ-MuLan with separate model-specific banks.",
    )
    parser.add_argument("--query", default=None, help="Positive prompt text prepended to the bank; each non-empty line is embedded.")
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
    parser.add_argument("--expected-db", type=Path, default=None, help="Existing database path; defaults to DJ_SIM_DB, then DJ_TRACK_SIMILARITY_DB. Required unless --no-db-check.")
    parser.add_argument("--no-db-check", action="store_true", help="Explicitly bypass the selected-database path and catalog guard.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--min-similarity", type=float, default=None)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--json", action="store_true", help="Emit the full results/execution JSON envelope, including query context and feedback status.")
    args = parser.parse_args()
    return run_text_search(args)


if __name__ == "__main__":
    sys.exit(main())
