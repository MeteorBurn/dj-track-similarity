# Frontend Notes

React + Vite + TypeScript UI for `dj-track-similarity`. See root `AGENTS.md` for cross-repo rules.

## Active Development

- This file is a map of the current frontend, not a permanent component tree,
  API contract, field order, or toolchain lock. The root evolution policy
  applies here.
- Requested UI, state, API, or build changes may reorganize components, routes,
  tabs, payloads, and tests. Update affected layers together; do not retain the
  old shape through hidden branches or speculative compatibility adapters.
- Prefer values and unions derived from shared sources over duplicated model
  lists, field-order assertions, or exhaustive switches that must be edited in
  parallel. Test behavior, accessibility, state ownership, and stale-response
  safety rather than incidental markup order.

## Current Stack

- Package versions are defined by `package.json` and its lockfile and may be
  updated when requested after compatibility checks.
- Icons: `lucide-react`.
- Tests currently use Node's built-in `node:test` runner
  (`node --test tests/*.test.mjs`), not Vitest or Jest. A requested toolchain
  migration is allowed when scripts, tests, dependencies, and docs move
  together.
- Playwright is currently installed without Playwright test files, so confirm
  the active scripts before assuming `npm test` exercises a browser.
- The current checkout has no ESLint, Biome, or Prettier configuration; strict
  TypeScript plus review provide the existing checks. This may evolve.

## Current Structure

- `src/main.tsx` — current React entry. The SPA currently has no router; adding
  or replacing navigation is a normal coordinated change when requested.
- `src/App.tsx` — current root stateful shell. It may be split or reorganized;
  keep request/result provenance explicit during refactors.
- Main panels: `LibraryPanel.tsx`, `TrackPanel.tsx`, `SearchPlaylistPanel.tsx`, `ReferenceComparePanel.tsx`, `ClapSearchTab.tsx`, `TrackMetadataDialog.tsx`.
- Helper dialogs: `AudioDoctorDialog.tsx`, `AudioDedupDialog.tsx`, `dialogs.tsx`.
- State and display helpers: `useLibraryState.ts`, `useSearchPlaylist.ts`, `useActivityLog.ts`, `useConfirmation.ts`, `analysisSelection.ts`, `jobUi.tsx`, `trackDisplay.ts`, `TrackRows.tsx`.
- HTTP types: `api.ts` (TypeScript mirror) + `apiClient.ts` (calls). Keep frontend requests and responses compatible with the active backend routes.
- Styling: `styles.css` (CSS custom properties per root `../DESIGN.md`). No CSS-in-JS.

## Current Compatibility

- `api.ts`, `apiClient.ts`, and active consumers may need coordinated updates
  when backend behavior changes. Use fresh focused checks for the paths being
  adapted.
- MuQ appears in analysis selection, coverage, metadata, and LAB Reference
  Compare; verify each user flow directly when extending its support.
- The frontend may be ported to newer backend behavior whenever requested.
  Update the affected API types, clients, consumers, and focused tests without
  treating the current generation as a compatibility ceiling.

## Current API Alignment

- When backend request or response behavior changes, verify the affected
  frontend types, client calls, consumers, and focused API parity tests.
- API parity tests live in `tests/apiContract.test.mjs` and read `api.ts` directly.
- Closed source types currently mirror the backend families accepted by each
  workflow. Extend, rename, or replace them with backend changes; avoid broad
  `string[]` when the active backend uses a closed schema.
- Generic embedding search sends the explicit `analysis_family`; analysis `device` is not a search field. Reset sends the backend's current family key and consumes the current reset response shape.

## Current SET, Hybrid, and Result Ownership

- SET Builder (`/api/set-builder/generate`) and Hybrid Preview
  (`/api/search/hybrid`) are currently separate workflows. Preserve independent
  request/result ownership unless a task deliberately redesigns their product
  behavior and API together.
- The current outer SET area uses an accessible nested tablist. Its layout and
  labels may change; maintain accessibility and avoid requests or state loss
  caused solely by navigation.
- Under the current ownership model, `Add preview` consumes only the latest
  non-stale SET Builder response; unrelated search and Hybrid results are not a
  generated SET. If those workflows are deliberately merged, define the new
  provenance rules instead of relaxing this guard implicitly.
- Late response/error/finally handlers must be request-key guarded; an older request may not replace results or clear loading for a newer request.

## Current Design System

- The current styling system uses CSS custom properties from `styles.css` (see
  root `../DESIGN.md`). While that system remains active, extend or reuse its
  tokens rather than introducing one-off component colors. A requested design
  system replacement may change this convention coherently.
- All buttons need `type="button"`, an accessible label, and a clear disabled state. No decorative motion.
- Missing model analysis renders as a non-blocking empty state, not a modal or destructive warning.

## TypeScript Rules

- `tsconfig.json` is strict; `npm run typecheck` runs `tsc --noEmit --noUnusedLocals --noUnusedParameters`. Unused imports/params fail the script even when `tsc --noEmit` alone passes.
- Prefer `type` aliases over `interface` for API payloads (mirrors existing `api.ts` style).
- Do not widen back to `any` or use `as unknown as X` casts. Add a discriminated union or narrow via schema.

## Testing

- `frontend/tests/*.test.mjs` — Node runner, assertions via `node:assert/strict`.
- Tests transpile source with `typescript` and often exercise pure logic + rendered DOM strings; they do not spin up a real browser.
- `fetch` is mocked per test.
- Always run `npm run typecheck` separately: source-text/transpile tests can miss a stale union or response type.
- For state, keyboard, and responsive behavior, add a focused component/browser smoke or pure state helper test; regex assertions over TSX/CSS alone are insufficient.

## Build / Dev

- `npm run dev` → Vite on `127.0.0.1:5173`; proxies `/api` and `/media` to `127.0.0.1:8765`.
- `npm run build` → `frontend/dist/`, which the FastAPI app mounts at `/`.
- `frontend/dist/` and `frontend/node_modules/` are gitignored.
