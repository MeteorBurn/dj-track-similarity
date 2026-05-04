# Agent Instructions

## Project Snapshot

dj-track-similarity is a local tool for preparing monotone seamless DJ sets. It scans an audio library, stores metadata in SQLite, generates track embeddings, searches for compatible tracks, builds playlists, exports M3U/CSV files, and can write custom `DJ_SIM_*` tags on explicit request.

The project is a Python backend/CLI with a React/Vite frontend:

- `src/dj_track_similarity/`: Python package for database access, scanning, analysis, search, export, tags, API, and CLI.
- `frontend/`: React UI built with Vite and TypeScript.
- `tests/`: pytest coverage for scanner/database, search, export, API dialog behavior, scan jobs, analysis jobs, and tags.
- `scripts/run_server.cmd`: Windows shortcut for running the FastAPI app on `127.0.0.1:8765`.

This workspace may not be a Git repository. Do not assume Git history, branches, or commits are available.

## Safety Rules

- Treat real audio files as user data. Scanning, analysis, search, and export should not modify audio files.
- Only `tag-apply` and `/api/tags/apply` write audio metadata, and they must only write custom `DJ_SIM_*` tags. Do not overwrite standard BPM, key, title, artist, album, mood, or other normal tags.
- Treat `dj-track-similarity.sqlite` as local user state. Tests should use temporary databases via `tmp_path` or explicit `--db` paths.
- Do not commit or preserve generated local artifacts unless explicitly asked: `*.sqlite`, `*.log`, `__pycache__/`, `.pytest_cache/`, `frontend/node_modules/`, and transient temp folders.
- Full MERT/CLAP analysis can be slow and may download Hugging Face/PyTorch model weights on first use. Prefer `--fake` for smoke checks unless the user asks for real ML analysis.
- In the UI, `Analyze limit = 0` means analyzing the whole library and is the default. Avoid triggering whole-library analysis unless the user clearly wants it or is operating the UI themselves.
- MERT/CLAP analysis should be accelerated with a single selected device plus inference batching, not multiple parallel model workers. Use `device=auto|cpu|cuda` and `batch_size`; keep legacy `workers` only as a compatibility alias for analysis batch size.
- If CUDA is explicitly requested and unavailable, surface an error instead of silently falling back to CPU. Use `auto` for fallback behavior.
- Current seed search UI is in MERT validation mode: active knobs are `Similarity`, `Lookback`, and `Limit`. BPM, Key, Energy, Epsilon, and Noise are disabled in the UI and should not be sent from the frontend search request until calibrated. Text search is a separate CLAP mode and requires `clap` embeddings.
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

Run tests:

```powershell
pytest
```

Run the app:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
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
dj-sim analyze --device cpu --batch-size 2 --limit 3
dj-sim analyze --device cuda --batch-size 8 --limit 3
dj-sim analyze --adapter clap --device cpu --batch-size 2 --limit 3
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 5
dj-sim analyze --fake
dj-sim export 1 --format m3u --output-dir "D:\Exports"
dj-sim export 1 --format csv --output-dir "D:\Exports"
dj-sim tag-preview 1 2 3
```

## Backend Map

- `src/dj_track_similarity/models.py`: dataclasses for tracks, scan/analyze stats, search results, and tag previews.
- `src/dj_track_similarity/database.py`: SQLite schema, connection handling, track upserts, embeddings, playlists, and row mapping.
- `src/dj_track_similarity/scanner.py`: synchronous library scan and audio metadata extraction with `mutagen`.
- `src/dj_track_similarity/scan_jobs.py`: scan job manager with progress, cancellation, event logs, and optional parallel workers.
- `src/dj_track_similarity/embedding.py`: embedding adapter protocol, deterministic fake adapter, MERT adapter, CLAP adapter, and adapter registry.
- `src/dj_track_similarity/analysis.py`: simple analyze-missing flow.
- `src/dj_track_similarity/analysis_jobs.py`: analysis job manager with batching, progress, cancellation, errors, adapter metadata, and embedding saves.
- `src/dj_track_similarity/search.py`: centroid-based similarity search plus arbitrary query-vector search for CLAP text mode.
- In the frontend, only Similarity, Lookback, and Limit are active for MERT validation; the other search filters remain backend capabilities/future knobs.
- `src/dj_track_similarity/exporter.py`: playlist export to M3U or CSV.
- `src/dj_track_similarity/tags.py`: custom `DJ_SIM_*` tag preview and apply logic.
- `src/dj_track_similarity/api.py`: FastAPI factory, request models, REST endpoints, static frontend mount, and media serving.
- `src/dj_track_similarity/cli.py`: Typer CLI entrypoint exposed as `dj-sim`.

## Frontend Map

- `frontend/src/api.ts`: typed fetch wrapper and API contract mirror for the FastAPI endpoints.
- `frontend/src/App.tsx`: single-page React app for scanning, analysis, search, playlist assembly, export, and tagging workflows.
- `frontend/src/styles.css`: app styling.
- `frontend/dist/`: built static frontend served by FastAPI. Regenerate it with `npm run build` after UI changes instead of editing built assets by hand.

## Development Conventions

- Keep Python code compatible with Python 3.10+.
- Prefer small, focused changes in the existing modules instead of introducing new architecture.
- Keep FastAPI request/response shapes in sync with `frontend/src/api.ts` types.
- If adding or changing scan or analysis job state, update both backend tests and frontend polling/display logic as needed.
- If changing search behavior, add or update focused tests in `tests/test_search.py`.
- If changing analysis performance controls, keep `frontend/src/api.ts`, `src/dj_track_similarity/api.py`, `src/dj_track_similarity/analysis_jobs.py`, and `src/dj_track_similarity/embedding.py` aligned.
- If changing UI controls, preserve tooltip coverage for format/type/range guidance.
- If touching tag writing, keep tests strict about preview being read-only and apply writing only custom tags.
- Prefer deterministic test data and fake adapters over real audio analysis in automated tests.
- Avoid broad refactors in `frontend/src/App.tsx` unless the task is specifically about frontend structure; it is currently the main UI surface.

## Verification Expectations

- Run `pytest` for backend changes.
- Run `npm run build` in `frontend/` for frontend changes and when backend static serving depends on current built assets.
- For API contract changes, exercise the affected endpoint through tests or a local server.
- For CLI behavior changes, run the specific `dj-sim ...` command with a temporary database or fake adapter when possible.
