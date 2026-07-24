# Build your first library

> Audience: Users creating a SQLite library from a music folder.
> Goal: Understand scan, Refresh Tags, browsing, and database selection.
> Type: tutorial

A library is the app's private map of your music collection. It lets you search one catalog even
when the files are spread across folders and their tags are incomplete. Your audio stays in its
original location.

## What you get after a scan

- one browsable list of supported audio files,
- searchable artist, title, album, genre, path, and other available tags,
- stable track rows that later analysis can attach results to,
- scan counts that show what was added, updated, unchanged, or skipped.

Scanning does not make sound-based search available by itself. It creates the catalog first; the
next step, [analysis](./first-analysis.md), adds audio evidence for similarity search, text search,
and SET previews.

## How the catalog is stored

The current Python runtime is a greenfield schema-v7 bundle. The selected Core file stores track
identity, paths, tags, small analysis rows, likes, and classifier scores. Its required companion is
`*.artifacts.sqlite`, which holds large embeddings, SONARA Timeline payloads, and fingerprints. The
two files must carry the same `catalog_uuid`. The runtime validates that binding before use.

`*.evaluation.sqlite` is an optional adjacent database for evaluation data. It is not created just
by resolving its path. Earlier v5/v6 layouts, including `*.timeline.sqlite` and
`*.representations.sqlite`, are not migrated by the v7 runtime.

## Choose or create a database

From the CLI, pass `--db`:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

The frontend v7 port is deferred. Do not rely on the current browser controls for a v7 library;
use the CLI or API contracts while the UI is being ported.

## Scan a folder

CLI:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

The verified v7 scan surface is the CLI command above. It creates a fresh, bound Core + Artifacts
pair when neither file exists. It does not convert an older database.

Scan supports these extensions:

```text
.aif .aiff .alac .flac .m4a .mp3 .ogg .opus .wav .wave
```

It skips AppleDouble-style files whose names start with `._`.

## What scan reads

Scan reads a fixed, human-useful metadata set through Mutagen: artist, title, album, genre, year, country, label, catalog number, track number, disc number, BPM, key, comments, ISRC, duration, audio format, and codec data when available.

If a tag cannot be read, scan still creates a minimal metadata row with the file stem as title.

## What scan writes

Scan writes Core track and tag rows only. It updates a track when file size or modification time
changes and does not write audio tags.

The CLI prints added, updated, unchanged, and skipped counts.

## Refresh Tags

The v7 backend can reread file tags for existing tracks without rerunning SONARA, MAEST, MERT,
MuQ, or CLAP. Its browser control is deferred with the frontend port, so use the current CLI/API
surface rather than treating the old UI instructions as available.

## Browse after scan

The v7 backend/API has typed library queries, but the frontend controls are not yet v7-compatible.
Treat existing browser instructions as deferred until the frontend port lands.
