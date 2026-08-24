# Run your first analysis

Scanning tells the app what files you own. Analysis gives it several limited ways to compare how
those files sound. No new audio file comes out of it. What you get is local evidence that unlocks
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
| SONARA | Core feature row, a dedicated 48D embedding row, and a versioned acoustic fingerprint row | Core-backed feature search, confidence-aware tempo, Camelot resolution, Evaluation transition diagnostics, Audio Dedup, classifier inputs; the fingerprint has no current UI, search, classifier, or dedup use |
| MAEST | `maest_genres` rows and a `maest_embeddings` row | genre display, genre tag apply, LAB Reference Compare, Audio Dedup, classifier input |
| MERT | a row in `mert_embeddings` | seed search, LAB Reference Compare, Audio Dedup, classifier input |
| MuQ | a row in `muq_embeddings` | seed search, LAB Reference Compare, Audio Dedup, classifier input |
| MuQ-MuLan | separate 512D L2-normalized audio embedding | seed search, text-to-track retrieval, optional ANN, and one of the six separate LAB Reference Compare groups |
| CLAP | a row in `clap_embeddings` | seed and text search, LAB Reference Compare, Audio Dedup, classifier input |
| CLASSIFIERS | rows in `classifier_scores` | CLASS filters |

Classifier scoring is a separate stage. Each promoted manifest defines its exact SONARA and
MAEST/MERT/MuQ/MuQ-MuLan/CLAP requirements. Incomplete tracks are counted as not ready rather than failed.
The stored SONARA embedding is not a current similarity, search, or classifier input.

## Choose a SONARA BPM range for your library

The SONARA BPM range is an analysis input, not a playback-tempo limit or a search threshold. Tempo
estimators can describe the same rhythmic pulse at half-time or double-time. A 174 BPM drum-and-bass
track can be useful to a DJ as 87 BPM. SONARA uses the supplied range to fold octave-related
tempo estimates into one working interpretation. Its lower and upper bounds need to span at
least one octave. See [SONARA BPM range](../reference/analysis-families.md#sonara-bpm-range) for the
project's stored range and exact analysis behavior.

There is no genre-independent correct window. It reflects how you want tempo to be represented in your
own library: whether a half-time break is filed near its slower pulse or near its full drum pattern, and
whether a mixed collection needs room for both slow and fast material. A narrow, genre-focused window can
make the chosen convention more consistent. A broad window is often a better first pass for a varied
library, followed by listening checks and review of BPM candidates for tracks whose pulse can reasonably
be read two ways.

These familiar application ranges are useful reference starting points, not universal genre standards or
guarantees about the defaults in every product version:

| Application | Reference BPM range |
| --- | ---: |
| Mixed In Key | 79 to 192 |
| rekordbox | 70 to 180 |
| Serato | 96 to 190 |

For a cross-genre collection, begin with the project range of 70 to 180 BPM. It was chosen from the
70 to 180 BPM rekordbox reference range and is recorded in [SONARA BPM range](../reference/analysis-families.md#sonara-bpm-range).
Decide later whether your collection needs a different interpretation window. Keep one convention within a
workflow when practical: otherwise an apparent BPM mismatch may only be a half/double-time representation.

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

SONARA is selected at startup and always runs one fixed output set. It includes Core data plus its
dedicated embedding and acoustic fingerprint. There are no output checkboxes. The ML selection contains MAEST, MERT, MuQ, MuQ-MuLan, and CLAP, not
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
staging-copy paths are supplied to `sonara.analyze_batch()` and, when native decoding fails, to its
PyAV recovery decoder from the active Python environment. The stored result, job status, and error
still belong to the original track.

StageSize bounds the total in-flight staging window. The count includes copy tasks plus files in the
ready queue or under analysis. A completed copy joins one shared ready queue. Each free process
immediately takes up to the configured Staged BatchSize and sets `RAYON_NUM_THREADS` from Threads;
one process does not wait for another process's mini-batch. This is SONARA CPU/Rust execution, not
ML inference batching.

SONARA normally decodes each staged path through its Symphonia path. If an individual result reports
a decode or codec failure, the project loads PyAV `17.1.0` from the active Python environment after
registering the validated FFmpeg `8.1.1` full shared runtime. It opens the same input with
`fflags=+discardcorrupt+genpts` and passes `err_detect=ignore_err` to the decoder. It retains valid
decoded frames, discards only a malformed `AVERROR_INVALIDDATA` packet, downmixes the PCM by the
arithmetic channel mean to mono `float32`, resamples for SONARA when necessary, and retries through
`analyze_signal()`. If that retry fails, only that track is reported as failed and other ready work
continues. ML models keep a separate recovery path: after a failed full TorchCodec decode, the
requested family makes its own in-process shared-library TorchCodec recovery. Neither recovery path
starts `ffmpeg.exe` or repairs an invalid source file.

Staging files are normally released when their native analysis and any fallback finish. If Windows
reports `WinError 32` or `WinError 64` for a completed copy, the runner logs the error at warning
level and skips its immediate deletion. Analysis continues with other tracks. Final session cleanup
attempts removal after the analyzer and copy worker pools exit. A later staging session also clears an
abandoned job directory when its recorded owner process no longer exists. Diagnostics include
staging use, shared-library recovery, copy/analyze/store timing, and per-track errors.

Staged Mode applies only to SONARA. MAEST, MERT, MuQ, MuQ-MuLan, and CLAP read the original source
paths and keep their own CPU/CUDA inference path. Their shared-library recovery does not use
SONARA staging settings, and their adapters retain model-specific resampling and window selection.

After each successful database store or finalized track failure, the existing UI Process Log
immediately shows one decode label for ML analysis: `[torchcodec] Track analyzed`, `[ffmpeg] Track
analyzed`, or `Track failed`. The first label means the initial full-track TorchCodec read
succeeded. The second is the existing recovery label and means direct shared-library TorchCodec
recovery was used, not that an `ffmpeg.exe` process ran. SONARA keeps its own event convention: a
normal Direct or Staged success is `Track analyzed`, while its PyAV/FFmpeg shared-library recovery
is `[ffmpeg] Track analyzed`. Events use the original source file and do not wait for the whole
staging queue. Staging does not add a separate UI panel.

## Already analyzed tracks

Analysis jobs target missing results for the selected families. SONARA skips a track only when its
current Core, dedicated embedding, and acoustic fingerprint rows are present. If any row is missing,
a normal SONARA rerun analyzes the track and stores all three rows together, atomically per track.
Other complete families are skipped.
Use reset only when you intentionally want to delete stored results.

After adopting a SONARA change, adapt storage explicitly if needed and decide which outputs to
reset or reanalyze. Follow [Migrate and reanalyze SONARA storage](../workflows/reanalyze-sonara-split-storage.md).

## Reset boundaries

- Reset SONARA removes Core rows plus dependent classifier scores. Dedicated SONARA embedding and
  fingerprint rows remain. The next normal SONARA run sees Core missing and writes all three outputs
  together. Labels and feedback remain intact.
- Reset MAEST removes MAEST metadata and MAEST embeddings.
- Reset MERT, MuQ, MuQ-MuLan, or CLAP deletes embeddings for that key.
- Reset CLASSIFIERS deletes selected classifier scores only.

All reset operations are SQLite-only.
