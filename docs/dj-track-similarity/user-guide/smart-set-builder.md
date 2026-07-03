# Build a Smart Set preview

> Audience: Users preparing an ordered listening or DJ candidate list.
> Goal: Explain SET controls, requirements, Hybrid preview, and safety boundaries.
> Type: guide

The **SET** tab calls `/api/set-builder/generate` and returns an ordered preview. It does not add anything to the current set until you click **Add preview**.

## Requirements

SET uses feature-complete tracks. A track is eligible only when it has:

- SONARA analysis,
- MERT embedding,
- MAEST embedding,
- CLAP audio embedding.

The response includes total-track and eligible-track counts, plus missing counts for MERT, MAEST, CLAP, and SONARA.

## Seed source

**Manual - selected** uses selected seed tracks as waypoint anchors. The backend validates that selected seeds are feature-complete and enforces the artist guard: at most one track per known artist in one preview.

**Auto - random start** chooses the first anchor from the feature-complete library, then chooses related waypoint anchors. **Auto anchors** is clamped to `1..5`.

## Set mode

- **Similar crate - close**: stays close to anchors and takes fewer diversity risks.
- **Weird adjacent - odd**: allows less obvious adjacent material while keeping a link to anchors.
- **Balanced set - flow**: balances similarity, diversity, transition compatibility, energy curve, and artist limits.
- **Discovery - wide**: broadens the search for novelty while keeping candidates connected to anchors.

## Size and diversity

- **Track limit** is `1..500`. Seeds and anchors count toward this limit.
- **Diversity** is `0.00..1.00`. Low values stay closer to anchors. High values spread candidates out while preserving connection.

## Energy curve

- **Balanced** keeps energy near the anchor context.
- **Warmup** starts lower and builds.
- **Peak** prefers higher energy and density.
- **Wave** creates a rise/fall pattern.

## BPM controls

Default **General BPM** uses BPM and key as soft transition compatibility signals only.
SET uses stored SONARA BPM for those signals and for trajectory modes when it exists. If SONARA BPM
is missing, SET falls back to the Mutagen BPM tag.

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

Missing classifier scores stay neutral. Classifier controls read stored scores. They do not train or decode audio.

## Hybrid preview

The SET tab also contains **Hybrid preview**, an explicit weighted preview across stored MERT, MAEST, SONARA, and CLAP data.

Hybrid preview:

- requires one to five selected seeds,
- lets you enable or disable each source,
- uses source weights from `0.00` to `1.00`,
- fetches `1..100` candidates per source,
- shows up to `1..100` preview rows,
- can apply an optional transition-risk penalty from `0.00` to `1.00`,
- can use classifier preference/risk controls when promoted classifiers expose compatible signals.

The UI records evaluation session and event rows for feedback. The preview itself leaves tracks and the current set unchanged.

## Add preview

Click **Add preview** to append the current SET preview tracks to the current set. Existing set tracks are not duplicated. Export is still a separate step.
