# Read similarity scores as suggestions

> Audience: Users comparing result scores across tabs.
> Goal: Prevent score-scale mistakes.
> Type: concept

Scores are ranking signals. They are useful inside the workflow that produced them. They are not universal music quality or mix probability.

## MERT seed search

MERT search compares stored audio embeddings from selected seed tracks to candidate tracks. The score is useful for seed-based audio-to-audio neighborhood ranking.

## SONARA search

SONARA search compares feature values and applies mixer weights plus optional modifier bias. It is more explainable than MERT, but it is still a similarity model. Raising a mixer weight changes the ranking question.

## CLAP text search

CLAP text search compares text embeddings to stored CLAP audio embeddings. Raw text-to-audio scores are often lower than seed-based audio-to-audio scores. Useful matches can appear around `0.35..0.55`, depending on prompts and library content.

When the Negative bank is enabled, the visible score is contrast evidence, not a probability.

## SET scores

Smart Set Builder combines MERT, CLAP audio, MAEST embedding, broad SONARA similarity, transition confidence, diversity, energy curve, BPM curve, artist pressure, and optional classifier preferences. The output score is for ordering a preview under the selected controls.

## Hybrid preview scores

Hybrid preview uses weighted reciprocal-rank fusion across enabled sources, optional transition-risk penalty, and optional classifier controls. Its detail panel is designed to explain source support and risk, not to prove a final mix.

## Audio Dedup thresholds

Audio Dedup `min_similarity` is an audio-to-audio content gate over stored MERT, MAEST, and CLAP audio embeddings. It is not comparable to CLAP text-search similarity.

## Practical reading

- Compare scores inside the same tab and same settings.
- Be careful after changing thresholds, weights, or prompts.
- Preview audio before adding to a set.
- Do not use one tab's threshold as another tab's safety rule.
