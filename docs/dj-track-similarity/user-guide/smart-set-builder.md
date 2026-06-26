# Smart Set Builder

Audience: DJs and advanced UI users  
Goal: generate ordered read-only set previews  
Type: how-to

Smart Set Builder, shown as the `SET` tab, builds an ordered preview from
manual seeds or automatic anchors. It does not modify the library. You add the
preview to the current set only with an explicit action.

## Requirements

SET needs feature-complete candidates:

- SONARA features;
- MERT embeddings;
- MAEST embeddings;
- CLAP audio embeddings.

MAEST genre labels are not the selection source for SET. MAEST embeddings can
be used as one similarity signal.

## Seed source

- `Manual`: use the tracks you selected as seeds.
- `Auto`: choose the first anchor from the feature-complete library, then build
  related waypoint anchors and bridge tracks.

Manual seeds with the same known artist are rejected. Generated previews also
keep a strict known-artist guard.

## Core controls

| Control | Meaning |
| --- | --- |
| `Set mode` | Similar crate, weird adjacent, balanced set, or discovery. |
| `Track limit` | Number of preview tracks, from 1 to 500. |
| `Auto anchors` | Number of automatic anchors, from 1 to 5. |
| `Energy curve` | Warmup, balanced, peak, or wave intensity shape. |
| `Diversity` | How broadly the route explores related candidates. |

## BPM controls

`BPM mode = general` keeps normal transition compatibility. `low_to_high` or
`high_to_low` adds an actual BPM trajectory.

When file tag BPM exists, SET prefers that value. SONARA BPM is a fallback.
Half/double tempo matching helps transition compatibility; it does not rewrite
the actual BPM trajectory.

## Classifier controls

Promoted classifier scores are optional modifiers. Missing scores stay neutral.
Preference can be positive or negative, and flow can be flat, rise, or fall.

Use `Reset sliders` to reset diversity plus classifier preference/flow values
without changing seed source, mode, limit, anchors, energy curve, or BPM
controls.

## Add the preview

Generate the preview, listen, inspect the list, then use the add action to move
the preview into the current set. Export remains a separate step.
