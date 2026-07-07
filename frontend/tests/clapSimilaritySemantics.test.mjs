import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appSource = readFileSync(fileURLToPath(new URL("../src/App.tsx", import.meta.url)), "utf8");
const panelSource = readFileSync(fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url)), "utf8");
const clapTabSource = readFileSync(fileURLToPath(new URL("../src/ClapSearchTab.tsx", import.meta.url)), "utf8");
const helpSource = readFileSync(fileURLToPath(new URL("../src/helpText.ts", import.meta.url)), "utf8");
const dedupDialogSource = readFileSync(fileURLToPath(new URL("../src/AudioDedupDialog.tsx", import.meta.url)), "utf8");

function tabPanelSource(tabName) {
  const startMarker = `{activeSearchTab === "${tabName}" && (`;
  const start = panelSource.indexOf(startMarker);
  assert.notEqual(start, -1, `${tabName} tab was not found`);
  const nextTab = panelSource.indexOf("{activeSearchTab ===", start + startMarker.length);
  return panelSource.slice(start, nextTab === -1 ? undefined : nextTab);
}

test("CLAP text search uses its own Similarity threshold state", () => {
  assert.match(appSource, /const\s+\[clapMinSimilarity,\s*setClapMinSimilarity\]\s*=\s*useState\(0\)/);
  assert.match(appSource, /min_similarity:\s*clapMinSimilarity/);
  assert.match(clapTabSource, /clapMinSimilarity:\s*number/);
  assert.match(clapTabSource, /onClapMinSimilarityChange:\s*\(value:\s*number\)\s*=>\s*void/);
});

test("CLAP UI keeps the Similarity label but documents text-audio score scale", () => {
  const clapPanel = clapTabSource;

  assert.match(clapPanel, />Similarity<input[^>]+value=\{clapMinSimilarity\}/);
  assert.match(clapPanel, /title=\{clapSimilarityHelp\}/);
  assert.match(helpSource, /clapSimilarity:/);
  assert.match(helpSource, /text-to-audio/i);
  assert.match(helpSource, /0\.35-0\.55/);
});

test("CLAP tab extraction preserves negative prompt visibility and exact copy", () => {
  assert.match(panelSource, /<ClapSearchTab/);
  assert.match(clapTabSource, /Hard-negative CLAP bank\. Type: multiline text\. One line is one unwanted audible class; presets fill this field directly\./);
  assert.match(clapTabSource, /Apply Negative as hard-negative CLAP queries\. Type: checkbox on\/off\. When disabled, the text stays in the field but is not included in search\./);
  assert.match(clapTabSource, /disabled=\{!clapUseNegativePrompt\}/);
  assert.match(clapTabSource, /Requires stored CLAP embeddings\. Run CLAP analysis first\./);
});

test("SONARA UI keeps the general Similarity threshold state", () => {
  const sonaraPanel = tabPanelSource("sonara");

  assert.match(sonaraPanel, />Similarity<input[^>]+value=\{filters\.minSimilarity\}/);
  assert.match(sonaraPanel, /title=\{helpText\.similarity\}/);
  assert.doesNotMatch(sonaraPanel, /clapMinSimilarity/);
});

test("Audio Dedup explains that its similarity gate is audio-to-audio, not CLAP text search", () => {
  assert.match(dedupDialogSource, /audio-to-audio/i);
  assert.match(dedupDialogSource, /MERT\/MAEST\/CLAP/);
  assert.match(dedupDialogSource, /not the lower CLAP text-search score/i);
});
