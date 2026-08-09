# Agent Instructions

This is the single project instruction file for `dj-track-similarity`.
Do not add nested `AGENTS.md` files for local notes unless the user explicitly
asks for a new instruction boundary. Keep this file short, current, and useful;
remove obsolete guidance instead of layering more rules on top of it.

## Operating Model

- The project is under active development. File layout, schemas, API shapes,
  field order, model sets, weights, defaults, commands, ports, and UI structure
  describe the current checkout, not permanent contracts.
- Treat the requested target behavior as the new source of truth. Update
  affected source, types, migrations, tests, and docs together when they really
  change.
- Do not preserve incidental structure with compatibility aliases, duplicated
  registries, version gates, hidden legacy branches, or tests that freeze field
  order. Prefer one discoverable source of truth and tests of observable
  behavior.
- Add backward compatibility or migrations only for real persisted data,
  external consumers, or an explicit user request.
- Keep work scoped. Preserve unrelated user changes. Do not create broad plans,
  specs, test profiles, or infrastructure unless they directly reduce current
  risk or complexity.

## Source Of Truth

- `dj-track-similarity` is a local-first DJ-library workbench. Keep claims
  modest: model outputs are ranking signals for listening-led shortlisting, not
  objective truth or finished automatic DJ generation.
- Executable sources beat prose when they disagree: `pyproject.toml`,
  `frontend/package.json`, `docs/dj-track-similarity/package.json`, tests,
  schemas, routes, and current source are authoritative.
- The maintained docs surface is `README.md` plus `docs/dj-track-similarity/`;
  English is primary and Russian mirrors live under
  `docs/dj-track-similarity/ru/`.
- Project databases live under `C:\projects\dj-track-similarity\database`.
  Never use a real project database in automated tests.

## Safety Baseline

These rules apply unless the user explicitly asks to redesign that workflow. A
redesign must state the new risk model, confirmation/recovery behavior, and
direct verification.

- Treat source audio as user data. Scan, tag refresh preview, analysis, search,
  preview, reset, relocation preview, export, graph export, classifier scoring,
  and routine verification must not modify audio files.
- The normal tag-write workflow is explicit and genre-only. It preserves
  existing normal tags. Do not add incidental audio writes.
- Browser preview may transcode AIFF to temporary WAV for streaming but must
  not rewrite or cache source audio.
- SQLite writes go through `LibraryDatabase` and the active locking/WAL/busy
  timeout policy or an explicitly verified replacement. Destructive maintenance
  on a real DB requires backup/copy first plus integrity/orphan checks.
- Startup must not silently mutate older database structures. Explicit
  migration workflows must be intentional, recoverable, and verified.
- The Windows launcher should preserve safe list-based argument forwarding with
  `shell=False` unless it is deliberately redesigned with equivalent injection
  protection.
- Audio Doctor is dry-run-first. Apply is limited to prior repairable findings,
  uses explicit confirmation, creates backups by default, verifies results, and
  restores on verification failure.
- Audio Dedup is report-first. Apply requires explicit confirmation, deletes
  only qualified targets inside the selected root, and removes DB rows only for
  files actually deleted. Never run apply mode for routine verification.
- KGLite Bridge treats project SQLite databases and source audio as read-only
  inputs. Open SQLite inputs read-only/query-only, do not write/checkpoint/vacuum
  them, and refuse output paths that resolve to input databases.
- Rhythm Lab keeps its labels, predictions, queues, checkpoints, and artifacts
  separate from the source database. Its only narrow source-DB write path is
  the explicit liked-track toggle. Promotion must keep runtime model/manifest
  reads atomic.
- Promoted classifier scoring is database-only, scoped by classifier key, and
  writes only that classifier's scores.
- Keep CLAP text-search scores separate from audio-to-audio CLAP signals used
  by SET, Hybrid, Audio Dedup, and classifiers. Do not substitute MuQ, MERT,
  MAEST, CLAP, or SONARA evidence for another family.

## Connected SONARA Repository

This project consumes SONARA from `C:\projects\sonara`.

Before SONARA work:

1. Read `C:\projects\sonara\AGENTS.md`.
2. Inspect Git status in both repositories.
3. Keep Git commands scoped to the intended repository.

By default, SONARA audits are fetch/inspection only. Build release wheels
outside both checkouts and smoke-test wheels in an isolated environment.

## Development Workflow

- Work directly on `main` for this project unless the user asks for another
  branch/worktree.
- Preserve unrelated dirty work. This repository may be dirty.
- Do not stage generated or local state unless the user explicitly requests
  it. Respect ignore rules and inspect exact staged paths before delivery.

## Verification Routing

Use the cheapest check that can actually catch a mistake in the touched scope.
Do not run full backend, frontend, docs, tool, or repository suites merely as a
precaution.

- **Instruction/docs-only:** inspect the scoped diff, run
  `git diff --check -- <paths>`, and use targeted `rg` sentinels for required
  safety/process wording. Do not run application tests.
- **Backend/source change:** run the focused pytest file or test selection that
  covers the touched path. Widen only when shared behavior or a focused failure
  justifies it.
- **Model/audio/database tests:** use temporary SQLite/WAV fixtures and stubs;
  do not call real SONARA, CLAP, MERT, MuQ, MAEST, or the user's music library.
- **Frontend change:** run `npm run typecheck`; add `npm test` or
  `npm run build` only when the touched UI/build path warrants it.
- **Docs site change:** from `docs/dj-track-similarity/`, run `npm run check`
  only for maintained docs-site content or docs tooling changes.
- **Real DB maintenance:** use backups/copies, integrity checks, row-count or
  semantic comparisons, and disposable benchmark clones when performance claims
  matter.
- **Release, broad refactor, migration, cross-module API/schema change, or
  explicit user request:** broaden verification deliberately and report why.
