# API reference

> Audience: Integrators and frontend maintainers.
> Goal: Know active endpoint families and write boundaries.
> Type: reference

## Endpoint families

- Database/library: `/api/database/current`, `/api/database/switch`, `/api/library/scan`, `/api/library/tags/refresh`, `/api/library/relocate`, `/api/tracks`, `/api/library/summary`, `/media/{track_id}`.
- Analysis/classifiers: `/api/analysis/jobs`, job status/cancel routes, `/api/analysis/reset`, `/api/classifiers`, classifier analyze/reset/report/suggestions routes.
- Search/SET: `/api/search`, `/api/search/sonara`, `/api/search/text`, `/api/set-builder/generate`.
- Exports/tags: `/api/export`, `/api/tags/genres/apply`, and `/api/tags/genres/jobs` routes.
- Helpers: `/api/audio-doctor/jobs`, `/api/audio-dedup/jobs`, `/api/evaluation/*`, and `/api/rhythm-lab/*`.
- Rhythm Lab review collections: main app `POST /api/rhythm-lab/collections`; lab-local `/api/collections`, `/api/collections/{id}`, and `/api/collections/{id}/tracks`.

## Analysis payload

`/api/analysis/jobs` accepts `models`, `classifier_keys`, `limit`, `device`, `top_k`, `track_batch_size`, and `inference_batch_size`.

## CLAP text search

`/api/search/text` accepts `query`, optional multiline-derived `positive_queries`, optional `negative_queries`, `adaptive_contrast`, `limit`, `min_similarity`, and `device`. Multiple positive queries are pooled into one CLAP text vector. Negative queries are treated as hard-negative candidates with a fixed `0.35` margin weight.

## Writes

Search and SET routes are previews. Genre tag routes are explicit audio tag write paths. Export writes playlist/report files only. Rhythm Lab review collection routes write only the lab labels database, and deleting a collection does not remove profile labels or source audio.
