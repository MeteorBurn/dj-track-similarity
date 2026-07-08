# Design System

## 1. Product surface

`dj-track-similarity` uses a dense local-workbench interface: fixed-width panels, compact controls, track rows, meters, and diagnostic chips. The UI prioritizes fast comparison and safe local-library operations over decorative presentation.

## 2. Tokens

Use the CSS custom properties in `frontend/src/styles.css` as the source of truth. Core surface tokens are `--app-bg`, `--surface`, `--surface-muted`, `--surface-raised`, `--border`, `--border-soft`, `--text`, `--text-muted`, `--accent`, `--accent-active-bg`, `--warning-*`, and `--danger-*`. Do not introduce raw colors in components; add or reuse a token first.

## 3. Typography

The app uses the existing system sans stack declared on `:root`. UI text is compact: panel titles use the existing `.panel-title` pattern, labels use 12px bold copy, and row content uses inherited body sizing.

## 4. Layout

Panels use bordered rounded surfaces with small gaps. Dense comparison views should use responsive CSS grid with `minmax()` tracks and should preserve internal scrolling rather than expanding the global workspace.

## 5. Components

- `panel`: bordered workbench surface with `.panel-title` header.
- `model-search-tab`: compact tab button for switching search surfaces.
- `result-row`: reusable candidate row with preview, score meter, metadata, seed, like, and playlist actions.
- `diagnostic chip`: small rounded label using muted/accent tokens for status or model metadata.
- `verdict button`: compact action button that records user listening feedback; active/saved state uses accent tokens and error state uses danger tokens.

## 6. States

Disabled controls must use existing disabled button/input styles. Error text uses danger tokens. Missing model analysis should render as a non-blocking empty state, not as a modal or destructive warning.

## 7. Motion and accessibility

No decorative animation. Buttons must have `type="button"`, titles or labels, and clear disabled states. Preserve keyboard access through native controls and existing `ResultRow` behavior.
