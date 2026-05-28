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
python scripts\audio_dedup\audio_dedup.py --help
```
