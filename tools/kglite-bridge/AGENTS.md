# KGLite Bridge Notes

Standalone, read-only derived-graph exporter. The root `AGENTS.md` also
applies.

## Active Development

- The root evolution policy applies. Graph schema, node and relationship sets,
  identity strategy, projections, CLI options, and validation rules describe
  the current exporter, not a permanent KGLite contract.
- A requested graph redesign may rename, reorder, add, or remove fields and
  entities. Update exporter, validator, digest/determinism behavior, tests, and
  consuming workflows together; add backward compatibility only for a real
  stored or external consumer requirement.
- Read-only treatment of project databases and source audio is the default
  safety baseline. It may change only as an explicit owner-directed capability
  with a newly defined and verified user-data boundary.

## Current Safety Boundary

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

## Current Graph Structure

- Current node identities use `catalog_uuid` plus `track_uuid` or a
  normalized-value digest. Numeric `track_id` is metadata, never graph
  identity.
- Current nodes include `Catalog`, `Projection`, `Track`, `Artist`, `Genre`, and
  `Collection`; evolve the graph shape as integration needs change.
- Current similarity relationships are source-specific. Discover the active
  set from exporter source and tests rather than freezing a duplicate list in
  new consumers.
- Current similarity is directed top-K per seed track, with rank, cosine score,
  and source family on each relationship. These semantics may evolve with a
  coordinated schema and consumer update.
- The current derived graph omits raw embedding vectors. Adding them would be a
  deliberate storage/privacy/size design change, not an incidental schema edit.
- Keep ordering and the projection digest deterministic for identical
  SQLite snapshots and CLI options.

## Testing

- Use only temporary Core/Artifacts fixtures and dummy audio bytes.
- Assert input database and audio hashes are unchanged.
- Run:
  `python -m pytest tools\kglite-bridge\tests\test_kglite_bridge.py --override-ini addopts=`
- A real KGLite end-to-end test may skip only when the optional `kglite`
  module is unavailable.
