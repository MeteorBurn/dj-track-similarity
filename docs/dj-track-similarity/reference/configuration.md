# Configuration reference

> Audience: Users wiring local paths, ports, and builds.
> Goal: Know important runtime and docs settings.
> Type: reference

## Paths

- Source package: `src/dj_track_similarity/`.
- Frontend source: `frontend/`.
- Docs source: `docs/dj-track-similarity/`.
- Docs output: `docs/dj-track-similarity/site/` (local build output, ignored by Git).
- Promoted classifiers: `models/classifiers/<artifact-prefix>/`.
- Persistent ANN sidecars: `.dj-track-similarity-indexes/` beside the selected SQLite database by default, or `--index-dir <index-folder>` when overridden.

## Ports

Main backend uses `8765`, frontend Vite uses `5173`, and Rhythm Lab uses `8777`. Check for an existing project process before starting another fixed-port server.

The main UI top bar includes a local server stop button for the current backend process. It calls `/api/server/shutdown` with the explicit shutdown action header, then the backend exits after acknowledging the request.

## Runtime

`ffmpeg` must be on `PATH` or configured through `DJ_TRACK_SIMILARITY_FFMPEG`. Analysis device values are `auto`, `cpu`, and `cuda`.

Persistent ANN index backends are selected with `dj-sim index build --backend auto|hnswlib|exact-numpy`. `auto` prefers `hnswlib` when the optional `ann` extra is installed and falls back to `exact-numpy` otherwise.

## Generated local state

Generated databases, logs, reports, backups, promoted classifier artifacts, and index sidecars may reveal private library information. Keep them out of Git unless they are intentionally sanitized.

## Docs

From `docs\dj-track-similarity`, run `npm run build` only when you intentionally need local preview or deployment output. VitePress uses `base: "/docs/"` and `outDir: "site"`. The backend serves `/docs/` from that folder when it exists; otherwise it shows a clear not-built page.
