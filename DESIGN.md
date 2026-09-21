# Design System

## 1. Product surface

`dj-track-similarity` uses a dense local-workbench interface: bounded panels, compact controls, track rows, meters, and chips. The UI prioritizes fast comparison and safe local-library operations over decorative presentation. This document describes the main application in `frontend/src/`. Rhythm Lab has a separate stylesheet, `tools/rhythm-lab/rhythm_lab/static/styles.css`, with its own tokens.

## 2. Tokens and themes

Use the CSS custom properties in `frontend/src/styles.css` as the source of truth. The app has a light theme on `:root` and a dark theme on `:root[data-theme="dark"]`. `theme.ts` resolves the initial theme from `localStorage` (`dj-track-similarity-theme`), falls back to `prefers-color-scheme`, and sets `data-theme` on `<html>`; `App.tsx` saves each change, and the top-bar theme button toggles it. Tokens are set in several `:root` and `:root[data-theme="dark"]` blocks, and later blocks override earlier ones, so confirm a resolved value with computed styles rather than the first definition. `--workbench-*` and `--player-*` are defined on `:root` only and shared by both themes.

Token families:

- surfaces and borders: `--app-bg`, `--surface`, `--surface-muted`, `--surface-subtle`, `--surface-raised`, `--surface-disabled`, `--surface-disabled-border`, `--border`, `--border-soft`, `--border-strong`, `--border-muted`, `--border-dashed`;
- text: `--app-text`, `--text`, `--text-strong`, `--text-muted`, `--text-soft`, `--text-faint`, `--text-disabled`, `--text-chip`, `--text-track`, `--body-copy`, `--meta-label`, `--inverse-text`;
- emphasis and status: `--accent*`, `--warning-*`, `--danger-*`, `--notice-*`, `--blue-*`, `--pink-*`, `--modifier-accent`, `--process-idle`, `--focus-ring`, `--brand-*`;
- controls and dialogs: `--button-*`, `--workbench-radius`, `--workbench-control-height`, `--workbench-dialog-radius`, `--workbench-dialog-shadow`, `--font-size-compact-selector`;
- depth: `--shadow-*`, `--overlay*`, `--inset-highlight`, `--tooltip-bg`;
- text-preset axes: `--preset-*`;
- single-purpose: `--scan-import-format-off-*`, `--player-edge`, `--player-glow-*`.

Do not introduce raw colors in components; add or reuse a token first, and check the result in both themes.

## 3. Typography

`:root` declares `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`. Inter is not bundled, so the system fonts apply where it is not installed. UI text is compact: panel titles (`.panel-title h2`) are 16px/600 and dialog titles 17px/600; track titles are 13px (600 in library rows, bold in result rows); row metadata is 11px; control labels are 12px in panels and 13px/600 in the scan-import, SONARA, and ML settings dialogs. Row indexes, scores, BPM, KEY and duration cells, counters, and the player time readout use `font-variant-numeric: tabular-nums`. Dense mobile selectors may use `--font-size-compact-selector` when four-column controls must preserve complete labels without overlap.

## 4. Layout

- **Top bar:** brand, workspace navigation (`.workbench-nav`), and actions such as the theme toggle. The navigation buttons DISCOVER, ANALYZE, LIBRARY, SEARCH, and EXPORT expose their state with `aria-pressed`: DISCOVER opens all three panels, ANALYZE, LIBRARY, and SEARCH open one each, and EXPORT switches to a separate export workspace.
- **Workspace:** a flexible three-column grid, `minmax(280px, 28fr) minmax(400px, 41fr) minmax(330px, 30fr)`, narrowed to `minmax(270px, 28fr) minmax(360px, 41fr) minmax(310px, 31fr)` at 1450px and below. It holds the numbered panels (1 database and analysis, 2 library, 3 search). A collapsed panel becomes a 56px rail (`.panel-rail-label`), and the open panels share the rest equally. A collapse made with the panel's own button or rail persists in `localStorage`; a navigation view changes the panels without saving. Above 1050px the workspace height is bounded and panels keep internal scrolling rather than expanding the page; at 1050px and below the workspace becomes one column and each panel is capped at 700px.
- **Player dock:** an always-present transport in normal flow below the workspace, also in EXPORT. At 1050px and below it becomes `position: sticky` at the bottom and hides BPM, KEY, and volume; at 600px and below it also hides the artwork.
- **Dense views:** use CSS grid with `minmax()` tracks and container queries (`library-tracks`, `results`, `search-workflow`, `library-tools`, `lab-model`) as well as viewport breakpoints.

## 5. Components

- `panel`: bordered workbench surface with a `.panel-title` header.
- `stage-card`: DATABASE, SONARA, and ML cards in the first panel; the checked stages start from the single `stage-start-button` at the foot of the panel.
- `model-search-tab`: compact tab button for switching search surfaces.
- `result-row` (`ResultRow` in `TrackRows.tsx`): candidate row with preview, title with an optional reason chip, score `<meter>` and value, and like, metadata, seed, and playlist actions, plus relevance verdicts when the consumer passes `onFeedback`. With `onSelect`, the row is a `role="button"` that answers Enter and Space. Library rows (`TrackList`, `.track-row`) show duration, BPM, and KEY and carry preview, like, metadata, seed, and playlist actions.
- `icon-button`: icon-only control using `lucide-react` icons; its `title` names the action. It is square by default and wider with a caption in the library tools row.
- chips: small rounded labels on muted, accent, or status tokens (`text-preset-chip`, `result-reason-chip`, `dedup-chip` and its `dedup-chip-*` variants, `scan-import-format-chip`, `seed-remove-chip`, `sonara-settings-bpm-preset-chip`).
- verdict buttons: result-row relevance buttons (`result-feedback-button`) stay neutral until chosen; "relevant" then uses `--preset-selected-*` and "irrelevant" `--danger-muted-*`. The LAB verdict buttons (`reference-compare-verdict-button`) use `--accent-active-*` when active. Errors appear as text (`.reference-compare-error`), not as a button state.
- dialogs: `role="dialog"` and `aria-modal="true"` over a backdrop, named by `aria-labelledby` (the track metadata dialog uses `aria-label`), with the shared workbench dialog radius and shadow. The scan-import, SONARA, and ML settings dialogs close on Escape unless disabled; the log and Audio Dedup dialogs also close on Escape, Audio Dedup cancelling its own confirmation first. The track metadata dialog and the app-level confirmation have no Escape handler. Confirmations use `ConfirmationDialog` through `useConfirmation`.
- tooltips: a `title` inside `.app-shell` is drawn by the global tooltip layer (`useGlobalTooltip`, `.ui-tooltip`, `role="tooltip"`) on pointer hover and keyboard focus; the layer suppresses the native tooltip while its own is shown.
- `NumberStepper`: bounded integer field with minus and plus buttons, used in the SONARA and ML settings dialogs; the analysis limit and the scan-import dialog repeat its `.stepper` markup.
- player dock (`PlayerDock.tsx`): artwork, track title and file information, play and pause, timeline, repeat, like, BPM and KEY readouts, and volume.

## 6. States

Disabled controls must use existing disabled button/input styles. Error text uses danger tokens. Missing model analysis should render as a non-blocking empty state (`.empty-state` in the search and export panels and the Audio Dedup dialog, `.library-empty-state` in the library panel, `.metadata-empty-state` in the track metadata dialog), not as a modal or destructive warning.

## 7. Motion and accessibility

State changes use short transitions (120–240ms) on background, border, color, or transform, and busy indicators spin. There is no other decorative animation, with one existing exception: the player dock's spectrum edge travels on a 14-second loop (`player-edge-travel`) and holds still under `prefers-reduced-motion: reduce`. Spinners and transitions are not gated by `prefers-reduced-motion`. Every button that does not submit has `type="button"`, a title or label, and a clear disabled state. Preserve keyboard access through native controls and existing `ResultRow` behavior.
