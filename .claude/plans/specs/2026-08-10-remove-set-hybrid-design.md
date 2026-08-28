# Remove SET / Hybrid Design

Date: 2026-08-10

Status: approved for implementation

Repository: `C:\projects\dj-track-similarity`

Target branch: `main`

## Objective

Physically remove the `SET` primary tab and the complete implementations of
Set Builder and Hybrid Preview. Remove their routes, schemas, source modules,
frontend state, UI, styles, tests, scripts, docs, and compatibility remnants.

Preserve the shared Current Set and the independent Evaluation subsystem. The
result must contain no active legacy path that keeps SET or Hybrid behavior
available under an alias, feature flag, deprecated endpoint, hidden component,
or compatibility response.

After the code cleanup, make one recoverable backup of the current database
bundle's writable targets and explicitly remove existing SET/Hybrid-owned data
from the current bundle. Do not add an automatic startup migration or leave a
one-off migration script in the repository.

## Product Boundary

### Remove

- The `SET` primary tab.
- The nested `Set Builder` surface.
- The nested `Hybrid Preview` surface.
- Set generation, ordering, SET preview, and bulk `Add preview` behavior.
- Hybrid weighted-preview UI, API, ranking, explanations, transition
  aggregation, feedback UI, and session recording integration.
- Capability claims, help text, examples, and navigation for these workflows.

### Preserve

- The shared Current Set state and panel.
- Individual Add/Remove operations from remaining search/library surfaces.
- The shared Audio Preview player and `/media/{track_id}` route.
- M3U/CSV export and Rhythm Lab collection transfer.
- SONARA, MERT, MAEST, MuQ, and CLAP analysis/search capabilities outside the
  removed workflows.
- Classifier scoring and classifier diagnostics.
- Evaluation API, CLI, metrics, candidate pools, source profiles, score
  profiles, calibration, ablation, risk sweep, feedback storage, and optional
  sidecar persistence.
- `transition_diagnostics.py`, because full transition-risk calculation remains
  a direct dependency of Evaluation weighted candidates and risk sweep.
- `pair_feedback` and `transition_feedback` as generic Evaluation data models.

## Implementation Shape

### Backend files to delete

- `src/dj_track_similarity/set_builder.py`
- `src/dj_track_similarity/set_sequence.py`
- `src/dj_track_similarity/api_routes_set_builder.py`
- `src/dj_track_similarity/hybrid_search.py`
- `src/dj_track_similarity/hybrid_transition.py`
- `src/dj_track_similarity/hybrid_explanation.py`

### Mixed backend files to edit

- Remove Set Builder route registration from `src/dj_track_similarity/api.py`.
- Remove the Hybrid endpoint and imports from
  `src/dj_track_similarity/api_routes_search.py`.
- Remove SET/Hybrid request and response schemas from
  `src/dj_track_similarity/api_schemas.py`.
- Remove Hybrid benchmark branches from `scripts/benchmark_search.py`.
- Remove active Hybrid branding from generic Evaluation defaults and messages.
  New defaults use neutral weighted-candidate terminology. Do not add aliases
  for the old names.

Evaluation modules and their API/CLI registrations remain. Mixed files must be
edited surgically rather than deleted wholesale.

### Frontend

Remove from the maintained React source:

- the `SET` primary-tab definition and nested-tab behavior;
- Set Builder controls, response state, request provenance, abort guards, and
  bulk `Add preview` callback;
- Hybrid controls, result/detail UI, diagnostics, feedback controls, request
  provenance, and abort guards;
- SET/Hybrid API request/response types and client methods;
- SET/Hybrid payload builders, defaults, reset helpers, and source files;
- SET/Hybrid CSS selectors and responsive rules;
- SET/Hybrid help text and keyboard/layout assumptions.

Preserve the generic track row, media player, Current Set, library identity
deduplication, individual Add/Remove operations, and export controls.

### Tests

Physically delete backend and frontend test files whose complete purpose is Set
Builder or Hybrid Preview. Remove SET/Hybrid-only cases and fixtures from mixed
test files. Update shared API, layout, help, and button-contract tests to the
new surface.

Retain Evaluation, transition-diagnostics, classifier, Current Set, Audio
Preview, export, and remaining search tests. Do not keep tests whose only
purpose is to preserve a removed API shape, field, ordering, alias, or error.

### Documentation

Delete dedicated Set Builder pages and their Russian mirrors. Remove their
VitePress navigation entries. Remove SET/Hybrid claims and instructions from
README and mixed maintained pages while preserving documentation for Current
Set, Audio Preview, export, Evaluation, and the remaining search tabs.

The local snapshot under `.ideas` is intentionally preserved and excluded from
legacy-code sentinel searches.

## API and Compatibility Policy

The following routes cease to exist:

- `POST /api/set-builder/generate`
- `POST /api/search/hybrid`

A request to either path receives the normal framework `404`. Do not add `410`
responses, redirects, route aliases, deprecated handlers, compatibility types,
feature flags, or hidden imports.

The frontend must contain no code capable of constructing either request.
Evaluation routes under `/api/evaluation/*` remain available.

## Evaluation Boundary

Evaluation remains a local diagnostics subsystem rather than a user-facing SET
surface. It continues to support:

- blind and weighted candidate export;
- seed sampling;
- pair and transition feedback import/storage;
- ranking reports and metrics;
- source ablation and source profiling;
- calibration and score-profile optimization/application;
- transition-risk penalty sweeps;
- explicit API and CLI execution.

The main frontend will have no Evaluation calls after Hybrid UI removal. That
does not make the backend/CLI subsystem obsolete. Classifier diagnostics may
continue reading generic pair feedback and Evaluation row counts.

Generic Evaluation code must not retain active Hybrid-specific defaults. For
example, a default profile name such as `hybrid_judged_v1` is changed to a
neutral weighted-candidate name. Existing persisted values are handled by the
one-time data cleanup below, not by compatibility code.

## One-Time Current-Database Cleanup

### Scope

Operate only on the current `volumes` bundle under
`C:\projects\dj-track-similarity\database` after the code cleanup is verified.
At design time the bundle contains:

- `volumes.sqlite` (Core);
- `volumes.artifacts.sqlite` (Artifacts);
- no `volumes.evaluation.sqlite` sidecar.

The apply step must repeat this inventory immediately before backup and must
stop if the resolved targets leave the named database directory or if the
bundle identity is inconsistent.

### One backup set

Create one timestamped pre-cleanup backup set under the database directory's
dedicated backup area. Use SQLite's consistent backup mechanism for every
database file that will be modified:

- back up `volumes.sqlite`;
- back up `volumes.evaluation.sqlite` only if it exists at apply time;
- do not copy or modify `volumes.artifacts.sqlite`, because the cleanup has no
  Artifacts targets.

Record backup paths, sizes, and SHA-256 digests. Do not create a second backup
for the same apply run.

### Deletion predicates

Use explicit field-level predicates, reviewed against the current schema and
payload shapes. Do not use an unbounded substring deletion across all settings
or reports.

Core targets:

- `pair_feedback` rows whose `source` is exactly `hybrid_ui`;
- promoted/settings payloads whose validated profile identity is explicitly a
  removed Hybrid profile.

Evaluation sidecar targets, when the sidecar exists:

- `search_sessions` whose mode is exactly `hybrid_search_preview`; rely on
  declared foreign-key cascade for their seeds and result events, then verify
  the result;
- calibration rows whose structured profile/search identity is explicitly a
  removed Hybrid identity;
- Evaluation settings whose key or validated structured identity explicitly
  belongs to the removed Hybrid workflow.

Do not delete generic `pair_feedback`, any `transition_feedback`, generic
candidate-pool sessions, weighted-candidate sessions, source profiles,
calibration records, or Evaluation settings.

Set Builder has no persisted database write path, so it has no separate rows to
delete.

At design time the read-only inventory reported zero total pair feedback, zero
`hybrid_ui` feedback, zero transition feedback, zero Hybrid-named Core settings,
and no Evaluation sidecar. The apply step still executes the bounded cleanup in
a transaction; a zero-row result is a verified no-op, not an assumed result.

### Transaction and failure behavior

- Re-run target counts before mutation and record them.
- Enable foreign-key enforcement and use an explicit transaction per database.
- Roll back on any statement or verification failure.
- Do not touch audio, model files, reports, or Artifacts data.
- If post-commit verification reveals corruption or a target mismatch, stop
  and restore the affected database from the single backup set before any retry.
- Do not add this cleanup to normal application startup.
- Do not leave a repository migration helper whose only purpose is this removed
  workflow.

### Database verification

After apply, verify and report:

- `PRAGMA integrity_check` is `ok` for every modified database;
- `PRAGMA foreign_key_check` returns no rows;
- every exact SET/Hybrid target count is zero;
- preserved Evaluation category counts match the pre-apply values;
- core library track/tag/analysis counts match the pre-apply values;
- the Artifacts database path, size, modification time, and digest are
  unchanged;
- the backup files exist and their recorded digests still match.

## Verification Strategy

This is a broad, cross-module removal. Run deliberately broad checks after
focused failures are resolved:

1. Inspect `git diff --name-status`, deletion counts, and the full scoped diff.
2. Search the repository for removed filenames, symbols, route paths, UI text,
   CSS selectors, types, imports, tests, fixtures, docs, and compatibility
   markers. Exclude `.git`, dependencies/build output, and `.ideas`.
3. Run the root backend pytest suite with the project virtual environment.
4. Run script tests for the touched benchmark surface.
5. Run full Ruff checking without unrelated mass formatting.
6. Run frontend `npm test` and `npm run typecheck`.
7. Run the maintained VitePress `npm run check`.
8. Run direct CLI help smoke tests for the main CLI and retained `eval` group.
9. Run `git diff --check`.
10. Verify the one-time database cleanup and backup using the checks above.
11. Confirm the final Git status and enumerate every physical deletion.

No generated frontend bundle rebuild is required unless a focused verification
failure demonstrates that the maintained static bundle is in scope.

## Acceptance Criteria

- No primary `SET` tab is present.
- No Set Builder or Hybrid Preview implementation remains.
- No SET/Hybrid route, schema, API client, payload builder, state, CSS, help,
  test, fixture, dedicated doc, benchmark path, compatibility alias, or hidden
  feature flag remains.
- All feature-owned files are physically deleted.
- Current Set, Audio Preview, remaining search tabs, export, and Rhythm Lab
  collection transfer remain operational.
- Evaluation API/CLI and transition diagnostics remain operational under
  neutral, non-Hybrid active defaults.
- The current database bundle has one verified backup set and zero bounded
  SET/Hybrid-owned rows after the one-time cleanup.
- Core library data, Artifacts data, audio, models, reports, and `.ideas` remain
  untouched except for the explicitly authorized bounded Core/Evaluation
  deletions and backup creation.
- All required verification commands pass, or any remaining baseline failure is
  identified with direct evidence and separated from this change.

## Out of Scope

- Removing Current Set or renaming it.
- Removing Audio Preview.
- Removing Evaluation as a subsystem.
- Removing generic transition diagnostics or transition feedback.
- Redesigning remaining search algorithms or classifier architecture.
- Rebuilding model outputs or scanning/reanalyzing the music library.
- Modifying or deleting source audio.
- Adding automatic database migrations or compatibility layers.
