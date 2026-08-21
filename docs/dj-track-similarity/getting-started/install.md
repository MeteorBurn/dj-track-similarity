# Install for local analysis

Install only what you actually need. The project is a Python package with optional extras, plus a
React frontend and VitePress docs. The command examples assume the environment is active.

## Requirements

- Python `>=3.10`.
- FFmpeg `8.1.1` as a full shared build. Put its library directory on `PATH`, or set
  `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` to that directory.
- Node.js and npm when building `frontend/dist` or the docs site.
- A local audio folder for the library, with no cloud storage needed for normal workflows.
- `uv` for every install that includes the `ml` extra.

The server registers the shared runtime during startup. It requires `ffmpeg.exe` reporting `8.1.1`
plus the complete compatible shared-library set. A missing, partial, or different runtime fails with
a clear setup error instead of silently using partial decoding. A bare `ffmpeg.exe` is not enough.

## Shared FFmpeg runtime

The FFmpeg runtime is not versioned or bundled with the repository. Install or provide exactly
FFmpeg `8.1.1` as a full shared build and make its library directory available to the process. On
Windows, the directory must contain `ffmpeg.exe` and this complete DLL set: `avcodec-62.dll`,
`avformat-62.dll`, `avutil-60.dll`, `avfilter-11.dll`, `swresample-6.dll`, and `swscale-9.dll`.

The runtime discovery order is:

1. `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR`, when set to a valid complete runtime.
2. The first valid complete FFmpeg `8.1.1` runtime directory on `PATH`.

To configure the preferred discovery choice for one PowerShell session:

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR = 'C:\path\to\ffmpeg\bin'
dj-sim serve --host 127.0.0.1 --port 8765
```

The main application uses TorchCodec and the shared libraries directly for decoding. The executable
is used only to verify the selected runtime version during setup. An executable installed for some
other application does not configure the required shared libraries and cannot stand in for them. The
base project dependency installs PyAV `17.1.0` into the active Python environment; it is not loaded
from `libs`.

After installation, verify the actual process environment:

```powershell
dj-sim doctor
```

The command reports the selected FFmpeg directory, version, required library paths, and the PyAV
version and module path. It fails clearly when the installed PyAV or FFmpeg runtime does not match
the project contract.

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
Uvicorn, Joblib, PyAV `17.1.0`, and dev test tools. This is enough for scan, CLI, backend API, export, and
database-selection paths. The typed React client is built separately with its recorded Node
dependencies.

## Optional extras

Install only the extras you need:

```powershell
uv sync --locked --extra sonara --extra ml --extra dev
```

The current `sonara` extra installs SONARA `0.3.5`. PyPI publishes `cp310-abi3` wheels, including
Windows x64, so supported Python 3.10+ environments do not need to build SONARA locally.

Verify the current installed runtime before analyzing a library:

```powershell
python -c "import sonara; print(sonara.__version__)"
```

The current tested environment prints `0.3.5`. This records the dependency used for the current
build. You can adopt a newer SONARA release by updating the project sources, manifests, and lockfile
together, followed by focused compatibility checks.

The `ml` extra records one mutually compatible loader stack. Installed packages must expose the
capabilities, checkpoints, and output shapes the adapters use, but the runtime does not reject a
package solely because its distribution version changed.

Use `uv` for this install because `pip` does not apply `[tool.uv.sources]`. On Windows AMD64 with
Python 3.10, `uv` selects `torch`, `torchaudio`, and `torchvision` from the CUDA 13.0 index plus the
exact TorchCodec `0.16.0+cu130` wheel and its SHA-256. Other supported environments select
TorchCodec `0.16.0`. The CUDA package selection does not move shared audio decoding to the GPU:
`AudioDecoder` has no device option in TorchCodec `0.16`, while `--device` controls model inference.
The project requests mono output with `num_channels=1`, keeps `AudioSamples.data[0]` as a 1D CPU
`torch.float32` tensor, and passes it directly to the adapters. Model-specific resampling remains in
Torchaudio.

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

The React client uses the current backend API. The backend serves `frontend/dist` when it exists. Create
that bundle with:

```powershell
npm --prefix .\frontend install
npm --prefix .\frontend run build
```

Run its API-shape tests when changing the client:

```powershell
npm --prefix .\frontend test
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
