# Agent Instructions

## Connected SONARA repository

This project consumes SONARA from a separate checkout:

- Downstream application: C:\projects\dj-track-similarity
- Upstream SONARA source: C:\projects\sonara

Before any SONARA operation:

1. Read C:\projects\sonara\AGENTS.md.
2. Inspect the Git status of both repositories.
3. Keep Git commands scoped to the intended repository.

By default:

- SONARA audits are fetch/inspection only.
- Do not overwrite or discard unrelated changes.
- Build release wheels outside both Git checkouts.
- Smoke-test wheels in an isolated environment.


## Source Of Truth

- `dj-track-similarity` is a local-first, enthusiast DJ-library workbench. Keep claims modest: model outputs are ranking signals for listening-led shortlisting, not objective truth or finished automatic DJ generation.
- Prefer executable sources over prose: `pyproject.toml`, `frontend/package.json`, `docs/dj-track-similarity/package.json`, tests, schemas, routes, and current source beat README/docs when they disagree.
- English is the source language for user-facing docs, with a maintained Russian mirror under `docs/dj-track-similarity/ru/`. The maintained public surface is `README.md` plus `docs/dj-track-similarity/`; the English entrypoint is `docs/dj-track-similarity/project-guide.md` and the Russian entrypoint is `docs/dj-track-similarity/ru/project-guide.md`.
- Project databases are stored in `C:\projects\dj-track-similarity\database`.
  Never use a real project database in automated tests.

## High-Value Map

- Backend/CLI/API live under `src/dj_track_similarity/`. Hot files by concern:
  - **Composition**: `cli.py` (Typer), `api.py` (`create_app`), `api_schemas.py`, `api_state.py` (`AppDatabaseState` + job managers), `api_routes_*.py`, `dependencies.py`, `runtime.py`, `job_runtime.py`, `logging_config.py`.
  - **Database**: `database.py` (`LibraryDatabase`), `db_connection.py`, `db_schema.py`, `db_ddl.py`, `db_structure.py`, `db_artifacts.py`, `db_evaluation_sidecar.py`, `db_tracks.py`, `db_analysis.py`, `db_analysis_candidates.py`, `db_storage.py`, `db_library_queries.py`, `db_search_fts.py`, `db_summary.py`, `db_evaluation.py`.
  - **Scanning + audio + tags**: `scanner.py`, `scan_jobs.py`, `audio_loader.py`, `media_preview.py`, `tags.py`, `wave_tags.py`, `genres.py`, `track_resolution.py`, `tempo_resolution.py`.
  - **Analysis orchestration**: `analysis_config.py`, `analysis_jobs.py`, `analysis_pipeline.py` (fixed order SONARA → ML → CLASSIFIERS), `analysis_queue.py`, `analysis_job_state.py`, `analysis_job_batch.py`, `analysis_model_runners.py`.
  - **Models**: `sonara_runtime.py`, `sonara_features.py`, `sonara_storage.py`, `sonara_similarity.py`, `sonara_similarity_scoring.py`, `embedding.py` (MERT/MuQ/CLAP adapters), `genres.py` (MAEST labels).
  - **Search + set + hybrid**: `search.py` (`SimilaritySearch`), `hybrid_search.py`, `hybrid_explanation.py`, `hybrid_transition.py`, `set_builder.py`, `set_sequence.py`, `transition_diagnostics.py`, `vector_index.py`, `ann_index.py`.
  - **Classifiers**: `classifier_jobs.py`, `classifier_manifest.py`, `classifier_production.py`, `classifier_scoring.py`.
  - **Evaluation subsystem**: `evaluation/` (`ablation`, `calibration`, `candidates`, `judged`, `labels`, `metrics`, `reports`, `risk_sweep`, `score_profile_optimizer`, `score_profiles`, `seed_sampling`, `source_profile`, `weighted_candidates`).
  - **Rhythm Lab bridge + misc**: `rhythm_lab_launcher.py`, `rhythm_lab_collections.py`, `reference_compare.py`, `exporter.py`.
- `frontend/` is the React + Vite + TypeScript UI. Root component tree in `frontend/src/App.tsx`; main panels in `LibraryPanel.tsx`, `TrackPanel.tsx`, `SearchPlaylistPanel.tsx`, `ReferenceComparePanel.tsx`, `ClapSearchTab.tsx`. Frontend tests use Node's built-in `node --test`, not Vitest. See `frontend/AGENTS.md`.
- `docs/dj-track-similarity/` is the VitePress source; `site/` is generated output. Style rules live in `.vale.ini`, `docs/dj-track-similarity/cspell.json`, and `docs/dj-track-similarity/.markdownlint.json`.
- Helper tools are separate safety domains, each with its own `AGENTS.md`: `tools/audio-doctor/`, `tools/audio-dedup/`, `tools/rhythm-lab/`.
- Runtime ports are fixed: backend `8765`, Vite `5173`, Rhythm Lab `8777`. Before starting one, check for an existing matching project process. Running `run_server.cmd` without arguments must prompt first for a database path with the shown default `C:\db\volumes.sqlite`, then prompt for local or LAN mode; pass the selected path to `dj-sim serve` only after both prompts complete. Explicit `run_server.cmd local ...` and `run_server.cmd lan ...` calls remain non-interactive and use only their supplied arguments. Keep argument forwarding through `scripts/run_server_launcher.py` as a list with `shell=False`; do not rebuild user-supplied paths into a `cmd.exe` command string.

## Architecture Sketch

- `create_app()` in `api.py` composes route modules and mounts the built `frontend/dist` at `/`. `AppDatabaseState` (`api_state.py`) owns `LibraryDatabase` plus job managers for scan, analysis, pipeline, classifier, audio-doctor, audio-dedup, and genre-tag work; a shared `AnalysisStageQueue` serialises SONARA/ML/CLASSIFIERS across UI and API.
- `AnalysisPipelineManager` fixes pipeline order to `("sonara", "ml", "classifiers")` (see `analysis_pipeline.py:PIPELINE_STAGE_ORDER`). Per-file failures are retained in status and do not halt the next stage; a fatal init error or cancellation does.
- CLI entry is `dj-sim = dj_track_similarity.cli:app`. Commands: `scan`, `relocate-library`, `analyze`, `analyze-classifiers`, `analyze-classifier`, `analyze-pipeline`, `doctor`, `text-search`, `migrate-database`, `serve`, plus `eval`, `classifier`, and `index` command groups.
- Central classes with heavy fan-in when editing: `LibraryDatabase`, `AppDatabaseState`, `AnalysisJobManager`, `ClassifierJobManager`, `AnalysisPipelineManager`, `SimilaritySearch`, `ClapEmbeddingAdapter`.

## SONARA Result Semantics

- Preserve SONARA scalar precision through database writes. Validate finite
  values and documented bounds, but do not round model or DSP outputs before
  storage; apply display precision only in the UI.
- SONARA tempo analysis uses the configured `70..180` BPM range. Store
  `detected_bpm` without rounding, render it with two decimal places, and do
  not expose `raw_bpm` in the metadata UI.
- The application passes `vocalness_model="bundled"`, so SONARA `vocalness`
  is stored as `vocal_probability`. Render it as a percentage because it is
  the bundled model's `P(vocal)`, but never describe it as the percentage of
  track duration containing vocals. Do not expose a duplicate `vocalness`
  field or derive a separate `instrumentalness` display.
- `mood_happy`, `mood_aggressive`, `mood_relaxed`, and `mood_sad` are
  independent heuristics, not classifier probabilities. Keep them in the
  `Mood` group with labels `Happy`, `Aggressive`, `Relaxed`, and `Sad`, and
  render them as `0.000`-style decimal scores rather than percentages.
- Dedicated SONARA Aggression is distinct from `mood_aggressive`. Store its
  rank, evidence support, forcefulness, harshness, tension, and rhythm without
  rounding. Render each as a three-decimal score without `%`; the rank is not
  a probability, and evidence support is not certainty.
- In the SONARA metadata UI, keep the model-backed groups immediately before
  `Vector summaries`, ordered as `Vocalness`, then `Aggression`.

## Safety Rules Agents Commonly Miss

- Treat source audio as user data. Scan, Refresh Tags, analysis, search, preview, reset, relocation preview, export, and classifier scoring must not modify audio files.
- The app's normal tag-write path is only `/api/tags/genres/apply` (route in `api_routes_tags_export.py`, writer in `tags.py`, WAV persist in `wave_tags.py`): write the stored MAEST-derived standard genre field and preserve title, artist, album, BPM, key, and other normal tags. WAV genre writes use Mutagen WAVE/ID3 and read back `TCON`; do not add custom RIFF repair here.
- Browser preview may transcode `.aif`/`.aiff` to a temporary WAV for streaming (`media_preview.py`), but must not rewrite or cache source audio.
- SQLite writes go through `LibraryDatabase` with path-scoped locking, WAL, and busy timeout. Relocation apply (`db_tracks.py`) updates stored `tracks.file_path` only; it never moves, copies, deletes, or retags audio.
- Database reset/clear is database-only and must require explicit UI confirmation where applicable. Destructive SQLite maintenance on a real DB needs a backup/copy first and should finish with integrity/orphan checks.
- Normal startup never changes an older database structure. Use only the explicit
  `dj-sim migrate-database --db <path>` command after reviewing its plan; apply
  requires the exact `MIGRATE DATABASE` confirmation and creates verified Core
  and Artifacts backups before changing either database.
- Audio Doctor is dry-run-first (`audio_doctor_jobs.py`). `--apply` may rewrite only prior `REPAIRABLE` findings, creates backups by default, verifies each result, and UI/API apply requires the exact `APPLY REPAIR` confirmation.
- Audio Dedup is report-only by default (`audio_dedup_jobs.py`). `--apply` requires exact `APPLY DELETE`, deletes only safe duplicate candidates inside `--root`, and removes SQLite rows only for files it actually deleted. MuQ can add configurable embedding evidence but never replaces the existing MERT+MAEST delete-safety corroboration. Do not run apply modes for routine verification.
- Rhythm Lab opens the main SQLite DB mostly read-only; labels, predictions, checkpoints, and artifacts stay under `tools/rhythm-lab/`. The explicit liked-track toggle is the narrow source-DB write path.
- Promoted classifier scoring (`classifier_scoring.py`) is database-only, scoped by `classifier_key`, and writes only that classifier's `classifier_scores`. Do not recompute or delete other classifier scores.
- Keep CLAP text-search scores separate from audio-to-audio CLAP signals used by SET/Hybrid/Audio Dedup. MuQ embeddings are supported by seed search, SET, Hybrid, Audio Dedup, and classifier inputs; do not mix MuQ with CLAP text scores.
- SET defaults to MERT/MAEST/MuQ/CLAP with raw weights `0.30/0.18/0.15/0.22` plus SONARA broad `0.30`, normalized over enabled signals. Hybrid defaults to MERT/MAEST/MuQ/SONARA/CLAP with equal normalized weights. Disabling a source removes it from eligibility and the weight map; never retain a disabled source at zero weight as a hidden readiness requirement.
- MuQ decodes and resamples through shared torchaudio only, at 24 kHz `float32`, with no half/bfloat/autocast/compile path (`embedding.py`). Do not import `librosa` into project source; it exists only as a locked transitive dependency in `uv.lock`.

## Tooling

### SQLite

- SQLite tools are intentionally absent from `PATH`. Resolve the toolkit from
  `$env:SQLITE_TOOLKIT_HOME`; if unavailable, use
  `C:\Utils\tools\sqlite-toolkit`.
- Before SQLite work, read the toolkit's `AGENTS.md`, select the smallest
  suitable included tool, and invoke it by explicit path.
- Use `sqlite3` for deterministic SQL, schema and index inspection, query
  plans, dumps, imports, exports, and integrity checks. Use `sqlite-utils` for
  concise structured exploration or conversion, Datasette for interactive
  browsing, `sqlite3_analyzer` for storage analysis, and `sqldiff` for database
  comparison.
- Start read-only when inspecting real data. Do not install another SQLite CLI
  unless the toolkit cannot perform the requested task.

## Development Workflow

- Keep edits scoped and preserve unrelated worktree changes. This repo may be dirty.
- Treat `pyproject.toml` as the current source for Python compatibility and
  update it when requested after focused compatibility checks. Frontend scripts
  are in `frontend/package.json`; docs scripts are in
  `docs/dj-track-similarity/package.json`.
- README examples should use `python ...` or `dj-sim ...`, not hard-coded `\.venv\Scripts\python.exe`; tool README files may show local helper invocations.
- Do not commit generated/local state: `*.sqlite`, `*.log`, `__pycache__/`, `.pytest_cache/`, virtualenvs, `frontend/node_modules/`, `frontend/dist`, `docs/dj-track-similarity/site/`, runtime logs, helper reports/backups, Rhythm Lab data/artifacts, or promoted classifier model files unless explicitly requested.

## Verification Shortcuts

- Optimize verification for the touched scope. Start with the smallest test,
  test file, package, or direct smoke check that can fail for the change, and
  widen only when shared interfaces, cross-module behavior, release risk, or a
  focused failure requires it. Do not run the full backend, frontend, docs, or
  repository test suite merely as a precaution.
- No CI is configured (`.github/workflows/` does not exist) and there is no pre-commit/husky/lint-staged setup. Verification is always local. There is no cross-package task runner; `run_server.cmd` is the only root launcher.
- Instruction-only edit: inspect the scoped `git diff` for every touched `AGENTS.md`, run `git diff --check -- <paths>`, and use `rg` sentinel terms for relevant safety topics. Do not run backend/frontend suites for instruction-only edits.
- Backend: `python -m pytest` from repo root only discovers `tests/` (per `[tool.pytest.ini_options] testpaths`, default `-q`). Focused runs: `python -m pytest <path> --override-ini addopts=`. No `conftest.py` exists; each test constructs its own temp SQLite/WAV and stubs SONARA/CLAP/MERT/MuQ/MAEST via `sonara_module=` / injected modules. Registered markers: `ml`, `slow`, `evaluation`.
- Frontend: from `frontend/`, run `npm run build`; add `npm run typecheck` (`tsc --noEmit --noUnusedLocals --noUnusedParameters`) or `npm test` (`node --test tests/*.test.mjs`) when the touched area warrants it. No ESLint/Biome config. Playwright is installed but no Playwright test files exist yet.
- Docs: from `docs/dj-track-similarity/`, run `npm run check` (strict Vale + VitePress build); run `npm run vale:sync` first after a fresh checkout or Vale package changes.
- Rhythm Lab: `python -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=`; include `tests\test_break_energy.py` for promoted classifier scoring boundaries.
- Audio Doctor: `python -m pytest scripts\tests\test_repair_audio_metadata.py --override-ini addopts=`.
- Audio Dedup: `python -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=`.
- Windows launcher: `python -m pytest scripts\tests\test_run_server_lan_script.py --override-ini addopts=`.
- SONARA changes should use stubbed helpers or small temp WAV fixtures, not the real music library.

## Runtime Dependencies

- Server startup requires `ffmpeg` on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG`; keep missing-ffmpeg errors actionable.
- TorchCodec-backed Windows decoding needs the shared FFmpeg build on `PATH`; the verified local build is under `C:\Utils\tools\ffmpeg\bin`.
- Manifest and lockfile versions describe the current tested environment, not
  permanent policy. When the user requests an update, select mutually
  compatible current versions, update manifests and lockfiles, and run focused
  compatibility checks. Do not reject an update solely because it changes a
  previously recorded package version.
- MuQ analysis uses shared decode and torchaudio resampling at `24_000 Hz`
  `float32`; project source does not use `librosa` for this path.
- Vale reads `.vale/styles` populated by `npm run vale:sync`; `vale.exe` is
  resolved from `VALE_EXE`, `PATH`, or `C:\Utils\tools\vale\vale.exe`.
