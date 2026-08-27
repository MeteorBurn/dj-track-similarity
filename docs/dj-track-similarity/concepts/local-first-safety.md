# Local-first safety model

`dj-track-similarity` is built around local files and local state. Normal workflows do not require uploading audio files or tags to a service.

## Local state

The app can create or update local artifacts:

- One selected library `.sqlite` database and an optional `*.evaluation.sqlite` sidecar.
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
| Analysis | library analysis and embedding rows |
| Search and Evaluation | Usually no data writes, except explicit feedback and evaluation rows |
| Browser preview | Temporary WAV only when transcoding is needed |
| Reset | library analysis records only; Evaluation data remains separate when present |
| Database clear | database records only; it does not touch source audio |
| Relocation preview | no data writes |
| Relocation apply | stored SQLite paths only |
| Export | new M3U or CSV file |
| Classifier scoring | SQLite classifier scores |
| Liked-track toggle | SQLite liked state only |

## Source-file write paths

Only these workflows can write or delete source audio files:

1. **MAEST genre tag apply** writes the standard genre tag field for tracks with stored MAEST genres.
2. **Audio Doctor apply** repairs files from a prior dry-run state after exact `APPLY REPAIR` confirmation.
3. **Audio Dedup deletion** removes duplicate files after exact `APPLY DELETE` confirmation. The CLI
   `--apply` run deletes the report's safe candidates permanently. The browser review deletes the
   copies you marked, to the recycle bin unless you choose a permanent delete. Both refuse a group
   that would lose every copy, and both leave source audio untouched until the phrase is typed.

## Relocation is not a file mover

Relocation apply updates stored `tracks.file_path` in the library after it verifies the target files exist
and no conflicts are detected. It does not move, copy, delete, or retag files.

## Database boundary

The library database owns one `catalog_uuid`. Keep its optional `*.evaluation.sqlite` sidecar with
the backup when it exists. Normal runtime does not rewrite a legacy split database or reconstruct
older layouts. The only supported legacy conversion is the confirmation-gated `dj-sim
migrate-database` command after all database users stop; it retains the original pair in a
timestamped backup and verifies the staged replacement before publishing it.

## Server binding

`dj-sim serve --host 127.0.0.1` is local-only. Use `0.0.0.0` or `run_server.cmd lan` only when you intentionally want other devices on the local network to connect.
