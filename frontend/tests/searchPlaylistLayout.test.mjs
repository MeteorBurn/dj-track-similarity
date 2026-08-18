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
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return styles.match(new RegExp(`${escapedSelector}\\s*{([\\s\\S]*?)}`))?.[1] || "";
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

test("primary search tabs expose the seven maintained workflows with roving ARIA relationships", () => {
  assert.match(panelSource, /primarySearchTabs\.map/);
  assert.match(panelSource, /id=\{`search-tab-\$\{tab\}`\}/);
  assert.match(panelSource, /aria-controls=\{`search-panel-\$\{tab\}`\}/);
  assert.match(panelSource, /tabIndex=\{activeSearchTab === tab \? 0 : -1\}/);
  assert.match(panelSource, /onKeyDown=\{handlePrimaryTabKeyDown\}/);
  assert.match(panelSource, /muq: \{ label: "MUQ"/);
  assert.match(panelSource, /mulan: \{ label: "MULAN"/);
});

test("TEXT tab keeps results from both text embedding models visible", () => {
  assert.match(panelSource, /clap: \{ label: "TEXT", title: "TEXT text search \(CLAP or MuQ-MuLan\)" \}/);
  assert.match(
    appSource,
    /commitGenericSearchResults\(ticket, "clap", value\)/
  );
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

test("Left Right Home End navigation wraps across maintained search tabs", async () => {
  const { primarySearchTabs, tabAfterKey } = await loadSearchSurfaceState();

  assert.deepEqual(primarySearchTabs, ["lab", "sonara", "mert", "muq", "mulan", "clap", "class"]);
  assert.equal(tabAfterKey(primarySearchTabs, "lab", "ArrowLeft"), "class");
  assert.equal(tabAfterKey(primarySearchTabs, "lab", "ArrowRight"), "sonara");
  assert.equal(tabAfterKey(primarySearchTabs, "muq", "Home"), "lab");
  assert.equal(tabAfterKey(primarySearchTabs, "muq", "ArrowRight"), "mulan");
  assert.equal(tabAfterKey(primarySearchTabs, "muq", "End"), "class");
});
