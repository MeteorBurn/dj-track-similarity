# Backend Package Notes

Guidance specific to `src/dj_track_similarity/`. See root `AGENTS.md` for global safety rules, model integration, and verification shortcuts — do not repeat them here.

## Active Development

- The root evolution policy applies. Modules, schemas, pipeline order, source
  families, defaults, and repository patterns below describe the current
  package; they may be deliberately redesigned.
- When requirements change, prefer a coherent new design and one source of
  truth over version checks, duplicated tuples, legacy aliases, or adapters
  whose only purpose is preserving this snapshot. Coordinate source, database
  migration when real stored data requires it, API types, frontend, tests, and
  docs.
- Preserve safety outcomes during ordinary changes. An explicit owner-directed
  safety redesign is allowed, but must define and verify the replacement
  boundary rather than bypassing the current one incidentally.

## Current Module Boundaries

- `api.py` currently composes `api_routes_<area>.py` modules through
  `register_<area>_routes(...)`. Follow that pattern for a local addition, or
  deliberately refactor composition when the requested change warrants it;
  avoid mixing business logic into composition accidentally.
- `api_state.py::AppDatabaseState` currently owns the job managers and shared
  `AnalysisStageQueue`; `switch()`, `require_*`, and `_has_active_jobs()` form
  the active lifecycle pattern. Follow it for a local addition, or update the
  complete lifecycle coherently when redesigning state ownership.
- `database.py::LibraryDatabase` is the current SQLite gateway, with `db_*.py`
  repository modules and connection policy in `db_connection.py`. This can be
  refactored, but direct connections must not bypass active locking, WAL, busy
  timeout, or equivalent concurrency safeguards.
- `analysis_pipeline.py::PIPELINE_STAGE_ORDER` currently sequences SONARA, ML,
  and classifiers. Reordering or replacing stages is allowed when requested;
  update stage dependencies, readiness accounting, status, and tests together.
- `analysis_model_runners.py` is the current seam between
  `AnalysisJobManager` and model backends. Confirm and update all current
  consumers rather than treating that fan-out as a permanent checklist.

## Current Safety-Critical Files

- `sonara_runtime.py`, `sonara_features.py`, and `sonara_storage.py` adapt the
  installed SONARA API and persist the concrete outputs the project uses.
  When SONARA changes, update these modules and verify the affected runtime
  paths directly; do not add version gates or compatibility identities.
- `classifier_manifest.py` describes classifier artifact metadata and supported
  inputs. Evolve it as needed for compatible package and model updates.
- `db_connection.py` + `db_schema.py` + `db_ddl.py` + `db_structure.py` own database
  creation, validation, and DDL. Schema evolution and migrations are allowed
  when requested and should be verified against temporary databases first.
- `tags.py` + `wave_tags.py` implement the currently sanctioned normal
  audio-write path. Do not introduce a new write as an incidental side effect;
  an explicitly requested write feature must define preservation, recovery,
  confirmation, and focused verification.
- `db_tracks.py` — relocation mutates only `tracks.file_path`; never touch files.
- `media_preview.py` — temporary WAV transcoding for AIFF preview only; must clean up the temp file.
- `audio_doctor_jobs.py` + `audio_dedup_jobs.py` own the current dry-run /
  report-first policies and confirmation sources. Keep safety literals
  centralized; a requested workflow change must update all surfaces and prove
  the replacement gate.
- `embedding.py::MuqEmbeddingAdapter` currently uses the verified 24 kHz
  `float32` torchaudio path. Alternative decoding or optimization is allowed
  when deliberately requested and supported by focused numerical, dependency,
  and device verification.

## Large / Complex Files (Read Carefully Before Editing)

- `set_builder.py` — Smart Set Builder core. Prefer extracting focused helpers before adding more responsibility.
- `cli.py` — Typer surface for every top-level command.
- `hybrid_search.py` + `hybrid_explanation.py` — hybrid scoring, diagnostics, session recording, and user-facing reasons.
- `db_analysis.py` + `ann_index.py` — analysis persistence and optional ANN sidecars.
- `db_connection.py` + `db_schema.py` + `db_ddl.py` + `db_structure.py` — database creation,
  validation, and DDL; adapt these together when storage requirements change.
- `transition_diagnostics.py` — mixing compatibility scoring; leans on `tempo_resolution.py` + `track_resolution.py`.

## Current Embedding Sources

- API source types currently live in `api_schemas.py`. Treat their members as
  the active schema, not a permanent family list; change shared schemas and
  generic mappings coherently instead of scattering family-specific branches.
- Generic seed search accepts `analysis_family="muq"` and reads stored embeddings. Prefer shared endpoints and index formats where practical.
- SET and Hybrid source sets, weights, and validation live in executable source
  and schemas. Treat them as tunable current defaults. When changing them,
  update selection, validation, readiness, normalization, explanations,
  transition diagnostics, API/UI, and focused tests from a shared definition.
- Under the current behavior, disabled sources are absent from readiness,
  fusion, breakdowns, and transition diagnostics. A redesigned behavior should
  state its semantics explicitly rather than preserving zero-weight sources as
  hidden requirements.
- MuQ cosine evidence is normalized like other embedding sources in Hybrid explanations, but it has no validated automatic mapping to mood/texture/genre axes. Keep it as generic acoustic support unless evidence justifies a specific semantic axis.
- Evaluation auto-seed completeness follows the request/profile's selected sources. Do not make MuQ globally mandatory for an explicit legacy profile that excludes it.

## Evaluation Subsystem (`evaluation/`)

- Retrieval evaluation, judged data, calibration, risk sweeps, and score-profile optimization. Registered marker `evaluation` is rarely applied — mark heavy sweeps with it so `-m "not evaluation"` can skip them.
- `score_profile_optimizer.py` and `risk_sweep.py` are heavyweight optimizers; treat them as compute-bound and prefer temp DB fixtures.

## Testing Conventions

- Tests live in the top-level `tests/` (not colocated). Function-based (no test classes). No `conftest.py`; each test constructs its own temp SQLite + WAV.
- SONARA is stubbed via `sonara_module=<FakeSonara>`; MERT / MuQ / CLAP / MAEST are stubbed with injected fake torch / laion_clap / huggingface modules. Do not add real-model calls to tests.
- Focused run: `python -m pytest tests/test_<name>.py --override-ini addopts=`.
- Embedding-source changes should be checked through the affected API,
  SET/Hybrid, evaluation, or classifier paths rather than relying only on an
  isolated unit test.
