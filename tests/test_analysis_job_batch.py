from __future__ import annotations

from pathlib import Path

from dj_track_similarity.analysis_job_batch import DecodeFailure, decode_analysis_batch
from dj_track_similarity.analysis_models import AnalysisCandidate, AnalysisOutput, AnalysisTarget


def _candidate() -> AnalysisCandidate:
    output = AnalysisOutput("mulan", "embedding")
    return AnalysisCandidate(
        target=AnalysisTarget(
            catalog_uuid="catalog-test",
            track_id=1,
            track_uuid="track-1",
        ),
        file_path="C:/Music/broken.flac",
        file_size_bytes=100,
        file_modified_ns=1,
        missing_outputs=(output,),
    )


def test_decode_batch_defers_a_full_decode_failure_to_model_fallback() -> None:
    candidate = _candidate()
    processed: list[AnalysisCandidate] = []

    items = decode_analysis_batch(
        [candidate],
        {1: ("mulan",)},
        lambda _path: (_ for _ in ()).throw(RuntimeError("broken tail")),
        set_current_path=lambda _path: None,
        mark_track_processed=processed.append,
    )

    assert len(items) == 1
    assert items[0].candidate == candidate
    assert items[0].models == ("mulan",)
    assert isinstance(items[0].decoded, DecodeFailure)
    assert "broken tail" in str(items[0].decoded.error)
    assert processed == []
