# Analysis families reference

MAEST, MERT, MuQ, MuQ-MuLan, and CLAP share one decoded input per track. TorchCodec `0.16` reads
all samples through the configured shared FFmpeg runtime as mono `float32` at the source sample
rate with `AudioDecoder(path, num_channels=1).get_all_samples()`. The project keeps
`AudioSamples.data[0]` as a 1D CPU `torch.float32` tensor in `DecodedAudio` and passes it directly
to the adapters, without a shared Tensor-to-NumPy-to-Tensor round-trip. If the full-track decode
fails, the selected ML family retries with PyAV over the same shared libraries and uses an
arithmetic channel mean for mono `float32`. It can still fail on invalid audio. Each adapter
applies its own resampling and window preparation after either decode path.
On the input path, NumPy conversion occurs only at the MERT feature-extractor and CLAP model-API
boundaries that require arrays.

## ML decode recovery

The initial ML decode remains one full-track TorchCodec read shared by the selected ML families.
The decode chain for a track is TorchCodec, then PyAV over the shared FFmpeg libraries, then a
recorded decode failure. A failed TorchCodec read is recovered independently for MAEST, MERT, MuQ,
MuQ-MuLan, or CLAP by a second decoder rather than a second attempt at the same one: pinned PyAV
`17.1.0` opens the file in process with `fflags=+discardcorrupt+genpts` and `err_detect=ignore_err`
against the configured shared FFmpeg `8.1.1` libraries. It does not launch `ffmpeg.exe`,
`ffprobe.exe`, or a shell command.

Because the recovery decoder is tolerant, a packet that fails its checksum is discarded and the
valid frames before and after it are kept, so a file the primary decoder refuses outright can
still be analyzed from its intact audio. The discarded packets are counted in the decode
detail string, each one is recorded at `DEBUG`, and one `WARNING` per file reports the total. A
track is failed only when both decoders fail.

This recovery route neither repairs the source file nor changes the model preprocessing: MAEST,
MERT, MuQ, MuQ-MuLan, and CLAP retain their existing resampling and window policies. SONARA has a
separate native/Symphonia decoder and uses the same tolerant PyAV decode after its own decode
failure.

| Family | Reads | Writes | Unlocks |
| --- | --- | --- | --- |
| SONARA | source paths in Direct Mode or temporary paths in Staged Mode; normally decoded by SONARA/Symphonia, with per-file direct shared-library recovery only after a native decode or codec failure | Core feature rows and a dedicated 48D embedding | Core-backed SONARA search, Evaluation transition diagnostics, Audio Dedup, classifier input |
| MAEST | shared ML decode | `maest_genres` rows and a `maest_embeddings` row | genre display, genre tag apply, seed search, LAB Reference Compare, Audio Dedup signal, classifier input |
| MERT | shared ML decode | a row in `mert_embeddings` | MERT seed search, LAB Reference Compare, Audio Dedup signal, classifier input |
| MuQ | shared ML decode, resampled to 24 kHz `float32` | a row in `muq_embeddings` | seed search, LAB Reference Compare, Audio Dedup signal, classifier input |
| MuQ-MuLan | shared ML decode, resampled to 24 kHz `float32` in 10-second windows | separate 512D L2-normalized audio embedding | MuQ-MuLan seed search, text-to-track retrieval, optional ANN, one of the six separate LAB Reference Compare groups, and classifier input |
| CLAP | shared ML decode | a row in `clap_embeddings` | seed and text search, LAB Reference Compare, Audio Dedup signal, classifier input |
| CLASSIFIERS | exact stored inputs from each promoted manifest | rows in `classifier_scores` | CLASS filters |

## Model warm-up

An analysis job loads every selected model before it decodes a track. The job reports that work as
its `warmup` phase, and switches to `analyzing` afterwards. Registering analysis outputs and
selecting candidates both happen after the phase switch, so no track is read while a model is still
loading. A model that fails to load fails the whole job during warm-up.

Warm-up visits the selected models in their configured order and writes these entries to the job
log:

| Entry | Meaning |
| --- | --- |
| `Model warm-up started: <models>` | The phase began for the listed ordered selection |
| `Warming up <model> (<n>/<total>)` | That model is being loaded now |
| `<model> ready on <device> in <seconds>s` | The model finished loading on the resolved device |
| `<model> already resident on <device>` | A runner loaded by an earlier job in the same server process was reused, so this model loaded nothing |
| `Model warm-up completed in <seconds>s` | Every selected model is loaded |
| `Analysis candidates ready: <n>` | Candidate selection ran, after warm-up finished |

ML runners are cached per model, requested device, inference batch size, and `top_k` for the life of
the server process. A later job with the same combination reuses the loaded runner, so its warm-up
reports `already resident` for that model rather than loading again. Restarting the backend clears
the cache, and the next job loads the models once more.

Model weights are fetched on first use rather than during installation, and there is no separate
prefetch command. On a machine that has not analyzed with a family yet, that family's first warm-up
also covers the download and checksum verification into the local cache.

SONARA has no model to preflight. It still appears in the warm-up sequence and reports its CPU
runner, without loading a model.

## Device behavior

- `auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU.
- `cpu` forces CPU.
- `cuda` requests CUDA and should fail clearly if unavailable.

SONARA uses its CPU runner. MAEST, MERT, MuQ, MuQ-MuLan, and CLAP use model adapters with the selected device. MuQ uses official `OpenMuQ/MuQ-large-msd-iter` weights. MuQ-MuLan uses official `OpenMuQ/MuQ-MuLan-large` weights through `MuQMuLan.from_pretrained(...)`. Both are fed mono 24 kHz `float32` audio in 10-second windows. CPU and CUDA are supported, with CUDA recommended for full-library runs.

The shared decoder-to-adapter handoff remains a CPU `torch.float32` tensor. `AudioDecoder` has no
device option in TorchCodec `0.16`, so the CUDA package variant does not make this decode step a GPU
operation.

## SONARA BPM range

SONARA analysis calls pass the BPM range of the library. That range is a property of the analysed data rather than a separate setting, because each stored Core row keeps the pair from its own run.

- The track-import dialog is where it gets picked, from a preset or as your own pair.
- The first SONARA analysis fixes it for the whole library.
- Any other range stays refused until SONARA analysis is reset.
- The upper bound must be at least twice the lower one, so every tempo folds into the range exactly once.

Presets are Rekordbox `70-180`, VirtualDJ `80-240`, and Mixed In Key `79-192`. None of them is a universal tempo standard. SONARA folds estimated tempos by octaves into that range before the project stores the working BPM field. SONARA is scheduled only as a standalone CPU job. The job passes source paths in Direct Mode or temporary copy paths in Staged Mode to `sonara.analyze_batch()` with `sr=22050`. SONARA/Symphonia owns normal decoding. A per-file native decode or codec failure falls back to a direct TorchCodec shared-library decode, mono `float32` PCM, and `analyze_signal()` without failing the other batch results.

Tempo-aware search and transition diagnostics resolve current SONARA evidence
first. Below `0.45` confidence, they retain ranked SONARA candidates and check the Mutagen BPM tag.
`grid_stability` can weaken reliability, and an unreliable estimate moves toward neutral instead of
adding similarity or becoming an automatic hard rejection.

Harmonic transition logic resolves a key in this order: a valid Camelot tag, SONARA
`key_camelot`, then conversion of an ordinary key name such as `A minor`. Compatibility is graded
as same, relative, adjacent, or clash. `key_confidence` is not a similarity dimension: a weak
analyzed key only pulls the harmonic result toward neutral. Legacy transition-risk v1 keeps its
original key behavior so recorded evaluations remain reproducible.

Normal analysis jobs skip a SONARA track only when Core, embedding, and fingerprint are present for
the current track identity.

## SONARA Core, embedding, and fingerprint

SONARA analysis produces a fixed Core, embedding, and fingerprint output set. It stores BPM/key/confidence,
loudness, dynamics, spectral and timbral values, Contrast (7), MFCC (13), Chroma (12), compact
structure/beat-grid values, vocalness, mood, aggression, and silence in `sonara_features`. The
unnormalized 48-dimensional `float32` embedding is stored separately in `sonara_embeddings`; the
versioned acoustic fingerprint is stored in `sonara_fingerprints` as SONARA's native base64 value.

Timeline collection remains disabled. The fingerprint is stored but is not a current UI, search,
classifier, or Audio Dedup input.

`bpm_confidence` is SONARA's `0..1` trust signal for the working BPM. `key_camelot` is SONARA's own Camelot code rather than a project-side derivation.

Core deliberately does not request SONARA's Full-only `time_signature` metrogram. It was not used by search or classifier inputs, while real-library results had no usable confidence and the calculation more than doubled Core compute time. Beatgrid uses SONARA's normal 4/4 fallback instead of consuming an untrusted meter estimate.

See [SONARA integration](./sonara-integration.md) for the current decode, storage, and update
boundaries.

Every native batch requests the upstream features needed for Core, the embedding, and the
fingerprint. Extra values returned by SONARA are ignored at the conversion boundary. Core explicitly selects the bundled
SONARA vocalness model.
`sonara_batch_size` is independent from ML batching and accepts `1..16`. Its default is `8` for the
standalone job and browser Direct Mode. Browser Staged Mode keeps a separate BatchSize with default
`4`; it also configures Processes, Threads, and the bounded StageSize window. The browser selects
SONARA at startup without output checkboxes, while Staged Mode does not apply to the GPU model
families.

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
Core features rather than the stored SONARA embedding or fingerprint, which are not current
similarity, search, classifier, or Audio Dedup inputs.

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

The library database stores embeddings and the SONARA fingerprint in dedicated tables:

- `sonara_embeddings`
- `sonara_fingerprints`
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

Analysis jobs target missing selected results. SONARA checks Core, embedding, and fingerprint
independently. If any current row is missing, the track becomes a candidate and one successful
SONARA pass writes all three rows together, and the track is skipped only when all three rows are
present. ML jobs also skip every track without current SONARA Core. Other already-complete analysis
families remain skipped until reset.

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

The family is not added to the existing default Evaluation source profile or Audio Dedup
source weights. Those mixed-score defaults remain unchanged. It is part of the default Rhythm
Lab training recipe, `sonara+mert+maest+clap+muq+mulan`. Elsewhere, choose MuQ-MuLan
explicitly: as its own seed or text search, or in another workflow that accepts a model-family
choice.
