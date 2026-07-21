# Analyze the library from the UI

> Audience: Users running analysis jobs in the browser.
> Goal: Explain model selection, job progress, and reset behavior.
> Type: guide

Use the analysis area after scanning tracks. Analysis reads audio and writes SQLite results. It does not modify source audio files.

## Pick models

The UI lists these choices:

- **SONARA**: audio features and working BPM/key/energy/duration data.
- **MAEST**: genre label output plus syncopated-rhythm metadata and the MAEST embedding.
- **MERT**: audio embedding for seed similarity.
- **MuQ**: 24 kHz `float32` audio embedding used by LAB Reference Compare.
- **CLAP**: audio embedding for text search and audio-to-audio comparison.
- **CLASSIFIERS**: promoted classifier scores, if compatible profiles are available.

The UI separates analysis into stage blocks with individual manual run buttons. The SONARA, ML
MODELS, and CLASSIFIERS blocks can also be submitted as one selected pipeline. All stages use one
sequential in-memory queue.

SONARA runs separately from the ML models and classifiers. It passes path batches to
`sonara.analyze_batch()`, whose Symphonia path owns decoding. There is no project FFmpeg,
`DecodedAudio`, `analyze_signal`, or per-file fallback in the SONARA job. SONARA BPM analysis uses
the project range `70.0..180.0`. Tempo-aware workflows start with current
signed SONARA evidence but do not trust it blindly. Below `0.45` confidence, the resolver checks
SONARA candidates and the Mutagen BPM tag. A corroborated tag can become the working BPM.
`grid_stability` can lower reliability, which moves the tempo score toward neutral. If you analyzed
tracks before the current range was configured, select SONARA and run analysis again. The legacy
signature does not match, so those tracks are queued automatically without a reset.

The default SONARA v0.2.9 Core result also stores raw BPM, `bpm_confidence`, tempo candidates, Camelot key, compact structure/loudness data, vocalness v2, mood, and other lightweight values. The metadata dialog shows Core values beside saved provenance such as schema version, sample rate, hop length, analysis mode, requested features, and installed package version.

## Choose SONARA outputs

When SONARA is selected, three checkboxes appear:

- **Core** (default) writes lightweight scalar and fixed-vector results to the selected main database.
- **Timeline** writes complete time arrays, events, and segments to the adjacent `*.timeline.sqlite` database.
- **Representations** writes the SONARA embedding and fingerprint to the adjacent `*.representations.sqlite` database.

You can run Core first and add Timeline or Representations later. One native batch requests the
union of selected outputs from Rust. Each output has its own deterministic
signature, so adding Timeline does not invalidate a current Core result.

Mood and instrumentalness are stored and displayed but do not enter current similarity, SET,
Hybrid, or classifier calculations. True peak and ReplayGain are stored for possible future
loudness-management work rather than direct SONARA similarity scoring. Complete beat/onset
positions, chord labels/events, tempo, energy and loudness curves, downbeat arrays, and structure
segments are Timeline data. The SONARA embedding and fingerprint are Representations data.

The metadata dialog displays all Core values. For Timeline and Representations it displays only
`Data present` plus the exact stored field names. It never loads the heavy values just to open the
dialog. The Timeline API remains available for future workflows that explicitly need the payload.

## Limit behavior

`Analyze limit = 0` in the UI means the whole library. Positive limits count tracks missing selected results.

The CLI differs: omit `--limit` for the whole library.

## Device

- `AUTO` selects CUDA when PyTorch sees a GPU, otherwise CPU.
- `CPU` forces CPU.
- `CUDA` requests CUDA and should fail clearly if CUDA is unavailable.

SONARA runs as a CPU runner. MAEST, MERT, MuQ, and CLAP use the selected device through their adapters. MuQ uses official `OpenMuQ/MuQ-large-msd-iter` weights and is fed only 24 kHz `float32` audio. It currently supports LAB Reference Compare, with no SET, Hybrid, Audio Dedup, or classifier-scoring integration.

## Batch controls

- **SONARA native batch**: `1..128` paths; default `64`. Cancellation takes effect between returned batches.
- **Track batch size**: `1..64`, decoded tracks held and processed together.
- **Inference batch size**: `1..128`, MAEST/MERT/MuQ/CLAP model samples per forward pass.

Lower these if memory is tight. Increase only after a small test batch works.

## Progress and logs

The UI polls the current job and shows:

- state: queued, running, completed, cancelled, or failed,
- total, processed, analyzed, failed, and skipped counts,
- current model and path,
- per-model progress,
- event log and errors.

The square stop button requests cancellation. It does not kill Python mid-write. A SONARA chunk is
persisted only after the native batch returns, and cancellation is checked before the next chunk.

## Pipeline and classifier readiness

The selected pipeline always runs SONARA, then ML, then CLASSIFIERS, regardless of selection order.
Per-file errors remain visible but do not stop later stages; fatal initialization errors and
cancellation stop the parent and cancel stages that have not started.

CLASSIFIERS never decode audio. The block shows ready/not-ready counts and manifest blockers. Its
total counts classifier-track pairs that are ready and have a missing score or a score from another
model ID. Rerun the stage later to pick up tracks that became ready after more SONARA or ML coverage.

## Reset buttons

Reset is SQLite-only:

- SONARA reset removes Core features, Timeline rows, SONARA embedding/fingerprint rows, flags, and dependent main-library classifier scores. Labels and feedback remain intact.
- MAEST reset removes MAEST metadata and MAEST embeddings.
- MERT, MuQ, and CLAP reset delete embeddings for that key.
- CLASSIFIERS reset deletes selected `track_classifier_scores` rows.

Before the first native SONARA job, old-contract data is a blocker. Back up the database and use the
explicit SONARA reset; the application does not adapt, mix, or automatically delete those rows.
Afterward, current partial output coverage can resume normally by signature.

For a complete existing-library procedure, including backups and classifier rebuilding, follow
[Reanalyze with split SONARA storage](../workflows/reanalyze-sonara-split-storage.md).
