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
| `409` current schema required | The selected SQLite file is not the current schema version. Evaluation endpoints require schema v4. |
| `404` | Unknown track, job, or media id. |
| Job `state` | One of `queued`, `running`, `completed`, `cancelled`, or `failed`. |
| `latest` job endpoints | Return `null` when no job of that family has run yet. |

Long-running work (scan, tag refresh, multi-model audio analysis, classifier
scoring, Audio Dedup, genre tag jobs) is started by a `POST` that returns an initial
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

The `q` search parameter keeps substring `LIKE` behavior by default. Pass
`search_mode=fts` to use the explicit token-based FTS5 index instead. FTS is
token-based: it does not match arbitrary substrings inside a token. It is
usually much faster for counting or narrowing token matches, but the paged
track response still sorts results by library order, so first-page latency can
vary for very common terms.

Use `/api/tracks` for paged browsing and `/api/tracks/{track_id}` only when a
full metadata dialog needs one track. This keeps large libraries responsive.

`/api/library/summary` includes a `classifiers` counter. It counts a track only
when the track has stored `track_classifier_scores` rows for every promoted
classifier whose runtime manifest is scoring-compatible.

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
| `POST` | `/api/audio-dedup/jobs` | Start an Audio Dedup report or confirmed apply job. |
| `GET` | `/api/audio-dedup/jobs/latest` | Return latest Audio Dedup job. |
| `GET` | `/api/audio-dedup/jobs/{job_id}` | Return one Audio Dedup job. |
| `POST` | `/api/audio-dedup/jobs/{job_id}/cancel` | Request Audio Dedup cancellation. |
| `GET` | `/api/audio-dedup/jobs/{job_id}/report/xlsx` | Download/open the generated XLSX workbook. |

Job endpoints let the frontend poll long-running work and request cancellation.
Cancellation is cooperative: a job may finish the current track or batch before
it stops.

Audio Dedup jobs read the selected SQLite database and write reports under
`tools/audio-dedup/data/reports` by default. The request body accepts `root`,
optional `path_contains`, `preset`, `min_score`, `min_similarity`,
`limit_groups`, `out_dir`, `apply`, and `confirmation`. `apply=true` is
rejected unless `confirmation` is exactly `APPLY DELETE`. Report-only jobs do
not modify audio files or SQLite rows.

### Analysis and Search

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analysis/jobs` | Start one selected-model audio-analysis job for SONARA, MAEST, MERT, and/or CLAP. |
| `GET` | `/api/classifiers` | List promoted classifiers from `models/classifiers/*/model.json`. |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | Start classifier scoring. |
| `GET` | `/api/classifiers/{classifier_key}/calibration-report` | Return a report-only classifier manifest, coverage, score-distribution, and feedback summary. |
| `GET` | `/api/classifiers/{classifier_key}/label-suggestions` | Return deterministic next-label suggestions from stored classifier scores and feedback rows. |
| `POST` | `/api/classifiers/reset` | Delete stored scores for the given classifier keys. |
| `POST` | `/api/analysis/reset` | Reset one analysis family. |
| `POST` | `/api/search` | Search in MERT embedding space. |
| `POST` | `/api/search/sonara` | Search with Sonara features. |
| `POST` | `/api/search/text` | Search CLAP audio vectors from text. |
| `POST` | `/api/search/hybrid` | Preview weighted rank-fusion over MERT, MAEST, SONARA, and CLAP candidates. |
| `POST` | `/api/set-builder/generate` | Generate an ordered Smart Set Builder preview from manual seeds or auto anchors. |

Use `/api/analysis/jobs` before search endpoints when a library has not been
processed yet. Its request body accepts `models`, `limit`, `device`, `top_k`,
`track_batch_size`, `inference_batch_size`, and optional `classifier_keys`.
`models` defaults to all four audio models (`sonara`, `maest`, `mert`, `clap`)
and must be a subset. It may be an empty list only when `classifier_keys` is
non-empty, which requests classifier scoring for tracks that already have the
required inputs. `limit: null` means all eligible tracks; positive limits count
candidate tracks that are missing at least one selected model or selected
classifier score.

`track_batch_size` controls how many decoded tracks the job holds and processes
together. `inference_batch_size` controls MAEST/MERT/CLAP model forward-pass
batches. The default values are `track_batch_size=4` and
`inference_batch_size=24`. The former single `batch_size` request field is no
longer accepted.

The analysis job skips selected-model results that already exist. Its top-level
status uses `total`, `processed`, `analyzed`, `failed`, and `skipped` for
track-level counters. `model_progress` keeps per-model counters for model-level
writes and failures. Status responses expose `track_batch_size` and
`inference_batch_size`; the legacy response field `batch_size` is not emitted.
`classifier_keys` echoes any promoted classifier scoring requested for the job.
`current_model` identifies which selected model or classifier is currently
running. Empty search results often mean the required Sonara features, MERT
embeddings, or CLAP embeddings are missing for the candidate tracks.

`GET /api/classifiers` needs no database; it discovers promoted profiles on
disk and includes manifest status fields. A missing `model.json` is reported as
`legacy` with warnings. Invalid manifests are listed with errors but are not
accepted for scoring. When a manifest includes `hybrid_signal`, the payload
also exposes that role/axis/label/default-weight metadata for the Hybrid UI.
The older `voice_presence`, `abstract_edge`, `break_energy`, and
`live_instrumentation` keys receive legacy fallback `hybrid_signal` metadata for
compatibility, but new classifier roles should live in `model.json`. The UI can
start promoted classifier scoring from the same analysis control block as the
audio models by enabling `CLASSIFIERS`; the frontend sends
the discovered profile keys as `/api/analysis/jobs` `classifier_keys`. The
analysis job runs those classifiers per decoded track batch after the selected
audio models for that batch complete. If CLAP is selected, the classifier step
waits for CLAP in that batch even though classifier scoring itself only needs
SONARA, MERT, and MAEST inputs. Those inputs must already exist or the matching
audio models must be selected in the same request; otherwise `/api/analysis/jobs`
returns `400` with a dependency error. The standalone
`/api/classifiers/{classifier_key}/analyze` endpoint starts a classifier-only
run for that single classifier key and only tracks missing that classifier
score. The CLASS tab's per-classifier score button first calls
`/api/classifiers/reset` for the selected classifier key, then starts that
classifier-only run, so the button fully recalculates the selected classifier
without touching scores for other promoted classifiers. `/api/classifiers/reset`
accepts a list of classifier keys and deletes their `track_classifier_scores`
rows (an empty list deletes nothing).

`GET /api/classifiers/{classifier_key}/calibration-report` reads stored
`track_classifier_scores`, likes, and app feedback rows for that classifier key.
It returns coverage, score quantiles/buckets, manifest/calibration status, and a
conservative status gate. `insufficient_data` means there are not enough app
feedback rows to treat the output as more than diagnostics. The endpoint does not
decode audio, train a model, write a calibration artifact, or claim benchmark
quality. When the current promoted manifest has a `model_id`, the report also
separates fresh and stale score rows by comparing it with stored
`track_classifier_scores.model_id`; stale rows are warned and are not treated as
fresh calibrated evidence.

`GET /api/classifiers/{classifier_key}/label-suggestions` accepts optional
`mode`, `limit`, and `random_seed` query parameters. Modes are `uncertainty`,
`hard_negative`, `diversity`, `disagreement`, and `high_impact_unlabeled`.
Suggestions are deterministic for the same inputs and use stored rows only; this
API does not create a persistent queue table and is not yet exposed as a full UI
workflow.

The default result limit for `/api/search`, `/api/search/sonara`, and
`/api/search/text` is `10` when a request omits `limit`.

`POST /api/search/hybrid` is a separate explicit preview endpoint. It does not
replace the MERT, SONARA, CLAP, SET, or CLASS paths and it does not change their
scoring or weights. The request accepts `seed_track_ids` (`1-5` ids), optional
`sources` from `mert`, `maest`, `sonara`, and `clap`, optional inline `weights` or a
`score_profile` object, `per_source`, `limit`, `rrf_k`, `random_seed`,
`transition_risk_weight` (`0.0-1.0`, default `0.0`),
`transition_risk_version` (`v2` by default, `v1` for compatibility), optional
`classifier_preferences`, optional `classifier_risk_weights`, and
`include_diagnostics`. It also accepts `record_session` (`false` by default).
If no weights are provided, the requested sources are weighted equally. Inline
weights are normalized internally after finite, non-negative validation, and the
endpoint rejects requests that provide both inline weights and a score profile.
Classifier preferences are signed `-1.0` to `1.0` values keyed by promoted
`classifier_key`; positive values prefer higher stored scores and negative values
prefer lower stored scores. Classifier risk weights are `0.0` to `1.0` values,
used for classifier risk roles such as vocalness or texture. Missing classifier
scores stay neutral. If the selected promoted manifest has a `model_id`, each
stored score's `model_id` is compared against it; stale rows remain usable as
warned local signals but are not reported as fresh calibrated evidence.

Hybrid search generates candidates from the existing exact source search paths,
excludes seed tracks, and fuses source ranks with weighted reciprocal-rank
fusion. CLAP is used as stored audio embeddings only; prompt-aware positive or
negative CLAP hybrid search remains outside this endpoint. With the default
`transition_risk_weight: 0.0`, ordering and score output stay the plain
weighted-RRF preview. When `transition_risk_weight` is greater
than zero, raw RRF scores are normalized within the candidate set and ranked by
`adjusted_score = normalized_rrf_score - transition_risk_weight * transition_risk`;
missing transition risk applies no penalty. The response returns `results`,
`weights_used`, `sources`, `warnings`, diagnostics, and limitations. Each result
has a `track`, a preview rank `score`/`total_score` (the adjusted display score),
`calibrated_score: null`, `adjusted_score`, `raw_rrf_score`,
`transition_risk_penalty`, `transition_risk_weight`, `rank`, per-source
`score_breakdown`, stable `risk_breakdown` (`bpm`, `tonal`, `energy_jump`,
`density_jump`, `texture_clash`, `mood_clash`, `vocal_conflict`,
`source_disagreement`, `confidence_missingness`), `source_support`, optional
`classifier_support`, and `match_character` axes
(`groove`, `density`, `texture`, `mood`, `tonal`, `vocalness`, `energy_flow`,
`novelty`). Missing explanation inputs are shown as neutral/unavailable rather
than as negative evidence. `classifier_support` entries include availability,
stored score, requested preference/risk weight, score/risk contribution,
manifest role/axis/label when known, production/manifest status, and `fresh` /
`stale` identity flags when a current manifest `model_id` can be compared with
the stored score. Rows also include sorted diagnostic `warnings`, short
`explanation` lines, additive `transition_risk` / `transition_diagnostics`, and
existing `feedback` for `source="hybrid_ui"` when that candidate has already been
rated from the UI; missing feedback is `null` and means unrated. With
`record_session: true`, the response includes `session_id` and records one
`hybrid_search_preview` session plus one `search_result_events` row per returned
candidate. Event score breakdown JSON uses diagnostic names such as
`score_kind`, `adjusted_score`, `raw_rrf_score`, `transition_risk`,
`transition_risk_penalty`, `transition_risk_weight`, per-source rank/score
payloads, and the PR-22 explanation fields (`total_score`, `calibrated_score`,
`score_breakdown`, `risk_breakdown`, `source_support`, `classifier_support`,
`match_character`, `warnings`, and `explanation`). The legacy `sources` event payload is preserved
for source-rank readers. Transition diagnostics use
stored BPM half/double compatibility, exact-key equality, energy jump,
source-consensus disagreement, and v2 stored-feature approximations for density,
texture, mood, vocal conflict, and missingness. They are lightweight diagnostic values for future
ranking experiments, not AutoMix, beatgrid or cue-point detection, and not a
calibrated transition estimate. The score is a preview rank score, not a
calibrated estimate of human taste. Missing source
coverage is reported in `warnings`; a configured source with no returned rows is
absent from scoring and transition source-consensus risk. If no source can return candidates, the
endpoint returns an empty result list rather than failing. It reads stored SQLite
analysis data only. By default it writes no rows; with explicit
`record_session: true`, it writes only evaluation session/event rows. It never
writes tags, audio files, classifiers, or production search configuration.

`POST /api/set-builder/generate` is a read-only set preview endpoint. It does
not run audio analysis, score classifiers, save sessions, write tags, or modify
audio files. It uses only stored MERT, MAEST, and CLAP audio embeddings,
stored SONARA playlist features, and optional stored promoted-classifier scores.
MAEST genre labels are not part of candidate selection.

Request fields:

- `seed_mode`: `manual` or `auto`. Manual mode requires `1-5`
  `seed_track_ids` and distributes them as waypoint anchors; auto mode samples
  the first anchor from the full feature-complete library, then samples the
  remaining waypoint anchors from related candidates.
- `seed_track_ids`: manual seed track IDs. Ignored in auto mode.
- `auto_seed_count`: number of waypoint anchors to use in auto mode, `1-5`.
- `mode`: `similar_crate`, `weird_adjacent`, `balanced_set`, or `discovery`.
- `limit`: preview length, default `24`.
- `diversity`: `0.0-1.0`, used during ordering.
- `energy_curve`: `warmup`, `balanced`, `peak`, or `wave`.
- `bpm_mode`: `general`, `low_to_high`, or `high_to_low`. `general`
  keeps the older soft BPM/key transition behavior without a separate tempo
  trajectory.
- `bpm_change`: `slow`, `medium`, or `fast`, used only when `bpm_mode` is not
  `general`.
- `bpm_start`, `bpm_target`: optional `20-300` BPM values for the tempo
  trajectory. When omitted, the builder infers them from the first seed/anchor
  and the available library BPM range.
- `classifier_preferences`: maps from promoted `classifier_key` to a signed
  `-1.0` to `1.0` preference. Positive values prefer higher classifier scores;
  negative values prefer lower classifier scores; `0.0` is ignored.
- `classifier_flows`: maps from promoted `classifier_key` to `flat`, `rise`,
  or `fall`. `flat` applies the preference evenly, `rise` increases that
  preference toward the end of the preview, and `fall` starts stronger then
  eases off.
- `random_seed`: optional integer for reproducing one randomized generation.
  Omit it for a fresh randomized auto/ordering pass.

The response includes `seed_track_ids`, feature coverage counters, and ordered
`items`. Each item has a `track`, `reason`, `score`, `score_breakdown`,
`sonara_groups`, `classifier_scores`, and transition metadata. Seeds or auto
anchors are included in the returned sequence with `reason=seed_anchor` and are
distributed through the ordered preview as waypoint items. In SET preview items,
`track.bpm` is the effective BPM used by SET ordering: file-tag BPM first, then
SONARA fallback only when the tag is missing.

Tracks missing any required MERT, MAEST, CLAP, or SONARA input are excluded
from candidate generation. Missing classifier scores are allowed: they simply
produce neutral classifier contribution and lower classifier confidence in the
score explanation. BPM/key ordering is soft and uses file tags first, with
SONARA values as fallback. If an explicit BPM mode is selected, actual track
BPM also contributes an ordered low-to-high or high-to-low tempo curve; missing
BPM stays neutral rather than excluding the track. In auto mode, the first
anchor is sampled before the related candidate prefilter so it can start from
the full eligible library. Active classifier preference and flow controls can
bias that start anchor and later auto-anchor selection, using stored scores
only. The ordered preview also applies a strict artist guard: each known artist
may appear at most once in one preview. Manual seeds are included as distributed
`seed_anchor` waypoint items, but duplicate known artists among manual seeds are
rejected. Later auto anchors and non-seed positions are sampled from mode-scored
pools, so repeated calls without `random_seed` can return different related
sets.

`POST /api/search/text` accepts `query`, `limit`, optional `min_similarity`,
and optional `device`. It also accepts adaptive contrast fields:
`positive_queries`, `negative_queries`, `adaptive_contrast`, and `preset`.
When `adaptive_contrast` is true and at least one `negative_queries` item is
present, the endpoint embeds every positive and negative prompt and ranks CLAP
audio vectors by `max positive similarity - max negative similarity`. Without a
negative prompt it falls back to direct CLAP text-vector search for the first
positive query.

Reset scope by family:

| Reset | Removes |
| --- | --- |
| `/api/analysis/reset` `sonara` | `sonara_*` metadata keys; recomputes stored BPM/key/energy/duration from remaining metadata. |
| `/api/analysis/reset` `maest` | `maest_*` metadata keys plus `maest` embeddings. |
| `/api/analysis/reset` `mert` / `clap` | Embeddings of that key. |
| `/api/classifiers/reset` | `track_classifier_scores` rows for the listed classifier keys. |

### Evaluation API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/evaluation/summary` | Return row counts for v4 evaluation tables. |
| `POST` | `/api/evaluation/feedback/pair` | Upsert optional manual audit feedback for one seed/candidate pair. |
| `POST` | `/api/evaluation/feedback/transition` | Append optional manual audit feedback for one outgoing/incoming transition. |
| `POST` | `/api/evaluation/run/source-profile` | Run the automatic unsupervised source-profile diagnostic in-process. |
| `POST` | `/api/evaluation/run/apply-score-profile` | Apply an inline score profile to recorded candidate pools. |
| `POST` | `/api/evaluation/run/weighted-candidates` | Generate a capped weighted candidate-pool preview from an inline score profile. |
| `GET` | `/api/evaluation/reports/latest` | Return persisted `calibration_runs` rows, if any. |

These endpoints are for local evaluation diagnostics only. They do not read or
modify audio files, do not train classifiers, do not use Rhythm Lab labels or
liked tracks as ground truth, and do not change production search endpoints,
scoring, or weights.
PR-23 judged-only validation is primarily a CLI/report mode for `dj-sim eval
report`, `run-ablation`, and `run-calibration`. The API does not expose separate
report/ablation/calibration run endpoints in this pass; the existing
`apply-score-profile` response includes the same matched judged-label gate fields
when it summarizes recorded candidate pools.

`/api/evaluation/summary` returns `schema_version` plus counts for
`search_sessions`, `search_result_events`, `track_pair_feedback`,
`transition_feedback`, and `calibration_runs`. Evaluation endpoints require a
selected current schema v4 database; older databases return a clear schema error.

Pair feedback accepts optional `session_id`, `seed_track_ids` (`1-5` ids),
`candidate_track_id`, `rating` (`0-3`), optional `reason_tags`, optional
`notes`, and `source` (default `manual`; the Hybrid UI uses `hybrid_ui`). It
upserts one row per seed using `(seed_track_id, candidate_track_id, source)`, so
submitting the same candidate rating again updates existing rows instead of
growing the label count. Allowed pair `reason_tags` are `good_groove`,
`good_density`, `good_texture`, `good_mood`, `good_tonal`, `too_vocal`,
`bad_density`, `bad_tonal`, `too_obvious`, `interesting_adjacent`,
`wrong_energy`, `wrong_texture`, and `bad_transition_risk`. Transition feedback
accepts `outgoing_track_id`, `incoming_track_id`,
`rating` (`0-3`), optional `risk_tags`, optional `notes`, and `source` (default
`manual`) and appends a new audit row. Manual feedback is optional audit and
validation data, not classifier training data and not required by the automatic
source-profile path.

`/api/evaluation/run/source-profile` accepts optional `seed_track_ids`; when they
are omitted, it samples `sample_count` seeds (default `50`) with `random_seed`
(default `123`). It also accepts `sources` (default `mert`, `maest`, `sonara`, `clap`),
`per_source` (default `30`), `top_k` (default `[10]`), optional `profile_name`,
and `include_profile` (default `true`). The response contains `source_profile`
diagnostics and, when the diagnostic status is `ok` and `include_profile` is
true, a compact `score_profile` JSON object with
`weight_kind: "unsupervised_internal_profile"`. The API does not write a score
profile artifact file and does not record candidate-pool sessions by default.

`/api/evaluation/run/apply-score-profile` accepts either a complete inline
`profile` object or normalized `weights` plus an optional `name`, along with `k`
(default `[5, 10]`) and `rrf_k` (default `60`). It applies the score profile to
already recorded candidate pools in SQLite and returns the same kind of report as
the CLI `apply-score-profile` command. Without pair feedback it still ranks the
candidate pools, but reports `label_status: "insufficient_data"` and makes no
claim about human taste. Under PR-23, `label_status`, `judged_pairs`,
`judged_seeds`, `can_create_candidate_profile`, `can_update_defaults`, and
`label_guidance` are based only on feedback labels that match recorded result
events, not on all feedback rows in the database.

`/api/evaluation/run/weighted-candidates` accepts the same inline `profile` or
`weights` plus optional `name`, optional `seed_track_ids`, `sample_count` (default
`50` when seeds are omitted), optional `sources`, `per_source` (default `30`, max
`100`), `random_seed`, `rrf_k`, `transition_risk_weight` (`0.0-1.0`, default
`0.0`), `record_session` (default `false` for API safety), and `limit_per_seed`
(default `30`, max `100`) for response capping. It generates a fresh candidate
pool and returns JSON preview rows sorted by weighted RRF over source ranks by
default. When the optional transition-risk weight is greater than zero, rows are
sorted by the same diagnostic adjusted score used by Hybrid preview; the row
payload includes `adjusted_score`, `raw_rrf_score`, `transition_risk`,
`transition_risk_penalty`, and `transition_risk_weight`. Transition risk remains
a v2 diagnostic preview signal, not AutoMix, beatgrid/cue detection, confidence, or
a calibrated transition probability. The requested sources must match the score
profile source set; missing weights or omitted profile sources return a clear
`400` error. With `record_session: true`, it records explicit
`evaluation_weighted_candidate_pool` sessions and profile-ranked result events
only; by default it writes no database rows.

`/api/evaluation/reports/latest` deliberately does not scan arbitrary report
directories. CLI JSON reports are local filesystem artifacts; the API only
returns persisted `calibration_runs` rows from the selected database, or a
`no_persisted_reports` summary when none exist.

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
If preview preparation fails, for example because FFmpeg rejects a malformed
file, the endpoint returns HTTP `422` with the FFmpeg error text instead of
raising an internal traceback.

Use `/api/export` for playlist/report files. Prefer `/api/tags/genres/jobs` for
genre writes so progress and cancellation are available; the synchronous
`/api/tags/genres/apply` returns one result row per track but blocks until the
whole batch finishes.
