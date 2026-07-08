import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
const panelPath = fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url));
const helpTextPath = fileURLToPath(new URL("../src/helpText.ts", import.meta.url));

test("SONARA tab exposes backend search modes instead of forcing custom mode", () => {
  const appSource = readFileSync(appPath, "utf8");
  const panelSource = readFileSync(panelPath, "utf8");

  assert.match(panelSource, /sonaraModeOptions/);
  assert.match(panelSource, /value=\{filters\.sonaraMode\}/);
  assert.match(appSource, /mode:\s*filters\.sonaraMode/);
  assert.doesNotMatch(appSource, /mode:\s*"custom"/);
});

test("SONARA custom modifiers include vocalness with help text", () => {
  const appSource = readFileSync(appPath, "utf8");
  const panelSource = readFileSync(panelPath, "utf8");
  const helpSource = readFileSync(helpTextPath, "utf8");

  assert.match(appSource, /vocalness:\s*0/);
  assert.match(panelSource, /key:\s*"vocalness", label:\s*"Vocal"/);
  assert.match(helpSource, /sonaraModifierVocalness:/);
});
