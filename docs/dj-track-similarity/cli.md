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
preset, or training/scoring combined classifier profiles. Use `--models mert`
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

Import manual evaluation labels into schema v4 SQLite databases and build JSON
reports from explicitly recorded `search_sessions` / `search_result_events`.
The app does not log search sessions automatically, so reports can be
`insufficient_data` until a workflow has recorded evaluation sessions and result
events.

```powershell
dj-sim eval export-seed-sample --db .\data\library_v4.sqlite --output .\labels\seed_sample.csv --count 50 --random-seed 123
dj-sim eval export-candidates --db .\data\library_v4.sqlite --output .\labels\candidate_pool.csv --seed-track-id 42 --source mert --source sonara --source maest --per-source 10 --random-seed 123
dj-sim eval import-pair-feedback --db .\data\library_v4.sqlite --input .\labels\pair_feedback.csv
dj-sim eval import-transition-feedback --db .\data\library_v4.sqlite --input .\labels\transition_feedback.jsonl
dj-sim eval run-ablation --db .\data\library_v4.sqlite --output .\reports\ablation.json --k 5 --k 10 --rrf-k 60
dj-sim eval run-calibration --db .\data\library_v4.sqlite --output .\reports\calibration.json --score-mode rrf --bins 10 --min-samples 30 --accepted-threshold 2
dj-sim eval report --db .\data\library_v4.sqlite --output .\reports\evaluation.json --k 5 --k 10
```

Candidate-pool export is the recommended first step when collecting new manual
ground truth:

1. Run `dj-sim eval export-seed-sample` to choose a reproducible, practical set
   of seed tracks for manual labeling.
2. Run `dj-sim eval export-candidates` for the exported seed IDs, usually with
   `--source mert --source sonara --source maest` and session recording enabled.
3. Open the generated candidate CSV and fill `rating`, `reason_tags`, and `notes`
   by hand.
4. Import the completed file with `dj-sim eval import-pair-feedback`.
5. Run `dj-sim eval run-ablation` to compare recorded source contributions on
   the labeled candidate pools.
6. Run `dj-sim eval run-calibration` for diagnostic score/relevance calibration
   summaries once enough labeled candidate rows exist.
7. Run `dj-sim eval report` for the general recorded-session report.

`run-ablation` evaluates only recorded candidate-pool events and imported pair
feedback. It builds single-source variants for `mert`, `maest`, and `sonara` when
those sources are present, a full Reciprocal Rank Fusion baseline, and
leave-one-out RRF variants that remove one source at a time. RRF is used because
raw source scores are not calibrated or directly comparable across models; the
ablation report uses recorded per-source ranks, or derives a source-local rank
from scores only when no rank was recorded. It does not tune production weights
or change runtime search behavior.

`report` summarizes recorded sessions against the imported ratings.

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

`export-candidates` reads existing exact search sources only: `mert` embedding
similarity, `maest` embedding similarity, and balanced/default `sonara`
similarity. It excludes the seed track, deduplicates candidates that appear from
multiple sources, stores per-source rank/score details in the final
`sources_json` column, and randomizes the visible `blind_rank` with
`--random-seed` so the labeler does not see which model proposed a candidate.
The default `source` column is `manual`, and the generated empty rating fields
are intended for human labels only. CLAP text search is not included because it
needs a text prompt rather than a seed-track query.

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
| `--source` | text | `mert`, `sonara`, `maest` | Candidate source. Repeat for a subset. |
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
run-ablation
run-calibration
report
```

The import commands fail fast on malformed ratings with the input line number
and print imported/upserted or inserted counts. `report` writes a JSON-safe file
with session totals, judged and unjudged result counts, labels by rating, and
ranking metrics for each requested `--k` cutoff.

`run-ablation` writes a JSON-safe file with `status`, `counts`, per-variant
metrics, and deltas versus `fusion:rrf_all`. If recorded candidate pools or
matching imported pair labels are missing, the report status is
`insufficient_data`.

`run-calibration` writes a JSON-safe file with `status`, `calibration_status`,
`score_mode`, `score_kind`, accepted-label counts, Brier score, log loss, ECE,
reliability bins, threshold diagnostics, and score quantiles when enough valid
samples exist. Supported `--score-mode` values are `rank-percentile`, `rrf`, and
`event-total-score`; `rrf` uses per-session min-max-normalized RRF as a
diagnostic score, not as calibrated confidence.

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
