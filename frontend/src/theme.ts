export type ThemeMode = "light" | "dark";

export const themeStorageKey = "dj-track-similarity-theme";

function storedTheme(value: string | null): ThemeMode | null {
  return value === "light" || value === "dark" ? value : null;
}

export function resolveInitialTheme(): ThemeMode {
  if (typeof window === "undefined") return "light";

  try {
    const stored = storedTheme(window.localStorage.getItem(themeStorageKey));
    if (stored) return stored;
  } catch {
    // Browser privacy settings can block storage; fall back to the system theme.
  }

  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: ThemeMode) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = theme;
}
