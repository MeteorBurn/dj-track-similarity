# Install for local analysis

> Audience: Users setting up the project locally.
> Goal: Install Python dependencies and know when Node/npm is needed.
> Type: tutorial

## Requirements

- Python 3.10+.
- `ffmpeg` on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG`.
- Node/npm only for rebuilding frontend or docs.
- A PyTorch stack that matches your CPU/GPU environment.

## Install

```powershell
python -m pip install -e ".[dev]"
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
dj-sim doctor
```

## Build assets

Build frontend from `frontend/` when frontend source changes. Build docs from `docs\dj-track-similarity` with `npm run build`; output goes to `site/`.
