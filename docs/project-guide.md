# dj-track-similarity Project Guide

This guide is the detailed reference for `dj-track-similarity`: what the
project does, how the local database is structured, what each analysis family
produces, how the web UI and API fit together, and how to use every CLI command.

The short project introduction remains in [README.md](../README.md). This file
is intentionally longer and more operational.

## Project Overview

`dj-track-similarity` is a local music-library analysis tool for DJ-set
preparation. It scans a folder of audio files, stores metadata and analysis
outputs in SQLite, and helps search for tracks that may work near each other in
a set.

The project is a personal and enthusiast tool, not a commercial product and not
a formal audio research benchmark. Its practical goal is to make a real local
collection easier to inspect, tag, search, and prepare for DJ use.

The application has two main surfaces:

- A Python backend and CLI installed as `dj-sim`.
- A React/Vite frontend served by the FastAPI backend.

The current workflow is:

1. Choose or create a SQLite database.
2. Scan a music folder.
3. Run one or more analysis passes: Sonara, MAEST, MERT, or CLAP.
4. Browse the paged library, inspect track metadata, and choose seed tracks.
5. Search with SONARA, MERT, or CLAP.
6. Assemble a temporary set and export it as M3U or CSV.
7. Optionally score promoted classifier profiles.
8. Optionally write MAEST genres into standard audio genre tags.

## Core Features

- Scans local audio folders and stores track rows in SQLite.
- Reads a fixed whitelist of human-relevant Mutagen file tags.
- Refreshes Mutagen tags for already indexed tracks without deleting analysis.
- Relocates stored track paths after moving the same library folder.
- Extracts Sonara playlist features for rhythm, loudness, tonal, perceptual,
  and spectral inspection.
- Builds MERT audio embeddings for seed-track similarity search.
- Builds CLAP audio embeddings and CLAP text vectors for text-to-audio search.
- Extracts MAEST genre labels and confidence scores.
- Stores MAEST embeddings during genre analysis.
- Scores promoted classifier models from existing SONARA, MERT, and MAEST data.
- Stores analysis status per track for `sonara`, `maest`, `mert`, and `clap`.
- Stores classifier scores separately from file tags and model metadata.
- Keeps the library browser server-side paginated for large local collections.
- Loads full metadata for one track only when the metadata dialog opens.
- Serves browser previews, starts playback from the preview button, and
  transcodes AIFF/AIF to temporary seekable WAV files.
- Exports the current temporary set as `.m3u` or `.csv`.
- Resets analysis families independently in SQLite.
- Clears the local database after explicit confirmation.
- Writes standard genre tags from stored MAEST labels only when explicitly
  requested.

## Safety Model

The default application behavior is database-first and read-only for audio
files.

- Scanning reads files and writes SQLite rows only.
- RefreshTags rereads file metadata and writes SQLite rows only.
- Sonara, MAEST, MERT, and CLAP analysis read audio and write SQLite analysis
  outputs only.
- Promoted classifier scoring reads existing SQLite analysis data and writes
  SQLite classifier rows only. It does not decode or modify audio.
- Search reads SQLite data and does not change audio or the database.
- Browser preview serves audio for the player; AIFF/AIF previews may be
  transcoded through `ffmpeg` to temporary seekable WAV files, but source files
  are not rewritten.
- Export writes playlist/export files only.
- Analysis reset deletes only selected local SQLite analysis outputs.
- Database clear deletes local SQLite track rows, embedding rows, and dependent
  classifier-score rows only.
- Library relocation updates only stored `tracks.path` values in SQLite.

The explicit exception is the genre-save workflow:

- `/api/tags/genres/apply` and `/api/tags/genres/jobs` can write standard audio
  genre tags from stored MAEST labels.
- Genre writing must overwrite only the genre field.
- Existing title, artist, album, BPM, key, and other normal tags must remain
  intact.

The standalone `scripts/audio_repair/repair_audio_metadata.py` helper is another explicit
exception. It is separate from the app, dry-run by default, and can rewrite
repairable audio files only with `--apply`.

## Supported Audio Files

The main scanner currently indexes these extensions:

```text
.aif, .aiff, .alac, .flac, .m4a, .mp3, .ogg, .opus, .wav, .wave
```

The repair helper supports a broader diagnostic set because it checks container
and codec mismatches for more formats. See the maintenance script reference
below for that workflow.

## Architecture

The backend package lives in `src/dj_track_similarity/`.

- `cli.py` exposes the `dj-sim` Typer CLI.
- `api.py` creates the FastAPI app and REST endpoints.
- `database.py` owns SQLite access and all database mutations.
- `db_schema.py` defines the current SQLite schema and validation.
- `scanner.py` scans folders and reads Mutagen metadata.
- `scan_jobs.py`, `analysis_jobs.py`, `sonara_jobs.py`, `genre_jobs.py`,
  `classifier_jobs.py`, and `tags.py` manage cancellable jobs and status
  objects.
- `audio_loader.py` provides shared native-first audio loading.
- `sonara_features.py` extracts the focused Sonara playlist feature set.
- `sonara_similarity.py` and `sonara_similarity_scoring.py` rank Sonara
  feature similarity.
- `embedding.py` contains MERT and CLAP embedding adapters.
- `genres.py` contains the MAEST genre adapter.
- `classifier_scoring.py` loads promoted classifier artifacts and scores
  feature-complete tracks.
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
  rows and track details.
- `SearchPlaylistPanel.tsx` contains SONARA, MERT, CLAP, and CLASS tabs plus
  export controls.

## SQLite Specification

The current schema version is `2`.

### `tracks`

Stores one row per indexed audio file:

- `id`: stable local track ID.
- `path`: unique stored audio path.
- `size`: file size at scan time.
- `mtime`: file modification time at scan time.
- `artist`, `title`, `album`: selected file metadata.
- `bpm`, `musical_key`, `energy`, `duration`: working fields used by the UI and
  analysis flows.
- `metadata_json`: JSON object for Mutagen fields and model-derived metadata.
- `created_at`, `updated_at`: local row timestamps.

`metadata_json` must be valid JSON. The schema has triggers to reject invalid
JSON on insert or update.

### `embeddings`

Stores model vectors by track and embedding space:

- `track_id`: references `tracks.id`.
- `embedding_key`: currently `mert`, `clap`, or `maest`.
- `model_name`: model or checkpoint identifier.
- `dim`: vector dimension.
- `vector`: binary float32 vector payload.
- `updated_at`: local row timestamp.

The primary key is `(track_id, embedding_key)`, so the same track can have MERT,
CLAP, and MAEST vectors without mixing those spaces.

### `library_settings`

Stores local database-level settings such as the selected music root.

### `track_classifier_scores`

Stores derived classifier outputs by track and classifier key:

- `track_id`: references `tracks.id`.
- `classifier`: classifier key such as `live_instrumentation`.
- `score`: primary user-facing score used for filtering.
- `label`: coarse label such as `high`, `medium`, or `low`.
- `confidence`: maximum class probability.
- `probabilities_json`: classifier probabilities keyed by the profile's
  training labels.
- `feature_set`: feature family used by the classifier artifact, currently
  `combined`.
- `model_id`: promoted model path used for scoring.
- `analyzed_at`: local scoring timestamp.

The primary key is `(track_id, classifier)`, so rerunning a classifier updates
the score for that track instead of appending historical rows.

## Metadata and Analysis Data

The app deliberately separates file tags from computed values.

Mutagen scanning reads this fixed whitelist:

- `artist`
- `title`
- `album`
- `genre`
- `year`
- `country`
- `label`
- `catalog_number`
- `track_number`
- `disc_number`
- `bpm`
- `key`
- `comment`
- `isrc`
- `duration`
- `audio_format`
- `audio_codec`
- `date`

Values are normalized into JSON-safe values before being stored. Mutagen-specific
objects such as ID3 timestamps are converted to strings.

`RefreshTags` replaces only this Mutagen metadata subset. It preserves stored
paths and model analysis data.

## Analysis Families

### Sonara

Sonara is used in playlist mode as a fast explainable feature pass. It stores
focused playlist features under `metadata_json.sonara_features` and the model
name under `metadata_json.sonara_model`.

Stored groups and keys:

- Core features: `bpm`, `beats`, `onset_frames`, `onset_density`, `n_beats`,
  `rms_mean`, `rms_max`, `loudness_lufs`, `dynamic_range_db`,
  `spectral_centroid_mean`, `zero_crossing_rate`, `duration_sec`.
- Perceptual features: `energy`, `danceability`, `valence`, `acousticness`.
- Musical key: `key`, `key_confidence`.
- Tonal analysis: `predominant_chord`, `chord_change_rate`, `dissonance`.
- Spectral features: `spectral_bandwidth_mean`, `spectral_rolloff_mean`,
  `spectral_flatness_mean`, `spectral_contrast_mean`, `mfcc_mean`,
  `chroma_mean`.

Sonara BPM and key are analyzed values, not copied from file tags. The app keeps
raw Sonara key data and does not derive Camelot notation.

The CLI and UI call Sonara with `batch_size` as parallel track workers, not as a
neural-network inference batch.

### MAEST

MAEST writes genre metadata and embeddings only to SQLite during analysis:

- `metadata_json.maest_model`
- `metadata_json.maest_genres`
- `metadata_json.maest_syncopated_rhythm`
- `embeddings.embedding_key = "maest"`

The adapter uses `maest-infer` with `discogs-maest-30s-pw-129e-519l`. It
analyzes up to three 30-second windows per track:

- the 60-second offset;
- a window near 38 percent of duration;
- a window near 72 percent of duration.

Impossible or duplicate windows are clamped and deduplicated. Per-label
activations are averaged across windows, then the top labels are stored. MAEST
embedding rows are averaged across the same windows and stored under embedding
key `maest`.

MAEST analysis itself does not modify audio files. The separate genre-save
action can later write stored MAEST labels into standard audio genre tags.
The `maest_syncopated_rhythm` flag is derived from saved MAEST genres and is
used by the library `syncopated` preset.

### MERT

MERT builds audio-to-audio embeddings under embedding key `mert`.

The default model is:

```text
m-a-p/MERT-v1-95M
```

MERT search uses only MERT vectors. It does not mix with Sonara features or CLAP
vectors.

### CLAP

CLAP builds music-focused audio embeddings under embedding key `clap` and
creates text vectors for text-to-audio search.

The active checkpoint is:

```text
lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt
```

Text search requires CLAP audio embeddings produced by the same CLAP checkpoint.

### Promoted Classifiers

Promoted classifiers are local classifier profiles, not audio-analysis models
that decode files themselves. They score tracks from already stored analysis
outputs:

- SONARA playlist features from `metadata_json.sonara_features`;
- MERT embeddings from `embeddings.embedding_key = "mert"`;
- MAEST embeddings from `embeddings.embedding_key = "maest"`.

Tracks missing any of those inputs are skipped by the classifier job. Scores are
stored in `track_classifier_scores` under the profile classifier key.

Stable model locations use the profile artifact prefix:

```text
models/classifiers/<artifact-prefix>/model.joblib
```

Those files are produced outside the main app by Rhythm Lab's promotion command:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation
```

The promoted `model.joblib` and `model.json` files are local artifacts and are
ignored by git. The source Rhythm Lab training artifacts remain in the
classifier-specific lab workspace:

```text
tools/rhythm-lab/artifacts/<artifact-prefix>/
```

Promoted metadata is generated from the Rhythm Lab profile and model artifact:
`classifier_key`, profile name, profile type, labels, feature set, source
artifact, and training label counts. Rhythm Lab training metrics use the same
profile-neutral shape for all profiles (`positive_*` metrics and
`label_order`) instead of classifier-specific metric aliases.

Rhythm Lab itself can manage additional classifier profiles inside its own UI.
Those profiles are scoped to the lab database and can define a unique display
name, description, profile type, labels, a profile artifact folder, and a
per-profile train-refresh threshold for required new labels per training class.
Profile names are unique case-insensitively inside one lab database. Binary
profiles use one positive training label, one negative training label, and
optional review-only labels. Multiclass profiles use two or more user-defined
`class` labels, and each track can have only one current label for the active
profile. Track labels in Rhythm Lab are editable current-state annotations:
when a label changes, the new value replaces the old one and is used by the next
profile training run. Updating the train-refresh threshold immediately changes
the readiness calculation for that profile. Rhythm Lab profiles become main-app
`dj-sim` classifier scores after they are promoted and scored with the generic
classifier command or API.

Rhythm Lab profile archive and delete are different operations. Archive hides a
profile from the normal UI list while preserving its labels, likes,
predictions, and training checkpoints. Delete is a CLI-only hard delete that
removes the profile and all profile-scoped lab rows from `rhythm_lab.sqlite`;
it never deletes source audio, source database rows, or artifact files. Delete
requires an exact confirmation value and can target either the unique profile
name or `classifier_key`:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py delete-profile --labels tools\rhythm-lab\data\rhythm_lab.sqlite --name "Electronic Mood" --confirm "Electronic Mood"
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py delete-profile --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile electronic_mood --confirm electronic_mood
```

Rhythm Lab benchmarks `sonara`, `mert`, `maest`, and `combined` feature sets.
The `combined` feature set requires SONARA features plus MERT and MAEST
embeddings. The lab UI displays compact coverage badges for Tracks, SONARA,
MAEST, and MERT, plus label-count badges for the active profile.

The user-facing score is the classifier probability for the profile's positive
training label. Because UI displays can round probabilities, a value shown as
`1.0000` may be slightly below mathematical `1.0`. Use thresholds such as
`0.99`, `0.95`, or `0.90` for practical filtering instead of relying on exact
`1.0`.

## Search Modes

The search panel has separate tabs.

The library browser also has a `syncopated` preset filter. It selects tracks
whose stored MAEST metadata has `maest_syncopated_rhythm = true` and can be
combined with normal library text search and the add-filtered-tracks workflow.

The CLASS tab contains classifier controls discovered from promoted
`models/classifiers/*/model.json` metadata. Each promoted classifier can be
analyzed from the UI, and its slider filters the library and
add-filtered-tracks workflow by `track_classifier_scores.score`.

### SONARA Search

SONARA is the primary explainable seed-search path. It sends selected seed
tracks, optional lookback tracks, limit, minimum similarity, mixer weights, and
modifiers to `/api/search/sonara`.

Mixer weights:

- `timbre`
- `rhythm`
- `dynamics`
- `harmonic`
- `tempo`

Modifiers:

- `energy`
- `valence`
- `acousticness`
- `brightness`
- `rhythm_density`
- `dynamic_range`
- `loudness`

The backend still accepts preset mode names for compatibility:

```text
balanced, vibe, sound, dj_transition, custom
```

The active UI path uses the custom mixer.

### MERT Search

MERT seed search sends seed tracks, lookback tracks, limit, and optional minimum
similarity to `/api/search`. It ranks tracks in the MERT embedding space.

### CLAP Text Search

CLAP text search sends a text prompt, limit, optional minimum similarity, and
device to `/api/search/text`. It ranks CLAP audio vectors against a CLAP text
vector.

Concrete English prompts usually work best:

```text
Melancholic minimal house with broken drums, warm chords, no vocals
Dark hypnotic techno with sparse percussion and deep rolling bass
Organic microhouse with soft pads, plucked textures, and spacious mood
```

### CLASS / Classifiers

The CLASS tab is for classifier-driven workflows rather than similarity search.
It lists promoted classifiers discovered from `models/classifiers/*/model.json`:

- `Analyze <classifier>` starts a cancellable classifier job.
- Each classifier slider filters the library server-side by stored classifier
  score.
- The metadata dialog shows classifier scores, confidence, label, feature set,
  and model file below SONARA features.

Promoted classifiers require a promoted model file and feature-complete tracks.
They do not analyze audio directly; run SONARA, MERT, and MAEST first for the
tracks you want to score.

## Tag Writing

MAEST genre saving writes one normalized semicolon-separated genre string, for
example:

```text
Tech House; Minimal; Techno
```

MAEST category prefixes such as `Electronic---` are stripped before writing.

Format-specific genre fields:

- MP3, WAV, AIFF ID3 tags: `TCON`
- FLAC and Vorbis-style tags: `GENRE`
- MP4, M4A, ALAC: `©gen`

WAV genre writing uses Mutagen's `WAVE` support, saves the `TCON` value, and
verifies that the saved value can be read afterward. It does not run a custom
RIFF repair step. If a WAV write or readback fails, that track is reported as
failed while the batch continues.

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
`processed/total`, `analyzed`, `failed`, approximate `tracks/s`, and an
estimated remaining time. This is console-only progress for the CLI process that
started the job; it does not attach to jobs started by the web UI/server
process.

CLI analysis commands can also write diagnostic timing lines to the file log
when `--diagnostics` is passed on the command or
`DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS=1` is set. These include batch-level
`prepare_seconds`, `decode_seconds`, `inference_seconds`, `save_seconds`,
`total_seconds`, `tracks_per_second`, track count, and window count for
MERT/CLAP and MAEST. Sonara diagnostics log per-track `total_seconds` and
`tracks_per_second`, because its internal decode and feature extraction are
handled inside Sonara. Audio loading also logs decoder fallback details by path:
failed decoders such as `torchaudio`, `wave`, or `ffmpeg`, their error text, and
the fallback decoder that eventually succeeded when one does. This diagnostic
logging is off by default.

## CLI Reference

Install the project first so `dj-sim` is available:

```powershell
python -m pip install -e ".[dev]"
```

Use `--db` on commands that should target a specific SQLite database. Without
`--db`, CLI commands use:

```text
dj-track-similarity.sqlite
```

in the current working directory.

### `dj-sim`

```powershell
dj-sim [OPTIONS] COMMAND [ARGS]...
```

Global options:

| Option | Meaning |
| --- | --- |
| `--install-completion` | Install shell completion for the current shell. |
| `--show-completion` | Print shell completion code. |
| `--help` | Show help. |

Commands:

```text
scan
relocate-library
analyze
analyze-genres
analyze-sonara
analyze-classifier
doctor
text-search
serve
```

### `dj-sim scan`

Scan a music folder and add or update SQLite track rows.

```powershell
dj-sim scan <path-to-music> --db .\data\library.sqlite
```

Usage:

```text
dj-sim scan [OPTIONS] MUSIC_ROOT
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `MUSIC_ROOT` | path | yes | Folder scanned recursively for supported audio files. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--help` | flag | off | Show help. |

Output:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

`scan` reads audio metadata and writes SQLite only. It does not modify audio
files.

### `dj-sim serve`

Start the local FastAPI server and serve the frontend.

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Usage:

```text
dj-sim serve [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--host` | text | `127.0.0.1` | Bind address for the local server. |
| `--port` | integer | `8765` | HTTP port. |
| `--db` | path | none | Optional SQLite database path. Without it, choose/create a database in the UI. |
| `--log-level` | text | `info` | File log level: `debug`, `info`, `warning`, `error`, or `critical`. |
| `--log-track-events` | flag | off | Write successful per-track events to the file log. |
| `--help` | flag | off | Show help. |

Then open:

```text
http://127.0.0.1:8765/
```

There is also a Windows helper:

```powershell
scripts\run_server.cmd
```

### `dj-sim analyze`

Build missing MERT or CLAP embeddings.

```powershell
dj-sim analyze --adapter mert --device auto --batch-size 4 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of missing embeddings to analyze. |
| `--adapter` | text | `mert` | Embedding adapter: `mert` or `clap`. |
| `--device` | text | `auto` | Embedding device: `auto`, `cpu`, or `cuda`. |
| `--batch-size` | integer `1..64` | `4` | Embedding inference batch size. |
| `--diagnostics` | flag | off | Write decoder fallback and batch timing diagnostics to the file log. |
| `--help` | flag | off | Show help. |

Examples:

```powershell
dj-sim analyze --adapter mert --device cpu --batch-size 2 --db .\data\library.sqlite
dj-sim analyze --adapter clap --device cuda --batch-size 8 --db .\data\library.sqlite
```

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> embedding_key=<key> device=<device> batch_size=<n>
```

`auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU. Explicit `cuda`
fails if CUDA is unavailable.

### `dj-sim analyze-sonara`

Extract missing Sonara playlist features.

```powershell
dj-sim analyze-sonara --batch-size 4 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-sonara [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of tracks missing Sonara features to analyze. |
| `--batch-size` | integer `1..64` | `1` | Parallel Sonara track workers. |
| `--diagnostics` | flag | off | Write analysis timing diagnostics to the file log. |
| `--help` | flag | off | Show help. |

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> batch_size=<n>
```

Sonara `batch-size` means parallel track workers.

### `dj-sim analyze-genres`

Extract missing MAEST genre labels.

```powershell
dj-sim analyze-genres --device auto --top-k 3 --batch-size 4 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-genres [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of tracks missing MAEST genres to analyze. |
| `--device` | text | `auto` | MAEST device: `auto`, `cpu`, or `cuda`. |
| `--top-k` | integer `1..10` | `3` | Number of MAEST genre labels to store per track. |
| `--batch-size` | integer `1..64` | `4` | MAEST inference batch size. |
| `--diagnostics` | flag | off | Write decoder fallback and batch timing diagnostics to the file log. |
| `--help` | flag | off | Show help. |

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> embedding_key=maest device=<device> top_k=<n> batch_size=<n>
```

MAEST analysis writes SQLite genre metadata and a MAEST embedding vector.

### `dj-sim analyze-classifier`

Score tracks with a promoted classifier profile.

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-classifier CLASSIFIER [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `CLASSIFIER` | text | required | Classifier key, for example `live_instrumentation`. |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--model` | path | `models/classifiers/<artifact-prefix>/model.joblib` | Optional classifier artifact path. |
| `--limit` | integer | none | Maximum number of feature-complete tracks to score. |
| `--help` | flag | off | Show help. |

Output:

```text
classifier=live_instrumentation scored=<n> skipped=<n> model=<path>
```

The command reads existing SONARA, MERT, and MAEST data. Tracks missing any
required input are skipped. Scores are upserted into `track_classifier_scores`.

### `dj-sim text-search`

Run CLAP text-to-audio search.

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim text-search [OPTIONS] QUERY
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `QUERY` | text | yes | Text description embedded by CLAP. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer `1..500` | `50` | Maximum result count. |
| `--min-similarity` | float | none | Optional minimum score threshold. |
| `--device` | text | `auto` | CLAP device: `auto`, `cpu`, or `cuda`. |
| `--help` | flag | off | Show help. |

Output rows:

```text
<score>    <track_id>    <path>
```

CLAP audio embeddings must exist before text search can return useful results.

### `dj-sim relocate-library`

Preview or apply stored path relocation after moving the same music folder.

```powershell
dj-sim relocate-library .\music-old .\music-new --db .\data\library.sqlite
```

Apply after reviewing the dry run:

```powershell
dj-sim relocate-library .\music-old .\music-new --apply --db .\data\library.sqlite
```

Usage:

```text
dj-sim relocate-library [OPTIONS] OLD_ROOT NEW_ROOT
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `OLD_ROOT` | path | yes | Existing stored root prefix in SQLite. |
| `NEW_ROOT` | path | yes | New root where the same files now exist. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--apply` | flag | off | Update stored paths after preview checks pass. |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--help` | flag | off | Show help. |

Output:

```text
dry_run=<true|false> tracks_matched=<n> tracks_updated=<n> missing_files=<n> conflicts=<n>
```

Conflicts and missing target files are printed per track. Apply mode rejects
missing files and conflicts instead of partially updating paths.

### `dj-sim doctor`

Print Python, PyTorch, and CUDA runtime diagnostics.

```powershell
dj-sim doctor
```

Usage:

```text
dj-sim doctor [OPTIONS]
```

Output can include:

```text
python=<path>
torch=<version>
torch_cuda_build=<version-or-none>
cuda_available=<true|false>
cuda_device_count=<n>
cuda_device_name=<name-or-none>
nvidia_smi_cuda=<version-or-none>
device_auto=<cuda|cpu>
suggested_torch_index=<url>
install=torch torchaudio --index-url <url>
```

Use this when `auto`, `cpu`, or `cuda` behavior is unclear.

## Web API Reference

The frontend uses these endpoints through `frontend/src/api.ts`.

### Database

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/database/current` | Return selected database state. |
| `POST` | `/api/database/switch` | Switch to a database path. |
| `POST` | `/api/database/dialog` | Open a local database chooser dialog. |
| `POST` | `/api/database/clear` | Clear local SQLite tracks, embeddings, and dependent classifier scores. |

### Library

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/library/scan` | Start a scan job for a root folder. |
| `POST` | `/api/library/tags/refresh` | Start a Mutagen tag refresh job. |
| `POST` | `/api/library/relocate` | Preview or apply stored path relocation. |
| `GET` | `/api/library/summary` | Return counters for tracks and analysis families. |
| `GET` | `/api/tracks` | Return a paginated/searchable track page. |
| `GET` | `/api/tracks/{track_id}` | Return one full track payload. |
| `POST` | `/api/tracks/filtered` | Return filtered track rows for selection workflows. |

`/api/tracks` and `/api/tracks/filtered` accept `preset=syncopated` to filter on
the stored MAEST syncopated-rhythm flag. They also accept classifier threshold
maps to filter tracks by stored classifier scores.

### Jobs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/library/scan/jobs/latest` | Return latest scan or tag-refresh job. |
| `GET` | `/api/library/scan/jobs/{job_id}` | Return one scan job. |
| `POST` | `/api/library/scan/jobs/{job_id}/cancel` | Request scan cancellation. |
| `GET` | `/api/analyze/jobs/latest` | Return latest MERT/CLAP analysis job. |
| `GET` | `/api/analyze/jobs/{job_id}` | Return one MERT/CLAP analysis job. |
| `POST` | `/api/analyze/jobs/{job_id}/cancel` | Request MERT/CLAP cancellation. |
| `GET` | `/api/sonara/analyze/jobs/latest` | Return latest Sonara job. |
| `GET` | `/api/sonara/analyze/jobs/{job_id}` | Return one Sonara job. |
| `POST` | `/api/sonara/analyze/jobs/{job_id}/cancel` | Request Sonara cancellation. |
| `GET` | `/api/genres/analyze/jobs/latest` | Return latest MAEST job. |
| `GET` | `/api/genres/analyze/jobs/{job_id}` | Return one MAEST job. |
| `POST` | `/api/genres/analyze/jobs/{job_id}/cancel` | Request MAEST cancellation. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/latest` | Return latest classifier job. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}` | Return one classifier job. |
| `POST` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}/cancel` | Request classifier cancellation. |
| `GET` | `/api/tags/genres/jobs/latest` | Return latest genre tag write job. |
| `GET` | `/api/tags/genres/jobs/{job_id}` | Return one genre tag write job. |
| `POST` | `/api/tags/genres/jobs/{job_id}/cancel` | Request genre tag write cancellation. |

### Analysis and Search

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analyze` | Start MERT or CLAP embedding analysis. |
| `POST` | `/api/sonara/analyze` | Start Sonara feature analysis. |
| `POST` | `/api/genres/analyze` | Start MAEST genre analysis. |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | Start classifier scoring. |
| `POST` | `/api/analysis/reset` | Reset one analysis family. |
| `POST` | `/api/search` | Search in MERT embedding space. |
| `POST` | `/api/search/sonara` | Search with Sonara features. |
| `POST` | `/api/search/text` | Search CLAP audio vectors from text. |

### Export, Tags, Dialogs, Media

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/export` | Export selected tracks as M3U or CSV. |
| `POST` | `/api/tags/genres/apply` | Apply MAEST genres immediately. |
| `POST` | `/api/tags/genres/jobs` | Start cancellable MAEST genre tag write job. |
| `POST` | `/api/dialog/folder` | Open a folder chooser dialog. |
| `GET` | `/media/{track_id}` | Serve browser-playable audio for one track. |

The frontend preview player uses `/media/{track_id}` and starts playback after a
preview button click. AIFF/AIF responses are transcoded to temporary WAV files
for browser compatibility and scrubbing support without rewriting source audio.

## Maintenance Scripts

Run scripts with the project Python environment when possible:

```powershell
.\.venv\Scripts\python.exe scripts\<script-name>.py --help
```

### `scripts\audio_repair\repair_audio_metadata.py`

Standalone diagnostic and repair helper for audio metadata/container issues.
Dry-run is read-only and does not copy or write audio files.

Usage:

```text
python scripts\audio_repair\repair_audio_metadata.py [OPTIONS] [paths ...]
```

Inputs:

- positional `paths`: audio files to inspect or repair.
- `--folder FOLDER`: recursively collect supported audio files from a folder.
- `--db DB`: collect existing audio files from `tracks.path` in a SQLite
  library database. The database is opened read-only.
- `--db-root PATH`: only use database paths under this stored root. Can be
  repeated.
- `--file-root PATH`: replace the matching `--db-root` prefix with this real
  filesystem root before checking whether each file exists.
- `--log LOG`: extract post-save readback-failed WAV paths from a project log.
- `--since TIMESTAMP`: only use log lines at or after a timestamp.
- `--until TIMESTAMP`: only use log lines before a timestamp.

Repair and safety options:

- `--apply`: write repaired files. Default is dry-run.
- `--backup-dir PATH`: backup directory used only with `--apply`.
- `--no-backup`: apply without full-file backups; use only if another backup
  exists.
- `--keep-id3 first|last|none`: for WAV repair, choose which readable top-level
  ID3 chunk to keep. Default is `first`.
- `--reason VALUE`: in folder or database mode, apply only entries with a
  stored reason. Can be repeated.

Run control:

- `--limit N`: process only the first collected paths.
- `--summary-only`: print only the final summary.
- `--color auto|always|never`: colorize status labels.
- `--file-log PATH`: file log path overwritten on every run.
- `--no-file-log`: disable the file log.
- `--state PATH`: explicit folder/database-mode state file.
- `--workers N`: parallel dry-run workers. Apply mode always runs sequentially.

Examples:

```powershell
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --workers 4
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --apply --reason OVERSIZED_DATA
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes\Abstracted
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes --file-root S:\Music\Volumes
python scripts\audio_repair\repair_audio_metadata.py .\music\track.wav --summary-only
```

Status meanings:

- `OK`: no repair needed.
- `NOTICE`: non-required cleanup.
- `SUSPICIOUS`: format/container or codec mismatch.
- `TAG-ERROR`: tag-read failure without a safe repair path.
- `REPAIRABLE`: safe repair logic exists.
- `REPAIRED`: apply mode succeeded.

### `scripts\audio_dedup\audio_dedup.py`

Report-only duplicate-audio candidate helper. It reads an existing
`dj-track-similarity` SQLite database, compares tracks inside a selected stored
path root, and writes JSON, CSV, and text-log reports. It never deletes audio
files and never mutates the database.

Usage:

```text
python scripts\audio_dedup\audio_dedup.py --root ROOT [OPTIONS]
```

Options:

- `--db DB`: project SQLite database. Default is `C:\db\abstracted.sqlite`.
- `--root ROOT`: required stored path root used to limit candidate tracks.
- `--path-contains TEXT`: additional case-insensitive path filter. Can be
  repeated.
- `--preset safe|balanced|aggressive`: scoring preset. Default is `safe`.
- `--min-score SCORE`: override the preset duplicate threshold.
- `--limit-groups N`: write at most N duplicate groups.
- `--out-dir DIR`: output report directory. Default is
  `scripts\audio_dedup\reports`.

Examples:

```powershell
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music --preset balanced --path-contains mastered
```

Outputs are named `audio_dedup_report_<timestamp>.json`, `.csv`, and `.log`.
The default report directory is ignored by git. Review every candidate manually;
the report includes suggested keepers and candidate-delete evidence, but the
script intentionally performs no delete action.

### `scripts\migrate_sonara_brightness.py`

Dry-run-first helper for legacy databases that still have
`metadata_json.sonara_features.brightness`. It migrates that key to
`spectral_centroid_mean` without touching audio files.

Usage:

```text
python scripts\migrate_sonara_brightness.py [--db DB] [--apply] [db]
```

Examples:

```powershell
python scripts\migrate_sonara_brightness.py --db .\data\library.sqlite
python scripts\migrate_sonara_brightness.py --db .\data\library.sqlite --apply
```

### `scripts\strip_sonara_descriptions.py`

Dry-run-first helper that removes repeated Sonara feature `description` fields
and full `chord_sequence` payloads from `metadata_json`.

Usage:

```text
python scripts\strip_sonara_descriptions.py [--apply] db
```

Examples:

```powershell
python scripts\strip_sonara_descriptions.py .\data\library.sqlite
python scripts\strip_sonara_descriptions.py .\data\library.sqlite --apply
```

### `scripts\backfill_maest_syncopated_rhythm.py`

Dry-run-first helper that backfills
`metadata_json.maest_syncopated_rhythm` for existing MAEST results.

Usage:

```text
python scripts\backfill_maest_syncopated_rhythm.py [--apply] db
```

Examples:

```powershell
python scripts\backfill_maest_syncopated_rhythm.py .\data\library.sqlite
python scripts\backfill_maest_syncopated_rhythm.py .\data\library.sqlite --apply
```

### `scripts\diagnose_metadata_size.py`

Read-only metadata size diagnostics for a SQLite database.

Usage:

```text
python scripts\diagnose_metadata_size.py [--top TOP] db
```

Examples:

```powershell
python scripts\diagnose_metadata_size.py .\data\library.sqlite
python scripts\diagnose_metadata_size.py .\data\library.sqlite --top 50
```

### `scripts\optimize_database.py`

Optimizes a SQLite database that already matches the current schema contract. It
validates the schema, creates a backup, vacuums, analyzes, and verifies
integrity. It does not migrate, repair, or adapt databases from older schemas.

Usage:

```text
python scripts\optimize_database.py --db DB
```

Example:

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

This script writes to the database and creates a backup next to it. If the
database schema is not current, the script prints an error and stops before
creating a backup or modifying the database.

## Development Setup

Install development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Install Sonara support:

```powershell
python -m pip install -e ".[sonara,dev]"
```

Install ML dependencies:

```powershell
python -m pip install -e ".[ml,dev]"
```

Install the full local lab dependency set, including Rhythm Lab training:

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

Run backend tests:

```powershell
pytest
```

Build the frontend:

```powershell
cd frontend
npm run build
```

Run the frontend development server:

```powershell
cd frontend
npm run dev
```

For Python commands in this repository, prefer the project virtual environment
when available:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Verification Guidance

Use focused verification for code changes and script changes. Documentation-only
changes do not need the full test suite, but should be checked for stale local
paths and command accuracy.

Useful checks:

```powershell
dj-sim --help
dj-sim analyze --help
python scripts\audio_repair\repair_audio_metadata.py --help
python scripts\audio_dedup\audio_dedup.py --help
```
