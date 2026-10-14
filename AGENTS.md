# Project instructions

This is the single instruction entry point for `dj-track-similarity`. Do not add
nested `AGENTS.md` files unless the user explicitly asks for a new instruction
boundary. Apply the global instructions; this file adds project constraints.
Replace obsolete guidance instead of layering rules. Read detailed guides in
`docs/agent-guides/` only for the matching task.

## OVERVIEW

Local-first DJ-library workbench with a Python/FastAPI backend, SQLite, React/Vite,
and VitePress. Model outputs are ranking evidence, never objective DJ decisions.

## TASK-BASED READING

Apply the project-wide rules below to every task. Before the matching work, read the
relevant guide(s). Combine routes when a task crosses boundaries; do not read all
guides or the entire README at session start. Reuse already-read, unchanged
guidance. If a required guide is unavailable, continue independent work, but do
not perform changes whose constraints depend on it. Report the missing path as
the blocker.

| Task | Read before acting |
|---|---|
| Run application commands; change environment, dependencies, audio runtime/tools or server launch | [Environment and commands](docs/agent-guides/environment.md) |
| Locate unfamiliar code; edit source structure, shared contracts or workspace artifacts | [Architecture and routing](docs/agent-guides/architecture.md) |
| Run, edit or review models, inference, jobs, caches, output storage/readiness, search/ranking or classifier/UI contracts | [Model layer](docs/agent-guides/model-layer.md) |
| Access real SQLite data; change persistence, stored identities, database switching, migrations or deferred writes | [SQLite Toolkit and persistence](docs/agent-guides/sqlite-toolkit.md) |
| Select checks; add, change or delete tests; change runners, dependencies or persistence | [Verification and test policy](docs/agent-guides/verification.md) |
| Edit instructions, agents, skills, plugins, hooks or launchers; delegate roles; prepare requested documentation | [Agent layer](docs/agent-guides/agent-layer.md) |
| Research external facts, APIs, upstream behavior or model literature | [Web research](docs/agent-guides/web-research.md) |
| Explore or change repository code; Graphify navigation | [Graphify](docs/agent-guides/graphify.md) |
| UI layout, components, interaction or styling | [DESIGN.md](DESIGN.md); use existing tokens, no raw component colors; non-submit buttons use `type="button"` |
| Need product/setup orientation | Relevant sections of [README.md](README.md) |

## EXECUTION AND SCOPE

- Apply global scope and authorization rules to bug reports and UI
  contradictions. Repeated reports require renewed checking, not a restated
  explanation; keep delegated work within the same scope.
- Use Graphify first for source discovery as required by the Graphify guide,
  then use the available LSP for the file's language to resolve definitions and
  references when working with symbols. Before renaming a symbol, inspect its
  references and use LSP rename preparation when supported; review all resulting
  edits. After code changes, run LSP diagnostics on the affected files. For
  Python, also run the shared `C:\Utils\tools\ruff\ruff.exe` with the project's
  configuration and verification scope; do not install a project-local Ruff.
  If LSP is unavailable or lacks the needed capability, report the concrete
  limitation and continue with source inspection and the applicable checks.
  Simple prose or cosmetic edits do not require extra LSP checks.
- Work from the repository root using the verified root `uv` `.venv`.
  The environment guide owns installation via `.\install.ps1`, the locked
  SONARA/CUDA sources and inspection without environment changes. Audio uses
  shared FFmpeg libraries only, never `ffmpeg.exe` or `ffprobe.exe`.
- Follow `.gitattributes`: source text uses LF, `.cmd`/`.bat` use CRLF;
  new text is UTF-8 without BOM.
- `database/`, `logs/`, and `reports/` are local user state, never test fixtures.
  `frontend/dist/` and `graphify-out/` are generated; do not hand-edit them.
- `.djts/` is the tracked agent/plugin source. `.workspace/` is local ignored
  working output, never an agent/skill source. Inspect the live tree before
  reusing old artifact paths; do not recreate deleted artifacts or cleanup
  archives unless requested.
- Delegate substantial work across project ownership boundaries or an independent
  review when useful; keep small local changes with the current agent. Follow
  the agent-layer guide and active harness rules, and integrate one answer.
- Globally installed skills do not override this file. External design and
  output-style skills (`impeccable`, `design-taste-frontend`,
  `high-end-visual-design`, `minimalist-ui`, `full-output-enforcement`, and
  similar) are inactive here: `DESIGN.md` and `design-system-engineer` own UI
  decisions, and this file owns diff scope and output length. Invoke one only
  on explicit request, and keep its result subject to these rules.
- Development/server default: `database/Volumes.sqlite` relative to the root,
  unless another database is explicitly specified. Pass it explicitly and do
  not ask for confirmation again; tool defaults differ (see environment guide).
  For other database access, identify an explicitly named or already confirmed
  database. Never infer the active library from launcher defaults, filenames,
  timestamps, or a previous session. Ask only if the target remains unknown.
- State the model layer before changing shared model/search files. Keep family
  evidence separate and production logic in its owning layer; a request for one
  layer does not authorize extending another. The DJ SET tab lists its built
  set only as rows of the shared result list (`results-list`), in the order
  the builder returned, and tracks join the current set only through the
  existing "+" controls: do not add replace/save buttons, reordering or other
  set management to it without a new request.
- SONARA and ML never share a run. Preserve SONARA's atomic four-output writes
  and BPM lock, and ML's current-SONARA prerequisite; the model-layer guide owns
  run, readiness and REFERENCE-map contracts.
- Start servers through the launchers in visible interactive windows after
  checking existing processes/listeners and the selected database. Follow the
  environment guide for `run_server.cmd` and managed/standalone Rhythm Lab;
  never start direct `dj-sim`, Uvicorn, Vite or `rhythm_lab_cli.py serve` servers.

## Strict Simplicity & Anti-Bloat Guidelines

- **Zero Overengineering**: Implement the simplest working solution that meets the requirements. Do not introduce speculative abstractions, design patterns (factories, strategies, adapters), or generic wrappers unless explicitly requested or reused across 3+ distinct call sites.
- Do not add code, hooks or configuration toggles for hypothetical future features.
- **No Dependency Bloat**: Prefer the standard library and existing dependencies. Do not add external packages or tools without explicit prior confirmation.
- **Dead Code Cleanup**: Remove helpers and branches made unreachable or obsolete by the requested change, after checking callers and persisted or external contracts. Do not expand the task into adjacent cleanup.

## OPERATING MODEL

- The checkout is under active development. Current schemas, model sets,
  weights, defaults, commands, ports, and UI structure are not permanent APIs.
- Treat requested behavior as the new source of truth. Add compatibility or
  migrations only for persisted data, external consumers, or explicit requests.
- Prefer one discoverable source of truth. Do not add aliases, duplicate
  registries, version gates, version labels, or hidden legacy branches. Nothing
  is a fixed passport yet: model, adapter and preprocessing identities carry no
  version suffix, and upstream identities (checkpoint hashes, model revisions,
  external format versions) are not ours to number. TEST POLICY governs what
  the suite is allowed to pin.
- `dev` is the primary working branch until the user decides otherwise.
  For Git delivery authorized under the global rules, use `dev`: fetch before
  committing, compare ancestry with `origin/dev`, and account for parallel
  worktrees. New branches start from `origin/dev` (default prefix `codex/`).
  Update `main` only on a separate explicit user request, using fast-forward
  after ancestry and worktree checks. Keep `dev` as the working branch.
- Do not stage local databases, audio, logs, reports, model artifacts or generated output.
- Use executable source and tests to establish current behavior. They do not
  override the user's requested behavior or these safety constraints. Treat
  discrepancies as findings to resolve within the task.

## SAFETY INVARIANTS

- Treat source audio as user data. Scan, preview, analysis, search, reset,
  relocation preview, export, classifier scoring, and routine verification
  must not modify it.
- Normal tag writing is explicit and genre-only. Browser preview decodes to a
  streamed WAV (`Cache-Control: no-store`) or, in Rhythm Lab, a temporary WAV
  file; it must not rewrite or cache the source audio.
- Use `LibraryDatabase` for the main application's library reads and writes;
  preserve WAL, the busy timeout and identity/freshness checks inside each
  `BEGIN IMMEDIATE` write transaction. The SQLite guide owns the read-only
  inspection path and Rhythm Lab's limited `SourceDatabase` exception.
  Destructive work on real databases requires a backup or disposable copy plus
  integrity and orphan checks.
- Preserve existing catalog/track UUID, missing-state and selected-database
  generation checks for deferred operations. A numeric track ID alone is not
  sufficient authority to write results after the underlying identity changes.
- Startup must not silently migrate old databases. A migration is an explicit,
  recoverable workflow run once against a named database; reanalysis remains a
  separate user choice. Remove the one-off migration module, command and tests
  in the same change after successful migration and verification of every
  database explicitly included in the requested scope. A fixture or dry-run
  execution does not satisfy this condition. Do not retain migrations for
  source layouts no longer on disk; write a new one for a future schema change.
- Package, loader and lifetime refactors preserve existing schema, saved rows,
  model/output identities, vector formats and analysis readiness. They must not
  introduce data rewrites or requirements to reanalyze, rescore or retrain merely
  because source paths or in-memory ownership changed.
- Preserve Rhythm Lab's fingerprint-based identities and SONARA-supplied
  fingerprint version; the SQLite guide owns the format and mismatch rules.
- Keep launcher subprocess arguments list-based with `shell=False`. Local mode
  binds `127.0.0.1`; LAN exposure must be explicit.
- Audio Doctor is dry-run by default; Audio Dedup is report-first, with explicit
  deletion authorization and at least one disk copy retained per group. Read
  their full safety contracts in the environment guide. Never run apply modes for QA.
- Classifier scoring is database-only, scoped by classifier key, and must
  validate promoted manifest feature order and artifact hashes.
- Automated model/audio/database tests use temporary SQLite/WAV fixtures and
  stubs, never real project databases, music files, or downloaded model runs.
  Manual measurements and probes read audio only from
  tracks of the selected library (located through the database, read-only),
  the test corpus `C:/projects/tracks`, or generated signals in a temp
  directory; never browse or open other folders, such as parts of the music
  drive that are not in the database. Agents never load models on the GPU while
  an owner's analysis job runs; check `nvidia-smi` and use `device=cpu`.

## TEST POLICY

Read [Test policy](docs/agent-guides/verification.md#test-policy) before adding,
changing or deleting tests. It overrides automatic TDD requirements: protect
distinct durable behaviors or failure modes, prove new/extended tests fail
without the protected behavior, and never cut useful coverage to hold a count.

## DOCUMENTATION WORKFLOW

- The docs site (`docs/dj-track-similarity/`) is paused since 2026-09-15. Do not
  edit, audit or delegate work on it, even on explicit request, until the user
  says to resume; report the pause. It never establishes current behavior:
  use executable source and tests. Maintained instructions are this file,
  `README.md` and `docs/agent-guides/`.
- Update documentation only when requested in the current session. A code
  change does not authorize a docs pass; do not plan/delegate one, report a gap,
  or offer to close it. Instruction-file maintenance does not imply a docs-site
  update.
- Requested documentation follows the agent-layer guide's ownership, README
  format and English-language rules; the verification guide selects checks.

## DELIVERY

- Inspect `git status` and the scoped diff before delivery.
- Select checks using [Verification](docs/agent-guides/verification.md);
  TEST POLICY above governs test changes. Follow the global completion and
  reporting rules; source inspection is not live verification or a CI run.
