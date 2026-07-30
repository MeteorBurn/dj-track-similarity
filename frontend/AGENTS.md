# Frontend Notes

React + Vite + TypeScript UI for `dj-track-similarity`. See root `AGENTS.md` for cross-repo rules.

## Stack

- Package versions are defined by `package.json` and its lockfile and may be
  updated when requested after compatibility checks.
- Icons: `lucide-react`.
- Node's built-in `node:test` runner (`node --test tests/*.test.mjs`). NOT Vitest. NOT Jest.
- Playwright is installed but no Playwright test files exist yet — do not assume `npm test` exercises a browser.
- No ESLint, no Biome, no Prettier config. Style discipline is enforced by strict TypeScript + review.

## Structure

- `src/main.tsx` — React entry. No router; SPA state lives in `App.tsx`.
- `src/App.tsx` — root stateful shell; composes every panel + dialogs. Split cautiously and keep request/result provenance explicit.
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

## API Alignment

- When backend request or response behavior changes, verify the affected
  frontend types, client calls, consumers, and focused API parity tests.
- API parity tests live in `tests/apiContract.test.mjs` and read `api.ts` directly.
- Closed source types must include every current backend family: MERT/MAEST/MuQ/CLAP for embedding workflows and SONARA where Hybrid/evaluation permits it. Avoid broad `string[]` when the backend uses a `Literal`.
- Generic embedding search sends the explicit `analysis_family`; analysis `device` is not a search field. Reset sends the backend's current family key and consumes the current reset response shape.

## SET, Hybrid, and Result Ownership

- SET Builder (`/api/set-builder/generate`) and Hybrid Preview (`/api/search/hybrid`) are separate workflows. Keep their payloads, weights, loading/error/empty states, request keys, results, diagnostics, and feedback independent.
- If both are shown under the outer SET area, use an accessible nested tablist (`Set Builder` / `Hybrid Preview`) rather than one long merged panel. Switching tabs must not send a request or clear the other workflow.
- `Add preview` may consume only the latest non-stale SET Builder response. SONARA/MERT/MuQ/CLAP search results and Hybrid results must never be treated as a generated SET.
- Late response/error/finally handlers must be request-key guarded; an older request may not replace results or clear loading for a newer request.

## Design System

- Reuse CSS custom properties from `styles.css` (`--app-bg`, `--surface`, `--surface-muted`, `--border`, `--text`, `--accent`, `--warning-*`, `--danger-*`). Do not introduce raw hex/rgb in components — add or reuse a token first (see root `../DESIGN.md`).
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
