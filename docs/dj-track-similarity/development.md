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

Before a dev-to-main merge decision, run the reproducible milestone gate from
the repository root:

```powershell
.\scripts\verify_dev_milestone.ps1
```

The gate runs the non-ML backend pytest suite, focused evaluation/search tests,
frontend typecheck/tests/build, the static documentation build, and an exact
search benchmark smoke run with a synthetic temporary database. Benchmark JSON
is written to the system temporary directory by default so generated reports do
not become tracked runtime artifacts. Use `-Smoke` for a reduced local check of
the same orchestration path before running the full gate.

The milestone gate is non-ML by default. To add the explicit ML/CUDA check, pass
`-IncludeMl` and point `-MlPython` (or `DJ_TRACK_SIMILARITY_ML_PYTHON`) at a
prepared Python executable:

```powershell
.\scripts\verify_dev_milestone.ps1 -Smoke -IncludeMl -MlPython "<prepared-venv>\Scripts\python.exe"
```

This mode invokes the prepared environment read-only: it does not reinstall,
uninstall, or repoint packages, and it disables Python bytecode writes for the ML
commands. For the ML preflight and ML pytest run, the gate temporarily prepends
this repository's `src` directory to `PYTHONPATH` so imports verify the current
working tree instead of any editable install attached to the prepared
environment. The preflight fails before pytest if Torch, Torchaudio,
Torchvision, TorchCodec, CUDA availability, a tiny CUDA tensor operation, or the
`dj_track_similarity` import path is wrong.

Merge `dev` to `main` only after the full non-ML backend suite, frontend checks,
documentation build, schema/migration smoke, and an abstracted v4 SQLite smoke
are green. These checks must use temporary databases or explicit copies and must
not modify audio files or user SQLite state.

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

## Exact search benchmark and optional ANN prototype

`scripts/benchmark_search.py` creates a temporary synthetic schema v4 SQLite
library and measures the current `exact_numpy` vector backend. It writes a JSON
report only; by default the synthetic database is deleted after the run and the
script never reads a source library or audio file.

Production similarity search still defaults to this exact NumPy matrix-dot
backend. It is the reference backend for ANN recall and latency comparisons, and
production endpoints do not opt into ANN behavior by default.

An optional HNSW prototype is available for this benchmark script only. Install
it explicitly when needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ann,dev]"
```

The HNSW backend uses `hnswlib` lazily and is not a base runtime dependency. The
prototype builds an in-memory index for each benchmark search to avoid hidden
stale-index reuse. Treat its results as experimental and compare `recall_at_k`
against the exact backend before considering any ANN use.

Small smoke run:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_search.py --output .\reports\benchmark_search_smoke.json --track-count 100 --embedding-dim 16 --seed-count 5 --per-source 10 --vector-backend exact
```

Useful options include `--track-count` (repeatable), `--track-counts 1000,10000`,
`--embedding-dim 768` for full-size embedding vectors, `--classifier-profiles`
to populate synthetic classifier scores, and `--keep-db <path>` when debugging a
synthetic database. Use `--skip-sonara` only when you want an embedding-only
baseline. Use `--vector-backend hnsw` only in an environment where the optional
`ann` extra or an equivalent external `hnswlib` install is present.

The report includes environment details, setup time, the vector backend name,
`load_embedding_matrix` timings for MERT and MAEST, p50/p95 vector similarity
search timings over sampled seed tracks, weighted candidate pool timings, hybrid
search timings, result counts, and best-effort RSS memory in bytes. These
timings keep exact NumPy as the reference. HNSW benchmark reports also include
`recall_at_k` against exact results for the sampled searches. The script does not
change production scoring, result ordering, or endpoints.

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
