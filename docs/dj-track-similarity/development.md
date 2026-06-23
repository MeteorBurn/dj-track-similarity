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
```

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
