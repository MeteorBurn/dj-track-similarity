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
LAB comparison, Audio Dedup, and classifiers.

## How the catalog is stored

The selected library file stores track identity, paths, tags, analysis rows, embeddings, likes, and
classifier scores. Its one `library` row carries the `catalog_uuid` and selected scan roots.

`*.evaluation.sqlite` is an optional adjacent database for evaluation data. It is not created just
by resolving its path. Normal startup refuses a legacy split layout instead of adapting it.

## Choose or create a database

In the browser, click the database button beside the read-only path field and select the library
SQLite file. Selecting a new path creates the current library schema; an existing path loads only
after the runtime validates its `library` identity. Switching the database also clears old
library/search state so a late response cannot leak rows from the previous catalog.

From the CLI, pass `--db`:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

## Scan a folder

In the browser:

1. Choose the database.
2. Enter **Music root** or use the folder picker.
3. Adjust **Scan workers** when needed.
4. Click **Load tracks into the database**.

The scan job shows queued/running progress, counts, errors, cancellation, and completion in the
activity panel. The browser refreshes the typed library summary when the job finishes.

The equivalent CLI command is:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

Both surfaces create a fresh library database when the selected file does not exist. A legacy split
database remains unchanged until you explicitly stop its users and run `dj-sim migrate-database`.

Scan supports these extensions:

```text
.aif .aiff .alac .flac .m4a .mp3 .ogg .opus .wav .wave
```

It skips AppleDouble-style files whose names start with `._`.

## What scan reads

Scan reads a fixed, human-useful metadata set through Mutagen: artist, title, album, genre, year, country, label, catalog number, track number, disc number, BPM, key, comments, ISRC, duration, audio format, and codec data when available.

If a tag cannot be read, scan still creates a minimal metadata row with the file stem as title.

## What scan writes

Scan writes library track and tag rows only. It updates a track when file size or modification time
changes and does not write audio tags.

The CLI prints added, updated, unchanged, and skipped counts.

## Refresh Tags

The backend can reread file tags for existing tracks without rerunning SONARA, MAEST, MERT,
MuQ, or CLAP. Click **Refresh Tags** in the database panel to start the typed refresh job. It uses
the current scan-worker value and reports progress through the same activity surface as scan.

## Browse after scan

The library panel reads one server-backed page of up to `200` tracks at a time. Use **Prev**,
**Next**, or the page-number field to move between pages. Each page maps to one `/api/tracks`
request with `limit=200`. The final page can contain fewer rows. All rows from the current page
render in one scrollable list.

The browser deduplicates each loaded result by `catalog_uuid` and `track_uuid`, keeping the highest
`content_generation`. Metadata opens from the detail endpoint only when requested; preview and
liked-track changes use the same exact track identity.
