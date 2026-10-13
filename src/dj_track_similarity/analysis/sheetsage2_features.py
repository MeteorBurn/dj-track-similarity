"""Canonical SheetSage2 events and summaries derived without model inference."""

from __future__ import annotations

import copy
import math
from collections import Counter
from collections.abc import Mapping
from fractions import Fraction
from typing import Any

import numpy as np

from ..db.ddl import SHEETSAGE2_FEATURE_COLUMNS, SHEETSAGE2_JSON_FEATURES as SHEETSAGE2_JSON_FEATURES

_MELODY_GROUPS = ("all", "vocal", "instrumental")
SHEETSAGE2_FEATURE_NAMES = tuple(name for name, _ in SHEETSAGE2_FEATURE_COLUMNS)


def _number(value: Any, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"SheetSage2 {name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"SheetSage2 {name} must be finite and >= {minimum}")
    return result


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"SheetSage2 {name} must be an integer >= {minimum}")
    return value


def validate_sheetsage2_timeline(payload: Mapping[str, object]) -> dict[str, object]:
    """Validate the persisted event boundary, returning an independent JSON value."""
    if not isinstance(payload, Mapping):
        raise ValueError("SheetSage2 timeline must be an object")
    result = copy.deepcopy(dict(payload))
    duration = _number(result.get("duration_s"), "duration_s")
    if duration <= 0:
        raise ValueError("SheetSage2 duration_s must be positive")
    for name in ("model_revision", "base_model_revision"):
        if not isinstance(result.get(name), str) or not result[name]:
            raise ValueError(f"SheetSage2 {name} is required")
    if not isinstance(result.get("parameters"), dict):
        raise ValueError("SheetSage2 parameters must be an object")
    windows = result.get("windows")
    if not isinstance(windows, list) or not windows or any(not isinstance(w, dict) for w in windows):
        raise ValueError("SheetSage2 windows must be a nonempty object list")
    warnings = result.get("warnings")
    if not isinstance(warnings, list) or any(not isinstance(w, str) for w in warnings):
        raise ValueError("SheetSage2 warnings must be a string list")
    events = result.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("SheetSage2 requires timed events")
    previous_time = -1.0
    anchors = 0
    last_interval_end: dict[str, float] = {}
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("SheetSage2 event must be an object")
        time_s = _number(event.get("time_s"), "event time_s")
        if not previous_time <= time_s <= duration:
            raise ValueError("SheetSage2 event times must be ordered and inside the audio")
        previous_time = time_s
        for key in ("global_subbeat", "source_subbeat", "window_index"):
            _integer(event.get(key), key)
        if event["window_index"] >= len(windows):
            raise ValueError("SheetSage2 event references an unknown window")
        if "timestamp_anchor" in event and not isinstance(event["timestamp_anchor"], bool):
            raise ValueError("SheetSage2 timestamp_anchor must be boolean")
        anchors += event.get("timestamp_anchor", False)
        rhythm = event.get("rhythm")
        if rhythm is not None:
            if not isinstance(rhythm, dict):
                raise ValueError("SheetSage2 rhythm must be an object")
            eighth = _integer(rhythm.get("eighth_position"), "eighth_position")
            if rhythm.get("numerator") is not None or rhythm.get("denominator") is not None:
                numerator = _integer(rhythm.get("numerator"), "meter numerator", 1)
                denominator = _integer(rhythm.get("denominator"), "meter denominator", 1)
                if Fraction(eighth * denominator, 8) >= numerator:
                    raise ValueError("SheetSage2 rhythmic position is outside its meter")
            if not isinstance(rhythm.get("timestamp_anchor"), bool):
                raise ValueError("SheetSage2 timestamp_anchor must be boolean")
            anchors += rhythm["timestamp_anchor"]
        for key in ("chord", "key", "structure"):
            interval = event.get(key)
            if interval is None:
                continue
            if not isinstance(interval, dict) or not isinstance(interval.get("label"), str) or not interval["label"]:
                raise ValueError(f"SheetSage2 {key} interval requires a label")
            end = _number(interval.get("end_s"), f"{key} end_s")
            if not time_s <= end <= duration or time_s < last_interval_end.get(key, 0.0) - 1e-8:
                raise ValueError(f"SheetSage2 {key} intervals overlap or exceed the audio")
            last_interval_end[key] = end
        melody = event.get("melody", [])
        if not isinstance(melody, list):
            raise ValueError("SheetSage2 melody must be a list")
        for note in melody:
            if not isinstance(note, dict):
                raise ValueError("SheetSage2 melodic event must be an object")
            pitch = _integer(note.get("pitch_midi"), "pitch_midi")
            if pitch > 127 or note.get("source_track") not in ("vocal", "instrumental"):
                raise ValueError("SheetSage2 melody has an invalid pitch or source")
            start = _number(note.get("start_s"), "melody start_s")
            end = _number(note.get("end_s"), "melody end_s")
            if abs(start - time_s) > 1e-8 or not start < end <= duration:
                raise ValueError("SheetSage2 melodic intervals must start at their event and have positive duration")
            _number(note.get("duration_steps"), "melody duration_steps")
    if not anchors:
        raise ValueError("SheetSage2 requires at least one genuine timestamp anchor")
    return result


def _durations(intervals: list[tuple[float, float, str]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for start, end, label in intervals:
        result[label] = result.get(label, 0.0) + end - start
    return result


def _dominant(durations: dict[str, float]) -> str | None:
    return max(durations, key=durations.get) if durations else None


def _coverage(intervals: list[tuple[float, float]]) -> float:
    total = 0.0
    end = 0.0
    for start, stop in sorted(intervals):
        total += max(0.0, stop - max(start, end))
        end = max(end, stop)
    return total


def derive_sheetsage2_features(payload: Mapping[str, object]) -> dict[str, object]:
    """Compute the fixed feature contract using only the canonical timeline."""
    data = validate_sheetsage2_timeline(payload)
    duration = float(data["duration_s"])
    events = data["events"]
    beats = []
    meter_changes = []
    intervals = {key: [] for key in ("chord", "key", "structure")}
    notes = []
    for event in events:
        time_s = event["time_s"]
        rhythm = event.get("rhythm")
        if rhythm and rhythm["numerator"] is not None:
            meter = (rhythm["numerator"], rhythm["denominator"])
            if not meter_changes or meter_changes[-1][1] != meter:
                meter_changes.append((time_s, meter))
            position = Fraction(rhythm["eighth_position"] * meter[1], 8)
            if position.denominator == 1:
                beats.append((time_s, meter, int(position)))
        for key in intervals:
            if key in event:
                interval = event[key]
                intervals[key].append((time_s, interval["end_s"], interval["label"]))
        notes.extend(event.get("melody", []))
    bpms = [240.0 / (right[1][1] * (right[0] - left[0])) for left, right in zip(beats, beats[1:])
            if right[0] > left[0] and left[1] == right[1] and right[2] == (left[2] + 1) % left[1][0]]
    meters = [(start, meter_changes[i + 1][0] if i + 1 < len(meter_changes) else duration,
               f"{meter[0]}/{meter[1]}") for i, (start, meter) in enumerate(meter_changes)]
    chord_durations = _durations(intervals["chord"])
    key_durations = _durations(intervals["key"])
    meter_durations = _durations(meters)
    chord_changes = sum(a[2] != b[2] for a, b in zip(intervals["chord"], intervals["chord"][1:]))
    features: dict[str, object] = {
        "beat_count": len(beats), "downbeat_count": sum(position == 0 for _, _, position in beats),
        "meter_change_count": max(0, len(meters) - 1),
        "bpm_median": float(np.median(bpms)) if bpms else None,
        "bpm_min": min(bpms) if bpms else None, "bpm_max": max(bpms) if bpms else None,
        "bpm_std": float(np.std(bpms)) if bpms else None,
        "dominant_meter": _dominant(meter_durations), "meter_durations_s": meter_durations,
        "chord_segment_count": len(intervals["chord"]), "chord_unique_count": len(chord_durations),
        "chord_change_count": chord_changes, "chord_change_rate_per_minute": chord_changes * 60.0 / duration,
        "dominant_chord": _dominant(chord_durations), "chord_durations_s": chord_durations,
        "dominant_key": _dominant(key_durations), "key_durations_s": key_durations,
        "key_change_count": sum(a[2] != b[2] for a, b in zip(intervals["key"], intervals["key"][1:])),
        "major_fraction": sum(seconds for label, seconds in key_durations.items() if label.endswith(":major")) / duration,
        "minor_fraction": sum(seconds for label, seconds in key_durations.items() if label.endswith(":minor")) / duration,
        "section_count": len(intervals["structure"]),
        "section_counts": dict(Counter(label for _, _, label in intervals["structure"])),
        "section_durations_s": _durations(intervals["structure"]),
        "intro_end_s": next((end for _, end, label in intervals["structure"] if label == "intro"), None),
        "outro_start_s": next((start for start, _, label in intervals["structure"] if label == "outro"), None),
        "first_chorus_start_s": next((start for start, _, label in intervals["structure"] if label == "chorus"), None),
    }
    for group in _MELODY_GROUPS:
        selected = [note for note in notes if group == "all" or note["source_track"] == group]
        pitches = [note["pitch_midi"] for note in selected]
        durations = [note["end_s"] - note["start_s"] for note in selected]
        deltas = []
        for source in ("vocal", "instrumental"):
            ordered = sorted((note for note in selected if note["source_track"] == source),
                             key=lambda note: (note["start_s"], note["end_s"], note["pitch_midi"]))
            deltas.extend(right["pitch_midi"] - left["pitch_midi"] for left, right in zip(ordered, ordered[1:])
                          if left["end_s"] <= right["start_s"])
        values = {
            "event_count": len(selected), "pitch_min": min(pitches) if pitches else None,
            "pitch_median": float(np.median(pitches)) if pitches else None,
            "pitch_max": max(pitches) if pitches else None,
            "pitch_range": max(pitches) - min(pitches) if pitches else None,
            "duration_min": min(durations) if durations else None,
            "duration_median": float(np.median(durations)) if durations else None,
            "duration_mean": float(np.mean(durations)) if durations else None,
            "duration_max": max(durations) if durations else None,
            "duration_std": float(np.std(durations)) if durations else None,
            "density_per_second": len(selected) / duration,
            "coverage_fraction": _coverage([(note["start_s"], note["end_s"]) for note in selected]) / duration,
            "interval_pair_count": len(deltas), "interval_abs_mean": float(np.mean(np.abs(deltas))) if deltas else None,
            "interval_histogram": dict(Counter(str(delta) for delta in deltas)),
        }
        features.update((f"melody_{group}_{name}", value) for name, value in values.items())
    return {name: features[name] for name in SHEETSAGE2_FEATURE_NAMES}
