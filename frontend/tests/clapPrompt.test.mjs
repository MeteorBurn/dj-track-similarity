import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));

function loadClapPromptModule() {
  const source = readFileSync(join(srcDir, "clapPrompt.ts"), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports, console });
  return module.exports;
}

test("clap prompt presets provide direct Find and Avoid text", () => {
  const { clapPromptPresets } = loadClapPromptModule();

  const preset = clapPromptPresets.find((item) => item.key === "vocals_speech");

  assert.ok(preset);
  assert.match(preset.query, /vocals|speech|human voice/i);
  assert.match(preset.avoidQuery, /instrumental|no vocals/i);
  assert.ok(preset.query.length > 40);
  assert.ok(preset.avoidQuery.length > 30);
});

test("manual CLAP prompt text becomes one positive and one negative query", () => {
  const { promptQueriesFromText } = loadClapPromptModule();

  const queries = promptQueriesFromText(" acid techno,  rolling bass ", " bright pop, vocals ");

  assert.deepEqual([...queries.positiveQueries], ["acid techno, rolling bass"]);
  assert.deepEqual([...queries.negativeQueries], ["bright pop, vocals"]);
});
