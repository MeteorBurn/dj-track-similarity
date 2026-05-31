# Web API Reference

This page documents the FastAPI endpoints used by the frontend. Most users do
not need to call these endpoints directly; use this page when debugging the web
UI, integrating a local script, or checking which backend action a UI button
uses.

## Web API Reference

The frontend uses these endpoints through `frontend/src/api.ts`.

The API is local-first. Endpoints that scan, analyze, search, preview, export,
reset, clear, or relocate work against the selected SQLite database and local
filesystem paths. Audio-file writes happen only through the explicit MAEST
genre tag endpoints.

### Conventions

These shared conventions apply across the API:

| Convention | Meaning |
| --- | --- |
| `400` `DatabaseNotSelected` | A database-aware endpoint was called before a database was selected. Select one with `/api/database/switch` first. |
| `409` `DatabaseBusy` | A database switch was attempted while a job was `queued` or `running`. Wait for or cancel the job, then retry. |
| `404` | Unknown track, job, or media id. |
| Job `state` | One of `queued`, `running`, `completed`, `cancelled`, or `failed`. |
| `latest` job endpoints | Return `null` when no job of that family has run yet. |

Long-running work (scan, tag refresh, multi-model audio analysis, classifier
scoring, genre tag jobs) is started by a `POST` that returns an initial
job-status object. The frontend then polls the matching `jobs/latest` or
`jobs/{job_id}` endpoint and can request cooperative cancellation.

### Database

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/database/current` | Return selected database state. |
| `POST` | `/api/database/switch` | Switch to a database path. |
| `POST` | `/api/database/dialog` | Open a local database chooser dialog. |
| `POST` | `/api/database/clear` | Clear local SQLite tracks, embeddings, and dependent classifier scores. |

Use these endpoints when selecting the active library database. `clear` is a
database operation, not an audio-file delete operation, but it removes the
library index and analysis rows from the selected SQLite file.

### Library

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/library/scan` | Start a scan job for a root folder. |
| `POST` | `/api/library/tags/refresh` | Start a Mutagen tag refresh job. |
| `POST` | `/api/library/relocate` | Preview or apply stored path relocation. |
| `GET` | `/api/library/summary` | Return counters for tracks, analysis families, liked tracks, and complete promoted-classifier score coverage. |
| `GET` | `/api/tracks` | Return a paginated/searchable track page. |
| `GET` | `/api/tracks/{track_id}` | Return one full track payload. |
| `POST` | `/api/tracks/{track_id}/liked` | Save or remove the local liked flag for one track. |
| `POST` | `/api/tracks/filtered` | Return filtered track rows for selection workflows. |

`/api/tracks` and `/api/tracks/filtered` accept `preset=syncopated` to filter on
the stored MAEST syncopated-rhythm flag. They accept `liked=true` to show only
liked tracks, and classifier threshold maps to filter tracks by stored
classifier scores.

Use `/api/tracks` for paged browsing and `/api/tracks/{track_id}` only when a
full metadata dialog needs one track. This keeps large libraries responsive.

`/api/library/summary` includes a `classifiers` counter. It counts a track only
when the track has stored `track_classifier_scores` rows for every promoted
classifier discovered from `models/classifiers/*/model.json`.

`/api/library/relocate` is a preview-first endpoint: it returns the relocation
plan by default and only updates stored `tracks.path` values when `apply` is
`true`. It has no button in the current web UI and no method in
`frontend/src/api.ts`; drive relocation from the `dj-sim relocate-library` CLI
command or a direct API call. Apply is rejected when there are conflicts or
missing target files.

### Jobs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/library/scan/jobs/latest` | Return latest scan or tag-refresh job. |
| `GET` | `/api/library/scan/jobs/{job_id}` | Return one scan job. |
| `POST` | `/api/library/scan/jobs/{job_id}/cancel` | Request scan cancellation. |
| `GET` | `/api/analysis/jobs/latest` | Return latest multi-model audio analysis job. |
| `GET` | `/api/analysis/jobs/{job_id}` | Return one multi-model audio analysis job. |
| `POST` | `/api/analysis/jobs/{job_id}/cancel` | Request multi-model analysis cancellation. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/latest` | Return latest classifier job. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}` | Return one classifier job. |
| `POST` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}/cancel` | Request classifier cancellation. |
| `GET` | `/api/tags/genres/jobs/latest` | Return latest genre tag write job. |
| `GET` | `/api/tags/genres/jobs/{job_id}` | Return one genre tag write job. |
| `POST` | `/api/tags/genres/jobs/{job_id}/cancel` | Request genre tag write cancellation. |

Job endpoints let the frontend poll long-running work and request cancellation.
Cancellation is cooperative: a job may finish the current track or batch before
it stops.

### Analysis and Search

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analysis/jobs` | Start one selected-model analysis job for SONARA, MAEST, MERT, and/or CLAP. |
| `GET` | `/api/classifiers` | List promoted classifiers from `models/classifiers/*/model.json`. |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | Start classifier scoring. |
| `POST` | `/api/classifiers/reset` | Delete stored scores for the given classifier keys. |
| `POST` | `/api/analysis/reset` | Reset one analysis family. |
| `POST` | `/api/search` | Search in MERT embedding space. |
| `POST` | `/api/search/sonara` | Search with Sonara features. |
| `POST` | `/api/search/text` | Search CLAP audio vectors from text. |

Use `/api/analysis/jobs` before search endpoints when a library has not been
processed yet. Its request body accepts `models`, `limit`, `device`, `top_k`,
`track_batch_size`, and `inference_batch_size`. `models` defaults to all four
audio models (`sonara`, `maest`, `mert`, `clap`) and must be a non-empty
subset. `limit: null` means all eligible tracks; positive limits count
candidate tracks that are missing at least one selected model.

`track_batch_size` controls how many decoded tracks the job holds and processes
together. `inference_batch_size` controls MAEST/MERT/CLAP model forward-pass
batches. The default values are `track_batch_size=6` and
`inference_batch_size=24`. The former single `batch_size` request field is no
longer accepted.

The analysis job skips selected-model results that already exist. Its top-level
status uses `total`, `processed`, `analyzed`, `failed`, and `skipped` for
track-level counters. `model_progress` keeps per-model counters for model-level
writes and failures.
`current_model` identifies which selected model is currently running. Empty
search results often mean the required Sonara features, MERT embeddings, or
CLAP embeddings are missing for the candidate tracks.

`GET /api/classifiers` needs no database; it discovers promoted profiles on
disk. `/api/classifiers/reset` accepts a list of classifier keys and deletes
their `track_classifier_scores` rows (an empty list deletes nothing).

Reset scope by family:

| Reset | Removes |
| --- | --- |
| `/api/analysis/reset` `sonara` | `sonara_*` metadata keys; recomputes stored BPM/key/energy/duration from remaining metadata. |
| `/api/analysis/reset` `maest` | `maest_*` metadata keys plus `maest` embeddings. |
| `/api/analysis/reset` `mert` / `clap` | Embeddings of that key. |
| `/api/classifiers/reset` | `track_classifier_scores` rows for the listed classifier keys. |

### Export, Tags, Dialogs, Media

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/export` | Export selected tracks as M3U or CSV. |
| `POST` | `/api/tags/genres/apply` | Write MAEST genres synchronously to every track that has MAEST genres. |
| `POST` | `/api/tags/genres/jobs` | Start a cancellable background MAEST genre tag write job. |
| `POST` | `/api/dialog/folder` | Open a folder chooser dialog. |
| `GET` | `/media/{track_id}` | Serve browser-playable audio for one track. |

Both genre tag endpoints apply to all tracks that have stored MAEST genres.
They do not accept a track subset: a request body with `track_ids` is rejected
with HTTP `400`. They are the explicit audio-file write path and overwrite only
the standard genre field.

The frontend preview player uses `/media/{track_id}` and starts playback after a
preview button click. AIFF/AIF responses are transcoded to temporary WAV files
for browser compatibility and scrubbing support without rewriting source audio.

Use `/api/export` for playlist/report files. Prefer `/api/tags/genres/jobs` for
genre writes so progress and cancellation are available; the synchronous
`/api/tags/genres/apply` returns one result row per track but blocks until the
whole batch finishes.
