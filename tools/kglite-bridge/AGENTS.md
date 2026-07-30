# KGLite Bridge Notes

Standalone, read-only derived-graph exporter. The root `AGENTS.md` also
applies.

## Safety boundary

- Project SQLite databases are inputs only. Open them with SQLite URI
  `mode=ro`, set `PRAGMA query_only = ON`, and never run
  DDL, DML, checkpoints, vacuum, attach-write, or migrations.
- Never read, decode, copy, rewrite, retag, move, or delete source audio.
  Stored file paths are metadata only.
- The output `.kgl` is disposable derived state. Never treat it as the
  authoritative catalog, analysis store, or deletion evidence.
- Refuse an output path that resolves to either input SQLite file. Existing
  `.kgl` output requires explicit `--overwrite`.
- Export only validated embedding rows with the required track identity,
  dimension, normalization, and finite float32 payload.
- Do not add Codingest or KGLite to application runtime dependencies. KGLite
  is an optional local tool dependency imported only when writing or
  validating a graph.

## Graph structure

- Stable node identities use `catalog_uuid` plus `track_uuid` or a
  normalized-value digest. Numeric `track_id` is metadata, never graph
  identity.
- Nodes include `Catalog`, `Projection`, `Track`, `Artist`, `Genre`, and
  `Collection`; evolve the graph shape as integration needs change.
- Similarity relationships are source-specific:
  `SIMILAR_MAEST`, `SIMILAR_MERT`, `SIMILAR_MUQ`, `SIMILAR_CLAP`, and
  `SIMILAR_SONARA`.
- Similarity is directed top-K per seed track. Every relationship carries
  rank, cosine score, and source family.
- Do not store raw embedding vectors in the graph.
- Keep ordering and the projection digest deterministic for identical
  SQLite snapshots and CLI options.

## Testing

- Use only temporary Core/Artifacts fixtures and dummy audio bytes.
- Assert input database and audio hashes are unchanged.
- Run:
  `python -m pytest tools\kglite-bridge\tests\test_kglite_bridge.py --override-ini addopts=`
- A real KGLite end-to-end test may skip only when the optional `kglite`
  module is unavailable.
