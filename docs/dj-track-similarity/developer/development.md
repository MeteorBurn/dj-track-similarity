# Development workflow

> Audience: Developers making local changes.
> Goal: Use setup and build commands for backend, frontend, and docs.
> Type: how-to

## Setup

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
python -m pytest
```

## Ports

Before starting a fixed port, check whether a matching project process is already running. Main backend uses `8765`, frontend Vite uses `5173`, and Rhythm Lab uses `8777`.

## Builds

Build frontend from `frontend/` with `npm run build`. Build docs from `docs\dj-track-similarity` with `npm run build` when you need local preview or deployment output. The docs `site/` directory is generated output and is not tracked in Git.
