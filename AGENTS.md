# Agent Instructions

## Project Snapshot

`dj-track-similarity` is a public personal/enthusiast project for local DJ
music-library analysis and track similarity. Keep public docs honest, practical,
and modest: this is not a polished commercial product or a research benchmark.

User-facing project documentation should be English unless the user asks
otherwise. The detailed user/developer guide is `docs/project-guide.md`; use it
for full CLI/API/script details instead of duplicating long references here.

The project is a Python backend/CLI plus a React/Vite frontend:

- `src/dj_track_similarity/`: database, scanning, analysis, search, export,
  tags, API, and CLI.
- `frontend/`: React UI built with Vite and TypeScript.
- `tests/`: pytest coverage for backend/API/search/jobs/tags.
- `scripts/repair_audio_metadata.py`: standalone dry-run-first audio metadata
  diagnostic/repair helper.
- `scripts/audio_repair/`: runtime state/log/report/backup workspace; commit
  only `.gitkeep`.

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
- `scripts/repair_audio_metadata.py --apply` is separate and may rewrite only
  files it reports as `REPAIRABLE`; dry-run must not write/copy audio, apply is
  sequential, and full-file backups are created by default.
- Keep SQLite writes routed through `LibraryDatabase`, with the shared
  path-scoped write lock, WAL, and busy timeout so scan/RefreshTags/Sonara/
  MAEST/MERT/CLAP/reset writes queue safely.
- Treat `dj-track-similarity.sqlite` as local user state. Tests must use
  temporary databases (`tmp_path` or explicit `--db`).
- Do not commit generated local artifacts: `*.sqlite`, `*.log`, `__pycache__/`,
  `.pytest_cache/`, `frontend/node_modules/`, transient temp folders, or
  generated `scripts/audio_repair/` contents.
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
- Keep library browsing scalable: `/api/tracks` remains server-side
  paginated/searchable with lightweight rows, `/api/library/summary` provides
  counters, and full metadata loads via `/api/tracks/{id}` only on dialog open.
- Reset controls are database-only per analysis family. Database clear deletes
  SQLite records only and must require explicit UI confirmation.
- Metadata dialog must keep Mutagen tags, SONARA features, and MAEST genres
  visually separate; preserve the current display order and source boundaries.
- Keep hover help on user-editable controls with purpose, type/format, and range.

## Common Commands

For the complete CLI, API, and maintenance script reference, see
`docs/project-guide.md`.

```powershell
python -m pip install -e ".[dev]"
python -m pip install -e ".[sonara,ml,dev]"
pytest
dj-sim serve --host 127.0.0.1 --port 8765
dj-sim serve --host 127.0.0.1 --port 8765 --log-track-events
scripts\run_server.cmd
cd frontend
npm run build
npm run dev
```

Useful focused CLI examples:

```powershell
dj-sim scan <path-to-music> --db .\data\library.sqlite
dj-sim analyze-sonara --limit 3 --batch-size 4 --db .\data\library.sqlite
dj-sim analyze --adapter mert --device cpu --batch-size 2 --limit 3 --db .\data\library.sqlite
dj-sim analyze --adapter clap --device cpu --batch-size 2 --limit 3 --db .\data\library.sqlite
dj-sim analyze-genres --device cpu --batch-size 2 --limit 3 --db .\data\library.sqlite
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 5 --db .\data\library.sqlite
dj-sim relocate-library .\music-old .\music-new --db .\data\library.sqlite
dj-sim relocate-library .\music-old .\music-new --apply --db .\data\library.sqlite
dj-sim doctor
```

Focused repair-script test when only `scripts/repair_audio_metadata.py` changes:

```powershell
python -m pytest scripts\tests\test_repair_audio_metadata.py --override-ini addopts=
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
- If changing Mutagen tags, Sonara features, MAEST job state, audio decoding,
  search, library browsing, relocation, analysis controls, SQLite writes, UI
  controls, custom tags, or standard genre writes, update the corresponding
  focused tests and frontend/API/docs surfaces.
- Prefer deterministic test data and test-local stub adapters over real audio
  analysis in automated tests.

## Verification Expectations

- Backend changes: run focused pytest for the touched behavior; use full
  `pytest` for broad/shared changes.
- Frontend changes: run `npm run build` in `frontend/`.
- API contract changes: exercise the affected endpoint through tests or a local
  server.
- CLI behavior changes: run the specific `dj-sim ...` command with a temporary
  database when practical.
- Relocation changes: verify dry-run does not modify paths, apply preserves IDs
  and analysis state, and conflicts/missing files block apply.
- Sonara changes: prefer stubbed helpers or small temp WAV fixtures; never rely
  on a real user music library in automated tests.
