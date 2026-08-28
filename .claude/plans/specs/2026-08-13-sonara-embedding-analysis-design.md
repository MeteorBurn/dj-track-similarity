# SONARA Embedding Analysis Design

## Goal

Compute SONARA's native embedding during the normal SONARA analysis pass and
persist it in `sonara_embeddings` in the main library database. Existing stored
model embeddings are trusted and are not revalidated during candidate
discovery; validation belongs to analysis and the write boundary.

## Confirmed SONARA Contract

- The installed SONARA runtime is `0.3.5+sym06fallback.1`.
- `sonara.SIMILARITY_VERSION` is `2`.
- `sonara.EMBEDDING_DIM` is `48`.
- The Python analysis result exposes `embedding` as `List[float]` only when the
  `embedding` feature is explicitly requested.
- The persisted representation is contiguous little-endian float32: 48 values,
  192 bytes.
- Storage normalization is `none`. SONARA applies fixed per-dimension feature
  normalization, but the resulting vector is not L2-unit-normalized.

## Current State

The `main` branch already has the generic embedding output, SQLite write,
UPSERT, and analysis orchestration boundaries. SONARA is not yet registered in
the fixed-family embedding specification and currently requests and persists
only its Core output.

The intended table already exists in `database/volumes_exp.sqlite`, but it does
not exist in the main `database/volumes.sqlite`. No embedding rows will be
migrated or backfilled. The exact table and index will be created explicitly in
the main database before reanalysis; application startup must remain
non-mutating.

## Database Structure

`sonara_embeddings` follows the existing model-embedding table pattern:

```sql
CREATE TABLE sonara_embeddings (
    track_id       INTEGER PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    track_uuid     TEXT    NOT NULL,
    dim            INTEGER NOT NULL CHECK(dim = 48),
    normalization  TEXT    NOT NULL CHECK(normalization = 'none'),
    embedding_blob BLOB    NOT NULL CHECK(length(embedding_blob) = 48 * 4),
    analyzed_at    TEXT    NOT NULL
);
CREATE INDEX idx_sonara_embeddings_track_uuid
    ON sonara_embeddings(track_uuid);
```

The same DDL becomes part of fresh-library schema creation. For the existing
main database, table creation is an explicit one-time schema operation after a
recoverable backup. It does not modify tracks, Core analysis, or other model
tables.

## Analysis Data Flow

1. The SONARA runner advertises both `sonara/core` and `sonara/embedding`.
2. The runtime requests `embedding` alongside the existing Core feature list.
3. SONARA returns one analysis mapping containing Core fields, `embedding`, and
   `embedding_version`.
4. Result conversion validates the newly calculated embedding as a numeric,
   finite, one-dimensional 48-value vector and converts it to contiguous
   little-endian float32.
5. A `SonaraWrite` carries the Core row and SONARA `EmbeddingOutput` together.
6. The repository writes Core and embedding under the same per-track savepoint.
   Either both writes succeed or neither becomes visible.
7. Reanalysis uses the existing UPSERT contract, replacing the current row for
   the same `track_id` and refreshing `track_uuid` and `analyzed_at`.

## Existing-Data Trust Boundary

Candidate discovery must not read, decode, or validate stored embedding BLOBs.
For every embedding family, readiness is determined from the stored
`track_id`/`track_uuid` keys only. A matching stored key means that output is
present and the candidate does not need that model output recalculated.

Payload checks remain only at the boundary that receives a newly calculated
embedding and serializes it. This change is limited to analysis readiness;
unrelated search, classifier, and UI behavior is unchanged.

## Main Database Operation

Before changing `database/volumes.sqlite`:

1. Checkpoint WAL and close active database users if required.
2. Create a SQLite backup copy and record its SHA-256 hash.
3. Record table counts and run `PRAGMA integrity_check` and
   `PRAGMA foreign_key_check`.
4. Create only `sonara_embeddings` and its index in one transaction.
5. Reopen the database and repeat integrity, foreign-key, count, and schema
   checks. Existing table counts must be unchanged and the new table must be
   empty before reanalysis.

The reanalysis itself is user-run. With SONARA Core already present and the new
embedding table empty, SONARA candidates are selected because only
`sonara/embedding` is missing.

## Verification

- One focused table-format round-trip proves `dim=48`,
  `normalization='none'`, and a 192-byte float32 BLOB.
- Focused SONARA tests prove the runtime requests `embedding`, exposes both
  outputs, prepares a 48D write, and persists Core plus embedding atomically.
- A focused candidate test proves a stored embedding key is considered ready
  without adding payload-validation behavior.
- A temporary database is used for automated tests; the real database is
  checked only with explicit schema, count, integrity, and foreign-key queries.
- No tests are added for unrelated non-use by search, classifiers, Rhythm Lab,
  or the UI.

## Non-Goals

- No embedding search or similarity consumer is added.
- No classifier, Rhythm Lab, Audio Dedup, or UI integration is added.
- No existing SONARA embeddings are copied from the experimental database.
- No startup-time schema mutation is introduced.
- No additional validation pass over already stored model embeddings is added.
