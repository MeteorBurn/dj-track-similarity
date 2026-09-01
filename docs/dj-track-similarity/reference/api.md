# API reference

The API is local and unauthenticated by design. Bind the server carefully. Use `127.0.0.1` unless
you intentionally expose it on a LAN.

The backend registers 76 JSON routes plus two static mounts. Every route below is registered by
`create_app()`. The React client imports matching identities, track shapes, request fields, and
response types from `frontend/src/api.ts`, and this page remains the reference for ranges and
validation rules.

## Cross-cutting rules

Two exception handlers apply to the whole application:

| Condition | Status | Meaning |
| --- | ---: | --- |
| `DatabaseNotSelected` | `400` | The server started without `--db` and no database has been chosen yet. |
| `DatabaseBusy` | `409` | A background job is running, or another exclusive operation holds the database. |

Individual routes add their own codes on top of those.

Most mutations carry track identity. A request body that names a `track_id` also names the
`catalog_uuid` and `track_uuid` the caller believes it has. When the stored row no longer matches,
the write is refused. A bare `track_id` is never a safe write target.

Most request bodies set `extra="forbid"`, so an unknown field is a `422` rather than a silently
ignored key. The analysis, pipeline, search, text-search, warmup, feedback, Reference Compare, and
Audio Dedup contracts all forbid extras. A few smaller bodies, including the tag-refresh and
relocation requests, do not.

Clear, delete, reset, relocation apply, genre writes, and Audio Dedup deletion take an exclusive
database reservation. While one runs, a database switch and any job start return `409`.

## Database

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/database/current` | current SQLite selection |
| `POST` | `/api/database/switch` | switch to a path |
| `POST` | `/api/database/dialog` | open native database picker |
| `POST` | `/api/database/clear` | delete SQLite library records |
| `POST` | `/api/database/validation/jobs` | start one read-only validation job |
| `GET` | `/api/database/validation/jobs/latest` | latest validation job, or `null` |
| `GET` | `/api/database/validation/jobs/{job_id}` | validation job status |
| `POST` | `/api/database/validation/jobs/{job_id}/cancel` | request cancellation |

`/api/database/clear` is registered in the library route module. It does not delete audio files.

Database state returns `path`, `evaluation_path`, `catalog_uuid`, and `selected`. A fresh path
creates one library database. The adjacent Evaluation database remains optional and is created only
by Evaluation workflows. Incompatible legacy layouts are rejected rather than migrated during
normal startup.

`/api/database/switch` takes `{"path": "..."}`. An invalid path returns `400`. A busy database
returns `409`. The browser client does not call this route. It uses the picker instead.

`/api/database/dialog` opens a native save dialog on the machine running the backend. It returns
`503` when Tk is unavailable, and returns the unchanged current state when the dialog is cancelled.

The validation job family runs `DatabaseValidator` against a read-only connection, streams findings
into the job event log, and ends `completed`, `cancelled`, or `failed`. One validation job runs at a
time, and a second start returns `409`. The browser reaches it from the shield button in panel 1,
database and analysis (see the [UI language glossary](../help/ui-language.md) for the on-screen
strings). The command-line equivalent is `dj-sim validate-database`, which also carries the result
in its exit code.

## Library and media

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/library/scan` | start scan job |
| `POST` | `/api/library/tags/refresh` | start tag refresh job |
| `POST` | `/api/library/relocate` | preview or apply stored path relocation |
| `GET` | `/api/library/scan/jobs/latest` | latest scan or tag-refresh job, or `null` |
| `GET` | `/api/library/scan/jobs/{job_id}` | scan job status |
| `POST` | `/api/library/scan/jobs/{job_id}/cancel` | request cancellation |
| `GET` | `/api/library/summary` | counts for tracks, analyses, likes, classifiers |
| `GET` | `/api/tracks` | paginated lightweight track rows |
| `POST` | `/api/tracks/filtered` | full filtered list for UI set actions |
| `GET` | `/api/tracks/{track_id}` | full metadata row |
| `POST` | `/api/tracks/{track_id}/liked` | toggle local liked state |
| `POST` | `/api/tracks/{track_id}/reveal` | open the containing folder on the server machine |
| `DELETE` | `/api/tracks/{track_id}` | remove one current catalog track and its catalog-owned data |
| `GET` | `/media/{track_id}` | stream preview audio |

Track list query ranges include `limit=1..500`, `offset>=0`, `search_mode=like|fts`, and
`preset=all|syncopated`. `liked` filters to liked rows. `classifier_min_scores` is a JSON **object
encoded as a query string**, mapping a classifier key to a float in `0..1`. A value that fails to
parse as JSON, is not an object, or falls outside `0..1` returns `422`.

Regular track rows use `TrackSummaryResponse`: stable identity (`catalog_uuid`,
`track_id`, `track_uuid`), `file_path`, compact tags, `analysis_coverage`, and
classifier-score summaries. Detailed rows expose SONARA Core, MAEST, embedding summaries for the
active ML families, and classifier details. The stored SONARA embedding and acoustic fingerprint
are not part of a track response, and neither is a current similarity, search, or classifier
input. The fingerprint's one consumer is the standalone Audio Dedup tool. Timeline fields are
also absent.

`POST /api/tracks/{track_id}/liked` takes `{catalog_uuid, track_uuid, liked}`. An unknown track is
`404`. An identity that no longer matches the stored row is `409`, because the row exists and its
content changed.

`POST /api/tracks/{track_id}/reveal` launches the platform file browser on the machine running the
backend and selects the file. It reads nothing and writes nothing. A missing track or a missing file
is `404`, and a failure to launch the browser is `503`. The response is `{"path": "..."}`.

`POST /api/tracks/filtered` returns the whole matching set with no limit, which is what the
add-visible-tracks action needs. Use `GET /api/tracks` for paging.

`POST /api/library/tags/refresh` accepts `{"workers": N}` with `N` in `1..64`. The scan dialog in
the browser offers `1..16`, so an API caller has a wider range than the UI.

`GET /api/library/summary` returns coverage counts plus `sonara_bpm_min` and `sonara_bpm_max`,
which hold the BPM range the library is already bound to, or `null` while no SONARA row exists.

`GET /media/{track_id}` streams the source file directly for formats a browser can play. For the
formats listed in `BROWSER_PREVIEW_TRANSCODE_SUFFIXES`, and for any WAV that is not 16-bit with a
valid channel count and sample rate, it decodes to a temporary 44.1 kHz stereo WAV and deletes that
file after the response. The source is never rewritten or cached.

`DELETE /api/tracks/{track_id}` requires the current track identity in its JSON body:
`catalog_uuid` and `track_uuid`. It removes the matching SQLite catalog row, its FTS entry, and
foreign-key-cascaded catalog relations in one transaction. It never deletes or changes the source
audio file. After that transaction commits, it also removes the track's `search_session_seeds` and
`search_result_events` rows from the optional Evaluation sidecar, which is a separate file that no
foreign key reaches. The sidecar is opened only when it already exists. The Rhythm Lab database is
independent and is not modified by this route.

`POST /api/library/relocate` takes `{old_root, new_root, apply}`. Preview needs only a selected
database. Apply takes an exclusive reservation and rewrites `tracks.file_path` and the matching
`library.roots_json` entries. It never touches audio. The browser has no relocation control, so this
route is reachable from a direct HTTP call or from `dj-sim relocate-library`.

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
database reservation while it runs. Selected members are deleted whether or not the report called
them safe, the suggested keeper included, and a group that would lose every copy is skipped instead.
The response returns `requested`, `deleted_track_ids`, `deleted_paths`, `skipped`, `failed`, and
`rhythm_lab_deleted_rows`. Report artifacts are left as written, so the next group page shows the
deleted copies as stale.

The phrase is an API contract rather than a person typing it. The command-line tool makes a human
type `APPLY DELETE` at a prompt. The browser client inserts the same string into the request body
itself and asks the user a **Yes / No** dialog instead. For the review workflow and the shared
deletion gates, see [Audio Dedup](../tools-and-scripts/audio-dedup.md).

## Analysis and classifiers

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analysis/jobs` | start one analysis job |
| `GET` | `/api/analysis/jobs/latest` | latest analysis job, or `null` |
| `GET` | `/api/analysis/jobs/{job_id}` | job status |
| `POST` | `/api/analysis/jobs/{job_id}/cancel` | request cancellation |
| `GET` | `/api/analysis/sonara/status` | current SONARA Core, embedding, and fingerprint coverage |
| `POST` | `/api/analysis/reset` | reset one family |
| `POST` | `/api/analysis/pipelines` | queue selected stages in fixed order |
| `GET` | `/api/analysis/pipelines/latest` | latest parent pipeline status |
| `GET` | `/api/analysis/pipelines/{job_id}` | parent and child-stage status |
| `POST` | `/api/analysis/pipelines/{job_id}/cancel` | cancel current and pending stages |
| `GET` | `/api/classifiers` | promoted classifier profiles |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | score one classifier |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/latest` | latest scoring job for that key, or `null` |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}` | scoring job status |
| `POST` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}/cancel` | request cancellation |
| `GET` | `/api/classifiers/{classifier_key}/calibration-report` | calibration diagnostics for one promoted key |
| `GET` | `/api/classifiers/{classifier_key}/label-suggestions` | ranked label suggestions for one promoted key |
| `POST` | `/api/classifiers/reset` | delete one classifier's scores |

`GET /api/classifiers` works with no database selected. It then lists the promoted profiles without
their `scored_tracks` counts.

`GET /api/classifiers/{classifier_key}/label-suggestions` accepts `mode` (default `uncertainty`),
`limit` in `1..500` (default `25`), and `random_seed` (default `123`). An unknown key is `400`.

`POST /api/analysis/jobs` accepts `models`, `limit`, `device`, `top_k`, `track_batch_size`,
`inference_batch_size`, `sonara_batch_size`, `sonara_bpm_min`, and `sonara_bpm_max`. There is no
output selector, and `classifier_keys` is not accepted. This request body has **no mode field and no
staging block**, so a job started here always runs in Direct Mode. Staged Mode for either family is
reachable through `/api/analysis/pipelines`, and ML Staged Mode is also reachable through
`dj-sim analyze --ml-staged`.

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

A pipeline request carries a separate settings block per stage:

```json
{
  "stages": ["sonara", "ml"],
  "limit": null,
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
  },
  "ml": {
    "models": ["maest", "mert", "muq", "mulan", "clap"],
    "device": "auto",
    "top_k": 3,
    "track_batch_size": 8,
    "inference_batch_size": 16,
    "mode": "staged",
    "staged": {
      "folder": "D:/MLStaging",
      "copy_workers": 4,
      "decode_workers": 8,
      "stage_size": 64,
      "inference_batch_size": 16,
      "preflight_copy_enabled": true,
      "preflight_copy_count": 64
    }
  }
}
```

`stages` accepts `sonara` and `ml`. Execution order is always SONARA then ML, whatever order the
request lists. The SONARA range is validated before the job is queued, so a range that conflicts
with the stored one returns an error instead of failing mid-run.

SONARA settings: `mode` defaults to `direct`, `direct_batch_size` accepts `1..16`, and `bpm_min`
and `bpm_max` accept `20..400` with the upper bound at least twice the lower. Direct Mode ignores
the nested `staged` block. Staged Mode requires an existing folder and accepts Processes `1..16`,
Threads `1..64`, BatchSize `1..16`, and StageSize `1..512`. Staged SONARA passes temporary copy
paths to native analysis while retaining the original track identity.

ML settings: `mode` defaults to `direct`, and the `staged` block accepts `copy_workers` `1..16`
(default `4`), `decode_workers` `1..32` (default `8`), `stage_size` `1..512` (default `64`),
`inference_batch_size` `1..128` (default `16`), `preflight_copy_enabled` (default `true`), and
`preflight_copy_count` `1..512` (default `64`). The browser exposes the folder, Workers, and
StageSize only.

Following a failed full TorchCodec decode, the requested ML family makes its own in-process PyAV
recovery decode with the shared FFmpeg libraries, keeping the valid frames around any malformed
packet, and then retains its existing model-specific resampling and window preparation.

Database migration is intentionally not an API operation. Use the explicit CLI command
`dj-sim migrate-database` after stopping every SQLite user.

Classifier analysis is always started for one explicit `classifier_key`. Readiness is
manifest-specific, and not-ready tracks are excluded by the candidate query rather than failed. The
`not_ready` field in the status payload is currently a fixed `0` and carries no computed value. All
manual and pipeline stages share one sequential application queue, so a SONARA stage, an ML stage,
and a classifier stage are strictly serialized.

`GET /api/library/summary` reports current coverage for SONARA Core, MAEST analysis and embedding,
MERT, MuQ, MuQ-MuLan, CLAP, likes, and compatible classifiers. Per-track `analysis_coverage` contains
`sonara_core` only for SONARA. Use `GET /api/analysis/sonara/status` for separate current Core,
embedding, and fingerprint counts.

Reset requests use `{ "analysis_family": "sonara" }` (or `maest`, `mert`, `muq`, `mulan`, `clap`).
The typed response returns `feature_rows_deleted`, `embedding_rows_deleted`, and
`classifier_rows_deleted`. What each family deletes:

| Family | Deleted tables | Left in place |
| --- | --- | --- |
| `sonara` | `sonara_features` | `sonara_embeddings`, `sonara_fingerprints` |
| `maest` | `maest_genres`, `maest_embeddings` | none |
| `mert`, `muq`, `mulan`, `clap` | that family's embedding table | none |

`classifier_rows_deleted` is a fixed `0` in every response. Analysis reset never deletes a row from
`classifier_scores`. Clearing classifier scores is a separate call to `/api/classifiers/reset` with
`{ "classifier_key": "live_instrumentation" }`, which takes exactly one key.

Resetting SONARA leaves the embedding and fingerprint rows behind. The next SONARA run selects those
tracks anyway, because their Core row is missing, and one successful pass rewrites all three rows.

## Search and Reference Compare

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/search` | seed search for `maest`, `mert`, `muq`, `mulan`, or `clap` |
| `POST` | `/api/search/random-track` | one random track that has an embedding in the named family |
| `POST` | `/api/search/sonara` | SONARA Core seed search |
| `POST` | `/api/search/sonara/random-track` | one random SONARA-ready track |
| `POST` | `/api/search/text` | CLAP or MuQ-MuLan text-to-track search |
| `POST` | `/api/search/text/warmup` | load one text family before a search waits on it |
| `POST` | `/api/search/text/feedback` | store one relevance verdict per preset |
| `POST` | `/api/reference/compare` | per-model Reference Compare groups for one seed |
| `POST` | `/api/reference/compare/verdict` | save one Reference Compare listening verdict |

Every result-returning search re-checks each hit's `catalog_uuid` and `track_uuid` against fresh
summaries and returns `409` when a row moved underneath the request.

`POST /api/search` accepts:

| Field | Required | Current behavior |
| --- | --- | --- |
| `analysis_family` | no | `maest`, `mert`, `muq`, `mulan`, or `clap`. Defaults to `mert`. |
| `seed_track_ids` | yes | `1..5` entries, and they must be unique. Seeds are excluded from results. |
| `limit` | no | `1..500`. Defaults to `10`. |
| `min_similarity` | no | `0..1` score floor. There is no default threshold. |
| `epsilon` | no | `0` or more. Keeps only candidates within that distance of the best score. |
| `noise` | no | `0..1`, default `0`. Deterministic per-track jitter applied to the ranking order only. The returned `score` is untouched. |

The query vector is the L2-normalized mean of the seed rows. CLAP is accepted here even though the
browser SIMILARITY tab does not offer it.

`POST /api/search/random-track` takes `{analysis_family, exclude_track_ids}` and returns one
`TrackSummaryResponse`. The SONARA variant takes `{exclude_track_ids}` only. Excluded IDs must be
unique. The browser wires both to its **Add Random Track** buttons.

`POST /api/search/sonara` accepts:

| Field | Required | Current behavior |
| --- | --- | --- |
| `seed_track_ids` | yes | `1..5` unique entries. |
| `limit` | no | `1..500`. Defaults to `10`. |
| `mode` | no | `balanced`, `vibe`, `sound`, `dj_transition`, or `custom`. Defaults to `balanced`. |
| `min_similarity` | no | `0..1` score floor. |
| `mixer_weights` | no | Five weights, each `0..5`. Defaults are `timbre 1.0`, `rhythm 1.0`, `dynamics 0.8`, `harmonic 0.8`, `tempo 0.35`. |
| `modifiers` | no | Nine directional knobs, each `-1..1`, all defaulting to `0.0`: `energy`, `valence`, `acousticness`, `brightness`, `rhythm_density`, `dynamic_range`, `loudness`, `vocalness`, `aggression`. |

`mixer_weights` and `modifiers` take effect in `custom` mode. SONARA search reads stored Core
fields. The stored 48-dimensional SONARA embedding is not a search input.

`POST /api/search/text` accepts this JSON contract:

| Field | Required | Current behavior |
| --- | --- | --- |
| `positive_queries` | yes | Non-empty prompt array. Blank entries are removed, every remaining prompt is embedded, and the bank is mean-pooled and normalized. |
| `analysis_family` | no | `"clap"` or `"mulan"`. Defaults to `"clap"`. Search uses only stored audio embeddings from that family. |
| `negative_queries` | no | Prompt array for competing audible classes. Blank entries are removed before contrast scoring. |
| `negative_weight` | no | Number from `0..2`. Defaults to `0.5`. |
| `limit` | no | `1..500`. Defaults to `10`. |
| `min_similarity` | no | Optional API score threshold. There is no default threshold. |
| `device` | no | `"auto"`, `"cpu"`, or `"cuda"`. Selects the text adapter device. |

Unknown fields are rejected. There is no `query`, `preset`, or `adaptive_contrast` field. Results
contain `track`, `score`, and nullable `score_breakdown`. Contrast searches report
`positive`, `negative`, `contrast`, and `negative_weight` in that breakdown. Results stay in
descending score order.

One positive prompt with no negatives runs as a plain vector search. Any other bank runs as a
contrast search. For how the negative term is combined, see
[Similarity scores](../concepts/similarity-scores.md).

Text-search scores are cosine or contrast ranking evidence, not probabilities. Compare them only
within one selected family and prompt bank. Do not compare them with seed-search scores, SONARA,
MERT, or the other text family. The endpoint reads stored embeddings and track rows. It does not
modify source audio, tags, analysis rows, or classifier scores. Browser search does not send
`min_similarity`. It uses `Limit` and keeps the full descending rank. API and CLI threshold
workflows remain separate.

`POST /api/search/text/warmup` takes `{analysis_family, device}` and returns
`{analysis_family, device, seconds}`. It loads the family and embeds one fixed literal prompt. It
touches no database, so it works before any analysis exists. The browser fires it when the PROMPT
tab opens and again on every model change, which is what the loading banner reports.

`POST /api/search/text/feedback` takes `{track_uuid, preset_keys, analysis_family, verdict}` with
`verdict` in `-1`, `0`, or `+1`. It writes one row per `(track, preset_key, analysis_family)` into
`text_preset_feedback`, and `0` withdraws the stored verdicts for those presets. The response is
`{presets, verdict}`, where `presets` counts the affected rows. An unknown `track_uuid` is `404`.
This is the only route that can add a table to an existing library at runtime. See
[Database reference](./database.md#text-preset-feedback).

Reference Compare accepts one `seed_track_id`, optional `models` from `clap`, `mert`, `muq`,
`mulan`, `maest`, and `sonara`, and `limit=1..100`. When `models` is omitted, it returns six
separate default groups in that order, including `mulan`. An unavailable family stays in the
response with `available=false` and a reason. Verdicts use `mood`, `palette`, `instruments`,
`groove`, `genre`, `transition`, or `miss`. They persist as local pair feedback under
`reference_compare:<model>`.

## Evaluation

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/evaluation/summary` | row counts across feedback, profiles, sessions, and calibration runs |
| `POST` | `/api/evaluation/feedback/pair` | record one seed/candidate judgement |
| `POST` | `/api/evaluation/feedback/transition` | record one outgoing/incoming transition judgement |
| `POST` | `/api/evaluation/run/source-profile` | build an unsupervised source-agreement profile |
| `POST` | `/api/evaluation/run/apply-score-profile` | score an existing profile or a weight set |
| `POST` | `/api/evaluation/run/weighted-candidates` | build weighted candidate pools |
| `GET` | `/api/evaluation/reports/latest` | the last recorded calibration runs |

This group has no browser surface. It exists for scripted diagnostics beside the `dj-sim eval`
commands, and both write the same storage.

`GET /api/evaluation/summary` returns `counts` for `pair_feedback`, `transition_feedback`,
`evaluation_profiles`, `search_sessions`, `search_session_seeds`, `search_result_events`, and
`calibration_runs`. The five sidecar-backed counts report `0` when the sidecar file does not exist,
and reading the summary never creates it.

`POST /api/evaluation/feedback/pair` takes `1..5` unique seeds, a `rating` in `0..3`, and
`reason_tags` from a closed vocabulary. Transition feedback takes free-form `risk_tags` instead.
Both write into the main library database rather than the sidecar.

`POST /api/evaluation/run/apply-score-profile` requires exactly one of `profile` or `weights`.
`POST /api/evaluation/run/weighted-candidates` accepts `limit_per_seed` in `1..100`, default `30`,
and its `record_session` defaults to `false`, which is the opposite of the CLI default.

`GET /api/evaluation/reports/latest` returns the last ten `calibration_runs` rows, or
`{"status": "no_persisted_reports"}`. CLI JSON report directories are not scanned by this route.

Any `RuntimeError` or `sqlite3.OperationalError` inside this group becomes a `409` whose detail
starts with "Evaluation API requires the current SQLite structure."

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

`POST /api/export` takes `{name, track_ids, output_dir, format}` with `format` of `m3u` or `csv`,
and returns `{"path": "..."}`. A track ID that is not in the catalog returns `404`.

The two genre routes are the only backend paths that write audio files. Both take an exclusive
database reservation. The request body is empty and forbids extra fields, because the genre API
rejects per-track writes and always writes every available stored MAEST genre. Each write goes
through an expected file state, then re-reads the tags and verifies that the stored genres round-trip
before the write counts as successful.

`POST /api/dialog/folder` opens a native folder picker on the machine running the backend and
returns `{"path": null}` on cancel. It returns `503` when Tk is unavailable.

## Rhythm Lab and server

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/rhythm-lab/status` | status |
| `POST` | `/api/rhythm-lab/launch` | launch or reuse Rhythm Lab |
| `POST` | `/api/rhythm-lab/collections` | save main UI set as collection |
| `POST` | `/api/server/shutdown` | request server shutdown |

`GET /api/rhythm-lab/status` returns `{running, managed, url, source}`. Launch binds the current
database and its `catalog_uuid` to the Lab process, and returns `503` when the launch fails.

`POST /api/rhythm-lab/collections` takes `{name, tracks, source, note, mode}` with at least one
unique track and `mode` of `append` or `replace`.

Server shutdown requires the `X-DJ-Track-Similarity-Action: shutdown-server` header, and returns
`403` without it. On success the route returns `{"status":"shutdown_requested"}`, then schedules
dependent cleanup in the background. When a managed Rhythm Lab server is active, shutdown attempts
to stop it before the main backend process. A Rhythm Lab cleanup failure is logged, and the backend
shutdown still proceeds.

## Static mounts

| Path | Behavior |
| --- | --- |
| `/docs` and `/docs/{path}` | The built VitePress site at `docs/dj-track-similarity/site`, mounted when that folder exists. When it is absent, both paths return a `503` HTML page telling the reader to run the docs build. |
| `/` | The built frontend bundle at `frontend/dist`, mounted when that folder exists. |

Both mounts are registered after the JSON routes, so neither can shadow `/api`. Both paths are
resolved relative to the repository root as seen from the installed package, so a non-editable
site-packages install finds neither.
