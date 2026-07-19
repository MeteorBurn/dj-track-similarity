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

One job can include multiple families. Tracks that already have a selected result are skipped for that family.

SONARA BPM analysis uses the project range `79.0..192.0`. Tempo-aware workflows start with current
signed SONARA evidence but do not trust it blindly. Below `0.45` confidence, the resolver checks
SONARA candidates and the Mutagen BPM tag. A corroborated tag can become the working BPM.
`grid_stability` can lower reliability, which moves the tempo score toward neutral. If you analyzed
tracks before the current range was configured, select SONARA and run analysis again. The legacy
signature does not match, so those tracks are queued automatically without a reset.

The default SONARA v0.2.4 result also stores raw BPM, `bpm_confidence`, tempo candidates, and Camelot key. The metadata dialog shows the `0..1` BPM confidence beside saved provenance such as schema version, sample rate, hop length, analysis mode, requested features, and installed package version when available.

## Full SONARA capture

SONARA offers eight additional feature families: structure, loudness, beat grid, key candidates,
vocalness, mood, instrumentalness, and silence. UI, CLI, and API defaults request all eight automatically.
Use CLI `--sonara-minimal`, individual family flags, or an explicit API profile only when a smaller profile is intentional. Changing the
requested profile changes the deterministic analysis signature; the next SONARA job queues mismatched
tracks automatically, so profile changes do not normally require a reset.

Mood and instrumentalness are stored and displayed but do not enter current similarity, SET,
Hybrid, or classifier calculations. True peak and ReplayGain are stored for possible future
loudness-management work rather than direct SONARA similarity scoring. Complete beat/onset
positions, chord labels/events, tempo, energy, and loudness curves, downbeat arrays, and the SONARA
embedding and fingerprint are saved out-of-band in `sonara_curves`; the metadata dialog loads the
lazy payloads on demand and renders browser-side summaries without putting them on the hot search path.
The lazy API response still contains the complete stored values. Time signature, its confidence,
tempo variability, and embedding/fingerprint version fields remain lightweight metadata.

## Limit behavior

`Analyze limit = 0` in the UI means the whole library. Positive limits count tracks missing selected results.

The CLI differs: omit `--limit` for the whole library.

## Device

- `AUTO` selects CUDA when PyTorch sees a GPU, otherwise CPU.
- `CPU` forces CPU.
- `CUDA` requests CUDA and should fail clearly if CUDA is unavailable.

SONARA runs as a CPU runner. MAEST, MERT, MuQ, and CLAP use the selected device through their adapters. MuQ uses official `OpenMuQ/MuQ-large-msd-iter` weights and is fed only 24 kHz `float32` audio. It currently supports LAB Reference Compare, with no SET, Hybrid, Audio Dedup, or classifier-scoring integration.

## Batch controls

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

The square stop button requests cancellation. It does not kill Python mid-write. The job checks the cancellation flag between work units.

## Reset buttons

Reset is SQLite-only:

- SONARA reset removes SONARA features, provenance, signature, curves, flags, and dependent main-library classifier scores. Labels and feedback remain intact.
- MAEST reset removes MAEST metadata and MAEST embeddings.
- MERT, MuQ, and CLAP reset delete embeddings for that key.
- CLASSIFIERS reset deletes selected `track_classifier_scores` rows.

Use reset when you intentionally want to delete stored results before a fresh run. Do not reset for a
SONARA version/profile mismatch: normal analysis detects the signature mismatch and queues reanalysis.

For a complete existing-library procedure, including backups and classifier rebuilding, follow
[Migrate and reanalyze SONARA v0.2.4](../workflows/migrate-sonara-v0-2-4.md).
