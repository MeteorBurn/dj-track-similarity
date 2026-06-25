# CLI Reference

This page documents the `dj-sim` command line interface. Use the CLI for
repeatable local workflows, batch analysis, quick diagnostics, and operations
that are easier to review in a terminal than in the web UI.

## CLI Reference

Install the project first so `dj-sim` is available:

```powershell
python -m pip install -e ".[dev]"
```

Each database-aware command declares its own `--db` option; there is no global
`--db`. Use `--db` to target a specific SQLite database. When `--db` is omitted,
those commands default to:

```text
dj-track-similarity.sqlite
```

in the current working directory. The `doctor` command does not touch any
database and therefore accepts no `--db`.

## Choosing a Command

| Goal | Command |
| --- | --- |
| Add or refresh tracks from a folder | `dj-sim scan` |
| Start the local web UI/API server | `dj-sim serve` |
| Build SONARA, MAEST, MERT, and/or CLAP analysis | `dj-sim analyze` |
| Score a promoted Rhythm Lab classifier | `dj-sim analyze-classifier` |
| Search with a CLAP text prompt | `dj-sim text-search` |
| Import manual evaluation labels or build a search-quality report | `dj-sim eval` |
| Update stored paths after moving a library | `dj-sim relocate-library` |
| Check Python, PyTorch, and CUDA setup | `dj-sim doctor` |

### `dj-sim`

```powershell
dj-sim [OPTIONS] COMMAND [ARGS]...
```

App-level options (Typer built-ins, not a shared `--db`):

| Option | Meaning |
| --- | --- |
| `--install-completion` | Install shell completion for the current shell. |
| `--show-completion` | Print shell completion code. |
| `--help` | Show help. |

> Note: `--db` is not an app-level option. It is repeated on each command that
> reads or writes a database. The job-based `analyze` command renders a live
> progress bar; `scan`, `relocate-library`, `analyze-classifier`,
> `text-search`, `eval`, `doctor`, and `serve` print plain output only.

Commands:

```text
scan
relocate-library
analyze
analyze-classifier
doctor
text-search
eval
serve
```

### `dj-sim scan`

Scan a music folder and add or update SQLite track rows.

```powershell
dj-sim scan <path-to-music> --db .\data\library.sqlite
```

Usage:

```text
dj-sim scan [OPTIONS] MUSIC_ROOT
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `MUSIC_ROOT` | path | yes | Folder scanned recursively for supported audio files. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--help` | flag | off | Show help. |

Output:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

`scan` reads audio metadata and writes SQLite only. It does not modify audio
files. AppleDouble resource-fork files such as `._track.aiff` are skipped.

Use this first for a new database, and rerun it after adding files to the music
folder. Existing analysis is kept for unchanged tracks.

### `dj-sim serve`

Start the local FastAPI server and serve the frontend.

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Usage:

```text
dj-sim serve [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--host` | text | `127.0.0.1` | Bind address for the local server. |
| `--port` | integer | `8765` | HTTP port. |
| `--db` | path | none | Optional SQLite database path. Without it, choose/create a database in the UI. |
| `--log-level` | text | `info` | File log level: `debug`, `info`, `warning`, `error`, or `critical`. |
| `--log-track-events` | flag | off | Write successful per-track events to the file log. |
| `--help` | flag | off | Show help. |

Then open:

```text
http://127.0.0.1:8765/
```

There is also a Windows helper:

```powershell
scripts\run_server.cmd
```

For local-network access from another device on the same LAN, use:

```powershell
run_server_lan.cmd
```

It activates `.venv`, starts `dj-sim serve --host 0.0.0.0 --port 8765`, and
prints the LAN URL to try from another device. Windows Firewall may still need
to allow Python for inbound local-network connections.

Use `serve` when you want the browser workflow: paged browsing, playback
preview, analysis controls, search tabs, classifier filters, exports, and
metadata review.

### `dj-sim analyze`

Analyze missing SONARA, MAEST, MERT, and/or CLAP results in one job. By
default, all four audio models are selected.

```powershell
dj-sim analyze --models sonara,maest,mert,clap --device auto --track-batch-size 4 --inference-batch-size 24 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of candidate tracks to analyze. |
| `--models` | comma-separated text | `sonara,maest,mert,clap` | Selected analysis models. Valid values: `sonara`, `maest`, `mert`, `clap`. |
| `--device` | text | `auto` | MAEST/MERT/CLAP device: `auto`, `cpu`, or `cuda`. |
| `--top-k` | integer `1..10` | `3` | Number of MAEST genre labels to store per track. |
| `--track-batch-size` | integer `1..64` | `4` | Number of decoded tracks held and processed together. |
| `--inference-batch-size` | integer `1..128` | `24` | MAEST/MERT/CLAP model inference batch size. |
| `--diagnostics` | flag | off | Write decoder fallback and batch timing diagnostics to the file log. |
| `--help` | flag | off | Show help. |

Examples:

```powershell
dj-sim analyze --db .\data\library.sqlite
dj-sim analyze --models maest,mert --device cpu --track-batch-size 2 --inference-batch-size 4 --db .\data\library.sqlite
dj-sim analyze --models clap --device cuda --track-batch-size 4 --inference-batch-size 24 --db .\data\library.sqlite
```

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> models=<models> device=<device> top_k=<n> track_batch_size=<n> inference_batch_size=<n>
```

`processed`, `analyzed`, and `failed` are track-level counters. Per-model
successes and failures remain available in the web/API `model_progress` status.

`auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU. Explicit `cuda`
fails if CUDA is unavailable.

Candidate selection is per track: a track enters the job if it is missing at
least one selected model. Existing selected-model results are skipped, and
tracks missing only unselected models are ignored. The job decodes each track
once per in-memory batch, then runs the missing selected models in this order:
SONARA, MAEST, MERT, CLAP.

Use `--models sonara` for the SONARA search tab and visible feature groups.
Use `--models maest` before reviewing generated genres, using the `syncopated`
preset, or scoring promoted combined Rhythm Lab classifiers. Use `--models mert`
for seed-track similarity and `--models clap` before CLAP text search. MAEST
analysis writes SQLite genre metadata and a MAEST embedding vector; it does not
write genre tags to audio files by itself.

### `dj-sim analyze-classifier`

Score tracks with a promoted classifier profile.

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-classifier CLASSIFIER [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `CLASSIFIER` | text | required | Classifier key, for example `live_instrumentation`. |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--model` | path | `models/classifiers/<artifact-prefix>/model.joblib` | Optional classifier artifact path. |
| `--limit` | integer | none | Maximum number of feature-complete tracks to score. |
| `--help` | flag | off | Show help. |

Output:

```text
classifier=live_instrumentation scored=<n> skipped=<n> model=<path>
```

The command reads existing SONARA, MERT, and MAEST data. Tracks missing any
required input are skipped. Scores are upserted into `track_classifier_scores`.
Unlike the three `analyze*` job commands, classifier scoring runs synchronously
and prints a single summary line instead of a live progress bar.

Use this after promoting a model from Rhythm Lab. If many tracks are skipped,
run Sonara, MERT, and MAEST analysis for those tracks first.

### `dj-sim text-search`

Run CLAP text-to-audio search.

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim text-search [OPTIONS] QUERY
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `QUERY` | text | yes | Text description embedded by CLAP. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer `1..500` | `50` | Maximum result count. |
| `--min-similarity` | float | none | Optional minimum score threshold. |
| `--device` | text | `auto` | CLAP device: `auto`, `cpu`, or `cuda`. |
| `--help` | flag | off | Show help. |

Output rows:

```text
<score>    <track_id>    <path>
```

CLAP audio embeddings must exist before text search can return useful results.

Use this for exploratory searches where a text description is faster than
choosing seed tracks. Concrete prompts with mood, rhythm, instrumentation, and
vocal presence tend to be more useful than a single broad genre.

### `dj-sim eval`

Build local evaluation diagnostics for schema v4 SQLite databases. Manual
evaluation labels are optional validation/audit data, not classifier training and
not required for automatic source profiling. Reports that depend on recorded
`search_sessions` / `search_result_events` can still be `insufficient_data` until
a workflow has recorded evaluation sessions and result events.

```powershell
dj-sim eval export-seed-sample --db .\data\library_v4.sqlite --output .\labels\seed_sample.csv --count 50 --random-seed 123
dj-sim eval export-candidates --db .\data\library_v4.sqlite --output .\labels\candidate_pool.csv --seed-track-id 42 --source mert --source maest --source sonara --source clap --per-source 10 --random-seed 123
dj-sim eval import-pair-feedback --db .\data\library_v4.sqlite --input .\labels\pair_feedback.csv
dj-sim eval import-transition-feedback --db .\data\library_v4.sqlite --input .\labels\transition_feedback.jsonl
dj-sim eval profile-sources --db .\data\library_v4.sqlite --seed-sample .\labels\seed_sample.csv --output .\reports\source_profile.json --profile-output .\reports\score_profile_auto.json --profile-name auto_source_profile --source mert --source maest --source sonara --source clap --per-source 30 --random-seed 123
dj-sim eval export-weighted-candidates --db .\data\library_v4.sqlite --profile .\reports\score_profile_auto.json --output .\labels\weighted_candidate_pool.csv --seed-sample .\labels\seed_sample.csv --per-source 30 --random-seed 123 --rrf-k 60
dj-sim eval apply-score-profile --db .\data\library_v4.sqlite --profile .\reports\score_profile_auto.json --output .\reports\score_profile_apply.json --k 5 --k 10 --rrf-k 60
dj-sim eval sweep-risk-penalty --db .\data\library_v4.sqlite --profile .\reports\score_profile_auto.json --output .\reports\risk_penalty_sweep.json --weight 0 --weight 0.25 --weight 0.5 --weight 1.0 --k 5 --k 10 --rrf-k 60
dj-sim eval run-ablation --db .\data\library_v4.sqlite --output .\reports\ablation.json --k 5 --k 10 --rrf-k 60 --score-profile .\reports\score_profile_auto.json
dj-sim eval run-calibration --db .\data\library_v4.sqlite --output .\reports\calibration.json --score-mode rrf --bins 10 --min-samples 30 --accepted-threshold 2
dj-sim eval report --db .\data\library_v4.sqlite --output .\reports\evaluation.json --k 5 --k 10
dj-sim eval report --db .\data\library_v4.sqlite --output .\reports\evaluation_judged.json --judged-only
dj-sim eval run-ablation --db .\data\library_v4.sqlite --output .\reports\ablation_judged.json --judged-only
dj-sim eval run-calibration --db .\data\library_v4.sqlite --output .\reports\calibration_judged.json --judged-only
dj-sim eval optimize-score-profile --db .\data\library_v4.sqlite --output .\reports\score_profile_optimizer.json --objective balanced --split-by seed --min-judged-pairs 200 --rrf-k 60 --grid-step 0.25 --bootstrap-samples 30
```

For automatic source diagnostics, run `profile-sources` first. It samples or
reads seed IDs, asks each selected source for top candidates, and computes
coverage, top-K overlap/Jaccard, rank agreement, RRF-style consensus support,
conflict rates, score quantiles, and normalized internal weights from
internal agreement/coverage/stability. The JSON has
`profile_kind: "unsupervised_source_profile"` and
`weight_kind: "unsupervised_internal_profile"`. These weights are not trained,
not probability calibration, and not proof of human DJ taste without external
validation.

When `profile-sources` is run with `--profile-output`, it also writes a reusable
score profile JSON artifact with `profile_kind: "unsupervised_source_profile"`,
`weight_kind: "unsupervised_internal_profile"`, `sources`, and normalized
`weights`. This is not classifier training, probability calibration, or proof of
human taste; it is an unsupervised internal weighting profile based on coverage,
agreement, consensus, and conflicts in the current analysis data. Score profiles
are JSON artifacts under a path you choose, such as `reports/experiments/`, and
schema v4 does not add a database table for them.

Candidate-pool export is the recommended first step when collecting optional new
manual ground truth:

1. Run `dj-sim eval export-seed-sample` to choose a reproducible, practical set
   of seed tracks for manual labeling.
2. Run `dj-sim eval export-candidates` for the exported seed IDs, usually with
   `--source mert --source maest --source sonara --source clap` and session recording enabled.
3. Open the generated candidate CSV and fill `rating`, `reason_tags`, and `notes`
   by hand.
4. Import the completed file with `dj-sim eval import-pair-feedback`.
5. Run `dj-sim eval profile-sources --profile-output <json>` any time you want
   automatic unsupervised source reliability diagnostics and a schema-validated
   score profile artifact from existing analysis data.
6. Run `dj-sim eval export-weighted-candidates --profile <json>` when you want a
   fresh candidate CSV already ordered by the automatic score profile for an
   explicit future-ranker preview. It uses weighted RRF over per-source ranks,
   not raw source score magnitudes, and records
   `evaluation_weighted_candidate_pool` sessions by default unless
   `--no-record-session` is passed.
7. Run `dj-sim eval apply-score-profile --profile <json>` to rank recorded
   candidate pools with weighted RRF over per-source ranks. If imported pair
   feedback exists, the report includes the same ranking metrics as ablation; if
   no labels exist, it still reports rankings with
   `label_status: "insufficient_data"` and makes no quality claim.
8. Run `dj-sim eval sweep-risk-penalty --profile <json>` before choosing a
   non-zero transition-risk penalty. It applies the same score profile to
   recorded candidate pools across repeated `--weight` values and reports
   top-K risk/source diagnostics even when no labels exist. If imported pair
   feedback is available, it also includes ranking metrics and `best_by_metric`;
   otherwise it makes no best-weight claim.
9. Run `dj-sim eval run-ablation --score-profile <json>` to compare recorded
   source contributions and the weighted RRF profile on the labeled candidate
   pools.
10. Run `dj-sim eval run-calibration` for diagnostic score/relevance calibration
     summaries once enough labeled candidate rows exist.
11. Run `dj-sim eval optimize-score-profile` only after enough matched judged
    labels exist. It proposes guarded judged source weights in a JSON report; it
    never applies them as defaults.
12. Run `dj-sim eval report` for the general recorded-session report.

Use `--judged-only` on `report`, `run-ablation`, or `run-calibration` when you
want PR-23 judged validation instead of general diagnostics. The judged gate uses
only feedback rows that can be matched back to recorded `search_result_events` for
the same seed/candidate/source; extra feedback rows that never appeared in a
recorded result are not counted for the gate. Reports include
`evaluation_mode`, `label_status`, `judged_pairs`, `judged_seeds`,
`can_create_candidate_profile`, `can_update_defaults`, and human-readable
guidance. Fewer than 50 matched judged pairs means `insufficient_data`; 50-199 is
diagnostics only; 200-499 may justify considering a candidate score profile; 500+
may justify considering a default update, but never automatically.

`optimize-score-profile` is the guarded PR-24 judged-profile path. It uses only
feedback labels that match recorded result events, splits matched examples by
`seed_track_id` so train and validation seeds do not overlap, searches a bounded
finite grid of non-negative normalized MERT/MAEST/SONARA/CLAP source weights, and
keeps missing source payloads neutral by scoring over the sources present for a
candidate. A proposal is rejected unless validation NDCG@10 improves over the
equal-weight RRF baseline, BadSuggestionRate@10 does not increase, and the
deterministic bootstrap stability check passes. The JSON report includes
`source: "judged_feedback"`, train/validation and baseline metrics, source
weights, proposal-only risk weights, PR-23 label-gate fields, guardrails,
`can_apply_as_default: false`, and manual guidance. `--record` is optional and
writes only an `ok` diagnostic summary row to `calibration_runs`; default
behavior writes no database rows.

`run-ablation` evaluates only recorded candidate-pool events and imported pair
feedback. It builds single-source variants for `mert`, `maest`, `sonara`, and `clap` when
those sources are present, a full Reciprocal Rank Fusion baseline, and
leave-one-out RRF variants that remove one source at a time. RRF is used because
raw source scores are not calibrated or directly comparable across models; the
ablation report uses recorded per-source ranks, or derives a source-local rank
from scores only when no rank was recorded. It does not tune production weights
or change runtime search behavior. With `--score-profile`, it also adds a
`fusion:weighted_rrf:<profile_name>` diagnostic variant using
`sum(weight[source] * (1 / (rrf_k + rank)))`. Missing sources contribute `0`, and
the variant uses ranks rather than raw source scores.
With `--judged-only`, ranking metrics are computed from matched judged result rows
only instead of treating unjudged candidates as non-relevant placeholders. The
report still keeps unjudged counts and ranked candidate IDs for audit context.

`apply-score-profile` is the direct automatic-profile path: it loads the JSON
artifact, reads recorded `search_sessions` / `search_result_events`, extracts
source ranks from `score_breakdown` / `sources_json`, and ranks candidates with
`sum(weight[source] * (1 / (rrf_k + rank)))`. It does not write to SQLite by
default, does not use raw source scores as comparable weights, and does not change
runtime search endpoints or scoring. Manual feedback is optional validation only;
when no labels exist, the report status can still be `ok` while
`label_status` remains `insufficient_data`. Under PR-23, `label_status` follows
the matched judged-pair gates rather than merely checking whether any label row
exists, so small labeled samples stay diagnostic.

`sweep-risk-penalty` is the report-only transition-risk tuning path. It reads the
same recorded candidate-pool events, applies the score profile, then repeats the
ranking with each `--weight` by using
`normalized_rrf_score - weight * transition_risk`. It prefers stored
`transition_risk` fields from weighted candidate-pool events and falls back to
recomputing lightweight diagnostics from stored track BPM/key/energy/source-count
metadata when older events did not record risk. With no pair feedback, the JSON
still includes `ranked_sessions`, `average_transition_risk_at_k`,
`source_count_at_k`, score quantiles, and `label_status: "insufficient_data"`,
but no `best_by_metric`. With labels, it adds NDCG, MAP, MRR, precision, bad
suggestion rate, and hit-rate metrics using the same unjudged-as-non-relevant
policy as `apply-score-profile`, then reports `best_by_metric`. The command is
for comparing report evidence before choosing a preview penalty; it is not
AutoMix, beatgrid/cue detection, probability calibration, or a production search
scoring change.

`export-weighted-candidates` is the fresh-pool automatic-profile preview path. It
loads the same score profile artifact, generates candidates from the requested
sources for the requested or sampled seeds, merges duplicate candidates per seed,
and sorts them with `sum(weight[source] * (1 / (rrf_k + rank)))`. The command
requires the requested source set to match the profile source set so missing
weights or accidentally omitted profile sources fail clearly. The generated CSV
keeps empty manual-label columns for optional audit/import workflows and adds
profile rank/score, source counts, source-rank JSON, and profile-weight JSON. It
is an explicit evaluation/future-ranker command only; it does not change runtime
search endpoints or scoring.

`report` summarizes recorded sessions against the imported ratings.

`profile-sources` is read-only and does not use manual labels. If
`--seed-sample` points at a CSV created by `export-seed-sample`, its `track_id`
column becomes the seed list. Without `--seed-sample`, the command samples up to
`--sample-count` tracks internally with the same deterministic sampler but allows
partial analysis coverage so missing-source rates remain visible. It compares
sources by ranks rather than raw scores because MERT, MAEST, SONARA, and CLAP scores
use different scales. A source with no sampled coverage gets normalized internal
weight `0` and a warning. Missing analysis for one source does not stop other selected
sources from being profiled.

`run-calibration` is report-only diagnostics over manual pair feedback. It treats
ratings at or above `--accepted-threshold` as accepted labels, then compares those
labels with a selected diagnostic score. Raw source scores, total scores, rank
percentiles, and min-max-normalized RRF values are not production confidence or
probabilities. The JSON report always includes `score_kind` and
`calibration_status`; when fewer than `--min-samples` judged rows are available,
the status is `insufficient_data` and probability metrics are withheld. The
default `--no-record` writes only the JSON file; use `--record` explicitly to save
an `ok` summary into `calibration_runs`. No calibration command changes runtime
search endpoints, scoring weights, or default thresholds.
With `--judged-only`, calibration can only report `ok` when the matched judged
label gate is no longer `insufficient_data`; otherwise it writes the same sample
counts, score quantiles, and guidance without implying that search quality has
been validated.

`optimize-score-profile` is also report/proposal-only. It cannot overwrite
`DEFAULT_HYBRID_SOURCES`, default source weights, production score profiles, app
settings, database defaults, UI defaults, or runtime search behavior. Even when
500+ matched judged pairs are available, the report can only mark a manual
default-review candidate; it never applies a default automatically.

`export-candidates` reads existing exact search sources only: `mert` embedding
similarity, `maest` embedding similarity, balanced/default `sonara`
similarity, and `clap` stored audio-embedding similarity. It excludes the seed track, deduplicates candidates that appear from
multiple sources, stores per-source rank/score details in the final
`sources_json` column, and randomizes the visible `blind_rank` with
`--random-seed` so the labeler does not see which model proposed a candidate.
The default `source` column is `manual`, and the generated empty rating fields
are intended for human labels only. Prompt-aware CLAP text search is not included
because it needs a text prompt rather than a seed-track query.

`export-seed-sample` is read-only and exists to prepare those seed IDs before
candidate-pool export. By default it samples only tracks with complete SONARA,
MERT, CLAP, and MAEST coverage so early ablation reports compare sources on the
same set of tracks; use `--allow-partial-analysis` only for exploratory labeling.
Sampling is deterministic for the same `--random-seed`, prefers spread across
BPM/energy buckets when enough BPM and energy values are available, falls back to
a deterministic random sample otherwise, and prefers distinct known artists
without failing when the library does not have enough unique artists.

Usage:

```text
dj-sim eval export-seed-sample [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Schema v4 SQLite database path. |
| `--output` | CSV path | required | Seed-sample CSV to create. |
| `--count` | integer `>=1` | `50` | Maximum number of seed tracks to export. |
| `--random-seed` | integer | `123` | Deterministic sample seed. |
| `--require-complete-analysis/--allow-partial-analysis` | flag | require complete | Require SONARA, MERT, CLAP, and MAEST coverage before sampling. |
| `--help` | flag | off | Show help. |

Seed-sample CSV columns:

```text
track_id,artist,title,album,bpm,musical_key,energy,has_sonara_analysis,has_mert_embedding,has_clap_embedding,has_maest_embedding,bucket
```

Usage:

```text
dj-sim eval export-candidates [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Schema v4 SQLite database path. |
| `--output` | CSV path | required | Candidate-pool CSV to create. |
| `--seed-track-id` | integer | required | Seed track ID. Repeat for multiple seeds. |
| `--source` | text | `mert`, `maest`, `sonara`, `clap` | Candidate source. Repeat for a subset. |
| `--per-source` | integer `>=1` | `10` | Maximum top candidates requested from each source per seed. |
| `--random-seed` | integer | `123` | Deterministic blind-order seed. |
| `--record-session/--no-record-session` | flag | record | Record `search_sessions` and blinded `search_result_events`. |
| `--help` | flag | off | Show help. |

Candidate-pool CSV columns:

```text
seed_track_id,candidate_track_id,blind_rank,rating,reason_tags,notes,source,seed_artist,seed_title,candidate_artist,candidate_title,candidate_bpm,candidate_key,candidate_energy,sources_json
```

When session recording is enabled, the command creates one
`evaluation_candidate_pool` search session per seed. Runtime API/UI searches are
still not logged automatically. Missing analysis for a selected source is printed
as a warning and does not stop export while another selected source produces
candidates.

Usage:

```text
dj-sim eval export-weighted-candidates [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Schema v4 SQLite database path. |
| `--profile` | JSON path | required | Score profile artifact created by `profile-sources --profile-output`. |
| `--output` | CSV path | required | Weighted candidate-pool CSV to create. |
| `--seed-sample` | CSV path | none | Optional CSV with a `track_id` column from `export-seed-sample`. |
| `--seed-track-id` | integer | none | Seed track ID. Repeat for multiple seeds. Mutually exclusive with `--seed-sample`. |
| `--sample-count` | integer `>=1` | `50` | Seeds to sample internally with complete-analysis coverage when no seed input is provided. |
| `--source` | text | profile `sources` | Candidate source. Repeat for the exact source set in the profile. |
| `--per-source` | integer `>=1` | `30` | Maximum top candidates requested from each source per seed. |
| `--random-seed` | integer | `123` | Deterministic seed for internal sampling and tie ordering. |
| `--rrf-k` | integer `>=1` | `60` | RRF smoothing constant for weighted source-rank fusion. |
| `--transition-risk-weight` | number `0.0-1.0` | `0.0` | Optional diagnostic transition-risk penalty. Default keeps plain weighted RRF. |
| `--record-session/--no-record-session` | flag | record | Record `evaluation_weighted_candidate_pool` sessions and profile-ranked events. |
| `--help` | flag | off | Show help. |

Weighted candidate CSV columns:

```text
seed_track_id,candidate_track_id,profile_rank,profile_score,adjusted_score,raw_rrf_score,transition_risk,transition_risk_penalty,transition_risk_weight,rating,reason_tags,notes,source,seed_artist,seed_title,candidate_artist,candidate_title,candidate_album,candidate_bpm,candidate_musical_key,candidate_energy,source_count,sources_json,score_profile_name,score_profile_weights_json
```

When `--transition-risk-weight` is greater than zero, candidates are sorted by the
same adjusted diagnostic score as Hybrid preview:
`normalized_rrf_score - transition_risk_weight * transition_risk`; missing risk
applies no penalty. Transition risk is a preview diagnostic only, not AutoMix,
beatgrid/cue detection, calibrated confidence, or a calibrated transition
probability. When session recording is enabled, the score breakdown stores
weighted-RRF components, adjusted/raw scores, risk penalty fields, profile
weights, source ranks, and original source rank/score payloads in profile-rank
order. This is explicit evaluation logging only.

Usage:

```text
dj-sim eval profile-sources [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Schema v4 SQLite database path. |
| `--output` | JSON path | required | Source-profile report to create. |
| `--profile-output` | JSON path | none | Optional score profile artifact to create from this source-profile run. |
| `--profile-name` | text | `auto-source-profile` | Optional score profile name when `--profile-output` is used. |
| `--seed-sample` | CSV path | none | Optional CSV with a `track_id` column from `export-seed-sample`. |
| `--source` | text | `mert`, `maest`, `sonara`, `clap` | Candidate source. Repeat for a subset. |
| `--sample-count` | integer `>=1` | `50` | Seeds to sample internally when `--seed-sample` is omitted. |
| `--per-source` | integer `>=1` | `30` | Maximum top candidates requested from each source per seed. |
| `--top-k` | integer `>=1` | `10` | Agreement cutoff. Repeat for multiple top-K metrics. |
| `--random-seed` | integer | `123` | Deterministic seed for internal sampling. |
| `--help` | flag | off | Show help. |

The source-profile JSON includes `status`, `profile_kind`, `sources`,
`seed_count`, `per_source`, `pairwise_agreement`, RRF `consensus`, `recommended_weights`,
`warnings`, and `limitations`. The `limitations` field explicitly states that
the output is an internal consistency/source reliability diagnostic, not a
calibrated probability or production confidence score.

Usage:

```text
dj-sim eval build-score-profile [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--source-profile-report` | JSON path | required | Report created by `profile-sources`. |
| `--output` | JSON path | required | Score profile artifact to create. |
| `--name` | text | required | Profile name used in weighted RRF variant names. |
| `--rrf-k` | integer `>=1` | `60` | Accepted for command-line continuity; apply-time `--rrf-k` controls weighted RRF. |
| `--help` | flag | off | Show help. |

The score profile JSON includes `name`, `profile_kind`, `weight_kind`, `sources`,
normalized `weights`, `created_at`, a compact `source_report_summary`,
`limitations`, and `version`. Loading rejects negative, non-finite,
non-normalized, missing, or unknown source weights.

Usage:

```text
dj-sim eval apply-score-profile [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Schema v4 SQLite database path. |
| `--profile` | JSON path | required | Score profile artifact created by `profile-sources --profile-output`. |
| `--output` | JSON path | required | Application report to create. |
| `--k` | integer `>=1` | `5`, `10`, `20` | Metric cutoff when optional pair labels exist. Repeat for multiple values. |
| `--rrf-k` | integer `>=1` | `60` | RRF smoothing constant for weighted source-rank fusion. |
| `--help` | flag | off | Show help. |

The apply report includes `status`, PR-23 `label_status`, `profile_name`,
`profile_kind`, `weight_kind`, `weights`, session/ranking counts, per-session
ranked candidates, limitations, and a note that the profile is automatic internal
score weighting rather than calibrated confidence. Metrics are included only when
matching pair feedback labels exist, but candidate profile/default-update gate
fields remain conservative until enough matched judged pairs have accumulated.

Usage:

```text
dj-sim eval sweep-risk-penalty [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Schema v4 SQLite database path. |
| `--profile` | JSON path | required | Score profile artifact created by `profile-sources --profile-output`. |
| `--output` | JSON path | required | Risk-penalty sweep report to create. |
| `--weight` | number `0.0-1.0` | `0`, `0.25`, `0.5`, `1.0` | Transition-risk penalty weight. Repeat for a sweep. |
| `--k` | integer `>=1` | `5`, `10`, `20` | Metric and diagnostic cutoff. Repeat for multiple values. |
| `--rrf-k` | integer `>=1` | `60` | RRF smoothing constant for weighted source-rank fusion. |
| `--help` | flag | off | Show help. |

The sweep report includes one variant per weight, per-session ranked candidates,
top-K transition-risk/source-count diagnostics, and score distributions. Ranking
metrics and `best_by_metric` appear only when matching pair feedback exists; an
unlabeled sweep is diagnostics-only and deliberately does not name a best weight.

Usage:

```text
dj-sim eval optimize-score-profile [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Schema v4 SQLite database path. |
| `--output` | JSON path | none | Optional guarded optimizer report to create. |
| `--profile-name` | text | `hybrid_judged_v1` | Proposal profile name written into the JSON report and optional calibration summary. |
| `--objective` | text | `balanced` | MVP objective; only `balanced` is supported. |
| `--split-by` | text | `seed` | MVP split strategy; only seed/`seed_track_id` splitting is supported. |
| `--min-judged-pairs` | integer `>=1` | `200` | Requested minimum matched judged pairs. The PR-23 200-pair candidate-profile gate still applies even if this is lower. |
| `--rrf-k` | integer `>=1` | `60` | RRF smoothing constant for source-rank fusion. |
| `--k` | integer `>=1` | `10` | Metric cutoff to include. Repeat for multiple values; NDCG@10/BadSuggestionRate@10 guardrails are always included. |
| `--random-seed` | integer | `123` | Deterministic split and bootstrap seed. |
| `--grid-step` | number `0.01-1.0` | `0.25` | Bounded normalized source-weight grid step. |
| `--bootstrap-samples` | integer `>=0` | `30` | Deterministic validation bootstrap samples; `0` disables that stability check. |
| `--record/--no-record` | flag | no record | Record only an `ok` diagnostic summary to `calibration_runs`. |
| `--help` | flag | off | Show help. |

The optimizer report is aligned with the judged score-profile template: it includes
`profile_name`, `source: "judged_feedback"`, PR-23 `label_status`, `judged_pairs`,
`judged_seeds`, `train_metrics`, `validation_metrics`, baseline metrics,
normalized `weights`, non-negative proposal `risk_weights`, `guardrails`,
`status`, `decision`, and human-readable `guidance`. Rejected reports keep the
diagnostics and explain which gate or guardrail failed.

Pair feedback CSV columns:

```text
seed_track_id,candidate_track_id,rating,reason_tags,notes,source
```

Transition feedback CSV columns:

```text
outgoing_track_id,incoming_track_id,rating,risk_tags,notes,source
```

JSONL inputs use the same field names. Ratings are integers from `0` through
`3`. `reason_tags` and `risk_tags` are comma-separated strings in CSV, or arrays
or comma-separated strings in JSONL. Empty tag fields become empty lists. Empty
`source` values default to `manual`.

Evaluation labels are explicit local ground truth only when imported or recorded
as evaluation feedback. Rhythm Lab labels and `track_likes` are not used as
search-evaluation ground truth by default. Evaluation commands write SQLite rows
or JSON reports only; they never read, rewrite, retag, move, copy, or delete
audio files.

Usage:

```text
dj-sim eval [OPTIONS] COMMAND [ARGS]...
```

Commands:

```text
export-seed-sample
export-candidates
import-pair-feedback
import-transition-feedback
profile-sources
export-weighted-candidates
apply-score-profile
sweep-risk-penalty
optimize-score-profile
run-ablation
build-score-profile
run-calibration
report
```

The import commands fail fast on malformed ratings with the input line number
and print imported/upserted or inserted counts. `report` writes a JSON-safe file
with session totals, judged and unjudged result counts, labels by rating, and
ranking metrics for each requested `--k` cutoff. PR-23 metrics include NDCG,
precision, bad-suggestion rate, strong/maybe/reject rates, MRR, and MAP at the
requested cutoffs. `ExplanationTagAgreement@3` is reported as unavailable with
zero coverage until the explanation layer exists.

`run-ablation` writes a JSON-safe file with `status`, `counts`, per-variant
metrics, and deltas versus `fusion:rrf_all`. If recorded candidate pools or
matching imported pair labels are missing, the report status is
`insufficient_data`. With `--score-profile`, it still includes the weighted RRF
variant metadata and rankings when recorded candidate-pool events exist, even if
there are no labels yet.

`run-calibration` writes a JSON-safe file with `status`, `calibration_status`,
`score_mode`, `score_kind`, accepted-label counts, Brier score, log loss, ECE,
reliability bins, threshold diagnostics, and score quantiles when enough valid
samples exist. It also includes the PR-23 judged label gate fields. Supported
`--score-mode` values are `rank-percentile`, `rrf`, and
`event-total-score`; `rrf` uses per-session min-max-normalized RRF as a
diagnostic score, not as calibrated confidence.

`optimize-score-profile` writes a guarded judged-feedback proposal report. It uses
only matched judged result labels, keeps train and validation seeds disjoint,
rejects overfit or unstable weight grids, and leaves all production/default
weights unchanged. With `--record`, only an `ok` diagnostic summary is inserted
into `calibration_runs`.

`profile-sources` writes a JSON-safe file with coverage, pairwise agreement,
consensus/conflict diagnostics, source score quantiles, and normalized
unsupervised internal weights. It does not record evaluation rows, read Rhythm
Lab labels or `track_likes`, train classifiers, or write audio files.

`apply-score-profile` applies those normalized internal weights as a
schema-validated JSON score profile artifact to recorded candidate pools. It does not write to SQLite, train
a classifier, calibrate probabilities, or affect production search endpoints.
`export-weighted-candidates` uses the same artifact to produce a fresh weighted
candidate-pool CSV and optional explicit evaluation session logging; it does not
train a classifier, use labels as ground truth, or affect production search
endpoints.

### `dj-sim relocate-library`

Preview or apply stored path relocation after moving the same music folder.

```powershell
dj-sim relocate-library .\music-old .\music-new --db .\data\library.sqlite
```

Apply after reviewing the dry run:

```powershell
dj-sim relocate-library .\music-old .\music-new --apply --db .\data\library.sqlite
```

Usage:

```text
dj-sim relocate-library [OPTIONS] OLD_ROOT NEW_ROOT
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `OLD_ROOT` | path | yes | Existing stored root prefix in SQLite. |
| `NEW_ROOT` | path | yes | New root where the same files now exist. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--apply` | flag | off | Update stored paths after preview checks pass. |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--help` | flag | off | Show help. |

Output:

```text
dry_run=<true|false> tracks_matched=<n> tracks_updated=<n> missing_files=<n> conflicts=<n>
```

Conflicts and missing target files are printed per track. Apply mode rejects
missing files and conflicts instead of partially updating paths.

Use this only when the same audio files moved to a new root folder and you want
to keep existing track IDs, analysis, and classifier scores. Always review the
dry-run output before adding `--apply`.

### `dj-sim doctor`

Print Python, PyTorch, and CUDA runtime diagnostics.

```powershell
dj-sim doctor
```

Usage:

```text
dj-sim doctor [OPTIONS]
```

`doctor` is read-only environment diagnostics. It does not open a database and
accepts no `--db`.

Output can include:

```text
python=<path>
torch=<version>
torch_cuda_build=<version-or-none>
cuda_available=<true|false>
cuda_device_count=<n>
cuda_device_name=<name-or-none>
nvidia_smi_cuda=<version-or-none>
device_auto=<cuda|cpu>
suggested_torch_index=<url>
install=torch torchaudio --index-url <url>
```

Use this when `auto`, `cpu`, or `cuda` behavior is unclear.

Run this before long GPU analysis if you changed Python packages, CUDA wheels,
drivers, or FFmpeg/TorchCodec setup.
