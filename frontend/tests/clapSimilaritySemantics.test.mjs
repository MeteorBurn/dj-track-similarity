import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appSource = readFileSync(fileURLToPath(new URL("../src/App.tsx", import.meta.url)), "utf8");
const panelSource = readFileSync(fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url)), "utf8");
const clapTabSource = readFileSync(fileURLToPath(new URL("../src/ClapSearchTab.tsx", import.meta.url)), "utf8");
const embeddingTabSource = readFileSync(fileURLToPath(new URL("../src/EmbeddingSearchTab.tsx", import.meta.url)), "utf8");
const dedupDialogSource = readFileSync(fileURLToPath(new URL("../src/AudioDedupDialog.tsx", import.meta.url)), "utf8");

function tabPanelSource(tabName) {
  const startMarker = `{activeSearchTab === "${tabName}" && (`;
  const start = panelSource.indexOf(startMarker);
  assert.notEqual(start, -1, `${tabName} tab was not found`);
  const nextTab = panelSource.indexOf("{activeSearchTab ===", start + startMarker.length);
  return panelSource.slice(start, nextTab === -1 ? undefined : nextTab);
}

test("search tabs do not expose or send a minimum similarity threshold", () => {
  assert.doesNotMatch(appSource, /clapMinSimilarity|filters\.minSimilarity|min_similarity:/);
  assert.doesNotMatch(panelSource, />Similarity<input/);
  assert.doesNotMatch(clapTabSource, />Similarity<input|clapMinSimilarity|clapSimilarityHelp/);
  assert.doesNotMatch(embeddingTabSource, /minSimilarity|similarityHelp|onMinSimilarityChange/);
});

test("CLAP tab extraction preserves negative prompt visibility and exact copy", () => {
  assert.match(panelSource, /<ClapSearchTab/);
  assert.match(clapTabSource, /Hard-negative CLAP bank\. Type: multiline text\. One line is one unwanted audible class; presets fill this field directly\./);
  assert.match(clapTabSource, /Apply Negative as hard-negative CLAP queries\. Type: checkbox on\/off\. When disabled, the text stays in the field but is not included in search\./);
  assert.match(clapTabSource, /disabled=\{!clapUseNegativePrompt\}/);
  assert.match(clapTabSource, /Requires stored CLAP embeddings\. Run CLAP analysis first\./);
});

test("SONARA UI keeps mode and limit without a Similarity threshold", () => {
  const sonaraPanel = tabPanelSource("sonara");

  assert.match(sonaraPanel, />Limit<input[^>]+value=\{filters\.limit\}/);
  assert.doesNotMatch(sonaraPanel, />Similarity<input/);
  assert.doesNotMatch(sonaraPanel, /clapMinSimilarity/);
});

test("Audio Dedup explains that its similarity gate is audio-to-audio, not CLAP text search", () => {
  assert.match(dedupDialogSource, /audio-to-audio/i);
  assert.match(dedupDialogSource, /MERT\/MAEST\/MuQ\/CLAP/);
  assert.match(dedupDialogSource, /not the lower CLAP text-search score/i);
});
