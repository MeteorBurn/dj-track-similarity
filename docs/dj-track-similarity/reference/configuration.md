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

## Ports

Main backend uses `8765`, frontend Vite uses `5173`, and Rhythm Lab uses `8777`. Check for an existing project process before starting another fixed-port server.

## Runtime

`ffmpeg` must be on `PATH` or configured through `DJ_TRACK_SIMILARITY_FFMPEG`. Analysis device values are `auto`, `cpu`, and `cuda`.

## Docs

From `docs\dj-track-similarity`, run `npm run build` for local preview or deployment. VitePress uses `base: "/docs/"` and `outDir: "site"`. The backend serves `/docs/` from that folder when it exists; otherwise it shows a clear not-built page.
