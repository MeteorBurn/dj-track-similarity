# SONARA Clock and Dissonance Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render SONARA duration, intro end, and outro start as unambiguous whole-second clocks (`m:ss` or `h:mm:ss`), and align Dissonance with SONARA's three-decimal summary format, while preserving raw stored precision.

**Architecture:** Keep SONARA analysis, database values, and API payloads unchanged. Reuse the existing frontend `formatClockPosition` helper and select zero fractional digits only at the three relevant `formatFeatureValue` call sites. Give `dissonance_score` its own three-decimal display branch instead of grouping it with four-decimal spectral and curve statistics.

**Tech Stack:** React, TypeScript, Node.js built-in test runner, Vite

## Global Constraints

- Change only `analyzed_duration_seconds`, `intro_end_seconds`, `outro_start_seconds`, and `dissonance_score` presentation.
- Preserve the existing two-decimal silence-duration display and all other SONARA units.
- Preserve unrelated and previously authorized unstaged frontend changes.
- Do not read from or write to a real project database during tests.
- Do not create an implementation commit automatically because the two target frontend files already contain earlier in-scope unstaged precision changes.

---

## Task 1: Lock the expected clock and Dissonance behavior with a failing test

**Files:**

- Modify: `frontend/tests/metadataReference.test.mjs`
- Test: `frontend/tests/metadataReference.test.mjs`

- [x] Add a focused test that sends raw seconds through `sonaraFeatures` and checks:

```js
assert.equal(inspected.get("analyzed_duration_seconds").value, "9:44");
assert.equal(common.get("intro_end_seconds").value, "0:18");
assert.equal(common.get("outro_start_seconds").value, "3:19");
assert.equal(hour.get("analyzed_duration_seconds").value, "1:02:03");
assert.equal(carry.get("analyzed_duration_seconds").value, "1:00");
```

- [x] Add the inspected track's structural offsets as regression evidence:

```js
assert.equal(inspected.get("intro_end_seconds").value, "0:01");
assert.equal(inspected.get("outro_start_seconds").value, "9:20");
```

- [x] Update existing assertions for the three clock fields so they expect no fractional suffix.

- [x] Update the existing Dissonance assertion to match SONARA's `TrackAnalysis` summary formatter:

```js
assert.equal(features.get("dissonance_score").value, "0.018");
```

- [x] Run the focused test and confirm it fails because the production call sites still request one or two decimal places:

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity\frontend'
node --test tests/metadataReference.test.mjs
```

Expected failure examples: actual `9:44.42`, `0:18.0`, or `3:19.0` versus whole-second expectations, plus actual `0.0182` versus SONARA's three-decimal `0.018`.

## Task 2: Select whole-second clocks and three-decimal Dissonance

**Files:**

- Modify: `frontend/src/TrackMetadataDialog.tsx`
- Test: `frontend/tests/metadataReference.test.mjs`

- [x] Change the analyzed duration call from two fractional digits to zero:

```ts
if (key === "analyzed_duration_seconds") return formatClockPosition(value, 0);
```

- [x] Change intro and outro calls from one fractional digit to zero:

```ts
if (key === "intro_end_seconds" || key === "outro_start_seconds") {
  return formatClockPosition(value, 0);
}
```

- [x] Keep `formatClockPosition` generic so its existing rounding and hour handling remain centralized.

- [x] Give Dissonance its upstream display precision without changing its raw value:

```ts
if (key === "dissonance_score") return value.toFixed(3);
```

- [x] Leave `energy_curve_stddev`, `spectral_flatness`, and `zero_crossing_rate` on their existing four-decimal branch.

- [x] Run the focused test and confirm all clock and neighboring unit assertions pass:

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity\frontend'
node --test tests/metadataReference.test.mjs
```

## Task 3: Verify type safety, production build, and scoped diff

**Files:**

- Verify: `frontend/src/TrackMetadataDialog.tsx`
- Verify: `frontend/tests/metadataReference.test.mjs`
- Verify: `docs/superpowers/specs/2026-07-30-sonara-time-format-design.md`
- Verify: `docs/superpowers/plans/2026-07-30-sonara-time-format.md`

- [x] Run strict TypeScript checking:

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity\frontend'
npm run typecheck
```

- [x] Run the Vite production build:

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity\frontend'
npm run build
```

- [x] Inspect the scoped diff and whitespace errors:

```powershell
Set-Location -LiteralPath 'C:\projects\dj-track-similarity'
git diff --check -- frontend/src/TrackMetadataDialog.tsx frontend/tests/metadataReference.test.mjs docs/superpowers/plans/2026-07-30-sonara-time-format.md
git diff -- frontend/src/TrackMetadataDialog.tsx frontend/tests/metadataReference.test.mjs docs/superpowers/plans/2026-07-30-sonara-time-format.md
```

- [x] Confirm no database, backend, API, or SONARA source file changed.
