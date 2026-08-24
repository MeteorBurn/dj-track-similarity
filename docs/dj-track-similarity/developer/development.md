# Development workflow

What you need to run the project from a checkout, and where the moving parts sit while you work on
it.

## Setup

From a fresh Windows checkout, create the base Python environment, install the
frontend dependencies used by the launcher, and verify the shared FFmpeg runtime:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
npm --prefix .\frontend install
dj-sim doctor
```

Use the locked optional stack when working on model-backed analysis or Rhythm
Lab:

```powershell
uv sync --locked --extra sonara --extra ml --extra rhythm-lab --extra dev
```

Use `uv` for installs containing the `ml` extra because `pip` does not apply `[tool.uv.sources]`.
On Windows AMD64 with Python 3.10, `uv` selects the PyTorch packages from the CUDA 13.0 index.

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
- Root Pytest collects only `tests/`; run `tools/rhythm-lab/tests` and
  `scripts/tests` explicitly when changing those areas.

## Builds

Build frontend from `frontend/` with `npm run build`; this build is required
before a commit. Check public docs from `docs\dj-track-similarity` with
`npm run check`; it checks `README.md` plus the VitePress Markdown tree with
strict Vale failures and builds VitePress. Run `npm run vale:sync` once after a
fresh checkout or when `.vale.ini` packages change. Use `npm run lint:style`
when you want a non-failing style report while editing. The docs `site/`
directory is generated output and is not tracked in Git.
