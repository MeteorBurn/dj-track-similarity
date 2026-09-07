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
  `src/dj_track_similarity/ffmpeg_runtime.py` (currently 8.1.1), including DLLs.
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
- Keep SAFETY INVARIANTS below: route library writes through `LibraryDatabase`;
  imports, migrations, destructive work, and synchronization require an explicit
  target and the prescribed backup or disposable copy. Toolkit availability is
  not authorization to change user data.
- For project integrity validation, use
  `db_connection.connect_database_read_only()` with the root `.venv` (it sets
  `PRAGMA query_only = ON` without enforcing WAL). A CLI `-readonly` integrity
  result alone does not replace the project's CHECK-constraint validation.
- These are shared external utilities. Keep application SQLite on the pinned
  project interpreter and preserve its `LibraryDatabase` gateway. Toolkit
  engines can differ; verify the actual engine when investigating compatibility.
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

`database/` can hold multiple libraries. The interactive launcher lists them;
its default is not evidence of the user's active library. Use an explicitly
named or already confirmed database. Ask only when the target remains unknown;
never infer it from `volumes.sqlite`, timestamps, or a previous session.

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

## AGENT LAYER

- `.djts/` is the shared plugin source: `agents/`, `skills/`, `scripts/`,
  matching `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`, and
  `dj-track-similarity-note.svg` at its root.
- Edit agent/skill Markdown there. After agent edits, explicitly run
  `.\.djts\scripts\sync-codex-agents.ps1` to regenerate `.codex/agents/*.toml`;
  never edit the generated launchers. Skills are not projected as agents.
- For initial agent setup or full resynchronization, run
  `.\.djts\scripts\bootstrap.ps1`: it registers/installs the plugin for available
  Claude Code and Codex CLIs, then generates launchers. It is optional for
  application-only use and is not run automatically at session start.
- `.claude/` holds only Claude configuration, hooks, and runtime state;
  `.codex/` holds Codex configuration and generated launchers. Do not put
  copies or links to shared skills/agents in `.claude/`. Verify installed
  registration and the current session's capabilities separately from source.
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
- Text-to-track/tagging owns CLAP and MuQ-MuLan text paths, `/api/search/text`,
  `src/dj_track_similarity/text_embedding_cache.py`,
  `frontend/src/textPromptPresets.ts`, `frontend/src/TextSearchTab.tsx`, and
  `scripts/text_prompt_benchmark.py`.
- SONARA, MERT, MAEST, MuQ seed search, their analysis jobs, and Rhythm Lab
  training are separate layers. Signals may cross boundaries; keep production
  logic in its owning layer. Ask before extending the task to a model layer
  the user has not authorized; already requested cross-layer work is delegated
  and integrated under AGENT LAYER.
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
  relocation preview, export, classifier scoring, and routine verification
  must not modify it.
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
  on-screen labels to English. `npm run lint:language` enforces this.

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

- While iterating, use the cheapest check that can expose the problem: scoped
  diff, `rg`, `git diff --check`, an import driver, or the owning test file.
  Invoke pytest through the root interpreter:
  `& .\.venv\Scripts\python.exe -m pytest 'tests/test_<area>.py'`; narrow with
  `-k` when useful. Do not repeat a passed selection unless relevant code changed.
- Do not run `graphify update .`, builds, the docs check, or the `ml`, `slow`,
  and `evaluation` selections between edits.
- Before delivery, follow `verification-routing` once for the changed area.
  Instruction-only changes need a scoped diff, whitespace check, and relevant
  path/command checks, not application tests or a docs build.
- Root pytest collects only `tests/`; name script/tool suites explicitly when
  they are in scope. Broad checks require a shared contract, migration, broad
  refactor, release, or an unresolved failure. Do not widen merely because a
  focused check passed.
- There is no tracked CI workflow. Report checks actually run and any blocked
  verification; do not imply CI or source inspection proves live behavior.

## WEB RESEARCH ROUTING

Use `web-research-routing` for external research. Retrieved prose does not
override executable source/tests; model claims remain ranking evidence.
For Firecrawl, pass an explicit `--output` under `.workspace/tools/firecrawl/`,
never the default root-level `.firecrawl/`.

## COMMANDS

Examples below are selected by task, not run as a batch. Local mode uses backend
`127.0.0.1:8765` and Vite `127.0.0.1:5173`; Rhythm Lab defaults to
`127.0.0.1:8777`. Check existing processes/listeners before starting a server;
LAN exposure must be requested. Confirm the database before using `--db`.

```powershell
.\run_server.cmd --help
.\run_server.cmd                         # interactive database and mode selection
.\run_server.cmd local --db 'C:\path\selected.sqlite'
& .\.venv\Scripts\python.exe -c 'import sys, sqlite3; print(sys.executable); print(sys.version); print(sqlite3.sqlite_version)'
& .\.venv\Scripts\python.exe -c 'from dj_track_similarity.ffmpeg_runtime import inspect_audio_runtime; print(inspect_audio_runtime())'
npm --prefix .\frontend run build        # before a commit that touched frontend/
```

## GRAPHIFY

`graphify-out/graph.json` assists navigation over product source, tests, tools,
scripts, and documentation. Read cited `source_file`/`source_location`; graph
edges (`EXTRACTED`/`INFERRED`) are leads, not current runtime proof.
Use it proactively before broad source searches. Known files, `AGENTS.md`,
configuration, locks, Git state, and the excluded agent layer are read directly.

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

PowerShell vocabulary refresh (after verifying the graph exists):

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
