# dj-track-similarity

[Русская версия](README.ru.md)

Local DJ library analysis and similarity search for finding tracks that may work
near each other in a set.

`dj-track-similarity` is a personal, local-first tool for DJs and music
collectors. It scans a folder of audio files into SQLite, runs optional audio
analysis, and gives you a browser UI for inspecting tracks, searching by sound,
building temporary set ideas, and exporting playlists.

It is not a polished commercial product and not a formal audio research
benchmark. It is an enthusiast project built around a real local library, with
practical workflows kept ahead of broad claims.

![dj-track-similarity web UI](https://i.ibb.co/FkKt31n3/Q3n-Az-F6u7-T.png)

## Who This Is For

Use this project if you:

- collect local music files and want a searchable analysis database;
- prepare DJ sets and want more than BPM, key, and genre tags;
- want seed-track search, text-to-audio search, or explainable audio features;
- want to train small personal classifiers such as vocal presence or live
  instrumentation;
- are comfortable running a local Python app and keeping your music library on
  your own machine.

The repository does not include a demo music library. The first useful result
comes from scanning your own audio folder.

## What It Helps With

- Browse a large local library without loading every metadata field at once.
- Compare file tags, Sonara features, MAEST labels, embeddings, and classifier
  scores without mixing their sources.
- Find neighbors from selected seed tracks with SONARA or MERT.
- Search by text prompts such as `dark hypnotic techno, rolling bass, no vocals`
  after CLAP analysis.
- Generate ordered Smart Set Builder previews from manual seeds or automatic
  anchors.
- Train Rhythm Lab classifiers for personal concepts and promote them into the
  main app as reusable CLASS filters.
- Export temporary sets as M3U or CSV.

## Quick Start

These commands use PowerShell on Windows, which is the primary verified local
environment for this project.

Requirements:

- Python `>=3.10`
- FFmpeg on `PATH`, or `DJ_TRACK_SIMILARITY_FFMPEG` pointing to `ffmpeg.exe`
- Local audio files to scan

Create an environment and install the base development package:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Expected result:

```text
The dj-sim command is available in the active environment.
```

Create a local database and scan a music folder:

```powershell
New-Item -ItemType Directory -Force .\data
dj-sim scan D:\Music --db .\data\library.sqlite
```

Expected result:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

Start the local web UI:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Open:

```text
http://127.0.0.1:8765/
```

Expected result:

```text
The browser shows your scanned tracks. You can browse, inspect metadata, play
previews, choose seed tracks, and start analysis jobs from the UI.
```

There is also a Windows helper:

```powershell
scripts\run_server.cmd
```

For local-network access from another device on the same LAN:

```powershell
run_server_lan.cmd
```

## Add Audio Analysis

The base install is enough to scan, browse, serve the app, and use stored data.
Install optional analysis dependencies when you want model-backed features:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

For Rhythm Lab classifier training, include the lab extra:

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

Run a small Sonara pass first if you want an explainable search surface:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
```

Expected result:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> ...
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> models=sonara ...
```

Then refresh the web UI and use the SONARA tab or feature controls.

For full MAEST, MERT, and CLAP setup, including the verified Windows CUDA stack,
read [Installation](docs/dj-track-similarity/install.md).

## Common Workflows

### Browse and Inspect a Local Library

Scan a folder, start the server, then use the Library and metadata dialog in the
UI. File tags, model-derived values, and classifier scores are shown as separate
sources so disagreements remain visible.

### Find Similar or Compatible Tracks

Run the analysis family that matches your goal:

- SONARA for explainable rhythm, energy, loudness, tonal, and spectral features.
- MERT for seed-track audio similarity.
- CLAP for text-to-audio search.
- MAEST for generated genre labels, syncopated-rhythm filtering, and classifier
  inputs.

The SET tab can then build an ordered preview from manual seeds or automatic
anchors.

### Train Personal Classifiers

Use Rhythm Lab when generic similarity is not enough. It runs separately from
the main app, stores labels under `tools/rhythm-lab/data/`, and promotes runtime
models into:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

Typical flow:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Open:

```text
http://127.0.0.1:8777/
```

Expected result:

```text
Rhythm Lab opens for profile-based labeling, train-refresh, prediction review,
and promotion into the main app.
```

See [Rhythm Lab](docs/dj-track-similarity/rhythm-lab.md) before training or
promoting classifiers.

### Search by Text

After CLAP audio embeddings exist:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 25 --db .\data\library.sqlite
```

Expected result:

```text
<score>    <track_id>    <path>
```

### Export a Temporary Set

Use the web UI to add tracks to the current set, then export M3U or CSV. Export
writes playlist/report files only; it does not rewrite audio files.

## Installation Options

Dependency groups are defined in `pyproject.toml`:

| Extra | Use it when |
| --- | --- |
| `dev` | You want tests, linting, and normal local development. |
| `sonara` | You want Sonara playlist feature extraction. |
| `ml` | You want MAEST, MERT, CLAP, PyTorch, TorchCodec, and related ML packages. |
| `rhythm-lab` | You want local classifier labeling and training with scikit-learn. |
| `ann` | You want optional generated ANN sidecar indexes for embedding search experiments. |

Useful installs:

```powershell
python -m pip install -e ".[dev]"
python -m pip install -e ".[sonara,ml,dev]"
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

Check the environment:

```powershell
dj-sim --help
dj-sim doctor
```

Expected result:

```text
dj-sim doctor reports Python, PyTorch, CUDA visibility, and the device selected
by auto.
```

## Configuration

Most commands accept `--db <path>`. If no database is supplied, the default is
`dj-track-similarity.sqlite` in the repository root or the app asks you to pick a
database in the UI.

FFmpeg is required for server startup and robust audio decoding. Put FFmpeg on
`PATH` or set:

```text
DJ_TRACK_SIMILARITY_FFMPEG
```

On Windows, TorchCodec-backed Torchaudio decoding needs an FFmpeg shared build
with DLLs on `PATH`, not only a standalone static `ffmpeg.exe`. The verified
setup is documented in [Installation](docs/dj-track-similarity/install.md).

## Safety and Limitations

Default app workflows are database-first and read-only for audio files:

- scan, RefreshTags, analysis, search, preview, reset, relocation preview, and
  export do not modify audio files;
- classifier scoring writes only SQLite `track_classifier_scores`;
- library relocation updates only stored SQLite paths;
- database clear deletes local SQLite rows only;
- browser AIFF/AIF preview may transcode to a temporary WAV stream, but it does
  not rewrite the source file.

Explicit exceptions:

- the genre-save workflow can write stored MAEST labels into standard audio
  genre tags;
- the standalone audio repair helper is separate, dry-run-first, and can rewrite
  only repairable files when run with `--apply`.

Known practical limits:

- model analysis can be slow on CPU;
- CLAP, MERT, and MAEST require optional ML dependencies;
- useful classifier models require enough consistent local labels;
- score thresholds may need local calibration because every music library is
  different;
- this project is public, but local databases, logs, reports, and trained models
  may contain private library information and should not be committed casually.

## Troubleshooting

### `dj-sim` Is Not Found

Activate the virtual environment and reinstall the package:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### The Server Fails on FFmpeg

Install FFmpeg, add its `bin` folder to `PATH`, or set
`DJ_TRACK_SIMILARITY_FFMPEG`. On Windows ML decoding, use a shared FFmpeg build
with DLLs on `PATH`.

### Text Search Returns Nothing Useful

CLAP text search needs CLAP audio embeddings first:

```powershell
dj-sim analyze --models clap --db .\data\library.sqlite
```

### A Promoted Classifier Was Retrained

After promoting a new classifier model, recompute that classifier's scores. The
main UI classifier row does this by resetting only that classifier's stored
scores and then rescoring it.

## Documentation

Start here:

- [Project guide](docs/dj-track-similarity/project-guide.md)
- [Installation](docs/dj-track-similarity/install.md)
- [Overview](docs/dj-track-similarity/overview.md)
- [Analysis families](docs/dj-track-similarity/analysis.md)
- [Search and tags](docs/dj-track-similarity/search-and-tags.md)
- [Rhythm Lab](docs/dj-track-similarity/rhythm-lab.md)
- [CLI reference](docs/dj-track-similarity/cli.md)
- [Web API](docs/dj-track-similarity/api.md)
- [Development](docs/dj-track-similarity/development.md)

## Development

Run backend tests:

```powershell
pytest
```

Build the frontend bundle served by the backend:

```powershell
cd frontend
npm run build
```

Build the docs site for local preview or deployment:

```powershell
cd docs\dj-track-similarity
npm run build
```

The docs build output is written to `docs/dj-track-similarity/site/` and is not
tracked in Git. If that folder is missing, the backend `/docs/` route shows a
short "documentation is not built" page.

There is currently no separate `CONTRIBUTING.md` or license file in the
repository. Use the development guide and focused tests as the source of truth
for local changes.
