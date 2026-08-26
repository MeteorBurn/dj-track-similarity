from __future__ import annotations

from dj_track_similarity import (
    analysis_job_batch,
    analysis_job_state,
    analysis_jobs,
    analysis_model_runners,
)


MODULE_OWNERSHIP = {
    "dj_track_similarity.analysis_jobs": (analysis_jobs.AnalysisJobManager,),
    "dj_track_similarity.analysis_job_state": (
        analysis_job_state.AnalysisJobStatus,
        analysis_job_state.mark_track_processed,
        analysis_job_state.copy_analysis_status,
    ),
    "dj_track_similarity.analysis_job_batch": (
        analysis_job_batch.AnalysisBatchItem,
        analysis_job_batch.decode_analysis_batch,
    ),
    "dj_track_similarity.analysis_model_runners": (
        analysis_model_runners.SonaraModelRunner,
        analysis_model_runners.MaestModelRunner,
        analysis_model_runners.EmbeddingModelRunner,
    ),
}


def test_analysis_job_modules_own_their_declared_members() -> None:
    for module_name, members in MODULE_OWNERSHIP.items():
        for member in members:
            assert member.__module__ == module_name
