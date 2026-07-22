# Backend Package Notes

Guidance specific to `src/dj_track_similarity/`. See root `AGENTS.md` for global safety rules, model contracts, and verification shortcuts — do not repeat them here.

## Module Boundaries

- `api.py` composes route modules only. Add a new route by creating `api_routes_<area>.py` with a `register_<area>_routes(app, state, ...)` function and wiring it into `create_app()`. Keep composition free of business logic.
- `api_state.py::AppDatabaseState` owns every job manager and the shared `AnalysisStageQueue`. Add a new job manager as a field, initialise it in `switch()`, and expose it through a `require_*` method. `_has_active_jobs()` guards DB switching — extend it if you add a manager.
- `database.py::LibraryDatabase` is the sole SQLite gateway. New tables/queries live in a `db_*.py` module (repository style) and are called through a `LibraryDatabase` method. Do not open `sqlite3` connections directly outside `db_connection.py` — path-scoped locking, WAL, and busy timeout are set there.
- `analysis_pipeline.py::PIPELINE_STAGE_ORDER = ("sonara", "ml", "classifiers")`. Never reorder unless deliberately redesigning; SONARA feeds classifier scoring, and reversing it breaks readiness accounting.
- `analysis_model_runners.py` is the single seam between `AnalysisJobManager` and each model backend. Adding a model touches this file + `analysis_config.py` (validation) + `api_schemas.py` (schema).

## Safety-Critical Files

- `sonara_contract.py` — every SONARA signature constant (`SONARA_EXPECTED_VERSION`, `SONARA_EXPECTED_SCHEMA_VERSION`, `SONARA_ANALYSIS_MODE`, `SONARA_SAMPLE_RATE`, `SONARA_BPM_MIN/MAX`, `SONARA_PROJECT_FEATURE_REVISION`, `SONARA_DECODER_BACKEND`, `SONARA_EXECUTION_PATH`). Bumping any invalidates every stored SONARA result; follow the reanalysis + classifier-retrain protocol in root `AGENTS.md`.
- `classifier_manifest.py` — `CLASSIFIER_MANIFEST_VERSION = 2`, `CLASSIFIER_REQUIRED_INPUTS = ("sonara", "mert", "maest")`, `CLASSIFIER_SUPPORTED_INPUTS` adds CLAP. Changing required inputs or the manifest version blocks scoring on old artifacts.
- `db_schema.py` (SONARA sidecar migration + classifier-score invalidation on feature-revision bump) — never add a code path that silently keeps SONARA-dependent scores after a revision change.
- `tags.py` + `wave_tags.py` — the only sanctioned audio-write path (MAEST genre only). Do not add other write paths here.
- `db_tracks.py` — relocation mutates only `tracks.path`; never touch files.
- `media_preview.py` — temporary WAV transcoding for AIFF preview only; must clean up the temp file.
- `audio_doctor_jobs.py` + `audio_dedup_jobs.py` — dry-run / report-first invariants plus the exact `APPLY REPAIR` / `APPLY DELETE` phrases. Do not weaken.
- `embedding.py::MuqEmbeddingAdapter` — 24 kHz `float32`, torchaudio-only. No librosa, no half-precision, no autocast, no `torch.compile`.

## Large / Complex Files (Read Carefully Before Editing)

- `set_builder.py` (~1865 lines) — Smart Set Builder core. Split before adding more responsibility.
- `cli.py` (~1213 lines) — Typer surface for every top-level command.
- `hybrid_search.py` (~1064 lines) + `hybrid_explanation.py` (~710 lines) — hybrid scoring + user-facing reasons.
- `db_analysis.py` (~1061 lines) + `ann_index.py` (~964 lines) — analysis persistence + optional ANN sidecars.
- `db_schema.py` (~595 lines) — every migration lives here; migrations are one-way and must not leave mixed-signature data.
- `transition_diagnostics.py` (~629 lines) — mixing compatibility scoring; leans on `tempo_resolution.py` + `track_resolution.py`.

## Evaluation Subsystem (`evaluation/`)

- Retrieval evaluation, judged data, calibration, risk sweeps, and score-profile optimization. Registered marker `evaluation` is rarely applied — mark heavy sweeps with it so `-m "not evaluation"` can skip them.
- `score_profile_optimizer.py` (~43 kB) and `risk_sweep.py` (~32 kB) are the heavyweight optimizers; treat as compute-bound and prefer temp DB fixtures.

## Testing Conventions

- Tests live in the top-level `tests/` (not colocated). Function-based (no test classes). No `conftest.py`; each test constructs its own temp SQLite + WAV.
- SONARA is stubbed via `sonara_module=<FakeSonara>`; MERT / MuQ / CLAP / MAEST are stubbed with injected fake torch / laion_clap / huggingface modules. Do not add real-model calls to tests.
- Focused run: `python -m pytest tests/test_<name>.py --override-ini addopts=`.
