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

Tempo-aware search, transition diagnostics, and SET ordering resolve current signed SONARA evidence
first. Below `0.45` confidence, they retain ranked SONARA candidates and check the Mutagen BPM tag.
`grid_stability` can weaken reliability, and an unreliable estimate moves toward neutral instead of
adding similarity or becoming an automatic hard rejection.

Harmonic transition logic resolves a key in this order: a valid Camelot tag, SONARA
`key_camelot`, then conversion of an ordinary key name such as `A minor`. Compatibility is graded
as same, relative, adjacent, or clash. `key_confidence` is not a similarity dimension: a weak
analyzed key only pulls the harmonic result toward neutral. Legacy transition-risk v1 keeps its
original key behavior so recorded evaluations remain reproducible.

Only SONARA rows with the requested current analysis signature are skipped by normal analysis jobs. A legacy row, another feature profile, or a row from another SONARA/schema/project revision is treated as missing and is analyzed again.

## SONARA feature profiles

A plain SONARA v0.2.4 run stores the base playlist output plus four fields that arrive without an opt-in request: `bpm_raw`, `bpm_confidence`, `bpm_candidates`, and `key_camelot`. `bpm_confidence` is SONARA's `0..1` trust signal for the working BPM. `key_camelot` is SONARA's own Camelot code rather than a project-side derivation.

The track metadata also stores `sonara_provenance` separately from feature values. It preserves the provenance fields returned by SONARA, such as schema version, sample rate, hop length, mode, and requested features, and adds the installed SONARA package version when the package exposes it. The metadata dialog displays this information for result audits and reanalysis decisions. Reset SONARA removes the provenance with the feature data.

The separate `sonara_analysis_signature` is the compatibility contract rather than an informational label. Its deterministic digest covers SONARA `0.2.4`, upstream schema `3`, playlist mode, sample rate `22050`, BPM range `79..192`, the sorted requested-feature profile, and project feature revision `1`. The presence flag remains a fast storage flag. Analysis scheduling uses the signature to distinguish current results from legacy rows.

The project model label `sonara-playlist-lab` is informational and is not a freshness check. The
signature contains expanded, sorted upstream feature names rather than only the eight project family
names. Hop length remains in provenance, not in the signature. See the
[SONARA v0.2.4 project contract](./sonara-v0-2-4-contract.md) for the complete JSON example and
confidence formulas.

The browser UI, direct API defaults, and `dj-sim analyze` all use the complete profile with all eight extra feature families. This prevents an ordinary scripted reanalysis from silently replacing richer archived data with a smaller profile. Plain playlist mode requires either an explicit empty API `sonara_features` list or CLI `--sonara-minimal`. Individual CLI flags and non-empty API lists select intentional subsets:

| Family | CLI flag | API `sonara_features` entry | Adds |
| --- | --- | --- | --- |
| structure | `--sonara-structure` | `structure` | energy curve, segments, intro/outro, energy level |
| loudness | `--sonara-loudness` | `loudness` | true peak, ReplayGain, loudness curve, momentary max, LRA |
| beatgrid | `--sonara-beatgrid` | `beatgrid` | downbeats, grid offset, grid stability |
| key_candidates | `--sonara-key-candidates` | `key_candidates` | top-3 key candidates with Camelot codes |
| vocalness | `--sonara-vocalness` | `vocalness` | vocal-presence heuristic (0-1) |
| mood | `--sonara-mood` | `mood` | happy, aggressive, relaxed, and sad heuristic affinities (0-1) |
| instrumentalness | `--sonara-instrumentalness` | `instrumentalness` | instrumentalness heuristic (0-1) |
| silence | `--sonara-silence` | `silence` | leading/trailing silence offsets |

When an extended profile is present, the adapter requests the playlist-equivalent feature set together with the selected families. That explicit playlist set also captures `tempo_curve`, time-signature analysis, the SONARA embedding, and the SONARA fingerprint. Small archival fields such as `tempo_variability`, `time_signature`, `time_signature_confidence`, `embedding_version`, and `fingerprint_version` stay in track metadata.

The adapter does not request upstream file-tag passthrough or a SONARA genre model. Mutagen remains
the project's file-tag source, so SONARA `tags.original_year` is not stored in this analysis family.

Light fields (scalars, fixed vectors, `segments`, and `key_candidates`) stay in the track's SONARA
metadata. This includes all four `mood_*` values, `instrumentalness`, true peak, ReplayGain,
momentary loudness maximum, and loudness range. The supported upstream runner returns fixed vectors
as short lists, so their components remain available to search and classifiers. A custom injected
runner that supplies a NumPy array uses the generic summary-only serializer instead.

Complete `beats`, `onset_frames`, `chord_sequence`, `chord_events`, `tempo_curve`, `energy_curve`,
`loudness_curve`, and `downbeats` sequences, plus `embedding` and `fingerprint`, are stored
out-of-band in the separate `sonara_curves` table. Beat and onset descriptors also remain in hot
metadata: short lists can retain their values there, while longer lists retain only a summary. The
metadata dialog fetches the complete lazy payload and summarizes it in the browser. Search and
classifiers never load the out-of-band copy. SONARA reset and library clear remove both stores.

Transition-risk v2 uses `grid_stability` as a beat-grid reliability signal. When structure data is
available, it also compares the outgoing outro window with the incoming intro, segment-boundary
energy, energy level, and the light `energy_curve_summary` stored beside those fields. Missing opt-in data
does not become a zero-valued feature. Mood, instrumentalness, true peak, and ReplayGain remain
outside transition scoring.

Storage does not imply scoring. `mood_*` and `instrumentalness` are retained for inspection and future workflows but are not current SONARA similarity, SET, Hybrid, or Rhythm Lab classifier inputs. True peak and ReplayGain are not direct SONARA similarity dimensions. They are retained for possible loudness-management features. Loudness scalars remain available to the `sonara2` classifier variant, momentary loudness maximum and loudness range remain available to the existing SONARA dynamics comparison, and `vocalness` remains an explicit search modifier and an optional `sonara2vocal` variant.

The archived SONARA `embedding`, `fingerprint`, tempo curve, and time-signature fields are data-only today. MERT and CLAP remain the search embeddings, while Audio Dedup and the current similarity and classifier matrices ignore the archived values.

## Batch and label ranges

| Setting | Range | Default |
| --- | ---: | ---: |
| `top_k` | `1..10` | `3` |
| `track_batch_size` | `1..64` | `4` |
| `inference_batch_size` | `1..128` | `24` |

## Missing-result behavior

Analysis jobs target missing selected results. For SONARA, only an exact current signature for the requested feature profile counts as complete. A legacy result or a mismatch in version, schema, mode, sample rate, BPM range, requested features, or project feature revision is queued for reanalysis automatically. A reset is not normally required. Other already-complete analysis families remain skipped until reset.

Saving a new SONARA result replaces the old `sonara_features` object and replaces or removes the
track's `sonara_curves` row. A minimal or subset run does not merge with a previous full result.

## Classifier requirement

Classifier jobs need SONARA, MAEST, and MERT data. The analysis job can include missing required families in the same run, or you can analyze them first.

SONARA-dependent classifier artifacts also carry the exact training-analysis signature in manifest version `2`. Promotion and runtime scoring reject missing, stale, or mismatched signatures. A track must match the artifact signature and contain every requested SONARA classifier value; an absent opt-in such as `vocalness` is skipped instead of becoming `0.0`.

When the project SONARA feature revision changes, the main database invalidates SONARA-dependent
classifier scores and the Rhythm Lab database invalidates SONARA-dependent predictions. The rule
covers `combined` and every plus-separated source whose name starts with `sonara`, including
`sonara`, `sonara2`, and `sonara2vocal` combinations. Labels and feedback remain intact. Existing
stale artifacts are not trusted: scoring stays blocked until the affected profile is retrained and
promoted with a current signed manifest.
