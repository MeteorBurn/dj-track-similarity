# Read similarity scores as suggestions

> Audience: Users comparing result scores across tabs.
> Goal: Prevent score-scale mistakes.
> Type: concept

Scores answer "which candidates should I inspect first under these settings?" They can tell you that
one candidate ranked ahead of another inside the same search. They cannot judge musical quality or
promise that a transition will work. Scores from different tabs also have no shared scale.

The practical output of a score is an audition order. Listen from the top, keep useful exceptions,
and stop when you have enough candidates.

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

## Reference Compare scores

The LAB Reference Compare panel keeps CLAP, MERT, MuQ, MAEST, and SONARA results in separate groups for one seed track. Compare scores within one model group first. A high MERT score, a high CLAP audio score, and a high SONARA score are related listening hints, not the same measurement.

Saved LAB verdicts are manual pair-feedback labels for a specific model source. They record what you heard. They are not automatic truth labels and they do not rewrite the model score.

## Audio Dedup thresholds

Audio Dedup `min_similarity` is an audio-to-audio content gate over stored MERT, MAEST, and CLAP audio embeddings. It is not comparable to CLAP text-search similarity.

## Practical reading

- Compare scores inside the same tab and same settings.
- Be careful after changing thresholds, weights, or prompts.
- Preview audio before adding to a set.
- Do not use one tab's threshold as another tab's safety rule.
- Use LAB when you need to compare model families by ear before deciding which signal to trust for a reference track.
