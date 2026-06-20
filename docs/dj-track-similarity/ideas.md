# Ideas

This page captures larger workflow ideas that are not implemented yet. Treat
them as product notes, not as current behavior or API contracts.

## Smart Set Builder From Seed Tracks

Add a dedicated UI workflow that generates a varied DJ set candidate list from
3-10 selected seed tracks. The goal is not just "more similar tracks"; it should
act as a curator over existing analysis models and produce a useful sequence for
listening, digging, or set preparation.

The first version could work without training a new model:

- use MERT similarity for musical/audio closeness;
- use MAEST labels for genre and texture hints;
- use SONARA features for BPM, energy, and rhythmic compatibility;
- use promoted classifier scores such as `abstract_edge`, `break_energy`, or
  `voice_presence` as preference and exclusion signals;
- exclude tracks that are already labelled, liked, reviewed, or recently shown
  when the user wants discovery rather than confirmation.

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

Useful controls:

- seed track picker;
- target length;
- diversity amount;
- energy curve such as warmup, balanced, peak, or wave;
- classifier targets and avoid rules;
- exclude liked, labelled, reviewed, or already exported tracks;
- optional BPM/key compatibility constraints.

The generated result should explain why each track was selected, for example
`similar_to_seed`, `bridge`, `weird_adjacent`, or `classifier_match`, and expose
the underlying MERT/MAEST/SONARA/classifier scores for manual review.

Possible API shape:

```text
POST /api/set-builder/generate
```

Input fields:

- `seed_track_ids`
- `limit`
- `mode`
- `diversity`
- `energy_curve`
- `classifier_targets`
- `exclude_reviewed`

Output fields:

- ranked track rows;
- selection reason;
- similarity and diversity scores;
- relevant classifier scores;
- optional set-order metadata such as energy step or bridge target.

Later extensions could send selected tracks to Rhythm Lab, mark them as reviewed,
export M3U/XLSX lists, or save generated sessions for iterative active-learning
loops.
