# dj-track-similarity

A local-first DJ library workbench for a local music folder. It stores tag scans in SQLite. Optional analysis and set-prep tools stay local.

This is a public personal project for self-managed DJ libraries. It is not a commercial recommendation service and it is not a benchmark. Treat the model outputs as ranking signals: useful for shortlisting tracks, never a substitute for listening.

![dj-track-similarity web UI](https://i.ibb.co/FkKt31n3/Q3n-Az-F6u7-T.png)

## Main jobs

- Scans local audio files into a SQLite database with Mutagen metadata.
- Browses large libraries through a paginated web UI.
- Shows metadata, analysis coverage, likes, audio preview, and search/set state.
- Runs SONARA, MAEST, MERT, and CLAP analysis jobs.
- Searches from seed tracks with MERT and SONARA.
- Searches from text prompts with CLAP after CLAP audio embeddings exist.
- Builds Smart Set Builder previews from selected seeds or automatic anchors.
- Offers a Hybrid preview for weighted MERT, MAEST, SONARA, and CLAP candidate checks.
- Reads promoted Rhythm Lab classifier scores for filtering, SET biasing, and Hybrid diagnostics.
- Exports the current set as M3U or CSV.
- Includes report-first helper tools for Audio Doctor, Audio Dedup, database optimization, and optional ANN sidecar indexes.

## How the pieces fit

```text
audio files -> scan tags -> SQLite library -> browse/search/export
      |                         ^
      +---- analysis jobs -------+
```

The app keeps evidence sources separate:

- **File tags** come from Mutagen during scan and Refresh Tags.
- **SONARA** stores audio features such as rhythm, dynamics, timbre, tonal signals, BPM, key, duration, and energy.
- **MAEST** stores genre labels and an audio embedding.
- **MERT** stores an audio embedding for seed similarity.
- **CLAP** stores an audio embedding for text-to-audio search and audio-to-audio comparison.
- **Rhythm Lab classifiers** store optional local scores under a classifier key.

## Quick start

Verified local development is Windows-first, but the Python package and web app are ordinary local tools. The command examples assume the environment is active.

You need:

- Python `>=3.10`
- FFmpeg on `PATH`, or `DJ_TRACK_SIMILARITY_FFMPEG` pointing to the ffmpeg executable
- A local folder of audio files
- Node.js only when you build the frontend or docs from source

Install the base package:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Create a database and scan a music folder:

```powershell
mkdir data
dj-sim scan D:\Music --db .\data\library.sqlite
```

Start the web UI:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Open:

```text
http://127.0.0.1:8765/
```

There is also a Windows launcher that activates `.venv` and forwards remaining arguments to `dj-sim serve`:

```powershell
run_server.cmd local --db C:\db\abstracted.sqlite
run_server.cmd lan --db C:\db\abstracted.sqlite
```

`local` binds to `127.0.0.1`. `lan` binds to `0.0.0.0` and prints a LAN URL.

## Add model-backed analysis

The base install is enough for scan, browse, UI serving, existing SQLite data, and set export. Install optional analysis dependencies when you want the model jobs:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

Run a small first pass:

```powershell
dj-sim analyze --models sonara,maest,mert,clap --limit 25 --db .\data\library.sqlite
```

Useful options from the current CLI and API are:

- `--models sonara,maest,mert,clap`
- `--device auto|cpu|cuda`
- `--top-k 1..10` for MAEST labels
- `--track-batch-size 1..64`
- `--inference-batch-size 1..128`
- `--diagnostics` to write decoder and batch timing details to the file log

In the CLI, omit `--limit` to analyze the whole library. In the UI, `Analyze limit = 0` means the whole library.

## Main UI surfaces

The browser UI is split into three working areas:

1. **Database and analysis**: choose a SQLite database, choose a music folder, scan, refresh tags, run analysis, reset analysis results, write MAEST genres, and clear the database.
2. **Library browser**: use paginated search and row actions for metadata, preview, likes, seeds, and current-set changes.
3. **Search and set preparation**: use SET, SONARA, MERT, CLAP, CLASS, Hybrid preview, playlist export, and Rhythm Lab collection save.

The search panel uses these tabs:

- **SET** builds a read-only ordered set preview. Manual mode uses selected seeds. Auto mode chooses anchors from feature-complete tracks.
- **SONARA** searches from seed tracks with feature mixer and modifier controls.
- **MERT** searches from selected seeds in the MERT embedding space.
- **CLAP** searches from text prompts against stored CLAP audio embeddings.
- **CLASS** filters and rescans promoted local classifier profiles.

CLAP text-search scores are not the same scale as seed-based audio-to-audio scores. Good text results can have lower raw scores. Do not compare them directly with MERT scores or Audio Dedup thresholds.

## Maintenance tools

- **Audio Doctor** checks audio metadata/container issues. It is dry-run-first. Apply mode requires exact `APPLY REPAIR` and existing dry-run state.
- **Audio Dedup** reports duplicate candidates from stored analysis data. Apply mode requires exact `APPLY DELETE` and deletes only safe candidates inside the selected root.
- **Persistent ANN indexes** are optional generated sidecars for repeated vector lookup. Missing or stale indexes fall back to exact search where supported.
- **Database optimization** backs up the SQLite file, runs integrity checks, and then runs SQLite maintenance commands.

## Safety model

Default workflows do not modify source audio files:

- scan
- Refresh Tags
- analysis
- search
- audio preview
- analysis reset
- database clear
- relocation preview
- set generation
- export
- classifier scoring

Explicit write paths are narrow:

- MAEST genre tag apply writes the standard genre field in audio files.
- Audio Doctor apply can repair previously reported repairable files.
- Audio Dedup apply can delete confirmed duplicate candidates.
- Library relocation apply updates stored SQLite paths only. It does not move, copy, delete, or retag audio files.

SQLite databases, logs, reports, generated indexes, and promoted classifier artifacts can reveal library information. Keep them out of Git unless you intentionally choose otherwise.

## Documentation

Start here:

- [Project guide](docs/dj-track-similarity/project-guide.md)
- [Quickstart](docs/dj-track-similarity/getting-started/quickstart.md)
- [Install](docs/dj-track-similarity/getting-started/install.md)
- [First library](docs/dj-track-similarity/getting-started/first-library.md)
- [First analysis](docs/dj-track-similarity/getting-started/first-analysis.md)
- [Browse library](docs/dj-track-similarity/user-guide/browse-library.md)
- [Search with seeds](docs/dj-track-similarity/user-guide/search-with-seeds.md)
- [Smart Set Builder](docs/dj-track-similarity/user-guide/smart-set-builder.md)
- [Text search](docs/dj-track-similarity/user-guide/text-search.md)
- [Local-first safety](docs/dj-track-similarity/concepts/local-first-safety.md)
- [Tools and scripts](docs/dj-track-similarity/tools-and-scripts/index.md)
- [CLI reference](docs/dj-track-similarity/reference/cli.md)

## Development checks

Run backend tests:

```powershell
python -m pytest
```

Build the frontend bundle served by the backend:

```powershell
cd frontend
npm run build
```

Check and build the docs:

```powershell
cd docs\dj-track-similarity
npm run check
```

Run `npm run vale:sync` once after a fresh checkout or when `.vale.ini` packages change.
