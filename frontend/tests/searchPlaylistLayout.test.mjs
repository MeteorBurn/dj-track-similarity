import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { mkdtempSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");
const panelSource = readFileSync(fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url)), "utf8");
const trackPanelSource = readFileSync(fileURLToPath(new URL("../src/TrackPanel.tsx", import.meta.url)), "utf8");
const appSource = readFileSync(fileURLToPath(new URL("../src/App.tsx", import.meta.url)), "utf8");
const embeddingTabSource = readFileSync(fileURLToPath(new URL("../src/EmbeddingSearchTab.tsx", import.meta.url)), "utf8");

async function loadSearchSurfaceState() {
  const sourcePath = new URL("../src/searchSurfaceState.ts", import.meta.url);
  const tempDir = mkdtempSync(join(tmpdir(), "search-layout-state-"));
  const modulePath = join(tempDir, "searchSurfaceState.cjs");
  const compiled = ts.transpileModule(readFileSync(sourcePath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  writeFileSync(modulePath, compiled, "utf8");
  return import(pathToFileURL(modulePath));
}

function cssRule(selector) {
  for (const [, selectorList, body] of styles.matchAll(/([^{}]+){([^{}]*)}/g)) {
    const selectors = selectorList.split(",").map((item) => item.trim());
    if (selectors.includes(selector)) return body;
  }
  return "";
}

test("set and export is a closed disclosure with 20-track pagination", () => {
  const disclosure = panelSource.match(
    /<details[\s\S]*?className="playlist-export-disclosure"[\s\S]*?<\/details>/
  )?.[0] || "";
  const openingTag = disclosure.match(/^<details[^>]*>/)?.[0] || "";
  const summary = disclosure.match(
    /<summary className="playlist-export-summary"[\s\S]*?<\/summary>/
  )?.[0] || "";
  const disclosureRule = cssRule(".playlist-export-disclosure");
  const listRule = cssRule(".playlist-export-section .playlist-list");
  const pageControlsRule = cssRule(".playlist-page-controls");

  assert.doesNotMatch(openingTag, /\sopen(?:=|\s|>)/);
  assert.match(panelSource, /const \[playlistExportOpen, setPlaylistExportOpen\] = useState\(false\)/);
  assert.match(panelSource, /const playlistPageSize = 20/);
  assert.match(openingTag, /onToggle=\{\(event\) =>/);
  assert.match(disclosure, /setPlaylistExportOpen\(event\.currentTarget\.open\)/);
  assert.match(summary, /Сет и экспорт/);
  assert.match(summary, /panel-counter">\{playlist\.length\}/);
  assert.ok(disclosure.indexOf("playlist-export-summary") < disclosure.indexOf("playlist-export-section"));
  assert.match(disclosure, /\{playlistExportOpen \? \(/);
  assert.match(disclosure, /playlistPageState\.items\.map\(\(track, index\)/);
  assert.match(disclosure, /playlistPageState\.pageStart\}–\{playlistPageState\.pageEnd\} из \{playlistPageState\.total\}/);
  assert.match(disclosure, /playlist-page-previous-button/);
  assert.match(disclosure, /playlist-page-next-button/);
  assert.doesNotMatch(panelSource, /playlistWindowStart|playlistVirtualHeight|playlist-list-virtualized/);
  assert.match(disclosureRule, /flex:\s*0 0 auto/);
  assert.match(disclosureRule, /margin-bottom:\s*2px/);
  assert.match(disclosureRule, /margin-top:\s*auto/);
  assert.match(listRule, /max-height:\s*min\(360px,\s*34vh\)/);
  assert.match(listRule, /overflow-y:\s*auto/);
  assert.match(listRule, /scrollbar-gutter:\s*stable/);
  assert.match(pageControlsRule, /display:\s*flex/);
  assert.match(styles, /\.playlist-export-summary-toggle::before\s*{[\s\S]*?content:\s*"Развернуть"/);
  assert.match(styles, /\.playlist-export-disclosure\[open\] \.playlist-export-summary-toggle::before\s*{[\s\S]*?content:\s*"Свернуть"/);
});

test("library and generic search results render visible track numbering", () => {
  const trackRows = readFileSync(fileURLToPath(new URL("../src/TrackRows.tsx", import.meta.url)), "utf8");

  assert.match(trackRows, /startIndex = 0/);
  assert.match(trackRows, /tracks\.map\(\(track, index\)/);
  assert.match(trackRows, /\{startIndex \+ index \+ 1\}/);
  assert.match(trackRows, /rowIndex != null \? <span className="row-index">\{rowIndex\}<\/span> : null/);
  assert.match(trackPanelSource, /startIndex=\{offset\}/);
  assert.match(panelSource, /rowIndex=\{index \+ 1\}/);
});

test("primary search tabs expose the five maintained workflows with roving ARIA relationships", () => {
  assert.match(panelSource, /primarySearchTabs\.map/);
  assert.match(panelSource, /id=\{`search-tab-\$\{tab\}`\}/);
  assert.match(panelSource, /aria-controls=\{`search-panel-\$\{tab\}`\}/);
  assert.match(panelSource, /tabIndex=\{activeSearchTab === tab \? 0 : -1\}/);
  assert.match(panelSource, /onKeyDown=\{handlePrimaryTabKeyDown\}/);
  assert.match(panelSource, /similarity: \{ label: "SIMILARITY", title: "Seed embedding similarity search \(MAEST, MERT, MuQ, MuQ-MuLan\)" \}/);
});

test("SIMILARITY selects MAEST embeddings and keeps MAEST result provenance", async () => {
  const {
    genericSearchResultIsCurrent,
    searchTabForResultOrigin,
    seedEmbeddingFamilies,
    seedEmbeddingFamilyPresentation
  } = await loadSearchSurfaceState();

  assert.deepEqual([...seedEmbeddingFamilies], ["maest", "mert", "muq", "mulan"]);
  assert.deepEqual(
    seedEmbeddingFamilies.map((family) => seedEmbeddingFamilyPresentation[family].label),
    ["MAEST", "MERT", "MuQ", "MuQ-MuLan"]
  );
  assert.equal(searchTabForResultOrigin("maest"), "similarity");
  assert.equal(searchTabForResultOrigin("mulan"), "similarity");
  assert.equal(searchTabForResultOrigin("text"), "text");
  assert.equal(genericSearchResultIsCurrent("similarity", "muq", "key", "key"), true);
  assert.equal(genericSearchResultIsCurrent("text", "muq", "key", "key"), false);
  assert.equal(genericSearchResultIsCurrent("similarity", "muq", "stale", "key"), false);
  assert.match(panelSource, /searchResultOriginLabel\(genericSearchResultOrigin\)/);
  assert.match(appSource, /seed_embedding_family: seedEmbeddingFamily/);
});

test("PROMPT tab compares the two text models over one bank without merging them", () => {
  // Rank fusion was measured and rejected, so A/B keeps two orders apart and
  // lets the ear decide. Each model reads its own variant of the bank: the
  // vocabulary carries per-model wording because the two towers were trained on
  // different language, so a single shared text would test one of them on prose
  // written for the other. What ships is a model with its own bank.
  assert.match(appSource, /textCompareModels/);
  assert.match(appSource, /\["mulan", "clap"\]/);
  assert.match(appSource, /const families: TextEmbeddingFamily\[\]/);
  assert.match(appSource, /composePromptBanks\(selectedPresetKeys, family\)/);
  // A hand-edited field is the question being asked, so it goes to both as is.
  assert.match(appSource, /bankIsUnedited/);
  // The first column also feeds the shared result list, so preview and the set
  // keep working off one source in both modes.
  assert.match(appSource, /commitGenericSearchResults\(ticket, "text", columns\[0\]\.results\)/);
  // Each column carries its own verdicts, because the same track sits in both
  // and the two answers may honestly differ.
  assert.match(panelSource, /className="generic-search-results generic-search-compare"/);
  assert.match(panelSource, /feedbackVerdict=\{column\.verdicts\[track\.track_uuid\] \?\? null\}/);
});

test("SONARA tab can add an unselected random SONARA-ready seed", () => {
  const addRandomTrackPosition = panelSource.indexOf("Add Random Track");
  const filtersPosition = panelSource.indexOf("sonara-search-filter-grid");
  const searchPosition = panelSource.indexOf("SONARA search");

  assert.match(panelSource, /handleAddRandomSonaraTrack/);
  assert.match(panelSource, /Add Random Track/);
  assert.match(panelSource, /Добавить случайный SONARA-ready трек из базы в seed/);
  assert.ok(addRandomTrackPosition < filtersPosition);
  assert.ok(filtersPosition < searchPosition);
  assert.match(cssRule(".sonara-random-track-action"), /justify-content:\s*flex-start/);
  assert.match(cssRule(".sonara-random-track-button"), /min-height:\s*28px/);
});

test("SIMILARITY tab can add a random seed of the selected embedding family", () => {
  const addRandomTrackPosition = embeddingTabSource.indexOf("Add Random Track");
  const filtersPosition = embeddingTabSource.indexOf("embedding-search-grid");
  const searchPosition = embeddingTabSource.indexOf("embedding-search-button");

  assert.match(panelSource, /onAddRandomTrack=\{handleAddRandomEmbeddingTrack\}/);
  assert.match(appSource, /api\.randomEmbeddingTrack\(\{\s*analysis_family: seedEmbeddingFamily,/);
  // The seed count gates the search button, never the button that adds a seed.
  assert.match(panelSource, /randomTrackBusy=\{busy\}/);
  assert.match(embeddingTabSource, /disabled=\{randomTrackBusy \|\| Boolean\(missingReason\)\}/);
  assert.match(embeddingTabSource, /\{pending \? "Searching\.\.\." : "Search"\}/);
  assert.ok(addRandomTrackPosition < filtersPosition);
  assert.ok(filtersPosition < searchPosition);
  assert.match(cssRule(".embedding-random-track-action"), /justify-content:\s*flex-start/);
  assert.match(cssRule(".embedding-random-track-button"), /min-height:\s*28px/);
});

test("Left Right Home End navigation wraps across maintained search tabs", async () => {
  const { primarySearchTabs, tabAfterKey } = await loadSearchSurfaceState();

  assert.deepEqual(primarySearchTabs, ["lab", "sonara", "similarity", "text", "class"]);
  assert.equal(tabAfterKey(primarySearchTabs, "lab", "ArrowLeft"), "class");
  assert.equal(tabAfterKey(primarySearchTabs, "lab", "ArrowRight"), "sonara");
  assert.equal(tabAfterKey(primarySearchTabs, "similarity", "Home"), "lab");
  assert.equal(tabAfterKey(primarySearchTabs, "similarity", "ArrowRight"), "text");
  assert.equal(tabAfterKey(primarySearchTabs, "similarity", "End"), "class");
});
