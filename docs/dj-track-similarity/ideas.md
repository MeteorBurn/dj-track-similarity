# Ideas

This page captures larger workflow ideas and staged product notes. Some ideas
may have a first implementation while later workflow extensions remain
exploratory.

## Smart Set Builder From Seed Tracks

The first Smart Set Builder version adds a dedicated SET tab that generates an
ordered DJ set preview from either `1-5` manual seed tracks or `1-5` random
but related auto anchors chosen by the backend on each generation. The goal is
not just "more similar tracks"; it acts as a curator over existing analysis
models and produces a sequence for listening, digging, or set preparation.

The first version works without training a new model:

- use MERT similarity for musical/audio closeness;
- use MAEST embeddings, but not MAEST genre labels, for audio-model agreement;
- use CLAP audio embeddings from stored analysis, without a text prompt;
- use a broad SONARA feature block for rhythm, dynamics, perception, tonal
  texture, spectral/timbre values, and saved array summaries;
- use promoted classifier scores such as `abstract_edge`, `break_energy`, or
  `voice_presence` as optional target, avoid, or mood-curve signals;
- use file-tag BPM/key first, with SONARA fallback, as soft transition-ordering
  signals rather than core vibe ranking, with optional explicit BPM trajectories
  for slow-to-fast or fast-to-slow sets.

Suggested modes:

- `similar_crate`: stay close to the seed tracks and rank by strong agreement
  across MERT, MAEST, SONARA, and classifier scores.
- `weird_adjacent`: keep enough similarity to remain relevant, but prefer
  candidates with unusual classifier/model disagreement or more experimental
  texture.
- `balanced_set`: generate a DJ-oriented list with bridge tracks, BPM/energy
  compatibility, and reduced repetition between adjacent tracks.
- `discovery`: allow riskier candidates and reserve part of the list for
  low-confidence tracks that could reveal useful new classifier positives.

Implemented controls:

- `Seed source`: manual selected waypoint seeds or auto random related
  waypoint anchors;
- `Set mode`: `Similar crate - close`, `Weird adjacent - odd`,
  `Balanced set - flow`, or `Discovery - wide`;
- `Track limit`: target length, defaulting to 24, with seeds/anchors counting
  toward that length and spaced across the preview;
- `Energy curve`: `Balanced - steady`, `Warmup - build`, `Peak - intense`, or
  `Wave - rise/fall`;
- `Auto anchors`: `1-5` waypoint anchors shown only in auto mode;

Advanced controls keep the less common shaping knobs available without making
the default SET workflow too dense:

- `Diversity`: how far the list may widen from the anchor zone while still
  following the selected mode;
- `BPM mode`: `General BPM - transition`, `Low to high - climb`, or
  `High to low - descend`;
- `BPM change`: slow, medium, or fast tempo movement across the preview;
- `Start BPM` and `Target BPM`: optional explicit tempo endpoints; empty values
  are inferred from the first seed/anchor and the library BPM range;
- classifier `Target boost`, `Avoid cut`, `Curve start`, and `Curve end`
  sliders;
- `Reset sliders`, which resets only diversity and classifier sliders;
- optional API-only `random_seed` for reproducing a specific randomized run.

The generated result explains why each track was selected, for example
`seed_anchor`, `similar_to_seed`, `bridge`, `weird_adjacent`, `discovery`,
`classifier_match`, or `mood_shift`, and exposes the underlying MERT, MAEST,
CLAP, SONARA group, classifier, and transition scores for manual review.
Manual seeds remain marked as `seed_anchor`, but the artist guard is strict:
one known artist can appear at most once in a generated SET preview, so
duplicate known artists in manual seeds are rejected.
Auto anchors use the same `seed_anchor` reason and are distributed as route
waypoints instead of being front-loaded at the beginning of the preview.

Possible API shape:

```text
POST /api/set-builder/generate
```

Input fields:

- `seed_mode`
- `seed_track_ids`
- `auto_seed_count`
- `limit`
- `mode`
- `diversity`
- `energy_curve`
- `bpm_mode`
- `bpm_change`
- `bpm_start`
- `bpm_target`
- `classifier_targets`
- `classifier_avoid`
- `classifier_curves`
- `random_seed`

Output fields:

- ordered track rows;
- selection reason;
- similarity, SONARA group, transition, classifier, and diversity scores;
- relevant classifier scores;
- set-order transition metadata.

Later extensions could send selected tracks to Rhythm Lab, mark them as reviewed,
export XLSX lists, exclude already reviewed/exported tracks, or save generated
sessions for iterative active-learning loops.
