# Smart Set Builder routing

Audience: users who want to understand SET output  
Goal: explain seeds, anchors, BPM, diversity, and guards  
Type: explanation

Smart Set Builder generates ordered previews. It is a route planner over local
analysis data, not an automatic final set.

## Candidate requirements

SET requires candidates with:

- SONARA features;
- MERT embeddings;
- MAEST embeddings;
- CLAP audio embeddings.

Tracks missing any required input are not feature-complete for SET.

## Manual seeds

Manual mode uses one to five selected seed tracks. Known artists must be unique
among those seeds.

## Auto anchors

Auto mode samples the first anchor from the full feature-complete library, then
samples remaining waypoint anchors from related candidates. The generated route
bridges between those anchors.

## Diversity and energy

`Diversity` changes how broadly the route explores related candidates.
`Energy curve` shapes the route as warmup, balanced, peak, or wave.

## BPM modes

`general` keeps normal transition compatibility. `low_to_high` and
`high_to_low` add an actual-BPM trajectory with `slow`, `medium`, or `fast`
change. Missing start or target BPM values can be inferred from the first
seed/anchor and the library range.

Half/double tempo matching helps compatibility. It does not change the actual
BPM trajectory.

## Classifier modifiers

Promoted classifiers are optional score modifiers. Missing scores stay neutral.
Classifier flow can be flat, rise, or fall across the preview.

## Artist guard

The generated preview keeps at most one track per known artist. Unknown artists
cannot be guarded reliably, so clean metadata still matters.
