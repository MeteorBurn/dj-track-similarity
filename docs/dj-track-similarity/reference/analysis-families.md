# Analysis families reference

> Audience: Users choosing which model outputs to compute.
> Goal: List what each family reads, writes, and unlocks.
> Type: reference

| Family | Reads | Writes | Unlocks |
| --- | --- | --- | --- |
| SONARA | decoded audio | SONARA metadata, working BPM/key/energy/duration, `has_sonara_analysis` | SONARA search, SET, Hybrid, classifier input |
| MAEST | decoded audio | genre labels, syncopated rhythm data, MAEST embedding, `has_maest_embedding` | genre display, genre tag apply, SET, Hybrid, Audio Dedup signal |
| MERT | decoded audio | MERT embedding, `has_mert_embedding` | MERT seed search, SET, Hybrid, Audio Dedup signal, classifier input |
| MuQ | decoded audio, resampled to 24 kHz `float32` | MuQ embedding, `has_muq_embedding` | LAB Reference Compare evidence |
| CLAP | decoded audio | CLAP audio embedding, `has_clap_embedding` | CLAP text search, SET, Hybrid, Audio Dedup signal |
| CLASSIFIERS | existing SONARA, MERT, MAEST data | `track_classifier_scores` | CLASS filters, SET preferences, Hybrid diagnostics |

## Device behavior

- `auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU.
- `cpu` forces CPU.
- `cuda` requests CUDA and should fail clearly if unavailable.

SONARA uses its CPU runner. MAEST, MERT, MuQ, and CLAP use model adapters with the selected device. MuQ uses official `OpenMuQ/MuQ-large-msd-iter` weights and is always fed 24 kHz `float32` audio. CPU and CUDA are supported, with CUDA recommended for full-library MuQ runs.

## SONARA BPM range

SONARA analysis calls pass `bpm_min=70.0` and `bpm_max=180.0`. SONARA folds estimated tempos by octaves into that range before the project stores the working BPM field. SONARA is scheduled only as a standalone CPU job. FFmpeg decodes each file to mono float32 at `22050 Hz` before the buffer enters the native Rust analyzer.

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

## SONARA output blocks

SONARA v0.2.9 is exposed as three independently selectable outputs. Core is the default. Timeline
and Representations can be added during the first analysis or computed later without replacing Core.

| Output | Main contents | Physical store |
| --- | --- | --- |
| Core | BPM/key/confidence, loudness, dynamics, spectral and timbral values, Contrast (7), MFCC (13), Chroma (12), compact structure/beat-grid values, vocalness v2, mood, silence | selected main `.sqlite` |
| Timeline | beats, onsets, chord sequence/events, tempo/energy/loudness curves, downbeats, structure segments | adjacent `*.timeline.sqlite` |
| Representations | SONARA embedding and fingerprint | adjacent `*.representations.sqlite` |

`bpm_confidence` is SONARA's `0..1` trust signal for the working BPM. `key_camelot` is SONARA's own Camelot code rather than a project-side derivation.

The track metadata also stores `sonara_provenance` separately from feature values. It preserves the provenance fields returned by SONARA, such as schema version, sample rate, hop length, mode, and requested features, and adds the installed SONARA package version when the package exposes it. The metadata dialog displays this information for result audits and reanalysis decisions. Reset SONARA removes the provenance with the feature data.

Each output has a separate compatibility signature. Its deterministic digest covers SONARA `0.2.9`, upstream schema `4`, playlist mode, sample rate `22050`, BPM range `70..180`, the output's sorted feature profile, and project feature revision `3`. Core keeps its full signature in track metadata. Side rows keep their own signature and digest.

The project model label `sonara-playlist-lab` is informational and is not a freshness check. The
signature contains expanded, sorted upstream feature names rather than only the three project output
names. Hop length remains in provenance, not in the signature. See the
[SONARA v0.2.9 project contract](./sonara-v0-2-9-contract.md) for the exact storage and signature rules.

The browser presents three checkboxes. The API uses `sonara_outputs`, and the CLI uses
`--sonara-outputs core,timeline,representations`. A combined request sends the union of required
upstream features to one Rust call after one FFmpeg decode, then splits the result by store. Core
explicitly selects the bundled SONARA vocalness v2 model.

The adapter does not request upstream file-tag passthrough or a SONARA genre model. Mutagen remains
the project's file-tag source, so SONARA `tags.original_year` is not stored in this analysis family.

Light fields (scalars, compact candidates, and fixed vectors) stay in Core metadata. This includes
all four `mood_*` values, `instrumentalness`, true peak, ReplayGain, momentary loudness maximum, and
loudness range. Contrast, MFCC, and Chroma retain every component because they are fixed vectors,
not time-series data. Long numeric sequences are reduced to a summary only when Core needs a compact
descriptor such as `energy_curve_summary`.

Complete `beats`, `onset_frames`, `chord_sequence`, `chord_events`, `tempo_curve`, `energy_curve`,
`segments`, `loudness_curve`, and `downbeats` sequences are Timeline. Embedding and fingerprint are
Representations. The metadata dialog receives only the sorted field names from both side databases;
it does not load the values. Search and classifiers never load Timeline payloads. SONARA reset and
library clear remove all three SONARA stores.

Transition-risk v2 uses `grid_stability` as a beat-grid reliability signal. When structure data is
available, it also compares the outgoing outro window with the incoming intro, segment-boundary
energy, energy level, and the light `energy_curve_summary` stored beside those fields. Missing opt-in data
does not become a zero-valued feature. Mood, instrumentalness, true peak, and ReplayGain remain
outside transition scoring.

Storage does not imply scoring. `mood_*` and `instrumentalness` are retained for inspection and future workflows but are not current SONARA similarity, SET, Hybrid, or Rhythm Lab classifier inputs. True peak and ReplayGain are not direct SONARA similarity dimensions. They are retained for possible loudness-management features. Loudness scalars remain available to the `sonara2` classifier variant, momentary loudness maximum and loudness range remain available to the existing SONARA dynamics comparison, and `vocalness` remains an explicit search modifier and an optional `sonara2vocal` variant.

The SONARA `embedding`, `fingerprint`, and tempo curve are data-only today. MERT and CLAP remain the search embeddings, while Audio Dedup and the current similarity and classifier matrices ignore the SONARA representations.

## Batch and label ranges

| Setting | Range | Default |
| --- | ---: | ---: |
| `top_k` | `1..10` | `3` |
| `track_batch_size` | `1..64` | `4` |
| `inference_batch_size` | `1..128` | `24` |

## Missing-result behavior

Analysis jobs target missing selected results. For SONARA, each selected output must have its exact current signature. A missing Timeline row does not make Core stale, and a missing fingerprint does not force Core to be rewritten. Other already-complete analysis families remain skipped until reset.

Saving Core replaces only the Core feature object. Saving Timeline or Representations independently
upserts that side output. Unselected current outputs remain intact.

## Classifier requirement

Classifier jobs need current SONARA Core, MAEST, and MERT data. SONARA cannot share an analysis job
with GPU models or classifiers, so run missing Core separately before scoring classifiers.

SONARA-dependent classifier artifacts also carry the exact training-analysis signature in manifest version `2`. Promotion and runtime scoring reject missing, stale, or mismatched signatures. A track must match the artifact signature and contain every requested SONARA classifier value; an absent opt-in such as `vocalness` is skipped instead of becoming `0.0`.

When the project SONARA feature revision changes, the main database invalidates SONARA-dependent
classifier scores and the Rhythm Lab database invalidates SONARA-dependent predictions. The rule
covers `combined` and every plus-separated source whose name starts with `sonara`, including
`sonara`, `sonara2`, and `sonara2vocal` combinations. Labels and feedback remain intact. Existing
stale artifacts are not trusted: scoring stays blocked until the affected profile is retrained and
promoted with a current signed manifest.
