# Manual Database Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide an explicit read-only validation run for the current database bundle through CLI, API, and UI.

**Architecture:** A `DatabaseValidator` streams Core rows through validators and produces structured findings. `DatabaseValidationJobManager` runs it in one background thread for the API and exposes the same status/event shape as the existing jobs; the CLI runs it synchronously. The UI polls the job and shows it in the existing log dialog.

**Tech Stack:** Python 3, SQLite, NumPy, Typer, FastAPI, Pydantic, React, TypeScript.

## Global Constraints

- Validation is explicit and read-only: no writes to SQLite, audio files, tags, model outputs, or startup counters.
- Do not hash or compare audio contents, size, or mtime; only require the stored path to exist as a file.
- Iterate each cursor row sequentially in one thread; do not use aggregate coverage queries or recalculate model data.
- Log an `OK`, `WARNING`, or `ERROR` finding for every validated entity.
- Existing schema and model specifications are the source of truth; an absent optional analysis row is not an error.

---

### Task 1: Validation domain model and streaming Core validator

**Files:**
- Create: `src/dj_track_similarity/database_validation.py`
- Create: `tests/test_database_validation.py`

**Interfaces:**
- Produces `ValidationFinding`, `DatabaseValidationReport`, and `DatabaseValidator(database: LibraryDatabase)`.
- `DatabaseValidator.run(emit: Callable[[ValidationFinding], None], cancelled: Callable[[], bool]) -> DatabaseValidationReport` only reads the selected Core database.

- [ ] **Step 1: Write failing tests** for a valid track, a missing path, an embedding with mismatched UUID/dimension/normalization/blob, a non-finite vector, and an audit that does not alter the Core file contents.
- [ ] **Step 2: Run** `./.venv/Scripts/python.exe -m pytest tests/test_database_validation.py -q` and confirm the tests fail because the module is missing.
- [ ] **Step 3: Implement** frozen finding/report models; sequential `tracks` and embedding cursors; canonical `validate_embedding_row_payload`; `PRAGMA integrity_check` and streamed `PRAGMA foreign_key_check`; structured codes and levels.
- [ ] **Step 4: Run** `./.venv/Scripts/python.exe -m pytest tests/test_database_validation.py -q` and confirm all Task 1 tests pass.

### Task 2: Job manager, API state, routes, and CLI

**Files:**
- Create: `src/dj_track_similarity/database_validation_jobs.py`
- Modify: `src/dj_track_similarity/api_state.py`
- Modify: `src/dj_track_similarity/api_routes_database.py`
- Modify: `src/dj_track_similarity/api_schemas.py`
- Modify: `src/dj_track_similarity/cli.py`
- Create: `tests/test_database_validation_jobs.py`
- Modify: `tests/test_api_database_selection.py`

**Interfaces:**
- Produces `DatabaseValidationJobManager.start()`, `.get(job_id)`, `.latest()`, and `.cancel(job_id)`.
- API exposes `POST /api/database/validation/jobs`, `GET /api/database/validation/jobs/latest`, `GET /api/database/validation/jobs/{job_id}`, and `POST /api/database/validation/jobs/{job_id}/cancel`.
- CLI adds `dj-sim validate-database --db PATH [--report PATH]`.

- [ ] **Step 1: Write failing API/job/CLI tests** that start a job, poll a completed status, block a concurrent database operation, return a validation error in the event stream, and write an optional JSON report without database mutation.
- [ ] **Step 2: Run** `./.venv/Scripts/python.exe -m pytest tests/test_database_validation_jobs.py tests/test_api_database_selection.py -q` and confirm the new tests fail because endpoints and manager are absent.
- [ ] **Step 3: Implement** a one-thread manager using `JobStore`, logger-backed event emission, bounded event tail, AppDatabaseState exclusivity, response schemas/routes, and the synchronous Typer command.
- [ ] **Step 4: Run** `./.venv/Scripts/python.exe -m pytest tests/test_database_validation_jobs.py tests/test_api_database_selection.py -q` and confirm all Task 2 tests pass.

### Task 3: Frontend trigger, polling, and log presentation

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/LibraryPanel.tsx`
- Modify: `frontend/src/dialogs.tsx`
- Modify: `frontend/src/jobUi.tsx`
- Modify: `frontend/src/styles.css`
- Test: existing focused frontend job/UI test file or a new `frontend/src/databaseValidation.test.tsx`

**Interfaces:**
- `api.startDatabaseValidation()`, `api.databaseValidationJob(id)`, and `api.cancelDatabaseValidationJob(id)` return the API job status.
- `LibraryPanel` receives `onValidateDatabase`, validation state, and disabled state.

- [ ] **Step 1: Write a failing frontend test** that clicks `Проверить БД`, invokes the API start operation, and renders validation `ERROR` events in the log selection.
- [ ] **Step 2: Run** the focused frontend test and confirm failure because the action/status type is absent.
- [ ] **Step 3: Implement** API typing/calls, App polling/cancellation/log-kind wiring, the non-destructive library button, and minimal matching CSS.
- [ ] **Step 4: Run** the focused frontend test and `npm run typecheck` from `frontend/` and confirm success.

### Task 4: Integration verification and documentation

**Files:**
- Modify: `README.md` or `docs/dj-track-similarity/` only if a user-facing command/API reference is maintained there.

- [ ] **Step 1: Add/update focused documentation** for the explicit command, read-only semantics, and report option.
- [ ] **Step 2: Run** the focused backend tests from Tasks 1–2, the frontend typecheck, and `git diff --check` for all changed files.
- [ ] **Step 3: Inspect** the final diff to verify it neither changes ordinary loading paths nor stages generated/local state.
