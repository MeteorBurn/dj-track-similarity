# Development

Аудитория: contributors  
Цель: setup and run focused local checks  
Тип: how-to

## Environment

From project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

All following Python commands assume active environment.

## Backend checks

```powershell
pytest
```

Prefer focused tests for small changes, then broaden only when change crosses
module boundaries.

## Frontend checks

```powershell
cd frontend
npm run build
```

Backend serves `frontend/dist`, not Vite hot reload.

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

Before starting fixed port, check whether matching project process already
running.
