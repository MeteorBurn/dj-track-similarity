# SONARA All-Outputs Analysis and Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every SONARA run produce one complete Core/Timeline/Embedding/Fingerprint result, remove all user-facing output selection, and expose only compact complete-result summaries in track metadata.

**Architecture:** Keep SONARA's four output identifiers for registration, readiness, persistence, and status, but remove every public and internal subset override. Convert and save one non-optional `SonaraWrite` bundle with one timestamp. Keep heavy JSON/BLOB values in the Artifacts SQLite and replace Library/detail hydration with metadata-only projections; only explicit server-side consumers load payloads. Present the complete bundle through one nullable typed API summary and one shared SONARA category renderer.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLite, pytest, React, TypeScript, Vite, Node `node:test`.

## Global Constraints

- Follow `docs/superpowers/specs/2026-07-30-sonara-all-outputs-metadata-design.md` as the approved product contract.
- A valid SONARA result is exactly Core + Timeline + Embedding + Fingerprint with one shared `analyzed_at`, or no SONARA result. Never expose a partial result as ready.
- Preserve `SONARA_OUTPUT_KINDS`, per-output registrations, job-status reporting, reset behavior, and internal coverage identifiers. Remove only the ability to choose a subset.
- Preserve the Library panel's mode rules: SONARA alone, CLASSIFIERS alone, or one or more MAEST/MERT/MuQ/CLAP models. Do not make a direct SONARA+ML+CLASSIFIERS job possible; the explicit pipeline remains the sequential orchestrator.
- Keep Timeline JSON, embedding BLOBs, and fingerprint BLOBs only in the mandatory Artifacts database. Library list/detail/readiness projections must not materialize those values.
- Preserve full payload validation before writes and in explicit consumers. Metadata-only reads may validate identity, dimensions, normalization, internal fingerprint metadata, timestamps, and SQL byte lengths.
- Link stored fingerprint data through the existing `track_id + track_uuid + content_generation` row identity and Artifacts/Core `catalog_uuid` binding. Do not add a retrieval API, matcher, hash, duplicate search, version badge, word-count badge, or byte-order badge.
- The metadata dialog must show `Timeline`, `Embedding`, `Fingerprint`, `Analysis` in that order immediately after `Vector summaries`. Fingerprint is only a green Check icon with accessible label `Fingerprint ready`; it has no visible `Ready` text.
- `Analysis` contains exactly one `Analyzed` value sourced from `optional_outputs.analyzed_at`; output categories have no individual timestamps.
- When the complete summary is absent, show one SONARA-level `Не рассчитано` state. Filter SONARA out of the generic `Embedding analyses` section.
- Do not modify source audio. Do not open, migrate, or test against `database/` or another real project database. All database tests use temporary bundles.
- Preserve unrelated working-tree changes and never stage `database/`.
- Use TDD for each task: first change the focused tests and observe the expected failure, then implement the smallest production change, then rerun the focused tests.

---

### Task 1: Remove SONARA subset selection from backend, API, pipeline, and CLI

**Files:**
- Modify: `tests/test_analysis_config.py`
- Modify: `tests/test_api_analysis_jobs.py`
- Modify: `tests/test_analysis_pipeline.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_cli_runtime.py`
- Modify: `src/dj_track_similarity/analysis_config.py`
- Modify: `src/dj_track_similarity/api_schemas.py`
- Modify: `src/dj_track_similarity/api_routes_analysis.py`
- Modify: `src/dj_track_similarity/analysis_jobs.py`
- Modify: `src/dj_track_similarity/analysis_pipeline.py`
- Modify: `src/dj_track_similarity/cli.py`

**Interfaces:**
- `build_analysis_job_config(...).sonara_outputs` remains an internal status/readiness tuple. It equals `SONARA_OUTPUT_KINDS` when `models` contains SONARA and `()` otherwise.
- `AnalysisJobRequest` no longer accepts `sonara_outputs`.
- `SonaraPipelineSettings` contains `batch_size` only.
- `AnalysisJobManager.create_job()` no longer accepts `sonara_outputs`.
- Pipeline SONARA settings contain `{"batch_size": int}` only.
- `dj-sim analyze` and `dj-sim analyze-pipeline` no longer expose `--sonara-outputs`.
- `AnalysisJobStatus.sonara_outputs` remains and reports all four canonical outputs for SONARA.

- [ ] **Step 1: Specify the fixed configuration contract**

Replace the subset/default tests in `tests/test_analysis_config.py` with assertions equivalent to:

```python
def test_build_analysis_job_config_assigns_all_sonara_outputs() -> None:
    assert build_analysis_job_config(models=["sonara"]).sonara_outputs == (
        "core",
        "timeline",
        "embedding",
        "fingerprint",
    )
    assert build_analysis_job_config(models=["mert"]).sonara_outputs == ()
```

Delete tests that call `build_analysis_job_config(..., sonara_outputs=...)`; the removed Python argument is intentional.

- [ ] **Step 2: Specify stale-client rejection and pipeline payload shape**

In `tests/test_api_analysis_jobs.py`:

- assert a top-level `sonara_outputs` field returns `422`;
- assert `sonara: {"outputs": [...]}` in the pipeline request returns `422`;
- assert SONARA still accepts `sonara_batch_size`;
- assert the captured analysis-manager kwargs have no `sonara_outputs` key;
- assert the captured pipeline SONARA settings equal `{"batch_size": 8}`;
- preserve the existing rejection of a direct `models=["sonara", "mert"]` job and of classifier fields in an audio-analysis request.

Use explicit absence checks:

```python
assert "sonara_outputs" not in calls[0]
assert calls[0]["sonara_batch_size"] == 8
```

- [ ] **Step 3: Specify CLI and pipeline removal**

In `tests/test_cli.py`, `tests/test_cli_runtime.py`, and `tests/test_analysis_pipeline.py`:

- replace subset-selection tests with assertions that `--sonara-outputs` is rejected as an unknown option before a database manager is opened;
- assert both `analyze --help` and `analyze-pipeline --help` omit the option;
- assert the manager receives no `sonara_outputs` kwarg;
- assert SONARA status text may still report the canonical four outputs;
- assert the pipeline child job receives no output list and fixed stage order remains SONARA → ML → CLASSIFIERS.

- [ ] **Step 4: Run the focused backend contract tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_config.py tests/test_api_analysis_jobs.py tests/test_analysis_pipeline.py tests/test_cli.py tests/test_cli_runtime.py --override-ini addopts=
```

Expected: failures because schemas, manager/config signatures, pipeline settings, and CLI options still accept output selection.

- [ ] **Step 5: Make configuration canonical**

In `analysis_config.py`:

- remove `DEFAULT_SONARA_OUTPUTS`, the local output-normalizer alias, `SONARA_OUTPUTS`, and `normalize_sonara_outputs()`;
- remove `sonara_outputs` from `build_analysis_job_config()`;
- assign:

```python
normalized_sonara_outputs = (
    SONARA_OUTPUT_KINDS if "sonara" in normalized_models else ()
)
```

Do not change `normalize_analysis_models()` or the direct-job mutual-exclusion rules.

- [ ] **Step 6: Remove public request fields**

In `api_schemas.py`:

- delete `AnalysisJobRequest.sonara_outputs`;
- delete `SonaraPipelineSettings.outputs`;
- retain the existing `ConfigDict(extra="forbid")` behavior so stale fields fail with `422`.

In `api_routes_analysis.py`:

- stop passing output selections to config or the manager;
- build the pipeline's SONARA dict as `{"batch_size": request.sonara.batch_size}`.

- [ ] **Step 7: Remove internal job and pipeline overrides**

In `analysis_jobs.py`, remove `sonara_outputs` from `create_job()` and its call to `build_analysis_job_config()`. Retain the canonical list copied from config into status.

In `analysis_pipeline.py`, remove `payload.sonara["outputs"]`; pass only the SONARA batch size to the child analysis job.

- [ ] **Step 8: Remove both CLI options**

In `cli.py`:

- remove the `--sonara-outputs` parameters from `analyze` and `analyze-pipeline`;
- remove CSV parsing and all selection forwarding;
- retain canonical output reporting from config/status where it is useful for observability.

- [ ] **Step 9: Run the focused tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_config.py tests/test_api_analysis_jobs.py tests/test_analysis_pipeline.py tests/test_cli.py tests/test_cli_runtime.py --override-ini addopts=
```

Expected: all selected tests pass.

- [ ] **Step 10: Inspect and commit the task**

```powershell
git diff --check -- tests/test_analysis_config.py tests/test_api_analysis_jobs.py tests/test_analysis_pipeline.py tests/test_cli.py tests/test_cli_runtime.py src/dj_track_similarity/analysis_config.py src/dj_track_similarity/api_schemas.py src/dj_track_similarity/api_routes_analysis.py src/dj_track_similarity/analysis_jobs.py src/dj_track_similarity/analysis_pipeline.py src/dj_track_similarity/cli.py
git diff -- tests/test_analysis_config.py tests/test_api_analysis_jobs.py tests/test_analysis_pipeline.py tests/test_cli.py tests/test_cli_runtime.py src/dj_track_similarity/analysis_config.py src/dj_track_similarity/api_schemas.py src/dj_track_similarity/api_routes_analysis.py src/dj_track_similarity/analysis_jobs.py src/dj_track_similarity/analysis_pipeline.py src/dj_track_similarity/cli.py
git add -- tests/test_analysis_config.py tests/test_api_analysis_jobs.py tests/test_analysis_pipeline.py tests/test_cli.py tests/test_cli_runtime.py src/dj_track_similarity/analysis_config.py src/dj_track_similarity/api_schemas.py src/dj_track_similarity/api_routes_analysis.py src/dj_track_similarity/analysis_jobs.py src/dj_track_similarity/analysis_pipeline.py src/dj_track_similarity/cli.py
git commit -m "Make SONARA output selection fixed"
```

---

### Task 2: Make runtime conversion and repository writes indivisible

**Files:**
- Modify: `tests/test_analysis_orchestration.py`
- Modify: `tests/test_sonara_features.py`
- Modify: `tests/test_sonara_storage.py`
- Modify: `tests/test_sonara_native_batch.py`
- Modify: `tests/test_analysis_repository.py`
- Modify compatible SONARA fixtures in:
  - `tests/test_api_reference_compare.py`
  - `tests/test_api_sonara_search.py`
  - `tests/test_break_energy.py`
  - `tests/test_evaluation_cli.py`
  - `tests/test_evaluation_seed_sampling.py`
  - `tests/test_reference_compare_runtime.py`
  - `tests/test_sonara_similarity.py`
  - `tests/test_sonara_similarity_runtime.py`
- Modify: `src/dj_track_similarity/sonara_runtime.py`
- Modify: `src/dj_track_similarity/analysis_model_runners.py`
- Modify: `src/dj_track_similarity/sonara_features.py`
- Modify: `src/dj_track_similarity/sonara_storage.py`
- Modify: `src/dj_track_similarity/analysis_models.py`
- Modify: `src/dj_track_similarity/db_analysis.py`

**Interfaces:**
- `SonaraModelRunner()` has no output-selection parameter and declares all four outputs for both candidate readiness and active registration.
- `default_model_runners(model, device, inference_batch_size, top_k)` has four arguments.
- `analyze_and_store_sonara_batch()` and `prepare_sonara_write()` have no `outputs` parameter.
- `SonaraWrite.timeline`, `.similarity_embedding`, and `.fingerprint` are non-optional.
- All four nested outputs share `core.analyzed_at`.
- `SonaraWrite.outputs` is always the canonical four-item tuple.
- `save_sonara_results()` always writes Core and all three artifacts through the existing coordinated per-track savepoints.

- [ ] **Step 1: Specify runner and conversion behavior**

Update `tests/test_analysis_orchestration.py`, `tests/test_sonara_features.py`, and `tests/test_sonara_storage.py` so they require:

```python
assert runner.candidate_outputs == analysis_outputs_for_sonara_runtime()
assert runner.active_outputs == analysis_outputs_for_sonara_runtime()
assert write.outputs == (
    AnalysisOutput("sonara", "core"),
    AnalysisOutput("sonara", "timeline"),
    AnalysisOutput("sonara", "embedding"),
    AnalysisOutput("sonara", "fingerprint"),
)
```

Delete tests asserting that selection changes persistence. Add parameterized conversion failures in which Timeline, embedding, or fingerprint data is absent/invalid. Assert the repository is not called for the failed track and another valid track in the same batch can still succeed.

- [ ] **Step 2: Specify one timestamp and transaction behavior**

In `tests/test_analysis_repository.py`:

- construct a full `SonaraWrite`;
- assert Core, Timeline, SONARA embedding, and fingerprint rows are all persisted into a temporary Core/Artifacts bundle;
- assert `written_outputs` contains all four canonical outputs;
- assert mismatched timestamps are rejected when constructing `SonaraWrite`;
- inject an artifact-upsert failure inside the existing transaction seam and assert no Core result is published for that track.

Use temporary databases only.

- [ ] **Step 3: Run the focused runtime tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_orchestration.py tests/test_sonara_features.py tests/test_sonara_storage.py tests/test_sonara_native_batch.py tests/test_analysis_repository.py --override-ini addopts=
```

Expected: failures because subset parameters and optional `SonaraWrite` fields still exist.

- [ ] **Step 4: Keep one canonical output tuple**

In `sonara_runtime.py`:

- retain `SONARA_OUTPUT_KINDS` and feature mapping;
- remove `DEFAULT_SONARA_OUTPUTS` and `normalize_sonara_outputs()`;
- make `analysis_outputs_for_sonara_runtime()` derive its order from `SONARA_OUTPUT_KINDS`.

- [ ] **Step 5: Remove selection from runner construction**

In `analysis_model_runners.py`:

```python
RunnerFactory = Callable[[str, str, int, int], AnalysisModelRunner]

class SonaraModelRunner:
    def __init__(self, *, sonara_module: Any | None = None) -> None:
        ...
```

- set `candidate_outputs` and `active_outputs` to the complete canonical tuple;
- remove `self.outputs`;
- call `analyze_and_store_sonara_batch()` without an output list;
- remove the fifth argument from `default_model_runners()`.

Update `analysis_jobs.py` only if Task 1 left a factory call that still passes a fifth argument.

- [ ] **Step 6: Convert all four outputs before a write**

In `sonara_features.py`, remove `outputs` and selection normalization. Generate one timestamp per successful analyzer result and pass it to:

```python
prepare_sonara_write(candidate, analysis, analyzed_at=analyzed_at)
```

In `sonara_storage.py`, remove `outputs` and always build Core, canonical Timeline, 48D SONARA embedding, and fingerprint. A missing or invalid member raises before repository persistence.

- [ ] **Step 7: Enforce the non-optional bundle model**

In `analysis_models.py`, define:

```python
@dataclass(frozen=True)
class SonaraWrite:
    target: AnalysisTarget
    core: SonaraRow
    timeline: SonaraTimelineOutput
    similarity_embedding: EmbeddingOutput
    fingerprint: SonaraFingerprintOutput
```

In `__post_init__()`:

- validate target UUID/generation consistency for every member;
- require `similarity_embedding.family == "sonara"`;
- require all four non-empty `analyzed_at` strings to be exactly equal.

Return all four outputs in canonical order without inspecting nullable fields.

- [ ] **Step 8: Persist all members through the coordinated write**

In `db_analysis.py`:

- remove nullable early returns for SONARA Timeline and fingerprint upserts;
- remove `needs_artifacts`;
- always enlist the Artifacts connection for non-empty SONARA writes;
- write Timeline, SONARA embedding, and fingerprint before the Core commit-last publication signal;
- preserve the existing coordinated savepoints and stale identity checks.

Do not add a schema migration.

- [ ] **Step 9: Update compatible test fixtures**

Every `SonaraWrite(` under the listed eight compatibility test files must construct a valid complete bundle with one timestamp. Keep each test's behavioral focus unchanged; do not weaken assertions or switch to real audio/data.

- [ ] **Step 10: Run focused and compatibility tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_orchestration.py tests/test_sonara_features.py tests/test_sonara_storage.py tests/test_sonara_native_batch.py tests/test_analysis_repository.py --override-ini addopts=
.\.venv\Scripts\python.exe -m pytest tests/test_api_reference_compare.py tests/test_api_sonara_search.py tests/test_break_energy.py tests/test_evaluation_cli.py tests/test_evaluation_seed_sampling.py tests/test_reference_compare_runtime.py tests/test_sonara_similarity.py tests/test_sonara_similarity_runtime.py --override-ini addopts=
```

Expected: all selected tests pass.

- [ ] **Step 11: Inspect and commit the task**

```powershell
git diff --check -- src/dj_track_similarity tests
git diff --stat -- src/dj_track_similarity tests
git add -- src/dj_track_similarity/sonara_runtime.py src/dj_track_similarity/analysis_model_runners.py src/dj_track_similarity/sonara_features.py src/dj_track_similarity/sonara_storage.py src/dj_track_similarity/analysis_models.py src/dj_track_similarity/db_analysis.py src/dj_track_similarity/analysis_jobs.py tests/test_analysis_orchestration.py tests/test_sonara_features.py tests/test_sonara_storage.py tests/test_sonara_native_batch.py tests/test_analysis_repository.py tests/test_api_reference_compare.py tests/test_api_sonara_search.py tests/test_break_energy.py tests/test_evaluation_cli.py tests/test_evaluation_seed_sampling.py tests/test_reference_compare_runtime.py tests/test_sonara_similarity.py tests/test_sonara_similarity_runtime.py
git commit -m "Persist complete SONARA result bundles"
```

---

### Task 3: Add metadata-only complete-bundle projections

**Files:**
- Modify: `tests/test_artifact_identity.py`
- Modify: `tests/test_library_repository.py`
- Modify: `tests/test_api_tracks.py`
- Modify: `tests/test_classifier_productionization.py`
- Modify: `src/dj_track_similarity/sonara_runtime.py`
- Modify: `src/dj_track_similarity/sonara_storage.py`
- Modify: `src/dj_track_similarity/db_artifacts.py`
- Modify: `src/dj_track_similarity/db_library_queries.py`
- Modify: `src/dj_track_similarity/db_analysis_candidates.py`
- Modify: `src/dj_track_similarity/library_models.py`
- Modify: `src/dj_track_similarity/api_schemas.py`

**Interfaces:**
- One ordered `SONARA_TIMELINE_FIELDS` tuple is shared by conversion validation and metadata summaries.
- Lightweight read validation uses identity, metadata, timestamp, and `length(blob)`; it never returns raw BLOB/JSON values.
- Full payload validators remain for writes and explicit consumer paths.
- `TrackDetail.optional_outputs` is `OptionalOutputs | None` with:

```text
analyzed_at
timeline.fields
embedding.dim
embedding.normalization
fingerprint.ready == true
```

- The summary exists only when current Core and all three current artifacts are metadata-valid and have the same timestamp.
- An incomplete result makes SONARA Core/detail and all public SONARA coverage flags unavailable together.
- The explicit Timeline endpoint still loads and fully validates Timeline JSON on demand.

- [ ] **Step 1: Specify metadata validator boundaries**

In `tests/test_artifact_identity.py`, add focused unit tests for new metadata validators:

- embedding accepts correct current identity, expected family dimension/normalization, non-empty timestamp, and `payload_bytes == dim * 4`;
- fingerprint accepts current identity, positive internal version/word count, `little` byte order, non-empty timestamp, and `payload_bytes == word_count * 4`;
- wrong identity, generation, length, normalization, byte order, or empty timestamp fails closed;
- existing full-payload reader tests remain unchanged.

- [ ] **Step 2: Specify the nullable nested repository summary**

In `tests/test_library_repository.py`, change the SONARA detail expectation to:

```python
assert detail.optional_outputs == OptionalOutputs(
    analyzed_at=analyzed_at,
    timeline=SonaraTimelineSummary(fields=SONARA_TIMELINE_FIELDS),
    embedding=SonaraEmbeddingSummary(dim=48, normalization="l2"),
    fingerprint=SonaraFingerprintSummary(),
)
```

Add parameterized cases for:

- a missing Timeline, embedding, or fingerprint row;
- wrong UUID or generation;
- wrong embedding dimension/byte length;
- invalid fingerprint metadata/byte length;
- any one artifact timestamp differing from Core.

For every case assert:

```python
assert detail.optional_outputs is None
assert detail.sonara_core is None
assert detail.analysis_coverage.sonara_core is False
assert detail.analysis_coverage.sonara_timeline is False
assert detail.analysis_coverage.sonara_embedding is False
assert detail.analysis_coverage.sonara_fingerprint is False
```

Also assert `detail.embeddings` contains no SONARA row and `library_summary().sonara` counts complete bundles only.

- [ ] **Step 3: Prove list/detail do not hydrate heavy values**

Capture SQL with `sqlite3.Connection.set_trace_callback()` around Library page and detail calls. Normalize whitespace/case, then assert the relevant queries:

- do not project `payload_json`;
- do not project a bare `embedding_blob` or `fingerprint_blob`;
- may use only `length(stored.embedding_blob) AS payload_bytes` and `length(stored.fingerprint_blob) AS payload_bytes`.

Keep a separate test proving the explicit Timeline loader still selects, parses, and returns the complete JSON payload.

- [ ] **Step 4: Specify the API response**

In `tests/test_api_tracks.py`, expect exact nested JSON:

```python
"optional_outputs": {
    "analyzed_at": analyzed_at,
    "timeline": {"fields": list(SONARA_TIMELINE_FIELDS)},
    "embedding": {"dim": 48, "normalization": "l2"},
    "fingerprint": {"ready": True},
}
```

Assert the serialized response contains none of:

```text
payload_json
embedding_blob
fingerprint_blob
fingerprint_version
word_count
byte_order
```

Update dummy `OptionalOutputs` builders in `tests/test_classifier_productionization.py`.

- [ ] **Step 5: Run repository/API tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_identity.py tests/test_library_repository.py tests/test_api_tracks.py tests/test_classifier_productionization.py --override-ini addopts=
```

Expected: failures because current queries load payloads and the response is a flat availability structure.

- [ ] **Step 6: Centralize canonical Timeline fields**

Define an ordered tuple in `sonara_runtime.py`:

```python
SONARA_TIMELINE_FIELDS = (
    "beats",
    "onset_frames",
    "chord_sequence",
    "chord_events",
    "tempo_curve",
    "downbeats",
    "energy_curve",
    "segments",
    "loudness_curve",
)
```

Import it from `sonara_storage.py` and `db_artifacts.py`. Remove the duplicate tuple/frozenset while preserving exact-key Timeline validation.

- [ ] **Step 7: Add lightweight row validators**

In `db_artifacts.py`, add metadata-only validators that accept `ArtifactTrackIdentity`, row metadata, byte length, and analyzed timestamp. Reuse the same identity and family dimension rules as the full validators, but do not accept or decode payload values.

Keep the existing full `validate_embedding_row_payload()`, Timeline payload validator, and fingerprint payload validator for write and explicit consumer paths.

- [ ] **Step 8: Replace Library hydration queries**

In `db_library_queries.py`:

- split metadata-only selectors from explicit full-payload loaders;
- Timeline metadata selects only identity/generation/analyzed_at;
- embedding metadata selects identity/generation/dim/normalization/analyzed_at plus `length(embedding_blob) AS payload_bytes`;
- fingerprint metadata selects identity/generation/version/word_count/byte_order/analyzed_at plus `length(fingerprint_blob) AS payload_bytes`;
- make valid Core lookup retain each row's `analyzed_at`;
- build the bundle only when all four timestamps match;
- set the four public SONARA coverage flags from one complete-bundle predicate;
- omit `sonara_core` and `optional_outputs` together when incomplete;
- omit SONARA from the generic embedding summaries.

Keep `load_sonara_timeline()` on a dedicated full-row query using full payload validation.

- [ ] **Step 9: Make readiness metadata-only**

Refactor `db_analysis_candidates.py::_valid_artifact_rows()` to use the same lightweight metadata selectors/validators. Candidate readiness must not load every existing SONARA BLOB/Timeline payload before scheduling analysis. Missing/incomplete metadata still schedules the complete SONARA bundle for reanalysis.

- [ ] **Step 10: Add typed domain and API summaries**

In `library_models.py`:

```python
@dataclass(frozen=True)
class SonaraTimelineSummary:
    fields: tuple[str, ...]

@dataclass(frozen=True)
class SonaraEmbeddingSummary:
    dim: int
    normalization: str

@dataclass(frozen=True)
class SonaraFingerprintSummary:
    ready: Literal[True] = True

@dataclass(frozen=True)
class OptionalOutputs:
    analyzed_at: str
    timeline: SonaraTimelineSummary
    embedding: SonaraEmbeddingSummary
    fingerprint: SonaraFingerprintSummary
```

Mirror those nested models in `api_schemas.py`, using `Literal[True]` for fingerprint readiness and `OptionalOutputsResponse | None` on detail.

- [ ] **Step 11: Run focused tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_identity.py tests/test_library_repository.py tests/test_api_tracks.py tests/test_classifier_productionization.py --override-ini addopts=
```

Expected: all selected tests pass.

- [ ] **Step 12: Inspect and commit the task**

```powershell
git diff --check -- src/dj_track_similarity tests
git diff --stat -- src/dj_track_similarity tests
git add -- src/dj_track_similarity/sonara_runtime.py src/dj_track_similarity/sonara_storage.py src/dj_track_similarity/db_artifacts.py src/dj_track_similarity/db_library_queries.py src/dj_track_similarity/db_analysis_candidates.py src/dj_track_similarity/library_models.py src/dj_track_similarity/api_schemas.py tests/test_artifact_identity.py tests/test_library_repository.py tests/test_api_tracks.py tests/test_classifier_productionization.py
git commit -m "Load SONARA metadata without heavy artifacts"
```

---

### Task 4: Remove FULL and SONARA output controls from the frontend

**Files:**
- Add: `frontend/tests/analysisSelection.test.mjs`
- Modify: `frontend/tests/buttonClasses.test.mjs`
- Modify: `frontend/tests/apiContract.test.mjs`
- Modify: `frontend/src/analysisSelection.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/LibraryPanel.tsx`
- Modify: `frontend/src/apiClient.ts`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- `toggleAnalysisSelection(current, model)` is a pure mode-selection helper.
- Library UI renders model selection only; SONARA's four outputs are a non-interactive compact statement.
- Frontend analysis-job and pipeline request payloads contain no output-selection field.
- Job-status `sonara_outputs` and the `SonaraOutput` response type remain.

- [ ] **Step 1: Specify mode-selection behavior as a pure test**

Create `frontend/tests/analysisSelection.test.mjs` covering:

- the last SONARA, CLASSIFIERS, or sole ML selection cannot be removed;
- selecting SONARA yields only SONARA;
- selecting CLASSIFIERS yields only CLASSIFIERS;
- selecting an ML model from either special mode removes that special mode;
- several ML models may coexist and remain in `mlAnalysisModelOrder`.

- [ ] **Step 2: Invert the source-contract tests**

In `frontend/tests/buttonClasses.test.mjs`, require absence of:

```text
FULL
analysis-full-check
analysis-models-heading-with-full
toggleAllAnalysisModels
analysisSelectionOrder
sonaraOutputs
toggleSonaraOutput
sonara-output-options
```

Require a non-checkbox `.sonara-output-summary` containing `Core · Timeline · Embedding · Fingerprint`. Preserve tests for separate SONARA and CLASSIFIERS rows and selectable ML rows.

- [ ] **Step 3: Specify payloads without output lists**

In `frontend/tests/apiContract.test.mjs`, assert a SONARA job body contains only models, limit, and `sonara_batch_size`, and a pipeline body contains:

```json
"sonara": {"batch_size": 8}
```

Assert neither request has `sonara_outputs` or `sonara.outputs`.

- [ ] **Step 4: Run focused frontend tests and verify RED**

From `frontend/`:

```powershell
node --test tests/analysisSelection.test.mjs tests/buttonClasses.test.mjs tests/apiContract.test.mjs
```

Expected: failures because FULL, output checkboxes/state, and request fields still exist.

- [ ] **Step 5: Implement the pure selection helper**

In `analysisSelection.ts`, keep:

- `AnalysisSelection`;
- `mlAnalysisModelOrder`;
- `defaultAnalysisSelections = ["sonara"]`;
- `isAudioAnalysisModel`.

Remove `audioAnalysisModelOrder` and `analysisSelectionOrder`. Add:

```ts
export function toggleAnalysisSelection(
  current: AnalysisSelection[],
  model: AnalysisSelection
): AnalysisSelection[] {
  // special modes are exclusive; ML modes can coexist in canonical order;
  // an existing final selection cannot be removed.
}
```

- [ ] **Step 6: Remove frontend state and handlers**

In `App.tsx`:

- remove the `SonaraOutput` import, `sonaraOutputs` state, `toggleAllAnalysisModels()`, and `toggleSonaraOutput()`;
- delegate `toggleAnalysisModel()` to `toggleAnalysisSelection()`;
- use a fixed log summary for all four SONARA outputs;
- send `sonara: {batch_size: sonaraBatchSize}`;
- remove obsolete `LibraryPanel` props.

In `apiClient.ts`:

- remove `DEFAULT_SONARA_OUTPUTS`;
- remove `AnalysisJobStartPayload.sonara_outputs`;
- remove the default output list from direct jobs;
- type pipeline SONARA settings as `{batch_size: number}`.

Do not remove response/status output types.

- [ ] **Step 7: Replace controls with static contract text**

In `LibraryPanel.tsx`:

- remove FULL and the four output checkboxes;
- retain existing model checkboxes;
- add:

```tsx
<div className="sonara-output-summary">
  <span>Всегда:</span>
  <strong>Core · Timeline · Embedding · Fingerprint</strong>
</div>
```

Remove checkbox-specific CSS and style this summary with existing surface, border, and muted-text tokens.

- [ ] **Step 8: Run focused tests, strict typecheck, and build**

From `frontend/`:

```powershell
node --test tests/analysisSelection.test.mjs tests/buttonClasses.test.mjs tests/apiContract.test.mjs
npm run typecheck
npm run build
```

Expected: all commands exit `0`.

- [ ] **Step 9: Inspect and commit the task**

```powershell
git diff --check -- frontend
git diff -- frontend/src/analysisSelection.ts frontend/src/App.tsx frontend/src/LibraryPanel.tsx frontend/src/apiClient.ts frontend/src/styles.css frontend/tests/analysisSelection.test.mjs frontend/tests/buttonClasses.test.mjs frontend/tests/apiContract.test.mjs
git add -- frontend/src/analysisSelection.ts frontend/src/App.tsx frontend/src/LibraryPanel.tsx frontend/src/apiClient.ts frontend/src/styles.css frontend/tests/analysisSelection.test.mjs frontend/tests/buttonClasses.test.mjs frontend/tests/apiContract.test.mjs
git commit -m "Remove SONARA output controls"
```

---

### Task 5: Present complete SONARA summaries in one metadata block

**Files:**
- Modify: `frontend/tests/metadataReference.test.mjs`
- Modify: `frontend/tests/sonaraDisplay.test.mjs`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/TrackMetadataDialog.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- `TrackDetail.optional_outputs` mirrors the backend's nullable nested complete summary.
- `metadataDialogModel()` exposes ordered SONARA categories consumed by rendering tests and the dialog.
- Timeline and Embedding use badge categories; Fingerprint uses a check category; Analysis uses a fields category.
- Generic embedding summaries exclude `analysis_family === "sonara"`.

- [ ] **Step 1: Update the frontend detail fixture**

Use:

```js
optional_outputs: {
  analyzed_at: "2026-07-24T10:05:00Z",
  timeline: { fields: ["beats", "energy_curve"] },
  embedding: { dim: 48, normalization: "l2" },
  fingerprint: { ready: true },
}
```

Set `sonara_core.analyzed_at` to a deliberately different timestamp so the test proves the displayed value comes from the complete bundle.

- [ ] **Step 2: Specify ordered categories and content**

In `frontend/tests/metadataReference.test.mjs`, assert the SONARA category tail is:

```js
[
  "Vocalness",
  "Aggression",
  "Vector summaries",
  "Timeline",
  "Embedding",
  "Fingerprint",
  "Analysis",
]
```

Also assert:

- Timeline badge labels are `beats` and `energy_curve`;
- Embedding badges are `48D` and `L2`;
- Fingerprint is a check category with `ariaLabel === "Fingerprint ready"`;
- exactly one field is labeled `Analyzed`;
- it formats `optional_outputs.analyzed_at`;
- a null summary produces no categories and one SONARA-level unavailable state;
- a SONARA row in `track.embeddings` does not appear in generic embedding summaries.

- [ ] **Step 3: Specify safe rendering**

In `frontend/tests/sonaraDisplay.test.mjs`, require:

- block title `SONARA`, not `SONARA · Core`;
- nested `timeline.fields`, `embedding.dim`, `embedding.normalization`, and `fingerprint.ready`;
- a Check icon with accessible label `Fingerprint ready`;
- no visible `Ready`;
- no legacy availability booleans or old presence blocks;
- no `fingerprint_version`, `word_count`, `byte_order`, raw payload/BLOB names, `api.sonaraTimeline`, or payload serialization.

- [ ] **Step 4: Run metadata tests and verify RED**

From `frontend/`:

```powershell
node --test tests/metadataReference.test.mjs tests/sonaraDisplay.test.mjs
```

Expected: failures because the frontend still models three independent availability blocks and sources `Analyzed` from Core.

- [ ] **Step 5: Mirror the nested API type**

In `api.ts`:

```ts
export type SonaraOptionalOutputsSummary = {
  analyzed_at: string;
  timeline: { fields: string[] };
  embedding: { dim: number; normalization: string };
  fingerprint: { ready: true };
};
```

Use `SonaraOptionalOutputsSummary | null` in `TrackDetail`. Widen `EmbeddingSummary.analysis_family` only as needed to represent the backend SONARA row, then filter it explicitly in the presentation layer.

- [ ] **Step 6: Build one SONARA category model**

In `TrackMetadataDialog.tsx`:

- remove the old `Analysis` descriptor from `sonaraCoreFeatureGroups`;
- add a discriminated category model for `fields`, `badges`, and `check`;
- return no SONARA categories unless both `sonara_core` and `optional_outputs` exist;
- append Timeline, Embedding, Fingerprint, Analysis after all Core categories;
- make Timeline field names code-style badges;
- make Embedding badges `${dim}D` and `normalization.toUpperCase()`;
- make Fingerprint a Check icon with `role="img"` and `aria-label="Fingerprint ready"`, with no visible status text;
- build Analysis from `optional_outputs.analyzed_at`;
- rename the block heading to `SONARA`;
- delete `TimelinePresenceBlock` and `OutputPresenceBlock`;
- filter SONARA out of `readableEmbeddings()`;
- never call the Timeline endpoint from the dialog.

- [ ] **Step 7: Add shared badge and success styles**

Reuse `.sonara-feature-group` as the category shell. Add shared summary-badge classes. Add a `--success-text` token to both themes and apply it to the Fingerprint check so it is visibly green in light and dark themes; keep the accessible label as the non-color signal.

Retain `.sonara-storage-block` if the generic embedding section still consumes it.

- [ ] **Step 8: Run focused tests and strict frontend verification**

From `frontend/`:

```powershell
node --test tests/metadataReference.test.mjs tests/sonaraDisplay.test.mjs
npm run typecheck
npm run build
```

Expected: all commands exit `0`.

- [ ] **Step 9: Inspect and commit the task**

```powershell
git diff --check -- frontend
git diff -- frontend/src/api.ts frontend/src/TrackMetadataDialog.tsx frontend/src/styles.css frontend/tests/metadataReference.test.mjs frontend/tests/sonaraDisplay.test.mjs
git add -- frontend/src/api.ts frontend/src/TrackMetadataDialog.tsx frontend/src/styles.css frontend/tests/metadataReference.test.mjs frontend/tests/sonaraDisplay.test.mjs
git commit -m "Show complete SONARA metadata summaries"
```

---

### Task 6: Verify the integrated contract and remove obsolete residue

**Files:**
- Modify only if verification reveals contract residue:
  - `src/dj_track_similarity/**`
  - `tests/**`
  - `frontend/src/**`
  - `frontend/tests/**`

**Interfaces:**
- No callable request, CLI, manager, runner, batch, or converter interface accepts an output subset.
- No Library/detail/readiness query materializes heavy SONARA artifacts.
- Job status still exposes all four output identifiers.
- The complete nested metadata contract agrees across Python models, Pydantic schemas, TypeScript types, and React rendering.

- [ ] **Step 1: Run sentinel searches**

```powershell
rg -n "DEFAULT_SONARA_OUTPUTS|normalize_sonara_outputs|sonara_outputs: Sequence|sonara_outputs: str|--sonara-outputs|toggleAllAnalysisModels|toggleSonaraOutput|sonara-output-options|analysis-full-check|SONARA · Core|timeline_fields|sonara_embedding_available|audio_fingerprint_available" src tests frontend/src frontend/tests
```

Review every match. Permitted matches are limited to canonical `AnalysisJobStatus.sonara_outputs`, response types/status rendering, and tests explicitly proving obsolete fields are rejected or absent.

- [ ] **Step 2: Run the integrated backend suite for touched boundaries**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_config.py tests/test_api_analysis_jobs.py tests/test_analysis_pipeline.py tests/test_analysis_orchestration.py tests/test_sonara_features.py tests/test_sonara_storage.py tests/test_sonara_native_batch.py tests/test_analysis_repository.py tests/test_artifact_identity.py tests/test_library_repository.py tests/test_api_tracks.py tests/test_cli.py tests/test_cli_runtime.py tests/test_analysis_sonara_preflight.py tests/test_classifier_productionization.py tests/test_api_reference_compare.py tests/test_api_sonara_search.py tests/test_break_energy.py tests/test_evaluation_cli.py tests/test_evaluation_seed_sampling.py tests/test_reference_compare_runtime.py tests/test_sonara_similarity.py tests/test_sonara_similarity_runtime.py --override-ini addopts=
```

Expected: all selected tests pass.

- [ ] **Step 3: Run the complete frontend test contract**

From `frontend/`:

```powershell
npm test
npm run typecheck
npm run build
```

Expected: all commands exit `0`.

- [ ] **Step 4: Verify no heavy payload crosses the API boundary**

Inspect the exact Pydantic/TypeScript response shapes and SQL trace tests. Confirm:

- no response model contains Timeline values, an embedding vector/BLOB, or fingerprint words/BLOB;
- Timeline values are available only through the explicit existing endpoint;
- no fingerprint endpoint or duplicate matcher was introduced;
- Core and Artifacts identity still share `catalog_uuid` validation.

- [ ] **Step 5: Inspect the whole branch diff**

```powershell
git diff --check
git status --short
git diff --stat
git diff
```

Confirm `database/` remains untouched/untracked and no generated `frontend/dist`, databases, logs, caches, or virtual environments are staged.

- [ ] **Step 6: Commit only a needed integration fix**

If Steps 1–5 required a real code/test correction, stage only those exact files and commit:

```powershell
git commit -m "Complete SONARA all-output integration"
```

If no correction was needed, do not create an empty commit.
