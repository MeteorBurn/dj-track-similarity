# Persistent ANN indexes

> Audience: Users with large analyzed libraries who want faster vector lookup.
> Goal: Build, verify, benchmark, and remove optional sidecar indexes without changing library data.
> Type: how-to

Persistent ANN indexes are generated sidecar files built from stored `mert`, `maest`, or `clap` audio embeddings. They are optional: normal vector search works without them, and opt-in search paths fall back to exact search when a requested sidecar is missing, stale, or unsupported.

Use them after analysis is already complete and exact vector search starts to feel slow on a large local library. Do not build them before the matching embeddings exist.

## What is stored

The index command writes generated files under an index directory. By default, that directory is placed beside the selected SQLite database:

```text
<database-folder>/.dj-track-similarity-indexes/
```

You can override it with `--index-dir <index-folder>`. The generated sidecar contains vectors and track IDs needed for lookup. It does not copy audio files and does not write new SQLite rows.

The default `.gitignore` excludes `.dj-track-similarity-indexes/`. Keep custom index directories out of Git as well.

## Install the optional backend

The base project can use the exact NumPy sidecar. For HNSW indexes, install the optional ANN dependency:

```powershell
python -m pip install -e ".[ann]"
```

`--backend auto` prefers `hnswlib` when it is installed. If it is not available, auto mode falls back to `exact-numpy` and prints a warning.

## Build and verify

Build one adapter at a time:

```powershell
dj-sim index build --adapter clap --db <library-db>
dj-sim index verify --adapter clap --db <library-db>
```

Supported adapters:

- `mert`
- `maest`
- `clap`

Useful build options:

- `--backend auto|hnswlib|exact-numpy`
- `--index-dir <index-folder>`
- `--ef-construction <n>` for HNSW build quality and cost
- `--m <n>` for HNSW graph connectivity
- `--ef-search <n>` saved into the manifest for HNSW search

`index build` removes older generated files for the same adapter in the selected index directory before writing the new sidecar.

## Benchmark recall

Benchmark compares the sidecar against exact vector search on deterministic seed embeddings:

```powershell
dj-sim index benchmark --adapter clap --recall-k 50 --threshold 0.97 --output .\reports\clap-index.json --db <library-db>
```

Use the JSON report when tuning HNSW settings. A failed benchmark means the sidecar is usable but did not meet the selected recall threshold.

## Use an index from text search

CLAP text search exposes explicit opt-in:

```powershell
dj-sim text-search "warm dub techno pads" --use-ann-index --db <library-db>
```

Add `--index-dir <index-folder>` if the sidecar is not in the default location.

If the sidecar is missing, stale, or unsupported, the command warns and falls back to exact search. This keeps results available, but it may be slower.

## Rebuild when embeddings change

Run `dj-sim index verify --adapter <adapter> --db <library-db>` when results look suspicious or after maintenance work. Rebuild after:

- running new analysis for the same adapter;
- resetting or clearing embeddings;
- copying or replacing the SQLite database;
- moving the sidecar to another machine;
- changing HNSW settings intentionally.

## Clear generated files

Remove one adapter sidecar:

```powershell
dj-sim index clear --adapter clap --db <library-db>
```

Remove all owned generated sidecar files from the selected index directory:

```powershell
dj-sim index clear --db <library-db>
```

`index clear` deletes only generated index files in the selected index directory. It does not delete audio files and does not remove SQLite data.
