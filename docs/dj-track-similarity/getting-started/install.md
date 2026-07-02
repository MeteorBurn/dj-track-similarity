# Install for local analysis

> Audience: Users setting up the project locally.
> Goal: Install Python dependencies and know when Node/npm is needed.
> Type: tutorial

## Requirements

- Python 3.10+.
- `ffmpeg` on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG` pointing to the executable.
- A PyTorch stack that matches your CPU/GPU environment when you run MERT, MAEST, or CLAP analysis.
- Node/npm only for rebuilding frontend or docs assets.

## Base install

The base package is enough for scanning and everyday UI browsing. It can serve the backend and work with already stored data:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Analysis install

Install the local ML extras when you want SONARA, MERT, MAEST, CLAP, or Rhythm Lab workflows:

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
dj-sim doctor
```

Keep the PyTorch-family packages synchronized with the wheel set you actually use. `dj-sim doctor` prints the detected Torch/CUDA state and suggested install index when it can infer one.

## Optional ANN index install

Persistent ANN sidecar indexes are optional. Install `hnswlib` through the `ann` extra when you want HNSW-backed indexes:

```powershell
python -m pip install -e ".[ann]"
```

Without this extra, `dj-sim index build --backend auto` can still fall back to an exact NumPy sidecar. See [Persistent ANN indexes](../tools-and-scripts/persistent-ann-indexes.md) for usage.

## Build assets

Build frontend from `frontend/` only when frontend source changes. Check docs from
`docs\dj-track-similarity` with `npm run check` when `README.md`, VitePress Markdown, or docs config
changes. Run `npm run vale:sync` once first if the Vale styles have not been installed locally. The
check command runs strict Vale style checking and the site build. Use `npm run build` only when you
intentionally need local site output or deployment output without the style check. The docs build
writes `site/`, which is ignored by Git.
