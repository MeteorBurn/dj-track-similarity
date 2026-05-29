from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import math
from pathlib import Path
import random
import sqlite3
import statistics
import sys
from typing import Any, Iterable

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DB = Path(r"C:\db\abstracted.sqlite")
DEFAULT_REPORTS_DIR = SCRIPT_DIR / "sonara_bpm_calibration" / "reports"
TARGET_SAMPLE_RATE = 22_050
TARGET_SAMPLE_RATE_POLICY = "nearest_standard_half_sample_rate"
DJ_MIN_BPM = 60.0
DJ_MAX_BPM = 190.0
HARMONIC_FACTORS = (0.25, 1.0 / 3.0, 0.5, 2.0 / 3.0, 0.75, 1.0, 4.0 / 3.0, 1.5, 2.0, 3.0, 4.0)
STANDARD_SAMPLE_RATES = {8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000, 176400, 192000}
LOGGER = logging.getLogger("sonara_bpm_calibration")


@dataclass(frozen=True)
class TrackInput:
    track_id: int
    path: str
    artist: str
    title: str
    tag_bpm: float
    stored_sonara_bpm: float | None
    stored_error: float | None


@dataclass(frozen=True)
class Candidate:
    value: float
    factor: float


@dataclass(frozen=True)
class ReportResult:
    json_path: Path
    csv_path: Path
    md_path: Path
    log_path: Path
    summary: dict[str, object]
    tracks: list[dict[str, object]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Sonara BPM calibration experiment against BPM tags. "
            "Writes JSON, CSV, Markdown, and log reports; never modifies the SQLite database or audio files."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=r"Project SQLite database. Default: C:\db\abstracted.sqlite.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of existing audio tracks to analyze.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many selected tracks before applying --limit.")
    parser.add_argument(
        "--sample",
        choices=("largest-error", "random", "bpm-buckets", "all"),
        default="largest-error",
        help="Track selection strategy.",
    )
    parser.add_argument("--seed", type=int, default=13, help="Random seed for --sample random.")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR, help="Directory for generated reports.")
    parser.add_argument("--min-bpm", type=float, default=DJ_MIN_BPM, help="Minimum BPM for calibrated candidates.")
    parser.add_argument("--max-bpm", type=float, default=DJ_MAX_BPM, help="Maximum BPM for calibrated candidates.")
    parser.add_argument("--max-duration-sec", type=float, help="Skip tracks longer than this stored metadata duration.")
    parser.add_argument("--no-beat-track", action="store_true", help="Skip extra sonara.beat_track start-BPM experiments.")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"), help="CLI logging level.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_calibration(
            db_path=args.db,
            reports_dir=args.reports_dir,
            limit=args.limit,
            offset=args.offset,
            sample_mode=args.sample,
            seed=args.seed,
            min_bpm=args.min_bpm,
            max_bpm=args.max_bpm,
            max_duration_sec=args.max_duration_sec,
            run_beat_track=not args.no_beat_track,
            log_level=args.log_level,
        )
    except (FileNotFoundError, OSError, RuntimeError, sqlite3.Error, ValueError) as error:
        print(f"sonara_bpm_calibration failed: {error}", file=sys.stderr)
        return 2
    print(f"tracks_evaluated={result.summary['tracks_evaluated']}")
    print(f"json={result.json_path}")
    print(f"csv={result.csv_path}")
    print(f"markdown={result.md_path}")
    print(f"log={result.log_path}")
    return 0


def run_calibration(
    *,
    db_path: Path,
    reports_dir: Path,
    limit: int,
    offset: int = 0,
    sample_mode: str = "largest-error",
    seed: int = 13,
    min_bpm: float = DJ_MIN_BPM,
    max_bpm: float = DJ_MAX_BPM,
    max_duration_sec: float | None = None,
    run_beat_track: bool = True,
    log_level: str | int = "INFO",
    sonara_module: Any | None = None,
) -> ReportResult:
    if limit <= 0:
        raise ValueError("--limit must be greater than zero")
    if offset < 0:
        raise ValueError("--offset must be zero or greater")
    selected_db = Path(db_path).expanduser().resolve(strict=False)
    if not selected_db.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {selected_db}")

    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = reports_dir / f"sonara_bpm_calibration_{timestamp}"
    log_path = base.with_suffix(".log")
    _configure_logging(log_path, log_level)
    LOGGER.info("starting calibration db=%s limit=%s sample=%s", selected_db, limit, sample_mode)

    sonara = sonara_module or _import_sonara()
    tracks = load_track_inputs(selected_db, max_duration_sec=max_duration_sec)
    library_median = _median([track.tag_bpm for track in tracks])
    selected = select_tracks(tracks, sample_mode=sample_mode, seed=seed, offset=offset, limit=limit)
    rows: list[dict[str, object]] = []
    failures = 0
    for index, track in enumerate(selected, start=1):
        try:
            row = analyze_track(
                track,
                sonara_module=sonara,
                library_median_bpm=library_median,
                min_bpm=min_bpm,
                max_bpm=max_bpm,
                run_beat_track=run_beat_track,
            )
            rows.append(row)
            LOGGER.info("track %s/%s id=%s tag=%.3f raw=%.3f", index, len(selected), track.track_id, track.tag_bpm, row["raw_sonara_bpm"])
        except Exception as error:  # noqa: BLE001 - research script should keep processing.
            failures += 1
            LOGGER.exception("failed track id=%s path=%s error=%s", track.track_id, track.path, error)
    summary = build_summary(
        rows,
        selected_count=len(selected),
        failure_count=failures,
        target_sample_rate_policy=TARGET_SAMPLE_RATE_POLICY,
        sample_mode=sample_mode,
        library_median_bpm=library_median,
    )
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "database_path": str(selected_db),
        "summary": summary,
        "tracks": rows,
    }
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    write_csv(csv_path, rows)
    write_markdown(md_path, payload)
    LOGGER.info("reports written json=%s csv=%s markdown=%s log=%s", json_path, csv_path, md_path, log_path)
    return ReportResult(json_path=json_path, csv_path=csv_path, md_path=md_path, log_path=log_path, summary=summary, tracks=rows)


def load_track_inputs(db_path: Path, *, max_duration_sec: float | None = None) -> list[TrackInput]:
    uri = "file:" + db_path.as_posix() + "?mode=ro"
    tracks: list[TrackInput] = []
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute("SELECT id, path, artist, title, bpm, duration, metadata_json FROM tracks ORDER BY id"):
            metadata = _metadata_from_json(str(row["metadata_json"] or "{}"))
            tag_bpm = parse_float(metadata.get("bpm"))
            if tag_bpm is None or tag_bpm <= 0:
                continue
            duration = parse_float(row["duration"]) or parse_float(metadata.get("duration"))
            if max_duration_sec is not None and duration is not None and duration > max_duration_sec:
                continue
            path = str(row["path"])
            if not Path(path).exists():
                continue
            stored = _extract_sonara_bpm(metadata) or parse_float(row["bpm"])
            tracks.append(
                TrackInput(
                    track_id=int(row["id"]),
                    path=path,
                    artist=str(row["artist"] or metadata.get("artist") or ""),
                    title=str(row["title"] or metadata.get("title") or Path(path).stem),
                    tag_bpm=tag_bpm,
                    stored_sonara_bpm=stored,
                    stored_error=abs(tag_bpm - stored) if stored is not None else None,
                )
            )
    return tracks


def select_tracks(tracks: list[TrackInput], *, sample_mode: str, seed: int, offset: int, limit: int) -> list[TrackInput]:
    if sample_mode == "largest-error":
        selected = sorted(tracks, key=lambda track: track.stored_error if track.stored_error is not None else -1.0, reverse=True)
    elif sample_mode == "random":
        selected = list(tracks)
        random.Random(seed).shuffle(selected)
    elif sample_mode == "bpm-buckets":
        buckets: dict[int, TrackInput] = {}
        for track in tracks:
            bucket = int(round(track.tag_bpm))
            current = buckets.get(bucket)
            if current is None or (track.stored_error or -1.0) > (current.stored_error or -1.0):
                buckets[bucket] = track
        selected = [buckets[key] for key in sorted(buckets)]
    elif sample_mode == "all":
        selected = list(tracks)
    else:
        raise ValueError(f"Unsupported sample mode: {sample_mode}")
    return selected[offset : offset + limit]


def analyze_track(
    track: TrackInput,
    *,
    sonara_module: Any,
    library_median_bpm: float | None,
    min_bpm: float,
    max_bpm: float,
    run_beat_track: bool,
) -> dict[str, object]:
    native_audio, native_sr = sonara_module.load(track.path, sr=0, mono=True)
    normalized_sr = normalized_sample_rate_for_native(int(native_sr))
    target_sr = target_sample_rate_for_native(int(native_sr))
    audio = np.asarray(native_audio, dtype=np.float32)
    if int(native_sr) != target_sr:
        audio = np.asarray(sonara_module.resample(audio, orig_sr=int(native_sr), target_sr=target_sr), dtype=np.float32)
    analysis = dict(sonara_module.analyze_signal(audio, sr=target_sr, mode="compact"))
    raw_bpm = _require_float(analysis.get("bpm"), "sonara bpm")
    candidates = harmonic_candidates(raw_bpm, min_bpm=min_bpm, max_bpm=max_bpm)
    by_tag = best_candidate_by_tag(candidates, track.tag_bpm)
    folded = fold_to_range(raw_bpm, min_bpm=min_bpm, max_bpm=max_bpm)
    tagless = select_tagless_candidate(candidates, library_median_bpm=library_median_bpm)
    strategies: dict[str, dict[str, object]] = {
        "raw_sonara": _strategy_payload(raw_bpm, 1.0, track.tag_bpm),
        "dj_range_fold": _strategy_payload(folded.value, folded.factor, track.tag_bpm),
        "best_harmonic_by_tag_oracle": _strategy_payload(by_tag.value, by_tag.factor, track.tag_bpm),
        "tagless_prior": _strategy_payload(tagless.value, tagless.factor, track.tag_bpm),
    }
    if track.stored_sonara_bpm is not None:
        strategies["stored_sonara"] = _strategy_payload(track.stored_sonara_bpm, 1.0, track.tag_bpm)
    if run_beat_track and hasattr(sonara_module, "beat_track"):
        if library_median_bpm is not None:
            tempo, beats = sonara_module.beat_track(y=audio, sr=target_sr, start_bpm=float(library_median_bpm), tightness=100.0, trim=True)
            strategies["beat_start_library_median"] = _strategy_payload(_require_float(tempo, "beat tempo"), 1.0, track.tag_bpm, extra={"beats": len(beats)})
        tempo, beats = sonara_module.beat_track(y=audio, sr=target_sr, start_bpm=float(track.tag_bpm), tightness=100.0, trim=True)
        strategies["beat_start_tag_oracle"] = _strategy_payload(_require_float(tempo, "beat tempo"), 1.0, track.tag_bpm, extra={"beats": len(beats)})
    return {
        "track_id": track.track_id,
        "path": track.path,
        "artist": track.artist,
        "title": track.title,
        "tag_bpm": track.tag_bpm,
        "raw_sonara_bpm": raw_bpm,
        "stored_sonara_bpm": track.stored_sonara_bpm,
        "native_sample_rate": int(native_sr),
        "normalized_sample_rate": normalized_sr,
        "native_sample_rate_standard": int(native_sr) in STANDARD_SAMPLE_RATES,
        "target_sample_rate": target_sr,
        "n_beats": parse_float(analysis.get("n_beats")),
        "strategies": strategies,
    }


def harmonic_candidates(raw_bpm: float, *, min_bpm: float = DJ_MIN_BPM, max_bpm: float = DJ_MAX_BPM) -> list[Candidate]:
    values: dict[float, Candidate] = {}
    for factor in HARMONIC_FACTORS:
        value = raw_bpm * factor
        if min_bpm <= value <= max_bpm:
            rounded_key = round(value, 6)
            values[rounded_key] = Candidate(value=value, factor=factor)
    if not values:
        folded = fold_to_range(raw_bpm, min_bpm=min_bpm, max_bpm=max_bpm)
        values[round(folded.value, 6)] = folded
    return sorted(values.values(), key=lambda candidate: candidate.value)


def target_sample_rate_for_native(native_sample_rate: int) -> int:
    return max(1, normalized_sample_rate_for_native(native_sample_rate) // 2)


def normalized_sample_rate_for_native(native_sample_rate: int) -> int:
    if native_sample_rate <= 0:
        return TARGET_SAMPLE_RATE * 2
    return min(STANDARD_SAMPLE_RATES, key=lambda sample_rate: abs(sample_rate - native_sample_rate))


def best_candidate_by_tag(candidates: Iterable[Candidate], tag_bpm: float) -> Candidate:
    return min(candidates, key=lambda candidate: abs(candidate.value - tag_bpm))


def select_tagless_candidate(candidates: Iterable[Candidate], *, library_median_bpm: float | None) -> Candidate:
    median = library_median_bpm if library_median_bpm and math.isfinite(library_median_bpm) else 128.0

    def score(candidate: Candidate) -> float:
        value = candidate.value
        prior_distance = abs(value - median)
        range_penalty = 0.0
        if value < 80.0:
            range_penalty += (80.0 - value) * 1.5
        if value > 160.0:
            range_penalty += (value - 160.0) * 0.75
        factor_penalty = 0.5 if abs(candidate.factor - 1.0) > 1e-9 else 0.0
        return prior_distance + range_penalty + factor_penalty

    return min(candidates, key=score)


def fold_to_range(raw_bpm: float, *, min_bpm: float, max_bpm: float) -> Candidate:
    value = raw_bpm
    factor = 1.0
    while value > max_bpm:
        value /= 2.0
        factor /= 2.0
    while value < min_bpm:
        value *= 2.0
        factor *= 2.0
    return Candidate(value=value, factor=factor)


def build_summary(
    rows: list[dict[str, object]],
    *,
    selected_count: int,
    failure_count: int,
    target_sample_rate_policy: str,
    sample_mode: str,
    library_median_bpm: float | None,
) -> dict[str, object]:
    strategy_names = sorted({name for row in rows for name in dict(row["strategies"]).keys()})
    return {
        "sample_mode": sample_mode,
        "tracks_selected": selected_count,
        "tracks_evaluated": len(rows),
        "tracks_failed": failure_count,
        "target_sample_rate_policy": target_sample_rate_policy,
        "library_median_bpm": library_median_bpm,
        "native_sample_rates": _sample_rate_counts(rows),
        "metrics": {name: _strategy_metrics(rows, name) for name in strategy_names},
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    strategy_names = sorted({name for row in rows for name in dict(row["strategies"]).keys()})
    fields = ["track_id", "tag_bpm", "native_sample_rate", "raw_sonara_bpm", "stored_sonara_bpm", "artist", "title", "path"]
    for name in strategy_names:
        fields.extend([f"{name}_bpm", f"{name}_abs_error", f"{name}_factor"])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            output = {key: row.get(key) for key in fields}
            strategies = dict(row["strategies"])
            for name in strategy_names:
                payload = strategies.get(name, {})
                output[f"{name}_bpm"] = payload.get("bpm")
                output[f"{name}_abs_error"] = payload.get("abs_error")
                output[f"{name}_factor"] = payload.get("factor")
            writer.writerow(output)


def write_markdown(path: Path, payload: dict[str, object]) -> None:
    summary = dict(payload["summary"])
    lines = [
        "# Sonara BPM Calibration Report",
        "",
        f"- Database: `{payload['database_path']}`",
        f"- Tracks evaluated: `{summary['tracks_evaluated']}`",
        f"- Target sample rate policy: `{summary['target_sample_rate_policy']}`",
        f"- Library median BPM tag: `{_fmt(summary['library_median_bpm'])}`",
        f"- Native sample rates: `{summary['native_sample_rates']}`",
        "",
        "| Strategy | Count | mean_abs_error | median_abs_error | p90_abs_error | within_3 | within_5 | gt20 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in dict(summary["metrics"]).items():
        metric = dict(metrics)
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    str(metric["count"]),
                    _fmt(metric["mean_abs_error"]),
                    _fmt(metric["median_abs_error"]),
                    _fmt(metric["p90_abs_error"]),
                    str(metric["within_3_bpm"]),
                    str(metric["within_5_bpm"]),
                    str(metric["outliers_gt_20_bpm"]),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict) and "value" in value:
        return parse_float(value["value"])
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    text = str(value).strip().replace(",", ".")
    number = ""
    for char in text:
        if char.isdigit() or char in ".+-":
            number += char
        elif number:
            break
    try:
        result = float(number)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _metadata_from_json(value: str) -> dict[str, object]:
    try:
        metadata = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _extract_sonara_bpm(metadata: dict[str, object]) -> float | None:
    features = metadata.get("sonara_features")
    if not isinstance(features, dict):
        return None
    return parse_float(features.get("bpm"))


def _strategy_payload(bpm: float, factor: float, tag_bpm: float, *, extra: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "bpm": bpm,
        "factor": factor,
        "abs_error": abs(tag_bpm - bpm),
    }
    if extra:
        payload.update(extra)
    return payload


def _strategy_metrics(rows: list[dict[str, object]], strategy: str) -> dict[str, object]:
    errors = [
        float(dict(dict(row["strategies"])[strategy])["abs_error"])
        for row in rows
        if strategy in dict(row["strategies"])
    ]
    if not errors:
        return {
            "count": 0,
            "mean_abs_error": None,
            "median_abs_error": None,
            "p90_abs_error": None,
            "within_1_bpm": 0,
            "within_3_bpm": 0,
            "within_5_bpm": 0,
            "outliers_gt_10_bpm": 0,
            "outliers_gt_20_bpm": 0,
            "outliers_gt_40_bpm": 0,
        }
    return {
        "count": len(errors),
        "mean_abs_error": statistics.mean(errors),
        "median_abs_error": statistics.median(errors),
        "p90_abs_error": _percentile(errors, 0.9),
        "within_1_bpm": sum(error <= 1.0 for error in errors),
        "within_3_bpm": sum(error <= 3.0 for error in errors),
        "within_5_bpm": sum(error <= 5.0 for error in errors),
        "outliers_gt_10_bpm": sum(error > 10.0 for error in errors),
        "outliers_gt_20_bpm": sum(error > 20.0 for error in errors),
        "outliers_gt_40_bpm": sum(error > 40.0 for error in errors),
    }


def _sample_rate_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["native_sample_rate"])
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _percentile(values: list[float], quantile: float) -> float:
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * quantile)))
    return sorted_values[index]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _fmt(value: object) -> str:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return f"{float(value):.3f}"
    return "n/a"


def _require_float(value: object, name: str) -> float:
    parsed = parse_float(value)
    if parsed is None:
        raise RuntimeError(f"Missing numeric {name}")
    return parsed


def _import_sonara() -> Any:
    try:
        import sonara
    except ImportError as error:
        raise RuntimeError('sonara is not installed. Install the project with: python -m pip install -e ".[sonara,dev]"') from error
    return sonara


def _configure_logging(log_path: Path, level: str | int) -> None:
    numeric_level = getattr(logging, str(level).upper(), level)
    root = LOGGER
    root.handlers.clear()
    root.setLevel(numeric_level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    console_handler.setLevel(numeric_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


if __name__ == "__main__":
    raise SystemExit(main())
