# SONARA Core-only Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SONARA analysis request, validate, persist, and expose Core only while preserving the existing reserved Artifacts tables and their creation order.

**Architecture:** Collapse the application-level SONARA output contract from four selectable outputs to one fixed Core output. Keep the explicit Core feature allowlist, discard any non-Core values returned by SONARA at the adapter boundary, and remove optional-output controls and read surfaces vertically through backend, API, frontend, and documentation. Preserve the Artifacts DDL and schema fingerprint exactly so new databases still contain the reserved tables.

**Tech Stack:** Python 3.12, Typer, FastAPI/Pydantic, SQLite, pytest, React 19, TypeScript, Vite, Node `node:test`, VitePress.

## Global Constraints

- Preserve every current SONARA Core field and its validation.
- Do not request standalone SONARA features `"embedding"` or `"fingerprint"`.
- Keep Core-required feature groups such as `beats`, `tempo_curve`, `beatgrid`, `structure`, and `loudness`.
- Register and persist only `AnalysisOutput("sonara", "core")`.
- Do not alter the DDL, columns, indexes, schema fingerprint, or creation order of `sonara_timeline`, `sonara_similarity_embeddings`, or `sonara_fingerprints`.
- Do not delete database rows or touch audio files.
- Ignore extra fields returned by SONARA.
- Keep `vocalness_model="bundled"`; any internal embedding computation remains SONARA's implementation detail.
- Preserve the unrelated untracked `database/` directory.

---

### Task 1: Collapse the SONARA runtime and typed write model to Core

**Files:**
- Modify: `src/dj_track_similarity/sonara_runtime.py`
- Modify: `src/dj_track_similarity/sonara_features.py`
- Modify: `src/dj_track_similarity/sonara_storage.py`
- Modify: `src/dj_track_similarity/analysis_models.py`
- Test: `tests/test_sonara_features.py`
- Test: `tests/test_sonara_storage.py`
- Test: `tests/test_analysis_orchestration.py`
- Test: `tests/test_model_adapter_identity.py`

**Interfaces:**
- Produces: `sonara_requested_features() -> tuple[str, ...]`, containing only `SONARA_CORE_REQUESTED_FEATURES`.
- Produces: `prepare_sonara_write(candidate, analysis, *, analyzed_at) -> SonaraWrite`.
- Produces: `SonaraWrite(target: AnalysisTarget, core: SonaraRow)` with no optional Timeline, embedding, or fingerprint fields.
- Produces: `analysis_outputs_for_sonara_runtime() == (AnalysisOutput("sonara", "core"),)`.

- [ ] **Step 1: Write failing Core-only runtime tests**

Add or replace focused assertions:

```python
def test_sonara_runtime_requests_only_core_features() -> None:
    requested = set(sonara_requested_features())
    assert requested == set(SONARA_CORE_REQUESTED_FEATURES)
    assert "embedding" not in requested
    assert "fingerprint" not in requested


def test_sonara_runtime_registers_only_core_output() -> None:
    assert analysis_outputs_for_sonara_runtime() == (
        AnalysisOutput("sonara", "core"),
    )
```

Update the fake SONARA batch test to capture `features` and assert that the
native call excludes `"embedding"` and `"fingerprint"` while the stored write
contains a valid Core row.

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```powershell
python -m pytest tests\test_sonara_features.py tests\test_analysis_orchestration.py --override-ini addopts=
```

Expected: failures showing four registered outputs and optional features still
present in the native request.

- [ ] **Step 3: Write failing typed-conversion tests**

Change the direct conversion call to:

```python
write = prepare_sonara_write(
    candidate,
    analysis,
    analyzed_at="2026-07-30T00:00:00.000000Z",
)
assert write.target == candidate.target
assert write.core.detected_bpm == 128.0
assert not hasattr(write, "timeline")
assert not hasattr(write, "similarity_embedding")
assert not hasattr(write, "fingerprint")
```

Keep the existing assertions for every Core scalar and compact vector so the
test characterizes the data that must survive.

- [ ] **Step 4: Run the conversion test and verify the expected failure**

Run:

```powershell
python -m pytest tests\test_sonara_storage.py --override-ini addopts=
```

Expected: failure because `prepare_sonara_write` still requires `outputs` and
`SonaraWrite` still exposes optional output fields.

- [ ] **Step 5: Implement the minimal Core-only runtime**

In `sonara_runtime.py`:

```python
def sonara_requested_features() -> tuple[str, ...]:
    return SONARA_CORE_REQUESTED_FEATURES
```

Delete `SONARA_OUTPUT_KINDS`, `DEFAULT_SONARA_OUTPUTS`,
`SONARA_TIMELINE_REQUESTED_FEATURES`,
`SONARA_EMBEDDING_REQUESTED_FEATURES`,
`SONARA_FINGERPRINT_REQUESTED_FEATURES`, `_REQUESTED_FEATURES_BY_OUTPUT`,
`normalize_sonara_outputs`, and `SONARA_EMBEDDING_DIM` when no remaining
active code needs it.

In `sonara_features.py`, register only Core, remove the `outputs` parameter from
`analyze_and_store_sonara_batch`, and call:

```python
prepare_sonara_write(
    candidate,
    analysis,
    analyzed_at=utc_timestamp(),
)
```

In `analysis_models.py`, reduce the SONARA output-kind declaration to
`frozenset({"core"})`; delete `SonaraTimelineOutput`,
`SonaraFingerprintOutput`, SONARA's entry in `CURRENT_EMBEDDING_SPECS`, and the
optional fields and output expansion from `SonaraWrite`.

In `sonara_storage.py`, keep `_sonara_core_row` and its helpers, remove
Timeline payload conversion, fingerprint decoding, SONARA embedding conversion,
and the `outputs` argument.

- [ ] **Step 6: Run the focused Core runtime tests**

Run:

```powershell
python -m pytest tests\test_sonara_features.py tests\test_sonara_storage.py tests\test_analysis_orchestration.py tests\test_model_adapter_identity.py --override-ini addopts=
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit the Core runtime slice**

```powershell
git add -- src/dj_track_similarity/sonara_runtime.py src/dj_track_similarity/sonara_features.py src/dj_track_similarity/sonara_storage.py src/dj_track_similarity/analysis_models.py tests/test_sonara_features.py tests/test_sonara_storage.py tests/test_analysis_orchestration.py tests/test_model_adapter_identity.py
git commit -m "Make SONARA runtime Core-only"
```

---

### Task 2: Remove SONARA output selection from jobs, CLI, and API

**Files:**
- Modify: `src/dj_track_similarity/analysis_config.py`
- Modify: `src/dj_track_similarity/analysis_model_runners.py`
- Modify: `src/dj_track_similarity/analysis_jobs.py`
- Modify: `src/dj_track_similarity/analysis_job_state.py`
- Modify: `src/dj_track_similarity/analysis_pipeline.py`
- Modify: `src/dj_track_similarity/api_schemas.py`
- Modify: `src/dj_track_similarity/api_routes_analysis.py`
- Modify: `src/dj_track_similarity/cli.py`
- Test: `tests/test_analysis_config.py`
- Test: `tests/test_api_analysis_jobs.py`
- Test: `tests/test_analysis_sonara_preflight.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_cli_runtime.py`
- Test: `tests/test_multi_model_analysis_jobs.py`
- Test: `frontend/tests/apiContract.test.mjs`

**Interfaces:**
- Produces: `AnalysisJobConfig` with no `sonara_outputs`.
- Produces: `AnalysisJobManager.start(..., sonara_batch_size=...)` with no SONARA output-selection argument.
- Produces: analysis API and pipeline SONARA payloads that carry `batch_size` only.
- Produces: CLI commands with no `--sonara-outputs` option.

- [ ] **Step 1: Write failing configuration and API contract tests**

Replace output-normalization tests with:

```python
def test_sonara_job_config_has_no_output_selection() -> None:
    config = build_analysis_job_config(models=["sonara"])
    assert not hasattr(config, "sonara_outputs")
```

Change API calls to omit `sonara_outputs`, then assert captured manager calls do
not contain that key. Add an obsolete-client case:

```python
response = client.post(
    "/api/analysis/jobs",
    json={"models": ["sonara"], "sonara_outputs": ["fingerprint"]},
)
assert response.status_code == 422
```

The request models use `extra="forbid"`, so the obsolete value must fail rather
than silently suggest that optional collection remains supported.

- [ ] **Step 2: Run the backend contract tests and verify failure**

Run:

```powershell
python -m pytest tests\test_analysis_config.py tests\test_api_analysis_jobs.py tests\test_analysis_sonara_preflight.py --override-ini addopts=
```

Expected: failures because configuration and manager status still carry
`sonara_outputs`.

- [ ] **Step 3: Write failing CLI tests**

Assert that:

```python
assert "--sonara-outputs" not in runner.invoke(app, ["analyze", "--help"]).output
assert "--sonara-outputs" not in runner.invoke(app, ["analyze-pipeline", "--help"]).output
```

Update fake manager expectations so SONARA calls include batch size but no
`sonara_outputs`.

- [ ] **Step 4: Run the CLI tests and verify failure**

Run:

```powershell
python -m pytest tests\test_cli.py tests\test_cli_runtime.py --override-ini addopts=
```

Expected: help and captured-call assertions fail on the existing option.

- [ ] **Step 5: Remove output selection through the backend contracts**

Delete `sonara_outputs` from configuration, job state, start signatures,
serialization, pipeline configuration, request schemas, routes, logs, status
copying, and runner construction.

Make `SonaraModelRunner` and `model_runner_for("sonara")` parameterless with
respect to outputs. Keep `sonara_batch_size` unchanged.

Change the pipeline SONARA schema from:

```python
{"outputs": [...], "batch_size": 8}
```

to:

```python
{"batch_size": 8}
```

Remove both CLI options and remove `sonara_outputs=...` from progress text.
SONARA status must report only the Core coverage row.

- [ ] **Step 6: Update the TypeScript API contract fixture**

Remove `sonara_outputs` from request fixtures and assert that the serialized
request body does not contain it:

```javascript
assert.equal("sonara_outputs" in JSON.parse(fetchCalls[0].options.body), false);
```

- [ ] **Step 7: Run the focused job, API, and CLI tests**

Run:

```powershell
python -m pytest tests\test_analysis_config.py tests\test_api_analysis_jobs.py tests\test_analysis_sonara_preflight.py tests\test_cli.py tests\test_cli_runtime.py tests\test_multi_model_analysis_jobs.py --override-ini addopts=
Push-Location frontend
try { npm test } finally { Pop-Location }
```

Expected: selected checks pass.

- [ ] **Step 8: Commit the contract slice**

```powershell
git add -- src/dj_track_similarity/analysis_config.py src/dj_track_similarity/analysis_model_runners.py src/dj_track_similarity/analysis_jobs.py src/dj_track_similarity/analysis_job_state.py src/dj_track_similarity/analysis_pipeline.py src/dj_track_similarity/api_schemas.py src/dj_track_similarity/api_routes_analysis.py src/dj_track_similarity/cli.py tests/test_analysis_config.py tests/test_api_analysis_jobs.py tests/test_analysis_sonara_preflight.py tests/test_cli.py tests/test_cli_runtime.py tests/test_multi_model_analysis_jobs.py frontend/tests/apiContract.test.mjs
git commit -m "Remove SONARA output selection contracts"
```

---

### Task 3: Remove active optional storage and read paths while preserving DDL

**Files:**
- Modify: `src/dj_track_similarity/db_analysis.py`
- Modify: `src/dj_track_similarity/db_analysis_candidates.py`
- Modify: `src/dj_track_similarity/db_library_queries.py`
- Modify: `src/dj_track_similarity/library_models.py`
- Modify: `src/dj_track_similarity/api_routes_library.py`
- Modify: `src/dj_track_similarity/api_schemas.py`
- Modify: `tools/kglite-bridge/kglite_bridge/core.py`
- Modify: `tools/kglite-bridge/tests/test_kglite_bridge.py`
- Preserve: `src/dj_track_similarity/db_artifacts.py` DDL blocks and `_ALL_DDL` ordering
- Preserve: `src/dj_track_similarity/db_tracks.py` reserved-table cleanup
- Preserve: `src/dj_track_similarity/db_migration.py` reserved-table compatibility
- Test: `tests/test_db_ddl.py`
- Test: `tests/test_runtime_foundation.py`
- Test: `tests/test_sonara_storage.py`
- Test: `tests/test_library_repository.py`
- Test: `tests/test_api_tracks.py`
- Test: `tests/test_api_runtime.py`
- Test: `tests/test_artifact_identity.py`

**Interfaces:**
- Produces: SONARA writes that touch Core only.
- Produces: track details with no Timeline fields or SONARA embedding/fingerprint availability flags.
- Preserves: all three reserved Artifacts tables, their indexes, and exact order.
- Produces: KGLite sources `("maest", "mert", "muq", "clap")` without SONARA embedding edges.

- [ ] **Step 1: Write failing persistence and read-surface tests**

Update repository tests to save a Core-only `SonaraWrite` and assert:

```python
rows = database.load_sonara_feature_rows(
    AnalysisOutput("sonara", "core"),
    targets=(target,),
)
assert [row.target.track_id for row in rows] == [target.track_id]
assert not hasattr(database.get_track_detail(track_id), "optional_outputs")
```

Add an API assertion:

```python
assert client.get(f"/api/tracks/{track_id}/sonara-timeline").status_code == 404
```

- [ ] **Step 2: Run the focused repository/API tests and verify failure**

Run:

```powershell
python -m pytest tests\test_library_repository.py tests\test_api_tracks.py tests\test_api_runtime.py --override-ini addopts=
```

Expected: failures because optional summaries and the Timeline route still
exist.

- [ ] **Step 3: Remove active optional storage and read code**

Delete `_upsert_sonara_timeline`, `_upsert_sonara_fingerprint`, and the SONARA
embedding branch from `save_sonara_results`.

Remove the three SONARA optional mappings from active-output candidate lookup.
Remove SONARA from active generic embedding maps while leaving the reserved DDL
table definition intact.

Remove Timeline/fingerprint loaders, coverage aggregation, optional-output
model fields, response fields, and `/api/tracks/{track_id}/sonara-timeline`.

Keep reserved table names in track deletion/reset, schema validation, and
migration code because those tables continue to exist.

- [ ] **Step 4: Write and run the DDL preservation test**

Keep or add:

```python
def test_artifacts_schema_retains_reserved_sonara_tables() -> None:
    with database.connect_artifacts() as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "sonara_timeline",
        "sonara_similarity_embeddings",
        "sonara_fingerprints",
    } <= names
```

Also retain the current column and index assertions in `test_db_ddl.py`.

Run:

```powershell
python -m pytest tests\test_db_ddl.py tests\test_runtime_foundation.py tests\test_artifact_identity.py --override-ini addopts=
```

Expected: all selected DDL checks pass with no schema fingerprint drift.

- [ ] **Step 5: Remove the KGLite SONARA embedding source**

Read `tools/kglite-bridge/AGENTS.md`, remove `"sonara"` from
`SUPPORTED_SOURCES`, `SOURCE_TABLES`, and projected relationship tests. Keep
MAEST/MERT/MuQ/CLAP behavior unchanged.

Run:

```powershell
python -m pytest tools\kglite-bridge\tests\test_kglite_bridge.py --override-ini addopts=
```

Expected: KGLite bridge tests pass with four embedding sources.

- [ ] **Step 6: Run the complete focused storage slice**

Run:

```powershell
python -m pytest tests\test_sonara_storage.py tests\test_library_repository.py tests\test_api_tracks.py tests\test_api_runtime.py tests\test_db_ddl.py tests\test_runtime_foundation.py tests\test_artifact_identity.py --override-ini addopts=
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit the storage/read slice**

```powershell
git add -- src/dj_track_similarity/db_analysis.py src/dj_track_similarity/db_analysis_candidates.py src/dj_track_similarity/db_library_queries.py src/dj_track_similarity/library_models.py src/dj_track_similarity/api_routes_library.py src/dj_track_similarity/api_schemas.py tools/kglite-bridge/kglite_bridge/core.py tools/kglite-bridge/tests/test_kglite_bridge.py tests/test_db_ddl.py tests/test_runtime_foundation.py tests/test_sonara_storage.py tests/test_library_repository.py tests/test_api_tracks.py tests/test_api_runtime.py tests/test_artifact_identity.py
git commit -m "Retire active SONARA optional artifacts"
```

---

### Task 4: Remove SONARA output controls and metadata blocks from the frontend

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/apiClient.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/LibraryPanel.tsx`
- Modify: `frontend/src/TrackMetadataDialog.tsx`
- Modify: `frontend/src/jobUi.tsx`
- Test: `frontend/tests/buttonClasses.test.mjs`
- Test: `frontend/tests/libraryLoading.test.mjs`
- Test: `frontend/tests/metadataReference.test.mjs`
- Test: `frontend/tests/sonaraDisplay.test.mjs`
- Test: `frontend/tests/apiContract.test.mjs`

**Interfaces:**
- Produces: analysis requests with SONARA batch size and no output array.
- Produces: Library analysis UI with no SONARA output checkbox fieldset.
- Produces: track metadata with Core groups only.

- [ ] **Step 1: Read frontend instructions and write failing source-contract tests**

Read `frontend/AGENTS.md`.

Replace the old checkbox assertions with:

```javascript
assert.doesNotMatch(appSource, /sonaraOutputs|toggleSonaraOutput/);
assert.doesNotMatch(panelSource, />Timeline</);
assert.doesNotMatch(panelSource, />Embedding</);
assert.doesNotMatch(panelSource, />Fingerprint</);
```

For metadata:

```javascript
assert.doesNotMatch(dialogSource, /TimelinePresenceBlock/);
assert.doesNotMatch(dialogSource, /sonaraEmbeddingAvailable/);
assert.doesNotMatch(dialogSource, /audioFingerprintAvailable/);
```

- [ ] **Step 2: Run frontend tests and verify failure**

Run:

```powershell
Push-Location frontend
try { npm test } finally { Pop-Location }
```

Expected: the new absence assertions fail against the existing controls.

- [ ] **Step 3: Remove frontend output-selection state and types**

Delete `SonaraOutput`, optional SONARA coverage flags, `DEFAULT_SONARA_OUTPUTS`,
`sonara_outputs` payload fields, App state/toggle logic, LibraryPanel props and
fieldset, job output formatting, and metadata presence blocks.

Change the pipeline request shape to:

```typescript
sonara: { batch_size: number };
```

The confirmation summary should describe SONARA Core and batch size without an
output list.

- [ ] **Step 4: Run frontend tests, typecheck, and build**

Run:

```powershell
Push-Location frontend
try {
    npm test
    npm run typecheck
    npm run build
} finally {
    Pop-Location
}
```

Expected: tests, TypeScript checks, and Vite build pass.

- [ ] **Step 5: Commit the frontend slice**

```powershell
git add -- frontend/src/api.ts frontend/src/apiClient.ts frontend/src/App.tsx frontend/src/LibraryPanel.tsx frontend/src/TrackMetadataDialog.tsx frontend/src/jobUi.tsx frontend/tests/buttonClasses.test.mjs frontend/tests/libraryLoading.test.mjs frontend/tests/metadataReference.test.mjs frontend/tests/sonaraDisplay.test.mjs frontend/tests/apiContract.test.mjs
git commit -m "Remove SONARA optional output controls"
```

---

### Task 5: Align maintained documentation and prove the complete boundary

**Files:**
- Modify: `README.md`
- Modify: `docs/dj-track-similarity/user-guide/analyze-library.md`
- Modify: `docs/dj-track-similarity/reference/sonara-integration.md`
- Modify: `docs/dj-track-similarity/reference/cli.md`
- Modify: `docs/dj-track-similarity/reference/api.md`
- Modify: `docs/dj-track-similarity/reference/database.md`
- Modify: `docs/dj-track-similarity/tools-and-scripts/kglite-bridge.md`
- Modify: `docs/dj-track-similarity/ru/user-guide/analyze-library.md`
- Modify: `docs/dj-track-similarity/ru/reference/sonara-integration.md`
- Modify: `docs/dj-track-similarity/ru/reference/cli.md`
- Modify: `docs/dj-track-similarity/ru/reference/api.md`
- Modify: `docs/dj-track-similarity/ru/reference/database.md`
- Modify: `docs/dj-track-similarity/ru/tools-and-scripts/kglite-bridge.md`

**Interfaces:**
- Produces: English and Russian docs that describe Core-only collection.
- Preserves: database reference entries for the three reserved tables, marked as currently unpopulated.

- [ ] **Step 1: Update English documentation**

Remove `--sonara-outputs` examples and four-output descriptions. State:

```text
The current application integration requests and stores SONARA Core only.
The reserved Timeline, SONARA similarity embedding, and fingerprint Artifacts
tables are created for future use but are not populated by analysis.
```

Update KGLite docs to list only MAEST, MERT, MuQ, and CLAP similarity edges.

- [ ] **Step 2: Mirror the change in Russian documentation**

Use the matching statement:

```text
Текущая интеграция приложения запрашивает и сохраняет только SONARA Core.
Зарезервированные таблицы Timeline, SONARA similarity embedding и fingerprint
создаются для возможного будущего использования, но анализ их не заполняет.
```

Keep English as the source and preserve section parity in the Russian mirror.

- [ ] **Step 3: Run documentation sentinel searches**

Run:

```powershell
rg -n --glob '!docs/superpowers/**' --glob '!docs/dj-track-similarity/site/**' -- '--sonara-outputs|core,timeline,embedding,fingerprint|SIMILAR_SONARA' README.md docs/dj-track-similarity
```

Expected: no active user instruction or KGLite claim remains. Reserved-table
reference names may remain.

- [ ] **Step 4: Run maintained documentation checks**

Run:

```powershell
Push-Location docs\dj-track-similarity
try { npm run check } finally { Pop-Location }
```

Expected: Vale and VitePress build pass.

- [ ] **Step 5: Run the final focused regression set**

Run:

```powershell
python -m pytest tests\test_sonara_features.py tests\test_sonara_storage.py tests\test_analysis_config.py tests\test_analysis_orchestration.py tests\test_api_analysis_jobs.py tests\test_analysis_sonara_preflight.py tests\test_cli.py tests\test_cli_runtime.py tests\test_multi_model_analysis_jobs.py tests\test_library_repository.py tests\test_api_tracks.py tests\test_api_runtime.py tests\test_db_ddl.py tests\test_runtime_foundation.py tests\test_artifact_identity.py --override-ini addopts=
python -m pytest tools\kglite-bridge\tests\test_kglite_bridge.py --override-ini addopts=
Push-Location frontend
try {
    npm test
    npm run typecheck
    npm run build
} finally {
    Pop-Location
}
```

Expected: all commands exit `0`.

- [ ] **Step 6: Inspect the final diff and Core-only sentinels**

Run:

```powershell
git diff --check
rg -n --glob '!docs/superpowers/**' --glob '!docs/dj-track-similarity/site/**' --glob '!database/**' 'SONARA_OUTPUT_KINDS|normalize_sonara_outputs|sonara_outputs|TimelinePresenceBlock|SIMILAR_SONARA' src tests frontend tools README.md docs/dj-track-similarity
git status --short
git diff --stat
```

Expected: no active optional-output selection symbols remain; any retained
Timeline/embedding/fingerprint references are limited to reserved DDL,
schema/migration compatibility, cleanup invariants, and database documentation.

- [ ] **Step 7: Commit the documentation and verification slice**

```powershell
git add -- README.md docs/dj-track-similarity
git commit -m "Document SONARA Core-only analysis"
```
