import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const displayPath = fileURLToPath(new URL("../src/sonaraDisplay.ts", import.meta.url));

function loadDisplayModule() {
  const compiled = ts.transpileModule(readFileSync(displayPath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports });
  return module.exports;
}

test("curve summaries expose count, min, max, and mean without rendering arrays", () => {
  const { readableSonaraCurves } = loadDisplayModule();
  const features = readableSonaraCurves({
    energy_curve: { type: "list", length: 3, value: [0.1, 0.4, 0.9] },
    loudness_curve: {
      type: "ndarray",
      size: 195,
      value: null,
      summary: { min: -23, max: -8, mean: -14.5, std: 2.1 }
    },
    downbeats: { type: "unavailable", value: null }
  });

  assert.equal(features.length, 2);
  assert.equal(features[0].key, "energy_curve");
  assert.equal(features[0].value, "3 values · min 0.1 · max 0.9 · mean 0.467");
  assert.equal(features[1].key, "loudness_curve");
  assert.equal(features[1].value, "195 values · min -23 · max -8 · mean -14.5");
  assert.doesNotMatch(features[0].value, /\[|\]/);
});

test("curve summaries use declared shape when values stay out of the response", () => {
  const { formatCurveSummary } = loadDisplayModule();

  assert.equal(
    formatCurveSummary({ shape: [2, 3], summary: { min: 1, max: 6, mean: 3.5 } }),
    "6 values · min 1 · max 6 · mean 3.5"
  );
  assert.equal(formatCurveSummary({ length: 0, value: [] }), "0 values");
});

test("stored playlist sequences stay compact in the metadata dialog", () => {
  const { readableSonaraCurves } = loadDisplayModule();
  const features = readableSonaraCurves({
    beats: { type: "list", length: 3, value: [10, 20, 30] },
    chord_sequence: { type: "list", length: 2, value: ["Am", "F"] },
    chord_events: {
      type: "list",
      length: 1,
      value: [{ label: "Am", start_sec: 0, end_sec: 12 }]
    }
  });

  assert.deepEqual(Array.from(features, (feature) => feature.key), ["beats", "chord_sequence", "chord_events"]);
  assert.equal(features[0].value, "3 values · min 10 · max 30 · mean 20");
  assert.equal(features[1].value, "2 values");
  assert.equal(features[2].value, "1 value");
});

test("archival tempo, embedding, and fingerprint payloads expose safe summaries only", () => {
  const { readableSonaraCurves } = loadDisplayModule();
  const fingerprint = "AQIDBAUGBwg=";
  const features = readableSonaraCurves({
    tempo_curve: { type: "list", length: 2, value: [126, 127] },
    embedding: { type: "ndarray", shape: [3], size: 3, value: [-0.5, 0.25, 0.75] },
    fingerprint: { type: "str", value: fingerprint }
  });

  assert.deepEqual(Array.from(features, (feature) => feature.key), ["tempo_curve", "embedding", "fingerprint"]);
  assert.equal(features[0].value, "2 values · min 126.0 · max 127.0 · mean 126.5");
  assert.equal(features[1].value, "3 dimensions · min -0.5 · max 0.75 · mean 0.167");
  assert.equal(features[2].value, "12 encoded characters");
  assert.doesNotMatch(features.map((feature) => feature.value).join(" "), /AQIDBAUGBwg|\[|\]/);
});
