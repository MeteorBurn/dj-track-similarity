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

The base package installs the core app dependencies: NumPy, Mutagen, Pydantic, Typer, FastAPI,
Uvicorn, Joblib, and dev test tools. This is enough for the v7 scan, CLI, backend API, export, and
database-selection paths. The React frontend is a separate deferred port.

## Optional extras

Install only the extras you need:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

The `sonara` extra installs pinned SONARA `v0.3.1`. PyPI publishes `cp310-abi3` wheels, including
Windows x64, so supported Python 3.10+ environments do not need to build SONARA locally.

Verify the runtime before analyzing a fresh library or preparing a new SONARA release:

```powershell
python -c "import sonara; print(sonara.__version__)"
```

The command must print `0.3.1`. The runtime creates fresh schema-v7 Core plus mandatory Artifacts
bundles and rejects older schemas. There is no migration command. Follow
[Prepare and rebuild a SONARA release](../workflows/reanalyze-sonara-split-storage.md).

The `ml` extra pins the loader stack, including `transformers==5.13.0` and
`huggingface-hub==1.22.0`. Model-adapter preflight fails closed when installed package identity does
not match the locked analysis contract.

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

The React client has not yet been ported to the v7 API. The commands below build the current source,
but the result is not a verified v7 UI.

The backend serves `frontend/dist` when it exists. Create that bundle with:

```powershell
npm --prefix .\frontend install
npm --prefix .\frontend run build
```

For live frontend development, use:

```powershell
npm --prefix .\frontend run dev
```

The development server binds to `127.0.0.1` by default.

## Build the docs site

The backend serves static docs from `docs/dj-track-similarity/site` when that directory exists. Build and check docs with:

```powershell
npm --prefix .\docs\dj-track-similarity install --no-package-lock
npm --prefix .\docs\dj-track-similarity run vale:sync
npm --prefix .\docs\dj-track-similarity run check
```

`npm run check` runs strict Vale style checks before the VitePress build, and Git ignores the generated `site/` directory.

## Start the server

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

The default fixed ports are:

| Tool | Port | Notes |
| --- | ---: | --- |
| Main backend | `8765` | `dj-sim serve` |
| Vite frontend dev server | `5173` | `npm run dev` in `frontend/` |
| Rhythm Lab | `8777` | standalone labeling/training UI |

Use one instance per fixed port.
