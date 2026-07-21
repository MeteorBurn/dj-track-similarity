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
| Stage blocks | SONARA, ML MODELS, CLASSIFIERS | independent manual runs or selected pipeline |
| Analyze limit | `0..100000` in UI | `0` means whole library |
| Device | AUTO, CPU, CUDA | for MAEST/MERT/MuQ/CLAP adapters |
| SONARA outputs | Core, Timeline, Representations | Core is default; other outputs are opt-in |
| SONARA native batch | `1..128` | path batch for `analyze_batch`; default `64` |
| Track batch size | `1..64` | decoded tracks held per job batch |
| Inference batch size | `1..128` | model samples per forward pass |
| Run selected pipeline | selected stages | fixed SONARA, ML, CLASSIFIERS order |
| Reset | one family | SQLite-only reset |

## Search

| Control | Range or values | Notes |
| --- | --- | --- |
| Similarity | `0.00..1.00` | MERT and SONARA threshold |
| CLAP Similarity | raw text score threshold | not comparable to MERT seed scores |
| Limit | `1..500` | search result count |
| SONARA mode | balanced, vibe, sound, dj transition, custom mixer | custom mode enables the visible mixer and modifiers |
| SONARA mixer | `0..5` | timbre, rhythm, dynamics, harmonic, tempo. Dynamics includes SONARA 2.0 loudness range, and harmonic includes Camelot key |
| SONARA modifiers | `-1..1` | directional bias from seed context, including vocalness |
| LAB Limit | `1..100` | Reference Compare candidates per model |
| LAB verdict | mood, palette, instruments, groove, genre, transition, miss | local listening feedback for one candidate and model |

Tempo-aware search filters start from current SONARA evidence. Below `0.45` confidence, they also
check SONARA candidates and the Mutagen BPM tag. Low reliability avoids a hard rejection after the
alternatives are checked.

The LAB tab compares CLAP, MERT, MuQ, MAEST, and SONARA around the first selected seed. The groups are diagnostic and remain separate. LAB is a listening comparison surface for model families.

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

SET BPM modes use the same confidence-aware resolver. `grid_stability` can weaken SONARA tempo
evidence, and unreliable pairs move toward neutral `0.5` rather than earning a match bonus.

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
