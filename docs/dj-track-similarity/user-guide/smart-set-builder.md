# Build a Smart Set preview

> Audience: Users preparing an ordered listening or DJ candidate list.
> Goal: Explain SET controls, requirements, Hybrid preview, and safety boundaries.
> Type: guide

SET helps after search has found too many plausible tracks but you still need a musical direction
and an order to review. You provide anchors or let the app choose them, then describe the desired
closeness, diversity, energy shape, and optional tempo or classifier direction.

The result is an ordered listening draft. It is useful for discovering a possible route through
the library and for spotting gaps, repetitions, or abrupt changes. It is not a finished performance
plan, cue-point generator, or guarantee that adjacent tracks will mix.

## Browser and API entry points

Open **SET** in the browser. Its nested **Set Builder** and **Hybrid Preview** tabs have independent
controls, results, errors, and cancellation. `ArrowLeft` and `ArrowRight` move between the two
tabs; `Home` and `End` jump to the first and last tab.

Set Builder calls `POST /api/set-builder/generate`. Hybrid Preview calls
`POST /api/search/hybrid`. Both browser forms expose source selection and optional custom weights.
The endpoints return data only. Export remains a separate action through `POST /api/export`. The
same fields and ranges are documented in the [API reference](../reference/api.md).

## What happens when you generate

1. SET limits the pool to tracks with the required analysis.
2. It finds candidates connected to the anchors across several audio signals.
3. It balances those candidates against your mode, diversity, energy, tempo, artist, and optional
   classifier controls.
4. It returns an ordered preview with coverage information.
5. Nothing enters the current set until you click **Add preview**.

The **SET** tab calls `/api/set-builder/generate` to create this preview.

## Requirements

SET always requires SONARA broad analysis. It also requires every enabled embedding source. The
default enabled sources are:

- MERT embedding,
- MAEST embedding,
- MuQ embedding,
- CLAP audio embedding.

The default raw fusion weights are:

| Signal | Raw weight |
| --- | ---: |
| `mert` | `0.30` |
| `maest` | `0.18` |
| `muq` | `0.15` |
| `clap` | `0.22` |
| `sonara_broad` | `0.30` |

SET normalizes these weights over the enabled embeddings plus SONARA broad. With all defaults, it
divides each raw weight by `1.15`; the response reports the result in `weights_used`.

For the exact pre-MuQ request profile, disable MuQ and enable custom weights. The browser sends only
`mert`, `maest`, and `clap` with raw weights `0.30`, `0.18`, `0.22`, plus `sonara_broad` at
`0.30`. MuQ is then neither loaded nor required for eligibility. The backend normalizes those raw
values before scoring. Custom weights must contain exactly the enabled embedding keys plus
`sonara_broad`.

The response includes total-track and eligible-track counts, plus missing counts for MERT, MAEST,
MuQ, CLAP, and SONARA.

## Seed source

**Manual - selected** uses selected seed tracks as waypoint anchors. The backend validates that selected seeds are feature-complete and enforces the artist guard: at most one track per known artist in one preview.

**Auto - random start** chooses the first anchor from the feature-complete library, then chooses related waypoint anchors. **Auto anchors** is clamped to `1..5`.

## Set mode

- **Similar crate - close**: stays close to anchors and takes fewer diversity risks.
- **Weird adjacent - odd**: allows less obvious adjacent material while keeping a link to anchors.
- **Balanced set - flow**: balances similarity, diversity, transition compatibility, energy curve, and artist limits.
- **Discovery - wide**: broadens the search for novelty while keeping candidates connected to anchors.

Choose the mode by what you want to hear in the result. Close is useful for a coherent crate,
Balanced is a general first draft, and the wider modes are for discovering less obvious links that
need more listening review.

## Size and diversity

- **Track limit** is `1..500`. Seeds and anchors count toward this limit.
- **Diversity** is `0.00..1.00`. Low values stay closer to anchors. High values spread candidates out while preserving connection.

## Energy curve

- **Balanced** keeps energy near the anchor context.
- **Warmup** starts lower and builds.
- **Peak** prefers higher energy and density.
- **Wave** creates a rise/fall pattern.

## BPM controls

Default **General BPM** uses BPM and key as soft transition compatibility signals only. SET uses
current signed SONARA tempo evidence first. Below `0.45` confidence, it checks SONARA candidates and
the Mutagen BPM tag. `grid_stability` can weaken tempo reliability, and the score moves toward
neutral when reliability is low instead of becoming a similarity bonus or hard rejection.

For key transitions, SET prefers a valid Camelot tag, then SONARA's Camelot result, then converts a
conventional key name. Same, relative, and adjacent keys receive graduated compatibility rather
than an exact-text-only match. Low SONARA key confidence weakens that harmonic evidence toward a
neutral score without making matching low confidence values count as similarity by themselves.

The explicit trajectory modes are:

- **Low to high**: build from lower BPM to higher BPM.
- **High to low**: descend from higher BPM to lower BPM.

When a trajectory mode is active:

- **BPM change** can be slow, medium, or fast.
- **Start BPM** and **Target BPM** accept `20..300` or can be left blank for auto inference.
- Half/double tempo matching is used for transition compatibility, not as a replacement for the actual BPM trajectory.

## Classifier sliders

Promoted classifiers can add a SET preference:

- **Preference** ranges from `-1.00` to `1.00`.
- **Flow** can be flat, rise, or fall.

SET follows the same classifier availability state as CLASS. An unavailable profile remains listed
with its status and blocker reason, but it exposes no **Preference** or **Flow** control and its
values are omitted from the SET request. An available profile shows its readiness counts and both
controls.

Missing classifier scores stay neutral. Classifier controls read stored scores. They do not train or decode audio.

## Hybrid preview

The SET tab also contains **Hybrid preview**, an explicit weighted preview across stored MERT, MAEST,
MuQ, SONARA, and CLAP data. The backend default enables `mert`, `maest`, `muq`, `sonara`, and `clap`
at an equal `0.20` each. The browser exposes every source toggle, **Custom weights**, and reset
controls. To reproduce the pre-MuQ Hybrid profile, disable MuQ; disabled sources are omitted from
the request and do not remain as hidden readiness requirements.

Hybrid preview:

- requires one to five selected seeds,
- lets you enable or disable each source,
- uses source weights from `0.00` to `1.00`,
- fetches `1..100` candidates per source,
- shows up to `1..100` preview rows,
- can apply an optional transition-risk penalty from `0.00` to `1.00`,
- can use classifier preference/risk controls when promoted classifiers expose compatible signals.

Transition-risk v2 can also use stored beat-grid stability and SONARA structure boundaries. These
signals remain diagnostics for listening-led ordering: they are not cue points or a promise that a
mix will work. Transition-risk v1 keeps its original calculation for reproducible evaluations.

SET sequencing uses structure separately from the Hybrid risk components. When structure evidence
exists, transition confidence combines `50%` tempo, `30%` harmonic compatibility, and `20%`
structure. Without structure, it uses `60%` tempo and `40%` harmonic compatibility. Beat-grid
stability reaches SET through tempo reliability.

See the [SONARA integration reference](../reference/sonara-integration.md) for the current tempo,
Camelot, and structure rules.

The UI records evaluation session and event rows for feedback. The preview itself leaves tracks and the current set unchanged.

## Add preview

Click **Add preview** to append the current SET preview tracks to the current set. The action is
enabled only for the latest Set Builder response whose database and form state still match. It
never appends Hybrid or another search tab's results. Existing set tracks are not duplicated.
Export is still a separate step.
