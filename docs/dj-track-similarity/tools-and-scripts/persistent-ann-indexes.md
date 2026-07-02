# Persistent ANN indexes

> Audience: Users with large analyzed libraries and repeated vector lookup.
> Goal: Build, verify, benchmark, use, and clear optional sidecar indexes.
> Type: guide

Persistent ANN indexes are generated sidecar files for stored embeddings. They are optional. Exact search still works without them.

## What is stored

Indexes live beside the selected SQLite database by default under:

```text
.dj-track-similarity-indexes/
```

They store generated vector-index artifacts and manifests for one adapter at a time: `mert`, `maest`, or `clap`. They do not copy audio files and they do not write new SQLite rows.

## Install optional backend

The `ann` extra installs `hnswlib`:

```powershell
python -m pip install -e ".[ann,dev]"
```

The CLI backend option can use `auto`, `hnswlib`, or `exact-numpy`. `auto` prefers hnswlib when available.

## Build and verify

```powershell
dj-sim index build --adapter clap --db .\data\library.sqlite
```

```powershell
dj-sim index verify --adapter clap --db .\data\library.sqlite
```

Adapters are selected with `--adapter` or `--embedding-key`.

Optional build controls:

```powershell
dj-sim index build --adapter clap --backend auto --ef-construction 200 --m 16 --ef-search 100 --db .\data\library.sqlite
```

## Benchmark recall

```powershell
dj-sim index benchmark --adapter clap --recall-k 50 --seed-count 20 --db .\data\library.sqlite
```

The benchmark compares against exact search and reports pass/fail using the chosen threshold.

## Use from CLAP text search

The current CLI opt-in is explicit:

```powershell
dj-sim text-search "warm dub techno pads" --use-ann-index --db .\data\library.sqlite
```

If the sidecar is missing, stale, or unsupported, the command warns and falls back to exact search.

## Rebuild after embeddings change

Rebuild after adapter analysis changes. Also rebuild after embedding reset, database replacement, or index directory moves.

## Clear generated files

Clear one adapter:

```powershell
dj-sim index clear --adapter clap --db .\data\library.sqlite
```

Clear all sidecar index files in the resolved index directory:

```powershell
dj-sim index clear --db .\data\library.sqlite
```

Sidecar indexes are generated local state and should stay out of Git.
