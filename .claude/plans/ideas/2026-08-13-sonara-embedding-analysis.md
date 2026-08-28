# SONARA Embedding Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute SONARA's native 48D embedding during normal analysis, persist it atomically with Core in the main library, and trust stored embedding rows during future candidate discovery.

**Architecture:** Register `sonara/embedding` in the existing analysis-output and embedding-storage contracts. Request `embedding` in the single SONARA runtime pass, validate and convert only the fresh result, then UPSERT Core and embedding under one savepoint. Candidate discovery reads only stored identity keys and does not load or validate embedding BLOBs.

**Tech Stack:** Python 3.11, NumPy float32, SQLite/WAL, pytest, SONARA 0.3.5+sym06fallback.1.

## Global Constraints

- Work directly on `main`.
- Use `database/volumes.sqlite` as the real target database.
- SONARA contract: `SIMILARITY_VERSION=2`, `EMBEDDING_DIM=48`, Python `List[float]`, persisted little-endian float32 BLOB of 192 bytes.
- Store `normalization='none'`; do not apply or require L2 normalization.
- Validate only freshly calculated values at analysis/write time.
- Do not read, decode, or validate stored embedding payloads during candidate discovery.
- Do not integrate SONARA embeddings into search, classifiers, Rhythm Lab, Audio Dedup, or the UI.
- Do not copy the 2,336 experimental rows into the main database.
- Do not commit or stage changes unless the user explicitly requests delivery.

---

### Task 1: Define failing SONARA and stored-readiness contracts

**Files:**
- Modify: `tests/test_analysis_orchestration.py`
- Modify: `tests/test_sonara_features.py`
- Modify: `tests/test_sonara_storage.py`
- Modify: `tests/test_single_library_runtime.py`

**Interfaces:**
- Consumes: existing `SonaraModelRunner`, `prepare_sonara_write()`, `LibraryDatabase`, `collect_analysis_candidates()`.
- Produces: observable contracts for default SONARA outputs, a typed 48D write, the fixed table format, and payload-free readiness queries.

- [ ] **Step 1: Make runner and batch expectations require both outputs**

Update the existing focused tests so the literal expected keys are:

```python
[("sonara", "core"), ("sonara", "embedding")]
```

and so the requested SONARA features equal:

```python
(*SONARA_CORE_REQUESTED_FEATURES, "embedding")
```

- [ ] **Step 2: Require the converted write to carry the exact fresh vector**

Extend `test_complete_analyzer_result_becomes_one_typed_sonara_write` with:

```python
assert write.embedding is not None
assert write.embedding.family == "sonara"
assert write.embedding.vector.dtype == np.dtype("<f4")
assert write.embedding.vector.shape == (48,)
assert np.array_equal(write.embedding.vector, _analysis()["embedding"])
assert write.outputs == (
    AnalysisOutput("sonara", "core"),
    AnalysisOutput("sonara", "embedding"),
)
```

- [ ] **Step 3: Add a fixed table-format round-trip**

Add a test that creates a temporary `LibraryDatabase`, inserts one track, calls `database.write_embedding()` with `family="sonara"` and a 48-value float32 vector, then asserts this literal stored contract:

```python
{
    "track_id": track_id,
    "track_uuid": "track-sonara-48d",
    "dim": 48,
    "normalization": "none",
    "blob_size": 192,
    "analyzed_at": analyzed_at,
}
```

- [ ] **Step 4: Prove readiness does not read stored payloads**

Use a real temporary SQLite connection containing a valid MERT row. Install a SQLite authorizer that returns `sqlite3.SQLITE_DENY` only for `SQLITE_READ` of column `embedding_blob`, then call `collect_analysis_candidates()` for `AnalysisOutput("mert", "embedding")`. Assert the stored track is considered ready and no exception is raised. The existing implementation must fail because it selects `embedding_blob`.

- [ ] **Step 5: Run the focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_orchestration.py::test_sonara_runner_exposes_default_core_and_embedding_outputs tests/test_sonara_features.py::test_default_batch_requests_registers_and_writes_core_with_embedding tests/test_sonara_storage.py::test_complete_analyzer_result_becomes_one_typed_sonara_write tests/test_single_library_runtime.py::test_sonara_embedding_table_uses_the_fixed_unversioned_48d_format tests/test_single_library_runtime.py::test_stored_embedding_readiness_does_not_read_payload -q
```

Expected: failures caused by the absent SONARA output/table/write integration and the current payload-selecting readiness query.

### Task 2: Register the SONARA embedding storage contract

**Files:**
- Modify: `src/dj_track_similarity/analysis_models.py`
- Modify: `src/dj_track_similarity/db_ddl.py`
- Modify: `src/dj_track_similarity/db_embeddings.py`
- Modify: `src/dj_track_similarity/db_analysis_candidates.py`

**Interfaces:**
- Consumes: `EmbeddingFamilySpec`, `EmbeddingOutput`, generic embedding UPSERT functions.
- Produces: `CURRENT_EMBEDDING_SPECS["sonara"]`, `sonara_embeddings`, `table_for_output(AnalysisOutput("sonara", "embedding"))`.

- [ ] **Step 1: Register the fixed family and output kind**

Add `SONARA_EMBEDDING_DIM = 48`, register `EmbeddingFamilySpec(48, "none")`, and permit `AnalysisOutput("sonara", "embedding")`. Extend `SonaraWrite` with `embedding: EmbeddingOutput | None` and expose that output only when present.

- [ ] **Step 2: Add the fresh-library table and storage mapping**

Add the exact `sonara_embeddings` DDL from the approved design before the MAEST tables, include it in `_ALL_DDL`, and map `"sonara"` to `"sonara_embeddings"` in `_EMBEDDING_TABLES` and `("sonara", "embedding")` in `_TABLE_BY_OUTPUT`.

- [ ] **Step 3: Replace persisted-payload readiness validation with identity-key loading**

Change the embedding readiness query to select only:

```sql
SELECT track_id, track_uuid FROM {table}
```

Return rows whose `(track_id, track_uuid)` match a current track. Remove the candidate module's dependency on `validate_embedding_row_payload`; do not alter write-time validation.

- [ ] **Step 4: Run the table and readiness tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_single_library_runtime.py::test_sonara_embedding_table_uses_the_fixed_unversioned_48d_format tests/test_single_library_runtime.py::test_stored_embedding_readiness_does_not_read_payload -q
```

Expected: `2 passed`.

### Task 3: Wire one SONARA pass to atomic Core plus embedding persistence

**Files:**
- Modify: `src/dj_track_similarity/sonara_runtime.py`
- Modify: `src/dj_track_similarity/sonara_features.py`
- Modify: `src/dj_track_similarity/sonara_storage.py`
- Modify: `src/dj_track_similarity/db_analysis.py`
- Modify: `tests/test_api_analysis_jobs.py`

**Interfaces:**
- Consumes: `sonara_requested_features()`, `_float32_vector()`, `write_valid_embedding_in_transaction()`.
- Produces: one `SonaraWrite` with Core and SONARA `EmbeddingOutput`, saved atomically.

- [ ] **Step 1: Request and advertise the new output**

Return `(*SONARA_CORE_REQUESTED_FEATURES, "embedding")` from `sonara_requested_features()` and return both `AnalysisOutput` values from `analysis_outputs_for_sonara_runtime()`.

- [ ] **Step 2: Convert the fresh result**

In `prepare_sonara_write()`, build:

```python
EmbeddingOutput(
    family="sonara",
    vector=_float32_vector(
        analysis.get("embedding"),
        dim=48,
        field_name="embedding",
    ),
    analyzed_at=analyzed_at,
)
```

This is the analysis-time type, shape, and finite-value validation boundary.

- [ ] **Step 3: Persist Core and embedding under one savepoint**

After `_upsert_sonara_core()` succeeds, call `write_valid_embedding_in_transaction()` with `_embedding_track(write.target)` and the typed embedding before releasing the savepoint.

- [ ] **Step 4: Run the SONARA focused tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_orchestration.py tests/test_sonara_features.py tests/test_sonara_storage.py tests/test_api_analysis_jobs.py tests/test_single_library_runtime.py -q
```

Expected: all selected tests pass with no warnings introduced by this change.

### Task 4: Create the table safely in the main database

**Files:**
- Modify data: `database/volumes.sqlite`
- Create recovery copy: `database/volumes.before-sonara-embeddings.<timestamp>.sqlite`

**Interfaces:**
- Consumes: approved `sonara_embeddings` DDL.
- Produces: an empty main-database table ready for user-run reanalysis.

- [ ] **Step 1: Resolve targets and capture the pre-change state**

Resolve both absolute paths inside `C:\projects\dj-track-similarity\database`, check available disk space, record SHA-256 of the source, direct row counts for existing tables, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check`.

- [ ] **Step 2: Create a recoverable SQLite backup**

Use SQLite's online `.backup` operation to a new timestamped path. Verify the backup hash, integrity, foreign keys, catalog UUID, and table counts before changing the source.

- [ ] **Step 3: Apply only the table and index DDL**

Execute `CREATE TABLE sonara_embeddings ...` and `CREATE INDEX idx_sonara_embeddings_track_uuid ...` in one explicit transaction against `database/volumes.sqlite`.

- [ ] **Step 4: Verify the reopened main database**

Reopen read-only and assert: integrity is `ok`, foreign-key check is empty, every pre-existing table count is unchanged, schema SQL matches the approved structure, and `SELECT COUNT(*) FROM sonara_embeddings` returns `0`.

### Task 5: Final focused verification and graph refresh

**Files:**
- Refresh generated graph state under `graphify-out/`.

**Interfaces:**
- Consumes: all implementation changes and verified main schema.
- Produces: current focused test evidence, clean scoped diff, and an updated code graph.

- [ ] **Step 1: Run focused backend verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_orchestration.py tests/test_sonara_features.py tests/test_sonara_storage.py tests/test_api_analysis_jobs.py tests/test_single_library_runtime.py -q
```

- [ ] **Step 2: Inspect the scoped diff**

Run `git diff --check` and inspect only the touched source/test paths. Confirm no launcher, frontend, classifier, Rhythm Lab, Audio Dedup, or experimental database path changed.

- [ ] **Step 3: Update the project graph**

Run `graphify update .` through the interpreter recorded in `graphify-out/.graphify_python`, then inspect `git status` so graph outputs remain separated from product changes.

- [ ] **Step 4: Recheck the real table without payload validation**

Query only the table schema, index, direct row count, integrity check, and foreign-key check. Do not scan embedding BLOBs.
