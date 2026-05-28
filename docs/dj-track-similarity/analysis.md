# Analysis Families

This page documents the analysis outputs used by the main app. For the separate classifier labeling and training tool, see [Rhythm Lab](rhythm-lab.md).

## Analysis Families

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

The CLI and UI call Sonara with `batch_size` as parallel track workers, not as a
neural-network inference batch.

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

### MERT

MERT builds audio-to-audio embeddings under embedding key `mert`.

The default model is:

```text
m-a-p/MERT-v1-95M
```

MERT search uses only MERT vectors. It does not mix with Sonara features or CLAP
vectors.

### CLAP

CLAP builds music-focused audio embeddings under embedding key `clap` and
creates text vectors for text-to-audio search.

The active checkpoint is:

```text
lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt
```

Text search requires CLAP audio embeddings produced by the same CLAP checkpoint.

### Promoted Classifiers

Promoted classifiers are local classifier profiles, not audio-analysis models
that decode files themselves. They score tracks from already stored analysis
outputs:

- SONARA playlist features from `metadata_json.sonara_features`;
- MERT embeddings from `embeddings.embedding_key = "mert"`;
- MAEST embeddings from `embeddings.embedding_key = "maest"`.

Tracks missing any of those inputs are skipped by the classifier job. Scores are
stored in `track_classifier_scores` under the profile classifier key.

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
