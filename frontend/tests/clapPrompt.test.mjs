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

test("clap prompt presets provide multiline positive and hard-negative banks", () => {
  const { clapPromptPresets } = loadClapPromptModule();

  const preset = clapPromptPresets.find((item) => item.key === "instrumental");

  assert.ok(preset);
  const positiveLines = preset.query.split("\n").filter(Boolean);
  const negativeLines = preset.negativeQuery.split("\n").filter(Boolean);

  assert.equal(positiveLines.length, 5);
  assert.equal(negativeLines.length, 4);
  assert.match(positiveLines[0], /\.$/);
  assert.match(positiveLines.join("\n"), /This audio is an instrumental electronic dance track\./);
  assert.match(negativeLines.join("\n"), /prominent singing vocals/i);
  assert.doesNotMatch(preset.query, /\bno\b|\bwithout\b|\bnot\b/i);
});

test("clap prompt presets expose the curated profile order", () => {
  const { clapPromptPresets } = loadClapPromptModule();

  assert.deepEqual(
    JSON.parse(JSON.stringify(clapPromptPresets.map((item) => [item.key, item.label]))),
    [
      ["breaks_broken", "Breaks / Syncopated drums"],
      ["deep_warmup", "Deep Warm-up"],
      ["vocals_speech", "Vocals / Speech"],
      ["vocals_music", "Vocals with Music"],
      ["instrumental", "Instrumental"],
      ["acoustic_organic", "Acoustic / Organic"],
      ["ambient_drone", "Ambient / Drone"],
    ],
  );
});

test("CLAP prompt text splits visible multiline banks into query arrays", () => {
  const { promptQueriesFromText } = loadClapPromptModule();

  const queries = promptQueriesFromText(
    " breakbeat.\n\nThis audio is a syncopated drum track. ",
    " This audio is a straight house track.\nThis audio is a vocal pop song. ",
    true,
  );

  assert.deepEqual([...queries.positiveQueries], ["breakbeat.", "This audio is a syncopated drum track."]);
  assert.deepEqual([...queries.negativeQueries], ["This audio is a straight house track.", "This audio is a vocal pop song."]);
});

test("manual CLAP prompt text omits disabled negative prompt text", () => {
  const { promptQueriesFromText } = loadClapPromptModule();

  const queries = promptQueriesFromText(" acid techno,  rolling bass ", " bright pop, vocals ", false);

  assert.deepEqual([...queries.positiveQueries], ["acid techno, rolling bass"]);
  assert.deepEqual([...queries.negativeQueries], []);
});
