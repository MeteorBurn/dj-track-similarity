# API reference

> Audience: Users and maintainers scripting against the local FastAPI app.
> Goal: Summarize endpoint families and key payload rules.
> Type: reference

The API is local and unauthenticated by design. Bind the server carefully. Use `127.0.0.1` unless you intentionally expose it on a LAN.

## Database

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/database/current` | current SQLite selection |
| `POST` | `/api/database/switch` | switch to a path |
| `POST` | `/api/database/dialog` | open native database picker |
| `POST` | `/api/database/clear` | delete SQLite library records |

`/api/database/clear` does not delete audio files.

## Library and media

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/library/scan` | start scan job |
| `POST` | `/api/library/tags/refresh` | start tag refresh job |
| `POST` | `/api/library/relocate` | preview or apply stored path relocation |
| `GET` | `/api/library/summary` | counts for tracks, analyses, likes, classifiers |
| `GET` | `/api/tracks` | paginated lightweight track rows |
| `POST` | `/api/tracks/filtered` | full filtered list for UI set actions |
| `GET` | `/api/tracks/{track_id}` | full metadata row |
| `POST` | `/api/tracks/{track_id}/liked` | toggle local liked state |
| `GET` | `/media/{track_id}` | stream preview audio |

Track list query ranges include `limit=1..500`, `offset>=0`, `search_mode=like|fts`, and `preset=all|syncopated`.

## Analysis and classifiers

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analysis/jobs` | start analysis job |
| `GET` | `/api/analysis/jobs/latest` | latest analysis job |
| `GET` | `/api/analysis/jobs/{job_id}` | job status |
| `POST` | `/api/analysis/jobs/{job_id}/cancel` | request cancellation |
| `POST` | `/api/analysis/reset` | reset one family |
| `GET` | `/api/classifiers` | promoted classifier profiles |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | score one classifier |
| `POST` | `/api/classifiers/reset` | delete selected classifier scores |

Analysis payload fields include `models`, `classifier_keys`, `limit`, `device`, `top_k`, `track_batch_size`, and `inference_batch_size`.

## Search and SET

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/search` | MERT seed search |
| `POST` | `/api/search/sonara` | SONARA seed search |
| `POST` | `/api/search/text` | CLAP text search |
| `POST` | `/api/search/hybrid` | weighted Hybrid preview |
| `POST` | `/api/set-builder/generate` | Smart Set Builder preview |
| `POST` | `/api/reference/compare` | per-model Reference Compare groups for one seed |
| `POST` | `/api/reference/compare/verdict` | save one Reference Compare listening verdict |

Important ranges:

- seed lists for Hybrid feedback and Hybrid search are `1..5` unique track IDs,
- search limits are usually `1..500`,
- Hybrid `per_source` is `1..100`,
- Hybrid `limit` is `1..100`,
- SET `limit` is `1..500`,
- SET `auto_seed_count` is `1..5`,
- SET `bpm_start` and `bpm_target` are `20..300` when provided.

Reference Compare accepts one `seed_track_id`, optional `models` from `clap`, `mert`, `muq`, `maest`, and `sonara`, and `limit=1..100`. Verdicts use `mood`, `palette`, `instruments`, `groove`, `genre`, `transition`, or `miss`. They persist as local pair feedback under `reference_compare:<model>`.

## Tags and export

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/export` | write M3U or CSV |
| `POST` | `/api/tags/genres/apply` | synchronous MAEST genre write path |
| `POST` | `/api/tags/genres/jobs` | start MAEST genre tag job |
| `GET` | `/api/tags/genres/jobs/latest` | latest genre job |
| `GET` | `/api/tags/genres/jobs/{job_id}` | genre job status |
| `POST` | `/api/tags/genres/jobs/{job_id}/cancel` | cancel genre job |
| `POST` | `/api/dialog/folder` | open native folder picker |

The genre API rejects per-track writes. Current behavior writes all available stored MAEST genres.

## Helper tools

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/audio-doctor/jobs` | start Audio Doctor job |
| `GET` | `/api/audio-doctor/jobs/latest` | latest Audio Doctor job |
| `GET` | `/api/audio-doctor/jobs/{job_id}` | job status |
| `POST` | `/api/audio-doctor/jobs/{job_id}/cancel` | cancel job |
| `GET` | `/api/audio-doctor/jobs/{job_id}/report/xlsx` | download XLSX |
| `POST` | `/api/audio-dedup/jobs` | start Audio Dedup job |
| `GET` | `/api/audio-dedup/jobs/latest` | latest Audio Dedup job |
| `GET` | `/api/audio-dedup/jobs/{job_id}` | job status |
| `POST` | `/api/audio-dedup/jobs/{job_id}/cancel` | cancel job |
| `GET` | `/api/audio-dedup/jobs/{job_id}/report/xlsx` | download XLSX |

Audio Doctor apply requires exact `APPLY REPAIR`. Audio Dedup apply requires exact `APPLY DELETE`.

## Rhythm Lab and server

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/rhythm-lab/status` | status |
| `POST` | `/api/rhythm-lab/launch` | launch or reuse Rhythm Lab |
| `POST` | `/api/rhythm-lab/stop` | stop managed Rhythm Lab |
| `POST` | `/api/rhythm-lab/collections` | save main UI set as collection |
| `POST` | `/api/server/shutdown` | request server shutdown |

Server shutdown requires the `X-DJ-Track-Similarity-Action: shutdown-server` header.
