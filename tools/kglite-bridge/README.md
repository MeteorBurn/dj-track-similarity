# KGLite Bridge

This helper creates a disposable KGLite graph from a selected current Core SQLite
database and its mandatory Artifacts sidecar. SQLite remains authoritative.
The bridge opens both inputs read-only, never opens audio, and does not store
raw embedding vectors.

The graph contains `Track`, `Artist`, `Genre`, liked `Collection`,
`EmbeddingContract`, `Catalog`, and `Projection` nodes. Current embedding
sources become directed top-K relationships named `SIMILAR_MAEST`,
`SIMILAR_MERT`, `SIMILAR_MUQ`, `SIMILAR_CLAP`, and `SIMILAR_SONARA`.

Validate without writing:

```powershell
.\.venv\Scripts\python.exe tools\kglite-bridge\kglite_bridge_cli.py `
  --db .\data\library.sqlite `
  --output tools\kglite-bridge\data\library.kgl `
  --dry-run --format json
```

Build the graph:

```powershell
.\.venv\Scripts\python.exe tools\kglite-bridge\kglite_bridge_cli.py `
  --db .\data\library.sqlite `
  --output tools\kglite-bridge\data\library.kgl `
  --top-k 10 --format json
```

The default source set is every active embedding contract. Repeat `--source`
to require an explicit subset. Existing output requires `--overwrite`.
`--omit-paths` removes stored audio paths from `Track` properties.

The machine-local wrapper stores code and library graphs outside the
repository:

```powershell
& 'C:\Utils\tools\codingest-djts\djts.ps1' library-build `
  --db '<core.sqlite>' --top-k 10 --format json
```

Run tests with temporary fixtures only:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tools\kglite-bridge\tests\test_kglite_bridge.py `
  --override-ini addopts=
```
