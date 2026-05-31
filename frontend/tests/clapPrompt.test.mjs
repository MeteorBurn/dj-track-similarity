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

test("clap prompt generator creates Find and Avoid prompts from a preset dictionary", () => {
  const { clapPromptPresets, generateClapPrompt } = loadClapPromptModule();

  const preset = clapPromptPresets.find((item) => item.key === "vocals_speech");
  const generated = generateClapPrompt({ currentText: "", presetKey: "vocals_speech" });

  assert.ok(preset);
  assert.match(generated.query, /vocals|speech/i);
  assert.match(generated.avoidQuery, /instrumental|no vocals/i);
  assert.deepEqual(generated.positiveQueries, preset.positiveQueries);
  assert.deepEqual(generated.negativeQueries, preset.negativeQueries);
});

test("clap prompt generator expands existing user text instead of replacing it", () => {
  const { generateClapPrompt } = loadClapPromptModule();

  const generated = generateClapPrompt({ currentText: "acid techno", presetKey: "peak_time_club" });

  assert.match(generated.query, /^acid techno,/);
  assert.match(generated.query, /club|peak/i);
  assert.ok(generated.negativeQueries.length > 0);
  assert.notEqual(generated.query, "acid techno");
});
