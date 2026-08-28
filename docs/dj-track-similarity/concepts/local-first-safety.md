# Local-first safety model

`dj-track-similarity` is built around local files and local state. Normal workflows do not upload
audio files or tags to a service.

This page is the single source of truth for which actions can write to your audio files. Other
pages link here rather than repeating the list.

## Local state

The app can create or update local artifacts:

- One selected library `.sqlite` database and an optional `*.evaluation.sqlite` sidecar.
- Runtime logs under `logs/`.
- Exported M3U and CSV files.
- Audio Doctor and Audio Dedup JSON, XLSX, and log reports.
- Audio Doctor state files and temporary apply-time backups.
- Rhythm Lab labels, predictions, queues, checkpoints, and artifacts.
- Promoted classifier model files under `models/classifiers/`.

These files may reveal local paths, tags, scores, and listening decisions. Keep them out of Git
unless that is an explicit choice.

## Read-only with respect to audio

These operations do not modify source audio files:

| Workflow | Writes |
| --- | --- |
| Scan | SQLite track rows and metadata |
| Refresh Tags | SQLite metadata for existing tracks |
| Analysis | library analysis and embedding rows |
| Search | no data writes |
| Text-search preset feedback | one `text_preset_feedback` verdict row per track, preset, and model |
| LAB verdicts and Evaluation feedback | `pair_feedback` and `transition_feedback` rows |
| Browser preview | a temporary WAV only when transcoding is needed |
| Reset | library analysis records only, with Evaluation data untouched |
| Database clear | database records only |
| Single-track delete | the catalog row and its cascaded catalog data |
| Reveal in Explorer | nothing, it opens a file browser window at the track |
| Relocation preview | no data writes |
| Relocation apply | stored SQLite paths only |
| Export | a new M3U or CSV file |
| Classifier scoring | SQLite classifier scores |
| Liked-track toggle | SQLite liked state only |

### Deleting a track keeps its audio

`DELETE /api/tracks/{track_id}` removes the catalog row and every catalog table that references it,
and the source audio path is deliberately never opened. The browser confirms this in its own
dialog: `Аудиофайл <track> на диске останется` (the audio file stays on disk). Audio Dedup deletion
is the only workflow that removes an audio file.

### Marking a track missing checks the disk first

Refresh Tags marks a track missing when its file has disappeared. The database layer refuses that
write while the source path still exists, so a transient read error cannot flag a present file as
missing.

### Browser preview does not rewrite the source

AIFF, FLAC, APE, WavPack, WMA, DSD, and non-16-bit WAV files are transcoded for browser playback.
The transcode goes to a temporary file that is deleted after the response, and the source file is
neither rewritten nor cached.

## Source-file write paths

Three workflows can write or delete source audio files. Everything else in the app cannot.

### 1. MAEST genre tag apply

Writes the standard genre field for tracks with stored MAEST genres. This is the only backend
audio writer, and it is started explicitly from `Сохранить жанры` (save genres) in panel
`1. База и анализ` or from the CLI.

### 2. Audio Doctor apply

Audio Doctor repairs known-safe container and tag failures. It is a standalone CLI tool with no
route in the application, so nothing in the browser can start it.

Its real protections:

- **Dry-run first.** Without `--apply` the run is read-only and copies nothing.
- **Backup by default.** `--apply` copies the whole file into `tools/audio-doctor/data/backups`
  before writing. `--no-backup` skips that step, and the tool refuses `--backup-dir` together with
  `--no-backup`.
- **Structural verification.** After the write it re-reads the file, checks the RIFF or FORM header
  and its declared size, and requires a clean Mutagen readback.
- **Restore on failure.** If any check fails, the backup is copied back over the file before the
  error is raised.
- **Sequential apply.** `--workers` parallelizes dry runs only.

Two limits worth knowing. Apply mode takes no confirmation phrase and no interactive prompt, so
`--apply` writes as soon as the run reaches a repairable file. The backup is deleted once
verification passes, so it is a rollback buffer for that one write rather than an archive. Take
your own backup before a large apply run.

### 3. Audio Dedup deletion

Audio Dedup reports duplicate candidates first. Deletion is a separate action, and the two surfaces
gate it differently.

From the CLI, `--apply` prints a `DESTRUCTIVE APPLY REQUESTED` block naming the database, the root,
and the candidate count, then waits for the operator to type exactly `APPLY DELETE`. Anything else
cancels the run. Deletion is permanent and is limited to safe candidates inside the selected root.

From the browser reviewer, you mark copies, choose `В корзину` (recycle bin) or `Безвозвратно`
(permanent) in the `Куда` select, then answer a `Да` / `Нет` dialog. The delete endpoint still
requires the `APPLY DELETE` phrase in its request body, and the browser client supplies that string
itself. Nobody types it, and the delete button has no phrase field. The phrase stops a stray POST
from deleting audio rather than gating the person at the screen.

Both surfaces refuse a selection that would leave a duplicate group with no copies.

## Relocation is not a file mover

Relocation apply updates stored `tracks.file_path` in the library after it verifies the target
files exist and finds no conflicts. It does not move, copy, delete, or retag files. Relocation runs
from the CLI only.

## Database boundary

The library database owns one `catalog_uuid`. Keep its optional `*.evaluation.sqlite` sidecar with
the backup when it exists. Normal runtime does not rewrite a legacy split database or reconstruct
older layouts. The only supported legacy conversion is the confirmation-gated `dj-sim
migrate-database` command, run after every database user stops. It retains the original pair in a
timestamped backup and verifies the staged replacement before publishing it.

## Server binding

`dj-sim serve --host 127.0.0.1` is local-only. Use `0.0.0.0` or `run_server.cmd lan` only when you
intentionally want other devices on the local network to connect.

The local API has no authentication. In LAN mode, any device on that network reaches the same
endpoints as the browser, down to database clear and Audio Dedup deletion. Bind to `127.0.0.1`
unless you trust the whole network.

## Related pages

- [Tags and audio writes](../user-guide/tags-and-audio-writes.md)
- [Audio Doctor](../tools-and-scripts/audio-doctor.md)
- [Audio Dedup](../tools-and-scripts/audio-dedup.md)
- [Known limits](../help/known-limits.md)
