# Database reference

> Audience: Users and maintainers who need to know what local SQLite stores.
> Goal: Explain the database as local state, not a full schema dump.
> Type: reference

Selecting `library.sqlite` opens one schema-v7 catalog bundle:

| Store | File | Creation | Contents |
| --- | --- | --- | --- |
| Core | `library.sqlite` | required | catalog identity, tracks, file tags, contracts, SONARA scalars, MAEST scores, classifier scores, likes, feedback, FTS, and settings |
| Artifacts | `library.artifacts.sqlite` | required | dedicated MAEST/MERT/MuQ/CLAP and SONARA embedding tables, SONARA timeline rows, and fingerprints |
| Evaluation | `library.evaluation.sqlite` | optional | search sessions, result events, calibration runs, and evaluation settings |

Core and Artifacts are created together for a fresh path and are bound by one generated
`catalog_uuid`. Opening requires both files to use the expected schema and catalog identity. The
Evaluation path can be resolved without creating its database. An evaluation workflow creates that
database when needed and validates the same catalog identity.

The v7 runtime supports greenfield bundles only. Existing non-v7 databases are rejected with an
expected-clean-v7 error. The removed `migrate-v7` and `migrate-schema-v7` commands are not available
in the current CLI.

## Core state

Core contains:

- `library_catalog` and `contracts` for catalog and immutable analysis identity;
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
`GET /api/tracks/{track_id}/sonara-timeline` route loads the current signed timeline payload.

## SONARA release state

The current SONARA contract is package `0.3.1`, upstream schema `5`, playlist mode, sample rate
`22050`, BPM range `70..180`, and project feature revision `6`. It defines four independent output
kinds: `core`, `timeline`, `embedding`, and `fingerprint`.

Before writing a new SONARA release, run:

```powershell
dj-sim prepare-sonara-release --db .\data\library.sqlite --backup-dir .\backup --confirm "PREPARE SONARA RELEASE"
```

The command derives the loaded runtime identity; callers cannot provide a release hash or choose a
subset. It verifies a Core plus Artifacts backup pair and uses an ordered, receipt-backed activation
that can resume after interruption and fails closed on mismatched state. It removes prior SONARA and
SONARA-dependent classifier rows so releases cannot mix. It does not migrate an older database
schema.

## Classifier state

The runtime accepts promoted manifest version `2`. Version `1` and unversioned manifests are blocked
with a retrain-and-promote message. The promoted artifacts currently under `models/classifiers/`
still use version `1`, so they cannot score until their profiles are retrained and promoted again.
Reset and scoring remain scoped by classifier key. Unrelated classifier scores are preserved.

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
