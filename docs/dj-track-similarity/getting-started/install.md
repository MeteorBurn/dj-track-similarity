# Install for local analysis

Install only what you actually need. The project is a Python package with optional extras, plus a
React frontend and VitePress docs. Run the command examples from the repository root. `dj-sim` and
`python` in them mean the project environment, which `uv run` reaches without activating anything:
`uv run dj-sim doctor`.

## Requirements

- `uv`. It supplies the interpreter as well as the packages: `.python-version` pins CPython
  `3.10.20`, and `uv sync` downloads that build when the machine does not already have it.
- FFmpeg `8.1.1` as a full shared build. Put its library directory on `PATH`, or set
  `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` to that directory.
- Node.js and npm when building `frontend/dist` or the docs site.
- A local audio folder for the library, with no cloud storage needed for normal workflows.

The server registers the shared runtime during startup. It requires `ffmpeg.exe` reporting `8.1.1`
plus the complete compatible shared-library set. A missing, partial, or different runtime fails with
a clear setup error instead of silently using partial decoding. A bare `ffmpeg.exe` is not enough.

## Shared FFmpeg runtime

The FFmpeg runtime is not versioned or bundled with the repository. Install or provide exactly
FFmpeg `8.1.1` as a full shared build and make its library directory available to the process. On
Windows, the directory must contain `ffmpeg.exe` and this complete DLL set: `avcodec-62.dll`,
`avformat-62.dll`, `avutil-60.dll`, `avfilter-11.dll`, `swresample-6.dll`, and `swscale-9.dll`.

The runtime discovery order is:

1. `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR`, when set to a valid complete runtime. A value pointing
   at an incomplete runtime fails immediately rather than falling through to `PATH`.
2. The first valid complete FFmpeg `8.1.1` runtime directory on `PATH`.

To configure the preferred discovery choice for one PowerShell session:

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR = 'C:\path\to\ffmpeg\bin'
dj-sim serve --host 127.0.0.1 --port 8765
```

The main application uses TorchCodec and the shared libraries directly for decoding. The executable
is used only to verify the selected runtime version during setup. An executable installed for some
other application does not configure the required shared libraries and cannot stand in for them. The
base project dependency installs PyAV `17.1.0` into the active Python environment. It is not loaded
from `libs`.

After installation, verify the actual process environment:

```powershell
dj-sim doctor
```

The command reports Python, Torch, and CUDA details, then the selected FFmpeg directory, version,
required library paths, and the PyAV version and module path. It fails clearly when the installed
PyAV or FFmpeg runtime does not match the project contract. With Torch missing it returns before the
audio check, so run it again after installing the `ml` extra.

## Install the project

```powershell
uv sync --locked --extra dev
```

`uv sync` reads `.python-version`, downloads that CPython build when the machine does not already
have it, and builds `.venv` in the repository root from `uv.lock`. `--locked` installs the recorded
dependency set instead of resolving a fresh one. `run_server.cmd` activates that `.venv` itself, so
nothing has to be activated by hand. To run a single command in the environment without activating
it, prefix it with `uv run`, as in `uv run dj-sim doctor`.

`uv sync` is the only supported way to install. Every environment has to carry the same SQLite the
project is developed against, and SQLite is compiled into the interpreter rather than installed
beside it, so only the pinned interpreter supplies it.

That install covers the core app dependencies: NumPy, Mutagen, Pydantic, Typer, FastAPI, Uvicorn,
Joblib, PyAV `17.1.0`, and the dev test tools. It is enough for scan, CLI, backend API, export, and
database-selection paths. The two Node manifests are installed separately, because `uv` cannot
manage a Node manifest: see the frontend and docs sections below.

## Optional extras

`pyproject.toml` declares five extras: `sonara`, `ml`, `rhythm-lab`, `audio-online`, and `dev`. Name
the ones you want in a single `uv sync`, which installs exactly the set you name:

```powershell
uv sync --locked --extra sonara --extra ml --extra rhythm-lab --extra dev
```

### What each extra brings

- `sonara`: SONARA feature extraction.
- `ml`: PyTorch, Torchaudio, Torchvision, TorchCodec, nnaudio, Transformers, Hugging Face Hub, LAION CLAP, MAEST, and MuQ inference packages.
- `rhythm-lab`: scikit-learn for classifier training.
- `audio-online`: openpyxl for the Audio Online workbook, plus tomli on Python versions with no
  `tomllib` in the standard library.
- `dev`: pytest, ruff, and the HTTP test client.

### The `sonara` extra needs a local wheel

The project requires SONARA `0.3.6` or newer. Storage reads `bpm_min` and `bpm_max` from the
analysis provenance SONARA returns, and that provenance was added in `0.3.6`. On `0.3.5` every
SONARA analysis fails while the record is validated.

`pyproject.toml` pins `sonara==0.3.6` and resolves it through `[tool.uv.sources]` to a patched wheel
built from the SONARA repository at tag `v0.3.6`. `uv.lock` records that wheel by path and by
SHA-256, so the installed build is exact.

That path is local to the maintainer machine. On any other machine, build the `0.3.6` wheel from the
SONARA sources first, then point `[tool.uv.sources]` at your own copy before running `uv sync`.

Verify the installed runtime before analyzing a library:

```powershell
python -c "import sonara; print(sonara.__version__)"
```

Expect `0.3.6` or newer. A lower version means the manifest pin was applied, and SONARA analysis
will fail. Adopting a newer SONARA release means updating the project sources, manifests, and
lockfile together, followed by focused compatibility checks.

The `ml` extra records one mutually compatible loader stack. Installed packages must expose the
capabilities, checkpoints, and output shapes the adapters use, but the runtime does not reject a
package solely because its distribution version changed.

The `ml` extra is the clearest case for the install rule above: it resolves through
`[tool.uv.sources]`, which only `uv` reads. On Windows AMD64 with Python 3.10, `uv` selects `torch`,
`torchaudio`, and `torchvision` from the CUDA 13.0 index plus the exact TorchCodec `0.16.0+cu130`
wheel and its SHA-256. Other supported environments select TorchCodec `0.16.0`. The CUDA package
selection does not move shared audio decoding to the GPU: `AudioDecoder` has no device option in
TorchCodec `0.16`, while `--device` controls model inference. The project requests mono output with
`num_channels=1`, keeps `AudioSamples.data[0]` as a 1D CPU `torch.float32` tensor, and passes it
directly to the adapters. Model-specific resampling remains in Torchaudio.

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
