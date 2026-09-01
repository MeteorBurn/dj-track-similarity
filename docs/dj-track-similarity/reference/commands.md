# CLI reference

Every command-line entry point in the repository, with its arguments, ranges, and defaults. It
covers the installed `dj-sim` command, the Windows launcher, and the command-line tools and scripts
under `tools/` and `scripts/`. It does not list tests, Python APIs, or private helpers.

All examples assume the project environment is active and the current directory is the repository
root. `PATH`, `FILE`, and `DIRECTORY` mean filesystem paths. Flags marked **required** must be
provided. Repeated flags may be supplied more than once. Every command accepts `--help`. The
argparse-based tools also accept `-h`.

`dj-sim` accepts these global options before its command:

| Option | Meaning |
| --- | --- |
| `--install-completion` | Install completion for the current shell. |
| `--show-completion` | Print shell-completion code. |
| `--help` | Show the root command help. |

Unless its own section says otherwise, an optional `dj-sim --db PATH` opens `PATH`, or uses
`dj-track-similarity.sqlite` in the current directory when omitted. `dj-sim serve` deliberately
has a different no-database behavior.

## Main project

<details>
<summary>Library, analysis, server, and database commands</summary>

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
```

### `dj-sim scan MUSIC_ROOT`

Scan one audio-folder root into the selected library.

| Argument or option | Meaning |
| --- | --- |
| `MUSIC_ROOT` | **Required.** Folder to scan. |
| `--db PATH` | Library database path. |

### `dj-sim validate-database`

Read and validate stored library data without recalculating analysis. The database is opened
read-only.

| Option | Meaning |
| --- | --- |
| `--db PATH` | **Required.** Library database path. |
| `--report PATH` | Optional JSON report output path. |

Findings stream to standard output as they are found, then one JSON summary with `status`,
`checked`, `warnings`, and `errors` is printed. Exit codes carry the result, so a script can branch
on them:

| Exit code | Meaning |
| ---: | --- |
| `0` | The run finished and found no error. Warnings alone still exit `0`. |
| `1` | The database file was missing, SQLite raised an error, or an argument was invalid. |
| `2` | The run finished and the error count was above zero. |

### `dj-sim migrate-database`

Merge a legacy Core/Artifacts pair into a single library database. Stop every SQLite user first.

| Option | Meaning |
| --- | --- |
| `--db PATH` | **Required.** Legacy Core database path. |
| `--backup-root PATH` | Parent folder for the timestamped backup. Default: the `backups` folder beside the database. |
| `--confirm TEXT` | Must exactly be `MIGRATE SINGLE LIBRARY`. Otherwise the command prompts for it. |

It writes the migrated database and moves the old files into its backup. It does not start
analysis or reanalysis. For what the migration copies and what it leaves empty, see
[Database reference](./database.md).

### `dj-sim relocate-library OLD_ROOT NEW_ROOT`

Preview replacement of stored library paths from `OLD_ROOT` to `NEW_ROOT`. This command has no
browser equivalent.

| Argument or option | Meaning |
| --- | --- |
| `OLD_ROOT` | **Required.** Existing stored-path root. |
| `NEW_ROOT` | **Required.** Replacement filesystem root. |
| `--apply` | After preview checks pass, write the new paths to SQLite. It does not move, copy, delete, or retag audio. |
| `--db PATH` | Library database path. |

### `dj-sim analyze`

Run one analysis job. `--models sonara` is the standalone SONARA job. ML model selections cannot
mix SONARA with ML models.

| Option | Range | Default | Meaning |
| --- | --- | --- | --- |
| `--db PATH` | path | `dj-track-similarity.sqlite` | Library database path. |
| `--limit INTEGER` | `0` or more | none | Maximum tracks to analyze. Omit for all eligible tracks. A literal `0` selects zero candidates. |
| `--models TEXT` | `maest,mert,muq,mulan,clap` or `sonara` alone | all five ML families | Comma-separated family selection. |
| `--device TEXT` | `auto`, `cpu`, `cuda` | `auto` | ML inference device. |
| `--top-k INTEGER` | `1..10` | `3` | MAEST labels stored per track. |
| `--track-batch-size INTEGER` | `1..64` | `8` | Decoded tracks held per ML job batch. |
| `--inference-batch-size INTEGER` | `1..128` | `16` | ML forward-pass batch size. |
| `--diagnostics` | flag | off | Write decoder and batch timing diagnostics to the file log. |
| `--sonara-batch-size INTEGER` | `1..16` | `8` | Native SONARA file batch size, independent from ML batching. |
| `--sonara-bpm-min FLOAT` | `20.0..400.0` | `70.0` | Lower bound of the SONARA BPM analysis range. |
| `--sonara-bpm-max FLOAT` | `20.0..400.0` | `180.0` | Upper bound of the SONARA BPM analysis range. It must be at least twice the lower bound. |
| `--ml-staged` | flag | off | Turn on ML Staged Mode, which copies candidates read-only before decode and inference. |
| `--ml-staging-path PATH` | existing directory | none | ML staging folder. Required whenever `--ml-staged` is supplied. |
| `--ml-copy-workers INTEGER` | `1..16` | `4` | Parallel copy workers feeding the ML staging window. |
| `--ml-decode-workers INTEGER` | `1..32` | `8` | Parallel TorchCodec decoders in ML Staged Mode. |
| `--ml-stage-size INTEGER` | `1..512` | `64` | Maximum files held in the ML staging directory at once. |

`--ml-staged` without `--ml-staging-path`, or with a path that is not an existing directory, exits
`1` before any work starts. The five `--ml-*` options apply only to the ML families. A SONARA job
ignores them.

The BPM range belongs to the library rather than to the run. Once one SONARA row exists, any other
pair is refused with an instruction to reset SONARA analysis first. See
[SONARA BPM range](./analysis-families.md#sonara-bpm-range).

### `dj-sim analyze-pipeline`

Run selected pipeline stages in fixed `sonara,ml` order.

| Option | Range | Default | Meaning |
| --- | --- | --- | --- |
| `--stages TEXT` | `sonara`, `ml` | `sonara,ml` | Comma-separated selected stages. Execution is always SONARA then ML. |
| `--ml-models TEXT` | `maest,mert,muq,mulan,clap` | all five | ML families only. Passing `sonara` here exits `1`. |
| `--db PATH` | path | `dj-track-similarity.sqlite` | Library database path. |
| `--limit INTEGER` | `0` or more | none | Maximum tracks per selected stage. Omit for all eligible tracks. |
| `--device TEXT` | `auto`, `cpu`, `cuda` | `auto` | ML inference device. |
| `--track-batch-size INTEGER` | `1..64` | `8` | Decoded tracks per ML batch. |
| `--inference-batch-size INTEGER` | `1..128` | `16` | ML forward-pass batch size. |
| `--sonara-batch-size INTEGER` | `1..16` | `8` | Native SONARA file batch size. |
| `--sonara-bpm-min FLOAT` | `20.0..400.0` | `70.0` | Lower bound of the SONARA BPM analysis range. |
| `--sonara-bpm-max FLOAT` | `20.0..400.0` | `180.0` | Upper bound, at least twice the lower bound. |

The pipeline CLI has no staging options. Staged Mode for either family is reachable from the
browser and from `POST /api/analysis/pipelines`, and ML Staged Mode is also reachable from
`dj-sim analyze --ml-staged`.

### `dj-sim analyze-classifier CLASSIFIER`

Score a promoted classifier against its declared database inputs. It does not decode or retag audio.

| Argument or option | Meaning |
| --- | --- |
| `CLASSIFIER` | **Required.** Promoted classifier key, such as `live_instrumentation`. |
| `--db PATH` | Library database path. |
| `--model PATH` | Optional promoted-model path override. |
| `--limit INTEGER` | Maximum tracks to score. |

Scoring is incremental. A track that already has a row for that classifier key is excluded from
the candidate query, so a rerun after a retrain finds no work until the stored scores are reset.

### `dj-sim doctor`

Print Python, Torch, CUDA, and recommended Torch-index diagnostics. When Torch is installed, it
also validates the audio runtime: the selected FFmpeg `8.1.1` full shared directory, its required
library paths, and PyAV `17.1.0` imported from the active Python environment. Without Torch the
command returns before the audio check. It takes no command-specific options.

### `dj-sim text-search QUERY`

Search the selected text-to-audio embedding space.

| Argument or option | Meaning |
| --- | --- |
| `QUERY` | **Required.** Text prompt. |
| `--db PATH` | Library database path. |
| `--model clap\|mulan` | Text embedding family. Default: `clap`. |
| `--limit INTEGER` | Result count, `1..500`. Default: `50`. |
| `--min-similarity FLOAT` | Optional result threshold. |
| `--device auto\|cpu\|cuda` | Text-embedding device. Default: `auto`. |

Output is tab-separated `score`, `track_id`, `track_uuid`, `file_path`, one row per hit.

### `dj-sim serve`

Start the API server.

| Option | Meaning |
| --- | --- |
| `--host TEXT` | Bind address. Default: `127.0.0.1`. |
| `--port INTEGER` | Bind port. Default: `8765`. |
| `--db PATH` | Open an existing library database or create one there. Omit it to start with no selected database and create no SQLite file. |
| `--log-level debug\|info\|warning\|error\|critical` | File-log level. Default: `info`. |
| `--log-track-events` | Include successful per-track events in the file log. |

</details>

<details>
<summary>Classifier diagnostics</summary>

```powershell
dj-sim classifier calibration-report --db .\data\library.sqlite
```

### `dj-sim classifier calibration-report`

| Option | Meaning |
| --- | --- |
| `--classifier TEXT` | **Required.** Promoted classifier key. |
| `--db PATH` | Library database path. |
| `--output FILE` | Optional JSON report file. Omit to print JSON. |
| `--min-feedback INTEGER` | Minimum feedback rows, at least `1`. Default: `30`. |

### `dj-sim classifier suggest-labels`

| Option | Meaning |
| --- | --- |
| `--classifier TEXT` | **Required.** Promoted classifier key. |
| `--mode uncertainty\|hard_negative\|diversity\|disagreement\|high_impact_unlabeled` | Ranking mode. Default: `uncertainty`. |
| `--db PATH` | Library database path. |
| `--limit INTEGER` | Suggestions, `1..500`. Default: `25`. |
| `--random-seed INTEGER` | Deterministic tie ordering. Default: `123`. |
| `--output FILE` | Optional JSON report file. Omit to print JSON. |

</details>

<details>
<summary>Evaluation and feedback commands</summary>

Evaluation commands use the library database and, when needed, its adjacent Evaluation sidecar.
They create reports and feedback records. They do not write audio files. Candidate source options
accept `mert`, `maest`, `muq`, `mulan`, `sonara`, or `clap` and are repeatable.

```powershell
dj-sim eval export-candidates --db .\data\library.sqlite --output .\reports\candidates.csv --seed-track-id 42 --source mert
```

Ablation, calibration, the score-profile optimizer, and the risk sweep are available here only. The
HTTP surface covers feedback, the source profile, score-profile application, weighted candidates,
and the last recorded reports. See [API reference](./api.md).

### `dj-sim eval export-candidates`

| Option | Meaning |
| --- | --- |
| `--db PATH` | Library database path. |
| `--output FILE` | **Required.** CSV output. |
| `--seed-track-id INTEGER` | Seed track ID. Repeatable. |
| `--source TEXT` | Candidate source. Repeatable. |
| `--per-source INTEGER` | Candidates per source, at least `1`. Default: `10`. |
| `--random-seed INTEGER` | Blind-order random seed. Default: `123`. |
| `--record-session` / `--no-record-session` | Record Evaluation search sessions and result events. Default: record. |

### `dj-sim eval export-weighted-candidates`

| Option | Meaning |
| --- | --- |
| `--db PATH` | Library database path. |
| `--profile FILE` | **Required.** Existing score-profile JSON. |
| `--output FILE` | **Required.** CSV output. |
| `--seed-sample FILE` | Existing exported seed sample. It is exclusive with supplied seed IDs. |
| `--seed-track-id INTEGER` | Seed ID. Repeatable. |
| `--sample-count INTEGER` | Internal seed count if neither seed input is supplied, at least `1`. Default: `50`. |
| `--source TEXT` | Profile source to use. Repeatable. |
| `--per-source INTEGER` | Candidates per source per seed, at least `1`. Default: `30`. |
| `--random-seed INTEGER` | Internal sampling and tie-order seed. Default: `123`. |
| `--rrf-k INTEGER` | Weighted rank-fusion smoothing constant, at least `1`. Default: `60`. |
| `--transition-risk-weight FLOAT` | Diagnostic transition-risk penalty, `0..1`. Default: `0.0`. |
| `--record-session` / `--no-record-session` | Record weighted sessions and events. Default: record. |

### `dj-sim eval export-seed-sample`

| Option | Meaning |
| --- | --- |
| `--db PATH` | Library database path. |
| `--output FILE` | **Required.** CSV output. |
| `--count INTEGER` | Maximum seeds, at least `1`. Default: `50`. |
| `--random-seed INTEGER` | Deterministic sample seed. Default: `123`. |
| `--require-complete-analysis` / `--allow-partial-analysis` | Require SONARA, MERT, MuQ, CLAP, and MAEST coverage. Default: require complete analysis. |

### Feedback import and reports

| Command | Options |
| --- | --- |
| `dj-sim eval import-pair-feedback` | `--db PATH`. `--input FILE` **required**, existing feedback input. |
| `dj-sim eval import-transition-feedback` | `--db PATH`. `--input FILE` **required**, existing feedback input. |
| `dj-sim eval report` | `--db PATH`. `--output FILE` **required**. `--k INTEGER` repeatable, each at least `1`. `--judged-only` to enforce matched judged-label gates. |
| `dj-sim eval run-ablation` | `--db PATH`. `--output FILE` **required**. `--k INTEGER` repeatable, at least `1`. `--rrf-k INTEGER` at least `1`, default `60`. `--score-profile FILE`. `--judged-only`. |

### Score-profile creation, calibration, and application

| Command | Options |
| --- | --- |
| `dj-sim eval build-score-profile` | `--source-profile-report FILE` **required**. `--output FILE` **required**. `--name TEXT` **required**. `--rrf-k INTEGER` at least `1`, default `60`, accepted and then discarded. |
| `dj-sim eval run-calibration` | `--db PATH`. `--output FILE` **required**. `--score-mode rrf\|rank-percentile\|event-total-score`, default `rrf`. `--bins INTEGER` at least `1`, default `10`. `--min-samples INTEGER` at least `1`, default `30`. `--accepted-threshold INTEGER` in `0..3`, default `2`. `--rrf-k INTEGER` at least `1`, default `60`. `--judged-only`. `--record` / `--no-record`, default no record. |
| `dj-sim eval optimize-score-profile` | `--db PATH`. `--output FILE`. `--profile-name TEXT`, default `weighted_candidates_judged_v1`. `--objective balanced`, default `balanced`. `--split-by seed`, default `seed`. `--min-judged-pairs INTEGER` at least `1`, default `200`. `--rrf-k INTEGER` at least `1`, default `60`. `--k INTEGER` repeatable, at least `1`. `--random-seed INTEGER`, default `123`. `--grid-step FLOAT` in `0.01..1`, default `0.25`. `--bootstrap-samples INTEGER` at least `0`, default `30`. `--record` / `--no-record`, default no record. `--save-profile` / `--no-save-profile`, default no save. |
| `dj-sim eval profile-sources` | `--db PATH`. `--output FILE` **required**. `--profile-output FILE`. `--profile-name TEXT`, default `auto-source-profile`. `--seed-sample FILE`. `--source TEXT` repeatable. `--sample-count INTEGER` at least `1`, default `50`. `--per-source INTEGER` at least `1`, default `30`. `--top-k INTEGER` repeatable, at least `1`. `--random-seed INTEGER`, default `123`. |
| `dj-sim eval apply-score-profile` | `--db PATH`. `--profile FILE` **required**, existing JSON. `--output FILE` **required**. `--k INTEGER` repeatable, at least `1`. `--rrf-k INTEGER` at least `1`, default `60`. |
| `dj-sim eval sweep-risk-penalty` | `--db PATH`. `--profile FILE` **required**, existing JSON. `--output FILE` **required**. `--weight FLOAT` repeatable. `--k INTEGER` repeatable, at least `1`. `--rrf-k INTEGER` at least `1`, default `60`. `--transition-risk-version v1\|v2`, default `v2`. |

`dj-sim eval build-score-profile` takes `--rrf-k` for argument symmetry with the other profile
commands and then ignores it. The written profile is identical for any value.

</details>

<details>
<summary>Windows launcher and database maintenance scripts</summary>

```powershell
python scripts\qa_database.py --db .\data\library.sqlite
```

### `run_server.cmd`

Start the API and Vite development UI together. With no argument it scans `database\` for
`.sqlite` files; if it finds any, it lists them and asks which one to open (default
`volumes.sqlite` when present, otherwise the first one listed, or type a path to use another
database), otherwise it asks for a database path (default `database\volumes.sqlite`). It then asks
for local or LAN mode. Explicit modes do not prompt.

| Argument or option | Meaning |
| --- | --- |
| `local`, `localhost`, `127.0.0.1`, or `--local` | Local mode. Backend and Vite bind to loopback. |
| `lan`, `network`, `0.0.0.0`, or `--lan` | LAN mode. Backend and Vite bind to all interfaces. |
| `help`, `--help`, or `/?` | Print launcher usage. |
| Remaining `dj-sim serve` options | Forwarded to `dj-sim serve`. See its options above. The launcher supplies its selected `--host` and `--port 8765`, and passes the prompted database when one was chosen. |

`run_server.cmd` hands its choices to `scripts/run_server_launcher.py` through five environment
variables rather than through arguments. Those variables are listed in
[Configuration reference](./configuration.md#environment-variables), and the launcher exits `2`
when the host or port variable is missing.

The browser top-bar power button calls the shutdown API for the current backend. After
`dj-sim serve` exits, the Python launcher stops its Vite child process before returning control to
the terminal.

### `python scripts/optimize_database.py`

| Option | Meaning |
| --- | --- |
| `--db PATH` | **Required.** SQLite database to back up, check, maintain, and verify. |

The tool makes a timestamped sibling backup before `VACUUM`, `ANALYZE`, and `PRAGMA optimize`.
Stop database writers first.

### `python scripts/qa_database.py`

| Option | Meaning |
| --- | --- |
| `--db PATH` | **Required.** Library SQLite database. |
| `--evaluation-db PATH` | Optional Evaluation sidecar. Otherwise an adjacent `library.evaluation.sqlite` is used when present. |

This is read-only integrity QA.

### `python scripts/benchmark_search.py`

Create a synthetic greenfield database and benchmark MERT/MAEST vector search. It does not use a
real project database.

| Option | Meaning |
| --- | --- |
| `--output PATH` | **Required.** JSON report path. |
| `--track-count INTEGER` | Repeatable synthetic count. Default: `1000`. Do not combine with `--track-counts`. |
| `--track-counts TEXT` | Comma-separated synthetic counts, such as `1000,10000`. |
| `--seed-count INTEGER` | Seeds per run. Default: `20`. |
| `--per-source INTEGER` | Candidate limit per source. Default: `30`. |
| `--random-seed INTEGER` | Deterministic seed. Default: `123`. |
| `--keep-db PATH` | Keep the synthetic database for debugging instead of cleaning it up. |

</details>

<details>
<summary>Text-layer measurement scripts</summary>

These five scripts under `scripts/` measure the text-to-track layer against labelled examples. All
five are read-only over the library and report-first. They write a JSON report or an `.npz` sidecar
and nothing else. `scripts/text_prompt_benchmark.py` is the committed evidence base that
`AGENTS.md` requires behind any prompt reliability claim.

```powershell
python scripts\text_prompt_benchmark.py --db .\data\library.sqlite --out .\reports\prompt-benchmark.json
```

### `python scripts/text_prompt_benchmark.py`

Rank a labelled pool with each prompt form, model, and negative weight, then report ROC-AUC, average
precision, precision at K, and median rank per form.

| Option | Meaning |
| --- | --- |
| `--db PATH` | **Required.** Library database to read. |
| `--labels PATH` | Rhythm Lab labels database. Default: `tools/rhythm-lab/database/rhythm_lab.sqlite`. |
| `--prompts PATH` | Prompt specification JSON. Default: `scripts/text_prompt_benchmark_prompts.json`. |
| `--models TEXT` | Comma-separated text families to compare. Default: `mulan,clap`. |
| `--device TEXT` | Text-embedding device. Default: `auto`. |
| `--concepts TEXT` | Comma-separated concept names. Default: every concept in the prompt file. |
| `--centered` | Also score against a library-mean-centered matrix as a modality-gap probe. |
| `--clap-checkpoint TEXT` | LAION-CLAP checkpoint to score with. Default: the production checkpoint. Both towers move together. |
| `--clap-vectors PATH` | Sidecar `.npz` from `clap_checkpoint_embed.py`, scored instead of stored `clap_embeddings`. Required for any non-production checkpoint. |
| `--out PATH` | Optional JSON report path. |

A non-production `--clap-checkpoint` without `--clap-vectors` is refused, because a checkpoint's
text tower and audio tower are one joint space.

### `python scripts/clap_checkpoint_embed.py`

Embed the labelled pool with one pinned LAION-CLAP checkpoint into an `.npz` sidecar. It is the one
script in this group that opens audio, and it opens it read-only.

| Option | Meaning |
| --- | --- |
| `--db PATH` | **Required.** Library database to read. |
| `--labels PATH` | Rhythm Lab labels database. Default: `tools/rhythm-lab/database/rhythm_lab.sqlite`. |
| `--checkpoint TEXT` | **Required.** One of the pinned LAION-CLAP checkpoint filenames. |
| `--out PATH` | **Required.** Sidecar `.npz` to write. |
| `--source audio\|stored` | `audio` decodes and embeds. `stored` copies the library's existing vectors, which answers only for the production checkpoint. Default: `audio`. |
| `--mirror PATH` | Restrict the pool to the track IDs of another sidecar, so two arms score the same tracks. |
| `--device TEXT` | Default: `auto`. |
| `--batch-size INTEGER` | Tracks decoded and embedded per forward pass. Default: `16`. |
| `--limit INTEGER` | Embed only the first N of the pool. Default: `0`, meaning the whole pool. |

### `python scripts/text_fusion_benchmark.py`

Test CLAP and MuQ-MuLan rank fusion against the better single model and a per-label oracle. This is
the measurement behind the project rule that the two text models are never fused.

| Option | Meaning |
| --- | --- |
| `--db PATH` | **Required.** Library database to read. |
| `--references PATH` | Reference label JSON. Default: `scripts/text_tag_crosscheck_references.json`. |
| `--device TEXT` | Default: `auto`. |
| `--out PATH` | Optional JSON report path. |

### `python scripts/text_tag_crosscheck.py`

Cross-check each preset against stored SONARA and MAEST signals and print an `ok`, `weak`,
`suspect`, or `INVERTED` verdict per label. It parses the preset file directly and refuses to use
promoted classifiers as references.

| Option | Meaning |
| --- | --- |
| `--db PATH` | **Required.** Library database to read. |
| `--references PATH` | Reference label JSON. Default: `scripts/text_tag_crosscheck_references.json`. |
| `--models TEXT` | Comma-separated text families. Default: `mulan,clap`. |
| `--device TEXT` | Default: `auto`. |
| `--out PATH` | Optional JSON report path. |

### `python scripts/prompt_preset_tune.py`

Turn accumulated `text_preset_feedback` verdicts into wording and weight proposals, with a
leave-one-out marginal value for every bank line. It writes no database rows and no preset file.

| Option | Meaning |
| --- | --- |
| `--db PATH` | **Required.** Library database to read. |
| `--models TEXT` | Comma-separated text families. Default: `mulan,clap`. |
| `--device TEXT` | Default: `auto`. |
| `--min-per-class INTEGER` | Minimum relevant and irrelevant verdicts before a preset is tuned. Default: `5`. |
| `--presets TEXT` | Comma-separated preset keys. Default: every preset with enough verdicts. |
| `--out PATH` | Optional JSON report path. |

</details>

## Rhythm Lab

<details>
<summary>Classifier training, prediction, promotion, and Lab server</summary>

The Rhythm Lab wrapper is `python tools/rhythm-lab/rhythm_lab_cli.py`. The default labels database
is `tools\rhythm-lab\database\rhythm_lab.sqlite`. The default feature set is
`sonara+mert+maest+clap+muq+mulan`. `--feature-set` accepts any non-empty `+`-joined combination of
`sonara`, `mert`, `maest`, `clap`, `muq`, and `mulan`, in any order.

`--source` carries a hard-coded absolute default from the author's own machine, so it will not
resolve on yours. Pass your library path explicitly on every command that reads the source
database.

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py calibration-report --profile live_instrumentation --labels .\data\rhythm_lab.sqlite
```

| Command | Arguments and options |
| --- | --- |
| `train` | `--source PATH`. `--labels PATH`. `--profile TEXT` **required**. `--artifacts PATH`. `--feature-set TEXT`, default full feature set. `--calibrate`. |
| `benchmark-ablation` | `--source PATH`. `--labels PATH`. `--profile TEXT` repeatable. `--feature-set TEXT` repeatable. `--artifacts-root PATH`. `--output PATH`. `--random-state INTEGER`, default `42`. `--calibrate-finalists`. |
| `predict ARTIFACT` | `ARTIFACT` **required** model artifact. `--source PATH`. `--labels PATH`. `--profile TEXT`. |
| `export-predictions` | `--labels PATH`. `--output PATH`. `--profile TEXT` **required**. |
| `promote` | `--profile TEXT` **required**. `--artifacts PATH`. `--feature-set TEXT`, default full feature set. `--source PATH` **required**. `--target PATH`, default `models\classifiers`. `--labels PATH`. `--require-calibration`. `--allow-uncalibrated`. Calibration is required unless `--allow-uncalibrated` is explicitly supplied. |
| `calibration-report` | `--profile TEXT` **required**. `--artifacts PATH`. `--artifact PATH`. `--feature-set TEXT`, default full feature set. `--labels PATH`. |
| `serve` | `--source PATH`. `--source-catalog-uuid TEXT`. `--labels PATH`. `--host TEXT`, default `127.0.0.1`. `--port INTEGER`, default `8777`. |

</details>

<details>
<summary>Active-learning queue and review collections</summary>

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py queue --profile live_instrumentation --labels .\data\rhythm_lab.sqlite
```

| Command | Arguments and options |
| --- | --- |
| `suggest-labels` | `--source PATH`. `--labels PATH`. `--profile TEXT` **required**. `--mode TEXT`, default `uncertainty`. `--limit INTEGER`, default `25`. `--random-seed INTEGER`, default `123`. `--write-queue` to upsert suggestions. |
| `queue` | `--labels PATH`. `--profile TEXT` **required**. `--state TEXT`. |
| `queue-export` | `--labels PATH`. `--profile TEXT` **required**. `--state TEXT`. `--output PATH` **required**. |
| `queue-mark` | `--labels PATH`. `--profile TEXT` **required**. `--queue-id INTEGER` **required**. `--state TEXT` **required**. |
| `queue-clear` | `--labels PATH`. `--profile TEXT` **required**. `--state TEXT` **required**. This deletes queue rows in that state. |
| `collection-save` | `--labels PATH`. `--source-db PATH`. `--name TEXT` **required**. `--source TEXT`, default `agent`. `--note TEXT`. `--track-id INTEGER` repeatable. `--track-ids PATH` (one ID per line). `--replace` to replace rather than append. |
| `collection-list` | `--labels PATH`. |
| `delete-profile` | Exactly one of `--profile TEXT` or `--name TEXT` **required**. `--confirm TEXT` **required** and must exactly match that key or name. `--labels PATH`. This permanently deletes the selected Lab profile and its data. |

</details>

<details>
<summary>Manual-label transfer</summary>

Use `python tools/rhythm-lab/rhythm_lab/label_transfer.py`. It exports a label bundle, previews
rebinding against a library, optionally builds a rebound bundle, then restores only on an explicit
apply.

```powershell
python tools\rhythm-lab\rhythm_lab\label_transfer.py preview --bundle .\exports\labels.zip --library-db .\data\library.sqlite --output .\reports\label-preview.json
```

| Command | Arguments and options |
| --- | --- |
| `export` | `--lab-db PATH` **required**. `--output PATH` **required**. `--promoted-models-root PATH`. `--force` to overwrite output. |
| `preview` | `--bundle PATH` **required**. `--library-db PATH` **required**. `--output PATH` **required**. `--force`. |
| `rebound` | `--bundle PATH` **required**. `--preview PATH` **required**. `--output PATH` **required**. `--force`. |
| `restore` | `--bundle PATH` **required**. `--library-db PATH` **required**. `--lab-db PATH` **required**. `--report PATH` **required**. `--accept-record-id TEXT` repeatable for weak matches. `--apply` to write the restore (otherwise read-only). `--force`. |

</details>

## Audio Dedup

<details>
<summary>Duplicate report and confirmed deletion</summary>

Run `python tools/audio-dedup/audio_dedup_cli.py`. It finds candidates from stored embeddings
and saved SONARA fingerprints. Every run writes a report, and deletion needs `--apply`. The
default search mode is `--fingerprint`. This table covers the CLI. The browser review dialog reads
the same reports and has its own deletion path.

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
```

| Option | Meaning |
| --- | --- |
| `--db PATH` | Project SQLite database. Default: `database\volumes.sqlite` under the repository root. |
| `--root PATH` | **Required.** Include only stored tracks beneath this root. |
| `--path-contains TEXT` | Additional case-insensitive stored-path substring filter. Repeatable. |
| `--preset safe\|balanced\|aggressive` | Threshold preset. Default: `safe`. |
| `--min-score FLOAT` | Override the preset duplicate-score threshold. |
| `--min-similarity FLOAT` | Override the preset content-similarity threshold. |
| `--source mert\|maest\|muq\|clap` | Enable one embedding family. Requires `--embedding`. Repeatable. Omit for all supported families. |
| `--weight FAMILY=VALUE` | Override every enabled-source weight. Requires `--embedding`. Repeat once for each enabled `--source`. |
| `--fingerprint` | Primary search mode, also the default. Search runs exclusively over stored SONARA fingerprints with no embedding loading. Candidate pairs come from fingerprint LSH only, and duplicate groups form from the exact native fingerprint score alone. Every reported candidate stays manual-review. Mutually exclusive with `--embedding`. |
| `--embedding` | Secondary search mode. Score duplicates from the enabled embedding families with the preset gates. The only mode that can produce safe delete candidates for `--apply`. Mutually exclusive with `--fingerprint`. |
| `--skip-spectral` | Skip the FFmpeg spectral check of duplicate-group files that flags suspected transcodes (fake-bitrate copies) and steers keeper choice toward full-band audio. |
| `--limit-groups INTEGER` | Maximum duplicate groups written. |
| `--out-dir PATH` | Report directory. Default: `tools\audio-dedup\data\reports`. |
| `--apply` | After reports are written, prompt for the exact phrase `APPLY DELETE`, delete safe candidates inside `--root`, and remove only their matching database rows. |

Complete command examples for every flag are on the [Audio Dedup](../tools-and-scripts/audio-dedup.md) page.

### `python tools/audio-dedup/spectral_check_cli.py`

Standalone fake-bitrate check. It estimates each file's spectral cutoff with the Audio Dedup
detector and flags suspected transcodes. It reads audio and never writes it.

| Argument or option | Meaning |
| --- | --- |
| `targets` | Zero or more audio files and directories. Directories are scanned recursively. |
| `--list PATH` | Text file with one path per line. Surrounding quotes are ignored. |
| `--csv PATH` | Also write every verdict to this CSV file. |

### `python tools/audio-dedup/benchmark_fingerprint_candidates.py`

Synthetic recall and cost benchmark for fingerprint candidate retrieval. It builds its own data and
touches no library.

| Option | Meaning |
| --- | --- |
| `--groups INTEGER` | Synthetic duplicate groups. Default: `32`. |
| `--distractors INTEGER` | Synthetic non-duplicate tracks. Default: `128`. |
| `--seed INTEGER` | Deterministic generator seed. Default: `20260826`. |
| `--out PATH` | Optional JSON report path. |

</details>

## Audio Doctor

<details>
<summary>Inspection, reports, and repair</summary>

Run `python tools/audio-doctor/audio_doctor_cli.py [paths ...]`. The default dry run inspects
audio without copying or writing source files. Input paths, `--folder`, `--log`, and `--db` may be
combined. Audio Doctor is command-line only and has no API route.

```powershell
python tools\audio-doctor\audio_doctor_cli.py --db .\data\library.sqlite --summary-only
```

| Argument or option | Meaning |
| --- | --- |
| `paths` | Zero or more individual audio paths. |
| `--folder PATH` | Recursively scan a folder for supported audio files. Repeatable. |
| `--log PATH` | Project log to extract post-save WAV readback failures from. Repeatable. |
| `--db PATH` | Library database from which to read `tracks.file_path`. Repeatable. |
| `--db-root PATH` | Restrict database paths to this root. It is also the source root for `--file-root`. Repeatable. |
| `--file-root PATH` | Filesystem replacement root for matching `--db-root` paths. |
| `--since TEXT` | Include log lines at or after this timestamp, such as `2026-05-21 20:26`. |
| `--until TEXT` | Include log lines before this timestamp. |
| `--apply` | Repair previously identified repairable files. Without it, the command is read-only. |
| `--backup-dir PATH` | Full-file backup directory for apply mode. Default: `tools\audio-doctor\data\backups`. |
| `--no-backup` | Apply without full-file backups. Use only when an independent backup exists. |
| `--keep-id3 first\|last\|none` | For WAV repair, readable top-level ID3 chunk to retain. Default: `first`. |
| `--limit INTEGER` | Maximum collected paths. |
| `--summary-only` | Print only the final summary. |
| `--color auto\|always\|never` | Status color policy. Default: `auto`. |
| `--file-log PATH` | Overwritten console-transcript log path. |
| `--no-file-log` | Do not write the optional console transcript log. |
| `--out-dir PATH` | JSON, XLSX, and structured-log directory. Default: `tools\audio-doctor\data\reports`. |
| `--no-report` | Do not write the JSON/XLSX/log report bundle. |
| `--state PATH` | Folder/DB state file. The default derives from `--folder` and `--db` sources. |
| `--workers INTEGER` | Parallel dry-run workers. Default: `1`. Apply is always sequential. |
| `--reason TEXT` | Stored state reason to repair after a dry run. Repeatable and must match exactly. |

`--apply` starts writing as soon as the run reaches a repairable file. There is no interactive
confirmation prompt. The protections are the dry-run default, the backup taken before each repair,
the verification after it, and the restore when verification fails.

</details>

## Audio Online

<details>
<summary>Metadata workbook and source authorization</summary>

Run `python tools/audio-online/metadata_enrichment_cli.py`. These commands contact configured
online sources. Credentials and authorization are stored according to the selected config file.

```powershell
python tools\audio-online\metadata_enrichment_cli.py check-auth beatport
```

| Command | Arguments and options |
| --- | --- |
| `enrich` | `--input PATH` **required**. `--output PATH` **required**. `--config PATH`, default `tools\audio-online\config.toml`. `--db PATH` for local evidence. `--node-executable PATH`. `--node-modules PATH`. XLSX output requires Node plus modules, supplied by environment variables or the two Node options. |
| `authorize SOURCE` | `SOURCE` **required**. `--config PATH`, default `tools\audio-online\config.toml`. Only configured supported OAuth sources can authorize. |
| `check-auth SOURCE` | `SOURCE` **required**. `--config PATH`, default `tools\audio-online\config.toml`. The current authorization check is supported for Beatport. |

</details>

## Grounding and update rule

The command and option inventory was checked against current parser definitions and live `--help`
output from the project environment. When code changes, rerun the relevant `--help` command and
update this page in the same documentation workflow.
