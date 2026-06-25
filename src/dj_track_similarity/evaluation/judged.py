from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_FEEDBACK_SOURCE = "manual"
JUDGED_MODE = "judged_validation"
DIAGNOSTIC_MODE = "unsupervised_diagnostics_with_optional_judged_labels"
INSUFFICIENT_JUDGED_PAIRS = 50
CANDIDATE_PROFILE_JUDGED_PAIRS = 200
DEFAULT_UPDATE_JUDGED_PAIRS = 500


@dataclass(frozen=True)
class MatchedJudgedLabel:
    session_id: int
    event_id: int
    seed_track_id: int
    candidate_track_id: int
    source: str
    rating: int


def build_judged_label_gate(
    sessions: Sequence[Mapping[str, Any]],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    *,
    judged_only: bool = False,
) -> dict[str, Any]:
    matched_labels = matched_judged_labels(sessions, feedback_map)
    unique_labels = _unique_matched_labels(matched_labels)
    judged_pairs = len(unique_labels)
    label_status = judged_label_status(judged_pairs)
    return {
        "evaluation_mode": JUDGED_MODE if judged_only else DIAGNOSTIC_MODE,
        "label_status": label_status,
        "judged_pairs": judged_pairs,
        "judged_seeds": len({label.seed_track_id for label in unique_labels}),
        "matched_result_events": len({(label.session_id, label.event_id) for label in matched_labels}),
        "matched_label_rows": len(unique_labels),
        "can_create_candidate_profile": judged_pairs >= CANDIDATE_PROFILE_JUDGED_PAIRS,
        "can_update_defaults": judged_pairs >= DEFAULT_UPDATE_JUDGED_PAIRS,
        "default_update_policy": "manual_review_only_never_automatic",
        "guidance": judged_label_guidance(judged_pairs),
        "labels_by_rating": _labels_by_rating(unique_labels),
    }


def matched_judged_labels(
    sessions: Sequence[Mapping[str, Any]],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> tuple[MatchedJudgedLabel, ...]:
    labels: list[MatchedJudgedLabel] = []
    for session in sessions:
        seed_track_ids = session_seed_track_ids(session)
        if not seed_track_ids:
            continue
        preferred_source = session_feedback_source(session, default=None)
        for event in session.get("events", ()):
            if not isinstance(event, Mapping):
                continue
            candidate_track_id = int(event["track_id"])
            for label in matching_labels(seed_track_ids, candidate_track_id, preferred_source, feedback_map):
                labels.append(
                    MatchedJudgedLabel(
                        session_id=int(session["id"]),
                        event_id=int(event["id"]),
                        seed_track_id=int(label["seed_track_id"]),
                        candidate_track_id=int(label["candidate_track_id"]),
                        source=str(label["source"]),
                        rating=int(label["rating"]),
                    ),
                )
    return tuple(labels)


def matching_label(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    preferred_source: str | None,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    labels = matching_labels(seed_track_ids, candidate_track_id, preferred_source, feedback_map)
    if not labels:
        return None
    return labels[0]


def matching_labels(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    preferred_source: str | None,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    labels: list[Mapping[str, Any]] = []
    for seed_track_id in seed_track_ids:
        label = _matching_label_for_seed(int(seed_track_id), int(candidate_track_id), preferred_source, feedback_map)
        if label is not None:
            labels.append(label)
    return tuple(labels)


def session_feedback_source(session: Mapping[str, Any], default: str | None = DEFAULT_FEEDBACK_SOURCE) -> str | None:
    request = session.get("request")
    if not isinstance(request, Mapping):
        return default
    source = request.get("feedback_source") or request.get("label_source") or request.get("source")
    if source is None:
        return default
    text = str(source).strip()
    return text or default


def session_seed_track_ids(session: Mapping[str, Any]) -> tuple[int, ...]:
    seed_track_ids = session.get("seed_track_ids")
    if not isinstance(seed_track_ids, Sequence) or isinstance(seed_track_ids, (str, bytes)):
        return ()
    return tuple(int(track_id) for track_id in seed_track_ids)


def judged_label_status(judged_pairs: int) -> str:
    clean_judged_pairs = _non_negative_int(judged_pairs, "judged_pairs")
    if clean_judged_pairs < INSUFFICIENT_JUDGED_PAIRS:
        return "insufficient_data"
    if clean_judged_pairs < CANDIDATE_PROFILE_JUDGED_PAIRS:
        return "sufficient_for_diagnostics"
    if clean_judged_pairs < DEFAULT_UPDATE_JUDGED_PAIRS:
        return "sufficient_for_candidate_profile"
    return "sufficient_for_default_review"


def judged_label_guidance(judged_pairs: int) -> str:
    label_status = judged_label_status(judged_pairs)
    if label_status == "insufficient_data":
        return "Fewer than 50 matched judged pairs are available. Report output is allowed, but this is not enough data for search-quality diagnostics."
    if label_status == "sufficient_for_diagnostics":
        return "50-199 matched judged pairs are available. Use the report for diagnostics only; do not create a candidate score profile or update defaults."
    if label_status == "sufficient_for_candidate_profile":
        return "200-499 matched judged pairs are available. A candidate score profile may be considered, but default updates remain out of scope."
    return "500 or more matched judged pairs are available. A default update may be considered only through explicit manual review; it is never automatic."


def report_status_for_judged_gate(default_status: str, gate: Mapping[str, Any], *, judged_only: bool) -> str:
    if not judged_only:
        return default_status
    if gate.get("label_status") == "insufficient_data":
        return "insufficient_data"
    return default_status


def _matching_label_for_seed(
    seed_track_id: int,
    candidate_track_id: int,
    preferred_source: str | None,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if preferred_source:
        return feedback_map.get((seed_track_id, candidate_track_id, preferred_source))
    manual_label = feedback_map.get((seed_track_id, candidate_track_id, DEFAULT_FEEDBACK_SOURCE))
    if manual_label is not None:
        return manual_label
    return _first_label_for_any_source(seed_track_id, candidate_track_id, feedback_map)


def _first_label_for_any_source(
    seed_track_id: int,
    candidate_track_id: int,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    matches = [
        label
        for (label_seed_id, label_candidate_id, _source), label in feedback_map.items()
        if label_seed_id == seed_track_id and label_candidate_id == candidate_track_id
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda label: (int(label["seed_track_id"]), str(label["source"])))[0]


def _unique_matched_labels(labels: Sequence[MatchedJudgedLabel]) -> tuple[MatchedJudgedLabel, ...]:
    by_key: dict[tuple[int, int, str], MatchedJudgedLabel] = {}
    for label in labels:
        key = (label.seed_track_id, label.candidate_track_id, label.source)
        by_key.setdefault(key, label)
    return tuple(by_key[key] for key in sorted(by_key))


def _labels_by_rating(labels: Sequence[MatchedJudgedLabel]) -> dict[str, int]:
    counts = Counter(label.rating for label in labels)
    return {str(rating): counts.get(rating, 0) for rating in range(4)}


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a non-negative integer") from error
    if clean_value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return clean_value
