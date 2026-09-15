import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

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
