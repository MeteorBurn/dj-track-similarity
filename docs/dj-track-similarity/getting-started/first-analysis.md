# Run your first analysis

> Audience: Users who have scanned tracks and want model-backed search.
> Goal: Choose analysis families safely and understand what each unlocks.
> Type: tutorial

Scanning tells the app what files you own. Analysis gives it several limited ways to compare how
those files sound. The useful result is not a new audio file: it is local evidence that unlocks
shortlists, filters, and ordered previews.

Analysis jobs read audio or stored analysis values and write SQLite results. They do not rewrite
source audio files.

## Choose by the result you want

| You want to | Run | What you get |
| --- | --- | --- |
| Start from a track and find a broad audio neighborhood | MERT | Ranked seed-search candidates |
| Steer by rhythm, texture, dynamics, harmony, or tempo | SONARA | Explainable feature search and transition evidence |
| Describe a desired sound in words | CLAP or MuQ-MuLan | Text-search candidates |
| Compare several model views or inspect duplicates | SONARA, MAEST, MERT, MuQ, MuQ-MuLan, CLAP | Feature-complete candidates for the available workflows |
| Compare another model's neighbors in LAB | MuQ or MuQ-MuLan | A separate result column in Reference Compare |
| Reuse your own labeled concept | CLASSIFIERS | Stored scores for CLASS filters |

For a first experiment, analyze 25 familiar tracks. Try the resulting searches before choosing
which families deserve a full-library run.

## What each family stores and unlocks

| Family | Writes | Unlocks |
| --- | --- | --- |
| SONARA | Core feature row and a dedicated 48D embedding row | Core-backed feature search, confidence-aware tempo, Camelot resolution, Evaluation transition diagnostics, Audio Dedup, classifier inputs |
| MAEST | Core genre/syncopation rows and an Artifacts embedding | genre display, genre tag apply, LAB Reference Compare, Audio Dedup, classifier input |
| MERT | Artifacts embedding | seed search, LAB Reference Compare, Audio Dedup, classifier input |
| MuQ | Artifacts embedding | seed search, LAB Reference Compare, Audio Dedup, classifier input |
| MuQ-MuLan | separate 512D L2-normalized audio embedding | seed search, text-to-track retrieval, optional ANN, and one of the six separate LAB Reference Compare groups |
| CLAP | Artifacts audio embedding | seed and text search, LAB Reference Compare, Audio Dedup, classifier input |
| CLASSIFIERS | Core `classifier_scores` rows | CLASS filters |

Classifier scoring is a separate stage. Each promoted manifest defines its exact SONARA and
MAEST/MERT/MuQ/MuQ-MuLan/CLAP requirements. Incomplete tracks are counted as not ready rather than failed.
The stored SONARA embedding is not a current similarity, search, or classifier input.

## CLI analysis

Install optional analysis dependencies first. Then run:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,mulan,clap --limit 25 --db .\data\library.sqlite
dj-sim analyze-pipeline --stages sonara,ml --db .\data\library.sqlite
```

Useful options:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,mulan,clap --device auto --top-k 3 --track-batch-size 8 --inference-batch-size 16 --db .\data\library.sqlite
```

- `--models` accepts `sonara`, `maest`, `mert`, `muq`, `mulan`, and `clap` as a comma-separated list. Omitting it selects the normal ML order: MAEST, MERT, MuQ, MuQ-MuLan, CLAP.
- `--device` accepts `auto`, `cpu`, or `cuda`.
- `--top-k` stores `1..10` MAEST genre labels per track.
- `--track-batch-size` is `1..64` decoded tracks per job batch. The default is `8`.
- `--inference-batch-size` is `1..128` model samples per forward pass for MAEST, MERT, MuQ, MuQ-MuLan, and CLAP. The default is `16`.
- `--sonara-batch-size` is `1..16` paths per native SONARA batch. The default is `8`.
- `--diagnostics` writes decoder fallback and batch timing details to the file log.

MuQ requires the optional `ml` dependencies and downloads the official `OpenMuQ/MuQ-large-msd-iter` weights. MuQ-MuLan uses the same optional dependencies and the official `OpenMuQ/MuQ-MuLan-large` weights. Both receive mono 24 kHz `float32` audio in 10-second windows. MuQ-MuLan writes its own L2-normalized 512D rows to `mulan_embeddings`. It does not transform MuQ rows. CPU and CUDA are supported, with CUDA recommended for full libraries.

In the CLI, omit `--limit` for the whole library.

## Analyze in the browser

Use the browser model checkboxes to start the same jobs. **Analyze limit** starts at `0` for the
whole eligible library. Track/Inference batch values, Device, SONARA mode settings, progress,
blockers, cancellation, and SQLite-only resets are carried through the typed requests and
responses. **CLASSIFIERS** stays a separate stage; **FULL** runs SONARA, ML, and CLASSIFIERS in
order.

SONARA is selected at startup and always runs Core plus its dedicated embedding as one fixed output
set. There are no output checkboxes. The ML selection contains MAEST, MERT, MuQ, MuQ-MuLan, and CLAP, not
SONARA or CLASSIFIERS.

Browser SONARA analysis has two modes:

| Mode or control | Initial value | Range or behavior |
| --- | ---: | --- |
| **Direct Mode / BatchSize** | `8` | `1..16`; native SONARA reads source paths directly |
| **Staged Mode / Folder** | empty | Choose an existing temporary folder before starting |
| **Staged Mode / Processes** | `4` | `1..16` worker processes |
| **Staged Mode / Threads** | `4` | `1..64` Rayon threads per process |
| **Staged Mode / BatchSize** | `4` | `1..16` ready files per native mini-batch |
| **Staged Mode / StageSize** | `32` | `1..512` files in the staging window |

Direct Mode is the initial mode. The read-only staging-folder field and its picker stay visible but
disabled in Direct Mode. They become active in Staged Mode. The folder has no initial path or
placeholder, and switching modes preserves the selected path and the two independent BatchSize
values. These settings are stored as one browser-local `localStorage` object rather than in SQLite.

Staged Mode is intended for source libraries on slower disks. It copies selected files without
changing or moving their originals to a temporary per-job directory below the selected folder. Only
staging-copy paths are supplied to `sonara.analyze_batch()` and, when needed, FFmpeg. The stored
result, job status, and error still belong to the original track.

StageSize bounds the total in-flight staging window. The count includes copy tasks plus files in the
ready queue or under analysis. A completed copy joins one shared ready queue. Each free process
immediately takes up to the configured Staged BatchSize and sets `RAYON_NUM_THREADS` from Threads;
one process does not wait for another process's mini-batch. This is SONARA CPU/Rust execution, not
ML inference batching.

SONARA normally decodes each staged path through its Symphonia path. If an individual result reports
a decode or codec failure, that staged copy is decoded through FFmpeg to mono `float32` PCM,
resampled for SONARA when necessary, and retried through `analyze_signal()`. If that retry fails,
only that track is reported as failed and other ready work continues. ML models keep a separate
recovery path: after a failed full TorchCodec decode, the requested family retries TorchCodec only
for its configured model windows before it can use a full FFmpeg decode. This does not repair an
invalid source file.

Staging files are released when their native analysis and any fallback finish. The job directory is
removed on completion, failure, or cancellation; a later staging session also clears an abandoned
job directory when its recorded owner process no longer exists. Diagnostics include staging use,
FFmpeg fallback, copy/analyze/store timing, and per-track errors.

Staged Mode applies only to SONARA. MAEST, MERT, MuQ, MuQ-MuLan, and CLAP read the original source
paths and keep their own CPU/CUDA inference path. Their model-window recovery does not use SONARA
staging settings.

After each successful database store or finalized track failure, the existing UI Process Log
immediately shows `Track analyzed`, `Track analyzed [ffmpeg decode]`, or `Track failed` for the
original source file. It does not wait for the whole staging queue, and staging does not add a
separate UI panel.

## Already analyzed tracks

Analysis jobs target missing results for the selected families. SONARA skips a track only when both
its current Core row and dedicated embedding row are present. If either row is missing, a normal
SONARA rerun analyzes the track and stores both rows together, atomically per track. Other complete families are skipped.
Use reset only when you intentionally want to delete stored results.

After adopting a SONARA change, adapt storage explicitly if needed and decide which outputs to
reset or reanalyze. Follow [Migrate and reanalyze SONARA storage](../workflows/reanalyze-sonara-split-storage.md).

## Reset boundaries

- Reset SONARA removes Core rows plus dependent classifier scores. Dedicated SONARA embedding rows
  remain. The next normal SONARA run sees Core missing and writes both outputs together. Labels and
  feedback remain intact.
- Reset MAEST removes MAEST metadata and MAEST embeddings.
- Reset MERT, MuQ, MuQ-MuLan, or CLAP deletes embeddings for that key.
- Reset CLASSIFIERS deletes selected classifier scores only.

All reset operations are SQLite-only.
