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

Existing SONARA rows are skipped by normal analysis jobs. Reset SONARA first when you want already analyzed tracks to be recalculated with the current BPM range.

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
