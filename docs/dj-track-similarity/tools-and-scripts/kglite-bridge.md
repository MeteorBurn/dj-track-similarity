# KGLite bridge

> Audience: Users exploring library relationships with local graph queries.
> Goal: Build a disposable, read-only graph from a selected library.
> Type: guide

The KGLite bridge projects selected SQLite data into a local `.kgl` graph.
Core and its mandatory Artifacts sidecar remain the source of truth. The
bridge opens both inputs with SQLite `mode=ro` and `PRAGMA query_only = ON`.
It never opens audio files and does not store raw embedding vectors.

KGLite is an optional tool dependency. It is not part of the application
runtime.

## Graph contents

The projection contains:

- `Catalog` and `Projection` nodes with the catalog binding and deterministic
  projection digest;
- `Track` nodes identified by `catalog_uuid` plus `track_uuid`;
- exact-tag `Artist` and `Genre` nodes;
- one liked `Collection` derived from the Core `likes` table, when present;
- one source node for every selected embedding family;
- directed top-K edges named `SIMILAR_MAEST`, `SIMILAR_MERT`, `SIMILAR_MUQ`,
  `SIMILAR_CLAP`, and `SIMILAR_SONARA`.

Every similarity edge records `source_family`, cosine `score`, `rank`, and the two
`content_generation` values. These values are
ranking signals for listening-led shortlisting, not probabilities or
objective musical truth.

## Current-data checks

The bridge fails closed when the Core or Artifacts structure is wrong, the
`catalog_uuid` binding differs, or a selected embedding family is unavailable.

It exports an embedding only when `track_uuid`, `content_generation`, dimension, `float32-le`
encoding, normalization, and finite vector values match current structural requirements. Stale
track generations are excluded and counted in the build report.

## Dry run

Always select the Core database explicitly. A dry run validates both inputs,
calculates the full projection, and writes no `.kgl` file:

```powershell
python tools\kglite-bridge\kglite_bridge_cli.py `
  --db .\data\library.sqlite `
  --output tools\kglite-bridge\data\library.kgl `
  --dry-run --format json
```

The default Artifacts path is `<db stem>.artifacts.sqlite`. Use `--artifacts`
only when the selected bundle uses another explicit path.

## Build

```powershell
python tools\kglite-bridge\kglite_bridge_cli.py `
  --db .\data\library.sqlite `
  --output tools\kglite-bridge\data\library.kgl `
  --top-k 10 --min-score 0.0 --format json
```

By default, the bridge selects every active embedding source. Repeat
`--source` to require a subset:

```powershell
python tools\kglite-bridge\kglite_bridge_cli.py `
  --db .\data\library.sqlite `
  --output tools\kglite-bridge\data\library.kgl `
  --source mert --source maest --source muq `
  --top-k 10 --format json
```

The output is written to a sibling staging file, reopened, checked against the
expected node and edge counts, and then published. Existing output is preserved
unless `--overwrite` is explicit. The bridge refuses an output path that
resolves to either SQLite input.

Track nodes include stored audio paths by default. Use `--omit-paths` before
sharing a graph. A `.kgl` graph can still expose library titles, artists,
genres, model identities, and similarity relationships, so treat it as private
local data.

## Local wrapper and queries

The optional machine-local wrapper keeps its disposable graph outside the
repository:

```powershell
& 'C:\Utils\tools\codingest-djts\djts.ps1' library-dry-run `
  --db '<core.sqlite>' --format json

& 'C:\Utils\tools\codingest-djts\djts.ps1' library-build `
  --db '<core.sqlite>' --top-k 10 --format json
```

Describe the graph before writing Cypher:

```powershell
& 'C:\Utils\tools\codingest-djts\djts.ps1' library-describe `
  --connections --cypher
```

Then query MuQ similarities:

```powershell
& 'C:\Utils\tools\codingest-djts\djts.ps1' library-query `
  'MATCH (a:Track)-[r:SIMILAR_MUQ]->(b:Track) RETURN a.title, b.title, r.score ORDER BY r.score DESC LIMIT 20' `
  --format json
```

`library-mcp` starts a read-only MCP server. `library-selftest` can inspect the
same graph concurrently because read-only KGLite servers do not retain a
writer lease.

## Verification

Tests create temporary Core/Artifacts databases and dummy audio bytes. They
verify current-only export, deterministic projection identity, real KGLite
reload, graph counts, and unchanged input hashes:

```powershell
python -m pytest tools\kglite-bridge\tests\test_kglite_bridge.py --override-ini addopts=
```
