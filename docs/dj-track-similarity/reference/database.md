# Database reference

Selecting `library.sqlite` opens one library database. A fresh selected path is
created directly in the current schema.

| Store | File | Creation | Contents |
| --- | --- | --- | --- |
| Library | `library.sqlite` | required | library identity, tracks, metadata, analysis, embeddings, classifier scores, feedback, and FTS |
| Evaluation | `library.evaluation.sqlite` | optional | saved evaluation profiles, search sessions, result events, and calibration runs |

The Evaluation file is absent until an Evaluation API or CLI path writes to it.
Opening a library never creates it.

Normal startup does not alter an existing database. It checks the singleton
`library` identity row, rather than maintaining a fixed allow-list of every
table, column, index, or trigger. That keeps future additions from blocking a
library that has the same identity. A legacy split database is converted only by
`dj-sim migrate-database --db PATH --confirm 'MIGRATE SINGLE LIBRARY'`, never at
startup. With all SQLite users stopped, the command first retains the old Core
and Artifacts files in a timestamped backup. It builds a staged current schema,
rebuilds FTS, verifies counts/integrity/foreign keys, then publishes the
one-file library. The old `library_settings` analysis counters are derived
cache values and are not carried into the current schema.

For an existing library that predates `mulan_embeddings`, the project owner performs the
one-time schema update outside the user-facing CLI. It adds only the separate table and never
derives MuQ-MuLan rows from existing `muq_embeddings`.

## Library tables

- `library`: one row with `catalog_uuid`, creation/update times,
  `schema_version = 1`, and `roots_json` for selected scan roots.
- `tracks`: stable track identity and file path, plus technical facts, scan
  state, and current content generation.
- `tags`: mutagen metadata for a track.
- `likes`: explicit liked state for a track.
- `sonara_features`: current SONARA scalar data and short fixed-size vectors.
- `sonara_embeddings`: one current unnormalized 48-dimensional `float32` SONARA embedding per track,
  bound to `track_uuid` and stored independently from Core features.
- `sonara_fingerprints`: one current versioned SONARA acoustic fingerprint per track, bound to
  `track_uuid` and containing native `fingerprint_base64` data plus `analyzed_at`.
- `maest_genres`: current MAEST genre labels and syncopation data.
- `maest_embeddings`, `mert_embeddings`, `muq_embeddings`, `mulan_embeddings`, and
  `clap_embeddings`: the current audio embedding for each model family. `mulan_embeddings` stores
  MuQ-MuLan's separate 512-dimensional L2-normalized vectors; it is not populated by converting
  `muq_embeddings`.
- `classifier_scores`: current promoted Rhythm Lab classifier scores.
- `pair_feedback` and `transition_feedback`: explicit evaluation feedback.
- `track_search_fts`: the FTS5 search index. SQLite owns its
  `track_search_fts_*` internal tables.

`catalog_uuid` and `track_uuid` are used when an operation must identify the
exact current track. The stored path is
`tracks.file_path`.

## Evaluation tables

The optional Evaluation database contains:

- `evaluation_profiles`: appended named JSON profiles (`profile_id`,
  `profile_name`, `profile_json`, `created_at`);
- `search_sessions`, `search_session_seeds`, and `search_result_events`;
- `calibration_runs`.

Saving an optimizer result with `dj-sim eval optimize-score-profile
--save-profile` records a profile only in this optional database. It does not
change search defaults or promote a Rhythm Lab classifier.

## Counts and write boundaries

`GET /api/library/summary` uses direct `COUNT(*)` queries against the library
tables. It does not cache counters or revalidate analysis payloads.

- Scan, tag refresh, analysis, reset, likes, classifier scoring, feedback, and
  relocation apply write library data.
- Clear removes library rows and scan roots; it does not delete source audio or
  the independent Evaluation database.
- Audio Dedup apply removes database rows only for files it actually deleted.
- Relocation apply changes only `tracks.file_path`; it does not move or modify
  audio.

## Backup habit

Before destructive maintenance on a real library, back up `library.sqlite` and
include `library.evaluation.sqlite` when it exists. Verify backup and final
SQLite integrity before continuing.
