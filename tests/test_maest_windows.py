from __future__ import annotations

import math

import pytest

from dj_track_similarity.maest_windows import (
    MaestWindowContext,
    select_maest_window_starts,
)


@pytest.mark.parametrize(
    ("duration", "expected"),
    (
        (20.0, (0.0,)),
        (30.0, (0.0,)),
        (30.5, (0.0,)),
        (40.0, (0.0, 5.0, 10.0)),
        (60.0, (0.0, 15.0, 30.0)),
        (180.0, (21.0, 75.0, 129.0)),
        (300.0, (45.0, 135.0, 225.0)),
    ),
)
def test_centered_full_duration_starts(
    duration: float,
    expected: tuple[float, ...],
) -> None:
    assert select_maest_window_starts(duration, 30.0) == expected


def test_prefers_intro_outro_range_inside_non_silent_range() -> None:
    context = MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=40.0,
        outro_start_seconds=170.0,
    )

    assert select_maest_window_starts(200.0, 30.0, context) == (
        51.0,
        90.0,
        129.0,
    )


def test_short_main_range_relaxes_to_non_silent_range() -> None:
    context = MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=100.0,
        outro_start_seconds=120.0,
    )

    assert select_maest_window_starts(200.0, 30.0, context) == pytest.approx(
        (27.0, 82.5, 138.0)
    )


def test_short_non_silent_range_relaxes_to_full_duration() -> None:
    context = MaestWindowContext(
        leading_silence_seconds=20.0,
        trailing_silence_seconds=20.0,
        intro_end_seconds=None,
        outro_start_seconds=None,
    )

    assert select_maest_window_starts(60.0, 30.0, context) == (
        0.0,
        15.0,
        30.0,
    )


@pytest.mark.parametrize(
    "context",
    (
        MaestWindowContext(
            leading_silence_seconds=math.nan,
            trailing_silence_seconds=None,
            intro_end_seconds=None,
            outro_start_seconds=None,
        ),
        MaestWindowContext(
            leading_silence_seconds=None,
            trailing_silence_seconds=None,
            intro_end_seconds=170.0,
            outro_start_seconds=40.0,
        ),
    ),
)
def test_invalid_context_falls_back_without_failure(
    context: MaestWindowContext,
) -> None:
    assert select_maest_window_starts(200.0, 30.0, context) == (
        25.0,
        85.0,
        145.0,
    )


def test_rejects_invalid_duration_or_window() -> None:
    with pytest.raises(ValueError, match="duration_seconds"):
        select_maest_window_starts(0.0, 30.0)
    with pytest.raises(ValueError, match="window_seconds"):
        select_maest_window_starts(60.0, 0.0)
