# Managed Server Shutdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the top-bar shutdown action stop all project-managed services from the normal Windows launcher without terminating unrelated listeners.

**Architecture:** The backend route stops the existing managed Rhythm Lab target before it schedules its own termination. The launcher remains the owner of the Vite process and replaces its single-process cleanup with Windows process-tree cleanup, so npm/cmd/Node descendants cannot keep port 5173 open after the backend exits.

**Tech Stack:** Python 3.10, FastAPI background tasks, `subprocess`, Windows `taskkill`, React typed API client (unchanged).

## Global Constraints

- Work only with processes owned by the project launcher; never scan ports and kill arbitrary listeners.
- Keep the explicit shutdown action header and the existing frontend request/response type unchanged.
- Stop Rhythm Lab only through its existing managed-stop callable; an unmanaged listener on 8777 is preserved.
- A Rhythm Lab stop error prevents backend shutdown and is returned to the UI.
- Do not add or retain a new test for this change. Run the existing focused test selection exactly once after all edits.
- Do not modify source audio, databases, generated assets, or the user's existing `AGENTS.md` change.

---

### Task 1: Coordinate the backend shutdown route

**Files:**
- Modify: `src/dj_track_similarity/api_routes_server.py:24-38`
- Modify: `src/dj_track_similarity/api.py:129`
- Verify: `tests/test_api_server_shutdown.py`

**Interfaces:**
- Consumes: `stop_rhythm_lab() -> dict[str, object]` from `rhythm_lab_launcher.py`.
- Produces: `register_server_routes(..., stop_rhythm_lab=...)`, which first invokes the managed Rhythm Lab stop callable and then schedules `shutdown_server`.

- [ ] **Step 1: Extend route registration with an optional managed Lab stopper**

```python
def register_server_routes(
    app: FastAPI,
    *,
    shutdown_server: Callable[[], None] = shutdown_current_process,
    stop_rhythm_lab: Callable[[], dict[str, object]] | None = None,
) -> None:
```

- [ ] **Step 2: Stop Lab after header validation and before backend scheduling**

```python
if action != SHUTDOWN_ACTION_HEADER:
    raise HTTPException(status_code=403, detail="Server shutdown requires the explicit shutdown action header")
if stop_rhythm_lab is not None:
    stop_rhythm_lab()
background_tasks.add_task(shutdown_server)
return {"status": "shutdown_requested"}
```

Do not catch `RuntimeError` from the Lab stopper: FastAPI must report the failure and the backend shutdown task must not be scheduled.

- [ ] **Step 3: Inject the project-managed Lab stopper from the application factory**

```python
register_server_routes(app, stop_rhythm_lab=stop_rhythm_lab)
```

Keep the default `None` in the route registration so existing isolated route tests retain their current setup and assertions.

### Task 2: Reliably clean the launcher-owned Vite tree on Windows

**Files:**
- Modify: `scripts/run_server_launcher.py:56-64`
- Verify: `scripts/tests/test_run_server_lan_script.py`

**Interfaces:**
- Consumes: the exact `subprocess.Popen` object returned when the launcher starts `npm run dev` or `npm run dev:lan`.
- Produces: `stop_process(process)` that terminates only that process and its descendants on Windows, or keeps the existing terminate/wait/kill fallback elsewhere.

- [ ] **Step 1: Replace Windows frontend cleanup with a known-root process-tree termination**

```python
if os.name == "nt":
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    process.wait(timeout=5)
    return
```

Use the `Popen` PID captured when this launcher started npm. Do not discover listeners by port or command line. Retain a bounded fallback for a process that has already exited and for the non-Windows implementation.

- [ ] **Step 2: Preserve the existing cleanup boundary**

Keep the call inside `main()`'s `finally` block. This ensures normal Ctrl+C and API-requested backend exit share one Vite cleanup path.

### Task 3: Review and verify once

**Files:**
- Inspect: `src/dj_track_similarity/api_routes_server.py`
- Inspect: `src/dj_track_similarity/api.py`
- Inspect: `scripts/run_server_launcher.py`
- Verify: `tests/test_api_server_shutdown.py`
- Verify: `scripts/tests/test_run_server_lan_script.py`

**Interfaces:**
- Consumes: the completed Task 1 and Task 2 changes.
- Produces: one evidence-backed verification result, with no persistent new test file or test case.

- [ ] **Step 1: Inspect the final diff for ownership and order**

```powershell
git diff -- src/dj_track_similarity/api_routes_server.py src/dj_track_similarity/api.py scripts/run_server_launcher.py
```

Confirm the route validates the header before attempting Lab stop, invokes the stopper before queueing backend shutdown, and the launcher uses only its captured frontend PID as the `taskkill` root.

- [ ] **Step 2: Run one focused verification command after every code edit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api_server_shutdown.py scripts/tests/test_run_server_lan_script.py
```

Run this command once only. Do not create, modify, or retain a task-specific test.

- [ ] **Step 3: Check the final patch whitespace and test scope**

```powershell
git diff --check -- src/dj_track_similarity/api_routes_server.py src/dj_track_similarity/api.py scripts/run_server_launcher.py
git status --short
```

Confirm that only the three source files were changed by the implementation and that the pre-existing `AGENTS.md` modification remains unstaged and untouched.
