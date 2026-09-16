# Environment and server commands

Read before running project commands or changing dependencies, interpreters, decoders, external tools, or server launch behavior.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## PYTHON AND WINDOWS ENVIRONMENT

- Work from the repository root in PowerShell 7. Invoke local commands with
  `.\run_server.cmd`, `& .\.venv\Scripts\python.exe`, and `& 'C:\path\tool.exe'`.
  Use PowerShell syntax and argument arrays; do not copy Bash examples into it.
  Follow `.gitattributes`: source text uses LF, `.cmd`/`.bat` use CRLF; new text
  is UTF-8 without BOM. Preserve unrelated file formatting.
- `.python-version` selects the development interpreter; `requires-python` in
  `pyproject.toml` is the package compatibility range, not an alternative pin.
  Use the root `.venv` created by `uv`, never an unverified system `python`.
  SQLite is bundled with that interpreter: verify `sqlite3.sqlite_version`
  when compatibility matters instead of inferring it from the Python version.
- `.\install.ps1` is the complete Windows x64 installation entry point. It
  requires 64-bit PowerShell 7. It prepares uv, Node.js/npm and the shared
  FFmpeg runtime, synchronizes the root
  `.venv`, installs and builds the frontend, downloads every pinned model asset,
  and checks the audio and ML runtime. Reuse compatible installed tools; missing
  portable tools and archive caches stay under `.tools/install/`, with FFmpeg
  in `libs/ffmpeg/bin/`. The installer makes no user or system `PATH` changes.
- If the Microsoft Visual C++ x64 runtime DLLs are unavailable, the installer
  verifies the pinned Microsoft redistributable's SHA-256 and Authenticode
  signature and runs it. This system prerequisite may request Windows UAC
  approval or report a required restart; the installer never restarts Windows.
- `uv sync --locked` is the Python dependency step. `pyproject.toml`,
  `uv.lock`, and `[tool.uv.sources]` govern dependencies and their sources;
  pip does not apply uv's interpreter/source selection. Do not introduce a
  separate pip installation workflow. Resolve `uv` with `Get-Command uv -All`;
  when unavailable, use `& .\.tools\install\uv\uv.exe` with the same arguments.
- All Python dependencies, including SONARA, ML, scikit-learn, development and
  Audio Online packages, belong to the root `pyproject.toml`. Project scripts
  and Python tools share the root `.venv`.
  Do not add private tool environments or requirements files.
- SONARA comes from the public `MeteorBurn/sonara` release
  `v0.3.6-meteorburn.1`, selected by URL in `[tool.uv.sources]` and by hash in
  `uv.lock`. Preserve that patched build, ML platform markers, wheel URLs and
  PyTorch index selection. Do not substitute another SONARA build on a download
  failure.
- `uv sync` is exact by default. `--locked` protects the lockfile, not the
  installed environment. For an audit, use `uv sync --locked --check --offline`;
  a cache or access failure is not evidence that dependencies are inconsistent.
- `scripts/download_models.py`, called by the installer with the root `.venv`,
  downloads every asset from the adapter manifests using pinned upstream
  revisions and SHA-256 hashes. Valid local assets are skipped; partial model
  downloads can resume. A downloaded file replaces its target only after hash
  verification. Inference stays offline and reads the local `models/` tree.
- Run inspection and tests with `& .\.venv\Scripts\python.exe -m '<module>'`
  after checking that interpreter exists; `uv run --no-sync python ...` is an
  alternative. Do not synchronize, upgrade, or recreate the environment merely
  to inspect it. Python code must support the pinned interpreter; TOML-reading
  tools cannot assume stdlib `tomllib` while the pin is Python 3.10.
- Use Node/npm for each Node package. A fresh locked install uses
  `npm --prefix .\frontend ci --include=dev`, followed by the frontend build;
  the installer performs both. Install `docs/dj-track-similarity` dependencies
  only for requested docs work. Use npm's install/update commands for dependency
  changes. The docs site is independent of the application installation.
- Audio requires the full shared FFmpeg runtime specified in
  `src/dj_track_similarity/audio/ffmpeg_runtime.py` (currently 8.1.1), including DLLs.
  Discovery uses `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR`, PATH or the installer's
  `libs/ffmpeg/bin/`. An explicit environment override must be valid. Verify with
  `inspect_audio_runtime()`, which also checks project PyAV; finding
  `ffmpeg.exe` alone is insufficient.
- On Windows x64 with Python 3.10.20, the lock selects PyTorch/TorchAudio
  `2.11.0+cu130`, TorchVision `0.26.0+cu130`, TorchCodec `0.16.0+cu130` and PyAV
  `17.1.0`. The binaries provide the CUDA 13.0 runtime. A separate CUDA Toolkit
  is unnecessary; GPU inference needs a compatible NVIDIA GPU and driver.
  The installer reports CUDA availability without installing a graphics driver.
- Ruff is external: invoke `C:\Utils\tools\ruff\ruff.exe` directly, without an
  update check, and report its version when used. Keep `[tool.ruff]` and the
  native root `.ruff_cache/`; do not add Ruff as a Python dependency or invoke
  `python -m ruff`. SQLite Toolkit uses its own external installation.
- Graphify is installed only for this repository in `.tools/graphify/`, separate
  from the application's `.venv`. Invoke `.\.tools\graphify\bin\graphify.exe`;
  its Python is `.tools/graphify/graphifyy/Scripts/python.exe`. For authorized
  package maintenance, set `UV_TOOL_DIR` to this repository's `.tools/graphify`
  and `UV_TOOL_BIN_DIR` to its `bin` child for that process only. Never add it to
  user/system PATH or install/register Graphify globally.

## COMMANDS

Examples below are selected by task, not run as a batch. Local mode uses backend
`127.0.0.1:8765` and Vite `127.0.0.1:5173`; Rhythm Lab defaults to
`127.0.0.1:8777`. Check existing processes/listeners before starting a server;
LAN exposure must be requested. Confirm the database before using `--db`.
Start project servers only through `run_server.cmd` in a visible interactive
window so the user can see and stop them. Do not launch hidden direct `dj-sim`,
Uvicorn or Vite processes. While the main server runs, start Rhythm Lab only
through it (Rhythm Lab button or `POST /api/rhythm-lab/launch`); it runs as the
server's managed child in the same window. Without the main server, use
`run_rhythm-lab.cmd` in a visible window, which hands off to a running main
server itself. Never run `rhythm_lab_cli.py serve` directly.

```powershell
.\run_server.cmd --help
.\run_server.cmd                         # interactive database and mode selection
.\run_rhythm-lab.cmd                     # via the running main server, else standalone
.\run_server.cmd local --db 'C:\path\selected.sqlite'
& .\.venv\Scripts\python.exe -c 'import sys, sqlite3; print(sys.executable); print(sys.version); print(sqlite3.sqlite_version)'
& .\.venv\Scripts\python.exe -c 'from dj_track_similarity.audio.ffmpeg_runtime import inspect_audio_runtime; print(inspect_audio_runtime())'
npm --prefix .\frontend run build        # frontend runtime/build changes; before a commit
```
