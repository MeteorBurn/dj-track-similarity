# Agent Instructions

## Project Snapshot

dj-track-similarity is a public personal/enthusiast project for exploring music-library analysis and track similarity for DJ-set preparation. The README should sound honest, practical, and modest: this is not a polished commercial product or a research benchmark. The user is building something useful for their own music collection, tagging workflow, and DJ sets, and it may also be useful to other music collectors.

Technically, it is a local tool that scans an audio library, stores metadata in SQLite, refreshes selected Mutagen file tags, relocates stored track paths after a library folder is moved, extracts Sonara playlist features, generates track embeddings, extracts MAEST genre labels, searches for compatible tracks, builds playlists, exports M3U/CSV files, can write custom `DJ_SIM_*` tags on explicit request, and can explicitly save MAEST genres into standard audio genre tags.

Keep user-facing project documentation in English unless the user asks otherwise.

The project is a Python backend/CLI with a React/Vite frontend:

- `src/dj_track_similarity/`: Python package for database access, scanning, analysis, search, export, tags, API, and CLI.
- `frontend/`: React UI built with Vite and TypeScript.
- `tests/`: pytest coverage for scanner/database, search, export, API dialog behavior, scan jobs, analysis jobs, and tags.
- `scripts/run_server.cmd`: Windows shortcut for running the FastAPI app on `127.0.0.1:8765`.

This workspace may not be a Git repository. Do not assume Git history, branches, or commits are available.

## Safety Rules

- Treat real audio files as user data. Scanning, analysis, search, preview, RefreshTags, reset, clear, and export should not modify audio files.
- Library path relocation updates only stored `tracks.path` values in SQLite. It must not move, copy, delete, rewrite, retag, or reanalyze audio files.
- Library path relocation must be previewable before applying. Dry-run output should report matched tracks, missing target files, and path conflicts. Apply must reject missing target files and conflicts instead of partially updating the database.
- Library path relocation must preserve track IDs and all dependent local state, including embeddings, Sonara features, MAEST genres, playlists, and tag metadata.
- `tag-apply` and `/api/tags/apply` write only custom `DJ_SIM_*` tags. They must not overwrite standard BPM, key, title, artist, album, mood, genre, or other normal tags.
- `/api/tags/genres/apply` is the explicit exception for standard metadata writes: it overwrites only the standard genre tag from stored MAEST labels. It must preserve existing artist, title, album, BPM, key, and other normal tags.
- Standard genre tag writing should use player-compatible fields: `TCON` for MP3/WAV/AIFF ID3 tags, `GENRE` for FLAC/Vorbis-style tags, and `©gen` for MP4/M4A/ALAC. Multiple MAEST labels should be written as one string separated by `;`, for example `Tech House; Minimal; Techno`.
- Standard genre writes must be an upsert of the genre field only. If no genre tag exists, create it; if one or many genre values already exist, replace them with the single normalized `;`-separated MAEST genre string. Do not append duplicate genre frames or preserve stale genre values.
- WAV genre writing should use `mutagen.wave.WAVE` for WAV files, validate the RIFF/WAVE data chunk before and after saving, and verify that the saved `TCON` value is readable afterward. It must preserve PCM audio payload and avoid repeated file growth when the same genre string is written again.
- WAV genre writing may perform narrow header/chunk repairs before saving when the file is otherwise playable: repair a `data` chunk that declares a size larger than the actual remaining file, repair the known two-byte `data`/`id3 ` boundary shift, and remove duplicate WAV `id3 `/`ID3 ` chunks while keeping the first ID3 tag block. Skip unsupported malformed containers instead of failing the whole genre-save batch. Do not manually rewrite whole WAV files for normal genre updates.
- Treat `dj-track-similarity.sqlite` as local user state. Tests should use temporary databases via `tmp_path` or explicit `--db` paths.
- SQLite writes must be safe for parallel jobs across the whole project, not just one analysis family. Keep all database mutations routed through `LibraryDatabase`, preserve the path-scoped write lock shared by `LibraryDatabase` instances for the same SQLite file, and keep connection pragmas such as `busy_timeout` plus WAL enabled so scan/RefreshTags/Sonara/MAEST/MERT/CLAP/reset/playlist writes queue cleanly while read-heavy work can continue.
- Do not commit or preserve generated local artifacts unless explicitly asked: `*.sqlite`, `*.log`, `__pycache__/`, `.pytest_cache/`, `frontend/node_modules/`, and transient temp folders.
- Runtime file logging defaults to `dj-track-similarity.log`; agents may inspect it when debugging, but must not commit log files.
- Runtime file logging defaults to warnings and errors only. Use `DJ_TRACK_SIMILARITY_LOG_LEVEL` or `dj-sim serve --log-level info|debug` when detailed track-level file logs are needed. Do not confuse this with UI job event logs, which remain separate.
- Server startup requires `ffmpeg` to be available on `PATH` or through `DJ_TRACK_SIMILARITY_FFMPEG`. Keep the startup error clear and actionable if ffmpeg is missing.
- Mutagen scanning and `RefreshTags` read only a fixed whitelist of human-relevant file tags. They update SQLite metadata only and must not modify audio files.
- Mutagen metadata written to SQLite must be JSON-safe. Convert Mutagen-specific objects such as ID3 timestamps to strings before saving.
- Sonara feature analysis writes only SQLite track metadata (`sonara_features` and `sonara_model`) plus working BPM/key/duration/energy fields derived from analysis. BPM and key from Sonara must be analyzed values, not copied from file tags.
- Sonara key data should stay in the original analyzed Sonara fields. Do not derive or display Camelot notation from Sonara key data until that conversion is explicitly redesigned.
- Sonara `playlist` storage should stay focused on the current grouped UI contract instead of dumping every possible Sonara or helper field. Keep these groups and order aligned between SQLite JSON and the metadata dialog: Core features (`bpm`, `beats`, `onset_frames`, `onset_density`, `n_beats`, `rms_mean`, `rms_max`, `loudness_lufs`, `dynamic_range_db`, `spectral_centroid_mean`, `zero_crossing_rate`, `duration_sec`), Perceptual features (`energy`, `danceability`, `valence`, `acousticness`), Musical key (`key`, `key_confidence`), Tonal analysis (`chord_sequence`, `predominant_chord`, `chord_change_rate`, `dissonance`), and Spectral features (`spectral_bandwidth_mean`, `spectral_rolloff_mean`, `spectral_flatness_mean`, `spectral_contrast_mean`, `mfcc_mean`, `chroma_mean`).
- Do not store or show `unavailable` placeholder rows for Sonara fields that the playlist workflow cannot produce. Do not persist helper-only diagnostics such as `requested_feature_count` or `decode_path` inside `sonara_features`.
- Audio analysis uses a native-first shared loader: Sonara starts with `sonara.analyze_file`, while MAEST/MERT/CLAP use decoded waveform input. If native decoding fails for WAV-like files, the shared loader may recover playable PCM from malformed containers and return mono float audio without writing temporary decoded audio into the project.
- Sonara fallback should call `sonara.analyze_signal` with decoded audio. MAEST/MERT/CLAP should keep using the shared loader rather than direct `torchaudio.load` so malformed but playable WAV files behave consistently across all analysis families.
- MAEST genre analysis itself writes only SQLite track metadata (`maest_genres` and `maest_model`). It must not modify audio files. The separate genre-save action may later write those stored labels into standard audio genre tags.
- Full MERT/CLAP/MAEST analysis can be slow and may download Hugging Face/PyTorch/MAEST model weights on first use. Sonara is lighter but still decodes audio. Prefer `--fake` for embedding smoke checks unless the user asks for real ML analysis.
- In the UI, `Analyze limit = 0` means analyzing the whole library and is the default. Positive limits count missing results for the selected analysis family, not the first N tracks overall: Sonara skips tracks with `sonara_features`, MAEST skips tracks with stored genres, and MERT/CLAP skip tracks with embeddings in their own embedding space. Avoid triggering whole-library analysis unless the user clearly wants it or is operating the UI themselves.
- The UI `Embedding batch size` control is shared deliberately: Sonara uses it as parallel track workers; MAEST, MERT, and CLAP use it as inference batch size.
- MERT/CLAP analysis should be accelerated with a single selected device plus inference batching, not multiple parallel model workers. Use `device=auto|cpu|cuda` and `batch_size`; keep legacy `workers` only as a compatibility alias for analysis batch size.
- MAEST uses the same `device=auto|cpu|cuda` selection model and supports inference batching through `batch_size`. Its adapter must call `model(audio_batch, melspectrogram_input=False)` and rank per-row logits; do not use `model.predict_labels()` for batch work because that helper averages activations into one label vector.
- Sonara batch size is not ML inference batching. It controls concurrent Sonara track workers in one job.
- `auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU.
- If CUDA is explicitly requested and unavailable, surface an error instead of silently falling back to CPU. Use `auto` for fallback behavior.
- For CUDA systems, PyTorch should usually be installed separately with the official CUDA wheel index before installing remaining ML dependencies. Do not assume plain `pip install -e ".[ml]"` will pick the correct CUDA build.
- Search UI is split into SONARA, MERT, and CLAP tabs inside the same search/listening panel. SONARA is the primary seed-search path and sends only `Mode`, `Similarity`, `Lookback`, and `Limit` to `/api/search/sonara`. MERT keeps its own seed-search tab and sends only `Similarity`, `Lookback`, and `Limit` to `/api/search`. CLAP text search keeps the prompt field in its own tab and requires `clap` embeddings.
- Algorithm reset controls are database-only. Reset Sonara, MAEST, MERT, CLAP, or fake independently without touching unrelated analysis families or audio files.
- The database clear control deletes local SQLite records only and must require an explicit UI confirmation. It must not delete audio files.
- The track metadata dialog should keep sources visually separate: the unnamed top table first, Sonara computed features next, and MAEST genre labels separately. The top table must always show `Title`, `Audio Length`, `Audio Format`, `File Size`, and `File Path`; then show Mutagen tags only when present in this order: `Artist`, `Album`, `Genre`, `Year`, `Country`, `Label`, `Catalog`, `Track no.`, `Disc no.`, `BPM tag`, `Key tag`, `Comment`, `ISRC`.
- Keep hover help on user-editable parameters. Tooltips should explain purpose, accepted format, value type, and range.

## Common Commands

Install for development:

```powershell
python -m pip install -e ".[dev]"
```

Install optional ML dependencies:

```powershell
python -m pip install -e ".[ml,dev]"
```

Install Sonara support:

```powershell
python -m pip install -e ".[sonara,dev]"
```

Install the full local lab dependency set:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

Run tests:

```powershell
pytest
```

Run the app:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
```

Detailed file logging, when needed:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --log-level info
```

or:

```powershell
scripts\run_server.cmd
```

Build the frontend after UI changes:

```powershell
cd frontend
npm run build
```

Frontend development server:

```powershell
cd frontend
npm run dev
```

Useful CLI smoke commands:

```powershell
dj-sim scan "D:\Music"
dj-sim analyze-sonara --batch-size 4 --limit 3
dj-sim analyze --device cpu --batch-size 2 --limit 3
dj-sim analyze --device cuda --batch-size 8 --limit 3
dj-sim analyze --adapter clap --device cpu --batch-size 2 --limit 3
dj-sim analyze-genres --device cpu --batch-size 2 --limit 3
dj-sim analyze-genres --device cuda --batch-size 4 --limit 3
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 5
dj-sim relocate-library "E:\MusicFast" "D:\MusicArchive"
dj-sim relocate-library "E:\MusicFast" "D:\MusicArchive" --apply
dj-sim analyze --fake
dj-sim doctor
dj-sim export 1 --format m3u --output-dir "D:\Exports"
dj-sim export 1 --format csv --output-dir "D:\Exports"
dj-sim tag-preview 1 2 3
```

## Backend Map

- `src/dj_track_similarity/models.py`: dataclasses for tracks, scan/analyze stats, search results, and tag previews.
- `src/dj_track_similarity/database.py`: SQLite schema, connection handling, path-scoped write serialization for parallel jobs, track upserts, embeddings, Sonara and MAEST metadata, library path relocation, analysis resets, database clearing, playlists, and row mapping.
- `src/dj_track_similarity/scanner.py`: synchronous library scan and fixed-whitelist audio metadata extraction with `mutagen`. Keep extracted values JSON-safe.
- `src/dj_track_similarity/scan_jobs.py`: scan and tag-refresh job manager with progress, cancellation, event logs, and optional parallel workers.
- `src/dj_track_similarity/audio_loader.py`: shared native-first audio loading and tolerant WAV recovery used by Sonara fallback, MAEST, MERT, and CLAP paths.
- `src/dj_track_similarity/dependencies.py`: runtime dependency checks such as required `ffmpeg` discovery.
- `src/dj_track_similarity/embedding.py`: embedding adapter protocol, deterministic fake adapter, MERT adapter, CLAP adapter, and adapter registry.
- `src/dj_track_similarity/runtime.py`: shared PyTorch runtime helpers for `auto|cpu|cuda`, CUDA diagnostics, and install hints.
- `src/dj_track_similarity/logging_config.py`: file logging setup, event log levels, and concise exception summaries.
- `src/dj_track_similarity/sonara_features.py`: Sonara playlist feature extraction, signal fallback through the shared audio loader, grouped feature summaries, and SQLite storage preparation.
- `src/dj_track_similarity/sonara_jobs.py`: Sonara feature analysis job manager with progress, cancellation, errors, and SQLite metadata saves.
- `src/dj_track_similarity/sonara_similarity.py`: SONARA-only feature similarity search for balanced, vibe, sound, and DJ-transition seed matching. It must ignore `camelot_key` even if stale metadata contains it.
- `src/dj_track_similarity/genres.py`: MAEST genre adapter using `maest-infer` with `discogs-maest-30s-pw-129e-519l`; batch inference must use direct model logits, not `predict_labels()`.
- `src/dj_track_similarity/analysis.py`: simple analyze-missing flow.
- `src/dj_track_similarity/analysis_jobs.py`: analysis job manager with batching, progress, cancellation, errors, adapter metadata, and embedding saves.
- `src/dj_track_similarity/genre_jobs.py`: MAEST genre analysis job manager with batching, progress, cancellation, errors, and SQLite metadata saves.
- `src/dj_track_similarity/search.py`: embedding-space centroid similarity search plus arbitrary query-vector search for CLAP text mode.
- In the frontend, SONARA, MERT, and CLAP search controls should stay separated by tabs so each model shows only its own parameters.
- `src/dj_track_similarity/exporter.py`: playlist export to M3U or CSV.
- `src/dj_track_similarity/tags.py`: custom `DJ_SIM_*` tag preview/apply logic plus explicit MAEST-to-standard-genre tag writing, including guarded WAV genre writes.
- `src/dj_track_similarity/api.py`: FastAPI factory, request models, REST endpoints including `/api/library/relocate`, static frontend mount, and media serving.
- `src/dj_track_similarity/cli.py`: Typer CLI entrypoint exposed as `dj-sim`, including `relocate-library` for previewing and applying stored path updates after moving a library folder.

## Frontend Map

- `frontend/src/api.ts`: typed fetch wrapper and API contract mirror for the FastAPI endpoints.
- `frontend/src/App.tsx`: single-page React app for scanning, RefreshTags, Sonara/MAEST/MERT/CLAP analysis, analysis counters in the header, algorithm resets, database clearing, track metadata popups, search, playlist assembly, export, and tagging workflows.
- `frontend/src/styles.css`: app styling.
- `frontend/dist/`: built static frontend served by FastAPI. Regenerate it with `npm run build` after UI changes instead of editing built assets by hand.

## Development Conventions

- Keep Python code compatible with Python 3.10+.
- Prefer small, focused changes in the existing modules instead of introducing new architecture.
- Keep FastAPI request/response shapes in sync with `frontend/src/api.ts` types.
- If adding or changing scan or analysis job state, update both backend tests and frontend polling/display logic as needed.
- If adding or changing Mutagen tag extraction, keep the fixed whitelist intentional, keep values JSON-safe, and update focused scanner/database tests.
- If adding or changing Sonara feature extraction, update `src/dj_track_similarity/sonara_features.py`, `src/dj_track_similarity/sonara_jobs.py`, `src/dj_track_similarity/database.py`, `src/dj_track_similarity/api.py`, `src/dj_track_similarity/cli.py`, `frontend/src/api.ts`, `frontend/src/App.tsx`, docs, and focused Sonara tests as needed. Keep the SQLite feature order and the UI group order in sync.
- If adding or changing MAEST genre job state, update `frontend/src/api.ts`, `frontend/src/App.tsx`, and focused genre job/API tests.
- If changing audio decode behavior, keep `src/dj_track_similarity/audio_loader.py`, Sonara fallback, MAEST/MERT/CLAP adapters, and focused malformed-WAV tests aligned.
- If changing search behavior, add or update focused tests in `tests/test_search.py`, `tests/test_sonara_similarity.py`, or API tests as appropriate.
- If changing library path relocation, keep `src/dj_track_similarity/database.py`, `src/dj_track_similarity/api.py`, `src/dj_track_similarity/cli.py`, `frontend/src/api.ts`, and focused database/API/CLI tests aligned.
- If changing analysis performance controls, keep `frontend/src/api.ts`, `src/dj_track_similarity/api.py`, `src/dj_track_similarity/analysis_jobs.py`, `src/dj_track_similarity/genre_jobs.py`, `src/dj_track_similarity/embedding.py`, `src/dj_track_similarity/genres.py`, and `src/dj_track_similarity/runtime.py` aligned.
- If changing SQLite connection handling, write paths, job batching, or worker concurrency, keep project-wide database-write safety in mind. Add or update focused tests that cover mixed parallel writes across analysis families and across separate `LibraryDatabase` instances pointing at the same SQLite file.
- If changing UI controls, preserve tooltip coverage for format/type/range guidance. Keep destructive controls such as database clear behind action-time confirmation.
- If touching custom tag writing, keep tests strict about preview being read-only and `tag-apply` writing only custom tags.
- If touching standard genre writing, keep tests strict that only genre fields are overwritten, existing normal tags are preserved, missing and pre-existing one-or-many genre values are both handled as upserts, MAEST category prefixes such as `Electronic---` are stripped, multiple labels are joined with `;`, malformed WAV containers are skipped without stopping the batch, supported WAV header/chunk repairs are narrow, duplicate WAV ID3 chunks are not retained, audio payload or decoded audio stays unchanged, repeated writes do not grow the file, and real temporary audio files are reread through Mutagen after saving.
- Prefer deterministic test data and fake adapters over real audio analysis in automated tests.
- Avoid broad refactors in `frontend/src/App.tsx` unless the task is specifically about frontend structure; it is currently the main UI surface.

## Verification Expectations

- Run `pytest` for backend changes.
- Run `npm run build` in `frontend/` for frontend changes and when backend static serving depends on current built assets.
- For API contract changes, exercise the affected endpoint through tests or a local server.
- For CLI behavior changes, run the specific `dj-sim ...` command with a temporary database or fake adapter when possible.
- For library path relocation changes, verify dry-run does not modify paths, apply preserves track IDs and analysis state, and conflicts or missing target files block apply.
- For Sonara changes, prefer tests with fakes or small temp WAV fixtures; avoid requiring a full user music library in automated tests.
