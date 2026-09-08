# Architecture and change routing

Read before locating unfamiliar code, changing source ownership or shared contracts, accessing local working artifacts, or cleaning up repository structure.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

The dated workspace inventory below is a recorded snapshot. Inspect the live
tree before relying on it; this guide does not establish current file existence.

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
| `database.LibraryDatabase` | Main application library gateway; access rules are in [SAFETY INVARIANTS](../../AGENTS.md#safety-invariants) |
| `search.engine.SimilaritySearch` | Shared seed, vector, and contrast-vector ranking boundary |
| `analysis.jobs.AnalysisJobManager` | Coordinates model runners, staging, writes, progress, cancellation and runtime release |
| `analysis.queue.AnalysisStageQueue` | Serial execution and draining of accepted analysis/classifier work |
| `api.state.AppDatabaseState` | Owns the selected database's managers and queue; replaces and closes their resources |
| `embedding.registry.create_embedding_adapter` | Typed lazy construction shared by analysis and text API |
| `embedding.text_cache.TextEmbeddingAdapterCache` | Application-owned text adapters, leases and idle expiry |
| `analysis_models` contracts | Shared family/output/reset types; changes affect backend, tests, and UI |
| `frontend App` | Main UI controller for database, jobs, search, preview, and export |
| `frontend api` | High-centrality client used by the UI; keep backend types aligned |

## CHANGE ROUTING

- Add or change HTTP endpoints in the matching `api/routes_*.py` module; keep
  `api/application.py:create_app` focused on application composition and shared state.
- Database changes belong in `database.py` plus the focused `db/*.py` storage,
  schema, or identity module; follow the access boundaries in [SAFETY INVARIANTS](../../AGENTS.md#safety-invariants).
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
