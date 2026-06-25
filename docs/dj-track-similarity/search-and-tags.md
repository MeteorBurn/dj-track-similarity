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

- manual seeds: `1-5` selected seed tracks distributed as waypoint anchors;
- auto anchors: `1-5` waypoint anchors, starting from a full-library random
  feature-complete track and then following a related route.

The four modes are:

- `similar_crate` (`Similar crate - close`): stay close to the seed or anchor
  zone.
- `weird_adjacent` (`Weird adjacent - odd`): keep relevance but allow stranger
  neighboring material.
- `balanced_set` (`Balanced set - flow`): prefer bridge tracks, softer
  transitions, and less repeated adjacent texture.
- `discovery` (`Discovery - wide`): reserve more room for lower-confidence
  candidates that may be worth checking.

The SET controls are split into a short Basic surface and a collapsed Advanced
surface. Basic keeps the normal generation path visible:

- `Seed source`: a two-option toggle. `Manual - selected` keeps selected seed
  chips and distributes them as waypoint anchors; `Auto - random start` samples
  the first anchor from the full feature-complete library on every run, then
  builds a related route.
- `Auto anchors`: number of waypoint anchors in auto mode, `1-5`; this control
  stays visible beside `Seed source` and is disabled until `Seed source` is
  `Auto - random start`.
- `Set mode`: chooses the scoring personality listed above.
- `Energy curve`: `Balanced - steady`, `Warmup - build`, `Peak - intense`, or
  `Wave - rise/fall`.
- `Track limit`: preview length, default `24`; seed or anchor positions count
  toward this number and are spaced across the preview.
- `Diversity`: `0.00-1.00`; lower values stay closer to anchors, higher values
  widen the set while preserving the mode constraints.

Advanced keeps optional bias and trajectory controls out of the default view:

- `BPM mode`: `General BPM - transition` keeps only the normal soft transition
  rule; `Low to high - climb` and `High to low - descend` add an explicit tempo
  trajectory.
- `BPM change`: `Slow - late change`, `Medium - linear`, or
  `Fast - early change`; active only for explicit BPM modes.
- `Start BPM` and `Target BPM`: optional `20-300` values. Leave either field
  empty to infer it from the first seed/anchor and the analyzed library range.
- Classifier controls: `Preference` is one signed slider from `-1.00` to
  `+1.00`; positive values prefer higher stored classifier scores, negative
  values prefer lower stored classifier scores, and `0.00` is neutral. `Flow`
  chooses whether that same preference is applied evenly (`Flat`), increases
  toward the end (`Rise`), or starts stronger then eases off (`Fall`).
- `Reset sliders`: resets only SET diversity and classifier sliders; seed
  source, mode, limit, anchor count, energy curve, and BPM controls stay
  unchanged.

The builder requires stored SONARA features plus MERT, MAEST, and CLAP audio
embeddings. Its SONARA pass uses a broad set of saved features: rhythm/tempo,
dynamics, perception, tonal texture, spectral/timbre values, and saved summary
statistics for larger arrays such as MFCC and chroma. It uses MAEST embeddings
but does not use MAEST genre labels for choosing tracks.
Auto mode samples its first anchor from all feature-complete tracks rather than
from the smaller related candidate pool. After that random start, the builder
prefilters around the chosen anchor, samples the remaining waypoint anchors from
related candidates, and places all anchors at evenly spaced positions in the
preview. Generated bridge, discovery, or mood-shift candidates fill the gaps
between anchors. The sequence itself is also sampled from mode-scored
candidates, so rerunning the same controls can produce a different set while
still following the selected mode.

BPM and key affect ordering as soft transition signals. File tags are preferred
first, with SONARA BPM/key as fallback when tags are missing. Explicit BPM mode
adds a separate actual-BPM curve on top of that transition compatibility, so a
set can be pushed from slow to fast or fast to slow while still obeying the
selected SET mode. Classifier controls in the SET tab use one signed preference
per classifier instead of separate target and avoid controls, so a classifier
cannot be requested and rejected at the same time. When active, these controls
can bias both the random-start anchor and later auto-anchor selection before the
ordered preview is filled. These controls read stored `track_classifier_scores`;
the SET tab does not launch classifier analysis. A `Preference` value of `0.00`
is treated as neutral; `Flow` only has an effect for classifiers with a non-zero
preference.
The generated sequence also applies a strict artist guard: a known artist can
appear at most once in one SET preview. Manual seed tracks are preserved as
distributed `seed_anchor` waypoint items, but manual seeds with the same known
artist are rejected instead of being separated by generated tracks.

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

### Hybrid Search Preview

`/api/search/hybrid` is exposed in the UI as a compact `Hybrid preview` block
inside the existing SET workflow. It is not a separate top-level tab, and it
does not replace or alter the visible SET, SONARA, MERT, CLAP, or CLASS tabs,
their endpoints, weights, or scoring behavior.

Use `Generate weighted preview` when you want a quick seed-based weighted
candidate list instead of an ordered Smart Set Builder route. The block reuses
the currently selected seed tracks and requires `1-5` seeds. MERT, MAEST,
SONARA, and CLAP sources can be enabled or disabled, each source has an inline weight, and
the UI exposes `Per-source` (`1-100`, default `30`) plus `Result limit`
(`1-100`, default `25`) and `Risk penalty` (`0.0-1.0`, default `0.0`). The
browser does not fetch profile artifacts from the filesystem; equal default
weights are sent unless you edit them, and the risk penalty is off unless you
opt in.

Hybrid preview rows also expose optional evaluation feedback controls. Rating
buttons map to `Strong = 3`, `Works = 2`, `Maybe = 1`, and `Reject = 0`. Reason
tags are limited to the PR-21 allowlist (`good_groove`, `good_density`,
`good_texture`, `good_mood`, `good_tonal`, `too_vocal`, `bad_density`,
`bad_tonal`, `too_obvious`, `interesting_adjacent`, `wrong_energy`,
`wrong_texture`, `bad_transition_risk`). A saved row shows a compact state such
as `Rated: Works · good_groove, good_density`. Re-rating the same candidate
overwrites the previous `hybrid_ui` pair labels for the current seeds, so the
label count stays stable on repeated edits. The block also shows accumulated
evaluation label counts when the selected database exposes schema-v4 evaluation
tables.
Use `dj-sim eval report --judged-only`, `run-ablation --judged-only`, or
`run-calibration --judged-only` after recording previews and ratings when you
want judged validation. These reports count only feedback that can be matched to
recorded result events. Small samples stay `insufficient_data`; larger samples
unlock diagnostics and candidate-profile review guidance, but never automatic
default updates.

The endpoint accepts `1-5` seed track IDs, generates candidates from requested
exact sources (`mert`, `maest`, `sonara`, `clap`), excludes the seeds, and ranks the
union with weighted reciprocal-rank fusion. CLAP is a stored audio-embedding
source in this preview, not a prompt-aware Hybrid UI. If no inline `weights` or
`score_profile` is supplied, requested sources use equal weights. The response
contains a preview `score`, `adjusted_score`, `raw_rrf_score`,
`transition_risk_penalty`, `transition_risk_weight`, per-source rank/weight
breakdown, light source-support diagnostics, lightweight transition diagnostics,
warnings, `weights_used`, and limitations. With the default risk penalty `0.0`,
ranking stays the plain weighted-RRF preview. When the penalty is greater than
zero, the preview normalizes raw RRF scores within the candidate set and sorts by
`adjusted_score = normalized_rrf_score - transition_risk_weight * transition_risk`;
missing risk applies no penalty.

The browser sends `record_session: true` for Hybrid preview so the generated
candidate list can be tied to later UI feedback. Direct API callers remain safe
by default because `record_session` defaults to `false`. Recorded Hybrid events
use diagnostic score naming (`score_kind`, `adjusted_score`, `raw_rrf_score`,
`transition_risk`, `transition_risk_penalty`, `transition_risk_weight`, and
per-source rank/score payloads); these values are ranking diagnostics, not
confidence or calibrated probabilities.

Before settling on a non-zero `Risk penalty`, use the CLI report
`dj-sim eval sweep-risk-penalty --profile <json> --weight ...` against recorded
candidate pools. Unlabeled sweeps provide only internal diagnostics such as
average transition risk at K and source-count coverage; labeled sweeps can compare
NDCG, MAP, MRR, precision, bad-suggestion rate, and hit rate. The report makes no
best-weight claim unless explicit evaluation pair feedback is present.

Treat the displayed score as a weighted rank-fusion preview only. It is not
confidence, probability, or a calibrated human-taste estimate. Each result also
includes `transition_risk` and `transition_diagnostics` built from stored
BPM, key, energy, and source-consensus signals. That risk is a lightweight
diagnostic score for future ranking experiments, not AutoMix, beatgrid analysis,
cue detection, calibrated confidence, or a calibrated transition probability. The
UI keeps diagnostics intentionally light: adjusted row score, compact risk text,
source support, source weights/ranks on hover, visible warnings when coverage is
missing, and limitations available from the `Score info` tooltip. A source such
as CLAP that returns no rows contributes no score and does not inflate the
source-disagreement transition risk. The endpoint
can return an empty result list. It reads stored SQLite analysis data only: no
audio files are written, search sessions are recorded only by explicit
`record_session`, classifiers are not trained, and existing production search
endpoints are unchanged.

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
