# UI controls reference

> Audience: Users tuning controls after learning the workflow.
> Goal: Summarize key labels, types, and ranges.
> Type: reference

## Analysis

| Control | Meaning |
| --- | --- |
| Analyze limit | `0` means whole library in the UI; positive values limit missing tracks |
| Device | `auto`, `cpu`, or `cuda` |
| Track batch size | decoded tracks grouped together |
| Inference batch size | model forward-pass batch size |

## SET

| Control | Type/range | Meaning |
| --- | --- | --- |
| Seed source | manual/auto | selected seeds or auto anchors |
| Set mode | four modes | similar crate, weird adjacent, balanced set, discovery |
| Track limit | integer | preview length |
| Auto anchors | 1-5 | waypoint count in auto mode |
| Energy curve | warmup/balanced/peak/wave | intensity route |
| Diversity | 0.00-1.00 | closeness vs exploration |
| BPM mode | general/low_to_high/high_to_low | compatibility or actual trajectory |
| BPM change | slow/medium/fast | trajectory speed |
| Start BPM, Target BPM | 20-300 or blank | trajectory bounds |
| Target boost, Avoid cut | classifier sliders | optional modifiers |
| Curve start, Curve end | classifier flow | flat/rise/fall shaping |
| Reset sliders | action | reset diversity and classifier slider values only |
