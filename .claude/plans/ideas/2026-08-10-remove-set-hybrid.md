# Remove SET and Hybrid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Physically remove Set Builder and Hybrid Preview while preserving Current Set, Evaluation, shared transition diagnostics, audio preview, export, and the user's current library data.

**Architecture:** Delete feature-owned backend and frontend modules, surgically remove their registrations and mixed-file branches, and retain Evaluation as a neutral API/CLI diagnostics subsystem. After code verification, create one consistent backup set and run a bounded one-time cleanup against the current `volumes` database bundle.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLite, React, TypeScript, Vite, Vitest/Node tests, pytest, Ruff, VitePress, PowerShell 7.

## Global Constraints

- Work directly on `main`; do not push unless explicitly requested.
- Preserve the shared Current Set, individual Add/Remove, Audio Preview, M3U/CSV export, and Rhythm Lab collection transfer.
- Preserve Evaluation API/CLI, generic feedback, candidate pools, score profiles, calibration, risk sweep, sidecar storage, classifier diagnostics, and `transition_diagnostics.py`.
- Do not retain compatibility aliases, feature flags, hidden routes, `410` responses, deprecated types, or tests that freeze removed behavior.
- Do not touch source audio, models, reports, or Artifacts rows.
- Use the project virtual environment for Python checks.
- Preserve `.ideas` and the approved design/plan documents as historical artifacts; exclude them from active-legacy sentinels.
- Back up the current writable SQLite targets exactly once immediately before the one-time data cleanup.
- Do not add an automatic startup migration or leave a one-off migration helper in the repository.

---

## File Map

### Delete

- `src/dj_track_similarity/set_builder.py`
- `src/dj_track_similarity/set_sequence.py`
- `src/dj_track_similarity/api_routes_set_builder.py`
- `src/dj_track_similarity/hybrid_search.py`
- `src/dj_track_similarity/hybrid_transition.py`
- `src/dj_track_similarity/hybrid_explanation.py`
- `frontend/src/setBuilderControls.ts`
- `tests/test_set_builder.py`
- `tests/test_api_set_builder.py`
- `tests/test_hybrid_search.py`
- `tests/test_api_hybrid_search.py`
- `tests/test_set_hybrid_runtime.py`
- `tests/test_hybrid_result_contract.py`
- `tests/test_match_character.py`
- `tests/test_explanation_consistency.py`
- `frontend/tests/setBuilderControls.test.mjs`
- `frontend/tests/hybridPreviewState.test.mjs`
- `frontend/tests/feedbackPayload.test.mjs`
- `docs/dj-track-similarity/user-guide/smart-set-builder.md`
- `docs/dj-track-similarity/concepts/smart-set-builder-routing.md`
- `docs/dj-track-similarity/ru/user-guide/smart-set-builder.md`
- `docs/dj-track-similarity/ru/concepts/smart-set-builder-routing.md`

### Modify surgically

- `src/dj_track_similarity/api.py`
- `src/dj_track_similarity/api_routes_search.py`
- `src/dj_track_similarity/api_schemas.py`
- `src/dj_track_similarity/evaluation/score_profile_optimizer.py`
- `tests/test_scoring_invariants.py`
- `tests/test_break_energy.py`
- Evaluation tests that use `hybrid_search_preview`, `hybrid_ui`, or `hybrid_judged_v1` merely as generic fixtures
- `scripts/benchmark_search.py` and its tests
- `frontend/src/App.tsx`
- `frontend/src/SearchPlaylistPanel.tsx`
- `frontend/src/searchSurfaceState.ts`
- `frontend/src/api.ts`
- `frontend/src/apiClient.ts`
- `frontend/src/styles.css`
- mixed frontend tests for API contracts, layout, buttons, and help text
- `README.md`
- maintained English and Russian docs containing active SET/Hybrid claims
- `docs/dj-track-similarity/.vitepress/config.mts`

### Preserve

- `src/dj_track_similarity/transition_diagnostics.py`
- `src/dj_track_similarity/evaluation/`
- `src/dj_track_similarity/api_routes_evaluation.py`
- `src/dj_track_similarity/db_evaluation.py`
- `src/dj_track_similarity/db_evaluation_sidecar.py`
- Current Set, media preview, export, classifier, tempo/key resolution, and remaining search modules/tests

---

### Task 1: Establish the new frontend surface contract

**Files:**
- Modify: `frontend/tests/searchPlaylistLayout.test.mjs`
- Modify: `frontend/tests/apiContract.test.mjs`
- Modify: `frontend/tests/buttonClasses.test.mjs`
- Modify: `frontend/tests/helpText.test.mjs`

**Interfaces:**
- Consumes: current rendered/source contracts in `SearchPlaylistPanel.tsx`, `api.ts`, and `apiClient.ts`
- Produces: tests describing only the remaining primary tabs, API methods, controls, and help copy

- [ ] **Step 1: Replace positive SET/Hybrid expectations with the exact remaining surface**

The remaining primary search tabs must be represented by the existing non-SET values and labels only. API-contract tests must enumerate retained calls without including `/api/set-builder/generate` or `/api/search/hybrid`; do not add negative compatibility tests containing removed route strings.

- [ ] **Step 2: Run the changed frontend tests and confirm they fail against the current implementation**

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity\frontend'
node --test tests\searchPlaylistLayout.test.mjs tests\apiContract.test.mjs tests\buttonClasses.test.mjs tests\helpText.test.mjs
```

Expected: at least one updated layout/API/help assertion fails because the SET surface still exists.

- [ ] **Step 3: Record the failing assertions for use during Task 3**

Do not change production frontend code in this task.

---

### Task 2: Remove the backend workflows and routes

**Files:**
- Delete: the six backend feature modules listed in the File Map
- Delete: the eight dedicated backend feature test files listed in the File Map
- Modify: `src/dj_track_similarity/api.py`
- Modify: `src/dj_track_similarity/api_routes_search.py`
- Modify: `src/dj_track_similarity/api_schemas.py`
- Modify: `tests/test_scoring_invariants.py`
- Modify: `tests/test_break_energy.py`

**Interfaces:**
- Consumes: FastAPI route registration and shared schemas
- Produces: an application with no SET/Hybrid import path or endpoint while retaining all Evaluation routes

- [ ] **Step 1: Delete feature-owned backend modules and dedicated tests with one explicit patch**

Use `apply_patch` delete operations. Do not use recursive filesystem deletion.

- [ ] **Step 2: Remove route registrations, imports, and schemas**

Remove `register_set_builder_routes`, `build_hybrid_search_preview`, the Hybrid endpoint block, and all Set Builder/Hybrid Pydantic models and type aliases. Do not add replacement handlers.

- [ ] **Step 3: Remove feature-only cases from mixed backend tests**

Retain generic Evaluation, transition diagnostics, scoring invariants, energy-break, database, and API tests. Remove only cases whose subject is SET/Hybrid behavior.

- [ ] **Step 4: Verify no Python import references a deleted module**

```powershell
rg -n -g '*.py' 'api_routes_set_builder|set_builder|set_sequence|hybrid_search|hybrid_transition|hybrid_explanation|SetBuilder|HybridSearch' src tests scripts
```

Expected: no active implementation/test import; remaining matches must be reviewed and removed unless they are neutral Evaluation fixtures scheduled for Task 4.

- [ ] **Step 5: Run focused backend API/import tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_api_route_modules.py tests\test_api_evaluation.py tests\test_transition_diagnostics.py -q
```

- [ ] **Step 6: Commit the backend removal**

```powershell
git add -u -- src tests scripts
git diff --cached --check
git commit -m "refactor: remove SET and Hybrid backend"
```

---

### Task 3: Remove the frontend workflows while preserving Current Set

**Files:**
- Delete: `frontend/src/setBuilderControls.ts`
- Delete: dedicated frontend feature tests listed in the File Map
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/SearchPlaylistPanel.tsx`
- Modify: `frontend/src/searchSurfaceState.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/apiClient.ts`
- Modify: `frontend/src/styles.css`
- Modify: mixed frontend tests from Task 1

**Interfaces:**
- Consumes: shared track rows, preview callbacks, Current Set state, export callbacks
- Produces: remaining search tabs and shared Current Set without any SET/Hybrid state or call path

- [ ] **Step 1: Delete the feature helper and dedicated tests**

Delete `setBuilderControls.ts`, its test, Hybrid state tests, and the Hybrid-only feedback payload test.

- [ ] **Step 2: Remove feature types and API methods**

Remove Set Builder/Hybrid request, response, result, diagnostic, reason-tag, feedback-state, and client method definitions. Retain generic Evaluation summary/feedback types only if a remaining frontend consumer exists; otherwise remove frontend-only clients/types while leaving backend Evaluation intact.

- [ ] **Step 3: Remove SET/Hybrid state and rendering**

Remove the `set` primary tab, nested-tab state, forms, request guards, abort controllers, response freshness signatures, result/detail components, feedback callbacks, and SET bulk `Add preview` handler. Do not change Current Set state or individual Add/Remove behavior.

- [ ] **Step 4: Remove feature CSS**

Delete only selectors and responsive rules whose DOM no longer exists. Preserve shared search, result-row, player, Current Set, dialog, and export styles.

- [ ] **Step 5: Run the frontend tests from Task 1**

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity\frontend'
npm test
```

Expected: all maintained frontend tests pass and no deleted test is collected.

- [ ] **Step 6: Run TypeScript verification**

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity\frontend'
npm run typecheck
```

Expected: exit code 0.

- [ ] **Step 7: Commit the frontend removal**

```powershell
git add -u -- frontend
git diff --cached --check
git commit -m "refactor: remove SET and Hybrid frontend"
```

---

### Task 4: Neutralize retained Evaluation fixtures and defaults

**Files:**
- Modify: `src/dj_track_similarity/evaluation/score_profile_optimizer.py`
- Modify: `tests/test_api_evaluation.py`
- Modify: `tests/test_evaluation_cli.py`
- Modify: `tests/test_evaluation_optimizer_e2e.py`
- Modify: `tests/test_evaluation_report.py`

**Interfaces:**
- Consumes: generic Evaluation candidate-session and feedback-source contracts
- Produces: Evaluation behavior with neutral defaults and no active Hybrid branding

- [ ] **Step 1: Change the default optimized profile name**

Set `DEFAULT_PROFILE_NAME` to `weighted_candidates_judged_v1` and update expected payloads.

- [ ] **Step 2: Replace generic fixture values**

Use existing neutral contracts:

```python
session_mode = "evaluation_candidate_pool"
feedback_source = "manual"
profile_name = "weighted_candidates_judged_v1"
```

Do not introduce aliases for `hybrid_search_preview`, `hybrid_ui`, or `hybrid_judged_v1`.

- [ ] **Step 3: Run retained Evaluation tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_api_evaluation.py tests\test_evaluation_cli.py tests\test_evaluation_optimizer_e2e.py tests\test_evaluation_report.py tests\test_evaluation_score_profile_optimizer.py tests\test_evaluation_weighted_candidates.py tests\test_evaluation_risk_sweep.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Commit the neutral Evaluation cleanup**

```powershell
git add -- src/dj_track_similarity/evaluation/score_profile_optimizer.py tests
git diff --cached --check
git commit -m "refactor: neutralize Evaluation workflow naming"
```

---

### Task 5: Remove scripts and maintained documentation

**Files:**
- Modify: `scripts/benchmark_search.py`
- Modify: `scripts/tests/test_benchmark_search.py`
- Modify: `README.md`
- Modify: `docs/dj-track-similarity/.vitepress/config.mts`
- Delete: dedicated English/Russian Set Builder pages
- Modify: every maintained English/Russian page with active SET/Hybrid claims

**Interfaces:**
- Consumes: remaining CLI/API/frontend capability surface
- Produces: docs and scripts that describe only executable current behavior

- [ ] **Step 1: Remove Hybrid benchmark modes and tests**

Preserve benchmarks for remaining search implementations. Remove feature imports, CLI options, output fields, and fixtures.

- [ ] **Step 2: Delete dedicated docs and navigation entries**

Delete the Smart Set Builder and routing pages plus exact Russian mirrors. Remove their VitePress sidebar links.

- [ ] **Step 3: Rewrite mixed docs**

Remove SET/Hybrid instructions, API paths, screenshots/copy, and capability claims. Preserve Current Set/export/audio preview instructions and Evaluation CLI/API documentation.

- [ ] **Step 4: Run script tests**

```powershell
.\.venv\Scripts\python.exe -m pytest scripts\tests -q
```

Expected: all maintained script tests pass.

- [ ] **Step 5: Run docs verification**

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity\docs\dj-track-similarity'
npm run check
```

Expected: 0 errors and 0 warnings.

- [ ] **Step 6: Commit scripts and docs cleanup**

```powershell
git add -u -- README.md docs/dj-track-similarity scripts
git diff --cached --check
git commit -m "docs: remove SET and Hybrid workflows"
```

---

### Task 6: Prove physical cleanup and verify the application

**Files:**
- No planned source creation
- Inspect: all tracked changes since design commit `a122e3b750c3431a0ccd2b681e1e5ea961344822`

**Interfaces:**
- Consumes: completed code/docs removal
- Produces: evidence that only historical spec/plan/snapshot artifacts retain the removed terminology

- [ ] **Step 1: Enumerate physical deletions**

```powershell
git diff --name-status a122e3b750c3431a0ccd2b681e1e5ea961344822..HEAD
git diff --diff-filter=D --name-only a122e3b750c3431a0ccd2b681e1e5ea961344822..HEAD
```

- [ ] **Step 2: Run active-legacy sentinels**

Search tracked source, tests, scripts, maintained docs, and frontend while excluding `.ideas`, `docs/superpowers`, `.git`, dependencies, and build output:

```powershell
rg -n --hidden -g '!/.git/**' -g '!/.ideas/**' -g '!docs/superpowers/**' -g '!/.venv/**' -g '!node_modules/**' -g '!dist/**' -g '!build/**' -g '!coverage/**' 'set-builder|Set Builder|SetBuilder|set_builder|set_sequence|Hybrid Preview|HybridSearch|hybrid_search|hybrid_transition|hybrid_explanation|hybrid_search_preview|hybrid_ui|hybrid_judged_v1' src frontend tests scripts docs/dj-track-similarity README.md
```

Expected: zero matches, except a reviewed generic word that is not an identifier or capability claim. Prefer removing/rewriting every match.

- [ ] **Step 3: Run full backend tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] **Step 4: Run full Ruff check**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

- [ ] **Step 5: Re-run frontend tests and typecheck**

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity\frontend'
npm test
npm run typecheck
```

- [ ] **Step 6: Smoke-test retained CLI and Evaluation group**

```powershell
.\.venv\Scripts\dj-sim.exe --help
.\.venv\Scripts\dj-sim.exe eval --help
```

- [ ] **Step 7: Check the complete diff**

```powershell
git diff --check a122e3b750c3431a0ccd2b681e1e5ea961344822..HEAD
git status --short --branch
```

---

### Task 7: Back up and clean the current database bundle once

**Files:**
- Read/modify: `database/volumes.sqlite`
- Conditionally read/modify: `database/volumes.evaluation.sqlite`
- Read-only evidence: `database/volumes.artifacts.sqlite`
- Create ignored local backup set: `database/backups/<timestamp>-pre-set-hybrid-removal/`

**Interfaces:**
- Consumes: current Core/Evaluation schemas and the exact removed identifiers
- Produces: one consistent backup set, zero bounded removed rows, verified preserved data

- [ ] **Step 1: Resolve and validate exact paths**

Resolve every target with `Resolve-Path -LiteralPath`; assert Core and Artifacts remain inside `C:\projects\dj-track-similarity\database`. Detect the optional sidecar by exact filename only.

- [ ] **Step 2: Capture pre-apply evidence**

Record sizes, timestamps, SHA-256 hashes, catalog identity, `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, library row counts, Evaluation category counts, and exact target counts. Use read-only SQLite connections.

- [ ] **Step 3: Create one backup set**

Create one timestamped directory and use the SQLite CLI `.backup` command for Core and the optional Evaluation sidecar. Write a manifest containing source/backup paths, sizes, hashes, catalog UUID, and pre-apply counts. Do not back up Artifacts because it is not modified.

- [ ] **Step 4: Apply bounded Core cleanup in one transaction**

Execute with foreign keys enabled:

```sql
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;
DELETE FROM pair_feedback WHERE source = 'hybrid_ui';
DELETE FROM library_settings
WHERE setting_key = 'evaluation.promoted_score_profile'
  AND json_extract(setting_value, '$.profile_name') = 'hybrid_judged_v1';
COMMIT;
```

The current read-only inventory predicts zero deleted Core rows.

- [ ] **Step 5: Apply bounded sidecar cleanup only if the sidecar exists**

After schema validation, execute with foreign keys enabled:

```sql
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;
DELETE FROM search_sessions WHERE mode = 'hybrid_search_preview';
DELETE FROM calibration_runs
WHERE profile_name = 'hybrid_judged_v1'
   OR search_mode = 'hybrid_search_preview';
DELETE FROM evaluation_settings
WHERE setting_key IN ('hybrid_search_preview', 'hybrid_judged_v1');
COMMIT;
```

Do not use broad `%hybrid%` deletion predicates.

- [ ] **Step 6: Verify post-apply state**

Require `integrity_check=ok`, no foreign-key violations, zero exact target rows, identical preserved Evaluation counts, identical Core library counts, and unchanged Artifacts size/time/hash. Verify backup hashes against the manifest.

- [ ] **Step 7: Report database effects**

Report backup location and recoverability, exact deleted counts per table, no-op status when applicable, and all preserved count/hash evidence. Do not stage database or backup files.

---

### Task 8: Final review and handoff

**Files:**
- Inspect: complete branch history and worktree

**Interfaces:**
- Consumes: verified code cleanup and database cleanup evidence
- Produces: clean local `main` with no required work remaining

- [ ] **Step 1: Review commits and staged scope**

```powershell
git log --oneline a122e3b..HEAD
git status --short --branch
```

- [ ] **Step 2: Confirm no ignored user data was staged**

```powershell
git ls-files database .ideas
```

Expected: no real database, backup, audio, model, report, or `.ideas` file newly tracked.

- [ ] **Step 3: Summarize results**

Include physical deletion counts and representative paths; preserved Current Set/Evaluation behavior; exact verification commands/results; backup path/digest; database deleted/preserved counts; branch/remote status; and any explicitly unrun check.
