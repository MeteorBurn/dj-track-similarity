# Search and Tag Writing

This page covers the search tabs, classifier filtering surface, and the explicit
genre-tag write workflow. Use it when the library is already scanned and you
want to find useful neighbors, build a temporary set, or decide whether to save
MAEST genres back to files.

## Search Modes

The search panel has separate tabs.

Choose the tab by intent:

| Tab | What it does | Use when |
| --- | --- | --- |
| SONARA | Searches with explainable playlist features and custom mixer weights. | You want DJ-transition candidates and control over rhythm, tempo, timbre, dynamics, or harmonic balance. |
| MERT | Searches from selected seed tracks in MERT embedding space. | You want audio-model similarity without tuning feature weights. |
| CLAP | Searches CLAP audio embeddings from a text prompt. | You know the sound or mood you want, but do not have a seed track. |
| CLASS | Filters by promoted classifier scores. | You want a reusable personal signal trained in Rhythm Lab. |

The library browser also has a `syncopated` preset filter. It selects tracks
whose stored MAEST metadata has `maest_syncopated_rhythm = true` and can be
combined with normal library text search and the add-filtered-tracks workflow.
Each library row also has a heart button for a local liked-track list. The
heart filter in the library controls shows only liked tracks in the same
paginated browser, and it can be combined with text search, the syncopated
preset, classifier score filters, and add-filtered-tracks. The library header
has a sort-direction button that reverses the currently loaded page in the
browser without changing the backend query or stored database order.

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

Start with SONARA when you want explainable results. Increase or reduce mixer
weights to make the search lean toward transition fit, rhythmic feel, harmonic
similarity, or overall sound.

### MERT Search

MERT seed search sends seed tracks, lookback tracks, limit, and optional minimum
similarity to `/api/search`. It ranks tracks in the MERT embedding space.

Use MERT after running `dj-sim analyze --adapter mert` or the matching UI
analysis job. If results are empty or stale, check whether the candidate tracks
have MERT embeddings.

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

Use CLAP for exploratory digging. Include musical texture, mood, tempo feel,
vocal presence, or instrumentation in the prompt instead of relying only on a
genre name.

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

Use CLASS filters after scoring a promoted classifier. A high score means the
model thinks the track matches that profile's positive label; it is a workflow
hint, not a guarantee.

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

Use tag writing only after reviewing MAEST labels in the app. It is intended
for saving generated genre labels into the standard genre field; it is not a
general metadata editor and should not be used to change title, artist, album,
BPM, key, or custom tags.
