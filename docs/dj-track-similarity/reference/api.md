# API reference

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

Database state returns `path`, `evaluation_path`, `catalog_uuid`, and `selected`. A fresh path
creates one library database. The adjacent Evaluation database remains optional and is created only
by Evaluation workflows. Incompatible legacy layouts are rejected rather than migrated during
normal startup.

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
| `DELETE` | `/api/tracks/{track_id}` | remove one current catalog track and its catalog-owned data |
| `GET` | `/media/{track_id}` | stream preview audio |

Track list query ranges include `limit=1..500`, `offset>=0`, `search_mode=like|fts`, and `preset=all|syncopated`.

Regular track rows use `TrackSummaryResponse`: stable identity (`catalog_uuid`,
`track_id`, `track_uuid`), `file_path`, compact tags, `analysis_coverage`, and
classifier-score summaries. Detailed rows expose SONARA Core, MAEST, embedding summaries for the
active ML families, and classifier details. The stored SONARA embedding and acoustic fingerprint
are not part of a track response, and neither is a current similarity, search, or classifier
input. The fingerprint's one consumer is the standalone Audio Dedup tool. Timeline fields are
also absent.

`DELETE /api/tracks/{track_id}` requires the current track identity in its JSON body:
`catalog_uuid` and `track_uuid`. It removes the matching SQLite catalog row, its FTS entry, and
foreign-key-cascaded catalog relations in one transaction. It never deletes or changes the source
audio file. After that transaction commits, it also removes the track's `search_session_seeds` and
`search_result_events` rows from the optional Evaluation sidecar, which is a separate file that no
foreign key reaches. The sidecar is opened only when it already exists. The Rhythm Lab database is
independent and is not modified by this route.

## Audio Dedup

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/audio-dedup/jobs` | start one duplicate scan |
| `GET` | `/api/audio-dedup/jobs/latest` | latest scan job, or `null` |
| `GET` | `/api/audio-dedup/jobs/{job_id}` | scan job status |
| `POST` | `/api/audio-dedup/jobs/{job_id}/cancel` | request cancellation |
| `GET` | `/api/audio-dedup/reports` | reports found in the report directory |
| `GET` | `/api/audio-dedup/reports/{report_id}` | one report summary |
| `GET` | `/api/audio-dedup/reports/{report_id}/groups` | paged, filtered, live-checked groups |
| `GET` | `/api/audio-dedup/reports/{report_id}/xlsx` | download that run's workbook |
| `POST` | `/api/audio-dedup/reports/{report_id}/delete` | delete a confirmed selection |

A scan request accepts `root`, `path_contains`, `search_mode` (`fingerprint` by default, or
`embedding`), `preset` (`safe`, `balanced`, or `aggressive`), `min_score`, `min_similarity`,
`limit_groups`, `sources`, `weights`, and `skip_spectral`. Unknown fields are rejected. `sources`
and `weights` require the embedding mode. The preset, sources, and weights are resolved before the
job is queued, so a rejected value returns `400` instead of failing inside the job thread. One scan
runs at a time and a second start returns `409`. Cancellation reports `state="cancelled"` rather
than a failure. The scan writes the same JSON, XLSX, and log artifacts the CLI writes, and the
completed status carries the `report_id`, which is the JSON file stem.

Reports are read back from disk, newest first, so a review survives a server restart and a
CLI-produced report is listed too. A `report_id` that is not a plain name inside the report
directory is rejected. The groups route accepts `offset`, `limit` (`1..200`, `25` by default),
repeatable `confidence`, `min_fingerprint`, `fake_bitrate_only`, and `path_contains`. Every
file it returns is checked against the live database and the disk with the tests the deletion gate
runs later, so a group entry carries `stale`, `stale_reason`, and `playable` alongside the report's
own evidence.

The delete request is `{"selections": [{"group_id": 1, "track_ids": [186]}], "deletion_mode":
"trash", "confirmation": "APPLY DELETE"}`. `deletion_mode` is `trash` or `permanent` and defaults to
`trash`. The route requires `confirmation` to equal `APPLY DELETE` exactly, and it rejects a
`track_id` that does not belong to the named `group_id`. The deletion root comes from the report
payload, and a report written against another database is refused. The route holds an exclusive
database reservation while it runs. Selected members are deleted whether or not the report called them safe, the suggested
keeper included, and a group that would lose every copy is skipped instead. The response returns
`requested`, `deleted_track_ids`, `deleted_paths`, `skipped`, `failed`, and
`rhythm_lab_deleted_rows`. Report artifacts are left as written, so the next group page shows the
deleted copies as stale. For the review workflow and the shared deletion gates, see
[Audio Dedup](../tools-and-scripts/audio-dedup.md).

## Analysis and classifiers

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analysis/jobs` | start analysis job |
| `GET` | `/api/analysis/jobs/latest` | latest analysis job |
| `GET` | `/api/analysis/jobs/{job_id}` | job status |
| `POST` | `/api/analysis/jobs/{job_id}/cancel` | request cancellation |
| `GET` | `/api/analysis/sonara/status` | current SONARA Core, embedding, and fingerprint coverage |
| `POST` | `/api/analysis/reset` | reset one family |
| `GET` | `/api/classifiers` | promoted classifier profiles |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | score one classifier |
| `POST` | `/api/classifiers/reset` | delete one classifier's scores |
| `POST` | `/api/analysis/pipelines` | queue selected stages in fixed order |
| `GET` | `/api/analysis/pipelines/latest` | latest parent pipeline status |
| `GET` | `/api/analysis/pipelines/{job_id}` | parent and child-stage status |
| `POST` | `/api/analysis/pipelines/{job_id}/cancel` | cancel current and pending stages |

Audio analysis payload fields include `models` and `limit`. ML requests add `device`, `top_k`,
`track_batch_size`, and `inference_batch_size`. A standalone SONARA request adds
`sonara_batch_size`. There is no output selector, and `classifier_keys` is not accepted. Standalone
SONARA runs in Direct Mode and passes source paths to native `analyze_batch()`.

The status payload returned by `GET /api/analysis/jobs/latest` and `GET /api/analysis/jobs/{job_id}`
carries a `phase` field with the values `preparing`, `warmup`, and `analyzing`. A job starts at
`preparing`, becomes `warmup` while it loads the selected models, and becomes `analyzing` once every
selected model is loaded. During `warmup` the ordered `models` list is already final, and
`current_model` and `model_name` name the model being loaded. `device` is written as each model
resolves its device, so it holds `null` until the first one finishes.
`current_model` returns to `null` when the phase becomes `analyzing`. Candidate selection runs after
warm-up, so `total` stays `0` and `model_progress` stays empty for the whole warm-up phase. See
[Model warm-up](./analysis-families.md#model-warm-up) for the job log entries and the runner reuse
that phase reports.

A pipeline request uses separate browser SONARA settings:

```json
{
  "stages": ["sonara"],
  "sonara": {
    "mode": "staged",
    "direct_batch_size": 8,
    "bpm_min": 70,
    "bpm_max": 180,
    "staged": {
      "folder": "D:/Staging",
      "processes": 4,
      "threads": 4,
      "batch_size": 4,
      "stage_size": 32
    }
  }
}
```

`mode` defaults to `direct`, and `direct_batch_size` accepts `1..16`. Direct Mode ignores the
nested Staged folder. Staged Mode requires an existing folder and accepts Processes `1..16`,
Threads `1..64`, BatchSize `1..16`, and StageSize `1..512`. Staged SONARA passes temporary copy
paths to native analysis and its per-file direct shared-library recovery while retaining the original
track identity. ML models do not use this staging configuration. Following a failed full TorchCodec
decode, the requested ML family makes its own in-process PyAV recovery decode with the shared
FFmpeg libraries, keeping the valid frames around any malformed packet, and then retains its
existing model-specific resampling and window preparation.
Database migration is intentionally not an API operation; use the explicit CLI command
`dj-sim migrate-database` after stopping every SQLite user.

Classifier analysis is always started for one explicit `classifier_key`. Readiness is
manifest-specific, and not-ready tracks are excluded rather than failed. A pipeline payload selects
`sonara` and/or `ml` plus one shared limit and nested stage settings. Execution order is always
SONARA, then ML. All manual and pipeline stages share one sequential application queue.

`GET /api/library/summary` reports current coverage for SONARA Core, MAEST analysis and embedding,
MERT, MuQ, MuQ-MuLan, CLAP, likes, and compatible classifiers. Per-track `analysis_coverage` contains
`sonara_core` only for SONARA. Use `GET /api/analysis/sonara/status` for separate current Core and
embedding counts.

Reset requests use `{ "analysis_family": "sonara" }` (or `maest`, `mert`, `muq`, `mulan`, `clap`). The typed
response returns `feature_rows_deleted`, `embedding_rows_deleted`, and `classifier_rows_deleted`.
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

`POST /api/search/text` accepts this JSON contract:

| Field | Required | Current behavior |
| --- | --- | --- |
| `positive_queries` | yes | Non-empty prompt array. Blank entries are removed, every remaining prompt is embedded, and the bank is mean-pooled and normalized. |
| `analysis_family` | no | `"clap"` or `"mulan"`. Defaults to `"clap"`. Search uses only stored audio embeddings from that family. |
| `negative_queries` | no | Prompt array for competing audible classes. Blank entries are removed before contrast scoring. |
| `negative_weight` | no | Number from `0..2`. Defaults to `0.5`. The contrast score subtracts the weighted negative match. |
| `limit` | no | `1..500`. Defaults to `10`. |
| `min_similarity` | no | Optional API score threshold. There is no default threshold. |
| `device` | no | `"auto"`, `"cpu"`, or `"cuda"`. Selects the text adapter device. |

Unknown fields are rejected. There is no `query`, `preset`, or `adaptive_contrast` field. Results
contain `track`, `score`, and nullable `score_breakdown`. Contrast searches report
`positive`, `negative`, `contrast`, and `negative_weight` in that breakdown. Results stay in
descending score order.

Text-search scores are cosine or contrast ranking evidence, not probabilities. Compare them only
within one selected family and prompt bank, not with seed-search scores, SONARA, MERT, or the other
text family. The endpoint reads stored embeddings and track rows; it does not modify source audio,
tags, analysis rows, or classifier scores. Browser search does not send `min_similarity`: it uses
`Limit` and keeps the full descending rank. API and CLI threshold workflows remain separate.

Reference Compare accepts one `seed_track_id`, optional `models` from `clap`, `mert`, `muq`, `mulan`, `maest`, and `sonara`, and `limit=1..100`. When `models` is omitted, it returns six separate default groups in that order, including `mulan`. Verdicts use `mood`, `palette`, `instruments`, `groove`, `genre`, `transition`, or `miss`. They persist as local pair feedback under `reference_compare:<model>`.

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

Server shutdown requires the `X-DJ-Track-Similarity-Action: shutdown-server` header. On success the
route returns `{"status":"shutdown_requested"}`, then schedules dependent cleanup in the
background. When a managed Rhythm Lab server is active, shutdown attempts to stop it before the main
backend process. A Rhythm Lab cleanup failure is logged, but the backend shutdown still proceeds.
