from __future__ import annotations

import math
from dataclasses import dataclass


MAEST_WINDOW_POSITIONS = (0.2, 0.5, 0.8)
MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class MaestWindowContext:
    leading_silence_seconds: float | None
    trailing_silence_seconds: float | None
    intro_end_seconds: float | None
    outro_start_seconds: float | None


def select_maest_window_starts(
    duration_seconds: float,
    window_seconds: float,
    context: MaestWindowContext | None = None,
) -> tuple[float, ...]:
    duration = _positive_finite(duration_seconds, "duration_seconds")
    window = _positive_finite(window_seconds, "window_seconds")
    if duration <= window:
        return (0.0,)

    range_start, range_end = _selected_range(duration, window, context)
    max_start = range_end - window
    starts: list[float] = []
    for position in MAEST_WINDOW_POSITIONS:
        center = range_start + position * (range_end - range_start)
        start = min(max(range_start, center - window / 2.0), max_start)
        if not any(
            abs(start - existing) < MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS
            for existing in starts
        ):
            starts.append(start)
    return tuple(starts) or (range_start,)


def _selected_range(
    duration: float,
    window: float,
    context: MaestWindowContext | None,
) -> tuple[float, float]:
    full = (0.0, duration)
    if context is None:
        return full

    leading = _optional_boundary(context.leading_silence_seconds, duration)
    trailing = _optional_boundary(context.trailing_silence_seconds, duration)
    hard_start = 0.0 if leading is None else leading
    hard_end = duration if trailing is None else duration - trailing
    hard = (hard_start, hard_end)

    intro = _optional_boundary(context.intro_end_seconds, duration)
    outro = _optional_boundary(context.outro_start_seconds, duration)
    main = (
        max(hard_start, 0.0 if intro is None else intro),
        min(hard_end, duration if outro is None else outro),
    )
    for candidate in (main, hard, full):
        if candidate[1] - candidate[0] >= window:
            return candidate
    return full


def _optional_boundary(value: float | None, duration: float) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return min(max(number, 0.0), duration)


def _positive_finite(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return number
