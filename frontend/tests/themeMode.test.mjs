import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src/", import.meta.url));
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const themePath = fileURLToPath(new URL("../src/theme.ts", import.meta.url));

test("theme helper owns persistence and document theme application", () => {
  assert.equal(existsSync(themePath), true);
  const source = readFileSync(themePath, "utf8");

  assert.match(source, /type ThemeMode = "light" \| "dark"/);
  assert.match(source, /dj-track-similarity-theme/);
  assert.match(source, /function resolveInitialTheme/);
  assert.match(source, /localStorage\.getItem/);
  assert.match(source, /matchMedia\??\.\("\(prefers-color-scheme: dark\)"\)/);
  assert.match(source, /function applyTheme/);
  assert.match(source, /documentElement\.dataset\.theme = theme/);
});

test("topbar exposes a persistent dark theme toggle", () => {
  const actionsBlock = appSource.match(/<div className="topbar-actions">([\s\S]*?)<\/div>/)?.[1] || "";

  assert.match(appSource, /theme-toggle-button/);
  assert.match(appSource, /resolveInitialTheme/);
  assert.match(appSource, /applyTheme/);
  assert.match(appSource, /localStorage\.setItem\(themeStorageKey, theme\)/);
  assert.match(actionsBlock, /theme-toggle-button[\s\S]*log-frame-button/);
  assert.match(actionsBlock, /title="Переключить тему"/);
  assert.match(actionsBlock, /aria-label="Переключить тему"/);
  assert.match(actionsBlock, /aria-pressed=\{theme === "dark"\}/);
  assert.match(actionsBlock, /theme === "dark" \? <Sun/);
  assert.match(actionsBlock, /<Moon/);
});

test("stylesheet defines light tokens and dark theme overrides", () => {
  assert.match(styles, /:root\s*{[\s\S]*--app-bg:\s*#f2f4ef/);
  assert.match(styles, /:root\[data-theme="dark"\]\s*{[\s\S]*--app-bg:/);
  assert.match(styles, /color-scheme:\s*dark/);
  assert.match(styles, /background:\s*var\(--app-bg\)/);
  assert.match(styles, /\.theme-toggle-button/);
});
