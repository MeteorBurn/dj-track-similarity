# Install for local analysis

> Audience: Users preparing a checkout for local scanning, UI use, and optional analysis.
> Goal: Install only what you need and know which tools are required.
> Type: tutorial

The project is a Python package with optional extras plus a React frontend and VitePress docs. The command examples assume the environment is active.

## Requirements

- Python `>=3.10`.
- FFmpeg on `PATH`, or `DJ_TRACK_SIMILARITY_FFMPEG` set to the full ffmpeg executable path.
- Node.js and npm when building `frontend/dist` or the docs site.
- A local audio folder for the library, with no cloud storage needed for normal workflows.

The server calls `require_ffmpeg()` during startup. If FFmpeg is missing, startup fails with a clear setup error instead of silently using partial decoding.

## Create and activate an environment

PowerShell example:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

After activation, use `python` and `dj-sim` directly in commands.

## Base package

```powershell
python -m pip install -e ".[dev]"
```

The base package installs the core app dependencies: NumPy, Mutagen, Pydantic, Typer, FastAPI, Uvicorn, Joblib, and dev test tools. This is enough for scan, browse, serve, export, database selection, and existing data.

## Optional extras

Install only the extras you need:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

On Windows x64, the `sonara` extra installs the pinned SONARA `v0.2.4` wheel from the
[MeteorBurn release](https://github.com/MeteorBurn/sonara/releases/tag/v0.2.4). Other
platforms install the same package version from PyPI.

- `sonara`: SONARA feature extraction.
- `ml`: PyTorch, Torchaudio, Torchvision, TorchCodec, nnaudio, Transformers, Hugging Face Hub, LAION CLAP, MAEST, and MuQ inference packages.
- `ann`: optional HNSW backend for persistent ANN sidecar indexes.
- `rhythm-lab`: scikit-learn for classifier training.

For optional ANN support:

```powershell
python -m pip install -e ".[ann,dev]"
```

For Rhythm Lab training:

```powershell
python -m pip install -e ".[rhythm-lab,dev]"
```

## Build the frontend bundle

The backend serves `frontend/dist` when it exists. Create that bundle with:

```powershell
cd frontend
npm install
npm run build
```

For live frontend development, use:

```powershell
npm run dev
```

The development server binds to `127.0.0.1` by default.

## Build the docs site

The backend serves static docs from `docs/dj-track-similarity/site` when that directory exists. Build and check docs with:

```powershell
cd docs\dj-track-similarity
npm install --no-package-lock
npm run vale:sync
npm run check
```

`npm run check` runs strict Vale style checks before the VitePress build, and Git ignores the generated `site/` directory.

## Start the server

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

The default fixed ports are:

| Tool | Port | Notes |
| --- | ---: | --- |
| Main backend/UI | `8765` | `dj-sim serve` |
| Vite frontend dev server | `5173` | `npm run dev` in `frontend/` |
| Rhythm Lab | `8777` | standalone labeling/training UI |

Use one instance per fixed port.
