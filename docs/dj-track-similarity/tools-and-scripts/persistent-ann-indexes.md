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

They store generated vector-index artifacts and manifests for one model family at a time: `maest`,
`mert`, `muq`, or `clap`. They do not copy audio files and they do not write new SQLite rows.

## Install optional backend

The `ann` extra installs `hnswlib`:

```powershell
python -m pip install -e ".[ann,dev]"
```

The persistent CLI backend is `hnswlib`.

## Build and verify

```powershell
dj-sim index build --model clap --db .\data\library.sqlite
```

```powershell
dj-sim index verify --model clap --db .\data\library.sqlite
```

Select the active embedding family with the required `--model` option.

Optional build controls:

```powershell
dj-sim index build --model clap --backend hnswlib --ef-construction 200 --m 16 --ef-search 100 --db .\data\library.sqlite
```

## Benchmark recall

```powershell
dj-sim index benchmark --model clap --recall-k 50 --seed-count 20 --db .\data\library.sqlite
```

The benchmark compares against exact search and reports pass/fail using the chosen threshold.

## Use from CLAP text search

The current CLI opt-in is explicit:

```powershell
dj-sim text-search "warm dub techno pads" --use-ann-index --db .\data\library.sqlite
```

If the sidecar is missing, stale, or unsupported, the command warns and falls back to exact search.

## Rebuild after embeddings change

Rebuild after the selected model's analysis changes. Also rebuild after embedding reset, database replacement, or index directory moves.

## Clear generated files

Clear one model family:

```powershell
dj-sim index clear --model clap --db .\data\library.sqlite
```

Clear all sidecar index files in the resolved index directory:

```powershell
dj-sim index clear --db .\data\library.sqlite
```

Sidecar indexes are generated local state and should stay out of Git.
