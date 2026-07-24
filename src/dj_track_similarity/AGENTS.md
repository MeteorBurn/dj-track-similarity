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
- `classifier_manifest.py` — `CLASSIFIER_MANIFEST_VERSION = 2`; `CLASSIFIER_SUPPORTED_INPUTS = ("sonara", "mert", "maest", "clap", "muq")`. Ordered `required_outputs` are derived from the artifact's actual features. Do not bump the manifest version merely to use an already-supported input; changing version or output semantics blocks old artifacts.
- `db_connection.py` + `db_schema.py` + `db_schema_v7.py` — greenfield Core/Artifacts creation, exact v7 validation, and canonical Core DDL/domain models. Non-v7 or definition-mismatched bundles are rejected; do not add an in-place migration path.
- `tags.py` + `wave_tags.py` — the only sanctioned audio-write path (MAEST genre only). Do not add other write paths here.
- `db_tracks.py` — relocation mutates only `tracks.file_path`; never touch files.
- `media_preview.py` — temporary WAV transcoding for AIFF preview only; must clean up the temp file.
- `audio_doctor_jobs.py` + `audio_dedup_jobs.py` — dry-run / report-first invariants plus the exact `APPLY REPAIR` / `APPLY DELETE` phrases. Do not weaken.
- `embedding.py::MuqEmbeddingAdapter` — 24 kHz `float32`, torchaudio-only. No librosa, no half-precision, no autocast, no `torch.compile`.

## Large / Complex Files (Read Carefully Before Editing)

- `set_builder.py` — Smart Set Builder core. Prefer extracting focused helpers before adding more responsibility.
- `cli.py` — Typer surface for every top-level command.
- `hybrid_search.py` + `hybrid_explanation.py` — hybrid scoring, diagnostics, session recording, and user-facing reasons.
- `db_analysis.py` + `ann_index.py` — analysis persistence and optional ANN sidecars.
- `db_connection.py` + `db_schema.py` + `db_schema_v7.py` — bundle creation/validation, exact Core schema checks, and canonical v7 DDL; preserve fail-closed rejection of non-v7 or mismatched bundles.
- `transition_diagnostics.py` — mixing compatibility scoring; leans on `tempo_resolution.py` + `track_resolution.py`.

## Embedding Source Contracts

- Canonical API types live in `api_schemas.py`: `EmbeddingSource` is MERT/MAEST/MuQ/CLAP; `HybridSearchSource` and `EvaluationSource` add SONARA. Extend shared literals and generic mappings instead of adding MuQ-only branches or aliases.
- Generic seed search accepts `analysis_family="muq"` and reads exact-current stored embeddings. Do not add a separate MuQ endpoint or index format.
- SET defaults are `("mert", "maest", "muq", "clap")`; raw weights are MERT `0.30`, MAEST `0.18`, MuQ `0.15`, CLAP `0.22`, and `sonara_broad` `0.30`. Weights must exactly match enabled embeddings plus `sonara_broad`, be finite/nonnegative, and normalize deterministically.
- Hybrid defaults are `("mert", "maest", "muq", "sonara", "clap")` with equal normalized weights when no profile/custom weights are supplied. Disabled sources are absent from readiness, contract hashes, fusion, breakdowns, and transition diagnostics.
- MuQ cosine evidence is normalized like other embedding sources in Hybrid explanations, but it has no validated automatic mapping to mood/texture/genre axes. Keep it as generic acoustic support unless evidence justifies a specific semantic axis.
- Evaluation auto-seed completeness follows the request/profile's selected sources. Do not make MuQ globally mandatory for an explicit legacy profile that excludes it.

## Evaluation Subsystem (`evaluation/`)

- Retrieval evaluation, judged data, calibration, risk sweeps, and score-profile optimization. Registered marker `evaluation` is rarely applied — mark heavy sweeps with it so `-m "not evaluation"` can skip them.
- `score_profile_optimizer.py` and `risk_sweep.py` are heavyweight optimizers; treat them as compute-bound and prefer temp DB fixtures.

## Testing Conventions

- Tests live in the top-level `tests/` (not colocated). Function-based (no test classes). No `conftest.py`; each test constructs its own temp SQLite + WAV.
- SONARA is stubbed via `sonara_module=<FakeSonara>`; MERT / MuQ / CLAP / MAEST are stubbed with injected fake torch / laion_clap / huggingface modules. Do not add real-model calls to tests.
- Focused run: `python -m pytest tests/test_<name>.py --override-ini addopts=`.
- Source-contract changes normally require the matching API, SET/Hybrid/evaluation/classifier test modules together; an isolated unit test is not proof that every consumer accepted the new source list.
