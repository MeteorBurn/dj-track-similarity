# Build your first library

> Audience: Users adding local tracks for the first time.
> Goal: Scan a music folder into SQLite and understand what the scan writes.
> Type: tutorial

## What a library is

A library is a SQLite database with track paths, file facts, readable Mutagen tags, metadata JSON, and analysis flags. Scan reads metadata and writes SQLite rows; it does not retag audio.

## Scan

```powershell
dj-sim scan <music-folder> --db .\data\library.sqlite
```

## UI path

Start the server, choose or enter a music folder, start scan, watch the process log, then browse the paginated library list.

## Refresh Tags

Refresh Tags repeats the metadata read for existing rows and updates SQLite only.
