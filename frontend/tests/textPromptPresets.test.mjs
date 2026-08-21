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
