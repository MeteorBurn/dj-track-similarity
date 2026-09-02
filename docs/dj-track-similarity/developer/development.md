# Development workflow

What you need to run the project from a checkout, and where the moving parts sit while you work on
it.

## Setup

A fresh Windows checkout takes three installs, one per manifest the project
keeps. `uv` owns every Python dependency, including the ones the tools under
`tools/` need, and `npm` owns the two Node manifests, which `uv` cannot manage:

```powershell
uv sync --locked --extra dev
npm --prefix .\frontend install
npm --prefix .\docs\dj-track-similarity install
```

Then verify the shared FFmpeg runtime:

```powershell
uv run dj-sim doctor
```

`uv sync` is the only supported install. It reads `.python-version`, downloads
that CPython build when the machine does not already have it, and builds `.venv`
in the repository root from `uv.lock`. `--locked` installs the recorded
dependency set rather than resolving a fresh one. `run_server.cmd` activates that
`.venv` itself, and `uv run` reaches it for a single command without activating
anything.

Add the optional stack when working on model-backed analysis or Rhythm Lab:

```powershell
uv sync --locked --extra sonara --extra ml --extra rhythm-lab --extra dev
```

`pyproject.toml` declares five extras: `sonara`, `ml`, `rhythm-lab`,
`audio-online`, and `dev`. Each run installs exactly the set you name, so name
every extra you want in one command. `ml` and `sonara` resolve through
`[tool.uv.sources]`, which only `uv` reads. On Windows AMD64 with Python 3.10,
`uv` selects the PyTorch packages from the CUDA 13.0 index.

## Ports

Before starting a fixed port, check whether a matching project process is already running. Main backend uses `8765`, frontend Vite uses `5173`, and Rhythm Lab uses `8777`. Local mode binds to `127.0.0.1`. LAN exposure is explicit and binds to `0.0.0.0`.

## Where changes go

- Add endpoints in the matching `src/dj_track_similarity/api_routes_*.py` module;
  keep `api.py:create_app` focused on composition and shared state.
- Route library SQLite access through `LibraryDatabase` and the focused `db_*.py`
  modules rather than opening independent write paths.
- When an API payload changes, update the backend contract,
  `frontend/src/api.ts`, `frontend/src/apiClient.ts`, UI callers, and focused
  Python and Node contract tests together.
- Keep frontend workflow state in the existing hooks and helpers. Use `App.tsx`
  to compose those workflows and panels.
- Root Pytest collects only `tests/`. Four other suites need naming on the command line:
  `tools/rhythm-lab/tests`, `tools/audio-dedup/tests`, `tools/audio-online/tests`, and
  `scripts/tests`.
- A new frontend test must drive its module rather than read its text.
  `frontend/tests/testsExecuteCode.test.mjs` enforces that: a test loads its subject through
  `ssrLoadModule`, through `transpileModule` plus `vm`, or through a direct `../src/` import. It
  keeps a legacy allow-list that may shrink and may never grow, must stay sorted, and may not name a
  file that has since been converted.

## Builds

Build frontend from `frontend/` with `npm run build`; this build is required
before a commit. Check public docs from `docs\dj-track-similarity` with
`npm run check`; it checks `README.md` plus the VitePress Markdown tree with
strict Vale failures and builds VitePress. Run `npm run vale:sync` once after a
fresh checkout or when `.vale.ini` packages change. Use `npm run lint:style`
when you want a non-failing style report while editing. The docs `site/`
directory is generated output and is not tracked in Git.
