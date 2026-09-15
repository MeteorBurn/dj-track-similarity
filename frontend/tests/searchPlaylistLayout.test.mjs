import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

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
    isSeedEmbeddingFamily,
  } = loadSearchSurfaceState();

  assert.equal(searchTabForResultOrigin("sonara"), "similarity");
  assert.equal(searchTabForResultOrigin("maest"), "similarity");
  assert.equal(searchTabForResultOrigin("mulan"), "similarity");
  assert.equal(isSeedEmbeddingFamily("mert_v2"), true);
  assert.equal(searchTabForResultOrigin("mert_v2"), "similarity");
  assert.equal(genericSearchResultIsCurrent("similarity", "mert_v2", "key", "key"), true);
  assert.equal(genericSearchResultIsCurrent("similarity", "mert_v2", "old-catalog", "key"), false);
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
