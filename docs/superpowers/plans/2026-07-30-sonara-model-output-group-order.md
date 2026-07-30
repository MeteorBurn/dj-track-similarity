# SONARA Model Output Group Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate the model-backed vocal output from heuristic Mood fields and place the Vocalness and Aggression groups immediately before Vector summaries.

**Architecture:** Keep the existing declarative `sonaraCoreFeatureGroups` array and change only group membership and array order. Exercise the exported `metadataDialogModel()` through the existing Node-based metadata-reference test so the test observes the same grouped model consumed by the React dialog.

**Tech Stack:** React, TypeScript, Node `node:test`, strict TypeScript checking.

## Global Constraints

- Do not change SONARA analysis, stored values, database columns, API fields, or value formatting.
- Keep `Mood` limited to `Happy`, `Aggressive`, `Relaxed`, and `Sad`.
- Put `Vocalness`, then `Aggression`, immediately before `Vector summaries`.
- Preserve all unrelated working-tree changes and never stage `database/`.

---

### Task 1: Reorder SONARA model-backed metadata groups

**Files:**
- Modify: `frontend/tests/metadataReference.test.mjs:350-385`
- Modify: `frontend/src/TrackMetadataDialog.tsx:43-119`

**Interfaces:**
- Consumes: `metadataDialogModel(track: TrackDetail)`, returning `coreGroups` with ordered group titles and ordered feature records.
- Produces: `Mood` without `vocal_probability`; `Vocalness` containing `vocal_probability`; ordered tail `Spectral`, `Vocalness`, `Aggression`, `Vector summaries`.

- [x] **Step 1: Change the focused test to specify the new grouping**

Replace the existing group-order assertions in the aggression metadata test with:

```js
const model = metadataDialog.metadataDialogModel(track);
const titles = Array.from(model.coreGroups, (group) => group.title);
const vectorSummariesIndex = titles.indexOf("Vector summaries");
assert.deepEqual(
  titles.slice(vectorSummariesIndex - 2, vectorSummariesIndex + 1),
  ["Vocalness", "Aggression", "Vector summaries"],
);

const mood = model.coreGroups.find((group) => group.title === "Mood");
const vocalness = model.coreGroups.find((group) => group.title === "Vocalness");
const aggression = model.coreGroups.find((group) => group.title === "Aggression");
assert.equal(
  mood.features.some((feature) => feature.key === "vocal_probability"),
  false,
);
assert.equal(
  mood.features.find((feature) => feature.key === "mood_aggressive_score").label,
  "Aggressive",
);
assert.deepEqual(
  Array.from(vocalness.features, (feature) => feature.key),
  ["vocal_probability"],
);
```

Retain the existing aggression value assertions so this behavior change cannot
silently alter three-decimal formatting.

- [x] **Step 2: Run the focused test and verify RED**

Run from `frontend/`:

```powershell
node --test tests/metadataReference.test.mjs
```

Expected: FAIL in the model-backed group test because `Vocalness` does not yet
exist and `Aggression` does not immediately precede `Vector summaries`.

- [x] **Step 3: Make the minimal declarative group change**

In `sonaraCoreFeatureGroups`:

1. Remove `vocal_probability` from `Mood`.
2. Change the Mood label from `Aggressive mood` to `Aggressive`.
3. Remove the current `Aggression` group from directly after `Mood`.
4. Immediately after `Spectral`, insert:

```ts
{
  title: "Vocalness",
  features: [
    feature("vocal_probability", "Vocal probability", "Probability returned by the bundled SONARA vocal model."),
  ],
},
{
  title: "Aggression",
  features: [
    feature("aggression_score", "Score", "Dedicated SONARA aggression perceptual rank; not the aggressive-mood heuristic."),
    feature("aggression_confidence", "Evidence support", "Supported musical evidence for the aggression analysis, not rank certainty."),
    feature("aggression_forcefulness", "Forcefulness", "SONARA forcefulness component of the aggression analysis."),
    feature("aggression_harshness", "Harshness", "SONARA harshness component of the aggression analysis."),
    feature("aggression_tension", "Tension", "SONARA tension component of the aggression analysis."),
    feature("aggression_rhythm", "Rhythm", "SONARA rhythmic component of the aggression analysis."),
  ],
},
```

- [x] **Step 4: Run the focused test and verify GREEN**

Run from `frontend/`:

```powershell
node --test tests/metadataReference.test.mjs
```

Expected: all tests in `metadataReference.test.mjs` pass.

- [x] **Step 5: Run strict frontend verification**

Run from `frontend/`:

```powershell
npm run typecheck
npm run build
```

Expected: both commands exit with code `0`.

- [x] **Step 6: Inspect the scoped diff**

Run:

```powershell
git diff --check -- frontend/src/TrackMetadataDialog.tsx frontend/tests/metadataReference.test.mjs
git diff -- frontend/src/TrackMetadataDialog.tsx frontend/tests/metadataReference.test.mjs
```

Confirm that the diff changes only the requested membership, labels, order, and
focused assertions. Keep these already-dirty feature files unstaged until the
complete SONARA Aggression change is reviewed and committed as one integrated
unit; a UI-only commit would depend on the currently uncommitted `SonaraCore`
type additions.
