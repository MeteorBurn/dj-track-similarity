# Local-first safety model

> Audience: Users deciding what data the app touches.
> Goal: Make read paths, SQLite writes, and source-file writes clear.
> Type: concept

`dj-track-similarity` is built around local files and local state. Normal workflows do not require uploading audio files or tags to a service.

## Local state

The app can create or update local artifacts:

- SQLite databases such as `dj-track-similarity.sqlite` or a user-selected `.sqlite` file.
- Runtime logs under `logs/`.
- Exported M3U and CSV files.
- Audio Doctor and Audio Dedup JSON/XLSX/log reports.
- Audio Doctor state files.
- Optional ANN sidecar indexes.
- Rhythm Lab labels, predictions, queues, checkpoints, and artifacts.
- Promoted classifier model files.

These files may reveal local paths, tags, scores, and listening decisions. Keep them out of Git unless that is an explicit choice.

## Read-only with respect to audio

These operations do not modify source audio files:

| Workflow | Writes |
| --- | --- |
| Scan | SQLite track rows and metadata |
| Refresh Tags | SQLite metadata for existing tracks |
| Analysis | SQLite metadata, flags, embeddings, and scores |
| Search and SET | Usually no data writes, except evaluation rows when Hybrid feedback is recorded |
| Browser preview | Temporary WAV only when transcoding is needed |
| Reset | SQLite records only |
| Database clear | SQLite records only |
| Relocation preview | no data writes |
| Relocation apply | stored SQLite paths only |
| Export | new M3U or CSV file |
| Classifier scoring | SQLite classifier scores |
| Liked-track toggle | SQLite liked state only |

## Source-file write paths

Only these workflows can write or delete source audio files:

1. **MAEST genre tag apply** writes the standard genre tag field for tracks with stored MAEST genres.
2. **Audio Doctor apply** repairs files from a prior dry-run state after exact `APPLY REPAIR` confirmation.
3. **Audio Dedup apply** deletes safe duplicate candidates after exact `APPLY DELETE` confirmation.

## Relocation is not a file mover

Relocation apply updates `tracks.path` in SQLite after it verifies the target files exist and no conflicts are detected. It does not move, copy, delete, or retag files.

## Server binding

`dj-sim serve --host 127.0.0.1` is local-only. Use `0.0.0.0` or `run_server.cmd lan` only when you intentionally want other devices on the local network to connect.
