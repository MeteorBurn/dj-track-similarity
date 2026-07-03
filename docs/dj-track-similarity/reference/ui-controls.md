# UI controls reference

> Audience: Users who want exact ranges and defaults for common controls.
> Goal: Keep controls searchable without repeating every guide page.
> Type: reference

## Database and scan

| Control | Range or values | Notes |
| --- | --- | --- |
| Database path | `.sqlite` path | existing or new local database |
| Music root | existing folder | scan source |
| Scan workers | `1..64` API, UI usually caps near CPU half up to 8 | metadata scan and Refresh Tags |

## Analysis

| Control | Range or values | Notes |
| --- | --- | --- |
| Model checkboxes | SONARA, MAEST, MERT, MUQ, CLAP, CLASSIFIERS | selected families in one job |
| Analyze limit | `0..100000` in UI | `0` means whole library |
| Device | AUTO, CPU, CUDA | for MAEST/MERT/MuQ/CLAP adapters |
| Track batch size | `1..64` | decoded tracks held per job batch |
| Inference batch size | `1..128` | model samples per forward pass |
| Reset | one family | SQLite-only reset |

## Search

| Control | Range or values | Notes |
| --- | --- | --- |
| Similarity | `0.00..1.00` | MERT and SONARA threshold |
| CLAP Similarity | raw text score threshold | not comparable to MERT seed scores |
| Limit | `1..500` | search result count |
| SONARA mixer | UI sliders `0..3`, API allows `0..5` | timbre, rhythm, dynamics, harmonic, tempo |
| SONARA modifiers | `-1..1` | directional bias from seed context |

Tempo-aware search filters resolve BPM from stored SONARA analysis first, then from the Mutagen BPM
tag when SONARA BPM is missing.

## SET

| Control | Range or values | Notes |
| --- | --- | --- |
| Seed source | Manual, Auto | selected seeds or automatic anchors |
| Auto anchors | `1..5` | active only in Auto mode |
| Set mode | similar crate, weird adjacent, balanced set, discovery | changes scoring balance |
| Track limit | `1..500` | seeds/anchors count toward it |
| Diversity | `0.00..1.00` | spread candidates while preserving relation |
| Energy curve | balanced, warmup, peak, wave | ordering pressure |
| BPM mode | general, low to high, high to low | trajectory only outside general |
| BPM change | slow, medium, fast | active for BPM trajectory |
| Start BPM | blank or `20..300` | auto when blank |
| Target BPM | blank or `20..300` | auto when blank |
| Classifier Preference | `-1.00..1.00` | missing scores stay neutral |
| Classifier Flow | flat, rise, fall | preference shape across preview |

SET BPM modes resolve tempo from stored SONARA BPM first, then from the Mutagen BPM tag when SONARA
BPM is missing.

## Hybrid preview

| Control | Range or values | Notes |
| --- | --- | --- |
| Sources | MERT, MAEST, SONARA, CLAP | at least one enabled |
| Source weight | `0.00..1.00` | ignored when source disabled |
| Per-source | `1..100` | candidates fetched per source |
| Result limit | `1..100` | preview rows |
| Risk penalty | `0.00..1.00` | diagnostic transition-risk penalty |
| Use classifier preferences | on/off | requires compatible promoted signals |

## Helper dialogs

Audio Doctor apply confirmation is `APPLY REPAIR`.

Audio Dedup apply confirmation is `APPLY DELETE`.
