# Agent Instructions

## Source Of Truth

- `dj-track-similarity` is a local-first, enthusiast DJ-library workbench. Keep claims modest: model outputs are ranking signals for listening-led shortlisting, not objective truth or finished automatic DJ generation.
- Prefer executable sources over prose: `pyproject.toml`, `frontend/package.json`, `docs/dj-track-similarity/package.json`, tests, schemas, routes, and current source beat README/docs when they disagree.
- English is the source language for user-facing docs, with a maintained Russian mirror under `docs/dj-track-similarity/ru/`. The maintained public surface is `README.md` plus `docs/dj-track-similarity/`; the English entrypoint is `docs/dj-track-similarity/project-guide.md` and the Russian entrypoint is `docs/dj-track-similarity/ru/project-guide.md`.
- For manual checks against the real library, use `C:\db\abstracted.sqlite` unless the user gives another DB. Never use the real library in automated tests.

## High-Value Map

- Backend/CLI/API live under `src/dj_track_similarity/` (~78 modules). Hot files by concern:
  - **Composition**: `cli.py` (Typer), `api.py` (`create_app`), `api_schemas.py`, `api_state.py` (`AppDatabaseState` + job managers), `api_routes_*.py`, `dependencies.py`, `runtime.py`, `job_runtime.py`, `logging_config.py`.
  - **Database**: `database.py` (`LibraryDatabase`), `db_connection.py`, `db_schema.py`, `db_tracks.py`, `db_analysis.py`, `db_analysis_candidates.py`, `db_storage.py`, `db_library_queries.py`, `db_search_fts.py`, `db_summary.py`, `db_evaluation.py`, `db_repository_utils.py`.
  - **Scanning + audio + tags**: `scanner.py`, `scan_jobs.py`, `audio_loader.py`, `media_preview.py`, `tags.py`, `wave_tags.py`, `genres.py`, `metadata_payload.py`, `track_resolution.py`, `tempo_resolution.py`.
  - **Analysis orchestration**: `analysis_config.py`, `analysis_jobs.py`, `analysis_pipeline.py` (fixed order SONARA → ML → CLASSIFIERS), `analysis_queue.py`, `analysis_job_state.py`, `analysis_job_batch.py`, `analysis_model_runners.py`.
  - **Models**: `sonara_contract.py` (safety-critical signature/version pin), `sonara_features.py`, `sonara_storage.py`, `sonara_similarity.py`, `sonara_similarity_scoring.py`, `embedding.py` (MERT/MuQ/CLAP adapters), `genres.py` (MAEST labels).
  - **Search + set + hybrid**: `search.py` (`SimilaritySearch`), `hybrid_search.py`, `hybrid_explanation.py`, `hybrid_transition.py`, `set_builder.py`, `set_sequence.py`, `transition_diagnostics.py`, `vector_index.py`, `ann_index.py`.
  - **Classifiers**: `classifier_jobs.py`, `classifier_manifest.py` (`CLASSIFIER_MANIFEST_VERSION = 2`), `classifier_production.py`, `classifier_scoring.py`.
  - **Evaluation subsystem**: `evaluation/` (`ablation`, `calibration`, `candidates`, `judged`, `labels`, `metrics`, `reports`, `risk_sweep`, `score_profile_optimizer`, `score_profiles`, `seed_sampling`, `source_profile`, `weighted_candidates`).
  - **Rhythm Lab bridge + misc**: `rhythm_lab_launcher.py`, `rhythm_lab_collections.py`, `reference_compare.py`, `exporter.py`.
- `frontend/` is the React 19 + Vite 7 + TypeScript 5.9 UI. Backend contracts stay aligned via `frontend/src/api.ts`; `frontend/dist` is generated unless explicitly requested. Root component tree in `frontend/src/App.tsx`; main panels in `LibraryPanel.tsx`, `TrackPanel.tsx`, `SearchPlaylistPanel.tsx`, `ReferenceComparePanel.tsx`, `ClapSearchTab.tsx`. Frontend tests use Node's built-in `node --test`, not Vitest. See `frontend/AGENTS.md`.
- `docs/dj-track-similarity/` is the VitePress source; `site/` is generated output. Style rules live in `.vale.ini`, `docs/dj-track-similarity/cspell.json`, and `docs/dj-track-similarity/.markdownlint.json`.
- Helper tools are separate safety domains, each with its own `AGENTS.md`: `tools/audio-doctor/`, `tools/audio-dedup/`, `tools/rhythm-lab/`.
- Runtime ports are fixed: backend `8765`, Vite `5173`, Rhythm Lab `8777`. Before starting one, check for an existing matching project process. For this workspace, prefer `run_server.cmd lan --db C:\db\abstracted.sqlite` when launching the main app.

## Architecture Sketch

- `create_app()` in `api.py` composes route modules and mounts the built `frontend/dist` at `/`. `AppDatabaseState` (`api_state.py`) owns `LibraryDatabase` plus job managers for scan, analysis, pipeline, classifier, audio-doctor, audio-dedup, and genre-tag work; a shared `AnalysisStageQueue` serialises SONARA/ML/CLASSIFIERS across UI and API.
- `AnalysisPipelineManager` fixes pipeline order to `("sonara", "ml", "classifiers")` (see `analysis_pipeline.py:PIPELINE_STAGE_ORDER`). Per-file failures are retained in status and do not halt the next stage; a fatal init error or cancellation does.
- CLI entry is `dj-sim = dj_track_similarity.cli:app`. Commands: `scan`, `relocate-library`, `analyze`, `analyze-classifiers`, `analyze-classifier`, `analyze-pipeline`, `doctor`, `text-search`, `serve`.
- Central classes with heavy fan-in when editing: `LibraryDatabase`, `AppDatabaseState`, `AnalysisJobManager`, `ClassifierJobManager`, `AnalysisPipelineManager`, `SimilaritySearch`, `ClapEmbeddingAdapter`.

## Safety Rules Agents Commonly Miss

- Treat source audio as user data. Scan, Refresh Tags, analysis, search, preview, reset, relocation preview, export, and classifier scoring must not modify audio files.
- The app's normal tag-write path is only `/api/tags/genres/apply` (route in `api_routes_tags_export.py`, writer in `tags.py`, WAV persist in `wave_tags.py`): write the stored MAEST-derived standard genre field and preserve title, artist, album, BPM, key, and other normal tags. WAV genre writes use Mutagen WAVE/ID3 and read back `TCON`; do not add custom RIFF repair here.
- Browser preview may transcode `.aif`/`.aiff` to a temporary WAV for streaming (`media_preview.py`), but must not rewrite or cache source audio.
- SQLite writes go through `LibraryDatabase` with path-scoped locking, WAL, and busy timeout. Relocation apply (`db_tracks.py`) updates stored `tracks.path` only; it never moves, copies, deletes, or retags audio.
- Database reset/clear is database-only and must require explicit UI confirmation where applicable. Destructive SQLite maintenance on a real DB needs a backup/copy first and should finish with integrity/orphan checks.
- Audio Doctor is dry-run-first (`audio_doctor_jobs.py`). `--apply` may rewrite only prior `REPAIRABLE` findings, creates backups by default, verifies each result, and UI/API apply requires the exact `APPLY REPAIR` confirmation.
- Audio Dedup is report-only by default (`audio_dedup_jobs.py`). `--apply` requires exact `APPLY DELETE`, deletes only safe duplicate candidates inside `--root`, and removes SQLite rows only for files it actually deleted. Do not run apply modes for routine verification.
- Rhythm Lab opens the main SQLite DB mostly read-only; labels, predictions, checkpoints, and artifacts stay under `tools/rhythm-lab/`. The explicit liked-track toggle is the narrow source-DB write path.
- Promoted classifier scoring (`classifier_scoring.py`) is database-only, scoped by `classifier_key`, and writes only that classifier's `track_classifier_scores`. Do not recompute or delete other classifier scores. The current manifest format is `CLASSIFIER_MANIFEST_VERSION = 2` (`classifier_manifest.py`); each track must match the manifest signature exactly before scoring, and mismatched artifacts are blocked with a retrain/promote message.
- Keep CLAP text-search scores separate from audio-to-audio CLAP signals used by SET/Hybrid/Audio Dedup. MuQ is stored for future workflows and is not a current search/SET/classifier input unless a future task explicitly changes that contract.
- Any SONARA update requires a complete SONARA reanalysis. This includes a package/version/build update and any change to the decoder, execution path, analysis mode, sample rate, BPM range, requested features, bundled model, schema, provenance, signature, or project feature revision. The current pinned contract lives in `sonara_contract.py`: SONARA `0.2.9`, schema `4`, mode `playlist`, sample rate `22050`, BPM range `70..180`, feature revision `5`, decoder `sonara-symphonia`, execution path `analyze_batch`. Never preserve compatibility by comparing, adapting, translating, or mixing results from the old and new SONARA contracts.
- Before writing results under a new SONARA contract, back up the real database and clear/invalidate all prior SONARA Core, Timeline, Representations, and SONARA-derived classifier data so SET, Hybrid, search, diagnostics, LAB, and classifiers cannot consume a mixed population. Then run a full-library SONARA reanalysis from a clean SONARA state; do not treat a pilot or partial refresh as migration completion.
- After the full SONARA reanalysis, retrain, re-promote, and re-score every classifier whose feature set uses SONARA. MERT-, MAEST-, MuQ-, or CLAP-only analysis and models remain independent unless their own contract changed.
- MuQ decodes and resamples through shared torchaudio only, at 24 kHz `float32`, with no half/bfloat/autocast/compile path (`embedding.py`). Do not import `librosa` into project source; it exists only as a locked transitive dependency in `uv.lock`.

## Development Workflow

- Keep edits scoped and preserve unrelated worktree changes. This repo may be dirty.
- Keep Python compatible with `>=3.10`. Project install/test metadata is in `pyproject.toml`; frontend scripts are in `frontend/package.json`; docs scripts are in `docs/dj-track-similarity/package.json`.
- If changing FastAPI request/response contracts, update backend schemas/routes and `frontend/src/api.ts` together.
- If changing scan/analysis jobs, audio decoding, tags, search, SET, classifier scoring, relocation, UI workflows, helper tools, safety rules, setup, commands, or verification behavior, update focused tests and the relevant `README.md`/`docs/dj-track-similarity/` pages in the same pass. If no docs change is needed, say why in the final response.
- When an English VitePress page changes, update its matching Russian page in `docs/dj-track-similarity/ru/`. Keep commands, code fences, links, API/schema names, and other technical identifiers aligned; `npm run check:locales` enforces mirror coverage and technical parity.
- README examples should use `python ...` or `dj-sim ...`, not hard-coded `\.venv\Scripts\python.exe`; tool README files may show local helper invocations.
- Do not commit generated/local state: `*.sqlite`, `*.log`, `__pycache__/`, `.pytest_cache/`, virtualenvs, `frontend/node_modules/`, `frontend/dist`, `docs/dj-track-similarity/site/`, runtime logs, helper reports/backups, Rhythm Lab data/artifacts, or promoted classifier model files unless explicitly requested.

## Verification Shortcuts

- No CI is configured (`.github/workflows/` does not exist) and there is no pre-commit/husky/lint-staged setup. Verification is always local. There is no cross-package task runner; `run_server.cmd` is the only root launcher.
- Instruction-only edit: `git diff -- AGENTS.md`, `git diff --check -- AGENTS.md`, then `rg` sentinel terms for safety topics. Do not run backend/frontend suites for instruction-only edits.
- Backend: `python -m pytest` from repo root only discovers `tests/` (per `[tool.pytest.ini_options] testpaths`, default `-q`). Focused runs: `python -m pytest <path> --override-ini addopts=`. No `conftest.py` exists; each test constructs its own temp SQLite/WAV and stubs SONARA/CLAP/MERT/MuQ/MAEST via `sonara_module=` / injected modules. Registered markers: `ml`, `slow`, `evaluation`.
- Frontend: from `frontend/`, run `npm run build`; add `npm run typecheck` (`tsc --noEmit --noUnusedLocals --noUnusedParameters`) or `npm test` (`node --test tests/*.test.mjs`) when the touched area warrants it. No ESLint/Biome config. Playwright is installed but no Playwright test files exist yet.
- Docs: from `docs/dj-track-similarity/`, run `npm run check` (strict Vale + VitePress build); run `npm run vale:sync` first after a fresh checkout or Vale package changes.
- Rhythm Lab: `python -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=`; include `tests\test_break_energy.py` for promoted classifier scoring boundaries.
- Audio Doctor: `python -m pytest scripts\tests\test_repair_audio_metadata.py --override-ini addopts=`.
- Audio Dedup: `python -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=`.
- SONARA changes should use stubbed helpers or small temp WAV fixtures, not the real music library.

## Runtime Dependencies

- Server startup requires `ffmpeg` on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG`; keep missing-ffmpeg errors actionable.
- TorchCodec-backed Windows decoding needs the shared FFmpeg build on `PATH`; the verified local build is under `C:\Utils\tools\ffmpeg\bin`.
- Keep the PyTorch-family ML stack synchronized unless deliberately upgrading: PyTorch `2.11.0`, Torchaudio `2.11.0`, Torchvision `0.26.0`, TorchCodec `0.13.0`, CUDA wheel index `cu130`, and `numpy>=1.26,<2.0`.
- MuQ is optional via `muq==0.1.0`; project code must not import/use `librosa` for MuQ analysis. Use shared decode and torchaudio resampling; keep MuQ audio at `24_000 Hz` `float32` with no half/bfloat/autocast/compile path.
- Frontend pins (`frontend/package.json`): React `19.2.3`, React DOM `19.2.3`, Vite `7.2.7`, TypeScript `5.9.3`, `@vitejs/plugin-react` `5.1.1`, Playwright `1.61.1`.
- Docs pins (`docs/dj-track-similarity/package.json`): VitePress `1.6.4`. Vale reads `.vale/styles` populated by `npm run vale:sync`; `vale.exe` is resolved from `VALE_EXE`, `PATH`, or `C:\Utils\tools\vale\vale.exe`.
