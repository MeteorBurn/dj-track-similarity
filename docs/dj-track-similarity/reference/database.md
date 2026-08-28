# Database reference

Selecting `library.sqlite` opens one library database. A fresh selected path is
created directly in the current schema.

| Store | File | Creation | Contents |
| --- | --- | --- | --- |
| Library | `library.sqlite` | required | library identity, tracks, metadata, analysis, embeddings, classifier scores, feedback, and FTS |
| Evaluation | `library.evaluation.sqlite` | optional | saved evaluation profiles, search sessions, result events, and calibration runs |

The Evaluation file is absent until an Evaluation API or CLI path writes to it.
Opening a library never creates it.

## Connection policy

Every connection the project opens applies the same settings before it does anything else:

| Setting | Value | Effect |
| --- | --- | --- |
| `journal_mode` | `WAL` | Enforced rather than requested. When the file cannot enter WAL, the open raises instead of continuing in another journal mode. |
| `busy_timeout` | `30000` ms | A writer blocked by another connection waits 30 seconds before it gives up. |
| `foreign_keys` | `ON` | Cascades from `tracks` actually run. |
| `synchronous` | `NORMAL` | The usual WAL pairing. |
| `temp_store` | `MEMORY` | Temporary tables and indexes stay in RAM. |
| `cache_size` | `-32768` | About 32 MiB of page cache per connection. |

In-memory databases are rejected, so `:memory:` and `file::memory:` are not valid selections.

Creating a fresh database is staged rather than in place. The project builds the schema in a
`.<name>.<hex>.create.tmp` sibling, runs an integrity check on it, then swaps it into position with
one `os.replace`. A `.<name>.create.lock` file guards that sequence across processes and releases on
a crash, so two backends pointed at the same new path cannot both publish a half-built file.

Writes go through one process-wide lock per resolved path. `LibraryDatabase` holds that lock and
takes it around every write, so a single process never has two writers on one file.

Normal startup does not alter an existing database. It checks the singleton
`library` identity row, rather than maintaining a fixed allow-list of every
table, column, index, or trigger. That keeps future additions from blocking a
library that has the same identity.

## Library tables

Tables in schema emission order.

| Table | Key columns and constraints |
| --- | --- |
| `library` | one row with `singleton_id = 1`, a unique `catalog_uuid`, `created_at`, `updated_at`, `schema_version` checked equal to `1`, and `roots_json` holding the selected scan roots as a JSON array |
| `tracks` | `track_id` autoincrement, unique `track_uuid`, unique `file_path`, `file_size_bytes`, `file_modified_ns`, `audio_format`, `sample_rate_hz`, `channel_count`, `bit_rate_bps`, `bit_depth`, `audio_duration_seconds` rounded to two decimals, `last_scanned_at`, `missing_since`, `created_at`, `updated_at` |
| `tags` | one row per track with `title`, `artist`, `album`, `track_number`, `label`, `country`, `year`, `tag_key`, `tag_bpm`, `comment`, `genres_json`, `tags_read_at` |
| `sonara_features` | one row per track holding the SONARA Core scalars, three fixed-size float32 blobs (`mfcc_mean_blob` 13 values, `chroma_mean_blob` 12, `spectral_contrast_mean_blob` 7), and the run provenance `analysis_schema_version`, `bpm_min`, `bpm_max` with a check that `bpm_max >= 2 * bpm_min`, plus `analyzed_at` |
| `sonara_embeddings` | one row per track, `dim` checked equal to `48`, `normalization` checked equal to `none`, a 192-byte `embedding_blob`, `track_uuid`, `analyzed_at` |
| `sonara_fingerprints` | one row per track with `track_uuid`, a positive `fingerprint_version`, the native `fingerprint_base64` value, and `analyzed_at` |
| `maest_genres` | one row per track with `syncopated_rhythm` of `0`, `1`, or `NULL`, a `genres_json` array, and `analyzed_at` |
| `maest_embeddings`, `mert_embeddings`, `muq_embeddings`, `mulan_embeddings`, `clap_embeddings` | identical shape per family: one row per track with `track_uuid`, a positive `dim`, `normalization` of `none` or `l2`, an `embedding_blob` checked to be `dim * 4` bytes, `analyzed_at`, and an index on `track_uuid` |
| `classifier_scores` | primary key `(track_id, classifier_key)`, plus `track_uuid`, `feature_set`, `feature_names_json`, `positive_label`, `predicted_class`, `score_bucket` of `low`, `medium`, or `high`, `score` and `confidence` in `0..1`, `probabilities_json`, `analyzed_at`, and an index on `(classifier_key, score DESC, track_id)` |
| `likes` | one row per liked track with `liked_at` |
| `pair_feedback` | `feedback_id`, `seed_track_id`, `candidate_track_id`, `rating` in `0..3`, `reason_tags_json`, `notes`, `source`, `created_at`, `updated_at`, unique on `(seed, candidate, source)` |
| `transition_feedback` | `transition_feedback_id`, `outgoing_track_id`, `incoming_track_id`, `rating` in `0..3`, `risk_tags_json`, `notes`, `source` fixed to `manual`, `created_at` |
| `text_preset_feedback` | primary key `(track_id, preset_key, analysis_family)`, `analysis_family` in `clap` or `mulan`, `verdict` in `-1` or `1`, `created_at`, `updated_at`, and an index on `(preset_key, analysis_family, verdict, track_id)` |
| `track_search_fts` | the FTS5 virtual table with `tokenize='unicode61'` over `file_path`, `title`, `artist`, `album`, `comment`, `label`, `country`, `year`, `track_number`, `file_genres`, and `maest_genres`, with `track_id` unindexed. SQLite owns its `track_search_fts_*` internal tables. |

Every derived table references `tracks(track_id)` with `ON DELETE CASCADE`.

`mulan_embeddings` stores MuQ-MuLan's separate 512-dimensional L2-normalized vectors. It is never
populated by converting `muq_embeddings`.

`catalog_uuid` and `track_uuid` are used when an operation must identify the
exact current track. The stored path is `tracks.file_path`. There is no content-generation column.
A file's content identity is the pair `file_size_bytes` and `file_modified_ns` recorded at scan time.

## Text preset feedback

`text_preset_feedback` is the only table that can appear in an existing library at runtime. Its DDL
uses `CREATE TABLE IF NOT EXISTS`, and `POST /api/search/text/feedback` runs that DDL plus its index
inside the same transaction as the first verdict write. A library created before the table existed
gains it on the first thumbs-up or thumbs-down in the PROMPT tab, which is an additive capability
rather than a migration of existing data.

One row holds one verdict per `(track, preset key, text model)`. A verdict of `0` sent to the API
deletes the stored rows for those presets instead of storing a third value, so the column check
allows `-1` and `1` only. `scripts/prompt_preset_tune.py` is the reader.

## Evaluation tables

The optional Evaluation database contains:

- `evaluation_profiles`: appended named JSON profiles (`profile_id`,
  `profile_name`, `profile_json`, `created_at`);
- `search_sessions`, `search_session_seeds`, and `search_result_events`;
- `calibration_runs`.

The file is created only under a cross-process lock and only when a workflow asks to write. Reads
against a missing sidecar return empty rather than creating it. Its rows name a track by ID but
cannot hold a foreign key into another file, so deleting a track purges those rows explicitly rather
than by cascade.

Saving an optimizer result with `dj-sim eval optimize-score-profile
--save-profile` records a profile only in this optional database. It does not
change search defaults or promote a Rhythm Lab classifier.

## Migration from the legacy pair

A legacy split database is converted only by
`dj-sim migrate-database --db PATH --confirm 'MIGRATE SINGLE LIBRARY'`, never at
startup. With all SQLite users stopped, the command first retains the old Core
and Artifacts files in a timestamped backup. It builds a staged current schema,
rebuilds FTS, verifies counts, integrity, and foreign keys, then publishes the
one-file library and writes a `migration-receipt.json`. Any failure restores the original pair.

The migration copies 13 tables: `tracks`, `tags`, `sonara_features`, `maest_genres`,
`maest_embeddings`, `mert_embeddings`, `muq_embeddings`, `mulan_embeddings`, `clap_embeddings`,
`classifier_scores`, `likes`, `pair_feedback`, and `transition_feedback`.

Three tables are created empty and never copied, because the legacy layout had no source for them:

- `sonara_embeddings`
- `sonara_fingerprints`
- `text_preset_feedback`

The first two are refilled by rerunning SONARA analysis, which selects a track whenever any of its
three outputs is missing. The old `library_settings` analysis counters are derived
cache values and are the one recorded exclusion. A migration that finds any other non-empty legacy
table with no destination refuses to run.

## Counts and write boundaries

`GET /api/library/summary` uses direct `COUNT(*)` queries against the library
tables. It does not cache counters or revalidate analysis payloads.

- Scan, tag refresh, analysis, reset, likes, classifier scoring, text preset feedback, and
  relocation apply write library data.
- Clear removes library rows and scan roots. It does not delete source audio or
  the independent Evaluation database. Its reported counters cover eight derived tables only:
  `sonara_features`, `maest_genres`, `classifier_scores`, and the five ML embedding tables. The
  cascade also removes SONARA embedding, SONARA fingerprint, likes, and feedback rows, and those are
  not counted in the response.
- Audio Dedup deletion removes database rows only for files it actually deleted. Its catalog removal
  refuses to drop a row while the source file is still present on disk, and it rechecks that
  immediately before the delete.
- Deleting one track row also removes that track's `search_session_seeds` and
  `search_result_events` rows from the optional Evaluation database. The sidecar
  is a separate file, so no foreign key cascades into it. This runs after the
  catalog delete commits, and it opens the sidecar only when it already exists.
  Both `DELETE /api/tracks/{track_id}` and Audio Dedup deletion take this path.
- Relocation apply changes only `tracks.file_path` and the matching `library.roots_json` entries. It
  rewrites paths in two passes through temporary unique values so a swap cannot collide with the
  `file_path` unique index. It does not move or modify audio.
- Analysis reset deletes whole tables for the requested family. `classifier_rows_deleted` in that
  response is a fixed `0`, and no reset path touches `classifier_scores`. See
  [API reference](./api.md#analysis-and-classifiers).
- Every transaction that writes an embedding table advances `PRAGMA
  user_version` before it commits. The counter dates the in-process cache of
  library vectors: a search compares it, plus the row counts, against the
  values its cached matrix was built from, and reloads when either moved. It is
  a header field rather than schema, so no table, column, or index carries it.
  An existing database needs no migration and starts counting at its next
  write. The value is a write counter only. It is not a schema version.

One savepoint per track covers the SONARA Core row together with its embedding and fingerprint
rows, so a track has all three or none of them. One failing track rolls back its own savepoint and
leaves the rest of the batch committed.

## Backup habit

Before destructive maintenance on a real library, back up `library.sqlite` and
include `library.evaluation.sqlite` when it exists. WAL means the `-wal` and `-shm` siblings matter
too, so copy the set after every writer has stopped. Verify backup and final
SQLite integrity before continuing.
