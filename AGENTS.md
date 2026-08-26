# PROJECT KNOWLEDGE BASE

This is the single instruction file for `dj-track-similarity`. Do not add nested
`AGENTS.md` files unless the user explicitly asks for a new instruction boundary.
Keep this file current by replacing obsolete guidance rather than layering rules.

## OVERVIEW

Local-first DJ-library workbench with a Python/FastAPI backend, SQLite, React/Vite,
and VitePress. Model outputs are ranking evidence, never objective DJ decisions.

## NEW CONTRIBUTOR START

- Development is Windows-first. Use Python `>=3.10`, Node/npm for frontend or
  docs work, and FFmpeg `8.1.1` as a full shared build; `ffmpeg.exe` alone is
  insufficient.
- Base checkout setup from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
npm --prefix .\frontend install
dj-sim doctor
```

- Use `uv sync --locked --extra sonara --extra ml --extra rhythm-lab --extra dev`
  for model-backed or Rhythm Lab development. Do not install the `ml` extra with
  pip because pip does not apply the PyTorch source declared in `pyproject.toml`.
- `run_server.cmd` starts backend `127.0.0.1:8765` and Vite `127.0.0.1:5173`;
  Rhythm Lab uses `127.0.0.1:8777`. Check for an existing project process before
  claiming a fixed port.
- Read `README.md` for product setup, then `docs/dj-track-similarity/developer/`
  for architecture, development, and verification details.

## STRUCTURE

| Area | Purpose |
|---|---|
| `src/dj_track_similarity/` | Python package: CLI, API, database, search, analysis, model adapters |
| `frontend/src/` | React UI; `main.tsx` mounts the controller in `App.tsx` |
| `tests/` | Primary Python unit/integration suite |
| `frontend/tests/` | Node tests for frontend behavior and API contracts |
| `scripts/` | Launch, benchmarks, database QA, and text-layer evaluation |
| `tools/` | Separately scoped Audio Doctor, Audio Dedup, Rhythm Lab, and helper tools |
| `docs/dj-track-similarity/` | Maintained VitePress documentation and docs tooling |
| `.agents/skills/` | Project-specific agent workflows |
| `database/`, `logs/`, `reports/` | Local user state; never use as automated-test fixtures |
| `frontend/dist/`, `graphify-out/` | Generated output; do not hand-edit |

## WHERE TO LOOK

| Task | Location |
|---|---|
| Installed command surface | `pyproject.toml` -> `dj_track_similarity.cli:app` |
| API composition and static UI mount | `src/dj_track_similarity/api.py:create_app` |
| Database access and write locking | `src/dj_track_similarity/database.py:LibraryDatabase` |
| Shared ranking/search | `src/dj_track_similarity/search.py:SimilaritySearch` |
| Analysis contracts and model identities | `src/dj_track_similarity/analysis_models.py` |
| Analysis orchestration | `src/dj_track_similarity/analysis_jobs.py`, `analysis_pipeline.py`, `analysis_model_runners.py` |
| Model-specific embedding production | `src/dj_track_similarity/embedding.py` |
| Frontend API contracts | `frontend/src/api.ts`, `frontend/src/apiClient.ts` |
| Windows app launcher | `run_server.cmd`, `scripts/run_server_launcher.py` |
| Maintained product documentation | `README.md`, `docs/dj-track-similarity/` |

## CODE MAP

| Symbol | Role / blast radius |
|---|---|
| `cli.app` / `cli.serve` | Typer entry; server path reaches `create_app()` and Uvicorn |
| `api.create_app` | Registers route modules, database state, and built frontend assets |
| `LibraryDatabase` | Required gateway for library SQLite reads/writes and locking policy |
| `SimilaritySearch` | Shared seed, vector, and contrast-vector ranking boundary |
| `AnalysisJobManager` | Coordinates model runners, staging, writes, progress, and cancellation |
| `analysis_models` contracts | Shared family/output/reset types; changes affect backend, tests, and UI |
| `frontend App` | Main UI controller for database, jobs, search, preview, and export |
| `frontend api` | High-centrality client used by the UI; keep backend types aligned |

## CHANGE ROUTING

- Add or change HTTP endpoints in the matching `api_routes_*.py` module; keep
  `api.py:create_app` focused on application composition and shared state.
- Database changes belong in `database.py` plus the focused `db_*.py` storage,
  schema, or identity module. Preserve `LibraryDatabase` as the public gateway.
- When an API payload changes, update the backend contract, `frontend/src/api.ts`,
  `frontend/src/apiClient.ts`, UI callers, and focused Python/Node contract tests
  together.
- Keep frontend state coordination in the existing hooks/helpers rather than
  growing `App.tsx`; use `App.tsx` to compose workflows and panels.
- Tool-specific code under `tools/` and script code under `scripts/` have their
  own focused suites. Root pytest configuration collects only `tests/`.
- Dependency changes use the owning package manager and lockfile: `uv.lock` for
  Python and `frontend/package-lock.json` for the frontend. Do not hand-edit locks.

## OPERATING MODEL

- The checkout is under active development. Current schemas, model sets,
  weights, defaults, commands, ports, and UI structure are not permanent APIs.
- Treat requested behavior as the new source of truth. Add compatibility or
  migrations only for persisted data, external consumers, or explicit requests.
- Prefer one discoverable source of truth. Do not add aliases, duplicate
  registries, version gates, or hidden legacy branches. TEST POLICY governs what
  the suite is allowed to pin.
- Keep work scoped and preserve unrelated dirty changes. Work on `main` unless
  the user asks for a branch or worktree.
- Inspect `git status` and the scoped diff before delivery. Do not stage local
  databases, audio, logs, reports, model artifacts, or generated output.
- Executable sources and tests beat prose when they disagree.

## MODEL LAYER OWNERSHIP

- State the model layer before changing shared files.
- Text-to-track/tagging owns CLAP and MuQ-MuLan text paths, `/api/search/text`,
  `src/dj_track_similarity/text_embedding_cache.py`,
  `frontend/src/textPromptPresets.ts`, `frontend/src/ClapSearchTab.tsx`, and
  `scripts/text_prompt_benchmark.py`.
- SONARA, MERT, MAEST, MuQ seed search, their analysis jobs, and Rhythm Lab
  training are separate layers. Signals may cross boundaries; production logic
  may not. Route changes to another layer back to the user.
- Shared surfaces such as `search.py`, `analysis_models.py`, `TrackRows.tsx`,
  and family unions in `frontend/src/api.ts` take additive, scoped changes only.
- Keep CLAP text scores separate from audio-to-audio CLAP signals. Never
  substitute MuQ, MERT, MAEST, CLAP, MuQ-MuLan, or SONARA evidence for another.
- Zero-shot text tags are additional evidence, not replacements for MAEST or
  classifier scores; never write them to `classifier_scores` or audio files.
- Browser search tabs are rank-only: use `Limit`, preserve descending scores,
  and do not add a minimum-similarity threshold. API/CLI thresholds and Audio
  Dedup content gates are separate workflows.
- Delegate text-search/model-choice work with `clap-query-workflow`; delegate
  preset/axis/tag vocabulary work with `prompt-bank-curator`. Reliability claims
  require a committed `scripts/text_prompt_benchmark.py` table.

## SAFETY INVARIANTS

- Treat source audio as user data. Scan, preview, analysis, search, reset,
  relocation preview, export, graph export, classifier scoring, and routine
  verification must not modify it.
- Normal tag writing is explicit and genre-only. Browser AIFF preview may use a
  temporary WAV but must not rewrite or cache the source.
- Route SQLite writes through `LibraryDatabase`; preserve WAL, busy-timeout,
  and per-database locking. Real-database destructive work requires a backup or
  disposable copy plus integrity and orphan checks.
- Startup must not silently migrate old databases. Migrations are explicit,
  recoverable workflows; reanalysis remains a separate user choice.
- Keep launcher subprocess arguments list-based with `shell=False`. Local mode
  binds `127.0.0.1`; LAN exposure must be explicit.
- Audio Doctor is dry-run-first, confirmation-gated, backup-first, verified,
  and rollback-capable. Audio Dedup is report-first and deletes only confirmed,
  qualified targets inside the selected root. Never run apply modes for QA.
- Rhythm Lab state remains separate from the source database except its explicit
  liked-track toggle. Classifier scoring is database-only, scoped by classifier
  key, and must validate promoted manifest feature order and artifact hashes.
- Automated model/audio/database tests use temporary SQLite/WAV fixtures and
  stubs, never real project databases, music files, or downloaded model runs.

## DOCUMENTATION WORKFLOW

- Maintained docs are only `README.md` and `docs/dj-track-similarity/` unless the
  user requests another artifact.
- Docs have their own npm environment. From `docs/dj-track-similarity/`, run
  `npm install`; run `npm run vale:sync` after a fresh checkout or Vale-package
  change. Never edit generated `site/` output.
- After behavior changes, delegate documentation to a dedicated sub-agent using
  `codebase-documentation-writer`. Pass implemented behavior and changed paths.
- Documentation is independent and must not block implementation, verification,
  commits, or later tasks. It describes current behavior, not plans.
- Do not create architecture notes, changelogs, migration documents, or local
  docs unless explicitly requested. Docs-only changes use docs-only checks.

## TEST POLICY

The suite is a set of standing contracts, not a log of past edits. It should
stay roughly the same size from one feature to the next. A change does not earn
a test by existing, and a growing test count is a defect, not progress.

- Add a test only for something durable: a persisted schema, migration, or
  on-disk format; an HTTP payload, CLI contract, or other cross-boundary shape;
  a scoring, ranking, or safety invariant; or a reproduced bug whose cause is
  understood, asserted at the cause rather than the symptom.
- Add no test for cosmetics, labels, copy, tooltips, colors, class names, the
  order of fields, rows, or menu entries, or a default, threshold, or option
  that is expected to keep moving.
- Add no test for wiring that the type checker, the import graph, or an existing
  focused run already covers.
- Never assert on the text of a source file. Reading a module, script, or
  `.cmd` file and matching strings pins how the code is written instead of what
  it does. Drive the running module and assert its behavior.
  `frontend/tests/testsExecuteCode.test.mjs` enforces this on the frontend.
- When behavior changes, edit the existing test that owns that contract instead
  of adding a second one. Two tests over one contract mean one is redundant.
- Delete a test whose contract is gone, and delete a test that blocks an
  intentional change while pinning only an incidental detail. Removing a test is
  a normal part of a change, not a regression.

## VERIFICATION ROUTING

Verification runs in two phases. While iterating, run the smallest selection
that can fail. At the end, run one pass scoped to what the change touched. The
global suites are for global changes; `.github/workflows/ci.yml` is the backstop
that runs everything on a clean machine when that is what the moment needs.

### While iterating

- Run only the tests covering the lines just edited: `python -m pytest
  tests/test_<area>.py`, narrowed further with `-k` when the file is large.
  One file is the normal unit; the whole suite is not.
- Do not re-run a selection that already passed while its code was untouched.
- Reading the scoped diff, `rg` sentinels, `git diff --check`, and a minimal
  import driver are cheaper than any suite. Reach for them first.
- Between edits, do not run `graphify update .`, `npm run build`, the docs
  check, or the `ml`, `slow`, and `evaluation` markers.

### Before delivery, once

Nothing in this list runs by default. Each line runs only when the change
actually touched what the line covers.

- `python -m pytest tests` is the global backend pass: 680 tests, about 40
  seconds. Run it only when the change reaches past one module — a shared
  contract, a persisted schema or migration, `LibraryDatabase`,
  `SimilaritySearch`, `AnalysisJobManager`, the `analysis_models` contracts, a
  broad refactor, or a release.
- A backend change confined to one module or one feature ends at the test files
  owning that module. That focused run is the whole backend pass for it; do not
  widen to `tests/` to feel safe.
- When no file under `src/` changed, do not run `tests/` at all. A frontend,
  docs, script, or tool change is verified in its own area and nowhere else.
- `scripts/tests`, `tools/audio-dedup/tests`, and `tools/rhythm-lab/tests` run
  only when those directories were touched; together they take about 20 seconds.
- Frontend, only when `frontend/` was touched: `npm run typecheck`, `npm test`,
  and `npm run build` before a commit. The three cost about 8 seconds.
- `graphify update .` once after the last source edit, not per edit. It rebuilds
  the whole graph and takes about 30 seconds.
- Docs site: run `npm run check` from `docs/dj-track-similarity/` only for
  maintained docs content or docs tooling changes.
- For behavior changes, exercise the matching surface once: browser for UI, live
  HTTP request for API, CLI invocation for commands, or a minimal import driver
  for library code. Cover one happy path and one relevant failure path.

### Scope gates

- Instructions/docs only: inspect the scoped diff, run `git diff --check --
  <paths>`, and use targeted `rg` sentinels. Do not run application suites.
- Root pytest collects only `tests/`; the script and tool suites are named
  explicitly or they do not run at all.
- Widen past the focused selection only for a shared contract, migration, broad
  refactor, release, or a focused-test failure whose cause is not yet clear.
- A frontend test must load the module it checks as running code, through
  `ssrLoadModule`, `transpileModule`, or a direct `../src/` import. Asserting on
  source text pins how a component is written instead of what it does.
  `frontend/tests/testsExecuteCode.test.mjs` enforces this and carries the
  shrinking list of files that predate the rule.
- `.github/workflows/ci.yml` runs the cheap tier on a clean machine, by manual
  trigger only. Pushing to `main` starts nothing.

## WEB RESEARCH ROUTING

- Configured servers are `tavily` and `firecrawl` in `opencode.json`; both spend
  API credits. Start with built-in `websearch`/`webfetch` and escalate only when
  the built-in result is insufficient.
- Facts, news, or link discovery: `tavily_search`. Multi-source questions that
  need synthesis: `tavily_research`.
- Content of a known URL: `tavily_extract` for plain pages, `firecrawl_scrape`
  for JS-rendered or protected pages.
- Schema-based structured extraction: `firecrawl_extract`. Site traversal:
  `firecrawl_map` for URLs, `firecrawl_crawl` with an explicit `limit`.
- Library, API, and error questions: `firecrawl_developer_search` over indexed
  GitHub issues, pull requests, READMEs, and documentation.
- Audio-model literature (CLAP, MuQ, MuQ-MuLan, MERT, MAEST, SONARA):
  `firecrawl_research_*`. Name the paper ID with any claim taken from it.
- Retrieved prose never outranks this checkout. Executable sources and tests win
  on conflict, and retrieved model claims remain ranking evidence.

## COMMANDS

```powershell
run_server.cmd                         # interactive backend + Vite UI
run_server.cmd local --db C:/db/library.sqlite
python -m pytest tests/test_sonara_features.py
python -m pytest tools/rhythm-lab/tests/test_rhythm_lab.py
npm --prefix .\frontend run typecheck
npm --prefix .\frontend test
npm --prefix .\frontend run build      # mandatory before a commit
npm --prefix .\docs\dj-track-similarity run check
```

## GRAPHIFY

When the user types `/graphify`, use the graphify skill first. Prefer scoped
`graphify query`, `path`, and `explain` commands, then `graphify-out/wiki/index.md`.
Read `GRAPH_REPORT.md` only when needed; dirty generated graph files are expected.
