# DB Optimization Plan

This plan is based on the current code, tests, `db_schema.py`, and the current
read-only performance checks against `C:\db\abstracted.sqlite`.

No schema, index, table, or field change is implemented in this branch unless it
is explicitly approved in a later step.

## Goals

- Keep library browsing, summary counters, search, and missing-analysis
  selection fast on large local libraries.
- Reduce JSON parsing and large `Track` payload creation on hot paths.
- Make cache invalidation exact and easy to reason about.
- Keep SQLite writes serialized through `LibraryDatabase`.
- Preserve audio-file safety: DB optimizations must not modify source audio.

## Baseline Already Observed

| Query/workflow | Current observation |
| --- | --- |
| Library summary counters | Single-digit milliseconds on `C:\db\abstracted.sqlite` in read-only smoke. |
| Library page | Single-digit milliseconds in read-only smoke. |
| Old combined missing-analysis selection | Around 715 ms in the first read-only baseline. |
| Two-phase lean missing-analysis selection | Around 108 ms in read-only smoke after using per-model candidate ID queries plus lean candidate rows. |

## No-Schema Hot-Path Checkpoint

Implemented in the current refactor branch without changing `db_schema.py`,
`CURRENT_SCHEMA_VERSION`, indexes, tables, or fields:

- `LibraryDatabase.list_analysis_candidates()` now uses one read connection for
  the candidate ID pass and lean candidate row hydration. This removes one
  SQLite open/close cycle from every analysis job creation while preserving the
  existing two-phase query shape.
- Classifier scoring now maps cached embedding matrix rows as NumPy views
  instead of copying every vector into a separate array. This keeps the current
  `load_embedding_matrix()` cache contract and reduces memory churn for promoted
  classifier jobs that need MERT and MAEST matrices.

## Phase 1: No Schema Changes

These can continue immediately:

1. Split `LibraryDatabase` into internal modules without changing public DB
   behavior:
   - `db_connection.py`: connection setup, WAL, busy timeout, write locks.
   - `db_schema.py`: schema and migrations.
   - `track_repository.py`: track CRUD, listing, likes, relocation.
   - `analysis_repository.py`: embeddings, Sonara/MAEST metadata, resets.
   - `library_queries.py`: summary, search/list page, analyzer candidates.
2. Keep hot-path query helpers lean:
   - Return `AnalysisCandidate` for analyzer selection.
   - Keep list/search rows metadata-free.
   - Load full metadata only from `/api/tracks/{id}`.
3. Add small benchmark/smoke commands for:
   - `/api/library/summary`
   - `/api/tracks`
   - `/api/search` and `/api/search/text` preconditions
   - `list_analysis_candidates`
   - classifier score filters
4. Tighten cache invalidation:
   - Invalidate MERT/CLAP/MAEST embedding matrix cache only for affected
     embedding keys.
   - Avoid invalidating all embedding caches after likes or unrelated metadata
     updates.
5. Use `EXPLAIN QUERY PLAN` in tests/smokes for the few hot selectors where a
   scan would be expensive.

## Phase 2: Index-Only Schema Changes

These require approval before implementation, but have low data-model risk:

| Candidate | Why | Migration shape |
| --- | --- | --- |
| Additional partial indexes for analyzer candidate selection | Current indexes cover Sonara and MAEST JSON presence, but MERT/CLAP missing selection depends on embeddings lookups. Validate whether current `(embedding_key, track_id)` plus PK is enough before adding. | `CREATE INDEX IF NOT EXISTS`, schema version bump only if project policy requires tracking index additions. |
| Composite indexes for classifier-filtered library pages | CLASS filters can combine score thresholds with sorted track pages. | Add targeted indexes after measuring `EXPLAIN QUERY PLAN` on real filter combinations. |
| FTS5 index for text library search | Current text search uses LIKE-style matching across track fields and metadata-derived text. | Add virtual table plus rebuild trigger or explicit rebuild helper. Needs fallback decision if SQLite build lacks FTS5. |

## Approval-Ready Schema Proposal

This proposal is prepared for review only. It is not implemented in this branch.

### Proposal A: `track_analysis_state`

Purpose: make missing/stale analysis selection, summary counters, and reset
checks independent from repeated JSON and `EXISTS` probes.

Proposed schema version: `3`.

Proposed table:

```sql
CREATE TABLE track_analysis_state (
    track_id INTEGER NOT NULL,
    analysis_key TEXT NOT NULL,
    model_name TEXT,
    source_size INTEGER NOT NULL,
    source_mtime REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(track_id, analysis_key),
    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
);

CREATE INDEX idx_track_analysis_state_key_track
ON track_analysis_state(analysis_key, track_id);
```

Backfill sources:

- `sonara`: rows where `json_type(tracks.metadata_json, '$.sonara_features') IS
  NOT NULL`; `model_name` from `metadata_json.sonara_model`.
- `maest`: rows from `embeddings.embedding_key = 'maest'`; `model_name` from
  `embeddings.model_name`.
- `mert`: rows from `embeddings.embedding_key = 'mert'`; `model_name` from
  `embeddings.model_name`.
- `clap`: rows from `embeddings.embedding_key = 'clap'`; `model_name` from
  `embeddings.model_name`.
- Promoted classifiers: rows from `track_classifier_scores`; `analysis_key`
  stored as `classifier:<classifier>`, `model_name` from `model_id`.

Write-path maintenance if approved:

- `save_sonara_features()`, `save_genres()`, and `save_embedding()` upsert the
  matching state row in the same write transaction as the existing data write.
- `save_classifier_score()` upserts `classifier:<classifier>`.
- `reset_analysis()`, `reset_classifier_scores()`, `clear_library()`, and
  track deletion remove the matching state rows.
- Scan/upsert can compare `source_size` and `source_mtime` to mark stale state
  in one place instead of repeating stale logic per analysis family.

Query replacements if approved:

- `list_analysis_candidates()` becomes an anti-join from `tracks` to
  `track_analysis_state` for each selected `analysis_key`.
- `library_summary()` can count `analysis_key` groups from
  `track_analysis_state` and keep `liked` from `track_likes`.
- Classifier job candidate selection can choose between "missing score" and
  "feature-complete missing score" explicitly rather than discovering missing
  MERT/MAEST/Sonara inputs during scoring.

Rollback strategy:

- Run migration only on a copy of `C:\db\abstracted.sqlite` first.
- Because this table is derived state, rollback is `DROP TABLE
  track_analysis_state; PRAGMA user_version = 2;` on the copied DB.
- The original `tracks`, `embeddings`, and `track_classifier_scores` remain the
  source of truth until the migrated copy passes correctness and performance
  checks.

Approval request should include:

- The exact migration SQL and Python migration guard.
- Backfill verification counts for `sonara`, `maest`, `mert`, `clap`, and each
  promoted classifier.
- Read-only before/after timings for `list_analysis_candidates()` and
  `/api/library/summary` on the copied database.

## Phase 3: New Tables Or Columns

These are higher-value and higher-risk. Each item needs a separate design review
and explicit approval before code changes.

| Candidate | Purpose | Expected benefit | Main risk |
| --- | --- | --- | --- |
| `track_analysis_state(track_id, analysis_key, model_name, source_size, source_mtime, updated_at)` | Central source of truth for whether Sonara, MAEST, MERT, CLAP, and classifier inputs are current. | Fast missing/stale analysis queries and exact invalidation when file size/mtime changes. | Must backfill correctly from `metadata_json` and `embeddings`; reset semantics must stay exact. |
| `track_genres(track_id, label, score, source, updated_at)` | Normalize MAEST genres out of JSON. | Faster genre search, syncopated filter, metadata dialog, tag-writing preview. | Must preserve current MAEST JSON display contract or migrate UI/API together. |
| `track_sonara_features(track_id, key, value_json)` or typed feature columns | Move frequently queried Sonara values out of nested JSON. | Faster Sonara filtering/search and fewer JSON parses. | Wide typed schema vs flexible key/value tradeoff; must preserve canonical stored keys. |
| `track_search_index(track_id, text)` or FTS5 virtual table | Materialize searchable text from artist/title/album/path/tags/MAEST genres. | Faster library search and lower API latency on large libraries. | Needs reliable rebuild after scan, RefreshTags, MAEST, relocation. |
| Real boolean columns such as `has_sonara`, `has_maest`, `has_mert`, `has_clap`, `maest_syncopated_rhythm` | Avoid repeated JSON/EXISTS checks in summaries and candidate selection. | Very fast counters and filters. | Duplicated state can drift unless all write/reset paths update it atomically. |

## Recommended Schema Path If Approved

Start with one migration version, not many small incompatible migrations:

1. Create a copy of `C:\db\abstracted.sqlite` and run all migration tests on the
   copy only.
2. Add `track_analysis_state` and backfill it from:
   - `metadata_json.sonara_features`
   - `metadata_json.maest_genres`
   - `embeddings.embedding_key`
   - `track_classifier_scores`
3. Update writes/resets to maintain `track_analysis_state` in the same
   transaction as existing metadata/embedding writes.
4. Move analyzer candidate selection and summary counters to
   `track_analysis_state`.
5. Add perf tests comparing old read-only queries against the migrated copy.
6. Only after that, consider `track_genres` or FTS/search materialization.

## Approval Gates

Before implementing any schema-changing item, ask for confirmation with:

- Exact tables, columns, indexes, and schema version change.
- Migration/backfill SQL.
- Rollback strategy for the local DB copy.
- Read-only benchmark target on `C:\db\abstracted.sqlite`.
- Focused test list and smoke commands.

Default implementation rule: optimize without schema changes first; schema
changes only after an explicit approval message.
