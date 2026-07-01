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

## Analysis payload

`/api/analysis/jobs` accepts `models`, `classifier_keys`, `limit`, `device`, `top_k`, `track_batch_size`, and `inference_batch_size`.

## Writes

Search and SET routes are previews. Genre tag routes are explicit audio tag write paths. Export writes playlist/report files only.
