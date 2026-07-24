# API reference

> Audience: Users and maintainers scripting against the local FastAPI app.
> Goal: Summarize endpoint families and key payload rules.
> Type: reference

The API is local and unauthenticated by design. Bind the server carefully. Use `127.0.0.1` unless you intentionally expose it on a LAN.

The backend schemas below are the active v7 contract. The checked-in React client still uses
pre-v7 payloads and has not yet been ported, so this page does not claim frontend compatibility.

## Database

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/database/current` | current SQLite selection |
| `POST` | `/api/database/switch` | switch to a path |
| `POST` | `/api/database/dialog` | open native database picker |
| `POST` | `/api/database/clear` | delete SQLite library records |

`/api/database/clear` does not delete audio files.

Database state returns `path`, `artifacts_path`, `evaluation_path`, `catalog_uuid`, and `selected`.
A fresh path creates schema-v7 Core plus mandatory Artifacts. Evaluation remains optional. Existing
non-v7 or incomplete bundles are rejected rather than migrated.

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
| `GET` | `/api/tracks/{track_id}/sonara-timeline` | explicit Timeline payload read |
| `POST` | `/api/tracks/{track_id}/liked` | toggle local liked state |
| `GET` | `/media/{track_id}` | stream preview audio |

Track list query ranges include `limit=1..500`, `offset>=0`, `search_mode=like|fts`, and `preset=all|syncopated`.

The timeline endpoint returns complete stored `beats`, `onset_frames`, `chord_sequence`,
`chord_events`, `tempo_curve`, `energy_curve`, `segments`, `loudness_curve`, and `downbeats` payloads
when available. It returns `{}` when no current timeline row exists and `404` for an unknown track.
Regular track rows use the v7 `TrackSummaryV7` shape: composite identity (`catalog_uuid`,
`track_id`, `track_uuid`, `content_generation`), `file_path`, compact tags, `analysis_coverage`, and
classifier-score summaries. Detailed rows expose `optional_outputs.timeline_fields`,
`sonara_embedding_available`, and `audio_fingerprint_available`.

Each field is a serialized payload rather than a raw top-level array. The response shape is:

```json
{
  "energy_curve": {
    "value": [0.31, 0.44, 0.72],
    "type": "list",
    "length": 3
  }
}
```

## Analysis and classifiers

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analysis/jobs` | start analysis job |
| `GET` | `/api/analysis/jobs/latest` | latest analysis job |
| `GET` | `/api/analysis/jobs/{job_id}` | job status |
| `POST` | `/api/analysis/jobs/{job_id}/cancel` | request cancellation |
| `POST` | `/api/analysis/reset` | reset one family |
| `POST` | `/api/analysis/sonara/releases/prepare` | back up and activate the loaded four-output SONARA release |
| `GET` | `/api/classifiers` | promoted classifier profiles |
| `POST` | `/api/classifiers/analyze` | score selected classifiers; empty list means all compatible |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | score one classifier |
| `POST` | `/api/classifiers/reset` | delete selected classifier scores |
| `POST` | `/api/analysis/pipelines` | queue selected stages in fixed order |
| `GET` | `/api/analysis/pipelines/latest` | latest parent pipeline status |
| `GET` | `/api/analysis/pipelines/{job_id}` | parent and child-stage status |
| `POST` | `/api/analysis/pipelines/{job_id}/cancel` | cancel current and pending stages |

Audio analysis payload fields include `models` and `limit`. ML requests add `device`, `top_k`,
`track_batch_size`, and `inference_batch_size`. SONARA requests add `sonara_outputs` and
`sonara_batch_size`. `classifier_keys` is not accepted.
Allowed SONARA outputs are `core`, `timeline`, `embedding`, and `fingerprint`. Omission defaults to
`["core"]`. At least one is required for a SONARA job, and normalization always includes `core`.
SONARA runs alone, and its scheduler compares the independent contract for every selected output. It
passes paths to native `analyze_batch`. ML models continue to use shared FFmpeg decode. An
unprepared release returns `409` with `SONARA_RELEASE_PREPARATION_REQUIRED`.

The prepare payload is:

```json
{
  "backup_dir": "C:\\backups\\dj-track-similarity",
  "confirm": "PREPARE SONARA RELEASE"
}
```

Clients cannot supply output kinds or a release hash. Preparation verifies Core and Artifacts
backups and uses an ordered, receipt-backed flow that can resume after interruption.

The aggregate classifier payload is `{ "classifier_keys": [], "limit": null }`. Readiness is
manifest-specific, totals count ready classifier-track pairs, and not-ready tracks are excluded
rather than failed. A pipeline payload selects `sonara`, `ml`, and/or `classifiers` plus one shared
limit and nested stage settings. Execution order is always SONARA, ML, CLASSIFIERS. All manual and
pipeline stages share one sequential application queue.

`GET /api/library/summary` reports current coverage for SONARA, MAEST analysis and embedding, MERT,
MuQ, CLAP, likes, and compatible classifiers. Per-track `analysis_coverage` separates `sonara_core`,
`timeline`, `sonara_embedding`, and `fingerprint`.

Reset requests use `{ "analysis_family": "sonara" }` (or `maest`, `mert`, `muq`, `clap`). The typed
response returns `core_rows_deleted`, `artifact_rows_deleted`, and `classifier_rows_deleted`.
SONARA removes only dependent classifier rows; labels, feedback, and embedding-only results remain.

## Search and SET

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/search` | seed search for `maest`, `mert`, `muq`, or `clap` |
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
