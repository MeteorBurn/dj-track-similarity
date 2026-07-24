# Analysis families reference

> Audience: Users choosing which model outputs to compute.
> Goal: List what each family reads, writes, and unlocks.
> Type: reference

| Family | Reads | Writes | Unlocks |
| --- | --- | --- | --- |
| SONARA | file paths decoded natively by SONARA/Symphonia | signed `core`, `timeline`, `embedding`, and `fingerprint` outputs | SONARA search, SET, Hybrid, classifier input |
| MAEST | shared FFmpeg-decoded audio | Core genre/syncopation rows and an Artifacts embedding | genre display, genre tag apply, SET, Hybrid, Audio Dedup signal |
| MERT | shared FFmpeg-decoded audio | Artifacts embedding | MERT seed search, SET, Hybrid, Audio Dedup signal, classifier input |
| MuQ | shared FFmpeg decode, resampled to 24 kHz `float32` | Artifacts embedding | LAB Reference Compare evidence |
| CLAP | shared FFmpeg-decoded audio | Artifacts audio embedding | CLAP text search, SET, Hybrid, Audio Dedup signal |
| CLASSIFIERS | exact stored inputs from each promoted manifest | Core `classifier_scores` rows | CLASS filters, SET preferences, Hybrid diagnostics |

## Device behavior

- `auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU.
- `cpu` forces CPU.
- `cuda` requests CUDA and should fail clearly if unavailable.

SONARA uses its CPU runner. MAEST, MERT, MuQ, and CLAP use model adapters with the selected device. MuQ uses official `OpenMuQ/MuQ-large-msd-iter` weights and is always fed 24 kHz `float32` audio. CPU and CUDA are supported, with CUDA recommended for full-library MuQ runs.

## SONARA BPM range

SONARA analysis calls pass `bpm_min=70.0` and `bpm_max=180.0`. SONARA folds estimated tempos by octaves into that range before the project stores the working BPM field. SONARA is scheduled only as a standalone CPU job. The job passes paths to `sonara.analyze_batch()` with `sr=22050`. SONARA/Symphonia owns decoding and no FFmpeg or signal-analysis fallback is used.

Tempo-aware search, transition diagnostics, and SET ordering resolve current signed SONARA evidence
first. Below `0.45` confidence, they retain ranked SONARA candidates and check the Mutagen BPM tag.
`grid_stability` can weaken reliability, and an unreliable estimate moves toward neutral instead of
adding similarity or becoming an automatic hard rejection.

Harmonic transition logic resolves a key in this order: a valid Camelot tag, SONARA
`key_camelot`, then conversion of an ordinary key name such as `A minor`. Compatibility is graded
as same, relative, adjacent, or clash. `key_confidence` is not a similarity dimension: a weak
analyzed key only pulls the harmonic result toward neutral. Legacy transition-risk v1 keeps its
original key behavior so recorded evaluations remain reproducible.

Only SONARA rows with the requested current analysis signature are skipped by normal analysis jobs.
Before any native job, the presence of an older decoder/execution contract blocks analysis and
requires an explicit backup and SONARA reset. Once the database contains only the native contract,
missing current outputs can resume normally.

## SONARA output kinds

SONARA v0.3.1 has one immutable release identity derived from four output contracts: `core`,
`timeline`, `embedding`, and `fingerprint`. A job can select which active contracts to materialize;
`core` is the CLI and API default. Selecting another output later does not change the four-contract
release identity or replace current `core` rows.

| Output | Main contents | Physical store |
| --- | --- | --- |
| `core` | BPM/key/confidence, loudness, dynamics, spectral and timbral values, Contrast (7), MFCC (13), Chroma (12), compact structure/beat-grid values, vocalness v2, mood, silence | Core `sonara` table |
| `timeline` | beats, onsets, chord sequence/events, tempo/energy/loudness curves, downbeats, structure segments | Artifacts `sonara_timeline` |
| `embedding` | 48-dimensional SONARA similarity vector | Artifacts `sonara_similarity_embeddings` |
| `fingerprint` | versioned SONARA audio fingerprint | Artifacts `sonara_fingerprints` |

`bpm_confidence` is SONARA's `0..1` trust signal for the working BPM. `key_camelot` is SONARA's own Camelot code rather than a project-side derivation.

The contract registry stores canonical contract JSON plus contract and release hashes. Analyzer
provenance is validated during ingestion, but the runtime does not promise to round-trip the raw
analyzer provenance payload.

Each output has a separate compatibility signature. Its deterministic digest covers SONARA `0.3.1`, upstream schema `5`, playlist mode, sample rate `22050`, BPM range `70..180`, the output's sorted feature profile, project feature revision `6`, `decoder_backend="sonara-symphonia"`, and `execution_path="analyze_batch"`.

Core deliberately does not request SONARA's Full-only `time_signature` metrogram. It was not used by search, SET, Hybrid, or classifier inputs, while real-library results had no usable confidence and the calculation more than doubled Core compute time. Beatgrid uses SONARA's normal 4/4 fallback instead of consuming an untrusted meter estimate.

The project model label `sonara-playlist` is informational and is not a freshness check. The
signature contains expanded, sorted upstream feature names rather than only the four project output
names. The analysis hop is part of the common parameters in every output contract and the
family-wide release hash. See the
[SONARA v0.3.1 project contract](./sonara-v0-3-1-contract.md) for the exact storage and signature rules.

The backend API uses `sonara_outputs`, and the CLI uses
`--sonara-outputs core,timeline,embedding,fingerprint`. Every native batch requests the same
canonical union of upstream features required by all four output contracts. The selection controls
persistence only: the converter writes each selected output to its contract-owned table. `core`
explicitly selects the bundled SONARA vocalness v2 model.
`sonara_batch_size` is independent from ML batching and accepts `1..16`. Its default is `8`. The React
frontend has not yet been ported to this v7 contract, so no current browser-control claim is made.

The adapter does not request upstream file-tag passthrough or a SONARA genre model. Mutagen remains
the project's file-tag source, so SONARA `tags.original_year` is not stored in this analysis family.

Light fields (scalars, compact candidates, and fixed vectors) stay in Core metadata. This includes
all four `mood_*` values, true peak, ReplayGain, momentary loudness maximum, and loudness range.
Contrast, MFCC, and Chroma retain every component because they are fixed vectors, not time-series
data. Long numeric sequences are reduced to a summary only when Core needs a compact descriptor
such as `energy_curve_summary`.

Complete `beats`, `onset_frames`, `chord_sequence`, `chord_events`, `tempo_curve`, `energy_curve`,
`segments`, `loudness_curve`, and `downbeats` sequences belong to the `timeline` output. `embedding`
and `fingerprint` are separate outputs. Search and classifiers do not load timeline payloads.

Transition-risk v2 uses `grid_stability` as a beat-grid reliability signal. When structure data is
available, it also compares the outgoing outro window with the incoming intro, segment-boundary
energy, energy level, and the light `energy_curve_summary` stored beside those fields. Missing opt-in data
does not become a zero-valued feature. Mood, true peak, and ReplayGain remain outside transition
scoring.

Storage does not imply scoring. `mood_*` values are retained for inspection and future workflows but
are not current SONARA similarity, SET, Hybrid, or Rhythm Lab classifier inputs. True peak and
ReplayGain are not direct SONARA similarity dimensions. They are retained for possible
loudness-management features. Loudness scalars remain available to the `sonara2` classifier
variant, momentary loudness maximum and loudness range remain available to the existing SONARA
dynamics comparison, and `vocalness` remains an explicit search modifier and an optional
`sonara2vocal` variant.

The SONARA `embedding`, `fingerprint`, and tempo curve are data-only today. MERT and CLAP remain the search embeddings, while Audio Dedup and the current similarity and classifier matrices ignore the SONARA representations.

## Dedicated storage tables

The required Artifacts database stores embeddings in dedicated tables:

- `maest_embeddings`
- `mert_embeddings`
- `muq_embeddings`
- `clap_embeddings`
- `sonara_similarity_embeddings`

There is no generic runtime `embeddings` table and no v6-to-v7 migration command. A fresh selected
path creates the v7 Core plus mandatory Artifacts bundle. A non-v7 database is rejected.

## Batch and label ranges


| Setting | Range | Default |
| --- | ---: | ---: |
| `top_k` | `1..10` | `3` |
| `track_batch_size` | `1..64` | `8` |
| `inference_batch_size` | `1..128` | `16` |

## Missing-result behavior

Analysis jobs target missing selected results. For SONARA, each selected output must have its exact
current contract from the active four-contract release. A missing `timeline` row does not make
`core` stale, and a missing fingerprint does not force `core` to be rewritten. Selecting fewer
outputs changes only which rows the job materializes, not the immutable release identity. Other
already-complete analysis families remain skipped until reset.

Saving `core` replaces only the Core feature row. Saving `timeline`, `embedding`, or `fingerprint`
upserts that Artifacts output. Unselected current outputs remain intact.

## Classifier requirement

Classifier jobs use the exact inputs named by each promoted manifest: current SONARA Core when
required, plus only the MERT, MAEST, and/or CLAP embeddings named by its features or
`required_inputs`. SONARA cannot share an audio job with GPU models, and classifier scoring is a
third database-only job, so run missing stages before scoring.

SONARA-dependent classifier artifacts also carry the exact training-analysis signature in manifest version `2`. Promotion and runtime scoring reject missing, stale, or mismatched signatures. A track must match the artifact signature and contain every requested SONARA classifier value; an absent opt-in such as `vocalness` is skipped instead of becoming `0.0`.

When the project SONARA feature revision changes, the main database invalidates SONARA-dependent
classifier scores and the Rhythm Lab database invalidates SONARA-dependent predictions. The rule
covers `combined` and every plus-separated source whose name starts with `sonara`, including
`sonara`, `sonara2`, and `sonara2vocal` combinations. Labels and feedback remain intact. Existing
stale artifacts are not trusted: scoring stays blocked until the affected profile is retrained and
promoted with a current signed manifest.

The repository's current promoted `model.json` files still declare manifest version `1`. Runtime
version `2` blocks them until their profiles are retrained and promoted.
