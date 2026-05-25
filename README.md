# dj-track-similarity

A personal experiment in building a local music-library tool for finding tracks
that feel close enough to work together in DJ sets.

This repository started as something useful for my own workflow. I collect
music, tag it in my own way, and spend a lot of time thinking about which
tracks can sit next to each other in a set. I am not a professional researcher
or audio engineer; this is an enthusiast project where I am trying ideas,
testing models on a real library, and slowly turning the useful parts into a
tool.

The repository is public because the problem is interesting, and maybe someone
else who collects, tags, or plays music will find the approach useful too.

![dj-track-similarity web UI](https://i.ibb.co/FkKt31n3/Q3n-Az-F6u7-T.png)

## What It Does

- Scans a local music folder and stores track metadata in SQLite.
- Reads a fixed, human-sized set of file tags through Mutagen and shows those
  tags separately from model-derived values.
- Refreshes Mutagen tags for already indexed tracks without rescanning paths or
  deleting analysis results.
- Can relocate stored track paths after moving the same music folder, without
  repeating completed analysis.
- Extracts focused Sonara playlist features for explainable seed-track search
  and track inspection.
- Builds MERT audio embeddings for audio-to-audio similarity search.
- Builds CLAP audio embeddings for text-to-audio search.
- Extracts MAEST genre labels and stores them in the local SQLite database.
- Scores a promoted Break Energy classifier for break-heavy drums, percussion,
  fills, and related drum-break texture using existing SONARA, MERT, and MAEST
  analysis data.
- Can explicitly save stored MAEST labels into standard audio genre tags.
- Keeps the library browser server-side paginated so large local databases stay
  usable.
- Lets you choose seed tracks, search for compatible tracks, preview results,
  assemble a temporary set, and export M3U or CSV files.
- Can reset one analysis family at a time, or clear the local SQLite database
  after confirmation.

The current focus is simple and practical: check whether modern audio embedding
models and explainable audio features can help find tracks that sound related,
without relying on BPM, key, or manually curated genre tags as the main signal.

## Current Status

The project is usable, but still experimental.

SONARA seed search is the primary explainable search path in the UI. MERT is
available as a separate seed-search tab, and CLAP is available for text-to-audio
search after CLAP audio embeddings have been analyzed. MAEST genre analysis is
available for local genre inspection and optional explicit genre tag writing.
The CLASS tab can run the Break Energy classifier after a model has been
promoted from the auxiliary Rhythm Lab tool into
`models/classifiers/break-energy/model.joblib`. Rhythm Lab lives under
`tools/rhythm-lab/` and keeps its training artifacts in
`tools/rhythm-lab/artifacts/break-energy/`.

The UI keeps file tags and model-derived values separate. This is intentional:
file tags, Sonara values, MAEST labels, MERT vectors, CLAP vectors, and
classifier scores can disagree, and each source answers a different question.

For the full manual, including CLI options, API endpoints, maintenance scripts,
database details, and advanced workflows, see
[docs/project-guide.md](docs/project-guide.md).

## Run The App

Install the project for local development:

```powershell
python -m pip install -e ".[dev]"
```

Install optional Sonara and ML dependencies when you need analysis features:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

For CUDA analysis on Windows, use the synchronized PyTorch stack that has been
tested with this project:

```powershell
python -m pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install torchcodec==0.13.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install -e ".[sonara,ml,dev]"
```

Start the server:

```powershell
dj-sim serve
```

Then open:

```text
http://127.0.0.1:8765/
```

There is also a Windows helper script:

```powershell
scripts\run_server.cmd
```

`ffmpeg` must be available on `PATH` or through `DJ_TRACK_SIMILARITY_FFMPEG`
for server startup and robust audio decoding. On Windows, TorchCodec-backed
Torchaudio decoding needs a shared FFmpeg build with DLLs on `PATH`; the
verified setup is GyanD `ffmpeg 8.1.1-full_build-shared`, for example
`C:\Utils\tools\ffmpeg\bin`.

## Full Guide

The complete documentation is in [docs/project-guide.md](docs/project-guide.md).
It covers CLI commands and arguments, API endpoints, maintenance scripts,
database details, analysis workflows, performance notes, and troubleshooting.

## Safety

- Scanning, analysis, search, preview, and export do not modify audio files.
- RefreshTags rereads file metadata and updates SQLite only.
- Library relocation updates only stored paths in SQLite.
- Analysis reset buttons delete only local SQLite analysis outputs.
- Break Energy scores are SQLite-only classifier outputs. They depend on
  SONARA, MERT, and MAEST data and can be recomputed from a promoted classifier
  model; they do not modify audio files.
- Database clear deletes local SQLite records only; it does not delete music
  files.
- The genre save action is the explicit app-level exception: it writes stored
  MAEST labels into the standard audio genre tag and should overwrite only that
  genre field.

## Roadmap

These are the directions that currently seem most useful, roughly in priority
order:

1. `Search calibration` - inspect real score distributions and choose practical
   defaults for similarity thresholds and controlled randomization.
2. `Auto chain` - build a set gradually by moving the search context forward.
3. `Sonara calibration` - inspect real result sets for the custom mixer,
   modifier controls, score breakdowns, and default thresholds.
4. `Mel/CNN similarity` - explore embeddings that better capture pattern,
   structure, groove, density, and spectral shape.
5. `Music feature similarity` - improve the explainable DSP layer with
   calibrated DJ-relevant features.
6. `Hybrid ranking` - combine MERT audio similarity and CLAP text/audio
   similarity after both score ranges are understood.
7. `DJ transition features` - add phrase, loudness, vocalness, density, and
   other transition-specific features.
8. `Classifier model benchmarks` - keep logistic regression as the small-data
   baseline, then compare Linear SVM with calibration, tree/boosting models for
   SONARA-style tabular features, and a small MLP once classifier profiles have
   enough labeled examples and hard negatives.
9. `MERT model upgrade` - add a heavier MERT model option after the current
   pipeline is stable.
10. `Scale improvements` - add an ANN index or cached embedding matrix for
   larger libraries.

## Development

Install for development:

```powershell
python -m pip install -e ".[dev]"
```

Install everything used by the full local lab:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

The current ML dependency set is pinned to PyTorch `2.11.0`, Torchaudio
`2.11.0`, Torchvision `0.26.0`, TorchCodec `0.13.0`, and `numpy>=1.26,<2.0`.
Use `dj-sim doctor` to confirm CUDA visibility before long analysis runs.

Run backend tests:

```powershell
pytest
```

Build the frontend:

```powershell
cd frontend
npm run build
```

Focused operational details live in
[docs/project-guide.md](docs/project-guide.md).
