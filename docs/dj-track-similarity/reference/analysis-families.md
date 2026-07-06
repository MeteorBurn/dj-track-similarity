# Analysis families reference

> Audience: Users choosing which model outputs to compute.
> Goal: List what each family reads, writes, and unlocks.
> Type: reference

| Family | Reads | Writes | Unlocks |
| --- | --- | --- | --- |
| SONARA | decoded audio | SONARA metadata, working BPM/key/energy/duration, `has_sonara_analysis` | SONARA search, SET, Hybrid, classifier input |
| MAEST | decoded audio | genre labels, syncopated rhythm data, MAEST embedding, `has_maest_embedding` | genre display, genre tag apply, SET, Hybrid, Audio Dedup signal |
| MERT | decoded audio | MERT embedding, `has_mert_embedding` | MERT seed search, SET, Hybrid, Audio Dedup signal, classifier input |
| MuQ | decoded audio, resampled to 24 kHz `float32` | MuQ embedding, `has_muq_embedding` | stored coverage for future workflows |
| CLAP | decoded audio | CLAP audio embedding, `has_clap_embedding` | CLAP text search, SET, Hybrid, Audio Dedup signal |
| CLASSIFIERS | existing SONARA, MERT, MAEST data | `track_classifier_scores` | CLASS filters, SET preferences, Hybrid diagnostics |

## Device behavior

- `auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU.
- `cpu` forces CPU.
- `cuda` requests CUDA and should fail clearly if unavailable.

SONARA uses its CPU runner. MAEST, MERT, MuQ, and CLAP use model adapters with the selected device. MuQ uses official `OpenMuQ/MuQ-large-msd-iter` weights and is always fed 24 kHz `float32` audio. CPU and CUDA are supported, with CUDA recommended for full-library MuQ runs.

## SONARA BPM range

SONARA analysis calls pass `bpm_min=79.0` and `bpm_max=192.0`. SONARA folds estimated tempos by octaves into that range before the project stores the working BPM field.

Tempo-aware search, transition diagnostics, and SET ordering read stored SONARA BPM first. If a track
has no SONARA BPM, they fall back to the Mutagen BPM tag stored during scan or Refresh Tags.

Existing SONARA rows are skipped by normal analysis jobs. Reset SONARA first when you want already analyzed tracks to be recalculated with the current BPM range.

## SONARA opt-in feature families

A plain SONARA run stores the base playlist output plus three fields new in SONARA 2.0 that arrive by default: `bpm_raw`, `bpm_candidates`, and `key_camelot` (sonara's own Camelot code, not a project-side derivation).

Six extra feature families are opt-in and OFF by default, so a normal run keeps the pre-2.0 output. Each has its own CLI flag and API field:

| Family | CLI flag | API `sonara_features` entry | Adds |
| --- | --- | --- | --- |
| structure | `--sonara-structure` | `structure` | energy curve, segments, intro/outro, energy level |
| loudness | `--sonara-loudness` | `loudness` | true peak, ReplayGain, loudness curve, momentary max, LRA |
| beatgrid | `--sonara-beatgrid` | `beatgrid` | downbeats, grid offset, grid stability |
| key_candidates | `--sonara-key-candidates` | `key_candidates` | top-3 key candidates with Camelot codes |
| vocalness | `--sonara-vocalness` | `vocalness` | vocal-presence heuristic (0-1) |
| silence | `--sonara-silence` | `silence` | leading/trailing silence offsets |

Light fields (scalars, `segments`, `key_candidates`) stay in the SONARA metadata used by search. Heavy curves (`energy_curve`, `loudness_curve`, `downbeats`) are stored whole in the separate `sonara_curves` table, loaded only for UI display and never read by the search path. SONARA reset and library clear remove both.

SONARA's `embedding` and `fingerprint` features are intentionally not implemented. They overlap the existing MERT/CLAP embeddings and Audio Dedup.

## Batch and label ranges

| Setting | Range | Default |
| --- | ---: | ---: |
| `top_k` | `1..10` | `3` |
| `track_batch_size` | `1..64` | `4` |
| `inference_batch_size` | `1..128` | `24` |

## Missing-result behavior

Analysis jobs target missing selected results. Existing selected results are skipped for that track unless you reset that family first.

## Classifier requirement

Classifier jobs need SONARA, MAEST, and MERT data. The analysis job can include missing required families in the same run, or you can analyze them first.
