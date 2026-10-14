# Environment and server commands

Read before running application commands or changing dependencies, interpreters,
decoders, audio tool behavior, external tools or server launch behavior. Git and
text-only instruction edits do not require this guide.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## PYTHON AND WINDOWS ENVIRONMENT

### Runtime selection and authoritative versions

- Work from the repository root in PowerShell 7. Invoke local commands with
  `.\run_server.cmd`, `& .\.venv\Scripts\python.exe`, and `& 'C:\path\tool.exe'`.
  Use PowerShell syntax and argument arrays; do not copy Bash examples into it.
- `.python-version` selects the development interpreter; `requires-python` in
  `pyproject.toml` is the package compatibility range, not an alternative pin.
  Use the root `.venv` created by `uv`, never an unverified system `python`.
  SQLite is bundled with that interpreter: verify `sqlite3.sqlite_version`
  when compatibility matters instead of inferring it from the Python version.
- Read dependency versions and platform selection from `pyproject.toml` and
  `uv.lock`; read FFmpeg/PyAV runtime requirements from
  `src/dj_track_similarity/audio/ffmpeg_runtime.py`. A lockfile pin does not
  establish what is currently installed. Do not maintain another version list
  in this guide.

### Installation and dependency changes

- `.\install.ps1` is the complete Windows x64 installation entry point. It
  requires 64-bit PowerShell 7. It prepares uv and Node.js/npm, synchronizes the
  root `.venv`, installs and builds the frontend, downloads every pinned model
  asset, and checks the audio and ML runtime. Reuse compatible installed tools;
  missing portable tools and archive caches stay under `.tools/install/`. The
  installer makes no user or system `PATH` changes and downloads nothing for
  audio: the FFmpeg libraries are tracked in `libs/ffmpeg/bin/`.
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
- SONARA comes from the public `MeteorBurn/sonara` release selected by URL in
  `[tool.uv.sources]` and by hash in `uv.lock`. Preserve that patched build,
  ML platform markers, wheel URLs and
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
  to inspect it. Python code must support the pinned interpreter; use the
  declared `tomli` dependency when it has no stdlib `tomllib`.
- Use Node/npm for each Node package. A fresh locked install uses
  `npm --prefix .\frontend ci --include=dev`, followed by the frontend build;
  the installer performs both. The docs site is independent of application
  installation and subject to the [pause](../../AGENTS.md#documentation-workflow).
  Its dependencies are only for authorized documentation checks or resumed site
  work. Use npm's install/update commands for dependency changes.

### Audio and GPU runtime

- Audio requires the shared FFmpeg runtime specified in
  `src/dj_track_similarity/audio/ffmpeg_runtime.py`, including DLLs.
  The repository ships an LGPL audio-only build in `libs/ffmpeg/bin/` and a PyAV
  wheel built against it in `libs/wheels/`; that wheel carries no libraries of its
  own, so `configure_shared_ffmpeg_runtime()` must run before anything imports
  `av`. Discovery checks `libs/ffmpeg/bin/` first, then the optional DLL
  directory in `DJTS_FFMPEG`, then PATH, skipping missing or invalid candidates,
  and fails explicitly if none is usable. The bundled build needs no environment
  setup; the installer does not create `DJTS_FFMPEG`. Verify
  with `inspect_audio_runtime()`, which also checks project PyAV; finding
  `ffmpeg.exe` alone is insufficient. No project code launches an FFmpeg
  executable.
- The CUDA wheels selected by `uv.lock` provide the CUDA runtime. A separate
  CUDA Toolkit is unnecessary; GPU inference needs a compatible NVIDIA GPU
  and driver. Preserve their sources rather than selecting wheels by a version
  number copied from documentation.
  The installer reports CUDA availability without installing a graphics driver.

### Shared development tools

- Ruff is external: invoke `C:\Utils\tools\ruff\ruff.exe` directly, without an
  update check; report its version only when relevant to the result. Keep `[tool.ruff]` and the
  native root `.ruff_cache/`; do not add Ruff as a Python dependency or invoke
  `python -m ruff`. SQLite Toolkit uses its own external installation.
- Graphify is installed only for this repository in `.tools/graphify/`, separate
  from the application's `.venv`. Invoke `.\.tools\graphify\bin\graphify.exe`;
  its Python is `.tools/graphify/graphifyy/Scripts/python.exe`. For authorized
  package maintenance, set `UV_TOOL_DIR` to this repository's `.tools/graphify`
  and `UV_TOOL_BIN_DIR` to its `bin` child for that process only. Never add it to
  user/system PATH or install/register Graphify globally.

## COMMANDS

### Audio tool safety contracts

- Audio Doctor is dry-run unless `--apply`; there is no interactive prompt.
  Apply makes a full-file backup, verifies the written file and restores the
  backup on failure; it deletes the backup after a verified write or a
  successful restore (a failed restore keeps it). `--no-backup` (rejected with
  `--backup-dir` under `--apply`) drops both backup and rollback.
- Audio Dedup finds duplicates from stored SONARA fingerprints alone; a fingerprint match is
  evidence, never authorization. It is report-first: deletion needs
  `APPLY DELETE` and a report written against the open database, stays inside
  the reviewer's path filter (rechecked on delete; an empty filter covers the
  whole report), rechecks track identity and file facts, and keeps at least one
  copy on disk per group. Its CLI is report-only;
  the browser deletes reviewer-selected copies (any group member, recycle bin by
  default). Never run apply modes for QA.

### Server launch and database selection

- Follow the confirmed development database and other database-selection rules
  in [EXECUTION AND SCOPE](../../AGENTS.md#execution-and-scope). Pass the selected
  path explicitly; never use a tool default to infer the selected library.
- Start project servers only through `run_server.cmd` in a visible interactive
  window, after checking existing listeners/processes and the selected database.
  Do not launch hidden direct `dj-sim`, Uvicorn or Vite processes. While the
  main server runs, Rhythm Lab starts only through it (its Rhythm Lab button or
  `POST /api/rhythm-lab/launch`) as a managed child in that server's window.
  Without the main server, start it with `run_rhythm-lab.cmd` in a visible
  window; the script hands off to a running main server itself. Never start
  `rhythm_lab_cli.py serve` directly.

| Entry point | Default/prompt behavior, not library selection authority |
|---|---|
| `run_server.cmd` | No default; lists `database/*.sqlite` or accepts a path; empty input cancels |
| `run_rhythm-lab.cmd` standalone prompt | `database\volumes.sqlite` |
| Audio Dedup `--db` | `database/volumes.sqlite` |
| Rhythm Lab data-command `--source` and `collection-save --source-db` | `C:\db\abstracted.sqlite` |
| Rhythm Lab `serve --source` | No default |

Local mode uses backend
`127.0.0.1:8765` and Vite `127.0.0.1:5173`; Rhythm Lab defaults to
`127.0.0.1:8777`. Check existing processes/listeners before starting a server;
LAN exposure must be requested. Use the database selected under the rules above;
do not ask again for the confirmed development default.

### Select commands by task

Read-only environment inspection (no server launch or database open):

```powershell
.\run_server.cmd --help
& .\.venv\Scripts\python.exe -c 'import sys, sqlite3; print(sys.executable); print(sys.version); print(sqlite3.sqlite_version)'
& .\.venv\Scripts\python.exe -c 'from dj_track_similarity.audio.ffmpeg_runtime import inspect_audio_runtime; print(inspect_audio_runtime())'
```

For requested startup, run the matching command in a visible interactive window
under the launch rules above; these are alternatives, not a batch:

```powershell
.\run_server.cmd                         # interactive database and mode selection
.\run_server.cmd local --db 'database/Volumes.sqlite'  # confirmed development default
.\run_rhythm-lab.cmd                     # via the running main server, else standalone
```

Build and test commands belong to [Verification](verification.md).
