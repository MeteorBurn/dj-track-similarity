# Managed server shutdown lifecycle

## Goal

The top-bar action labelled `Остановить текущий сервер` must stop every
project-managed server started by the normal Windows launcher:

- the main FastAPI backend on port `8765`;
- the Vite development UI on port `5173`;
- Rhythm Lab on port `8777`, but only when it is managed by this project.

It must not terminate an unrelated process that happens to listen on one of
those ports.

## Existing ownership model

`run_server.cmd` invokes `scripts/run_server_launcher.py`. The launcher starts
Vite through `npm run dev` and runs `dj-sim serve` as its backend child. Its
`finally` cleanup currently terminates only the top-level npm process. On
Windows, npm can create a cmd and Node descendant tree, leaving Vite alive
after the backend exits.

The backend endpoint `POST /api/server/shutdown` already requires the explicit
`X-DJ-Track-Similarity-Action: shutdown-server` header and schedules
termination after acknowledging the request. Rhythm Lab already has a managed
stop operation that validates its PID/source ownership and refuses unmanaged
listeners.

## Design

1. Add a launcher cleanup helper that terminates the complete process tree
   rooted at the launcher-owned frontend process. It runs only in the launcher's
   `finally` block, after the backend exits. On Windows it targets that known
   root PID and descendants; it does not search for arbitrary listeners on
   port `5173`.
2. Extend server-route registration with the existing Rhythm Lab stop callable.
   Before scheduling backend termination, the shutdown endpoint invokes that
   callable.
3. If Rhythm Lab is project-managed, its process stops before backend shutdown.
   If a listener on `8777` is unmanaged, the stop result reports no managed
   target and the backend/UI shutdown continues without touching it.
4. If the managed Rhythm Lab stop raises an error, the endpoint returns an
   error and does not schedule backend termination. This prevents a successful
   response while leaving a project-managed server running.
5. The frontend keeps its existing request, response type, and acknowledgement
   UI. The button does not issue independent port-kill requests.

## Verification

- Focused API tests cover the explicit-header guard, successful managed Rhythm
  Lab stop before scheduled backend shutdown, unmanaged Rhythm Lab behavior,
  and failure propagation without backend shutdown.
- Focused launcher tests verify the frontend cleanup calls the platform process
  tree terminator for the launcher-owned PID and preserves the non-Windows
  fallback behavior.
- Run the relevant backend and launcher pytest files, frontend typecheck if the
  typed response changes, plus `git diff --check` on touched paths.

## Non-goals

- Killing a manually started Vite, `dj-sim`, or Rhythm Lab process.
- Adding a supervisor service, PID registry, or changes to audio or database
  workflows.
