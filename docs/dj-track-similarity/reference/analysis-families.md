# Analysis families reference

> Audience: Users choosing which model outputs to compute.
> Goal: List what each family reads, writes, and unlocks.
> Type: reference

| Family | Reads | Writes | Unlocks |
| --- | --- | --- | --- |
| SONARA | file paths decoded natively by SONARA/Symphonia | Core feature rows and a dedicated 48D embedding | Core-backed SONARA search, Evaluation transition diagnostics, Audio Dedup, classifier input |
| MAEST | shared FFmpeg-decoded audio | Core genre/syncopation rows and an Artifacts embedding | genre display, genre tag apply, seed search, LAB Reference Compare, Audio Dedup signal, classifier input |
| MERT | shared FFmpeg-decoded audio | Artifacts embedding | MERT seed search, LAB Reference Compare, Audio Dedup signal, classifier input |
| MuQ | shared FFmpeg decode, resampled to 24 kHz `float32` | Artifacts embedding | seed search, LAB Reference Compare, Audio Dedup signal, classifier input |
| MuQ-MuLan | shared MuQ-compatible mono decode, resampled to 24 kHz `float32` in 10-second windows | separate 512D L2-normalized audio embedding | MuQ-MuLan seed search, text-to-track retrieval, optional ANN, and one of the six separate LAB Reference Compare groups |
| CLAP | shared FFmpeg-decoded audio | Artifacts audio embedding | seed and text search, LAB Reference Compare, Audio Dedup signal, classifier input |
| CLASSIFIERS | exact stored inputs from each promoted manifest | Core `classifier_scores` rows | CLASS filters |

## Device behavior

- `auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU.
- `cpu` forces CPU.
- `cuda` requests CUDA and should fail clearly if unavailable.

SONARA uses its CPU runner. MAEST, MERT, MuQ, MuQ-MuLan, and CLAP use model adapters with the selected device. MuQ uses official `OpenMuQ/MuQ-large-msd-iter` weights. MuQ-MuLan uses official `OpenMuQ/MuQ-MuLan-large` weights through `MuQMuLan.from_pretrained(...)`. Both are fed mono 24 kHz `float32` audio in 10-second windows. CPU and CUDA are supported, with CUDA recommended for full-library runs.

## SONARA BPM range

SONARA analysis calls pass `bpm_min=70.0` and `bpm_max=180.0`. SONARA folds estimated tempos by octaves into that range before the project stores the working BPM field. SONARA is scheduled only as a standalone CPU job. The job passes paths to `sonara.analyze_batch()` with `sr=22050`. SONARA/Symphonia owns decoding and no FFmpeg or signal-analysis fallback is used.

Tempo-aware search and transition diagnostics resolve current SONARA evidence
first. Below `0.45` confidence, they retain ranked SONARA candidates and check the Mutagen BPM tag.
`grid_stability` can weaken reliability, and an unreliable estimate moves toward neutral instead of
adding similarity or becoming an automatic hard rejection.

Harmonic transition logic resolves a key in this order: a valid Camelot tag, SONARA
`key_camelot`, then conversion of an ordinary key name such as `A minor`. Compatibility is graded
as same, relative, adjacent, or clash. `key_confidence` is not a similarity dimension: a weak
analyzed key only pulls the harmonic result toward neutral. Legacy transition-risk v1 keeps its
original key behavior so recorded evaluations remain reproducible.

Normal analysis jobs skip a SONARA track only when both Core and embedding are present for the
current track identity.

## SONARA Core and embedding

SONARA analysis produces a fixed Core-plus-embedding output set. It stores BPM/key/confidence,
loudness, dynamics, spectral and timbral values, Contrast (7), MFCC (13), Chroma (12), compact
structure/beat-grid values, vocalness, mood, aggression, and silence in `sonara_features`. The
unnormalized 48-dimensional `float32` embedding is stored separately in `sonara_embeddings`.

Timeline and fingerprint collection remain disabled and have no placeholder tables.

`bpm_confidence` is SONARA's `0..1` trust signal for the working BPM. `key_camelot` is SONARA's own Camelot code rather than a project-side derivation.

Core deliberately does not request SONARA's Full-only `time_signature` metrogram. It was not used by search or classifier inputs, while real-library results had no usable confidence and the calculation more than doubled Core compute time. Beatgrid uses SONARA's normal 4/4 fallback instead of consuming an untrusted meter estimate.

See [SONARA integration](./sonara-integration.md) for the current decode, storage, and update
boundaries.

Every native batch requests the upstream features needed for Core plus the embedding. Extra values
returned by SONARA are ignored at the conversion boundary. Core explicitly selects the bundled
SONARA vocalness model.
`sonara_batch_size` is independent from ML batching and accepts `1..16`. Its default is `8`. The
browser selects SONARA at startup. There are no output checkboxes.

The adapter does not request upstream file-tag passthrough or a SONARA genre model. Mutagen remains
the project's file-tag source, so SONARA `tags.original_year` is not stored in this analysis family.

Light fields (scalars, compact candidates, and fixed vectors) stay in Core metadata. This includes
all four `mood_*` values, true peak, ReplayGain, momentary loudness maximum, and loudness range.
Contrast, MFCC, and Chroma retain every component because they are fixed vectors, not time-series
data. Long numeric sequences are reduced to a summary only when Core needs a compact descriptor
such as `energy_curve_summary`.

Transition-risk v2 uses `grid_stability` as a beat-grid reliability signal. When structure data is
available, it also compares the outgoing outro window with the incoming intro, segment-boundary
energy, energy level, and the light `energy_curve_summary` stored beside those fields. Missing opt-in data
does not become a zero-valued feature. Mood, true peak, and ReplayGain remain outside transition
scoring.

Storage does not imply scoring. `mood_*` values are retained for inspection and future workflows but
are not current SONARA similarity or Rhythm Lab classifier inputs. `aggression_score` is a
confidence-aware directional modifier in Custom SONARA search. Its component values remain data-only.
DJ transition blends a soft, directional structure fit from the seed outro to the candidate intro
when both rows have usable structure fields. True peak and
ReplayGain are not direct SONARA similarity dimensions. They are retained for possible
loudness-management features. The current `sonara` classifier source includes those loudness
scalars and vocalness; momentary loudness maximum and loudness range remain available to the
existing SONARA dynamics comparison, and vocalness remains an explicit search modifier.

MAEST, MERT, MuQ, MuQ-MuLan, and CLAP are the current generic seed-search embeddings. SONARA search uses stored
Core features rather than the stored SONARA embedding, which is not a current similarity, search,
or classifier input.

## ML prerequisite and MAEST windows

Project ML jobs select only tracks with a valid SONARA Core result. ML and promoted-classifier jobs cannot start
until the catalog contains at least one such track. A pipeline that includes
SONARA can establish this prerequisite before its ML and classifier stages run.

MAEST analyzes up to three 30-second windows centered at 20%, 50%, and 80% of
the best available content range. Current SONARA leading and trailing silence
form hard boundaries; intro end and outro start form preferred soft
boundaries. A range shorter than 30 seconds falls back first to the non-silent
range and then to the full track. If the current valid SONARA result has no
structure boundaries, MAEST centers the windows over the full duration. Window
scores are averaged before the top-K genres are selected.

## Dedicated storage tables

The library database stores embeddings in dedicated tables:

- `sonara_embeddings`
- `maest_embeddings`
- `mert_embeddings`
- `muq_embeddings`
- `mulan_embeddings`
- `clap_embeddings`

There is no generic runtime `embeddings` table. A fresh selected path creates one library database.
A legacy split database is rejected during normal startup and remains unchanged until the explicit
`dj-sim migrate-database` command is run after stopping its SQLite users.

## Batch and label ranges


| Setting | Range | Default |
| --- | ---: | ---: |
| `top_k` | `1..10` | `3` |
| `track_batch_size` | `1..64` | `8` |
| `inference_batch_size` | `1..128` | `16` |

## Missing-result behavior

Analysis jobs target missing selected results. SONARA checks Core and embedding independently. If
either current row is missing, the track becomes a candidate and one successful SONARA pass writes
both rows together. A track is skipped only when both rows are present. ML jobs also skip every
track without current SONARA Core. Other already-complete analysis families remain skipped until
reset.

## Classifier requirement

Classifier jobs use the inputs named by each promoted manifest: current SONARA Core when
required, plus only the MERT, MAEST, MuQ, MuQ-MuLan, and/or CLAP embeddings named by its features or
`required_inputs`. SONARA cannot share an audio job with GPU models, and classifier scoring is a
third database-only job. Classifier scoring remains unavailable until the
catalog has at least one current SONARA result, so run SONARA before starting a
classifier-only job.

SONARA-dependent classifier artifacts carry their exact ordered feature names. Promotion and runtime
scoring reject missing or mismatched recipes. A track must contain every requested SONARA value; an
absent opt-in value such as `vocalness` is skipped instead of becoming `0.0`. When that recipe
changes, retrain and promote only the affected profile. Labels and feedback remain intact.

## Separate MuQ-MuLan space

MuQ-MuLan is a separate family, not a MuQ output variant. Analysis writes one 512-dimensional,
L2-normalized audio vector per current track to `mulan_embeddings`. Existing `muq_embeddings` are
neither copied nor transformed. Seed and text queries use only the selected family table and its
matching runtime identity.

The new family is not added to the existing default Evaluation source profile or Audio Dedup source
weights. Those mixed-score defaults remain unchanged. Choose MuQ-MuLan explicitly for
its own seed or text search, or explicitly in a workflow that accepts a model-family choice.
