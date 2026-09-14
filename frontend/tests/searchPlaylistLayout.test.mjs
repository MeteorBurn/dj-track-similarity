import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");
const panelSource = readFileSync(fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url)), "utf8");
const trackPanelSource = readFileSync(fileURLToPath(new URL("../src/TrackPanel.tsx", import.meta.url)), "utf8");

function loadSearchSurfaceState() {
  const sourcePath = new URL("../src/searchSurfaceState.ts", import.meta.url);
  const compiled = ts.transpileModule(readFileSync(sourcePath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports });
  return module.exports;
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

test("seed results share SIMILARITY while preserving source and request identity", () => {
  const {
    genericSearchResultIsCurrent,
    searchTabForResultOrigin,
  } = loadSearchSurfaceState();

  assert.equal(searchTabForResultOrigin("sonara"), "similarity");
  assert.equal(searchTabForResultOrigin("maest"), "similarity");
  assert.equal(searchTabForResultOrigin("mulan"), "similarity");
  assert.equal(searchTabForResultOrigin("text"), "text");
  assert.equal(genericSearchResultIsCurrent("similarity", "muq", "key", "key"), true);
  assert.equal(genericSearchResultIsCurrent("text", "muq", "key", "key"), false);
  assert.equal(genericSearchResultIsCurrent("similarity", "muq", "stale", "key"), false);
  assert.equal(genericSearchResultIsCurrent("similarity", "sonara", "key", "key"), true);
  assert.equal(genericSearchResultIsCurrent("text", "sonara", "key", "key"), false);
  assert.equal(genericSearchResultIsCurrent("similarity", "sonara", "stale", "key"), false);
});

test("Left Right Home End navigation wraps across tabs", () => {
  const { tabAfterKey } = loadSearchSurfaceState();
  const tabs = ["first", "middle", "last"];

  assert.equal(tabAfterKey(tabs, "first", "ArrowLeft"), "last");
  assert.equal(tabAfterKey(tabs, "last", "ArrowRight"), "first");
  assert.equal(tabAfterKey(tabs, "middle", "ArrowLeft"), "first");
  assert.equal(tabAfterKey(tabs, "middle", "ArrowRight"), "last");
  assert.equal(tabAfterKey(tabs, "middle", "Home"), "first");
  assert.equal(tabAfterKey(tabs, "middle", "End"), "last");
});
