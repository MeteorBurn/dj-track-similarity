# How Smart Set Builder routes a preview

> Audience: Users tuning SET controls.
> Goal: Explain why SET needs full analysis and why the preview is ordered the way it is.
> Type: concept

Smart Set Builder works from eligible tracks. Anchors and candidate scores feed the route sampler. The result is a preview for listening, not an automatic final DJ set.

## Eligibility

SONARA broad analysis is always required. A track must also have every enabled embedding source.
The defaults enable MERT, MAEST, MuQ, and CLAP. Disabling a source removes it from eligibility,
loading, centroids, and diversity calculations.

The exact pre-MuQ request selects `mert`, `maest`, and `clap` with raw weights `0.30`, `0.18`,
`0.22`, plus SONARA broad at `0.30`. It does not require MuQ. The backend normalizes those values,
and the response reports enabled sources, effective weights, and total and missing coverage.

The current browser exposes source toggles, custom raw weights, and a reset to the current default
profile. Disabled sources are omitted from the request and eligibility.

## Manual and auto anchors

Manual mode uses selected seed tracks as fixed waypoint anchors. Auto mode chooses the first anchor from the feature-complete library, then chooses related artist-diverse waypoint anchors.

The backend clamps auto anchors to `1..5` and requires enough eligible tracks.

## Candidate scoring

Base candidate scoring combines:

- MERT embedding similarity,
- MAEST embedding similarity,
- MuQ embedding similarity,
- CLAP audio embedding similarity,
- broad SONARA similarity,
- optional classifier preference and confidence.

Mode controls shift the balance between close similarity, discovery, weird adjacent matches, and flow.

Default raw weights are `0.30` for `mert`, `0.18` for `maest`, `0.15` for `muq`, `0.22` for `clap`,
and `0.30` for `sonara_broad`. SET normalizes over enabled embeddings plus SONARA broad, so the
five-signal default divides each raw value by `1.15`.

## Hybrid defaults

Hybrid search defaults to `mert`, `maest`, `muq`, `sonara`, and `clap`, each with an effective weight
of `0.20`. MuQ contributes through the same rank-fusion breakdown, diagnostics, and recorded source
details as the other embedding sources.

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
See the [SONARA integration reference](../reference/sonara-integration.md).

## Add preview is explicit

SET returns preview rows. It does not replace the current set. Click **Add preview** to append preview tracks to the set.
