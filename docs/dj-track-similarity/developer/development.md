# Development

Audience: contributors  
Goal: set up and run focused local checks  
Type: how-to

## Environment

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

All following Python commands assume the environment is active.

## Backend checks

```powershell
pytest
```

Prefer focused tests for small changes, then broaden only when the change
crosses module boundaries.

## Frontend checks

```powershell
cd frontend
npm run build
```

The backend serves `frontend/dist`, not Vite hot reload.

## Docs checks

```powershell
cd docs\dj-track-similarity
npm run build
```

Rebuild docs after changing Markdown under `docs/dj-track-similarity`.

## Local server

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Before starting a fixed port, check whether a matching project process is
already running.
