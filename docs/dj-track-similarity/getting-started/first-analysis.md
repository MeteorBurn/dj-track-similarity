# Run your first analysis

Scanning tells the app what files you own. Analysis gives it several limited ways to compare how
those files sound. No new audio file comes out of it. What you get is local evidence that unlocks
shortlists, filters, and ordered previews.

Analysis jobs read audio or stored analysis values and write SQLite results. They do not rewrite
source audio files.

Control names below are given as the Russian string the browser shows, with the English meaning in
parentheses. Panel 1 setting labels themselves stay English. The full mapping is in
[UI language](../help/ui-language.md).

## Choose by the result you want

| You want to | Run | What you get |
| --- | --- | --- |
| Start from a track and find a broad audio neighborhood | MERT | Ranked seed-search candidates |
| Steer by rhythm, texture, dynamics, harmony, or tempo | SONARA | Explainable feature search and transition evidence |
| Describe a desired sound in words | CLAP or MuQ-MuLan | Text-search candidates |
| Compare several model views or inspect duplicates | SONARA, MAEST, MERT, MuQ, MuQ-MuLan, CLAP | Feature-complete candidates for the available workflows |
| Compare another model's neighbors in LAB | MuQ or MuQ-MuLan | A separate result column in Reference Compare |
| Reuse your own labeled concept | Classifier scoring | Stored scores for CLASS filters |

For a first experiment, analyze 25 familiar tracks. Try the resulting searches before choosing
which families deserve a full-library run.

## SONARA runs first, and alone

A single analysis job takes either `sonara` or a set of ML models. Mixing them in one job is
rejected with `SONARA analysis must run alone and cannot be combined with ML models`. The browser
`Analyze` button hides that split behind one press: it submits a pipeline whose fixed stage order is
SONARA, then ML.

An ML job is also refused while no track carries a current SONARA row. In the browser the ML
checkboxes stay disabled until at least one SONARA row exists, and a blocked start shows the notice
`Сначала выполните SONARA-анализ хотя бы одного трека` (run SONARA analysis on at least one track
first).

## What each family stores and unlocks

| Family | Writes | Unlocks |
| --- | --- | --- |
| SONARA | Core feature row in `sonara_features`, a dedicated 48D embedding row, and a versioned acoustic fingerprint row | Core-backed feature search, confidence-aware tempo, Camelot resolution, Evaluation transition diagnostics, Audio Dedup, classifier inputs. The fingerprint's only current use is Audio Dedup candidate retrieval and manual review |
| MAEST | `maest_genres` rows and a `maest_embeddings` row | genre display, genre tag apply, LAB Reference Compare, Audio Dedup, classifier input |
| MERT | a row in `mert_embeddings` | seed search, LAB Reference Compare, Audio Dedup, classifier input |
| MuQ | a row in `muq_embeddings` | seed search, LAB Reference Compare, Audio Dedup, classifier input |
| MuQ-MuLan | a 512D L2-normalized row in `mulan_embeddings` | seed search, text-to-track retrieval, one of the six separate LAB Reference Compare groups, and classifier input |
| CLAP | a row in `clap_embeddings` | seed search from the API, text search, LAB Reference Compare, Audio Dedup, classifier input |

Classifier scoring is a separate stage started from the `CLASS` tab or the CLI, not from panel 1.
Each promoted manifest defines its exact SONARA and MAEST/MERT/MuQ/MuQ-MuLan/CLAP requirements.
Tracks missing any required input are excluded from the candidate query before the job total is
formed, so they are neither counted nor failed.

The stored SONARA 48-dimensional embedding has no current reader outside candidate selection and
schema validation. It is written deliberately and is not a similarity, search, or classifier input.

## Choose a SONARA BPM range for your library

The SONARA BPM range is an analysis input. It is neither a playback-tempo limit nor a search
threshold. Tempo estimators can describe the same rhythmic pulse at half-time or double-time. A 174
BPM drum-and-bass track can be useful to a DJ as 87 BPM. SONARA uses the supplied range to fold
octave-related tempo estimates into one working interpretation, so the upper bound must be at least
twice the lower one. Both bounds accept `20` to `400`.

There is no genre-independent correct window. It reflects how you want tempo to be represented in your
own library: whether a half-time break is filed near its slower pulse or near its full drum pattern, and
whether a mixed collection needs room for both slow and fast material. A narrow, genre-focused window can
make the chosen convention more consistent. A broad window is often a better first pass for a varied
library, followed by listening checks and review of BPM candidates for tracks whose pulse can reasonably
be read two ways.

The browser offers three preset chips in the import dialog: `Rekordbox` (70 to 180), `VirtualDJ`
(80 to 240), and `Mixed In Key` (79 to 192). Your own pair is accepted too. The CLI takes
`--sonara-bpm-min` and `--sonara-bpm-max`, defaulting to 70 and 180.

Whatever you pick, the first SONARA analysis fixes it for the whole library. Any later run must
reuse that range, and a job requesting a different one is refused with an instruction to reset
SONARA analysis first. Details are in
[SONARA BPM range](../reference/analysis-families.md#sonara-bpm-range) and the picker is documented
in [First library](./first-library.md).

Keep one convention within a workflow when practical. Otherwise an apparent BPM mismatch may only
be a half/double-time representation.

## CLI analysis

Install optional analysis dependencies first. Then run:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,mulan,clap --limit 25 --db .\data\library.sqlite
dj-sim analyze-pipeline --stages sonara,ml --db .\data\library.sqlite
```

Useful options:

```powershell
dj-sim analyze --models sonara --sonara-batch-size 8 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,mulan,clap --device auto --top-k 3 --track-batch-size 8 --inference-batch-size 16 --db .\data\library.sqlite
```

- `--models` accepts `sonara`, `maest`, `mert`, `muq`, `mulan`, and `clap` as a comma-separated list. Omitting it selects the normal ML order: MAEST, MERT, MuQ, MuQ-MuLan, CLAP.
- `--device` accepts `auto`, `cpu`, or `cuda`.
- `--top-k` stores `1..10` MAEST genre labels per track. The default is `3`.
- `--track-batch-size` is `1..64` decoded tracks per job batch. The default is `8`.
- `--inference-batch-size` is `1..128` model samples per forward pass for MAEST, MERT, MuQ, MuQ-MuLan, and CLAP. The default is `16`.
- `--sonara-batch-size` is `1..16` paths per native SONARA batch. The default is `8`.
- `--sonara-bpm-min` and `--sonara-bpm-max` set the library range on the first run. Defaults are `70` and `180`.
- `--ml-staged` with `--ml-staging-path` enables ML Staged Mode. Its tuning flags are `--ml-copy-workers` (`1..16`, default `4`), `--ml-decode-workers` (`1..32`, default `8`), and `--ml-stage-size` (`1..512`, default `64`). A missing or non-existent staging path exits with code 1.
- `--diagnostics` writes decoder fallback and batch timing details to the file log.

MuQ requires the optional `ml` dependencies and downloads the official `OpenMuQ/MuQ-large-msd-iter` weights. MuQ-MuLan uses the same optional dependencies and the official `OpenMuQ/MuQ-MuLan-large` weights. Both receive mono 24 kHz `float32` audio in 10-second windows. MuQ-MuLan writes its own L2-normalized 512D rows to `mulan_embeddings`. It does not transform MuQ rows. CPU and CUDA are supported, with CUDA recommended for full libraries.

In the CLI, omit `--limit` for the whole library.

## The first run loads models first

Any analysis job loads every selected model before it decodes a track, and reports that as a warm-up
phase. Weights are fetched on first use rather than during installation, and no prefetch command
exists, so the first job for a family spends this phase downloading and verifying its weights into
the local cache as well as loading them. A quiet stretch before the track counter moves is normally
this. Candidate selection happens after warm-up, so the job total stays `0` until loading finishes.
Later jobs in the same server session reuse the loaded models and pass warm-up without loading
again. Details and the job log entries are in
[Model warm-up](../reference/analysis-families.md#model-warm-up).

## Analyze in the browser

Panel `1. База и анализ` (database and analysis) holds one analysis block under the heading `Анализ`
with the note `Один запуск обработает выбранные стадии и пропустит уже готовые результаты` (one run
processes the selected stages and skips results that already exist).

The block has two cards. The first carries the `SONARA` row. The second is headed `ML-модели`
(ML models) with the rows `MAEST`, `MERT`, `MUQ`, `MULAN`, and `CLAP`. Each row shows a checkbox,
the model name, a Russian one-line description, the current analyzed count, and a trash icon titled
`Сбросить <MODEL>` (reset that model).

There is no classifier checkbox and no combined-run button in this panel. The selection is drawn
from the SONARA row and the five ML rows only, and one `Analyze` press runs the selected stages in
the order SONARA, then ML. Its tooltip states exactly that:
`Запустить отмеченные модели в порядке SONARA → ML`.

Shared settings sit under the ML card:

| Control | Initial value | Range |
| --- | ---: | --- |
| `Device` | `AUTO` | `AUTO`, `CPU`, `CUDA` |
| `Track batch` | `8` | `1..64` |
| `Inference batch` | `16` | `1..128` |
| `Analyze limit` | `0` | `0..100000`, where `0` means every eligible track |

`Analyze limit` applies separately to each stage, which its own hint states:
`0 = все треки; применяется отдельно к каждой стадии анализа`.

To stop a running stage, press the square Stop icon in the top bar, titled
`Остановить текущий scan или анализ` (stop the current scan or analysis). Cancellation is
cooperative: the run loop checks it between batches and between models.

## Direct and Staged modes

Both cards carry a `Mode` selector with `Direct` and `Staged`. Their tooltips are
`Читать исходные аудиофайлы напрямую` (read the source audio files directly) and
`Копировать входные файлы во временную SSD-папку` (copy the input files into a temporary SSD
folder). Direct is the initial mode for both.

Staged Mode is intended for source libraries on slower disks. It copies selected files read-only
into a temporary per-job directory below the folder you choose, without changing or moving the
originals. The stored result, job status, and error still belong to the original track.

### SONARA settings

| Mode | Control | Initial value | Range |
| --- | --- | ---: | --- |
| Direct | `BatchSize` | `8` | `1..16` native SONARA paths per batch |
| Staged | staging folder | empty | choose an existing folder before starting |
| Staged | `Processes` | `4` | `1..16` worker processes |
| Staged | `Threads` | `4` | `1..64` Rayon threads per process |
| Staged | `BatchSize` | `4` | `1..16` ready files per native mini-batch |
| Staged | `StageSize` | `32` | `1..512` files in the staging window |

The folder picker is titled `Choose Folder для staging-копий`. Switching modes preserves the
selected path and the two independent BatchSize values.

StageSize bounds the total in-flight staging window. The count includes copy tasks plus files in the
ready queue or under analysis. A completed copy joins one shared ready queue. Each free process
immediately takes up to the configured Staged BatchSize and sets `RAYON_NUM_THREADS` from Threads.
One process does not wait for another process's mini-batch. This is SONARA CPU/Rust execution, not
ML inference batching.

### ML settings

| Mode | Control | Initial value | Range |
| --- | --- | ---: | --- |
| Staged | staging folder | empty | choose an existing folder before starting |
| Staged | `Workers` | `4` | `1..16` |
| Staged | `StageSize` | `64` | `1..512` files in the staging window |

The ML folder picker is titled `Choose Folder для ML staging-копий`. The single `Workers` value is
sent as both `copy_workers` and `decode_workers`, so the browser cannot set them apart. The CLI can,
through `--ml-copy-workers` and `--ml-decode-workers`.

ML Staged Mode copies selected ML candidates read-only, then runs copy, decode, and inference. Its
StageSize bounds the active staging window rather than the whole job. Each completed track has its
staging copy deleted, and the window refills until every candidate in the current ML job has
finished.

Starting Staged Mode with an empty folder is refused with the notice
`Выберите папку staging перед запуском Staged Mode` (choose a staging folder before starting Staged
Mode).

### Where these settings live

SONARA and ML mode settings are kept as two browser `localStorage` objects,
`dj-track-similarity.sonara-analysis-settings` and `dj-track-similarity.ml-analysis-settings`. The
staging folder is deliberately excluded from both, because it receives temporary copies of your
audio, so every session asks for it again.

## Decode recovery

SONARA normally decodes each path through its Symphonia path. If an individual result reports a
decode or codec failure, the project loads PyAV `17.1.0` from the active Python environment after
registering the validated FFmpeg `8.1.1` full shared runtime. It opens the same input with
`fflags=+discardcorrupt+genpts` and passes `err_detect=ignore_err` to the decoder. It retains valid
decoded frames, discards only a malformed `AVERROR_INVALIDDATA` packet, downmixes the PCM by the
arithmetic channel mean to mono `float32`, resamples for SONARA when necessary, and retries through
`analyze_signal()`. If that retry fails, only that track is reported as failed and other ready work
continues.

ML models reach the same tolerant decoder by their own route. After a failed full TorchCodec decode,
the requested family retries the file with PyAV over the shared libraries and uses the frames it
recovers. Neither recovery path starts `ffmpeg.exe` or repairs an invalid source file.

Batch failure policy differs by family. A SONARA batch failure fails the whole job. An ML batch
failure is retried track by track, and each track's error is recorded individually.

After each successful database store or finalized track failure, the Process Log immediately shows
one decode label for ML analysis: `[torchcodec] Track analyzed`, `[ffmpeg] Track analyzed`, or
`Track failed`. The first label means the initial full-track TorchCodec read succeeded. The second
means the tolerant PyAV shared-library decode was used, not that an `ffmpeg.exe` process ran.
`Track failed` means both decoders failed. SONARA keeps its own convention: a normal Direct or
Staged success is `Track analyzed`, while its PyAV shared-library recovery is
`[ffmpeg] Track analyzed`.

## Staging cleanup

Staging files are normally released when their native analysis and any fallback finish. If Windows
reports `WinError 32` or `WinError 64` for a completed copy, the runner logs the error at warning
level and skips its immediate deletion. Analysis continues with other tracks. Final session cleanup
attempts removal after the analyzer and copy worker pools exit.

Each SONARA staged run uses a new unique job directory carrying an `.owner` marker with its process
ID. Before creating one, the runner removes owner-marked directories whose recorded process is gone
and empty `sonara-stage-*` residue without a valid marker. It preserves a directory with a live
owner and a nonempty directory without a valid marker.

## Already analyzed tracks

Analysis jobs target missing results for the selected families. SONARA skips a track only when its
current Core, dedicated embedding, and acoustic fingerprint rows are all present. If any row is
missing, a normal SONARA rerun analyzes the track and stores all three rows together, atomically per
track. Other complete families are skipped.

Use reset only when you intentionally want to delete stored results.

After adopting a SONARA change, adapt storage explicitly if needed and decide which outputs to
reset or reanalyze. Follow [Reanalyze SONARA data](../workflows/reanalyze-sonara-split-storage.md).

## Reset boundaries

Each model row carries its own trash icon. Pressing it asks
`Сбросить <MODEL>?` with the message
`Сбросить результаты <MODEL>? Аудиофайлы не трогаем, остальные алгоритмы останутся.`
(reset that model's results, source audio untouched, other algorithms retained).

| Reset | Deletes | Keeps |
| --- | --- | --- |
| SONARA | `sonara_features` Core rows | the dedicated SONARA embedding rows, the fingerprint rows, every classifier score, labels, and feedback |
| MAEST | MAEST genre rows and MAEST embeddings | everything else |
| MERT, MuQ, MuQ-MuLan, CLAP | embeddings for that family | everything else |

Resetting SONARA deletes Core rows only. Classifier scores survive, because classifier scoring is a
separate stage with its own reset in the `CLASS` tab. The SONARA embedding and fingerprint rows
survive too, and the next normal SONARA run sees Core missing and rewrites all three outputs
together.

All reset operations are SQLite-only. They do not touch audio files and do not start a new analysis
job.
