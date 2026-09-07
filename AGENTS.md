# PROJECT KNOWLEDGE BASE

This is the single instruction file for `dj-track-similarity`. Do not add nested
`AGENTS.md` files unless the user explicitly asks for a new instruction boundary.
Keep this file current by replacing obsolete guidance rather than layering rules.

## OVERVIEW

Local-first DJ-library workbench with a Python/FastAPI backend, SQLite, React/Vite,
and VitePress. Model outputs are ranking evidence, never objective DJ decisions.

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

## SQLITE TOOLKIT

For SQLite inspection and diagnostics in this project, agents must use the
shared installation at `C:\Utils\tools\sqlite-toolkit`. This section is the
complete project usage guide: do not read that directory's `AGENTS.md` as a
prerequisite. Use the selected command's `--help` only when a needed option is
unclear. Invoke these verified absolute paths from PowerShell:

| Executable | Use |
|---|---|
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3.exe` | Default for SQL, tables/schema/indexes, query plans, and exports |
| `C:\Utils\tools\sqlite-toolkit\bin\sqlite-utils.exe` | Discovery and JSON/CSV conversion when it simplifies the task |
| `C:\Utils\tools\sqlite-toolkit\bin\datasette.exe` | Interactive browsing when requested; bind to loopback |
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3_analyzer.exe` | Database size and storage analysis |
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqldiff.exe` | Compare schema and data in two databases; review its output before applying SQL |
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3_rsync.exe` | Synchronization only when explicitly requested |

- Identify the exact database first, following STRUCTURE below; never guess the
  current library. Resolve an existing path so a typo cannot create a new file.
- Start with `sqlite3 -readonly`, inspect tables/schema, and use `LIMIT` for
  exploratory queries. Use a consistent snapshot for comparisons of a live DB.
  Keep deterministic automation on `sqlite3`; use the other tools as needed.
- Follow SAFETY INVARIANTS below for application database access. Imports,
  migrations, destructive work, and synchronization require an explicit
  target and the prescribed backup or disposable copy. Toolkit availability is
  not authorization to change user data.
- For project integrity validation, use
  `db.connection.connect_database_read_only()` with the root `.venv` (it sets
  `PRAGMA query_only = ON` without enforcing WAL). A CLI `-readonly` integrity
  result alone does not replace the project's CHECK-constraint validation.
- Ordinary application startup is not a read-only database inspection:
  `LibraryDatabase.connect()` enforces WAL, and database selection can refresh
  `track_search_fts` through `ensure_search_index_current()`. Use the explicit
  read-only path for verification of a user library.
- These are shared external utilities. Keep application SQLite on the pinned
  project interpreter. Toolkit engines can differ; verify the actual engine
  when investigating compatibility.
  Do not add Toolkit packages to the project, activate its private environments,
  change PATH, or install/update tools as a prerequisite to routine use.

Read-only PowerShell example (replace the example path with the identified DB):

```powershell
$databasePath = (Resolve-Path -LiteralPath 'C:\path\selected.sqlite' -ErrorAction Stop).Path
$sqlite = 'C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3.exe'
& $sqlite -readonly $databasePath '.tables'
& $sqlite -readonly $databasePath '.schema'
& $sqlite -readonly -header -column $databasePath 'SELECT name, type FROM sqlite_schema ORDER BY name LIMIT 50;'
```

## STRUCTURE

| Area | Purpose |
|---|---|
| `database/`, `logs/`, `reports/` | Local user state; never use as automated-test fixtures |
| `frontend/dist/`, `graphify-out/` | Generated output; do not hand-edit |
| `.workspace/` | Local working output only: `audits/`, `handoffs/`, `ideas/`, `reports/`, `specs/`, and `tools/firecrawl/`; never a source of agents or skills |
| `.djts/` | The one tracked plugin root: `agents/`, `skills/`, plugin manifests, icon, and projection scripts |

The local inventory verified on 2026-09-08 after the owner's cleanup contains
only `.workspace/.gitignore` and three backlogs in `.workspace/specs/`:
`engineering-reliability.md`, `mir-quality-evaluation.md`, and
`prompt-search-and-personalization.md`. Earlier supporting artifact paths are
absent from this workspace; transcribed results are historical summaries.
Inspect the live tree before reusing a path. Do not recreate deleted artifacts
or create cleanup archives unless requested. Consolidate related pending work
and remove obsolete notes and empty nested directories during requested cleanup.
The plans remain local and ignored by Git.

`database/` can hold multiple libraries. The interactive launcher lists them;
its default is not evidence of the user's active library. Use an explicitly
named or already confirmed database. Ask only when the target remains unknown;
never infer it from `volumes.sqlite`, timestamps, or a previous session.

Python packages under `src/dj_track_similarity/` follow responsibility boundaries:

| Package | Owns |
|---|---|
| `api/` | FastAPI composition, routes, payload schemas, database selection and preview serving |
| `cli/` | Typer composition, command groups, shared input/output and progress |
| `audio/` | Decoding, audio loading and shared FFmpeg discovery |
| `embedding/` | Family adapters, construction registry, capability types, shared loading/audio/numerics and text cache |
| `analysis/` | Jobs, queue, pipeline, model runners, staging and SONARA extraction/runtime/results |
| `db/` | Repositories, connections, schema, stored formats, queries, migration and maintenance |
| `classifier/` | Promoted manifests/artifacts, feature requirements, scoring and jobs |
| `search/` | Ranking engines, vector index, SONARA similarity and reference comparison |
| `evaluation/` | Evaluation datasets, experiments, metrics and reports |

Keep shared domain contracts such as `analysis_models.py`, `track_models.py` and
`library_models.py` at the package root. Import implementations from their
owning modules; keep `__init__.py` lightweight and preserve the installed
`dj_track_similarity.cli:app` entry point.
Keep SONARA processing, ranking, classifier features and persistence with their
respective package owners.

## CODE MAP

| Symbol | Role / blast radius |
|---|---|
| `cli.app` / `cli.application.serve` | Typer entry; server path reaches `create_app()` and Uvicorn |
| `api.application.create_app` | Registers route modules, database state, and built frontend assets |
| `database.LibraryDatabase` | Main application library gateway; access rules are in SAFETY INVARIANTS |
| `search.engine.SimilaritySearch` | Shared seed, vector, and contrast-vector ranking boundary |
| `analysis.jobs.AnalysisJobManager` | Coordinates model runners, staging, writes, progress, cancellation and runtime release |
| `analysis.queue.AnalysisStageQueue` | Serial execution and draining of accepted analysis/classifier work |
| `api.state.AppDatabaseState` | Owns the selected database's managers and queue; replaces and closes their resources |
| `embedding.registry.create_embedding_adapter` | Typed lazy construction shared by analysis and text API |
| `embedding.text_cache.TextEmbeddingAdapterCache` | Application-owned text adapters, leases and idle expiry |
| `analysis_models` contracts | Shared family/output/reset types; changes affect backend, tests, and UI |
| `frontend App` | Main UI controller for database, jobs, search, preview, and export |
| `frontend api` | High-centrality client used by the UI; keep backend types aligned |

## AGENT LAYER

- `.djts/` is the shared plugin source: `agents/`, `skills/`, `scripts/`,
  matching `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`, and
  `dj-track-similarity-note.svg` at its root.
- Edit agent/skill Markdown there. After agent edits, explicitly run
  `.\.djts\scripts\sync-codex-agents.ps1` to regenerate `.codex/agents/*.toml`;
  never edit the generated launchers. Skills are not projected as agents.
- For initial agent setup, run
  `.\.djts\scripts\bootstrap.ps1`: it registers/installs the plugin for available
  Claude Code and Codex CLIs, then generates launchers. It is optional for
  application-only use and is not run automatically at session start.
- For a requested plugin refresh, inspect its registered source and installation
  scope first. Preserve the version unless the user requests a version change.
  Refresh Codex with `codex plugin add dj-track-similarity@dj-track-similarity`.
  For Claude, set `$pluginScope` to the verified existing scope (this checkout
  uses `project`), then run
  `claude plugin update dj-track-similarity@dj-track-similarity --scope $pluginScope --yes`.
  If the installed content remains stale at the same version, run
  `claude plugin uninstall dj-track-similarity@dj-track-similarity --scope $pluginScope --keep-data`
  followed by
  `claude plugin install dj-track-similarity@dj-track-similarity --scope $pluginScope --yes`.
  Target only this plugin; bootstrap or a successful update message alone does
  not prove its cached content was refreshed.
- Compare the installed plugin files and skill inventory with `.djts/`, including
  removal of deleted skills. Verify registration and enabled state separately.
  An already open session can retain old capabilities until restarted.
- `.claude/` holds only Claude configuration, hooks, and runtime state;
  `.codex/` holds Codex configuration and generated launchers. Do not put
  copies or links to shared skills/agents in `.claude/`.
- Keep `.workspace/` scoped as listed in STRUCTURE. Optional AgentProof/Superpowers
  state stays at its supported roots (`.agentproof/`, `.superpowers/`), without
  junction redirection.
  OpenCode/OMO are external and optional: do not restore `opencode.json`;
  clear `.omo/` only when cleanup is requested and no OMO/OpenCode process runs.

An agent owns a role; a skill is a reusable task. Keep role-specific procedures
inside the owning agent and shared tasks in `.djts/skills/`. Reference current
configuration and source instead of duplicating model lists, paths, or thresholds.

| Agent | Ownership |
|---|---|
| `code-explorer` | Read-only execution paths, architecture, callers, and blast radius |
| `ml-engineer` | Audio representations, inference, classifiers, similarity semantics, ML evaluation |
| `database-expert` | Schema, indexes, queries, migrations, integrity, locking |
| `backend-engineer` | HTTP/CLI contracts, jobs, service Python, environment |
| `frontend-engineer` | React/Vite, client state, typed API client, rendering |
| `performance-optimizer` | Bottleneck localization, profiling, benchmarks, measured improvement |
| `test-reviewer` | Test value, fixtures, suite health, failure triage |
| `code-refactor-master` | Behavior-preserving splits, moves, deduplication, reference updates |

Delegate work across these ownership boundaries and integrate it into one answer.
Give each worker a bounded scope, relevant instructions, and dirty-state context;
workers must preserve others' edits. Honor the active harness's delegation rules.
`context: fork` in a skill is effective only in harnesses that support it.

## CHANGE ROUTING

- Add or change HTTP endpoints in the matching `api/routes_*.py` module; keep
  `api/application.py:create_app` focused on application composition and shared state.
- Database changes belong in `database.py` plus the focused `db/*.py` storage,
  schema, or identity module; follow the access boundaries in SAFETY INVARIANTS.
- Route command changes to the owning `cli/` group and register root commands
  explicitly. Keep `cli/application.py` focused on composition and its retained
  commands; command modules must not import the application composer.
- When moving modules, update all consumers and actual-owner monkeypatch targets,
  including scripts, tools and Windows process-pool references. Preserve resource
  roots derived from module paths; moving code does not move assets or databases.
- When an API payload changes, update the backend contract, `frontend/src/api.ts`,
  `frontend/src/apiClient.ts`, UI callers, and focused Python/Node contract tests
  together.
- Keep frontend state coordination in the existing hooks/helpers rather than
  growing `App.tsx`; use `App.tsx` to compose workflows and panels.
- Dependency changes use the owning package manager and lockfile: `uv.lock` for
  Python and `frontend/package-lock.json` for the frontend. Do not hand-edit locks.
- UI work follows `DESIGN.md` at the repository root: no raw colours inside
  components, `type="button"` on every button that does not submit.

## OPERATING MODEL

- The checkout is under active development. Current schemas, model sets,
  weights, defaults, commands, ports, and UI structure are not permanent APIs.
- Treat requested behavior as the new source of truth. Add compatibility or
  migrations only for persisted data, external consumers, or explicit requests.
- Prefer one discoverable source of truth. Do not add aliases, duplicate
  registries, version gates, or hidden legacy branches. TEST POLICY governs what
  the suite is allowed to pin.
- Inspect `git status --short` and the relevant existing diff before editing.
  Preserve unrelated work. Create branches, commits, or PRs and push only when
  requested. For authorized Git delivery, use `main`: fetch before committing,
  compare ancestry with `origin/main`, and account for parallel worktrees.
  New branches start from `origin/main` (default prefix `codex/`).
  `dev` is frozen as of 2026-09-04; do not push to it or branch from it.
- Inspect `git status` and the scoped diff before delivery. Do not stage local
  databases, audio, logs, reports, model artifacts, or generated output.
- Executable sources and tests beat prose when they disagree.

## MODEL LAYER OWNERSHIP

- State the model layer before changing shared files.
- `embedding/registry.py` owns the single `adapter_factories()` map and typed
  `create_embedding_adapter()` factory; `embedding/contracts.py` defines the
  capabilities used by callers. Use the factory for shared analysis/text API
  construction. Family-specific callers import concrete classes from their
  family modules. SONARA keeps its dedicated runner in `analysis/model_runners.py`.
- Keep heavy imports and weight loading lazy. Each embedding adapter serializes
  construction per instance, checks readiness again after acquiring its lock,
  and publishes ready state only after all family preparation succeeds. Preserve
  shared MuQ/MuLan and CLAP construction locks, verified asset lifetimes and
  restoration of temporary loader bindings through `finally`.
- Loaded analysis runners belong to `AnalysisJobManager`; text adapters belong
  to the application's `TextEmbeddingAdapterCache`. Preserve their separate
  caches, leases and runtime keys. Database switching releases old analysis
  owners while retaining the application text cache.
- Owners drain `AnalysisStageQueue` before closing `AnalysisJobManager`, so
  accepted pipeline callbacks can finish their child stages. A closing queue
  rejects further submissions; release runners only after admitted work unwinds.
  Perform joins and final resource release outside locks needed by callbacks,
  and reject self-close. Replacement construction failure preserves the previously
  published state.
  App teardown closes these analysis owners and the text cache; analysis CLI
  closes its queue/manager. CLI cleanup must await actual worker completion even
  when progress reporting or a thread join is interrupted.
- Text-to-track/tagging owns CLAP and MuQ-MuLan text paths, `/api/search/text`,
  `src/dj_track_similarity/embedding/text_cache.py`,
  `frontend/src/textPromptPresets.ts`, `frontend/src/TextSearchTab.tsx`, and
  `scripts/text_prompt_benchmark.py`.
- SONARA, MERT, MAEST, MuQ seed search, their analysis jobs, and Rhythm Lab
  training are separate layers. Signals may cross boundaries; keep production
  logic in its owning layer. Ask before extending the task to a model layer
  the user has not authorized; already requested cross-layer work is delegated
  and integrated under AGENT LAYER.
- Shared surfaces such as `search/engine.py`, `analysis_models.py`, `TrackRows.tsx`,
  and family unions in `frontend/src/api.ts` take changes within the requested
  scope. Preserve unaffected contracts; update affected consumers together when
  the requested behavior changes a shared contract.
- Do not expand, redesign, or remove Model Listening Lab without a new request.
- Keep CLAP text scores separate from audio-to-audio CLAP signals. Never
  substitute MuQ, MERT, MAEST, CLAP, MuQ-MuLan, or SONARA evidence for another.
- Zero-shot text tags are additional evidence, not replacements for MAEST or
  classifier scores; never write them to `classifier_scores` or audio files.
- Browser search tabs are rank-only: use `Limit`, preserve descending scores,
  and do not add a minimum-similarity threshold. API/CLI thresholds and Audio
  Dedup content gates are separate workflows.
- Delegate text-search/model-choice work with `clap-query-workflow`. Reliability claims
  require a committed `scripts/text_prompt_benchmark.py` table.

## SAFETY INVARIANTS

- Treat source audio as user data. Scan, preview, analysis, search, reset,
  relocation preview, export, classifier scoring, and routine verification
  must not modify it.
- Normal tag writing is explicit and genre-only. Browser preview transcoding
  uses temporary output and must not rewrite or cache the source audio.
- Use `LibraryDatabase` for the main application's library reads and writes;
  explicit read-only inspection follows SQLITE TOOLKIT above. Preserve WAL,
  busy-timeout and per-database locking on application write connections.
  Rhythm Lab keeps its existing `SourceDatabase` boundary: query-only library
  reads and the explicit liked-track toggle with its shared write-lock and
  ID/UUID checks. Its other state remains separate from the source library.
  This exception does not authorize additional direct library writes.
  Real-database destructive work requires a backup or disposable copy plus
  integrity and orphan checks.
- Preserve existing catalog/track UUID, missing-state and selected-database
  generation checks for deferred operations. A numeric track ID alone is not
  sufficient authority to write results after the underlying identity changes.
- Startup must not silently migrate old databases. Migrations are explicit,
  recoverable workflows; reanalysis remains a separate user choice.
- Package, loader and lifetime refactors preserve existing schema, saved rows,
  model/output identities, vector formats and analysis readiness. They must not
  introduce data rewrites, schema or model/adapter revision bumps, or requirements
  to reanalyze, rescore or retrain merely because source paths or in-memory
  ownership changed.
- Keep launcher subprocess arguments list-based with `shell=False`. Local mode
  binds `127.0.0.1`; LAN exposure must be explicit.
- Audio Doctor is dry-run-first, confirmation-gated, backup-first, verified,
  and rollback-capable. Audio Dedup is report-first and deletes only confirmed,
  qualified targets inside the selected root. Never run apply modes for QA.
- Classifier scoring is database-only, scoped by classifier key, and must
  validate promoted manifest feature order and artifact hashes.
- Automated model/audio/database tests use temporary SQLite/WAV fixtures and
  stubs, never real project databases, music files, or downloaded model runs.
  Keep Audio Dedup's `DEFAULT_RHYTHM_LAB_DB` as its single default constant;
  isolate tests with `tmp_path` and `monkeypatch`, not additional runtime
  configuration switches.

## DOCUMENTATION WORKFLOW

- Update documentation only when requested in the current session. A code
  change does not authorize a docs pass; do not plan/delegate one, report a gap,
  or offer to close it. Instruction-file maintenance does not imply a docs-site
  update.
- For requested product/developer documentation, use
  `codebase-documentation-writer` for scope, layer routing, and docs verification.
  Read `README.md` for setup orientation when needed; verify current behavior
  against executable source and tests. Maintained docs can lag the code.
- Document current behavior, not plans. Docs do not block implementation,
  verification, or authorized Git delivery.
- Documentation is English. Translate Russian UI labels in prose; only
  `docs/dj-track-similarity/help/ui-language.md` may contain Cyrillic to map
  on-screen labels to English.
  `npm --prefix .\docs\dj-track-similarity run lint:language` enforces this.

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
  `frontend/tests/testsExecuteCode.test.mjs` checks for loader patterns outside
  its legacy exemptions; it does not prove that assertions exercise behavior
  and does not replace review. Do not grow the legacy exemption list.
- When behavior changes, edit the existing test that owns that contract instead
  of adding a second one. Two tests over one contract mean one is redundant.
- Delete a test whose contract is gone, and delete a test that blocks an
  intentional change while pinning only an incidental detail. Removing a test is
  a normal part of a change, not a regression.

## VERIFICATION ROUTING

- While iterating, use the cheapest check that can expose the problem: scoped
  diff, `rg`, `git diff --check`, an import driver, or the owning test file.
  Invoke pytest through the root interpreter:
  `& .\.venv\Scripts\python.exe -m pytest 'tests/test_<area>.py'`; narrow with
  `-k` when useful.
- Do not run `graphify update .`, builds, the docs check, or broad `ml`, `slow`,
  and `evaluation` selections between edits. Run focused owner tests when needed,
  including fake-loader tests marked `ml`; inspect and report skips rather than
  silently excluding the checks relevant to the change.
- Before delivery, ensure checks covering the final changed state have passed.
  Reuse a passed selection unless relevant code, configuration or dependencies
  changed; do not rerun merely for delivery. Instruction-only changes need a
  scoped diff, whitespace check and relevant path/command checks, not application
  tests or a docs build.
- A localized backend change ends at its owning test files. Broaden only for
  affected shared contracts, persistence, broad refactors, releases, unresolved
  failures, or dependency/runtime/test-runner changes with broad impact. Changes
  outside `src/` do not by themselves require or prohibit backend checks.
- Root pytest collects only `tests/`. Name affected script/tool suites explicitly:
  `scripts/tests`, `tools/audio-dedup/tests`, `tools/audio-doctor/tests`,
  `tools/audio-online/tests`, or `tools/rhythm-lab/tests`.
  For Audio Online workbook-bridge changes, also run
  `node --test tools/audio-online/workbook_bridge.test.mjs` with its existing
  runtime and dependencies, including `METADATA_ENRICHMENT_NODE_MODULES`.
  Report unavailable dependencies rather than creating another environment.
- For frontend runtime or build changes, run
  `npm --prefix .\frontend run typecheck` and `npm --prefix .\frontend test`;
  also run `npm --prefix .\frontend run build`
  before a commit. Frontend instruction-only and copy-only edits do not require
  these checks. For maintained docs or docs tooling changes, run
  `npm --prefix .\docs\dj-track-similarity run check`.
- For behavior changes, exercise the matching surface with one happy path and
  one relevant failure path: browser, HTTP request, CLI, or minimal import
  driver. Existing focused tests can satisfy these scenarios when they exercise
  the matching boundary; do not duplicate them with a manual smoke solely for
  this checklist. Follow the temporary-fixture and user-data safety rules above.
- Diagnose from source first, then confirm the hypothesis on the running
  surface. For browser layout, use DOM geometry, overflow and computed styles
  where supported; use screenshots when visual inspection is needed. Prefer
  semantic locators or element references supported by the active browser tool.
- Before testing database startup or persistence-sensitive refactors, inspect
  constructor/connect/schema paths for implicit migrations or data writes.
  For broad package/loader refactors, retain the same pre-change synthetic
  database and affected classifier artifacts, then compare read/search results,
  readiness and file seals without regenerating fixtures or running analysis.
- If sandbox permissions make the default temporary directory unusable, choose
  a unique workspace `--basetemp`; redirect process `TEMP`/`TMP` and application
  logs there when subprocesses or tools bypass pytest fixtures. Never point test
  temporary paths at user libraries or remove shared temp directories to retry.
- There is no tracked CI workflow. Report checks actually run and any blocked
  verification; do not imply CI or source inspection proves live behavior.

## WEB RESEARCH ROUTING

- Start with built-in web search/page reading. Use Tavily or Firecrawl when
  those results are insufficient; account for their API-credit costs. Discover
  the tools available in the current session and follow the provider's own
  skills/help rather than assuming fixed tool names or capabilities.
- Use Tavily search for facts, news and links, research for multi-source
  synthesis, and extraction for known URLs. For difficult or JS-rendered pages,
  use the provider's supported advanced extraction or browser workflow.
- Use map for URL discovery and crawl for page content, with explicit limits.
  For structured extraction, use a supported schema workflow or shape fields
  from extracted content when that capability is unavailable.
- For library/API behavior and errors, use Firecrawl's developer index when
  available to locate official documentation, repository issues and PRs.
- For audio-model literature (CLAP, MuQ, MuQ-MuLan, MERT, MAEST, SONARA), use
  the research-paper index when available, inspect relevant papers and linked
  repositories, and cite the paper URL or ID for claims. A web-search research
  category is not equivalent to searching a paper index or reading full text.
- Retrieved prose does not override executable source/tests about this checkout;
  model claims remain ranking evidence.
- For Firecrawl CLI output, pass an explicit `--output` under
  `.workspace/tools/firecrawl/`, never the default root-level `.firecrawl/`.

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

## GRAPHIFY

`graphify-out/graph.json` assists navigation over product source, tests, tools,
scripts, and documentation. Read cited `source_file`/`source_location`; graph
edges (`EXTRACTED`/`INFERRED`) are leads, not current runtime proof.
Use it proactively before broad source searches. Known files, `AGENTS.md`,
configuration, locks, Git state, and the excluded agent layer are read directly.

For read-only tasks or modes, use the existing graph, vocabulary and lessons
without running the write steps below: vocabulary refresh, `reflect`,
`save-result` or rebuilds. If vocabulary is missing or stale, derive tokens from
graph labels in memory. Missing lessons do not block inspection. Report stale
or unavailable graph data and verify findings directly in source.

| Navigation task | Run first |
|---|---|
| Locate an area | `graphify query "<expanded tokens>"` |
| Inspect a symbol and its neighbors | `graphify explain "<symbol>"` |
| Assess a shared-symbol change | `graphify affected "<symbol>"` |
| Trace a connection | `graphify path "<A>" "<B>"` |
| Orient in unfamiliar architecture | `graphify god-nodes`, then `explain` |

Follow `.djts/skills/graphify/references/query.md` with these project rules:

1. Use the installed CLI; for Python helpers, read and validate the interpreter
   in `graphify-out/.graphify_python`. It belongs to Graphify's external tool
   environment. Do not install Graphify into the project or blindly run
   `graphify install`, which can overwrite project instructions/hooks.
2. At the start of graph work, run `graphify reflect --if-stale` and read
   `graphify-out/reflections/LESSONS.md`. Hook configuration alone does not
   prove a hook ran in the current harness.
3. Before `query`, refresh/read `.vocab.txt` from graph labels. Select up to 12
   actual vocabulary tokens (prefer 3-6 English tokens). Matching has no stemming,
   synonyms, or cross-language translation. If none fit, stop that graph search
   and use direct source inspection; do not submit a misleading query.
4. Use `--dfs` for a chain. Treat `TRUNCATED` as incomplete: narrow the query,
   use `explain`, or increase `--budget`. Disambiguate repeated labels with the
   full node ID. Open the named source before drawing conclusions.
5. Save a graph-derived finding with `save-result`: include the expanded tokens,
   cited labels, and `--outcome useful|dead_end|corrected`; for a correction add
   `--correction`. Both the saved question and answer must be English even when
   the user's request is Russian; this overrides the reference's verbatim rule.
6. Pass the relevant graph rules to code-exploration workers explicitly; do not
   assume their prompts or tool access match the parent session.

PowerShell vocabulary refresh (when writes are allowed and the graph exists):

```powershell
$graphPython = (Get-Content -LiteralPath 'graphify-out\.graphify_python' -Raw).Trim()
if (-not (Test-Path -LiteralPath $graphPython -PathType Leaf)) { throw 'Graphify interpreter missing' }
@'
import json, re
from pathlib import Path
data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
vocab = set()
for node in data['nodes']:
    for word in re.findall(r'[^\W\d_]+', node.get('label', '') or '', re.UNICODE):
        for part in re.findall(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+', word) or [word]:
            if 3 <= len(part) <= 30:
                vocab.add(part.lower())
Path('graphify-out/.vocab.txt').write_text('\n'.join(sorted(vocab)), encoding='utf-8')
'@ | & $graphPython -
if ($LASTEXITCODE -ne 0) { throw 'Graph vocabulary refresh failed' }
```

`.graphifyignore` owns corpus exclusions, including `.workspace/`, `.djts/`,
`.agents/`, `.claude/`, and `.codex/`. Fix corpus scope there, not by hiding
unwanted hits. The local post-commit hook starts code rebuilds in the background
and skips linked worktrees and some Git operations; a commit does not prove the
graph is current. Check hook output/freshness when it matters.

Do not run `graphify update .` in the edit loop or as a routine delivery check;
manual rebuilds are for corpus-exclusion changes or substantial code deletions.
If the graph/tool is unavailable or stale, report that limit and inspect source
without assuming permission to install or rebuild. Read `GRAPH_REPORT.md` only
when needed; preserve unrelated generated changes.
