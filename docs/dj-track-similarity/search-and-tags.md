# Search and Tag Writing

This page covers the search tabs, classifier filtering surface, and the explicit genre-tag write workflow.

## Search Modes

The search panel has separate tabs.

The library browser also has a `syncopated` preset filter. It selects tracks
whose stored MAEST metadata has `maest_syncopated_rhythm = true` and can be
combined with normal library text search and the add-filtered-tracks workflow.

The CLASS tab contains classifier controls discovered from promoted
`models/classifiers/*/model.json` metadata. Each promoted classifier can be
analyzed from the UI, and its slider filters the library and
add-filtered-tracks workflow by `track_classifier_scores.score`.

### SONARA Search

SONARA is the primary explainable seed-search path. It sends selected seed
tracks, optional lookback tracks, limit, minimum similarity, mixer weights, and
modifiers to `/api/search/sonara`.

Mixer weights:

- `timbre`
- `rhythm`
- `dynamics`
- `harmonic`
- `tempo`

Modifiers:

- `energy`
- `valence`
- `acousticness`
- `brightness`
- `rhythm_density`
- `dynamic_range`
- `loudness`

The backend still accepts preset mode names for compatibility:

```text
balanced, vibe, sound, dj_transition, custom
```

The active UI path uses the custom mixer.

### MERT Search

MERT seed search sends seed tracks, lookback tracks, limit, and optional minimum
similarity to `/api/search`. It ranks tracks in the MERT embedding space.

### CLAP Text Search

CLAP text search sends a text prompt, limit, optional minimum similarity, and
device to `/api/search/text`. It ranks CLAP audio vectors against a CLAP text
vector.

Concrete English prompts usually work best:

```text
Melancholic minimal house with broken drums, warm chords, no vocals
Dark hypnotic techno with sparse percussion and deep rolling bass
Organic microhouse with soft pads, plucked textures, and spacious mood
```

### CLASS / Classifiers

The CLASS tab is for classifier-driven workflows rather than similarity search.
It lists promoted classifiers discovered from `models/classifiers/*/model.json`:

- `Analyze <classifier>` starts a cancellable classifier job.
- Each classifier slider filters the library server-side by stored classifier
  score.
- The metadata dialog shows classifier scores, confidence, label, feature set,
  and model file below SONARA features.

Promoted classifiers require a promoted model file and feature-complete tracks.
They do not analyze audio directly; run SONARA, MERT, and MAEST first for the
tracks you want to score.

## Tag Writing

MAEST genre saving writes one normalized semicolon-separated genre string, for
example:

```text
Tech House; Minimal; Techno
```

MAEST category prefixes such as `Electronic---` are stripped before writing.

Format-specific genre fields:

- MP3, WAV, AIFF ID3 tags: `TCON`
- FLAC and Vorbis-style tags: `GENRE`
- MP4, M4A, ALAC: `©gen`

WAV genre writing uses Mutagen's `WAVE` support, saves the `TCON` value, and
verifies that the saved value can be read afterward. It does not run a custom
RIFF repair step. If a WAV write or readback fails, that track is reported as
failed while the batch continues.
