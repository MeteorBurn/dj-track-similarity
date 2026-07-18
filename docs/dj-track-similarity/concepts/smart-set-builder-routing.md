# How Smart Set Builder routes a preview

> Audience: Users tuning SET controls.
> Goal: Explain why SET needs full analysis and why the preview is ordered the way it is.
> Type: concept

Smart Set Builder works from eligible tracks. Anchors and candidate scores feed the route sampler. The result is a preview for listening, not an automatic final DJ set.

## Eligibility

A track must have SONARA, MERT, MAEST, and CLAP data to be eligible. The response reports total and missing coverage so you know whether the library is ready.

## Manual and auto anchors

Manual mode uses selected seed tracks as fixed waypoint anchors. Auto mode chooses the first anchor from the feature-complete library, then chooses related artist-diverse waypoint anchors.

The backend clamps auto anchors to `1..5` and requires enough eligible tracks.

## Candidate scoring

Base candidate scoring combines:

- MERT embedding similarity,
- CLAP audio embedding similarity,
- MAEST embedding similarity,
- broad SONARA similarity,
- optional classifier preference and confidence.

Mode controls shift the balance between close similarity, discovery, weird adjacent matches, and flow.

## Ordering

The sequence step adds:

- transition confidence,
- energy curve fit,
- BPM curve fit when enabled,
- diversity pressure,
- classifier flow,
- artist pressure.

Known artists are guarded so one preview uses at most one track per known artist. If manual seeds violate that rule, SET fails clearly instead of hiding the conflict.

## BPM behavior

General BPM mode uses tempo for transition compatibility. Low-to-high and high-to-low modes add an actual BPM trajectory. Half/double tempo matching helps transition compatibility but does not replace the actual trajectory.

SET resolves current SONARA tempo evidence first. Below `0.45` confidence, ranked SONARA candidates
and the Mutagen BPM tag can corroborate or replace the working estimate. Beat-grid stability weakens
unreliable tempo evidence, and a low-reliability estimate cannot become a hard rejection by itself.
See the [SONARA v0.2.4 project contract](../reference/sonara-v0-2-4-contract.md).

## Add preview is explicit

SET returns preview rows. It does not replace the current set. Click **Add preview** to append preview tracks to the set.
