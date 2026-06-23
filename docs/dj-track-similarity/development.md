# Development and Verification

This page covers local setup and verification expectations.

## Development Setup

Install development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Install Sonara support:

```powershell
python -m pip install -e ".[sonara,dev]"
```

Install ML dependencies:

```powershell
python -m pip install -e ".[ml,dev]"
```

Install the full local lab dependency set, including Rhythm Lab training:

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

Run backend tests:

```powershell
pytest
```

Build the frontend:

```powershell
cd frontend
npm run build
```

Build the static HTML documentation:

```powershell
cd docs\dj-track-similarity
npm install
npm run build
```

The documentation HTML is generated into `docs/dj-track-similarity/site/`.
After the backend starts, the main UI opens it from the top-bar documentation
button at `/docs/`.

Run the frontend development server:

```powershell
cd frontend
npm run dev
```

For Python commands in this repository, prefer the project virtual environment
when available:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Verification Guidance

Use focused verification for code changes and script changes. Documentation-only
changes do not need the full test suite, but should be checked for stale local
paths and command accuracy.

Useful checks:

```powershell
dj-sim --help
dj-sim analyze --help
python scripts\audio_repair\repair_audio_metadata.py --help
python tools\audio-dedup\audio_dedup_cli.py --help
python scripts\optimize_database.py --help
python scripts\create_library_v4_from_v3.py --help
python scripts\benchmark_search.py --help
```

## Exact search benchmark before ANN work

`scripts/benchmark_search.py` creates a temporary synthetic schema v4 SQLite
library and measures the current `exact_numpy` vector backend before any ANN
index is introduced. It writes a JSON report only; by default the synthetic
database is deleted after the run and the script never reads a source library or
audio file.

Production similarity search still defaults to this exact NumPy matrix-dot
backend. It is the reference backend for future ANN recall and latency
comparisons; FAISS, HNSW, and other ANN indexes are not implemented here.

Small smoke run:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_search.py --output .\reports\benchmark_search_smoke.json --track-count 100 --embedding-dim 16 --seed-count 5 --per-source 10
```

Useful options include `--track-count` (repeatable), `--track-counts 1000,10000`,
`--embedding-dim 768` for full-size embedding vectors, `--classifier-profiles`
to populate synthetic classifier scores, and `--keep-db <path>` when debugging a
synthetic database. Use `--skip-sonara` only when you want an embedding-only
baseline.

The report includes environment details, setup time, the vector backend name,
`load_embedding_matrix` timings for MERT and MAEST, p50/p95 exact similarity
search timings over sampled seed tracks, weighted candidate pool timings, hybrid
search timings, result counts, and best-effort RSS memory in bytes. These
timings describe the current exact implementation only; the script does not add
FAISS, HNSW, ANN indexes, or change production scoring/endpoints.

## Library schema copy scripts

The main app expects the current library schema and does not runtime-migrate old
library databases. The schema v4 evaluation foundation is created from a v3
database with an explicit dry-run-first copy script:

```powershell
.\.venv\Scripts\python.exe scripts\create_library_v4_from_v3.py --source .\data\library_v3.sqlite --dest .\data\library_v4.sqlite
.\.venv\Scripts\python.exe scripts\create_library_v4_from_v3.py --source .\data\library_v3.sqlite --dest .\data\library_v4.sqlite --apply
```

The script opens the source read-only, writes only the destination copy, adds the
v4 evaluation/calibration tables, sets `PRAGMA user_version = 4`, and runs an
integrity check. It does not inspect or modify audio files.
