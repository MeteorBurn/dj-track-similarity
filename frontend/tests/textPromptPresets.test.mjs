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

test("the default negative weight tracks the server constant", () => {
  const { defaultNegativeWeight, negativeWeightRange } = loadTextPromptModule();
  const searchSource = readFileSync(
    join(srcDir, "..", "..", "src", "dj_track_similarity", "search.py"),
    "utf8",
  );

  // The slider shows a number before the request is sent, so a drift between
  // the two constants would show the user a weight the server never applied.
  const declared = searchSource.match(/CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT: Final = ([0-9.]+)/);
  assert.ok(declared, "search.py no longer declares the default negative weight");
  assert.equal(defaultNegativeWeight, Number(declared[1]));

  // TextSearchRequest bounds negative_weight to 0..2; the slider must not
  // offer a value the API rejects.
  assert.equal(negativeWeightRange.min, 0);
  assert.equal(negativeWeightRange.max, 2);
  assert.ok(negativeWeightRange.step > 0);
});

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
  // The set of axes is the contract; the order they are rendered in is not, and
  // it is expected to move as the picker is arranged.
  assert.deepEqual(
    [...textPromptAxes.map((axis) => axis.key)].sort(),
    [
      "abstract", "bass", "energy", "field-fx", "function", "groove",
      "instruments", "mood", "percussion", "rhythm", "space", "style",
      "synths", "texture", "timbre", "voice",
    ],
  );
});

test("every axis is drawn under a declared category", () => {
  const { textPromptAxes, textPromptCategories } = loadTextPromptModule();

  // A category is a divider in the picker and nothing else: it never reaches a
  // bank, a request or a score. The one thing worth pinning is that no axis can
  // point at a group that does not exist, which would leave it unrendered.
  const categoryKeys = new Set(textPromptCategories.map((category) => category.key));
  assert.ok(categoryKeys.size > 0);
  for (const axis of textPromptAxes) {
    assert.ok(
      categoryKeys.has(axis.category),
      `axis ${axis.key} names unknown category ${axis.category}`,
    );
  }
  for (const category of textPromptCategories) {
    assert.ok(
      textPromptAxes.some((axis) => axis.category === category.key),
      `category ${category.key} holds no axis`,
    );
    assert.ok(category.label.length > 0);
  }
});

test("the vocabulary declares no model until the comparison fills it in", () => {
  const { textPromptAxes, textPromptPresets, modelForPreset, modelAdvice } = loadTextPromptModule();

  // Which model ranks a label best is not a claim the vocabulary may make on its
  // own. The earlier tags came from an axis average over references that could
  // not tell an axis's labels apart, and the two models' own papers cannot
  // settle it either: the released MuQ-MuLan checkpoint documents no training
  // text at all. The assignment is now made by running both models against the
  // same bank and recording which results the listener kept, and that
  // measurement is what may write these fields.
  // The module runs in its own realm, so its arrays fail a strict deep compare
  // against a literal written here; count instead.
  assert.equal(textPromptAxes.filter((axis) => axis.model).length, 0);
  assert.equal(textPromptPresets.filter((preset) => preset.model).length, 0);
  assert.equal(modelForPreset("rhythm/breakbeat"), undefined);
  assert.equal(modelForPreset("style/jungle"), undefined);
  assert.equal(modelForPreset("nope/missing"), undefined);

  // Rank fusion was measured and rejected, so a selection may never be answered
  // by mixing the two. With nothing declared, every selection is honestly
  // unmeasured rather than silently pointed at a default.
  const advice = (keys) => ({ ...modelAdvice(keys) });
  assert.deepEqual(advice([]), { kind: "unmeasured" });
  assert.deepEqual(advice(["rhythm/breakbeat"]), { kind: "unmeasured" });
  assert.deepEqual(advice(["texture/lo-fi", "style/jungle"]), { kind: "unmeasured" });
  assert.deepEqual(advice(["nope/missing"]), { kind: "unmeasured" });
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

test("every preset bank holds the same four prompts", () => {
  const { textPromptPresets, resolvePromptVariants } = loadTextPromptModule();

  // The benchmark measured an ensemble of three to five short captions as one
  // of the two stable forms, while a bank of one or two behaves like the single
  // caption that ranged from 0.955 to 0.495 on wording alone. Equal length also
  // keeps one preset comparable with another when their reliability is measured.
  for (const preset of textPromptPresets) {
    for (const model of ["clap", "mulan"]) {
      assert.equal(
        resolvePromptVariants(preset.positive, model).length,
        4,
        `${preset.key} does not carry four positive prompts`,
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

  const composed = composePromptBanks(["rhythm/breakbeat", "voice/vocal-led"], "mulan");

  const positive = composed.positiveText.split("\n");
  assert.ok(positive.includes("breakbeat."));
  assert.ok(positive.includes("vocals."));
  assert.equal(new Set(positive).size, positive.length);
  assert.ok(composed.negativeText.split("\n").includes("instrumental."));
  // Both presets carry 0.5; the merge keeps the safest contributing weight.
  assert.equal(composed.negativeWeight, 0.5);
});

test("a preset with a zero weight contributes prompts but no negatives", () => {
  const { composePromptBanks } = loadTextPromptModule();

  const composed = composePromptBanks(["style/tech-house"], "mulan");

  assert.match(composed.positiveText, /A tech house track\./);
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
