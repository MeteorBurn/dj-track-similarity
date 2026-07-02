# Build your first library

> Audience: Users creating a SQLite library from a music folder.
> Goal: Understand scan, Refresh Tags, browsing, and database selection.
> Type: tutorial

A library is a local SQLite database. It stores paths, file stats, selected Mutagen metadata, analysis flags, embeddings, liked tracks, feedback rows, and optional classifier scores.

## Choose or create a database

From the CLI, pass `--db`:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

From the UI, use the database button in **1. Database and analysis**. The native dialog can choose an existing `.sqlite` file or set the path for a new one.

If the app starts without a selected database, the UI asks you to choose one before scan, search, or analysis can work.

## Scan a folder

CLI:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

UI:

1. Choose the SQLite database.
2. Enter or pick the music root.
3. Set **Scan workers**.
4. Click **Load tracks into database**.

Scan supports these extensions:

```text
.aif .aiff .alac .flac .m4a .mp3 .ogg .opus .wav .wave
```

It skips AppleDouble-style files whose names start with `._`.

## What scan reads

Scan reads a fixed, human-useful metadata set through Mutagen: artist, title, album, genre, year, country, label, catalog number, track number, disc number, BPM, key, comments, ISRC, duration, audio format, and codec data when available.

If a tag cannot be read, scan still creates a minimal metadata row with the file stem as title.

## What scan writes

Scan writes SQLite only. It upserts tracks by path and updates rows when file size or modification time changes. It does not write audio tags.

The UI scan job shows progress, events, current path, counts, and cancellation state. The CLI prints added, updated, unchanged, and skipped counts.

## Refresh Tags

Use **Refresh Tags** when files already exist in the library and you only want to reread file tags. This updates selected metadata fields in SQLite for existing tracks. It does not rerun SONARA, MAEST, MERT, MuQ, or CLAP.

## Browse after scan

The library browser uses server-side pagination. It supports `like` or FTS search mode, liked-track filtering, syncopated rhythm filtering, and classifier score filters when promoted classifiers exist.

Open a track details dialog only when you need full metadata. The list view stays lightweight for larger libraries.
