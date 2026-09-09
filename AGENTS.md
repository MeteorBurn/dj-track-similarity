# Project instructions

This is the single instruction entry point for `dj-track-similarity`. Do not add
nested `AGENTS.md` files unless the user explicitly asks for a new instruction
boundary. Keep this file current by replacing obsolete guidance rather than
layering rules. Detailed task guides live in `docs/agent-guides/`; read them only
when the matching task needs them.

## OVERVIEW

Local-first DJ-library workbench with a Python/FastAPI backend, SQLite, React/Vite,
and VitePress. Model outputs are ranking evidence, never objective DJ decisions.

## TASK-BASED READING

Apply the global rules below to every task. Before the matching work, read the
relevant guide(s). Combine routes when a task crosses boundaries; do not read all
guides or the entire README at session start. Reuse already-read, unchanged
guidance. If a required guide is unavailable, report it and keep the dependent
work unverified rather than inventing its instructions.

| Task                                                                                                     | Read before acting                                                                                           |
| -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Run project commands; change environment, dependencies, audio runtime or server launch                   | [Environment and commands](docs/agent-guides/environment.md)                                                 |
| Locate unfamiliar code; edit source structure, shared contracts or workspace artifacts                   | [Architecture and routing](docs/agent-guides/architecture.md)                                                |
| Edit or review models, inference, jobs, caches, search/ranking, classifier signals or their UI contracts | [Model layer](docs/agent-guides/model-layer.md)                                                              |
| Inspect, validate, query or maintain real SQLite data                                                    | [SQLite Toolkit](docs/agent-guides/sqlite-toolkit.md)                                                        |
| Select implementation checks; change tests, runners, dependencies or persistence                         | [Verification](docs/agent-guides/verification.md)                                                            |
| Edit agents, skills, plugins, hooks or generated launchers; delegate project roles                       | [Agent layer](docs/agent-guides/agent-layer.md)                                                              |
| Research external facts, APIs, upstream behavior or model literature                                     | [Web research](docs/agent-guides/web-research.md)                                                            |
| Broad source discovery or Graphify navigation                                                            | [Graphify](docs/agent-guides/graphify.md)                                                                    |
| UI layout, components, interaction or styling                                                            | [DESIGN.md](DESIGN.md); use existing tokens, no raw component colors; non-submit buttons use `type="button"` |
| Need product/setup orientation                                                                           | Relevant sections of [README.md](README.md)                                                                  |

## EXECUTION AND SCOPE

- Work from the repository root in PowerShell 7. Use the verified root `uv`
  `.venv`, never an unverified system Python. Read the environment guide before
  project commands; do not sync, upgrade or recreate environments for inspection.
- Source text uses LF, `.cmd`/`.bat` use CRLF; new text is UTF-8 without BOM.
  Follow `.gitattributes` and preserve unrelated formatting.
- `database/`, `logs/`, and `reports/` are local user state, never test fixtures.
  `frontend/dist/` and `graphify-out/` are generated; do not hand-edit them.
- `.djts/` is the tracked agent/plugin source. `.workspace/` is local ignored
  working output, never an agent/skill source. Inspect the live tree before
  reusing old artifact paths; do not recreate deleted artifacts or cleanup
  archives unless requested.
- Delegate work across project ownership boundaries and integrate one answer,
  subject to the active harness's delegation rules. Use the agent-layer guide
  for roles, bounded assignments, relevant instructions, and dirty-state context.
- Identify an explicitly named or already confirmed database before access.
  Never infer the active library from launcher defaults, filenames, timestamps,
  or a previous session. Ask only if the target remains unknown.
- State the model layer before changing shared model/search files. Keep family
  evidence separate and production logic in its owning layer; a request for one
  layer does not authorize extending another. Do not expand, redesign or remove
  Model Listening Lab without a new request.
- Start project servers only through `run_server.cmd` in a visible interactive
  window, after checking existing listeners/processes and the selected database.
  Do not launch hidden direct `dj-sim`, Uvicorn or Vite processes.

## Strict Simplicity & Anti-Bloat Guidelines

- **Zero Overengineering**: Implement the simplest working solution that meets the requirements. Do not introduce speculative abstractions, design patterns (factories, strategies, adapters), or generic wrappers unless explicitly requested or reused across 3+ distinct call sites.
- **YAGNI (You Aren't Gonna Need It)**: Do not write code, hooks, or configuration toggles for hypothetical future features.
- **Minimal Diffs**: Keep changes surgical and concise. Avoid unnecessary refactoring of adjacent code or cosmetic reformatting that inflates the PR size.
- **No Dependency Bloat**: Prefer the standard library and existing dependencies. Do not add external packages or tools without explicit prior confirmation.
- **Dead Code Cleanup**: When modifying an existing pipeline or endpoint, delete deprecated helpers and unreachable branches rather than leaving comments or fallback shims.

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
  requested. As of 2026-09-08, `dev` is the primary working branch until the
  user decides otherwise. For authorized Git delivery, use `dev`: fetch before
  committing, compare ancestry with `origin/dev`, and account for parallel
  worktrees. New branches start from `origin/dev` (default prefix `codex/`).
  Update `main` only on a separate explicit user request.
- Inspect `git status` and the scoped diff before delivery. Do not stage local
  databases, audio, logs, reports, model artifacts, or generated output.
- Executable sources and tests beat prose when they disagree.

## SAFETY INVARIANTS

- Treat source audio as user data. Scan, preview, analysis, search, reset,
  relocation preview, export, classifier scoring, and routine verification
  must not modify it.
- Normal tag writing is explicit and genre-only. Browser preview transcoding
  uses temporary output and must not rewrite or cache the source audio.
- Use `LibraryDatabase` for the main application's library reads and writes;
  explicit read-only inspection follows [SQLITE TOOLKIT](docs/agent-guides/sqlite-toolkit.md#sqlite-toolkit). Preserve WAL,
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

## DOCUMENTATION WORKFLOW

- Update documentation only when requested in the current session. A code
  change does not authorize a docs pass; do not plan/delegate one, report a gap,
  or offer to close it. Instruction-file maintenance does not imply a docs-site
  update.
- For requested product/developer documentation, delegate to
  `documentation-expert` (structure, audits, tooling) or `technical-writer`
  (reader-facing pages) per the agent-layer guide; scope, source ownership and
  verification come from this file and executable code. Read `README.md` for
  setup orientation when needed; verify current behavior against executable
  source and tests. Maintained docs can lag the code.
- Document current behavior, not plans. Docs do not block implementation,
  verification, or authorized Git delivery.
- Documentation is English. Translate Russian UI labels in prose; only
  `docs/dj-track-similarity/help/ui-language.md` may contain Cyrillic to map
  on-screen labels to English.
  `npm --prefix .\docs\dj-track-similarity run lint:language` enforces this.

## DELIVERY

- Instruction-only edits need a scoped diff, whitespace and relevant path/command
  checks, not application tests or a docs-site build. These task guides belong to
  instruction maintenance; changing them does not authorize product-docs work.
- For implementation work, follow the verification guide. Use the smallest
  meaningful check; broaden only to resolve concrete affected contracts or risk.
  Reuse checks that still cover the final state; do not rerun only for delivery.
- Report checks actually run and blocked verification. Do not imply source
  inspection proves live behavior or claim CI ran without execution evidence.
