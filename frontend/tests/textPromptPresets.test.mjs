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
      "abstract", "bass", "complexity", "density", "energy", "function",
      "groove", "harmony", "instruments", "mood", "movement", "organic",
      "percussion", "rhythm", "space", "style", "synths", "tension",
      "texture", "timbre", "voice",
    ],
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
  //
  // Instruments and voice are withdrawn for a different reason: an axis average
  // can only choose a model for its labels if its references can tell those
  // labels apart. All 21 instrument labels were scored against one number,
  // SONARA acousticness, and all 11 voice labels against one, vocal
  // probability. Those averages measure "sounds live" and "has a voice", not
  // which instrument or which kind of voice was found.
  assert.deepEqual(named, {
    rhythm: "mulan",
    texture: "clap",
    style: "mulan",
  });
  for (const axis of textPromptAxes) {
    if (!axis.model) continue;
    assert.ok(["clap", "mulan"].includes(axis.model), `${axis.key} names an unknown model`);
  }
});

test("a label overrides its axis only where its own evidence outranks the axis", () => {
  const { textPromptPresets, modelForPreset } = loadTextPromptModule();

  const overrides = textPromptPresets
    .filter((preset) => preset.model)
    .map((preset) => [preset.key, preset.model]);

  assert.deepEqual(Object.fromEntries(overrides), {
    "texture/clean": "mulan",
    "timbre/glassy": "mulan",
    "harmony/jazz": "mulan",
    "abstract/experimental": "clap",
  });
  // CLAP ranks jazz against chord changes per second the wrong way round, and
  // the harmony axis names no model, so nothing else would have warned.
  assert.equal(modelForPreset("harmony/jazz"), "mulan");
  assert.equal(modelForPreset("harmony/drone"), undefined);
  // The override has to actually win over the axis, or it is decoration.
  assert.equal(modelForPreset("timbre/glassy"), "mulan");
  assert.equal(modelForPreset("texture/lo-fi"), "clap");
  // On volumes.sqlite its hand labels put the two models 0.007 apart, so the
  // former CLAP override is withdrawn and the axis still names no model.
  assert.equal(modelForPreset("voice/vocal-led"), undefined);
  // No reference can say which model finds a sitar, so nothing recommends one.
  assert.equal(modelForPreset("instruments/sitar"), undefined);
  assert.equal(modelForPreset("instruments/steel-drum"), undefined);
  assert.equal(modelForPreset("voice/whispered"), undefined);
});

test("advice names a model, or says which kind of silence this is", () => {
  const { modelAdvice } = loadTextPromptModule();
  // The module runs in its own realm, so its objects fail a strict deep compare
  // against literals written here. Copy them into this realm first.
  const advice = (keys) => {
    const result = modelAdvice(keys);
    return result.kind === "conflict"
      ? { kind: result.kind, models: [...result.models] }
      : { ...result };
  };

  assert.deepEqual(advice(["texture/lo-fi", "function/peak"]), {
    kind: "single",
    model: "clap",
  });
  assert.deepEqual(advice(["style/jungle", "rhythm/breakbeat"]), {
    kind: "single",
    model: "mulan",
  });

  // Fusion was measured and rejected, so a split selection must not pick a
  // side. It must also not stay quiet: the two silent cases used to look the
  // same, and a third of the vocabulary falls into the second one.
  assert.deepEqual(advice(["texture/lo-fi", "style/jungle"]), {
    kind: "conflict",
    models: ["clap", "mulan"],
  });

  // An axis with no measurement neither recommends nor blocks. Instruments is
  // now one of those axes, so a sitar rides whatever the rest of the bank says.
  assert.deepEqual(advice(["space/wide"]), { kind: "unmeasured" });
  assert.deepEqual(advice(["instruments/sitar"]), { kind: "unmeasured" });
  assert.deepEqual(advice(["space/wide", "style/jungle"]), {
    kind: "single",
    model: "mulan",
  });
  assert.deepEqual(advice(["instruments/sitar", "style/jungle"]), {
    kind: "single",
    model: "mulan",
  });
  assert.deepEqual(advice([]), { kind: "unmeasured" });
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
  // breakbeat carries 1.0 and vocal-led 0.75 for MuQ-MuLan; the merge keeps
  // the safest contributing weight.
  assert.equal(composed.negativeWeight, 0.75);
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
