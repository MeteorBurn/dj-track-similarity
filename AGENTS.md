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
| Explore or change repository code; Graphify navigation                                                   | [Graphify](docs/agent-guides/graphify.md)                                                                    |
| UI layout, components, interaction or styling                                                            | [DESIGN.md](DESIGN.md); use existing tokens, no raw component colors; non-submit buttons use `type="button"` |
| Need product/setup orientation                                                                           | Relevant sections of [README.md](README.md)                                                                  |

## EXECUTION AND SCOPE

- Work from the repository root in PowerShell 7. Use the verified root `uv`
  `.venv`, never an unverified system Python. Read the environment guide before
  project commands; do not sync, upgrade or recreate environments for inspection.
- For requested full installation, use `.\install.ps1`. It prepares the shared
  environment, frontend, audio runtime and pinned model assets. All Python
  dependencies are required by the root `pyproject.toml`; preserve the locked
  SONARA fork and CUDA package sources. See the environment guide for details.
- scikit-learn is a required project-wide dependency managed in the root
  `pyproject.toml`. Prefer its existing tools for feature analysis, clustering,
  evaluation and classical ML when they fit the task.
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
- Globally installed skills do not override this file. External design and
  output-style skills (`impeccable`, `design-taste-frontend`,
  `high-end-visual-design`, `minimalist-ui`, `full-output-enforcement`, and
  similar) are inactive here: `DESIGN.md` and `design-system-engineer` own UI
  decisions, and this file owns diff scope and output length. Invoke one only
  on explicit request, and keep its result subject to these rules.
- For development and server startup, use `database/test.sqlite` relative to
  the repository root unless another database is explicitly specified.
  This is the user-confirmed default; do not ask for
  database-selection confirmation again when using it. Pass it explicitly:
  tool defaults are not the dev database (`run_server.cmd` prompt:
  `database\volumes.sqlite`; Audio Dedup `--db`: `database/volumes.sqlite`;
  Rhythm Lab CLI data-command `--source` and `collection-save --source-db`:
  `C:\db\abstracted.sqlite`; `serve --source` has no default).
  For other database access, identify an explicitly named or already confirmed
  database. Never infer the active library from launcher defaults, filenames,
  timestamps, or a previous session. Ask only if the target remains unknown.
- State the model layer before changing shared model/search files. Keep family
  evidence separate and production logic in its owning layer; a request for one
  layer does not authorize extending another. Do not expand, redesign or remove
  Model Listening Lab without a new request.
- SONARA and ML never share a run on any entry point: a pipeline job has one
  `stage` (`sonara` or `ml`), `dj-sim analyze --models` takes `sonara` alone or
  ML models only, and a job rejects the other layer's settings (SONARA BPM
  range, ML staged mode). ML refuses to start without any current SONARA track
  and skips tracks lacking it. A SONARA write needs all four outputs and stores
  them together: core, timeline, embedding, fingerprint. Readiness is a stored
  current-track row, not a payload check; payloads are validated on write
  (SONARA Core also on read), and `dj-sim validate-database` checks SONARA Core,
  embedding and fingerprint rows but not timeline rows.
  A library without the `sonara_timeline` table gets an explicit error and is
  never migrated automatically.
- Start project servers only through `run_server.cmd` in a visible interactive
  window, after checking existing listeners/processes and the selected database.
  Do not launch hidden direct `dj-sim`, Uvicorn or Vite processes. While the
  main server runs, Rhythm Lab starts only through it (its Rhythm Lab button or
  `POST /api/rhythm-lab/launch`) as a managed child in that server's window.
  Without the main server, start it with `run_rhythm-lab.cmd` in a visible
  window; the script hands off to a running main server itself. Never start
  `rhythm_lab_cli.py serve` directly.

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
  registries, version gates, version labels, or hidden legacy branches. Nothing
  is a fixed passport yet: model, adapter and preprocessing identities carry no
  version suffix, and upstream identities (checkpoint hashes, model revisions,
  external format versions) are not ours to number. TEST POLICY governs what
  the suite is allowed to pin.
- Inspect `git status --short` and the relevant existing diff before editing.
  Preserve unrelated work. Create branches, commits, or PRs and push only when
  requested. As of 2026-09-08, `dev` is the primary working branch until the
  user decides otherwise. For authorized Git delivery, use `dev`: fetch before
  committing, compare ancestry with `origin/dev`, and account for parallel
  worktrees. New branches start from `origin/dev` (default prefix `codex/`).
  Update `main` only on a separate explicit user request, using fast-forward
  after ancestry and worktree checks. Keep `dev` as the working branch.
- Inspect `git status` and the scoped diff before delivery. Do not stage local
  databases, audio, logs, reports, model artifacts, or generated output.
- Executable sources and tests beat prose when they disagree.

## SAFETY INVARIANTS

- Treat source audio as user data. Scan, preview, analysis, search, reset,
  relocation preview, export, classifier scoring, and routine verification
  must not modify it.
- Normal tag writing is explicit and genre-only. Browser preview decodes to a
  streamed WAV (`Cache-Control: no-store`) or, in Rhythm Lab, a temporary WAV
  file; it must not rewrite or cache the source audio.
- Use `LibraryDatabase` for the main application's library reads and writes;
  explicit read-only inspection follows [SQLITE TOOLKIT](docs/agent-guides/sqlite-toolkit.md#sqlite-toolkit). Preserve WAL,
  busy-timeout and per-database locking on application write connections.
  Rhythm Lab keeps its existing `SourceDatabase` boundary: query-only library
  reads, a read-only `ATTACH` that syncs `track_sightings` into the lab
  database, and the explicit liked-track toggle with its shared write-lock and
  ID/UUID checks. It switches libraries at runtime: the launcher's catalog pin
  covers only the first open, a switch is refused while a profile operation
  runs, and the main app verifies the catalog a managed lab returns after a
  switch. Its other state remains separate from the source library.
  This exception does not authorize additional direct library writes.
  Real-database destructive work requires a backup or disposable copy plus
  integrity and orphan checks.
- Preserve existing catalog/track UUID, missing-state and selected-database
  generation checks for deferred operations. A numeric track ID alone is not
  sufficient authority to write results after the underlying identity changes.
- Startup must not silently migrate old databases. A migration is an explicit,
  recoverable workflow run once against a named database; reanalysis remains a
  separate user choice. The repository does not keep migration code after the
  migration has been performed: delete the module, its command and its tests in
  the same change, and do not maintain them for a source layout no longer on
  disk. Write a new one if a future schema change needs it.
- Package, loader and lifetime refactors preserve existing schema, saved rows,
  model/output identities, vector formats and analysis readiness. They must not
  introduce data rewrites or requirements to reanalyze, rescore or retrain merely
  because source paths or in-memory ownership changed.
- Rhythm Lab labels, predictions, the label queue and review collections are
  keyed by `content_key` = `"sfp<version>:" + sha256("sfp:<version>:" +
  SONARA fingerprint bytes)`, so fingerprint bytes and version are preserved
  identities. SONARA supplies `fingerprint_version`; the project never assigns
  it. A library whose version differs from the stored sightings is refused
  rather than synced, and re-keying labels onto a new version is not
  implemented. A pre-content-identity lab database is rejected on open.
- Keep launcher subprocess arguments list-based with `shell=False`. Local mode
  binds `127.0.0.1`; LAN exposure must be explicit.
- Audio Doctor is dry-run unless `--apply`; there is no interactive prompt.
  Apply makes a full-file backup, verifies the written file and restores the
  backup on failure; it deletes the backup after a verified write or a
  successful restore (a failed restore keeps it). `--no-backup` (rejected with
  `--backup-dir` under `--apply`) drops both backup and rollback. Audio Dedup
  finds duplicates from stored SONARA fingerprints alone; a fingerprint match is
  evidence, never authorization. It is report-first: deletion needs
  `APPLY DELETE`, stays inside the report root, rechecks track identity and file
  facts, and keeps at least one copy on disk per group. Its CLI is report-only;
  the browser deletes reviewer-selected copies (any group member, recycle bin by
  default). Never run apply modes for QA.
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
a test by existing, and a growing test count is a defect, not progress. This
overrides the rule of TDD skills that every feature, fix, refactor or behavior
change starts with a new test: admit a test only under the rules below.

- Add a test only for something durable: a persisted schema, migration, or
  on-disk format; an HTTP payload, CLI contract, or other cross-boundary shape;
  a scoring, ranking, or safety invariant; or a reproduced bug whose cause is
  understood, asserted at the cause rather than the symptom.
- A new or extended test must fail without what it protects. Before keeping it,
  revert the fix or break that behavior in a disposable copy, watch the test go
  red, and report that run. A test that stays green protects nothing.
- Add no test for cosmetics, labels, copy, tooltips, colors, class names, the
  order of fields, rows, or menu entries, or a default, threshold, or option
  that is expected to keep moving.
- Add no test for wiring that the type checker, the import graph, or an existing
  focused run already covers.
- Never assert on the text of a source file. Reading a module, script, or
  `.cmd` file and matching strings pins how the code is written instead of what
  it does. Drive the running module and assert its behavior.
  `frontend/tests/testsExecuteCode.test.mjs` fails every frontend test that
  never reaches the module it checks through a loader or a `../src/` import; it
  does not prove that assertions exercise behavior and does not replace review.
- When behavior changes, edit the existing test that owns that contract instead
  of adding a second one. Two tests over one contract mean one is redundant.
- Delete a test whose contract is gone, and delete a test that blocks an
  intentional change while pinning only an incidental detail. Removing a test is
  a normal part of a change, not a regression.

## DOCUMENTATION WORKFLOW

- The docs site (`docs/dj-track-similarity/`) is temporarily unmaintained as of
  2026-09-15. Do not edit it, audit it for staleness, or delegate a pass over
  it, even on explicit request, until the user says to resume; report that it
  is paused instead. It is never a source of truth for your own work regardless
  of pause state: verify behavior against executable source and tests, not
  against this site. The maintained instruction set is this file, `README.md`,
  and `docs/agent-guides/`.
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
- Keep `README.md` concise and UI-first, without CLI/API command recipes.
  Use emoji headings/callouts, meaningful images, and working links.
  Installation order: prerequisites/warnings; one short installation procedure;
  dependencies grouped by role, one package per line with bold name/version and
  a short purpose; Audio Features Extraction Engine (patched SONARA fork and
  original citation); models and disk sizes. Model-specific packages remain
  actual dependencies but appear in their model block, not the general list.
  Verify installer/runtime/launcher claims against executable sources.
  When the user reports GitHub edits, fetch and integrate them before updating
  README; preserve user wording outside the requested scope.
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
