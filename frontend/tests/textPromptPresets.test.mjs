import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));

function loadTextPromptModule() {
  const source = readFileSync(join(srcDir, "textPromptPresets.ts"), "utf8");
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

test("every preset belongs to a declared axis and carries a unique key", () => {
  const { textPromptAxes, textPromptPresets } = loadTextPromptModule();

  const axisKeys = new Set(textPromptAxes.map((axis) => axis.key));
  const seen = new Set();
  for (const preset of textPromptPresets) {
    assert.ok(axisKeys.has(preset.axis), `${preset.key} has unknown axis ${preset.axis}`);
    assert.ok(!seen.has(preset.key), `duplicate preset key ${preset.key}`);
    seen.add(preset.key);
    assert.ok(preset.label.length > 0);
    assert.ok(preset.hint.length > 0);
  }
  assert.ok(textPromptPresets.length >= 100, `vocabulary shrank to ${textPromptPresets.length}`);
  for (const axis of textPromptAxes) {
    const onAxis = textPromptPresets.filter((preset) => preset.axis === axis.key);
    assert.ok(onAxis.length >= 3, `axis ${axis.key} has only ${onAxis.length} labels`);
  }
  assert.deepEqual(
    [...textPromptAxes.map((axis) => axis.key)],
    ["groove", "low", "texture", "harmony", "voice", "instruments", "space", "energy", "style"],
  );
});

test("an axis only names a model where the measurement can carry the claim", () => {
  const { textPromptAxes } = loadTextPromptModule();

  const named = Object.fromEntries(
    textPromptAxes.filter((axis) => axis.model).map((axis) => [axis.key, axis.model]),
  );

  // Measured by the share of the reference in the first 100 rows. Space has no
  // reference at all, low has one label, and harmony's two models sit 0.017
  // apart, so none of the three may claim a winner.
  assert.deepEqual(named, {
    groove: "mulan",
    texture: "clap",
    voice: "mulan",
    instruments: "clap",
    energy: "clap",
    style: "mulan",
  });
  for (const axis of textPromptAxes) {
    if (!axis.model) continue;
    assert.ok(["clap", "mulan"].includes(axis.model), `${axis.key} names an unknown model`);
  }
});

test("a label overrides its axis only where its own cross-check inverted", () => {
  const { textPromptPresets, modelForPreset } = loadTextPromptModule();

  const overrides = textPromptPresets
    .filter((preset) => preset.model)
    .map((preset) => [preset.key, preset.model]);

  assert.deepEqual(Object.fromEntries(overrides), {
    "texture/clean": "mulan",
    "texture/glassy": "mulan",
    "instruments/steel-drum": "mulan",
  });
  // The override has to actually win over the axis, or it is decoration.
  assert.equal(modelForPreset("texture/glassy"), "mulan");
  assert.equal(modelForPreset("texture/lo-fi"), "clap");
  assert.equal(modelForPreset("instruments/steel-drum"), "mulan");
  assert.equal(modelForPreset("instruments/sitar"), "clap");
});

test("a selection recommends one model, or none when the axes disagree", () => {
  const { recommendedModel } = loadTextPromptModule();

  assert.equal(recommendedModel(["instruments/sitar", "instruments/piano"]), "clap");
  assert.equal(recommendedModel(["style/jungle", "groove/breakbeat"]), "mulan");
  // Fusion was measured and rejected, so a split selection must not pick a side.
  assert.equal(recommendedModel(["instruments/sitar", "style/jungle"]), null);
  // An axis with no measurement neither recommends nor blocks.
  assert.equal(recommendedModel(["space/wide"]), null);
  assert.equal(recommendedModel(["space/wide", "style/jungle"]), "mulan");
  assert.equal(recommendedModel([]), null);
  assert.equal(recommendedModel(["nope/missing"]), null);
});

test("a label without measured reliability carries no invented negatives", () => {
  const { textPromptPresets, resolveNegativeWeight } = loadTextPromptModule();

  const unmeasured = textPromptPresets.filter((preset) => !preset.measured);
  assert.ok(unmeasured.length > 0);
  for (const preset of unmeasured) {
    if (!preset.negative) continue;
    for (const model of ["clap", "mulan"]) {
      assert.ok(
        resolveNegativeWeight(preset.negativeWeight, model) > 0,
        `${preset.key} ships negatives that are never applied`,
      );
    }
  }
});

test("prompt lines stay short enough for the CLAP token ceiling and avoid negation", () => {
  const { textPromptPresets } = loadTextPromptModule();

  for (const preset of textPromptPresets) {
    const banks = [preset.positive, preset.negative].filter(Boolean);
    for (const bank of banks) {
      for (const lines of Object.values(bank)) {
        for (const line of lines) {
          const words = line.split(/\s+/).filter(Boolean);
          assert.ok(
            words.length <= 24,
            `${preset.key} prompt is too long for the 77-token CLAP ceiling: ${line}`,
          );
          assert.match(line, /\.$/, `${preset.key} prompt should read as a caption: ${line}`);
        }
      }
    }
    for (const lines of Object.values(preset.positive)) {
      for (const line of lines) {
        assert.doesNotMatch(
          line,
          /\b(no|not|without)\b/i,
          `${preset.key} positive prompt uses negation, which the text encoders cannot model: ${line}`,
        );
      }
    }
  }
});

test("presets whose negatives were measured as harmful carry no negative bank", () => {
  const { textPromptPresets, resolveNegativeWeight } = loadTextPromptModule();

  for (const preset of textPromptPresets) {
    for (const model of ["clap", "mulan"]) {
      const weight = resolveNegativeWeight(preset.negativeWeight, model);
      assert.ok(weight >= 0 && weight <= 2, `${preset.key} weight out of range`);
      if (weight === 0) {
        assert.equal(preset.negative, undefined, `${preset.key} keeps unused negatives`);
      }
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

test("composing presets merges banks, drops duplicates and keeps the safest weight", () => {
  const { composePromptBanks } = loadTextPromptModule();

  const composed = composePromptBanks(["groove/breakbeat", "voice/vocal-led"], "mulan");

  const positive = composed.positiveText.split("\n");
  assert.ok(positive.includes("A breakbeat track."));
  assert.ok(positive.includes("A vocal music track."));
  assert.equal(new Set(positive).size, positive.length);
  assert.ok(composed.negativeText.split("\n").includes("An instrumental electronic dance track."));
  assert.equal(composed.negativeWeight, 0.45);
});

test("a preset with a zero weight contributes prompts but no negatives", () => {
  const { composePromptBanks } = loadTextPromptModule();

  const composed = composePromptBanks(["style/minimal-deep-tech"], "mulan");

  assert.match(composed.positiveText, /A minimal tech house track\./);
  assert.equal(composed.negativeText, "");
  assert.equal(composed.negativeWeight, null);
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

test("manual prompt text omits disabled negative prompt text", () => {
  const { promptQueriesFromText } = loadTextPromptModule();

  const queries = promptQueriesFromText(" acid techno,  rolling bass ", " bright pop, vocals ", false);

  assert.deepEqual([...queries.positiveQueries], ["acid techno, rolling bass"]);
  assert.deepEqual([...queries.negativeQueries], []);
});
