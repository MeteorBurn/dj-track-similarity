# Project Overview

This page covers what `dj-track-similarity` is, what it does, and which safety
boundaries apply to normal app workflows. Read it first if you are deciding
whether the project fits your local DJ library workflow.

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

Use the CLI when you want repeatable commands, batch work, or quick checks. Use
the web UI when you want to browse, listen, compare candidates, tune search
controls, export a temporary set, or review metadata before taking action.

## Typical Workflow

The usual path through the app is:

1. Choose or create a SQLite database.
2. Scan a music folder.
3. Run one or more analysis passes: Sonara, MAEST, MERT, or CLAP.
4. Browse the paged library, inspect track metadata, and choose seed tracks.
5. Search with SONARA, MERT, or CLAP.
6. Assemble a temporary set and export it as M3U or CSV.
7. Optionally score promoted classifier profiles.
8. Optionally write MAEST genres into standard audio genre tags.

You do not need to run every analysis family. A practical starting point is:

- Run `scan` first so the library exists in SQLite.
- Run Sonara when you want fast explainable similarity and library feature
  filters.
- Run MAEST when you want generated genre labels or the `syncopated` preset.
- Run MERT when you want seed-track audio similarity from embeddings.
- Run CLAP when you want text prompts such as "dark hypnotic techno".
- Run promoted classifiers only after Sonara, MERT, and MAEST data exist for
  the tracks you want to score.

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
and codec mismatches for more formats. See
[the audio metadata repair script](scripts/repair-audio-metadata.md) for that
workflow.
