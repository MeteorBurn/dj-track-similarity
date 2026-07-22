# Database reference

> Audience: Users and maintainers who need to know what local SQLite stores.
> Goal: Explain the database as local state, not a full schema dump.
> Type: reference

Selecting `library.sqlite` opens one catalog backed by three adjacent SQLite files:

| Store | File | Contents |
| --- | --- | --- |
| Core | `library.sqlite` | tracks, tags, SONARA scalars, MAEST scores, flags, likes, classifier state, FTS |
| Artifacts | `library.artifacts.sqlite` | required sidecar: all heavy BLOBs (MAEST/MERT/MuQ/CLAP/SONARA embeddings, timeline, fingerprints) |
| Evaluation | `library.evaluation.sqlite` | optional sidecar: search sessions and calibration metrics |

All three carry the same generated catalog ID. The app refuses a side database copied from another
catalog. Keep the files together when moving or backing up a library.

## Main library state

The database stores:

- track paths, size, mtime, and technical audio facts,
- working BPM, key, energy, duration, artist, title, and album fields,
- analysis presence derived from row and contract matches,
- `contracts` registry: append-only model identity (name, version, release hash, checkpoint),
- SONARA Core metadata: BPM, key, confidence, mood, instrumentalness, loudness, beat-grid, key-candidates, vocalness, silence, Contrast, MFCC, and Chroma fields,
- `maest_scores`: genre predictions and syncopated rhythm flags,
- liked tracks,
- classifier scores by `classifier_key`,
- FTS rows for library search,
- library settings such as the active SONARA release hash and promoted score profiles.

The Artifacts database preserves every heavy BLOB. This includes MAEST, MERT, MuQ, and CLAP embeddings, the optional SONARA similarity embedding, the SONARA timeline sequences, and the SONARA audio fingerprint. Regular track reads return only their field names, not the values.

The Evaluation database is optional and only exists if you run the score-profile optimizer. It records search sessions, result events, and calibration metrics.

## Schema migration

Opening a schema v6 main database migrates it to schema v7 and creates the artifacts sidecar. This
is intentionally a fresh SONARA migration. It keeps the catalog and MAEST metadata together with the
MAEST/MERT/MuQ/CLAP embeddings and their flags. Likes, feedback, and embedding-only
classifier scores also remain. The migration deletes old SONARA values and curves. SONARA-dependent classifier scores become invalid. Schema v5 and older databases
are rejected rather than adapted.

The project also records the SONARA classifier feature revision in `library_settings`. On the first
main-database open after this revision changes, stored scores are invalidated when `feature_set` is
`combined` or any plus-separated source begins with `sonara`. This includes `sonara`, `sonara2`,
`sonara2vocal`, and their embedding combinations. Rhythm Lab records the same revision independently
and removes SONARA-dependent predictions when its labels database opens. Embedding-only scores and
predictions, Rhythm Lab labels, likes, pair feedback, and transition feedback are preserved. Old
model files are left in place for recovery, but SONARA-dependent manifests without the current
analysis signature cannot be scored. Retraining and promotion are required.

Do not confuse the version numbers: upstream SONARA analysis schema is `4`, the main SQLite schema
is `7`, the project SONARA feature revision is `5`, and the promoted classifier manifest version is
`2`. Revision `5` also signs `decoder_backend="sonara-symphonia"` and
`execution_path="analyze_batch"`.

## Write boundaries

- Scan, Refresh Tags, analysis, reset, clear, liked toggle, classifier scoring, feedback, and relocation apply write SQLite.
- Relocation apply changes only stored paths.
- Database clear deletes Core tracks and attached Artifacts rows, then rebuilds track FTS state. It does not delete audio files.
- Reset SONARA deletes Core metadata, Artifacts rows (timeline, embedding, fingerprint), and SONARA-dependent classifier scores.
- Reset SONARA removes its saved provenance and analysis signature together with its feature metadata. It does not remove labels or feedback.
- Audio Dedup apply removes SQLite rows only for tracks whose files were successfully deleted.
- Migrating `C:\db\abstracted.sqlite` or any real library requires explicit user approval.

## Backup habit

Before destructive SQLite maintenance on a real database, back up all matching files or work on a copy. The database maintenance script does this automatically where supported.
