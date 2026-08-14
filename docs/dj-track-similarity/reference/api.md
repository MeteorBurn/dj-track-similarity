# API reference

> Audience: Users and maintainers scripting against the local FastAPI app.
> Goal: Summarize endpoint families and key payload rules.
> Type: reference

The API is local and unauthenticated by design. Bind the server carefully. Use `127.0.0.1` unless you intentionally expose it on a LAN.

The backend schemas below describe the current API. The React client imports matching identities,
track shapes, request fields, and response types; this page remains the reference for
endpoint ranges and validation rules.

## Database

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/database/current` | current SQLite selection |
| `POST` | `/api/database/switch` | switch to a path |
| `POST` | `/api/database/dialog` | open native database picker |
| `POST` | `/api/database/clear` | delete SQLite library records |

`/api/database/clear` does not delete audio files.

Database state returns `path`, `artifacts_path`, `evaluation_path`, `catalog_uuid`, and `selected`.
A fresh path creates Core plus mandatory Artifacts. Evaluation remains optional. Structurally
incompatible or incomplete bundles are rejected rather than migrated during normal startup.

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

Regular track rows use `TrackSummaryResponse`: stable identity (`catalog_uuid`,
`track_id`, `track_uuid`), `file_path`, compact tags, `analysis_coverage`, and
classifier-score summaries. Detailed rows expose SONARA Core, MAEST, embedding summaries for the
active ML families, and classifier details. The stored SONARA embedding is not part of the track
response or a current similarity, search, or classifier input. Timeline and fingerprint fields are
also absent.

## Analysis and classifiers

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analysis/jobs` | start analysis job |
| `GET` | `/api/analysis/jobs/latest` | latest analysis job |
| `GET` | `/api/analysis/jobs/{job_id}` | job status |
| `POST` | `/api/analysis/jobs/{job_id}/cancel` | request cancellation |
| `GET` | `/api/analysis/sonara/status` | current SONARA Core and embedding coverage |
| `POST` | `/api/analysis/reset` | reset one family |
| `GET` | `/api/classifiers` | promoted classifier profiles |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | score one classifier |
| `POST` | `/api/classifiers/reset` | delete one classifier's scores |
| `POST` | `/api/analysis/pipelines` | queue selected stages in fixed order |
| `GET` | `/api/analysis/pipelines/latest` | latest parent pipeline status |
| `GET` | `/api/analysis/pipelines/{job_id}` | parent and child-stage status |
| `POST` | `/api/analysis/pipelines/{job_id}/cancel` | cancel current and pending stages |

Audio analysis payload fields include `models` and `limit`. ML requests add `device`, `top_k`,
`track_batch_size`, and `inference_batch_size`. SONARA requests add `sonara_batch_size`;
there is no output selector. `classifier_keys` is not accepted.
SONARA runs alone and passes paths to native `analyze_batch`. ML models continue to use shared
FFmpeg decode. Database migration is intentionally not an API operation; use the explicit
`dj-sim migrate-database` CLI command after stopping every SQLite user.

Classifier analysis is always started for one explicit `classifier_key`. Readiness is
manifest-specific, and not-ready tracks are excluded rather than failed. A pipeline payload selects
`sonara` and/or `ml` plus one shared limit and nested stage settings. Execution order is always
SONARA, then ML. All manual and pipeline stages share one sequential application queue.

`GET /api/library/summary` reports current coverage for SONARA Core, MAEST analysis and embedding,
MERT, MuQ, MuQ-MuLan, CLAP, likes, and compatible classifiers. Per-track `analysis_coverage` contains
`sonara_core` only for SONARA. Use `GET /api/analysis/sonara/status` for separate current Core and
embedding counts.

Reset requests use `{ "analysis_family": "sonara" }` (or `maest`, `mert`, `muq`, `mulan`, `clap`). The typed
response returns `core_rows_deleted`, `artifact_rows_deleted`, and `classifier_rows_deleted`.
Classifier-score reset uses `{ "classifier_key": "live_instrumentation" }`.
SONARA removes only dependent classifier rows; labels, feedback, and embedding-only results remain.

## Search and Reference Compare

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/search` | seed search for `maest`, `mert`, `muq`, `mulan`, or `clap` |
| `POST` | `/api/search/sonara` | SONARA seed search |
| `POST` | `/api/search/text` | CLAP or MuQ-MuLan text-to-track search |
| `POST` | `/api/reference/compare` | per-model Reference Compare groups for one seed |
| `POST` | `/api/reference/compare/verdict` | save one Reference Compare listening verdict |

Search limits are usually `1..500`.

`POST /api/search/text` accepts `analysis_family: "clap" | "mulan"` and defaults to `clap`. It
embeds text with the selected family and searches only that family's stored audio vectors.

Reference Compare accepts one `seed_track_id`, optional `models` from `clap`, `mert`, `muq`, `mulan`, `maest`, and `sonara`, and `limit=1..100`. Its default model list remains unchanged, so include `mulan` explicitly when needed. Verdicts use `mood`, `palette`, `instruments`, `groove`, `genre`, `transition`, or `miss`. They persist as local pair feedback under `reference_compare:<model>`.

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

## Rhythm Lab and server

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/rhythm-lab/status` | status |
| `POST` | `/api/rhythm-lab/launch` | launch or reuse Rhythm Lab |
| `POST` | `/api/rhythm-lab/collections` | save main UI set as collection |
| `POST` | `/api/server/shutdown` | request server shutdown |

Server shutdown requires the `X-DJ-Track-Similarity-Action: shutdown-server` header.
