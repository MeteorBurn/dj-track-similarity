# Analyze a library

Analysis reads source audio and writes local SQLite state. It does not modify source audio files.
Scan first, then pick the analysis family that answers your listening question.

Control names below are given in English. Panel 1 setting labels are already English on screen. The
full mapping to the on-screen strings is in [UI language](../help/ui-language.md).

## The analysis block

Panel 1, database and analysis, holds one analysis block headed **Analysis**, with the note that one
run processes the selected stages and skips results that already exist.

Two cards sit under that heading:

- The first carries a single `SONARA` row.
- The second is headed **ML models** with the rows `MAEST`, `MERT`, `MUQ`, `MULAN`, and `CLAP`.

Each row shows a checkbox, the model name in capitals, a Russian one-line description, the current
analyzed count, and a trash icon titled **Reset `<MODEL>`**.

Only these six checkboxes form the selection. Classifier scoring is started from the
[CLASS tab](./class-tab.md) or the CLI, and it is not a checkbox here. One `Analyze` press runs the
selected stages in the fixed order SONARA, then ML, which its tooltip states as running the checked
models in SONARA then ML order.

The five ML checkboxes stay disabled until at least one track carries a SONARA row. Starting an ML
stage without one is refused with a notice saying to run SONARA on at least one track first. A
library reporting zero SONARA rows has its selection forced back to SONARA alone. The selection can
never be emptied.

Analysis start is announced in the log as "analysis started, SONARA then the ML models, whole
library", naming the stages and the scope.

## Shared settings

| Control | Initial value | Range |
| --- | ---: | --- |
| `Device` | `AUTO` | `AUTO`, `CPU`, `CUDA` |
| `Track batch` | `8` | `1..64` |
| `Inference batch` | `16` | `1..128` |
| `Analyze limit` | `0` | `0..100000`, where `0` means every eligible track |

`Analyze limit` applies separately to each stage, which its own hint states: `0` means every track,
applied per analysis stage. `Device` covers MAEST, MERT, MuQ, MuQ-MuLan, and CLAP inference. SONARA
uses its native CPU path.

## Direct and Staged modes

Both families have a `Mode` selector with `Direct` and `Staged`, starting on `Direct`. Their
tooltips are **Read the source audio files directly** and **Copy input files into a temporary SSD
folder**.

The ML card in panel 1 carries its own selector inline. SONARA's selector instead lives in the
**SONARA analysis settings** dialog, opened from a button on the SONARA card. That dialog also
carries the SONARA BPM range. See
[SONARA settings dialog](../reference/ui-controls.md#sonara-settings-dialog).

SONARA Staged exposes a staging folder plus `Processes` (`1..16`, default `4`), `Threads`
(`1..64`, default `4`), `BatchSize` (`1..16`, default `4`), and `StageSize` (`1..512`, default
`32`). SONARA Direct exposes only `BatchSize` (`1..16`, default `8`).

ML Staged exposes a staging folder plus `Workers` (`1..16`, default `4`) and `StageSize`
(`1..512`, default `64`). The single `Workers` value is sent as both `copy_workers` and
`decode_workers`, so the browser cannot set them apart. The CLI can, through `--ml-copy-workers` and
`--ml-decode-workers`.

Both staging folders start empty, and a Staged run needs one chosen first. A missing folder is
refused with a notice to choose a staging folder before starting Staged Mode. Neither folder is
restored from `localStorage`, because it receives temporary copies of your audio, so every session
asks for it again.

Full mode semantics, decode recovery, and staging cleanup are documented in
[First analysis](../getting-started/first-analysis.md).

## What happens after you press Analyze

A started job loads its models before it reads the first track. For that stretch the process box
shows a warm-up view headed **Model warm-up** instead of per-track progress. The view has a progress
bar over the number of selected models, the current model name, and its resolved device. A line
under them reads that models are being loaded into memory and that track decoding has not started.
The top-bar stage indicator shows **Model warm-up** while this lasts.

Candidate selection happens after warm-up, so the job total stays `0` until loading finishes. When
loading ends, the usual per-track progress box replaces the warm-up view and the counters start
moving.

An empty-looking gap at the start of a first run is normally this phase. Model weights download on
first use, so the first job for a family waits for that download here rather than in the middle of
track work. A model that cannot load fails the job during warm-up, before any track is read. Once a
model is loaded it stays in memory for the life of the server process, so a repeated job with the
same models, device, and batch settings passes warm-up without loading again. The job log entries
are listed in [Model warm-up](../reference/analysis-families.md#model-warm-up).

## Progress, cancellation, and failures

The top-bar log button opens the process box and the merged event log, which keeps up to `200`
events. The analysis box reports the raw job state, the running model and device, then counters for
processed over total, `ok`, `fail`, `skip`, the active SONARA mode, batch sizes, and a percentage.

A track counts as `analyzed` only when its successes reach its target model count. Any failure
counts it as `failed`, and anything else counts as `skipped`.

Cancellation is the square Stop icon in the top bar, titled **Stop the current scan or analysis**.
It sets a cancel request that the run loop checks between batches and between models, so a running
batch finishes first.

A SONARA batch failure fails the whole job, while an ML batch failure is retried track by track with
each track's error recorded individually. Per-file failures stay in the job status and do not stop
the next stage. A fatal initialization failure or cancellation does.

Jobs are serialized through one queue shared by SONARA, ML, and classifier stages, so only one runs
at a time.

## Run a family from the CLI

SONARA runs alone and writes its fixed Core, embedding, and fingerprint output set:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
```

ML families can run together:

```powershell
dj-sim analyze --models maest,mert,muq,mulan,clap --db .\data\library.sqlite
```

Combining `sonara` with any ML model in one job is rejected. Use `dj-sim analyze-pipeline --stages
sonara,ml` for both in one command, which is what the browser `Analyze` button submits.

Omit `--limit` to consider the whole library. A positive limit selects only candidates missing the
requested current outputs.

## SONARA storage

SONARA writes Core feature rows to `sonara_features`, unnormalized 48-dimensional `float32`
embeddings to the dedicated `sonara_embeddings` table, and versioned native-base64 acoustic
fingerprints to `sonara_fingerprints`. A successful SONARA pass stores all three rows together under
one per-track savepoint. Timeline collection remains disabled.

The SONARA embedding is persisted data only. It is not a current UI, similarity, search, classifier,
or Audio Dedup input. The fingerprint is not a UI, similarity, search, or classifier input either.
Audio Dedup reads it for candidate retrieval and manual review, its one current consumer.

MAEST, MERT, MuQ, MuQ-MuLan, and CLAP embeddings live in their own dedicated tables in the same
library database. MuQ-MuLan analysis reads mono 24 kHz `float32` audio in 10-second windows and
writes its own L2-normalized 512-dimensional rows to `mulan_embeddings`. It never converts existing
MuQ rows.

`*.evaluation.sqlite` is optional evaluation state. Normal startup refuses a legacy split layout
rather than adapting it automatically.

## Reset and reanalysis

Each model row's trash icon resets that family only, after a confirmation that asks whether to reset
that family's results and states that the audio files stay untouched and the other families remain.

- SONARA reset deletes `sonara_features` Core rows. The SONARA embedding rows, the fingerprint rows,
  and every classifier score survive.
- MAEST reset deletes MAEST genre rows and MAEST embeddings.
- MERT, MuQ, MuQ-MuLan, and CLAP reset delete embeddings for that family.

Resets affect SQLite data only and do not start a new job. A normal SONARA rerun then selects a
track when any current Core, embedding, or fingerprint row is missing and stores all three rows
together. Tracks with all three rows remain skipped.

Classifier scores have their own reset in the [CLASS tab](./class-tab.md), scoped to one
`classifier_key`. Retrain and promote a classifier only when its ordered feature recipe changed. See
[Reanalyze SONARA data](../workflows/reanalyze-sonara-split-storage.md).

Model outputs are ranking evidence for listening-led shortlists, not objective truth or automatic DJ
decisions.
