# Getting started

> Audience: First-time users setting up a local library.
> Goal: Move from checkout to a searchable, analyzed SQLite database.
> Type: tutorial index

The shortest useful path is: install, scan, serve the UI, analyze a small batch, search, then decide by ear.

## Pages

- [Quickstart](./quickstart.md): the shortest path through scan, serve, and first analysis.
- [Install](./install.md): prerequisites, package extras, FFmpeg, frontend, and docs build notes.
- [First library](./first-library.md): how scanning works and what the database stores.
- [First analysis](./first-analysis.md): model choices, device options, limits, and UI behavior.

## What you need first

- A local folder of audio files.
- A local SQLite path where the app can create or open the library.
- FFmpeg available on `PATH` or through `DJ_TRACK_SIMILARITY_FFMPEG`.
- Optional model dependencies if you want SONARA, MAEST, MERT, MuQ, or CLAP analysis.

## Privacy habit

Treat the SQLite database, logs, reports, generated indexes, and classifier artifacts as private library data. They can include paths, tags, model scores, and listening notes.
