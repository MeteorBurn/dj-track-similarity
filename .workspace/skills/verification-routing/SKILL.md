---
name: verification-routing
description: Use before delivering a change in dj-track-similarity to pick the smallest verification pass that covers what the change touched. Covers which pytest selections, frontend checks, script and tool suites, graphify, and docs checks to run, and the scope gates that stop a run from widening.
---

# Verification Routing

`AGENTS.md` at the repository root keeps the "While iterating" half of this
policy, because it applies on every edit. This file carries the end-of-change
pass and the scope gates. If this file and `AGENTS.md` ever disagree,
`AGENTS.md` wins.

## Before delivery, once

Nothing in this list runs by default. Each line runs only when the change
actually touched what the line covers.

- `python -m pytest tests` is the global backend pass: 680 tests, about 40
  seconds. Run it only when the change reaches past one module — a shared
  contract, a persisted schema or migration, `LibraryDatabase`,
  `SimilaritySearch`, `AnalysisJobManager`, the `analysis_models` contracts, a
  broad refactor, or a release.
- A backend change confined to one module or one feature ends at the test files
  owning that module. That focused run is the whole backend pass for it; do not
  widen to `tests/` to feel safe.
- When no file under `src/` changed, do not run `tests/` at all. A frontend,
  docs, script, or tool change is verified in its own area and nowhere else.
- `scripts/tests`, `tools/audio-dedup/tests`, and `tools/rhythm-lab/tests` run
  only when those directories were touched; together they take about 20 seconds.
- Frontend, only when `frontend/` was touched: `npm run typecheck`, `npm test`,
  and `npm run build` before a commit. The three cost about 8 seconds.
- `graphify update .` once after the last source edit, not per edit. It rebuilds
  the whole graph and takes about 30 seconds.
- Docs site: run `npm run check` from `docs/dj-track-similarity/` only for
  maintained docs content or docs tooling changes.
- For behavior changes, exercise the matching surface once: browser for UI, live
  HTTP request for API, CLI invocation for commands, or a minimal import driver
  for library code. Cover one happy path and one relevant failure path.
- Reading the code beats looking at it. Reach the diagnosis by reasoning about
  the source first — for CSS, which rule wins on specificity and source order
  and what that leaves the layout no room to do; for markup, what the DOM
  actually contains. Open a surface to confirm a hypothesis you already hold,
  not to go looking for one.
- When you do open the browser, verify with numbers, not pictures. Measure
  through `javascript_tool` — `getBoundingClientRect`, `scrollWidth` against
  `clientWidth`, `getComputedStyle` — and compare before against after. A
  measurement is reproducible and cheap to re-run; a screenshot has to be
  eyeballed, can disagree with the DOM, and costs a round trip each time.
  Screenshots are for showing the user a result, never for proving one. Click
  by `ref`, never by pixel coordinates read off a screenshot.

## Scope gates

- Instructions/docs only: inspect the scoped diff, run `git diff --check --
  <paths>`, and use targeted `rg` sentinels. Do not run application suites.
- Root pytest collects only `tests/`; the script and tool suites are named
  explicitly or they do not run at all.
- Widen past the focused selection only for a shared contract, migration, broad
  refactor, release, or a focused-test failure whose cause is not yet clear.
- A frontend test must load the module it checks as running code, through
  `ssrLoadModule`, `transpileModule`, or a direct `../src/` import. Asserting on
  source text pins how a component is written instead of what it does.
  `frontend/tests/testsExecuteCode.test.mjs` enforces this and carries the
  shrinking list of files that predate the rule.
- There is no CI workflow in this repository any more. Nothing runs on a clean
  machine unless you run it here.
