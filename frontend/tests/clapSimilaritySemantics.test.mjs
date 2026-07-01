import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appSource = readFileSync(fileURLToPath(new URL("../src/App.tsx", import.meta.url)), "utf8");
const panelSource = readFileSync(fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url)), "utf8");
const helpSource = readFileSync(fileURLToPath(new URL("../src/helpText.ts", import.meta.url)), "utf8");
const dedupDialogSource = readFileSync(fileURLToPath(new URL("../src/AudioDedupDialog.tsx", import.meta.url)), "utf8");

test("CLAP text search uses its own Similarity threshold state", () => {
  assert.match(appSource, /const\s+\[clapMinSimilarity,\s*setClapMinSimilarity\]\s*=\s*useState\(0\)/);
  assert.match(appSource, /min_similarity:\s*clapMinSimilarity/);
  assert.match(panelSource, /clapMinSimilarity:\s*number/);
  assert.match(panelSource, /onClapMinSimilarityChange:\s*\(value:\s*number\)\s*=>\s*void/);
});

test("CLAP UI keeps the Similarity label but documents text-audio score scale", () => {
  assert.match(panelSource, />Similarity<input[^>]+value=\{clapMinSimilarity\}/);
  assert.match(panelSource, /title=\{helpText\.clapSimilarity\}/);
  assert.match(helpSource, /clapSimilarity:/);
  assert.match(helpSource, /text-to-audio/i);
  assert.match(helpSource, /0\.35-0\.55/);
});

test("Audio Dedup explains that its similarity gate is audio-to-audio, not CLAP text search", () => {
  assert.match(dedupDialogSource, /audio-to-audio/i);
  assert.match(dedupDialogSource, /MERT\/MAEST\/CLAP/);
  assert.match(dedupDialogSource, /not the lower CLAP text-search score/i);
});
