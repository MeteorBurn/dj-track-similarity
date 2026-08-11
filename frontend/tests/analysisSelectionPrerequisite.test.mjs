import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

async function loadAnalysisSelection() {
  const sourcePath = new URL("../src/analysisSelection.ts", import.meta.url);
  const tempDir = mkdtempSync(join(tmpdir(), "analysis-selection-"));
  const modulePath = join(tempDir, "analysisSelection.cjs");
  const compiled = ts.transpileModule(readFileSync(sourcePath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  writeFileSync(modulePath, compiled, "utf8");
  return import(pathToFileURL(modulePath));
}

test("ML requires existing SONARA unless SONARA is selected", async () => {
  const { analysisStartBlockedByMissingSonara } = await loadAnalysisSelection();

  assert.equal(analysisStartBlockedByMissingSonara(["mert"], 0), true);
  assert.equal(
    analysisStartBlockedByMissingSonara(["sonara", "maest"], 0),
    false,
  );
  assert.equal(analysisStartBlockedByMissingSonara(["mert"], 1), false);
  assert.equal(analysisStartBlockedByMissingSonara(["sonara"], 0), false);
});
