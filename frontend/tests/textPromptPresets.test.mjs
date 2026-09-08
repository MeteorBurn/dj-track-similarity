import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));

function loadTextPromptModule(presets) {
  const source = readFileSync(join(srcDir, "textPromptPresets.ts"), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports, console });
  if (presets) module.exports.textPromptPresets.splice(0, module.exports.textPromptPresets.length, ...presets);
  return module.exports;
}

test("preset keys identify nonempty model banks on declared axes", () => {
  const { textPromptAxes, textPromptPresets, presetByKey, resolvePromptVariants } = loadTextPromptModule();

  const axisKeys = new Set(textPromptAxes.map((axis) => axis.key));
  const seen = new Set();
  assert.ok(textPromptPresets.length > 0);
  for (const preset of textPromptPresets) {
    assert.ok(axisKeys.has(preset.axis), `${preset.key} has unknown axis ${preset.axis}`);
    assert.ok(!seen.has(preset.key), `duplicate preset key ${preset.key}`);
    seen.add(preset.key);
    assert.equal(presetByKey(preset.key), preset);
    for (const model of ["clap", "mulan"]) {
      const prompts = resolvePromptVariants(preset.positive, model);
      assert.ok(prompts.length > 0, `${preset.key} has no ${model} bank`);
      assert.ok(prompts.every((line) => typeof line === "string" && line.trim().length > 0));
    }
  }
});

test("model variants fall back to the shared bank", () => {
  const { resolvePromptVariants } = loadTextPromptModule();

  const variants = { shared: ["A shared prompt."], clap: ["A CLAP prompt."] };

  assert.deepEqual([...resolvePromptVariants(variants, "clap")], ["A CLAP prompt."]);
  assert.deepEqual([...resolvePromptVariants(variants, "mulan")], ["A shared prompt."]);
  assert.deepEqual([...resolvePromptVariants(undefined, "mulan")], []);
});

test("composing banks deduplicates prompts and uses the minimum contributing model weight", () => {
  const { composePromptBanks } = loadTextPromptModule([
    { key: "rhythm/a", axis: "rhythm", positive: { shared: ["Shared.", "First."] },
      negative: { shared: ["Opposite."], clap: ["CLAP opposite."] },
      negativeWeight: { clap: 0.8, mulan: 0.2 } },
    { key: "bass/a", axis: "bass", positive: { shared: ["Shared.", "Second."] },
      negative: { shared: ["Opposite.", "Other."] }, negativeWeight: 0.4 },
    { key: "mood/a", axis: "mood", positive: { shared: ["Third."] }, negativeWeight: 0.01 },
  ]);
  for (const model of ["clap", "mulan"]) {
    const composed = composePromptBanks(["rhythm/a", "bass/a", "mood/a", "missing"], model);
    assert.deepEqual(composed.positiveText.split("\n"), ["Shared.", "First.", "Second.", "Third."]);
    assert.deepEqual(composed.negativeText.split("\n"),
      model === "clap" ? ["CLAP opposite.", "Opposite.", "Other."] : ["Opposite.", "Other."]);
    assert.equal(composed.negativeWeight, model === "clap" ? 0.4 : 0.2);
  }
});

test("a zero model weight excludes negatives without excluding positive prompts", () => {
  const { composePromptBanks } = loadTextPromptModule([
    { key: "rhythm/a", axis: "rhythm", positive: { shared: ["Positive."] },
      negative: { shared: ["Negative."] }, negativeWeight: { clap: 0, mulan: 0.3 } },
  ]);
  const composed = composePromptBanks(["rhythm/a"], "clap");
  assert.equal(composed.positiveText, "Positive.");
  assert.equal(composed.negativeText, "");
  assert.equal(composed.negativeWeight, null);
  const mulan = composePromptBanks(["rhythm/a"], "mulan");
  assert.equal(mulan.positiveText, "Positive.");
  assert.equal(mulan.negativeText, "Negative.");
  assert.equal(mulan.negativeWeight, 0.3);
});

test("selecting nothing clears both banks", () => {
  const { composePromptBanks } = loadTextPromptModule();

  const composed = composePromptBanks([], "clap");

  assert.equal(composed.positiveText, "");
  assert.equal(composed.negativeText, "");
  assert.equal(composed.negativeWeight, null);
});

test("prompt text splits visible multiline banks into query arrays", () => {
  const { promptQueriesFromText } = loadTextPromptModule();

  const queries = promptQueriesFromText(
    " A breakbeat track.\n\nA track with broken drums. ",
    " A four-on-the-floor house track.\nA vocal pop song. ",
    true,
  );

  assert.deepEqual([...queries.positiveQueries], [
    "A breakbeat track.",
    "A track with broken drums.",
  ]);
  assert.deepEqual([...queries.negativeQueries], [
    "A four-on-the-floor house track.",
    "A vocal pop song.",
  ]);
});

test("generated bank queries omit disabled negatives", () => {
  const { promptQueriesFromText } = loadTextPromptModule();

  const queries = promptQueriesFromText(" acid techno,  rolling bass ", " bright pop, vocals ", false);

  assert.deepEqual([...queries.positiveQueries], ["acid techno, rolling bass"]);
  assert.deepEqual([...queries.negativeQueries], []);
});
