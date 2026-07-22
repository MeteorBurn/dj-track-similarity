# Frontend Notes

React 19 + Vite 7 + TypeScript 5.9 UI for `dj-track-similarity`. See root `AGENTS.md` for cross-repo rules.

## Stack

- React `19.2.3`, React DOM `19.2.3`, Vite `7.2.7`, TypeScript `5.9.3`, `@vitejs/plugin-react` `5.1.1`.
- Icons: `lucide-react`.
- Node's built-in `node:test` runner (`node --test tests/*.test.mjs`). NOT Vitest. NOT Jest.
- Playwright `1.61.1` is installed but no Playwright test files exist yet — do not assume `npm test` exercises a browser.
- No ESLint, no Biome, no Prettier config. Style discipline is enforced by strict TypeScript + review.

## Structure

- `src/main.tsx` — React entry. No router; SPA state lives in `App.tsx`.
- `src/App.tsx` (~1435 lines) — root stateful shell; composes every panel + dialogs. Split cautiously.
- Main panels: `LibraryPanel.tsx`, `TrackPanel.tsx`, `SearchPlaylistPanel.tsx` (~1742 lines), `ReferenceComparePanel.tsx`, `ClapSearchTab.tsx`, `TrackMetadataDialog.tsx`.
- Helper dialogs: `AudioDoctorDialog.tsx`, `AudioDedupDialog.tsx`, `dialogs.tsx`.
- State hooks (`use*`): `useLibraryState.ts`, `useSearchPlaylist.ts`, `useActivityLog.ts`, `useConfirmation.ts`.
- HTTP + contracts: `api.ts` (types) + `apiClient.ts` (calls). `api.ts` is the source of truth for backend request/response shapes.
- Styling: `styles.css` (CSS custom properties per `DESIGN.md`). No CSS-in-JS.

## Contract Alignment

- Every FastAPI schema change in `src/dj_track_similarity/api_schemas.py` (or a new route) requires a matching update in `frontend/src/api.ts` in the same commit.
- Contract tests live in `tests/apiContract.test.mjs` and read `api.ts` directly.

## Design System

- Reuse CSS custom properties from `styles.css` (`--app-bg`, `--surface`, `--surface-muted`, `--border`, `--text`, `--accent`, `--warning-*`, `--danger-*`). Do not introduce raw hex/rgb in components — add or reuse a token first (see `DESIGN.md`).
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
- Current tree: 139 passing tests — keep them green.

## Build / Dev

- `npm run dev` → Vite on `127.0.0.1:5173`; proxies `/api` and `/media` to `127.0.0.1:8765`.
- `npm run build` → `frontend/dist/`, which the FastAPI app mounts at `/`.
- `frontend/dist/` and `frontend/node_modules/` are gitignored.
