# Smart Set Builder routing

Аудитория: пользователи, которым нужно понять SET output  
Цель: объяснить seeds, anchors, BPM, diversity и guards  
Тип: explanation

Smart Set Builder генерирует ordered previews. Это route planner поверх local
analysis data, а не автоматический final set.

## Candidate requirements

SET requires candidates with:

- SONARA features;
- MERT embeddings;
- MAEST embeddings;
- CLAP audio embeddings.

Tracks без любого required input не feature-complete для SET.

## Manual seeds

Manual mode использует от одного до пяти selected seed tracks. Known artists
должны быть unique среди seeds.

## Auto anchors

Auto mode samples first anchor из full feature-complete library, затем samples
remaining waypoint anchors из related candidates. Generated route bridges
between anchors.

## Diversity and energy

`Diversity` меняет, насколько широко route исследует related candidates.
`Energy curve` формирует route как warmup, balanced, peak или wave.

## BPM modes

`general` сохраняет normal transition compatibility. `low_to_high` and
`high_to_low` добавляют actual-BPM trajectory с `slow`, `medium` или `fast`
change. Missing start/target BPM can be inferred from first seed/anchor and
library range.

Half/double tempo matching помогает compatibility. Оно не меняет actual BPM
trajectory.

## Classifier modifiers

Promoted classifiers - optional score modifiers. Missing scores neutral.
Classifier flow может быть flat, rise или fall across preview.

## Artist guard

Generated preview keeps at most one track per known artist. Unknown artists
guarded reliably быть не могут, поэтому clean metadata все еще важна.
