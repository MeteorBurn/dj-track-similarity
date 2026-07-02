# Know when audio files can be written

> Audience: Users who want to avoid accidental edits to source files.
> Goal: Separate read-only workflows from explicit file-writing workflows.
> Type: guide

Most app workflows are read-only with respect to source audio. The source file exceptions are intentional and narrow.

## Read-only for audio files

These workflows do not edit audio files:

- scan,
- Refresh Tags,
- SONARA, MAEST, MERT, and CLAP analysis,
- MERT, SONARA, CLAP, SET, and Hybrid search,
- browser preview,
- analysis reset,
- classifier scoring,
- database clear,
- relocation preview,
- relocation apply,
- export to M3U or CSV.

They may still write SQLite rows, logs, reports, temporary preview WAV files, generated sidecars, or export files.

## MAEST genre tag apply

The genre save button starts a genre tag job for all tracks with stored MAEST genres. The API rejects per-track genre writes. Current behavior is all available MAEST genre rows.

The job writes only the standard genre field:

| Format | Tag field |
| --- | --- |
| MP3 | ID3 `TCON` |
| WAV/WAVE | Mutagen WAVE/ID3 genre handling, read back as `TCON` |
| AIFF | ID3 genre handling |
| FLAC | `GENRE` |
| M4A/MP4/ALAC | `©gen` |

It preserves normal tags such as title, artist, album, BPM, key, and other fields. After a successful write, the app refreshes the scanned metadata for that track in SQLite.

Failed writes are recorded per track and the batch continues.

## Audio Doctor apply

Audio Doctor is dry-run-first. Apply mode requires exact `APPLY REPAIR` and prior state, then repairs only files reported as repairable. Apply runs sequentially and creates backups by default in the standalone tool.

## Audio Dedup apply

Audio Dedup reports duplicate candidates by default. Apply mode requires exact `APPLY DELETE`. It then deletes only safe duplicate candidates inside the selected root and removes SQLite rows only for tracks whose files were deleted.

## Relocation apply

Relocation apply updates stored SQLite paths only. It rejects conflicts and missing target files before applying. It does not move, copy, delete, or retag audio files.
