# DB Schema Optimization Research

Date: 2026-05-31

This research used the current code and the live library database as the source
of truth. The live database `C:\db\abstracted.sqlite` was opened read-only with
`mode=ro`. Schema experiments were run only on a temporary SQLite backup created
with the SQLite backup API.

No schema, index, table, or field changes were applied to the live database or
to application code.

## Source Database Shape

| Item | Value |
| --- | ---: |
| Source database | `C:\db\abstracted.sqlite` |
| Source size | 1019.24 MB |
| `PRAGMA user_version` | 2 |
| Tracks | 61,373 |
| Sonara rows in `tracks.metadata_json` | 61,356 |
| MAEST embeddings | 61,355 |
| MERT embeddings | 61,355 |
| CLAP embeddings | 61,355 |
| Likes | 15 |
| Classifier score rows | 122,710 |
| Classifier keys observed | `break_energy`, `live_instrumentation` |

## Baseline Query Findings

The current schema already has good coverage for the ordinary library page,
summary counters, Sonara missing selection, syncopated browsing, and embedding
summary counts.

| Workflow | Current plan shape | Median |
| --- | --- | ---: |
| `/api/library/summary` track count | covering scan of `tracks` unique path index | 2.453 ms |
| Sonara summary count | partial index `idx_tracks_sonara_present` | 2.070 ms |
| MAEST summary count | covering index `idx_embeddings_key_track` | 2.783 ms |
| MERT summary count | covering index `idx_embeddings_key_track` | 2.467 ms |
| CLAP summary count | covering index `idx_embeddings_key_track` | 3.063 ms |
| Library page ids | `idx_tracks_sort_artist_title_path` | 0.056 ms |
| Syncopated page ids | `idx_tracks_syncopated_sort` | 0.056 ms |
| Text library search ids, common term `unknown` | scan in sort order, `LOWER(...) LIKE` predicates | 93.999 ms |
| Missing Sonara ids | `idx_tracks_sonara_missing_sort` | 0.018 ms |
| Missing MAEST ids | scan sorted tracks plus embedding index probe | 33.677 ms |
| Missing MERT ids | scan sorted tracks plus embedding index probe | 40.524 ms |
| Missing CLAP ids | scan sorted tracks plus embedding index probe | 35.017 ms |
| Missing classifier ids | scan sorted tracks plus classifier PK probe | 47.186 ms |
| Analysis candidate hydration for 18 ids | track PK lookup plus embedding PK probes | 0.098 ms |
| Classifier-filtered library page | scans tracks, correlated score subqueries, temp sort | 299.644 ms |

Main baseline conclusion: the hottest measured problem is not the analyzer
candidate hydration. The most obvious UI/API hotspot is classifier-filtered
library browsing.

## Candidate 1: Rewrite Classifier-Filtered Library Query

This does not require a schema change.

The current classifier-filtered page starts from `tracks`, probes classifier
scores through correlated subqueries, and then sorts. On the copied database it
measured around 333 ms for the first page.

Starting from `track_classifier_scores` lets SQLite use the existing
`idx_classifier_scores_lookup(classifier, score DESC, track_id)` index:

```sql
SELECT t.id
FROM track_classifier_scores cs
JOIN tracks t ON t.id = cs.track_id
WHERE cs.classifier = ? AND cs.score >= ?
ORDER BY cs.score DESC, COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
LIMIT ? OFFSET ?;
```

| Query | Plan shape | Median |
| --- | --- | ---: |
| Current classifier filter | full `tracks` scan, correlated subqueries | 333.261 ms |
| Rewritten classifier filter | `idx_classifier_scores_lookup`, track PK lookup | 0.119 ms |
| Rewritten classifier count | `idx_classifier_scores_lookup` | 0.257 ms |

Recommendation: implement this before any schema migration. It is a low-risk
query rewrite and gives the largest measured win.

## Candidate 2: Core Analysis Flags On `tracks`

The first schema-changing performance candidate should be explicit core-analysis
presence flags on `tracks`, not a separate `track_analysis_state` table.

Tested columns on the copied database:

```sql
ALTER TABLE tracks ADD COLUMN has_sonara_analysis INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tracks ADD COLUMN has_maest_embedding INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tracks ADD COLUMN has_mert_embedding INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tracks ADD COLUMN has_clap_embedding INTEGER NOT NULL DEFAULT 0;
```

Backfill used current sources of truth:

```sql
UPDATE tracks
SET has_sonara_analysis =
    CASE WHEN json_type(metadata_json, '$.sonara_features') IS NOT NULL THEN 1 ELSE 0 END;

UPDATE tracks
SET has_maest_embedding =
    CASE WHEN EXISTS (
        SELECT 1 FROM embeddings e
        WHERE e.track_id = tracks.id AND e.embedding_key = 'maest'
    ) THEN 1 ELSE 0 END;

UPDATE tracks
SET has_mert_embedding =
    CASE WHEN EXISTS (
        SELECT 1 FROM embeddings e
        WHERE e.track_id = tracks.id AND e.embedding_key = 'mert'
    ) THEN 1 ELSE 0 END;

UPDATE tracks
SET has_clap_embedding =
    CASE WHEN EXISTS (
        SELECT 1 FROM embeddings e
        WHERE e.track_id = tracks.id AND e.embedding_key = 'clap'
    ) THEN 1 ELSE 0 END;
```

Tested missing-selection indexes:

```sql
CREATE INDEX idx_tracks_missing_sonara_flag_sort
ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
WHERE has_sonara_analysis = 0;

CREATE INDEX idx_tracks_missing_maest_embedding_flag_sort
ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
WHERE has_maest_embedding = 0;

CREATE INDEX idx_tracks_missing_mert_embedding_flag_sort
ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
WHERE has_mert_embedding = 0;

CREATE INDEX idx_tracks_missing_clap_embedding_flag_sort
ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
WHERE has_clap_embedding = 0;
```

Tested present-count indexes:

```sql
CREATE INDEX idx_tracks_present_sonara_flag
ON tracks(id) WHERE has_sonara_analysis = 1;

CREATE INDEX idx_tracks_present_maest_embedding_flag
ON tracks(id) WHERE has_maest_embedding = 1;

CREATE INDEX idx_tracks_present_mert_embedding_flag
ON tracks(id) WHERE has_mert_embedding = 1;

CREATE INDEX idx_tracks_present_clap_embedding_flag
ON tracks(id) WHERE has_clap_embedding = 1;
```

Backfill plus index setup took 5.997 seconds on the copied database. Backfilled
counts matched current sources:

| Flag | Count |
| --- | ---: |
| `has_sonara_analysis` | 61,356 |
| `has_maest_embedding` | 61,355 |
| `has_mert_embedding` | 61,355 |
| `has_clap_embedding` | 61,355 |

Measured query results:

| Workflow | Median |
| --- | ---: |
| Sonara flag summary count | 1.276 ms |
| MAEST flag summary count | 1.268 ms |
| MERT flag summary count | 1.275 ms |
| CLAP flag summary count | 1.291 ms |
| Missing Sonara ids | 0.017 ms |
| Missing MAEST ids | 0.018 ms |
| Missing MERT ids | 0.018 ms |
| Missing CLAP ids | 0.018 ms |

Recommendation: if schema changes are approved, this should be the first
schema migration for analyzer hot paths. It is faster and simpler than
`track_analysis_state` for the current missing-analysis selectors.

Required write-path maintenance if approved:

- `save_sonara_features()` sets `has_sonara_analysis = 1`.
- `save_embedding()` sets the matching `has_*_embedding = 1` for MAEST, MERT,
  and CLAP.
- `reset_analysis()` sets the matching flag back to `0` in the same transaction
  that deletes or clears the existing analysis data.
- `clear_library()` needs no special cleanup beyond deleting `tracks`.
- New tracks default to `0`.
- Metadata refresh should preserve these flags unless a separate stale-analysis
  invalidation policy is approved.

These flags should initially represent presence of the current stored analysis,
not a new stale/fresh policy. If stale invalidation based on size/mtime is
approved later, that should be designed as a separate behavior change.

## Candidate 3: FTS5 Library Search

The current text search uses `LOWER(...) LIKE` across artist, title, album, path,
and `metadata_json`. On the live database this was around 94 ms for the common
term `unknown`.

The copied database supports FTS5. A prototype virtual table was created:

```sql
CREATE VIRTUAL TABLE track_search_fts
USING fts5(track_id UNINDEXED, text, tokenize='unicode61');
```

Prototype backfill:

```sql
INSERT INTO track_search_fts(rowid, track_id, text)
SELECT id, id,
       LOWER(
           COALESCE(artist, '') || ' ' ||
           COALESCE(title, '') || ' ' ||
           COALESCE(album, '') || ' ' ||
           path || ' ' ||
           metadata_json
       )
FROM tracks;
```

| Workflow | Median |
| --- | ---: |
| FTS setup/backfill | 9.906 s |
| FTS first page, `unknown` | 21.873 ms |
| FTS count, `unknown` | 0.163 ms |

Recommendation: useful, but not the first schema migration. It has a larger API
contract risk because FTS token matching is not identical to substring `LIKE`.
Before implementing, decide whether search should keep substring semantics,
switch to token search, or expose both modes.

## Candidate 4: `track_analysis_state`

The earlier proposal was tested on the copied database:

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

Backfill completed and source/state counts matched for Sonara, MAEST, MERT,
CLAP, `classifier:break_energy`, and `classifier:live_instrumentation`.

| Backfill step | Time |
| --- | ---: |
| Sonara rows | 588.218 ms |
| Embedding rows | 1.757 s |
| Classifier rows | 975.942 ms |

However, it is not a good first performance migration for missing-analysis
selection:

| Workflow | Current median | `track_analysis_state` median |
| --- | ---: | ---: |
| Missing Sonara ids | 0.018 ms | 74.212 ms |
| Missing MAEST ids | 33.677 ms | 73.716 ms |
| Missing MERT ids | 40.524 ms | 74.648 ms |
| Missing CLAP ids | 35.017 ms | 74.524 ms |
| Missing classifier ids | 47.186 ms | 72.169 ms |

The anti-join still scans sorted `tracks` and probes state for each row. With
near-complete analysis coverage, this is slower than the existing targeted
indexes and slower than direct boolean partial indexes.

Recommendation: do not implement `track_analysis_state` as the next schema
change for speed. Revisit it only if the goal changes to centralized source
freshness bookkeeping, dynamic analysis state history, or a more explicit
invalid/stale analysis model.

## Storage Notes

The temporary copied database grew from the 1019.24 MB source size to 1444.60 MB
after all experimental structures were added together (`track_analysis_state`,
flag columns/indexes, and FTS5). The local SQLite build did not expose `dbstat`,
so exact per-object sizes were not available in this run.

Before implementing FTS5, run a dedicated size experiment that applies only the
FTS table to a fresh copy and records the file growth. The core flag/index
migration should also get its own size check before approval.

## Revised Implementation Order

1. Implement the no-schema classifier filter query rewrite.
2. Ask for explicit approval for schema version 3 with core-analysis flags on
   `tracks` and partial indexes for missing/present counts.
3. If approved, implement the migration on a copy first, then update write paths
   and focused tests.
4. Consider FTS5 search only after deciding search semantics.
5. Defer `track_analysis_state` until there is a clear source-freshness or state
   history requirement that justifies the extra table.

## Approval Gate For Schema Version 3

Before changing the real app schema, confirm whether to implement:

- Four `tracks` columns:
  `has_sonara_analysis`, `has_maest_embedding`, `has_mert_embedding`,
  `has_clap_embedding`.
- Four missing-sort partial indexes for analyzer candidate selection.
- Four present-count partial indexes for summary counters.
- Backfill from existing `metadata_json` and `embeddings`.
- Write-path maintenance in `save_sonara_features()`, `save_embedding()`, and
  `reset_analysis()`.
- No stale-analysis invalidation semantics yet.

Focused verification for that implementation should include:

- Migration/backfill test on a copied database.
- `tests/test_scanner_database.py`
- `tests/test_analysis_jobs.py`
- `tests/test_api_tracks.py`
- `tests/test_search.py`
- `tests/test_break_energy.py`
- Read-only smoke timings for library summary and `list_analysis_candidates()`.
