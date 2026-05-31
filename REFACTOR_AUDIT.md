# Refactor Audit

This audit is based on the current code and tests. The current working database
is `C:\db\abstracted.sqlite`; no schema or field changes are approved here.

## Whitelist

| Area | Keep | Reason |
| --- | --- | --- |
| CLI | `scan`, `serve`, `analyze`, `analyze-classifier`, `doctor`, `text-search`, `relocate-library` | Current local workflows and tests exercise these commands. |
| API | UI-facing `/api/database/*`, `/api/library/*`, `/api/tracks*`, `/api/analysis/*`, `/api/search*`, `/api/classifiers*`, `/api/tags/genres*`, `/api/export`, `/media/{track_id}` | Current frontend API client calls these endpoints. |
| Scripts | `scripts/audio_repair/repair_audio_metadata.py`, `scripts/audio_dedup/audio_dedup.py`, `scripts/optimize_database.py`, `scripts/sonara_bpm_calibration.py`, `scripts/diagnose_metadata_size.py` | Useful maintenance or diagnostic flows; not removed by UI-only criteria. |
| Tests | Negative tests for removed fake adapters, removed old endpoints, and rejected legacy options | These protect the active surface from reintroducing old behavior. |

## Removed

| Symbol/path | Callers found in current code | Tests found | Decision |
| --- | --- | --- | --- |
| `scripts/migrate_sonara_brightness.py` | None. `rg migrate_sonara_brightness` only found this audit after removal. | `scripts/tests/test_migrate_sonara_brightness.py` covered the script itself only. | Remove one-way migration for an old SONARA payload shape; not needed for the current single database workflow. |
| `scripts/backfill_maest_syncopated_rhythm.py` | None. `rg backfill_maest_syncopated_rhythm` only found this audit after removal. | `scripts/tests/test_backfill_maest_syncopated_rhythm.py` covered the script itself only. | Remove one-way backfill for older MAEST metadata; current code writes `maest_syncopated_rhythm` directly in `save_genres`. |
| `scripts/strip_sonara_descriptions.py` | None. `rg strip_sonara_descriptions` only found this audit after removal. | `scripts/tests/test_strip_sonara_descriptions.py` covered the script itself only. | Remove one-way cleanup for old oversized SONARA metadata; current Sonara storage no longer writes those payloads. |
| `LibraryDatabase.list_tracks_missing_sonara` | None. `rg list_tracks_missing_sonara` found no callers after analysis job refactor. | No direct tests; covered indirectly by old selected-analysis job flow before replacement. | Remove unused per-model missing-track query; `list_analysis_candidates` is the single active analyzer candidate interface. |
| `LibraryDatabase.list_tracks_missing_maest` | None. `rg list_tracks_missing_maest` found no callers after analysis job refactor. | No direct tests; covered indirectly by old selected-analysis job flow before replacement. | Remove unused per-model missing-track query; `list_analysis_candidates` handles MAEST candidates and missing model accounting. |
| `LibraryDatabase.list_tracks_missing_embedding` | None. `rg list_tracks_missing_embedding` found no callers after analysis job refactor. | No direct tests; covered indirectly by old selected-analysis job flow before replacement. | Remove unused generic embedding missing-track query; MERT/CLAP selection now goes through `list_analysis_candidates`. |
| `LibraryDatabase.list_tracks_missing_any_analysis` | None. `rg list_tracks_missing_any_analysis` found no callers after analysis job refactor. | Replaced by focused tests for `list_analysis_candidates` and `AnalysisJobManager` using that helper. | Remove the heavier Track-producing multi-model candidate query; the analyzer now fetches lean `AnalysisCandidate` rows. |
| `analysis_jobs._missing_models` | None after `AnalysisCandidate.missing_models` became the job source of truth. | Replaced by `test_database_lists_lean_analysis_candidates_with_missing_models`. | Remove duplicate missing-model accounting from the orchestration layer. |

## Deferred

| Candidate | Decision |
| --- | --- |
| `batch_size` compatibility fields in job statuses | Keep for now because tests and frontend types still read them; remove only after a focused UI/API contract update. |
| Rhythm Lab old table migrations in `lab_db.py` | Keep until the active `tools/rhythm-lab/data/rhythm_lab.sqlite` is audited; this is a separate database from `C:\db\abstracted.sqlite`. |
| Current API/CLI negative tests for removed routes/options | Keep as safety guards. |
