# Architecture and Runtime

This page maps the backend, frontend, runtime dependencies, and logging behavior.

## Architecture

The backend package lives in `src/dj_track_similarity/`.

- `cli.py` exposes the `dj-sim` Typer CLI.
- `api.py` creates the FastAPI app and REST endpoints.
- `database.py` owns SQLite access and all database mutations.
- `db_schema.py` defines the current SQLite schema and validation.
- `scanner.py` scans folders and reads Mutagen metadata.
- `scan_jobs.py`, `analysis_jobs.py`, `classifier_jobs.py`, and `tags.py`
  manage cancellable jobs and status objects.
- `audio_loader.py` provides shared native-first audio loading.
- `sonara_features.py` extracts the focused Sonara playlist feature set.
- `sonara_similarity.py` and `sonara_similarity_scoring.py` rank Sonara
  feature similarity.
- `embedding.py` contains MERT and CLAP embedding adapters.
- `genres.py` contains the MAEST genre adapter.
- `classifier_scoring.py` loads promoted classifier artifacts and scores
  feature-complete tracks.
- `tags.py` writes MAEST labels into the standard genre field and runs the
  cancellable genre-tag job; `wave_tags.py` provides the guarded WAV/ID3
  genre-write path.
- `search.py` performs embedding-space similarity search.
- `exporter.py` writes M3U and CSV outputs.
- `runtime.py` selects `auto`, `cpu`, or `cuda` for PyTorch work.
- `dependencies.py` checks runtime dependencies such as `ffmpeg`.
- `logging_config.py` configures rotating file logs.

The frontend lives in `frontend/src/`.

- `api.ts` mirrors the FastAPI contract.
- `App.tsx` coordinates app state and workflows.
- `LibraryPanel.tsx` contains scan, refresh, analysis, reset, and clear
  controls.
- `TrackPanel.tsx`, `TrackRows.tsx`, and `TrackMetadataDialog.tsx` show library
  rows, liked-track controls, and track details.
- `SearchPlaylistPanel.tsx` contains SONARA, MERT, CLAP, and CLASS tabs plus
  export controls.

## Runtime Dependencies

Core runtime dependencies are declared in `pyproject.toml`:

- `numpy>=1.26,<2.0`
- `mutagen`
- `pydantic`
- `typer`
- `fastapi`
- `uvicorn`
- `joblib`

Optional groups:

- `sonara`: installs Sonara support.
- `ml`: installs the synchronized PyTorch/Torchaudio/Torchvision/TorchCodec
  stack, Transformers, Hugging Face Hub, LAION-CLAP, and MAEST support.
- `rhythm-lab`: installs scikit-learn for local classifier training and
  benchmarking in Rhythm Lab.
- `dev`: installs pytest and Ruff.

`ffmpeg` is required for robust server startup and audio decoding. It can be
found from `PATH` or configured with:

```text
DJ_TRACK_SIMILARITY_FFMPEG
```

The verified Windows CUDA stack is:

- PyTorch `2.11.0`
- Torchaudio `2.11.0`
- Torchvision `0.26.0`
- TorchCodec `0.13.0`
- NumPy `>=1.26,<2.0`
- PyTorch wheel index `https://download.pytorch.org/whl/cu130`

Install the matching CUDA wheels from the official PyTorch wheel index before
installing the remaining ML dependencies:

```powershell
python -m pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install torchcodec==0.13.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install -e ".[sonara,ml,dev]"
```

Use `.[sonara,ml,rhythm-lab,dev]` instead when the same environment will also
train Rhythm Lab classifier profiles.

On Windows, TorchCodec-backed Torchaudio decoding needs an FFmpeg shared build
with DLLs available on `PATH`, not only a static `ffmpeg.exe`. The portable tools
setup should use GyanD `ffmpeg 8.1.1-full_build-shared` or a compatible
`full_build-shared` FFmpeg layout such as:

```text
C:\Utils\tools\ffmpeg\bin\ffmpeg.exe
C:\Utils\tools\ffmpeg\bin\avcodec-*.dll
C:\Utils\tools\ffmpeg\bin\avformat-*.dll
```

## Logging

Runtime file logging defaults to:

```text
dj-track-similarity.log
```

The log rotates daily at midnight and keeps one rotated day. INFO-level startup,
completion, warning, and error summaries are written by default. Successful
per-track job events are aggregated out of the file log unless detailed logging
is enabled.

Environment variables:

- `DJ_TRACK_SIMILARITY_LOG`: file log path.
- `DJ_TRACK_SIMILARITY_LOG_LEVEL`: `debug`, `info`, `warning`, `error`, or
  `critical`.
- `DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS`: set to `1`, `true`, `yes`, or `on` to
  write successful per-track job events.

The server also exposes `--log-level` and `--log-track-events`.

CLI analysis commands print a live one-line progress display while they run.
The line is redrawn in place and includes a progress bar, percentage,
`processed/total`, track-level `analyzed` and `failed`, approximate `tracks/s`,
and an estimated remaining time. This is console-only progress for the CLI
process that started the job; it does not attach to jobs started by the web
UI/server process.

CLI analysis commands can also write diagnostic timing lines to the file log
when `--diagnostics` is passed on the command or
`DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS=1` is set. These include batch-level
model timing, `tracks_per_second`, track count, and window count where the
selected adapter exposes those details. Audio loading also logs decoder
fallback details by path: failed decoders such as `torchaudio`, `wave`, or
`ffmpeg`, their error text, and the fallback decoder that eventually succeeded
when one does. This diagnostic logging is off by default.
