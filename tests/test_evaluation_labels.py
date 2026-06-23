from __future__ import annotations

from pathlib import Path

import pytest

from dj_track_similarity.evaluation.labels import (
    PairFeedbackLabel,
    TransitionFeedbackLabel,
    load_pair_feedback_labels,
    load_transition_feedback_labels,
)


def test_load_pair_feedback_csv_parses_tags_and_defaults_source(tmp_path: Path) -> None:
    input_path = tmp_path / "pair_feedback.csv"
    input_path.write_text(
        "seed_track_id,candidate_track_id,rating,reason_tags,notes,source\n"
        '1,2,3,"groove, bad",works,manual\n',
        encoding="utf-8",
    )

    labels = load_pair_feedback_labels(input_path)

    assert labels == [PairFeedbackLabel(1, 2, 3, ("groove", "bad"), "works", "manual")]


def test_load_transition_feedback_jsonl_parses_list_tags(tmp_path: Path) -> None:
    input_path = tmp_path / "transition_feedback.jsonl"
    input_path.write_text(
        '{"outgoing_track_id": 1, "incoming_track_id": 2, "rating": 2, "risk_tags": ["energy", "key"], "notes": "watch", "source": "crate"}\n',
        encoding="utf-8",
    )

    labels = load_transition_feedback_labels(input_path)

    assert labels == [TransitionFeedbackLabel(1, 2, 2, ("energy", "key"), "watch", "crate")]


def test_pair_feedback_loader_fails_fast_with_rating_line_number(tmp_path: Path) -> None:
    input_path = tmp_path / "pair_feedback.csv"
    input_path.write_text(
        "seed_track_id,candidate_track_id,rating,reason_tags,notes,source\n"
        "1,2,4,,nope,manual\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid rating on line 2"):
        load_pair_feedback_labels(input_path)
