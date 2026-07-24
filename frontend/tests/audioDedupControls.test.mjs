import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import ts from "typescript";
import vm from "node:vm";

const sourcePath = fileURLToPath(new URL("../src/AudioDedupDialog.tsx", import.meta.url));

function loadAudioDedupModule() {
  const source = readFileSync(sourcePath, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, {
    module,
    exports: module.exports,
    require: (specifier) => {
      if (specifier === "react") {
        return {
          useEffect: () => undefined,
          useMemo: (factory) => factory(),
          useState: (initial) => [
            typeof initial === "function" ? initial() : initial,
            () => undefined
          ]
        };
      }
      if (specifier === "react/jsx-runtime") {
        return { jsx: () => null, jsxs: () => null };
      }
      if (specifier === "lucide-react") {
        return {
          FileSpreadsheet: () => null,
          FolderOpen: () => null,
          Play: () => null,
          Square: () => null,
          X: () => null
        };
      }
      if (specifier === "./jobUi") {
        return { AudioDedupProcessStatus: () => null };
      }
      if (specifier === "./trackDisplay") {
        return { basename: (value) => value };
      }
      throw new Error(`Unexpected require: ${specifier}`);
    }
  });
  return module.exports;
}

function defaultDraft(overrides = {}) {
  return {
    root: " D:/Music ",
    pathContains: ["Sets", "Archive"],
    sources: ["mert", "maest", "muq", "clap"],
    customWeights: false,
    weightInputs: {
      mert: "0.43",
      maest: "0.32",
      muq: "0.12",
      clap: "0.04"
    },
    preset: "safe",
    minScore: "",
    minSimilarity: "",
    limitGroups: "",
    outDir: "",
    apply: false,
    confirmation: "",
    ...overrides
  };
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

test("Audio Dedup default payload enables MuQ and delegates raw defaults to the backend", () => {
  const {
    audioDedupDefaultWeights,
    audioDedupSourceOrder,
    buildAudioDedupJobPayload
  } = loadAudioDedupModule();

  assert.deepEqual(plain(audioDedupSourceOrder), ["mert", "maest", "muq", "clap"]);
  assert.deepEqual(plain(audioDedupDefaultWeights), {
    mert: 0.43,
    maest: 0.32,
    muq: 0.12,
    clap: 0.04
  });

  const result = buildAudioDedupJobPayload(defaultDraft());
  assert.equal(result.ok, true);
  assert.deepEqual(plain(result.payload), {
    root: "D:/Music",
    path_contains: ["Sets", "Archive"],
    sources: ["mert", "maest", "muq", "clap"],
    weights: null,
    preset: "safe",
    min_score: null,
    min_similarity: null,
    limit_groups: null,
    out_dir: null,
    apply: false,
    confirmation: null
  });
});

test("custom payload contains exactly the enabled source keys", () => {
  const { buildAudioDedupJobPayload } = loadAudioDedupModule();
  const result = buildAudioDedupJobPayload(defaultDraft({
    sources: ["mert", "muq"],
    customWeights: true,
    weightInputs: {
      mert: "0.5",
      maest: "99",
      muq: "0.25",
      clap: "99"
    }
  }));

  assert.equal(result.ok, true);
  assert.deepEqual(plain(result.payload.sources), ["mert", "muq"]);
  assert.deepEqual(plain(result.payload.weights), { mert: 0.5, muq: 0.25 });
});

test("custom weight validation rejects empty duplicate invalid and zero-only profiles", () => {
  const { buildAudioDedupJobPayload } = loadAudioDedupModule();
  const cases = [
    defaultDraft({ sources: [] }),
    defaultDraft({ sources: ["mert", "mert"] }),
    defaultDraft({
      customWeights: true,
      weightInputs: { mert: "NaN", maest: "0.32", muq: "0.12", clap: "0.04" }
    }),
    defaultDraft({
      customWeights: true,
      weightInputs: { mert: "-0.1", maest: "0.32", muq: "0.12", clap: "0.04" }
    }),
    defaultDraft({
      customWeights: true,
      weightInputs: { mert: "0", maest: "0", muq: "0", clap: "0" }
    })
  ];

  for (const draft of cases) {
    assert.equal(buildAudioDedupJobPayload(draft).ok, false);
  }
});

test("apply payload preserves the exact gate and non-legacy MERT plus MAEST safety", () => {
  const { buildAudioDedupJobPayload } = loadAudioDedupModule();

  const whitespaceConfirmation = buildAudioDedupJobPayload(defaultDraft({
    apply: true,
    confirmation: " APPLY DELETE"
  }));
  assert.equal(whitespaceConfirmation.ok, false);
  assert.match(whitespaceConfirmation.error, /APPLY DELETE/);

  const unsafeNonLegacy = buildAudioDedupJobPayload(defaultDraft({
    sources: ["muq", "clap"],
    customWeights: true,
    weightInputs: { mert: "0.43", maest: "0.32", muq: "0.8", clap: "0.2" },
    apply: true,
    confirmation: "APPLY DELETE"
  }));
  assert.equal(unsafeNonLegacy.ok, false);
  assert.match(unsafeNonLegacy.error, /MERT и MAEST/);

  const defaultApply = buildAudioDedupJobPayload(defaultDraft({
    apply: true,
    confirmation: "APPLY DELETE"
  }));
  assert.equal(defaultApply.ok, true);
  assert.equal(defaultApply.payload.weights, null);
  assert.equal(defaultApply.payload.confirmation, "APPLY DELETE");
});

test("exact pre-MuQ legacy opt-out remains serializable with its raw weights", () => {
  const { buildAudioDedupJobPayload } = loadAudioDedupModule();
  const result = buildAudioDedupJobPayload(defaultDraft({
    sources: ["mert", "maest", "clap"],
    customWeights: true,
    apply: true,
    confirmation: "APPLY DELETE"
  }));

  assert.equal(result.ok, true);
  assert.deepEqual(plain(result.payload.sources), ["mert", "maest", "clap"]);
  assert.deepEqual(plain(result.payload.weights), {
    mert: 0.43,
    maest: 0.32,
    clap: 0.04
  });
});

test("Audio Dedup surface exposes actual status profile and truthful safety copy", () => {
  const source = readFileSync(sourcePath, "utf8");

  assert.match(source, /Actual Audio Dedup sources and weights/);
  assert.match(source, /job\.sources\.map/);
  assert.match(source, /job\.weights\[source\]/);
  assert.match(source, /weighted ranking signal, не вероятность/);
  assert.match(source, /audio-to-audio embedding, а не CLAP text search/);
  assert.match(source, /MuQ или CLAP[\s\S]*сами по себе никогда не разрешают удаление/);
  assert.match(source, /Pre-MuQ legacy/);
});
