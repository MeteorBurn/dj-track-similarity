"""Small deterministic complete SheetSage2 results for temporary libraries."""

from __future__ import annotations

import numpy as np

from dj_track_similarity.analysis.sheetsage2_features import derive_sheetsage2_features
from dj_track_similarity.analysis_models import (
    AnalysisTarget, EmbeddingOutput, MERT_V2_MODEL_REVISION, SHEETSAGE2_MODEL_REVISION, SheetSage2Write,
)


def sheetsage2_timeline() -> dict[str, object]:
    return {
        "duration_s": 2.0,
        "model_revision": SHEETSAGE2_MODEL_REVISION,
        "base_model_revision": MERT_V2_MODEL_REVISION,
        "parameters": {"sample_rate_hz": 24000, "window_s": 300, "overlap_s": 200, "lookahead_s": 100},
        "windows": [{"start": 0.0, "end": 2.0, "accept_start": 0.0, "accept_end": 2.0}],
        "warnings": [],
        "events": [{
            "time_s": 0.0, "global_subbeat": 0, "source_subbeat": 0, "window_index": 0,
            "rhythm": {"numerator": 4, "denominator": 4, "eighth_position": 0, "timestamp_anchor": True},
            "chord": {"label": "C:maj", "end_s": 2.0},
            "key": {"label": "C:major", "end_s": 2.0},
            "structure": {"label": "intro", "end_s": 2.0},
            "melody": [{"pitch_midi": 60, "source_track": "instrumental", "start_s": 0.0,
                        "end_s": 0.5, "duration_steps": 4}],
        }, {
            "time_s": 0.5, "global_subbeat": 4, "source_subbeat": 4, "window_index": 0,
            "rhythm": {"numerator": 4, "denominator": 4, "eighth_position": 2, "timestamp_anchor": True},
        }],
    }


def complete_sheetsage2_write(
    database,
    target: AnalysisTarget,
    *,
    embedding: EmbeddingOutput | None = None,
    analyzed_at: str = "2026-10-13T00:00:00.000000Z",
) -> SheetSage2Write:
    state = database.get_track_file_states_by_ids((target.track_id,))[0]
    timeline = sheetsage2_timeline()
    if embedding is None:
        vectors = tuple(np.eye(1, 1024, index, dtype=np.float32)[0] for index in range(24))
        embedding = EmbeddingOutput("sheetsage2", vectors[-1], analyzed_at, vectors)
    return SheetSage2Write(
        target=target, file_path=state.file_path,
        file_size_bytes=state.file_size_bytes, file_modified_ns=state.file_modified_ns,
        timeline=timeline, features=derive_sheetsage2_features(timeline), embedding=embedding,
    )
