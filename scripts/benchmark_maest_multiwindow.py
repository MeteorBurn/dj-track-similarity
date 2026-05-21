from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from dj_track_similarity.audio_loader import load_audio_mono
from dj_track_similarity.database import SYNCOPATED_RHYTHM_GENRES
from dj_track_similarity.genres import MaestGenreAdapter, maest_input_seconds


TARGET_SAMPLE_RATE = 16000
WINDOW_COUNT = 3


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare stored single-window MAEST genres with temporary 3-window MAEST genres."
    )
    parser.add_argument("--db", required=True, help="SQLite database path.")
    parser.add_argument("--limit", type=int, default=125, help="Number of existing audio tracks to test.")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"], help="MAEST device.")
    parser.add_argument("--top-k", type=int, default=8, help="Top labels to keep per method.")
    parser.add_argument(
        "--window-batch-size",
        type=int,
        default=24,
        help="Number of 30-second windows per MAEST inference micro-batch.",
    )
    parser.add_argument("--output", required=True, help="Output JSON report path.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve(strict=False)
    output_path = Path(args.output).resolve(strict=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    selected = _select_tracks(db_path, limit=max(1, args.limit))
    started = time.perf_counter()
    report = _run_multiwindow(
        selected,
        db_path=db_path,
        device=args.device,
        top_k=max(1, args.top_k),
        window_batch_size=max(1, args.window_batch_size),
    )
    elapsed = time.perf_counter() - started

    report["elapsed_seconds"] = elapsed
    report["elapsed_human"] = _format_seconds(elapsed)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "elapsed_seconds": elapsed, "tracks": len(report["tracks"])}, ensure_ascii=False))


def _select_tracks(db_path: Path, *, limit: int) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, path, artist, title, album, duration, metadata_json
            FROM tracks
            WHERE metadata_json LIKE '%"maest_genres"%'
            ORDER BY id
            """
        ).fetchall()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        path = Path(str(row["path"]))
        if not path.exists():
            continue
        metadata = _metadata(row["metadata_json"])
        stored = _stored_genres(metadata)
        reason, priority = _selection_reason(row, metadata, stored)
        candidates.append(
            {
                "id": int(row["id"]),
                "path": str(path),
                "artist": row["artist"] or "",
                "title": row["title"] or path.stem,
                "album": row["album"] or "",
                "duration": _optional_float(row["duration"]),
                "metadata_duration": _optional_float(metadata.get("duration")),
                "stored_genres": stored,
                "stored_model": str(metadata.get("maest_model") or ""),
                "selection_reason": reason,
                "_priority": priority,
            }
        )

    candidates.sort(key=lambda item: (item["_priority"], item["id"]))
    selected = candidates[:limit]
    for item in selected:
        item.pop("_priority", None)
    return selected


def _run_multiwindow(
    tracks: list[dict[str, Any]],
    *,
    db_path: Path,
    device: str,
    top_k: int,
    window_batch_size: int,
) -> dict[str, Any]:
    adapter = MaestGenreAdapter(device=device, top_k=top_k)
    adapter._load_model()
    torch = adapter._torch
    torchaudio = adapter._torchaudio
    model = adapter._model
    assert torch is not None and torchaudio is not None and model is not None

    device_name = adapter._device()
    input_seconds = maest_input_seconds(adapter.model_name)
    target_samples = int(TARGET_SAMPLE_RATE * input_seconds)
    labels = [_clean_label(str(label)) for label in getattr(model, "labels")]

    window_batch: list[Any] = []
    window_refs: list[tuple[int, float]] = []
    track_scores: dict[int, list[list[float]]] = defaultdict(list)
    track_window_summaries: dict[int, list[dict[str, Any]]] = defaultdict(list)
    processed_windows = 0
    failed_windows = 0

    for index, track in enumerate(tracks):
        track_started = time.perf_counter()
        try:
            audio = _load_track_audio(track["path"], torch=torch, torchaudio=torchaudio)
            duration = float(audio.numel()) / TARGET_SAMPLE_RATE if audio.numel() else 0.0
            starts = _window_starts(duration, input_seconds)
            track["window_starts_sec"] = starts
            track["used_window_count"] = len(starts)
            for start in starts:
                segment = _slice_window(audio, start_seconds=start, target_samples=target_samples, torch=torch)
                window_batch.append(segment)
                window_refs.append((index, start))
                if len(window_batch) >= window_batch_size:
                    processed_windows += _flush_windows(
                        window_batch,
                        window_refs,
                        track_scores,
                        track_window_summaries,
                        labels,
                        model=model,
                        torch=torch,
                        device=device_name,
                        top_k=top_k,
                    )
                    window_batch = []
                    window_refs = []
            track["multi_error"] = ""
        except Exception as error:  # noqa: BLE001 - report per-track errors without stopping the benchmark.
            failed_windows += WINDOW_COUNT
            track["window_starts_sec"] = []
            track["used_window_count"] = 0
            track["multi_error"] = f"{type(error).__name__}: {error}"
        finally:
            track["processing_seconds"] = time.perf_counter() - track_started

    if window_batch:
        processed_windows += _flush_windows(
            window_batch,
            window_refs,
            track_scores,
            track_window_summaries,
            labels,
            model=model,
            torch=torch,
            device=device_name,
            top_k=top_k,
        )

    for index, track in enumerate(tracks):
        scores = track_scores.get(index, [])
        stored = track.get("stored_genres", [])
        if scores:
            averaged = [sum(values) / len(values) for values in zip(*scores)]
            multi = _rank(labels, averaged, top_k)
            track["multi_genres"] = multi
            track["window_genres"] = track_window_summaries.get(index, [])
            track["top1_changed"] = bool(stored and multi and stored[0]["label"] != multi[0]["label"])
            track["top3_overlap"] = _label_overlap(stored, multi, n=3)
            track["top5_overlap"] = _label_overlap(stored, multi, n=5)
            track["new_labels_top5"] = _new_labels(stored, multi, n=5)
            track["dropped_labels_top5"] = _new_labels(multi, stored, n=5)
            track["window_disagreement"] = _window_disagreement(track["window_genres"])
        else:
            track["multi_genres"] = []
            track["window_genres"] = []
            track["top1_changed"] = False
            track["top3_overlap"] = 0
            track["top5_overlap"] = 0
            track["new_labels_top5"] = []
            track["dropped_labels_top5"] = []
            track["window_disagreement"] = ""

    changed = sum(1 for track in tracks if track.get("top1_changed"))
    errored = sum(1 for track in tracks if track.get("multi_error"))
    return {
        "database": str(db_path),
        "model_name": adapter.model_name,
        "device": device_name,
        "requested_device": device,
        "top_k": top_k,
        "track_count": len(tracks),
        "processed_window_count": processed_windows,
        "failed_window_estimate": failed_windows,
        "changed_top1_count": changed,
        "changed_top1_rate": changed / len(tracks) if tracks else 0.0,
        "errored_track_count": errored,
        "window_policy": {
            "input_seconds": input_seconds,
            "starts": "60s, 38% duration, 72% duration; clamped before outro and de-duplicated",
        },
        "tracks": tracks,
    }


def _flush_windows(
    window_batch: list[Any],
    window_refs: list[tuple[int, float]],
    track_scores: dict[int, list[list[float]]],
    track_window_summaries: dict[int, list[dict[str, Any]]],
    labels: list[str],
    *,
    model: Any,
    torch: Any,
    device: str,
    top_k: int,
) -> int:
    audio_batch = torch.stack(window_batch, dim=0).to(device)
    with torch.inference_mode():
        logits, _embeddings = model(audio_batch, melspectrogram_input=False)
        activations = torch.sigmoid(logits).detach().cpu().numpy()
    for (track_index, start), scores in zip(window_refs, activations):
        score_values = [float(score) for score in scores]
        track_scores[track_index].append(score_values)
        track_window_summaries[track_index].append(
            {
                "start_sec": round(start, 3),
                "genres": _rank(labels, score_values, top_k),
            }
        )
    return len(window_refs)


def _load_track_audio(path: str, *, torch: Any, torchaudio: Any) -> Any:
    audio_values, sample_rate, _decode_detail = load_audio_mono(
        path,
        torchaudio_module=torchaudio,
        target_sample_rate=TARGET_SAMPLE_RATE,
    )
    audio = torch.from_numpy(audio_values.copy()).unsqueeze(0)
    if sample_rate != TARGET_SAMPLE_RATE:
        audio = torchaudio.transforms.Resample(sample_rate, TARGET_SAMPLE_RATE)(audio)
    return audio.squeeze(0)


def _window_starts(duration_seconds: float, input_seconds: float) -> list[float]:
    if duration_seconds <= 0:
        return [0.0]
    max_start = max(0.0, duration_seconds - input_seconds)
    requested = [60.0, duration_seconds * 0.38, duration_seconds * 0.72]
    starts: list[float] = []
    for value in requested:
        start = min(max(0.0, value), max_start)
        if not any(abs(start - existing) < 1.0 for existing in starts):
            starts.append(start)
    return starts or [0.0]


def _slice_window(audio: Any, *, start_seconds: float, target_samples: int, torch: Any) -> Any:
    start = max(0, int(round(start_seconds * TARGET_SAMPLE_RATE)))
    segment = audio[start : start + target_samples]
    if segment.numel() < target_samples:
        segment = torch.nn.functional.pad(segment, (0, target_samples - segment.numel()))
    return segment


def _metadata(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stored_genres(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw = metadata.get("maest_genres")
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = _clean_label(str(item.get("label") or ""))
        score = _optional_float(item.get("score"))
        if label:
            result.append({"label": label, "score": float(score or 0.0)})
    return result


def _selection_reason(row: sqlite3.Row, metadata: dict[str, Any], stored: list[dict[str, Any]]) -> tuple[str, int]:
    labels = {str(item.get("label", "")).casefold() for item in stored}
    syncopated = {label.casefold() for label in SYNCOPATED_RHYTHM_GENRES}
    if labels & syncopated:
        return "stored_maest_syncopated_family", 0
    haystack = " ".join(
        str(value or "")
        for value in (
            row["artist"],
            row["title"],
            row["album"],
            row["path"],
            metadata.get("genre"),
            metadata.get("comment"),
        )
    ).casefold()
    hints = ("break", "broken", "garage", "electro", "jungle", "drum n bass", "drum & bass", "syncop")
    if any(hint in haystack for hint in hints):
        return "metadata_text_broken_hint", 1
    return "deterministic_fill_by_id", 2


def _clean_label(label: str) -> str:
    text = label.replace("_", " ").strip()
    if "---" in text:
        text = text.rsplit("---", 1)[-1].strip()
    return text


def _rank(labels: list[str], scores: list[float], top_k: int) -> list[dict[str, Any]]:
    by_label: dict[str, float] = {}
    for label, score in zip(labels, scores):
        if not label:
            continue
        by_label[label] = max(by_label.get(label, 0.0), float(score))
    ranked = sorted(by_label.items(), key=lambda item: item[1], reverse=True)
    return [{"label": label, "score": score} for label, score in ranked[:top_k]]


def _label_overlap(left: list[dict[str, Any]], right: list[dict[str, Any]], *, n: int) -> int:
    left_labels = {str(item.get("label", "")) for item in left[:n]}
    right_labels = {str(item.get("label", "")) for item in right[:n]}
    return len(left_labels & right_labels)


def _new_labels(left: list[dict[str, Any]], right: list[dict[str, Any]], *, n: int) -> list[str]:
    left_labels = {str(item.get("label", "")) for item in left[:n]}
    return [str(item.get("label", "")) for item in right[:n] if str(item.get("label", "")) not in left_labels]


def _window_disagreement(window_genres: list[dict[str, Any]]) -> str:
    top_labels = [str(window["genres"][0]["label"]) for window in window_genres if window.get("genres")]
    if not top_labels:
        return ""
    unique = sorted(set(top_labels))
    if len(unique) == 1:
        return f"stable:{unique[0]}"
    return "varies:" + " | ".join(unique)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _format_seconds(seconds: float) -> str:
    minutes, remainder = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours}h {minutes}m {remainder:.1f}s"
    if minutes:
        return f"{minutes}m {remainder:.1f}s"
    return f"{seconds:.1f}s"


if __name__ == "__main__":
    main()
