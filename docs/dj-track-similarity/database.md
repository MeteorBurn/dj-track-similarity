# Database and Stored Data

This page documents the current SQLite schema and the metadata/analysis payloads
stored in SQLite. Use it when you want to understand what the app saves, what a
reset removes, or why one search mode needs a particular analysis pass first.

## SQLite Specification

The current schema version is `4`.

Existing schema version `2` or `3` library databases are not migrated
automatically by the app. For v2 databases, run the standalone v3 migration
script first, with dry-run as the default mode:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_database_v3.py --db .\data\library.sqlite
.\.venv\Scripts\python.exe scripts\migrate_database_v3.py --db .\data\library.sqlite --apply
```

The script creates an online SQLite backup before `--apply`. Close the running
app before applying the migration to the same database. The same script also
backfills the v3 FTS search table for databases that were already migrated to
v3 before the FTS index existed; this is still an explicit script action, not a
runtime migration.

Schema v4 is created as an explicit one-off copy from a complete v3 library
database. The source v3 file is opened read-only, the destination must be a new
path unless `--force` is supplied, and the app does not perform this conversion
at runtime:

```powershell
.\.venv\Scripts\python.exe scripts\create_library_v4_from_v3.py --source .\data\library_v3.sqlite --dest .\data\library_v4.sqlite
.\.venv\Scripts\python.exe scripts\create_library_v4_from_v3.py --source .\data\library_v3.sqlite --dest .\data\library_v4.sqlite --apply
```

The database is local user state. Normal scan, analysis, search, reset, clear,
and relocation workflows modify SQLite records only; they do not rewrite audio
files. The explicit exception is the separate MAEST genre tag write workflow,
which is documented in [Search & Tags](search-and-tags.md).

### `tracks`

Stores one row per indexed audio file:

- `id`: stable local track ID.
- `path`: unique stored audio path.
- `size`: file size at scan time.
- `mtime`: file modification time at scan time.
- `artist`, `title`, `album`: selected file metadata.
- `bpm`, `musical_key`, `energy`, `duration`: working fields used by the UI and
  analysis flows.
- `has_sonara_analysis`, `has_maest_embedding`, `has_mert_embedding`,
  `has_clap_embedding`: derived presence flags maintained by analysis writes
  and resets. They speed up library summary counters and missing-analysis
  candidate selection. They represent stored analysis presence, not a
  stale/fresh policy.
- `metadata_json`: JSON object for Mutagen fields and model-derived metadata.
- `created_at`, `updated_at`: local row timestamps.

`metadata_json` must be valid JSON. The schema has triggers to reject invalid
JSON on insert or update.

The v3 schema includes partial indexes for both missing and present analysis
flags. These indexes are used by library summary counters and by analyzer
candidate selection, so running analysis on a mostly complete large library
does not need to scan the full `tracks` table to find the small set of missing
SONARA, MAEST, MERT, or CLAP rows.

Use this table to answer "what tracks are in the library?" and "what metadata
or analysis summaries does the UI show for a row?" The `path` is the link back
to the local audio file; relocation updates that stored path only when the same
files moved to a new root.

### `embeddings`

Stores model vectors by track and embedding space:

- `track_id`: references `tracks.id`.
- `embedding_key`: currently `mert`, `clap`, or `maest`.
- `model_name`: model or checkpoint identifier.
- `dim`: vector dimension.
- `vector`: binary float32 vector payload.
- `updated_at`: local row timestamp.

The primary key is `(track_id, embedding_key)`, so the same track can have MERT,
CLAP, and MAEST vectors without mixing those spaces.

Use this table to check whether an embedding-backed workflow has enough data:
MERT search needs `mert`, CLAP text search needs `clap`, and promoted combined
classifiers need `mert` plus `maest` alongside Sonara features.

### `library_settings`

Stores local database-level settings such as the selected music root.

Use this table for app-level preferences tied to one database rather than one
track.

### `track_likes`

Stores the local liked-track list:

- `track_id`: references `tracks.id`.
- `liked_at`: local timestamp for the latest like action.

The primary key is `track_id`, so a track is either liked or not liked. Rows are
deleted automatically when the related track is removed from the local library
database. Likes are app state only; they never write to audio files or Mutagen
tags.

### `track_classifier_scores`

Stores derived outputs from promoted Rhythm Lab classifier profiles by track and
classifier key. It is not used for `dj-sim eval profile-sources` automatic score
profiles, which remain JSON report artifacts outside SQLite:

- `track_id`: references `tracks.id`.
- `classifier`: classifier key such as `live_instrumentation`.
- `score`: primary user-facing score used for filtering.
- `label`: coarse label such as `high`, `medium`, or `low`.
- `confidence`: maximum class probability from that promoted classifier output;
  it is not calibrated confidence and is unrelated to automatic source-profile
  weights.
- `probabilities_json`: classifier probabilities keyed by the profile's
  training labels.
- `feature_set`: feature family used by the classifier artifact, currently
  `combined`.
- `model_id`: promoted model path used for scoring.
- `analyzed_at`: local scoring timestamp.

The primary key is `(track_id, classifier)`, so rerunning a classifier updates
the score for that track instead of appending historical rows.

Use this table when a CLASS filter does not behave as expected. Missing rows
usually mean the promoted classifier has not scored that track yet, or the track
was missing required Sonara, MERT, or MAEST inputs during scoring.

### `track_search_fts`

Stores a derived FTS5 index for explicit token-based library search:

- `track_id`: stable local track ID, stored unindexed for joins back to
  `tracks.id`.
- `search_text`: materialized artist, title, album, path, and `metadata_json`
  text.

The default library search still uses substring `LIKE` semantics. FTS is used
only when the caller explicitly requests `search_mode=fts`. FTS token matching
can make broad count and filter work much cheaper, but sorted first pages can
still be dominated by the library-order sort when the token is very common.
Scan/upsert, RefreshTags, MAEST genre saves, Sonara metadata saves, resets that
edit metadata, library relocation, and clear-library operations maintain the FTS
rows in the same SQLite write transaction as the related `tracks` update.

### Evaluation and calibration tables

Schema v4 adds local evaluation tables for future search-quality and transition
calibration work:

- `search_sessions`: one row per explicitly recorded evaluation search request,
  with JSON seed track IDs and request payload.
- `search_result_events`: ranked result rows tied to a recorded search session
  and candidate track, with a JSON score breakdown.
- `track_pair_feedback`: manual or tool-sourced ratings for seed/candidate pairs.
  Ratings are `0` through `3`; reason tags are stored as JSON. The unique key is
  `(seed_track_id, candidate_track_id, source)` so repeated feedback from the
  same source updates the same row.
- `transition_feedback`: append-only ratings and risk tags for outgoing/incoming
  transition pairs.
- `calibration_runs`: diagnostic/report-only calibration profile/config/metrics
  JSON snapshots.

These rows are app evaluation data only. They are not Rhythm Lab classifier
labels, not `track_likes`, and not file tags. Foreign keys cascade when related
local `tracks` or `search_sessions` rows are removed. Recording evaluation data
updates SQLite only and never writes to audio files.

The Hybrid preview UI writes pair labels with `source="hybrid_ui"`. One UI
rating over `1-5` selected seeds upserts one `track_pair_feedback` row per seed
for the same candidate. Repeating the rating updates those rows instead of
adding duplicates, and Hybrid search results hydrate any existing `hybrid_ui`
feedback so labels survive refresh. The UI reason-tag allowlist is
`good_groove`, `good_density`, `good_texture`, `good_mood`, `good_tonal`,
`too_vocal`, `bad_density`, `bad_tonal`, `too_obvious`,
`interesting_adjacent`, `wrong_energy`, `wrong_texture`, and
`bad_transition_risk`.

Manual pair and transition feedback can be imported with `dj-sim eval` commands
from CSV or JSONL files. These CSVs/JSONL files are optional audit and validation
inputs, not classifier training data, and automatic source profiling does not
require them.
Search-quality reports use only explicit evaluation feedback plus already
recorded search sessions/result events; likes and Rhythm Lab labels are not
treated as ground truth by default.
PR-23 judged label gates count only feedback rows that can be matched back to a
recorded `search_result_events` row for the same seed/candidate/source. Extra
feedback rows that do not appear in a recorded result are still stored as audit
data but do not raise `judged_pairs` for judged-only reports. The gate is:
fewer than 50 matched judged pairs is `insufficient_data`, 50-199 is diagnostics
only, 200-499 may justify considering a candidate score profile, and 500+ may
justify considering a default update through explicit manual review only. No
report updates production defaults automatically.

`dj-sim eval export-candidates` can create blinded manual-labeling CSVs from
existing exact MERT, MAEST, balanced SONARA, and CLAP audio-embedding search sources. With session
recording enabled, it stores one `evaluation_candidate_pool` search session per
seed and records the blinded candidate order in `search_result_events`; the score
breakdown contains source ranks/scores and `blind_rank`. The generated CSV still
requires human ratings before `import-pair-feedback` turns those rows into ground
truth.

`dj-sim eval run-calibration` builds diagnostic calibration JSON from recorded
candidate-pool events and imported pair feedback. It records nothing by default;
with explicit `--record`, only an `ok` summary is inserted into
`calibration_runs` using profile `manual_feedback`. Raw scores and RRF-derived
diagnostic scores are stored and reported as diagnostics, not as production
confidence or probabilities, and calibration reports do not change runtime search
weights or thresholds.

`dj-sim eval profile-sources` is the automatic unsupervised source profiling
path. It reads existing MERT, MAEST, SONARA, and CLAP analysis data for sampled seeds,
computes coverage, rank agreement, RRF-style consensus support, conflicts, score
quantiles, and normalized internal source weights. A selected source with no
coverage receives warning diagnostics and zero weight instead of penalizing other
sources. It does not write to the
database, does not use manual labels as required ground truth, does not calibrate
probabilities, and does not prove human DJ taste without external validation.

`dj-sim eval profile-sources --profile-output <json>` saves those normalized
internal weights as a schema-validated JSON score profile artifact, usually under
`reports/experiments/` or another user-selected reports path. Schema validation
checks the artifact shape only; it is not external validation of human DJ taste.
Score profiles are not stored in SQLite in schema v4, do not create a schema v5
migration, do not train classifiers, and do not change production search
endpoints.
`dj-sim eval apply-score-profile --profile <json>` applies the artifact to
recorded candidate pools with weighted RRF over stored source ranks. If pair
feedback exists it includes validation metrics; without labels it still reports
rankings with `label_status: "insufficient_data"` and no quality claim.

`dj-sim eval export-weighted-candidates --profile <json>` creates a fresh
weighted candidate-pool CSV from the same artifact. With default session recording
it stores one `evaluation_weighted_candidate_pool` search session per seed and
records profile-ranked `search_result_events`; each score breakdown includes the
weighted-RRF components, profile weights, source ranks, and original source
rank/score payloads. This is explicit evaluation/future-ranker logging only and
does not affect production search endpoints.

`POST /api/search/hybrid` remains read-only unless the request sets
`record_session: true`. In that opt-in mode it records one `hybrid_search_preview`
session for the request seed list and one `search_result_events` row per returned
candidate. The event score breakdown stores diagnostic names such as
`score_kind`, `adjusted_score`, `raw_rrf_score`, `transition_risk`,
`transition_risk_penalty`, `transition_risk_weight`, and per-source rank/score
payloads. It also stores PR-22 explanation fields (`total_score`,
`calibrated_score: null`, `score_breakdown`, `risk_breakdown`, `source_support`,
`match_character`, `warnings`, and `explanation`) while preserving the legacy
`sources` payload used by reports, calibration, and ablation readers. These are
ranking diagnostics, not production weights or calibrated human-taste estimates.

The local Web API exposes the same evaluation data under `/api/evaluation/*`.
The API summary endpoint reads only these v4 tables, manual feedback endpoints
write only the optional audit/validation rows described above, and the automatic
source-profile/apply-score-profile endpoints are read-only diagnostics over
stored analysis and recorded candidate pools. The weighted-candidates endpoint is
also explicit evaluation-only and writes no rows unless `record_session` is set.
They do not scan report directories, do not write score-profile artifact files,
and do not change production search scoring.

## Metadata and Analysis Data

The app deliberately separates file tags from computed values.

Mutagen scanning reads this fixed whitelist:

- `artist`
- `title`
- `album`
- `genre`
- `year`
- `country`
- `label`
- `catalog_number`
- `track_number`
- `disc_number`
- `bpm`
- `key`
- `comment`
- `isrc`
- `duration`
- `audio_format`
- `audio_codec`
- `date`

Values are normalized into JSON-safe values before being stored. Mutagen-specific
objects such as ID3 timestamps are converted to strings.

`RefreshTags` replaces only this Mutagen metadata subset. It preserves stored
paths and model analysis data.

Analysis outputs live beside those file tags instead of replacing them. This is
why a track can show both file metadata such as `genre` or `bpm` and computed
values such as Sonara BPM, MAEST genres, embeddings, or classifier scores.
