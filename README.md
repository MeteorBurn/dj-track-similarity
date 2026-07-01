# dj-track-similarity

A local-first DJ library workbench for scanning music files, running audio analysis, finding related tracks, and preparing set ideas without uploading your collection anywhere.

`dj-track-similarity` is built for people who manage real local music libraries. It stores metadata and analysis results in SQLite, exposes a browser UI for day-to-day work, and keeps model outputs separate so you can see where each recommendation comes from.

It is a practical personal project, not a commercial recommendation service or a formal benchmark. The goal is simple: help you move faster from "I have a large folder of tracks" to "these are candidates worth listening to together."

![dj-track-similarity web UI](https://i.ibb.co/FkKt31n3/Q3n-Az-F6u7-T.png)

## What You Can Do

- Scan a local music folder into a searchable SQLite library.
- Browse tracks with paginated metadata, tags, analysis coverage, and audio preview.
- Run SONARA, MAEST, MERT, and CLAP analysis when you need richer search signals.
- Search by seed tracks with MERT or SONARA.
- Search by text prompts with CLAP after CLAP audio embeddings are available.
- Generate Smart Set Builder previews from selected seeds or automatic anchors.
- Train and promote personal Rhythm Lab classifiers for concepts such as vocals, live instrumentation, or energy shape.
- Export temporary sets as M3U or CSV.
- Use Audio Doctor and Audio Dedup as report-first maintenance tools.

## How It Thinks About Music

The app deliberately keeps different evidence sources separate:

- **File tags** come from the audio files through Mutagen.
- **SONARA features** describe measurable musical properties such as energy, rhythm, loudness, and tonal signals.
- **MERT, MAEST, and CLAP embeddings** are vector spaces for similarity search.
- **MAEST labels** help with genre-like browsing and tag workflows.
- **Classifier scores** come from your own promoted Rhythm Lab models.

Those scores are useful ranking signals, not objective truth. A good workflow is to use the app to shortlist candidates, then preview and decide by ear.

## Quick Start

Verified local development is Windows-first, using PowerShell and Python `>=3.10`.

You need:

- Python `>=3.10`
- FFmpeg on `PATH`, or `DJ_TRACK_SIMILARITY_FFMPEG` pointing to `ffmpeg.exe`
- A folder of local audio files

Create an environment and install the base package:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Create a local database and scan a folder:

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

The browser should show your scanned tracks. From there you can browse the library, open metadata, preview audio, choose seed tracks, and start analysis jobs.

There is also a Windows launcher:

```powershell
run_server.cmd local --db C:\db\abstracted.sqlite
run_server.cmd lan --db C:\db\abstracted.sqlite
```

## Add Analysis

The base install is enough for scanning, browsing, serving the UI, and using existing data. Install optional analysis dependencies when you want model-backed search:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

Run a small first analysis pass:

```powershell
dj-sim analyze --models sonara,mert,clap --limit 25 --db .\data\library.sqlite
```

In the UI, `Analyze limit = 0` means the whole library. Positive limits count tracks missing the selected analysis family.

For the full Windows ML stack, CUDA notes, and FFmpeg details, see [Install](docs/dj-track-similarity/getting-started/install.md).

## Search Modes

The main search surface is split into tabs:

- **SET** builds a read-only set preview from manual seeds or automatic anchors.
- **SONARA** searches with explainable audio features and optional mixer/modifier controls.
- **MERT** searches from selected seed tracks in MERT embedding space.
- **CLAP** searches with a text prompt against stored CLAP audio embeddings.
- **CLASS** filters or scores with promoted local classifier profiles.

CLAP text scores are usually lower than seed-based audio-to-audio scores. Useful CLAP text results may sit around `0.35-0.55`; they should not be compared directly with MERT seed-search scores or Audio Dedup thresholds. If the CLAP `Avoid` field is filled, the shown score is contrast evidence: positive prompt match minus negative prompt match.

## Personal Classifiers

Rhythm Lab is the companion workflow for labels and local classifiers. It runs separately, reads the main library for context, and stores labels under `tools/rhythm-lab/data/`.

Start it with:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Open:

```text
http://127.0.0.1:8777/
```

Promoted runtime models live under:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

Read [Classifiers and Rhythm Lab](docs/dj-track-similarity/concepts/classifiers-and-rhythm-lab.md) before training or promoting classifiers.

## Maintenance Tools

The repository includes helper tools for local-library maintenance:

- **Audio Doctor** is dry-run-first and can repair only files that were reported as repairable.
- **Audio Dedup** writes JSON/XLSX/log reports by default and deletes only after explicit `APPLY DELETE` confirmation.
- **Database optimization** should create a SQLite backup before maintenance work.

Audio Dedup uses audio-to-audio MERT, MAEST, CLAP, SONARA, and duration evidence. Its `Min similarity` gate is not the same scale as CLAP text search.

## Safety Model

Default workflows do not modify audio files:

- scan
- Refresh Tags
- analysis
- search
- preview
- reset
- relocation preview
- export
- classifier scoring

The explicit write paths are narrow:

- MAEST genre tag apply can write standard genre tags to audio files.
- Audio Doctor `--apply` can repair files after a dry run.
- Audio Dedup apply mode can delete confirmed duplicate candidates.
- Relocation apply updates stored SQLite paths only; it does not move files.

Local databases, logs, reports, and trained models may reveal private library information. Keep them out of Git unless you intentionally decide otherwise.

## Documentation

Start with:

- [Project guide](docs/dj-track-similarity/project-guide.md)
- [Quickstart](docs/dj-track-similarity/getting-started/quickstart.md)
- [Install](docs/dj-track-similarity/getting-started/install.md)
- [First library](docs/dj-track-similarity/getting-started/first-library.md)
- [First analysis](docs/dj-track-similarity/getting-started/first-analysis.md)
- [Search by text with CLAP](docs/dj-track-similarity/user-guide/text-search.md)
- [Similarity scores](docs/dj-track-similarity/concepts/similarity-scores.md)
- [Audio Dedup](docs/dj-track-similarity/tools-and-scripts/audio-dedup.md)
- [CLI reference](docs/dj-track-similarity/reference/cli.md)
- [API reference](docs/dj-track-similarity/reference/api.md)
- [Development](docs/dj-track-similarity/developer/development.md)

## Development

Run backend tests:

```powershell
python -m pytest
```

Build the frontend bundle served by the backend:

```powershell
cd frontend
npm run build
```

Build the docs site:

```powershell
cd docs\dj-track-similarity
npm run build
```

The docs build output goes to `docs/dj-track-similarity/site/` and is not tracked in Git.

There is currently no separate `CONTRIBUTING.md` or license file in the repository.
