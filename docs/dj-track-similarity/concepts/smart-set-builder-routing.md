# How Smart Set Builder routes a preview

> Audience: Users tuning SET controls.
> Goal: Explain route shaping, coverage, BPM behavior, and classifiers.
> Type: explanation

## Coverage

Feature-complete candidates require stored MERT, MAEST, and CLAP audio embeddings plus SONARA features. Missing classifier scores remain neutral.

## BPM

`general` BPM mode keeps normal transition rules. `low_to_high` and `high_to_low` add an actual-BPM trajectory. Blank start/target values can be inferred.

## MAEST

SET may use MAEST embeddings, but MAEST genre labels are not the selection source for routing.
