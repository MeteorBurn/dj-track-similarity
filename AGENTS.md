# Agent Instructions

## Project Snapshot

`dj-track-similarity` is a public personal/enthusiast project for local DJ
music-library analysis and track similarity. Keep public docs honest, practical,
and modest: this is not a polished commercial product or a research benchmark.

User-facing project documentation should be English unless the user asks
otherwise. The English documentation index is
`docs/dj-track-similarity/project-guide.md`; use its linked topic pages for full
CLI/API/script details instead of duplicating long references here. Russian
documentation lives under `docs/dj-track-similarity/ru/` and is updated only on
explicit request; keep routine documentation maintenance current in the English
version first.

## Project Documentation

Project documentation lives under `docs/dj-track-similarity/`, with the
canonical English source at the documentation root and the Russian localization
under `docs/dj-track-similarity/ru/`. Treat
`docs/dj-track-similarity/project-guide.md` as the English entrypoint, then
follow its links to the focused topic pages for installation, overview,
architecture, database, analysis models, analysis families, search/tag writing,
CLI, API, Rhythm Lab, development, and stable maintenance scripts.

Read the relevant page in `docs/dj-track-similarity/` before making changes to
documented behavior, public commands, API contracts, database fields, analysis
outputs, UI workflows, Rhythm Lab, or stable maintenance scripts. When such
behavior changes, update the matching page in `docs/dj-track-similarity/` in the
same change. Do not update `docs/superpowers/` as project documentation; it is
agent workflow material and should stay separate.

When any Markdown source under `docs/dj-track-similarity/` changes, rebuild the
static HTML documentation before finishing by running `npm run build` from
`docs/dj-track-similarity/`. The generated HTML lives in
`docs/dj-track-similarity/site/` and is served from the main UI documentation
button at `/docs/`.

The project is a Python backend/CLI plus a React/Vite frontend:

- `src/dj_track_similarity/`: database, scanning, analysis, classifiers,
  search, export, tags, API, and CLI.
- `frontend/`: React UI built with Vite and TypeScript.
- `tests/`: pytest coverage for backend/API/search/jobs/tags.
- `tools/rhythm-lab/`: auxiliary classifier labeling/training UI and CLI for
  user-created classifier profiles. It runs separately from
  `dj_track_similarity`, but stays in this repository as a helper project.
- `scripts/audio_repair/repair_audio_metadata.py`: standalone dry-run-first audio metadata
  diagnostic/repair helper.
- `scripts/audio_repair/`: repair helper script plus runtime
  state/log/report/backup workspace; commit only `repair_audio_metadata.py` and
  `.gitkeep`.
- `scripts/audio_dedup/`: duplicate-audio candidate helper. By default it reads
  the project SQLite database and writes ignored reports only; `--apply` is the
  explicit destructive cleanup mode.

This workspace may not always be a Git repository. Do not assume commits,
branches, or history are available.

## Safety Invariants

- Treat real audio files as user data. Scanning, RefreshTags, analysis, search,
  preview, reset, clear, relocation preview, and export must not modify audio.
- Browser preview may transcode `.aif`/`.aiff` to WAV for `/media/{track_id}`;
  this is read-only streaming and must not rewrite/cache source audio.
- Library relocation updates only stored `tracks.path` values in SQLite. It must
  be previewable, reject missing target files/conflicts on apply, preserve track
  IDs and all analysis/tag metadata, and never move/copy/delete/retag audio.
- `/api/tags/genres/apply` is the explicit app-level standard-tag write path:
  overwrite only the standard genre field from stored MAEST labels, preserving
  title/artist/album/BPM/key and other normal tags.
- Genre writes are upserts: replace any existing genre values with one normalized
  `;`-separated MAEST genre string. Use `TCON` for MP3/WAV/AIFF ID3, `GENRE`
  for FLAC/Vorbis-style tags, and `\xa9gen` for MP4/M4A/ALAC.
- WAV genre writing must use Mutagen WAVE/ID3 handling and read back `TCON`.
  Do not add custom RIFF repair/validation to the app path; failed WAV writes
  should fail that track and let the batch continue.
- `scripts/audio_repair/repair_audio_metadata.py --apply` is separate and may rewrite only
  files it reports as `REPAIRABLE`; dry-run must not write/copy audio, apply is
  sequential, and full-file backups are created by default.
- `scripts/audio_repair/repair_audio_metadata.py --db` opens the selected
  SQLite library database read-only, reads existing `tracks.path` values, and
  may remap stored roots with `--db-root` plus `--file-root` before checking the
  filesystem. Missing remapped files are skipped, not repaired.
- `scripts/audio_dedup/audio_dedup.py` is report-only by default. It opens
  SQLite read-only and writes JSON/XLSX/log reports under
  `scripts/audio_dedup/reports/` by default. With explicit `--apply`, it must
  prompt for exact confirmation, delete only safe duplicate candidates inside
  the selected `--root`, and remove SQLite rows only for tracks whose files were
  successfully deleted. Do not invoke the script with `--apply` in tests or
  routine verification runs.
- Keep SQLite writes routed through `LibraryDatabase`, with the shared
  path-scoped write lock, WAL, and busy timeout so scan/RefreshTags/Sonara/
  MAEST/MERT/CLAP/reset writes queue safely.
- Promoted classifier scoring is database-only. It must read existing SONARA
  features plus MERT and MAEST embeddings, then write only
  `track_classifier_scores`; it must not decode audio or modify audio files.
- Rhythm Lab must never write to source audio files. It opens the main project
  SQLite database read-only for browsing, analysis metadata, training inputs,
  and preview. Its only source-database write path is the explicit liked-track
  toggle, which updates `track_likes` through `LibraryDatabase`; lab labels,
  predictions, and checkpoints stay under `tools/rhythm-lab/data/`.
- Treat `dj-track-similarity.sqlite` as local user state. Tests must use
  temporary databases (`tmp_path` or explicit `--db`).
- Do not commit generated local artifacts: `*.sqlite`, `*.log`, `__pycache__/`,
  `.pytest_cache/`, `frontend/node_modules/`, transient temp folders, or
  generated `scripts/audio_repair/` contents except `repair_audio_metadata.py`.
  Rhythm Lab generated state and
  training artifacts under `tools/rhythm-lab/data/` and
  `tools/rhythm-lab/artifacts/*/` must also stay out of git except `.gitkeep`.
  Generated duplicate-audio reports under `scripts/audio_dedup/reports/` must
  also stay out of git except `.gitkeep`.
- Server startup requires `ffmpeg` on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG`;
  keep missing-ffmpeg errors clear and actionable.
- The verified Windows CUDA ML stack is PyTorch `2.11.0`, Torchaudio
  `2.11.0`, Torchvision `0.26.0`, TorchCodec `0.13.0`, CUDA wheel index
  `cu130`, and `numpy>=1.26,<2.0`. Keep these synchronized unless a deliberate
  dependency upgrade is being tested.
- TorchCodec-backed Torchaudio decoding on Windows requires an FFmpeg shared
  build with DLLs on `PATH`; the verified portable build is GyanD
  `ffmpeg 8.1.1-full_build-shared` under `C:\Utils\tools\ffmpeg\bin`.

## Analysis And UI Contracts

- Mutagen scan/RefreshTags read only the fixed human-relevant whitelist and
  update SQLite only. Stored metadata must be JSON-safe.
- Sonara writes only SQLite metadata (`sonara_features`, `sonara_model`) plus
  derived working BPM/key/duration/energy fields. Sonara BPM/key are analyzed
  values, not copied file tags.
- Keep Sonara playlist storage focused on the grouped UI contract. Do not store
  placeholder `unavailable` rows, helper diagnostics, or `chord_sequence`.
- Keep Sonara database keys canonical (`*_mean` stays in SQLite). Friendly UI
  labels may omit `mean`, but do not rename stored keys or derive Camelot data.
- Shared audio loading is native-first standard decoding: Sonara starts with
  `sonara.analyze_file`; Sonara fallback, MAEST, MERT, and CLAP use the shared
  loader (`torchaudio` with TorchCodec when provided, Python `wave` for WAV,
  then `ffmpeg`).
- MAEST analysis writes only SQLite metadata and must use the three-window
  30-second policy with direct `model(audio_batch, melspectrogram_input=False)`
  logits, not `predict_labels()` for batch work.
- MERT/CLAP/MAEST use one selected device plus inference batching. `auto` picks
  CUDA when PyTorch sees a GPU, otherwise CPU; explicit `cuda` must error if
  unavailable.
- In the UI, `Analyze limit = 0` means whole library. Positive limits count
  missing results for the selected analysis family.
- Search UI stays split into SONARA, MERT, and CLAP tabs. SONARA sends custom
  mixer/modifiers to `/api/search/sonara`; MERT seed search uses `/api/search`;
  CLAP text search uses `/api/search/text` and requires `clap` embeddings.
- The search/listening panel also has a CLASS tab for classifier controls. It
  discovers promoted local classifier profiles from
  `models/classifiers/*/model.json`. Keep generated classifier assets
  (`model.joblib`, `model.json`) out of git.
- Promoted classifier scores are stored in `track_classifier_scores` with their
  profile `classifier_key`. The user-facing score is the promoted model's
  positive-label probability stored as `score`; per-label probabilities remain
  in `probabilities_json`.
- Rhythm Lab's lab DB uses `classifier_labels`, `classifier_predictions`, and
  `classifier_training_checkpoints`, scoped by `classifier_key`. Do not
  reintroduce `rhythm_*` lab tables except in a one-way migration that removes
  them after data is copied.
- Rhythm Lab profiles support `profile_type = "binary"` and
  `profile_type = "multiclass"`. Binary profiles use exactly one positive and
  one negative training label plus optional review labels. Multiclass profiles
  use `class` labels only, can have arbitrary user-defined classes, and one
  track can hold only one current label for the active profile.
- Rhythm Lab training artifacts are classifier-scoped under
  `tools/rhythm-lab/artifacts/<artifact-prefix>/`. Promoted runtime models for
  the main app stay separate under `models/classifiers/<artifact-prefix>/`.
- Rhythm Lab training benchmarks `sonara`, `mert`, `maest`, and `combined`.
  `combined` requires existing SONARA features plus MERT and MAEST embeddings;
  do not remove SONARA from the combined classifier path. Rhythm Lab summary UI
  should expose SONARA, MAEST, and MERT coverage counters.
- Keep library browsing scalable: `/api/tracks` remains server-side
  paginated/searchable with lightweight rows, `/api/library/summary` provides
  counters, and full metadata loads via `/api/tracks/{id}` only on dialog open.
- Reset controls are database-only per analysis family. Database clear deletes
  SQLite records only and must require explicit UI confirmation.
- Metadata dialog must keep Mutagen tags, SONARA features, and MAEST genres
  visually separate; preserve the current display order and source boundaries.
  Classifier scores may be shown as their own block below SONARA features.
- Keep hover help on user-editable controls with purpose, type/format, and range.

## Common Commands

For the CLI, API, and maintenance script documentation index, see
`docs/dj-track-similarity/project-guide.md` and its linked topic pages.

```powershell
python -m pip install -e ".[dev]"
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
pytest
dj-sim serve --host 127.0.0.1 --port 8765
dj-sim serve --host 127.0.0.1 --port 8765 --log-track-events
scripts\run_server.cmd
cd frontend
npm run build
npm run dev
cd docs\dj-track-similarity
npm run build
```

Useful focused CLI examples:

```powershell
dj-sim scan <path-to-music> --db .\data\library.sqlite
dj-sim analyze-sonara --limit 3 --batch-size 4 --db .\data\library.sqlite
dj-sim analyze --adapter mert --device cpu --batch-size 2 --limit 3 --db .\data\library.sqlite
dj-sim analyze --adapter clap --device cpu --batch-size 2 --limit 3 --db .\data\library.sqlite
dj-sim analyze-genres --device cpu --batch-size 2 --limit 3 --db .\data\library.sqlite
dj-sim analyze-classifier live_instrumentation --limit 3 --db .\data\library.sqlite
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 5 --db .\data\library.sqlite
dj-sim relocate-library .\music-old .\music-new --db .\data\library.sqlite
dj-sim relocate-library .\music-old .\music-new --apply --db .\data\library.sqlite
dj-sim doctor
```

Focused repair-script test when only `scripts/audio_repair/repair_audio_metadata.py` changes:

```powershell
.\.venv\Scripts\python.exe -m pytest scripts\tests\test_repair_audio_metadata.py --override-ini addopts=
```

Focused duplicate-report test when only `scripts/audio_dedup/audio_dedup.py`
changes:

```powershell
.\.venv\Scripts\python.exe -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=
```

## Code Map

- `src/dj_track_similarity/database.py`: SQLite schema access, path-scoped write
  serialization, track rows, summaries, embeddings, analysis metadata,
  relocation, resets, and clear.
- `src/dj_track_similarity/scanner.py`: supported audio discovery and Mutagen
  metadata extraction.
- `src/dj_track_similarity/audio_loader.py`: shared standard decoder path.
- `src/dj_track_similarity/sonara_features.py` / `sonara_jobs.py`: Sonara
  feature extraction and jobs.
- `src/dj_track_similarity/genres.py` / `genre_jobs.py`: MAEST genre analysis.
- `src/dj_track_similarity/embedding.py` / `analysis_jobs.py`: MERT/CLAP
  embeddings and jobs.
- `src/dj_track_similarity/classifier_scoring.py` / `classifier_jobs.py`:
  promoted classifier scoring and cancellable classifier jobs.
- `tools/rhythm-lab/rhythm_lab/`: separate classifier lab package for labels,
  predictions, feature matrices, training artifacts, and the standalone lab UI.
- `scripts/audio_dedup/audio_dedup.py`: duplicate-audio candidate reporting and
  explicit confirmed `--apply` cleanup from an existing library database.
- `src/dj_track_similarity/search.py`, `sonara_similarity.py`: embedding and
  Sonara search.
- `src/dj_track_similarity/tags.py`, `wave_tags.py`: MAEST-to-standard-genre
  writes and guarded WAV handling.
- `src/dj_track_similarity/api.py`, `cli.py`: FastAPI and Typer entrypoints.
- `frontend/src/api.ts`: frontend API contract mirror.
- `frontend/src/App.tsx` and panels/dialogs: main UI surface. Avoid broad
  refactors unless the task is specifically frontend-structure work.

## Development Conventions

- Keep Python compatible with 3.10+.
- Prefer small, scoped edits that follow existing module patterns.
- Keep FastAPI request/response shapes aligned with `frontend/src/api.ts`.
- If changing scan/analysis job state, update backend tests and frontend
  polling/display logic.
- If changing Mutagen tags, Sonara features, MAEST job state, classifier jobs,
  audio decoding, search, library browsing, relocation, analysis controls,
  SQLite writes, UI controls, custom tags, or standard genre writes, update the
  corresponding focused tests, frontend/API surfaces, and
  `docs/dj-track-similarity/` documentation pages.
- Prefer deterministic test data and test-local stub adapters over real audio
  analysis in automated tests.
- Do not add legacy compatibility layers, fallback paths, or parallel old/new
  behavior unless the user explicitly asks for compatibility. Prefer migrating
  code, docs, tests, local DB schemas, and local artifact layout in one pass.
- Before starting any local UI/server process, check whether the intended port
  already has a listener and whether a matching project process is already
  running. Keep one instance per fixed project port: main backend `8765`,
  frontend Vite `5173`, and Rhythm Lab `8777`.

## Verification Expectations

- Backend changes: run focused pytest for the touched behavior; use full
  `pytest` for broad/shared changes.
- Frontend changes: run `npm run build` in `frontend/`.
- API contract changes: exercise the affected endpoint through tests or a local
  server.
- CLI behavior changes: run the specific `dj-sim ...` command with a temporary
  database when practical.
- Rhythm Lab changes: run
  `.\.venv\Scripts\python.exe -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=`
  and, for promoted classifier scoring boundaries, include
  `tests\test_break_energy.py`.
- Audio dedup report changes: run
  `.\.venv\Scripts\python.exe -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=`.
- Relocation changes: verify dry-run does not modify paths, apply preserves IDs
  and analysis state, and conflicts/missing files block apply.
- Sonara changes: prefer stubbed helpers or small temp WAV fixtures; never rely
  on a real user music library in automated tests.
