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
| SET | Generates an ordered Smart Set Builder preview from manual seeds or auto anchors. | You want a DJ-oriented sequence candidate, not just a single-model search result. |
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
preset, classifier score filters, and add-filtered-tracks. The library controls
include an explicit `LIKE` / `FTS` search-mode toggle. `LIKE` is the default
substring search across artist, title, album, path, and metadata. `FTS` uses
the token-based SQLite FTS5 index. It can count or narrow token matches much
faster, but it does not match arbitrary substrings inside one token and very
common tokens can still spend noticeable time sorting the first page by library
order. The add-filtered-tracks workflow uses the selected search mode. The
library controls also include a sort-direction button that reverses the
currently loaded page in the browser without changing the backend query or
stored database order. Pagination controls sit on the left side of the library
controls after the filter buttons. The right side shows the total count for the
current library view followed by sort-direction and add-visible-tracks controls.
The total count and page counter reflect the active text search, search mode,
preset, liked filter, and classifier score filters.

The CLASS tab contains classifier controls discovered from promoted
`models/classifiers/*/model.json` metadata. Each promoted classifier can be
filtered with a slider, and that slider filters the library and
add-filtered-tracks workflow by `track_classifier_scores.score`. Each
classifier row also has its own score button. Use that button after promoting a
new Rhythm Lab profile when you want to score only that classifier's missing
rows without deleting or recomputing scores for older promoted classifiers.
The main analysis block can still run the `CLASSIFIERS` checkbox after any
selected audio-analysis models. The analysis model rows show coverage counts
for SONARA, MAEST, MERT, CLAP, and complete promoted-classifier score coverage;
the top header keeps only the total track count.

### SET / Smart Set Builder

The SET tab calls `/api/set-builder/generate` and shows an ordered preview that
can be added to the current set. It does not replace or append to the set until
you use the preview action.

SET can run from:

- manual seeds: `1-5` selected seed tracks;
- auto anchors: `3-5` feature-complete tracks chosen by the backend.

The four modes are:

- `similar_crate`: stay close to the seed or anchor zone.
- `weird_adjacent`: keep relevance but allow stranger neighboring material.
- `balanced_set`: prefer bridge tracks, softer transitions, and less repeated
  adjacent texture.
- `discovery`: reserve more room for lower-confidence candidates that may be
  worth checking.

The builder requires stored SONARA features plus MERT, MAEST, and CLAP audio
embeddings. Its SONARA pass uses a broad set of saved features: rhythm/tempo,
dynamics, perception, tonal texture, spectral/timbre values, and saved summary
statistics for larger arrays such as MFCC and chroma. It uses MAEST embeddings
but does not use MAEST genre labels for choosing tracks.

BPM and key affect ordering as soft transition signals. File tags are preferred
first, with SONARA BPM/key as fallback when tags are missing. Classifier
controls in the SET tab can boost target classifier scores, avoid unwanted
scores, or shape a start-to-end mood curve. These controls read stored
`track_classifier_scores`; the SET tab does not launch classifier analysis.

Each preview row exposes a reason such as `seed_anchor`, `similar_to_seed`,
`bridge`, `weird_adjacent`, `discovery`, `classifier_match`, or `mood_shift`.
Hover the score to inspect model scores, SONARA group scores, classifier scores,
and transition confidence.

### SONARA Search

SONARA is the primary explainable seed-search path. It sends selected seed
tracks, limit, minimum similarity, mixer weights, and modifiers to
`/api/search/sonara`.

The UI default result limit is `10`.

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

MERT seed search sends seed tracks, limit, and optional minimum similarity to
`/api/search`. It ranks tracks in the MERT embedding space.

The UI and API default result limit is `10`.

Use MERT after running `dj-sim analyze --models mert` or the matching selected
model in the UI analysis job. If results are empty or stale, check whether the
candidate tracks have MERT embeddings.

### CLAP Text Search

CLAP text search sends a text prompt, limit, optional minimum similarity, and
device to `/api/search/text`. It ranks CLAP audio vectors against a CLAP text
vector. The UI uses adaptive contrast by default: it sends the Text query as a
positive CLAP prompt and the optional Avoid field as a negative CLAP prompt,
then ranks candidates by `positive similarity - negative similarity`. This is
useful for queries such as vocal presence, ambience, drum feel, or other broad
descriptors where a single positive prompt is often too vague.

The CLAP tab includes prompt presets. Presets provide local Find/Avoid prompt
pairs; selecting one immediately fills both Text query and Avoid, then closes
the preset menu. The menu also closes when focus moves to another part of the
app.

The UI and API default result limit is `10`.

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

The CLASS tab is for classifier-driven filtering workflows rather than
similarity search.
It lists promoted classifiers discovered from `models/classifiers/*/model.json`:

- Each classifier slider filters the library server-side by stored classifier
  score.
- Each classifier's play button resets stored scores for that classifier key and
  then starts a job for that classifier only.
- The metadata dialog shows stored classifier scores below SONARA features.

Promoted classifiers require a promoted model file and feature-complete tracks.
They do not analyze audio directly. Select `CLASSIFIERS` in the main analysis
block to start cancellable classifier jobs after any selected audio models, or
use the per-classifier play button in the CLASS tab for a full recalculation of
one classifier across all eligible tracks. Run SONARA, MERT, and MAEST first
for the tracks you want to score.

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
