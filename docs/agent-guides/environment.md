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
- `uv sync` is the supported Python installation path. `pyproject.toml`,
  `uv.lock`, and `[tool.uv.sources]` govern dependencies and their sources;
  pip does not apply uv's interpreter/source selection. Do not introduce a
  separate pip installation workflow.
- For model-backed or Rhythm Lab development, use
  `uv sync --locked --extra sonara --extra ml --extra rhythm-lab --extra dev`.
  Add `--extra audio-online` for that tool. Project scripts and Python tools
  share the root `.venv`; extra tool dependencies belong in `pyproject.toml`.
  Do not add private tool environments or requirements files.
- Before syncing, check that the SONARA wheel named in `[tool.uv.sources]`
  exists. It is a machine-local Windows wheel; a fresh clone does not provide
  it. Preserve the ML platform markers, wheel URLs, and PyTorch index selection.
  A missing local artifact calls for locating the intended build, not replacing
  it with an arbitrary package or silently changing the source.
- `uv sync` is exact by default and can remove unselected extras. Retain the
  extras needed by the existing environment when adding another one.
  `--locked` protects the lockfile, not the installed environment. For an audit,
  use `uv sync --locked --check --offline` with the intended extras; a cache or
  access failure is not evidence that dependencies are inconsistent.
- Run inspection and tests with `& .\.venv\Scripts\python.exe -m '<module>'`
  after checking that interpreter exists; `uv run --no-sync python ...` is an
  alternative. Do not synchronize, upgrade, or recreate the environment merely
  to inspect it. Python code must support the pinned interpreter; TOML-reading
  tools cannot assume stdlib `tomllib` while the pin is Python 3.10.
- Use Node/npm for each Node package. A fresh locked install uses
  `npm --prefix .\frontend ci`; install `docs/dj-track-similarity` dependencies
  only for requested docs work. Use npm's install/update commands for dependency
  changes. Python, frontend, and docs installations remain separate.
- Audio requires the full shared FFmpeg runtime specified in
  `src/dj_track_similarity/audio/ffmpeg_runtime.py` (currently 8.1.1), including DLLs.
  On this host it is under `C:\Utils\tools\ffmpeg\bin`; discovery uses
  `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` or PATH. Verify with
  `inspect_audio_runtime()`, which also checks project PyAV; finding
  `ffmpeg.exe` alone is insufficient.
- Ruff is external: invoke `C:\Utils\tools\ruff\ruff.exe` directly, without an
  update check, and report its version when used. Keep `[tool.ruff]` and the
  native root `.ruff_cache/`; do not add Ruff as a Python dependency or invoke
  `python -m ruff`. SQLite Toolkit and Graphify also use their own external
  installations, not the application's `.venv`.

## COMMANDS

Examples below are selected by task, not run as a batch. Local mode uses backend
`127.0.0.1:8765` and Vite `127.0.0.1:5173`; Rhythm Lab defaults to
`127.0.0.1:8777`. Check existing processes/listeners before starting a server;
LAN exposure must be requested. Confirm the database before using `--db`.
Start project servers only through `run_server.cmd` in a visible interactive
window so the user can see and stop them. Do not launch hidden direct `dj-sim`,
Uvicorn or Vite processes.

```powershell
.\run_server.cmd --help
.\run_server.cmd                         # interactive database and mode selection
.\run_server.cmd local --db 'C:\path\selected.sqlite'
& .\.venv\Scripts\python.exe -c 'import sys, sqlite3; print(sys.executable); print(sys.version); print(sqlite3.sqlite_version)'
& .\.venv\Scripts\python.exe -c 'from dj_track_similarity.audio.ffmpeg_runtime import inspect_audio_runtime; print(inspect_audio_runtime())'
npm --prefix .\frontend run build        # frontend runtime/build changes; before a commit
```
