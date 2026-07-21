# Agent Instructions

## Source Of Truth

- `dj-track-similarity` is a local-first, enthusiast DJ-library workbench. Keep claims modest: model outputs are ranking signals for listening-led shortlisting, not objective truth or finished automatic DJ generation.
- Prefer executable sources over prose: `pyproject.toml`, `frontend/package.json`, `docs/dj-track-similarity/package.json`, tests, schemas, routes, and current source beat README/docs when they disagree.
- User-facing docs are English. The maintained public surface is `README.md` plus `docs/dj-track-similarity/`; the docs entrypoint is `docs/dj-track-similarity/project-guide.md`.
- For manual checks against the real library, use `C:\db\abstracted.sqlite` unless the user gives another DB. Never use the real library in automated tests.

## High-Value Map

- Backend/CLI/API live under `src/dj_track_similarity/`. Hot files: `cli.py`, `api.py`, `api_schemas.py`, `api_routes_*.py`, `database.py`, `db_*`, `scanner.py`, `audio_loader.py`, `analysis_jobs.py`, `sonara_features.py`, `genres.py`, `embedding.py`, `search.py`, `sonara_similarity.py`, `set_builder.py`, `tags.py`, `wave_tags.py`, `media_preview.py`, `classifier_scoring.py`.
- `frontend/` is the React/Vite UI. Keep API shapes aligned with `frontend/src/api.ts`; `frontend/dist` is generated unless explicitly requested.
- `docs/dj-track-similarity/` is the VitePress source; `site/` is generated output.
- Helper tools are separate safety domains: `tools/audio-doctor/`, `tools/audio-dedup/`, and `tools/rhythm-lab/`.
- Runtime ports are fixed: backend `8765`, Vite `5173`, Rhythm Lab `8777`. Before starting one, check for an existing matching project process. For this workspace, prefer `run_server.cmd lan --db C:\db\abstracted.sqlite` when launching the main app.

## Safety Rules Agents Commonly Miss

- Treat source audio as user data. Scan, Refresh Tags, analysis, search, preview, reset, relocation preview, export, and classifier scoring must not modify audio files.
- The app's normal tag-write path is only `/api/tags/genres/apply`: write the stored MAEST-derived standard genre field and preserve title, artist, album, BPM, key, and other normal tags. WAV genre writes use Mutagen WAVE/ID3 and read back `TCON`; do not add custom RIFF repair here.
- Browser preview may transcode `.aif`/`.aiff` to a temporary WAV for streaming, but must not rewrite or cache source audio.
- SQLite writes go through `LibraryDatabase` with path-scoped locking, WAL, and busy timeout. Relocation apply updates stored `tracks.path` only; it never moves, copies, deletes, or retags audio.
- Database reset/clear is database-only and must require explicit UI confirmation where applicable. Destructive SQLite maintenance on a real DB needs a backup/copy first and should finish with integrity/orphan checks.
- Audio Doctor is dry-run-first. `--apply` may rewrite only prior `REPAIRABLE` findings, creates backups by default, and UI/API apply requires exact `APPLY REPAIR`.
- Audio Dedup is report-only by default. `--apply` requires exact `APPLY DELETE`, deletes only safe duplicate candidates inside `--root`, and removes SQLite rows only for files it actually deleted. Do not run apply modes for routine verification.
- Rhythm Lab opens the main SQLite DB mostly read-only; labels, predictions, checkpoints, and artifacts stay under `tools/rhythm-lab/`. The explicit liked-track toggle is the narrow source-DB write path.
- Promoted classifier scoring is database-only, scoped by `classifier_key`, and writes only that classifier's `track_classifier_scores`. Do not recompute or delete other classifier scores.
- Keep CLAP text-search scores separate from audio-to-audio CLAP signals used by SET/Hybrid/Audio Dedup. MuQ is stored for future workflows and is not a current search/SET/classifier input unless a future task explicitly changes that contract.
- Any SONARA update requires a complete SONARA reanalysis. This includes a package/version/build update and any change to the decoder, execution path, analysis mode, sample rate, BPM range, requested features, bundled model, schema, provenance, signature, or project feature revision. Never preserve compatibility by comparing, adapting, translating, or mixing results from the old and new SONARA contracts.
- Before writing results under a new SONARA contract, back up the real database and clear/invalidate all prior SONARA Core, Timeline, Representations, and SONARA-derived classifier data so SET, Hybrid, search, diagnostics, LAB, and classifiers cannot consume a mixed population. Then run a full-library SONARA reanalysis from a clean SONARA state; do not treat a pilot or partial refresh as migration completion.
- After the full SONARA reanalysis, retrain, re-promote, and re-score every classifier whose feature set uses SONARA. MERT-, MAEST-, MuQ-, or CLAP-only analysis and models remain independent unless their own contract changed.

## Development Workflow

- Keep edits scoped and preserve unrelated worktree changes. This repo may be dirty.
- Keep Python compatible with `>=3.10`. Project install/test metadata is in `pyproject.toml`; frontend scripts are in `frontend/package.json`; docs scripts are in `docs/dj-track-similarity/package.json`.
- If changing FastAPI request/response contracts, update backend schemas/routes and `frontend/src/api.ts` together.
- If changing scan/analysis jobs, audio decoding, tags, search, SET, classifier scoring, relocation, UI workflows, helper tools, safety rules, setup, commands, or verification behavior, update focused tests and the relevant `README.md`/`docs/dj-track-similarity/` pages in the same pass. If no docs change is needed, say why in the final response.
- README examples should use `python ...` or `dj-sim ...`, not hard-coded `\.venv\Scripts\python.exe`; tool README files may show local helper invocations.
- Do not commit generated/local state: `*.sqlite`, `*.log`, `__pycache__/`, `.pytest_cache/`, virtualenvs, `frontend/node_modules/`, `frontend/dist`, `docs/dj-track-similarity/site/`, runtime logs, helper reports/backups, Rhythm Lab data/artifacts, or promoted classifier model files unless explicitly requested.

## Verification Shortcuts

- Instruction-only edit: `git diff -- AGENTS.md`, `git diff --check -- AGENTS.md`, then `rg` sentinel terms for safety topics. Do not run backend/frontend suites for instruction-only edits.
- Backend: run focused `python -m pytest ... --override-ini addopts=` for touched behavior; use full `python -m pytest` for broad/shared changes.
- Frontend: from `frontend/`, run `npm run build`; add `npm run typecheck` or `npm test` when the touched area warrants it.
- Docs: from `docs/dj-track-similarity/`, run `npm run check`; run `npm run vale:sync` first after a fresh checkout or Vale package changes.
- Rhythm Lab: `python -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=`; include `tests\test_break_energy.py` for promoted classifier scoring boundaries.
- Audio Doctor: `python -m pytest scripts\tests\test_repair_audio_metadata.py --override-ini addopts=`.
- Audio Dedup: `python -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=`.
- SONARA changes should use stubbed helpers or small temp WAV fixtures, not the real music library.

## Runtime Dependencies

- Server startup requires `ffmpeg` on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG`; keep missing-ffmpeg errors actionable.
- TorchCodec-backed Windows decoding needs the shared FFmpeg build on `PATH`; the verified local build is under `C:\Utils\tools\ffmpeg\bin`.
- Keep the PyTorch-family ML stack synchronized unless deliberately upgrading: PyTorch `2.11.0`, Torchaudio `2.11.0`, Torchvision `0.26.0`, TorchCodec `0.13.0`, CUDA wheel index `cu130`, and `numpy>=1.26,<2.0`.
- MuQ is optional via `muq==0.1.0`; project code must not import/use `librosa` for MuQ analysis. Use shared decode and torchaudio resampling; keep MuQ audio at `24_000 Hz` `float32` with no half/bfloat/autocast/compile path.
