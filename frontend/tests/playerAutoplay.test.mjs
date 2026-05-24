import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const trackPanelPath = fileURLToPath(new URL("../src/TrackPanel.tsx", import.meta.url));

test("library preview audio starts after one play-button click", () => {
  const source = readFileSync(trackPanelPath, "utf8");
  const previewAudio = source.match(/<audio\b[^>]*src=\{`\/media\/\$\{preview\.id\}`\}[^>]*\/>/)?.[0] || "";

  assert.match(previewAudio, /\bautoPlay\b/);
});
