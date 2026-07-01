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

test("clap prompt presets provide direct Find and Negative text", () => {
  const { clapPromptPresets } = loadClapPromptModule();

  const preset = clapPromptPresets.find((item) => item.key === "vocals_speech");

  assert.ok(preset);
  assert.match(preset.query, /vocals|speech|human voice/i);
  assert.match(preset.negativeQuery, /instrumental|no vocals/i);
  assert.ok(preset.query.length > 40);
  assert.ok(preset.negativeQuery.length > 30);
});

test("clap prompt presets expose the curated profile order", () => {
  const { clapPromptPresets } = loadClapPromptModule();

  assert.deepEqual(
    JSON.parse(JSON.stringify(clapPromptPresets.map((item) => [item.key, item.label]))),
    [
      ["adaptive_contrast", "Adaptive"],
      ["breaks_broken", "Breaks / Syncopated drums"],
      ["deep_warmup", "Deep Warm-up"],
      ["vocals_speech", "Vocals / Speech"],
      ["instrumental", "Instrumental"],
      ["acoustic_organic", "Acoustic / Organic"],
      ["ambient_drone", "Ambient / Drone"],
    ],
  );
});

test("manual CLAP prompt text becomes one positive and one enabled negative query", () => {
  const { promptQueriesFromText } = loadClapPromptModule();

  const queries = promptQueriesFromText(" acid techno,  rolling bass ", " bright pop, vocals ", true);

  assert.deepEqual([...queries.positiveQueries], ["acid techno, rolling bass"]);
  assert.deepEqual([...queries.negativeQueries], ["bright pop, vocals"]);
});

test("manual CLAP prompt text omits disabled negative prompt text", () => {
  const { promptQueriesFromText } = loadClapPromptModule();

  const queries = promptQueriesFromText(" acid techno,  rolling bass ", " bright pop, vocals ", false);

  assert.deepEqual([...queries.positiveQueries], ["acid techno, rolling bass"]);
  assert.deepEqual([...queries.negativeQueries], []);
});
