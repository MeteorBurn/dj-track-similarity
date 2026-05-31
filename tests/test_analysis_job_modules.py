from __future__ import annotations

from pathlib import Path


def test_analysis_jobs_keeps_orchestration_separate_from_runner_implementations() -> None:
    source = Path("src/dj_track_similarity/analysis_jobs.py").read_text(encoding="utf-8")

    assert "class AnalysisJobManager" in source
    assert "class SonaraModelRunner" not in source
    assert "class MaestModelRunner" not in source
    assert "class EmbeddingModelRunner" not in source
    assert "ClapEmbeddingAdapter" not in source
    assert "MaestGenreAdapter" not in source
    assert "analyze_and_store_sonara_features_from_audio" not in source
    assert "decode_analysis_batch" in source
    assert "copy_analysis_status" in source


def test_analysis_split_modules_expose_batch_state_and_runner_boundaries() -> None:
    state_source = Path("src/dj_track_similarity/analysis_job_state.py").read_text(encoding="utf-8")
    batch_source = Path("src/dj_track_similarity/analysis_job_batch.py").read_text(encoding="utf-8")
    runner_source = Path("src/dj_track_similarity/analysis_model_runners.py").read_text(encoding="utf-8")

    assert "class AnalysisJobStatus" in state_source
    assert "def mark_track_processed" in state_source
    assert "class AnalysisBatchItem" in batch_source
    assert "def decode_analysis_batch" in batch_source
    assert "class SonaraModelRunner" in runner_source
    assert "class MaestModelRunner" in runner_source
    assert "class EmbeddingModelRunner" in runner_source
