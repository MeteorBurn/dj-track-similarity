# Database reference

> Audience: Users and maintainers who need to know what local SQLite stores.
> Goal: Explain the database as local state, not a full schema dump.
> Type: reference

Selecting `library.sqlite` opens one catalog bundle:

| Store | File | Creation | Contents |
| --- | --- | --- | --- |
| Core | `library.sqlite` | required | catalog identity, tracks, file tags, SONARA scalars, MAEST scores, classifier scores, likes, feedback, FTS, and settings |
| Artifacts | `library.artifacts.sqlite` | required | dedicated MAEST/MERT/MuQ/CLAP and SONARA embedding tables, SONARA timeline rows, and fingerprints |
| Evaluation | `library.evaluation.sqlite` | optional | search sessions, result events, calibration runs, and evaluation settings |

Core and Artifacts are created together for a fresh path and are bound by one generated
`catalog_uuid`. Opening requires both files to use the expected schema and catalog identity. The
Evaluation path can be resolved without creating its database. An evaluation workflow creates that
database when needed and validates the same catalog identity.

Normal runtime validates required tables, columns, indexes, foreign keys, and the shared catalog
identity. It refuses an incompatible layout rather than adapting it during startup. Preview the
dedicated migration with `dj-sim migrate-database --db <path> --dry-run`.

## Core state

Core contains:

- `library_catalog` for catalog identity;
- `tracks` and `file_tags` for file identity, paths, technical facts, and Mutagen metadata;
- current SONARA scalar and fixed-vector values in `sonara`;
- MAEST labels and syncopation data in `maest_scores`;
- promoted classifier results in `classifier_scores`;
- likes, pair feedback, transition feedback, FTS, and library settings.

Track identity is composite: `catalog_uuid`, `track_id`, `track_uuid`, and
`content_generation`. Mutation requests use the expected identity so a stale client cannot silently
write against a replaced or re-scanned track. The stored path column is `tracks.file_path`.

## Artifacts state

The mandatory Artifacts database contains dedicated tables:

- `maest_embeddings`;
- `mert_embeddings`;
- `muq_embeddings`;
- `clap_embeddings`;
- `sonara_similarity_embeddings`;
- `sonara_timeline`;
- `sonara_fingerprints`.

Normal track responses return small summaries and availability flags. The explicit
`GET /api/tracks/{track_id}/sonara-timeline` route loads the stored timeline payload.

## Structural migration

Inspect an incompatible Core/Artifacts pair before changing it:

```powershell
dj-sim migrate-database --db .\data\library.sqlite --dry-run
```

Apply only after reviewing that plan. Rerun without `--dry-run` and type the exact confirmation
`MIGRATE DATABASE`. The command creates and validates self-contained backups of both databases,
rebuilds the required tables, and checks integrity, foreign keys, and cross-database orphans before
success. It does not rewrite Evaluation or start reanalysis.

## Classifier state

Promoted classifiers record their ordered feature names and required inputs. A changed or incomplete
recipe is blocked with a retrain-and-promote message instead of reusing incompatible scores. Reset
and scoring remain scoped by classifier key. Unrelated classifier scores are preserved.

## Write boundaries

- Scan, Refresh Tags, analysis, reset, clear, liked toggle, classifier scoring, feedback, and relocation apply write SQLite.
- Relocation apply changes only `tracks.file_path`. It does not move or modify audio.
- Database clear removes Core rows, matching Artifacts rows, and existing Evaluation payload rows. It does not delete audio.
- Reset removes only the active outputs for the requested analysis family and dependent SONARA classifier scores.
- Audio Dedup apply removes database rows only for files it actually deleted.
- Destructive work on `C:\db\volumes.sqlite` or another real library requires explicit approval and a verified backup first.

## Backup habit

Keep Core and Artifacts together. Include Evaluation when it exists. Before destructive SQLite
maintenance on a real library, back up the complete existing bundle or work on a copy, then verify
the backup and final database integrity.
