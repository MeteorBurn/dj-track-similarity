import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const helpPath = fileURLToPath(new URL("../src/helpText.ts", import.meta.url));

function loadHelpText() {
  const source = readFileSync(helpPath, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports });
  return module.exports.helpText;
}

test("MuQ help describes current search SET Hybrid Dedup and classifier support", () => {
  const helpText = loadHelpText();

  assert.match(helpText.muqAnalyze, /seed-поиска/);
  assert.match(helpText.muqAnalyze, /SET/);
  assert.match(helpText.muqAnalyze, /Hybrid/);
  assert.match(helpText.muqAnalyze, /Audio Dedup/);
  assert.match(helpText.classifiersAnalyze, /MuQ/);
  assert.match(helpText.classifiersAnalyze, /CLAP/);
  assert.doesNotMatch(helpText.muqAnalyze, /без поиска и SET/);
  assert.doesNotMatch(helpText.classifiersAnalyze, /только .*SONARA, MERT и MAEST/);
});

test("CLAP help keeps text-to-audio separate from stored audio-to-audio evidence", () => {
  const helpText = loadHelpText();

  assert.match(helpText.clapAnalyze, /Text-to-audio/);
  assert.match(helpText.clapAnalyze, /audio-to-audio CLAP evidence/);
  assert.match(helpText.clapSimilarity, /text-to-audio similarity/);
});
