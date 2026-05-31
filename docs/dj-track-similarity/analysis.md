# Analysis Families

This page documents the analysis outputs used by the main app. Use it to decide
which analysis job to run before spending CPU or GPU time. For the separate
classifier labeling and training tool, see [Rhythm Lab](rhythm-lab.md).

## Analysis Families

Each family writes different SQLite data and supports a different workflow:

| Family | What it does | Use when |
| --- | --- | --- |
| Sonara | Extracts explainable playlist features such as tempo, energy, loudness, rhythm, and tonal summaries. | You want fast seed search, visible feature controls, or library filters. |
| MAEST | Predicts genre labels and stores MAEST embeddings. | You want generated genre tags, genre review, the `syncopated` preset, or classifier inputs. |
| MERT | Builds audio embeddings for seed-track similarity. | You want "find tracks close to this track" behavior from an audio model. |
| CLAP | Builds music audio embeddings and text vectors. | You want text-to-audio search from descriptive prompts. |
| Promoted classifiers | Scores tracks with a local model trained in Rhythm Lab. | You want a reusable custom signal such as vocal presence, live instrumentation, or another profile-specific label. |

The main audio-analysis workflow is one selected-model job. In the UI, select
SONARA, MAEST, MERT, and/or CLAP with checkboxes and start one analysis run. In
the CLI, use `dj-sim analyze --models sonara,maest,mert,clap`; omitting
`--models` selects all four. A track is eligible when it is missing at least
one selected model, and existing selected-model results are skipped.

### Sonara

Sonara is used in playlist mode as a fast explainable feature pass. It stores
focused playlist features under `metadata_json.sonara_features` and the model
name under `metadata_json.sonara_model`.

Stored groups and keys:

- Core features: `bpm`, `beats`, `onset_frames`, `onset_density`, `n_beats`,
  `rms_mean`, `rms_max`, `loudness_lufs`, `dynamic_range_db`,
  `spectral_centroid_mean`, `zero_crossing_rate`, `duration_sec`.
- Perceptual features: `energy`, `danceability`, `valence`, `acousticness`.
- Musical key: `key`, `key_confidence`.
- Tonal analysis: `predominant_chord`, `chord_change_rate`, `dissonance`.
- Spectral features: `spectral_bandwidth_mean`, `spectral_rolloff_mean`,
  `spectral_flatness_mean`, `spectral_contrast_mean`, `mfcc_mean`,
  `chroma_mean`.

Sonara BPM and key are analyzed values, not copied from file tags. The app keeps
raw Sonara key data and does not derive Camelot notation.

In the multi-model job, Sonara runs after the shared per-batch decode step and
before MAEST, MERT, and CLAP. `batch_size` caps the in-memory track batch used
by the selected models. The shared decode uses FFmpeg to produce mono `float32`
audio at the source sample rate; each model runner then resamples to its own
required rate.

Run Sonara early if you are unsure where to start. It is the most transparent
analysis family because the UI can show and mix its feature groups directly.

### MAEST

MAEST writes genre metadata and embeddings only to SQLite during analysis:

- `metadata_json.maest_model`
- `metadata_json.maest_genres`
- `metadata_json.maest_syncopated_rhythm`
- `embeddings.embedding_key = "maest"`

The adapter uses `maest-infer` with `discogs-maest-30s-pw-129e-519l`. It
analyzes up to three 30-second windows per track:

- the 60-second offset;
- a window near 38 percent of duration;
- a window near 72 percent of duration.

Impossible or duplicate windows are clamped and deduplicated. Per-label
activations are averaged across windows, then the top labels are stored. MAEST
embedding rows are averaged across the same windows and stored under embedding
key `maest`.

MAEST analysis itself does not modify audio files. The separate genre-save
action can later write stored MAEST labels into standard audio genre tags.
The `maest_syncopated_rhythm` flag is derived from saved MAEST genres and is
used by the library `syncopated` preset.

Run MAEST before using genre writing or the `syncopated` preset. Review labels
before writing them to files; analysis is database-only, but tag writing is an
explicit audio-file mutation.

### MERT

MERT builds audio-to-audio embeddings under embedding key `mert`.

The default model is:

```text
m-a-p/MERT-v1-95M
```

MERT search uses only MERT vectors. It does not mix with Sonara features or CLAP
vectors.

Run MERT when seed-track similarity matters more than explainable controls.
Search results depend on existing MERT embeddings, so newly scanned tracks must
be analyzed before they appear in useful MERT results.

### CLAP

CLAP builds music-focused audio embeddings under embedding key `clap` and
creates text vectors for text-to-audio search.

The active checkpoint is:

```text
lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt
```

Text search requires CLAP audio embeddings produced by the same CLAP checkpoint.

Run CLAP when you want to search by mood, instrumentation, energy, or other
descriptive language. Clear concrete prompts usually work better than single
genre words.

### Promoted Classifiers

Promoted classifiers are local classifier profiles, not audio-analysis models
that decode files themselves. They score tracks from already stored analysis
outputs:

- SONARA playlist features from `metadata_json.sonara_features`;
- MERT embeddings from `embeddings.embedding_key = "mert"`;
- MAEST embeddings from `embeddings.embedding_key = "maest"`.

Tracks missing any of those inputs are skipped by the classifier job. Scores are
stored in `track_classifier_scores` under the profile classifier key.

Use promoted classifiers after you have trained and promoted a profile in
Rhythm Lab. They are best for personal library concepts that are difficult to
capture with a generic genre label or one similarity seed.

Stable model locations use the profile artifact prefix:

```text
models/classifiers/<artifact-prefix>/model.joblib
```

Those files are produced outside the main app by Rhythm Lab's promotion command:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation
```

The promoted `model.joblib` and `model.json` files are local artifacts and are
ignored by git. The source Rhythm Lab training artifacts remain in the
classifier-specific lab workspace:

```text
tools/rhythm-lab/artifacts/<artifact-prefix>/
```

Promoted metadata is generated from the Rhythm Lab profile and model artifact:
`classifier_key`, profile name, profile type, labels, feature set, source
artifact, and training label counts. Rhythm Lab training metrics use the same
profile-neutral shape for all profiles (`positive_*` metrics and
`label_order`) instead of classifier-specific metric aliases.

For Rhythm Lab profile management, labeling, training, prediction, promotion, archive, and delete workflows, see [Rhythm Lab](rhythm-lab.md).

The user-facing score is the classifier probability for the profile's positive
training label. Because UI displays can round probabilities, a value shown as
`1.0000` may be slightly below mathematical `1.0`. Use thresholds such as
`0.99`, `0.95`, or `0.90` for practical filtering instead of relying on exact
`1.0`.
