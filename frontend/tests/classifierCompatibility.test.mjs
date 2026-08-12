import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

async function loadClassifierCompatibility() {
  const sourcePath = new URL("../src/classifierCompatibility.ts", import.meta.url);
  const tempDir = mkdtempSync(join(tmpdir(), "classifier-compatibility-"));
  const modulePath = join(tempDir, "classifierCompatibility.cjs");
  const compiled = ts.transpileModule(readFileSync(sourcePath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  writeFileSync(modulePath, compiled, "utf8");
  return import(pathToFileURL(modulePath));
}

function classifier(classifierKey, overrides = {}) {
  return {
    classifier_key: classifierKey,
    name: classifierKey,
    artifact_prefix: classifierKey,
    model_path: `${classifierKey}/model.joblib`,
    metadata_path: `${classifierKey}/model.json`,
    ...overrides,
  };
}

test("classifier availability follows manifest scoring compatibility", async () => {
  const {
    classifierIsAvailable,
    classifierProfileStatus,
    classifierScoringBlockedReason,
    filterAvailableClassifierValues,
  } = await loadClassifierCompatibility();

  const unsupported = classifier("legacy", {
    is_scoring_compatible: false,
    manifest_status: "unsupported",
    production_status: "unsupported",
    manifest_errors: ["Manifest version 1 is no longer supported."],
  });
  const available = classifier("ready", {
    is_scoring_compatible: true,
  });

  assert.equal(classifierIsAvailable(unsupported), false);
  assert.equal(classifierProfileStatus(unsupported), "unsupported");
  assert.equal(
    classifierScoringBlockedReason(unsupported),
    "Manifest version 1 is no longer supported.",
  );
  assert.equal(classifierIsAvailable(available), true);
  assert.equal(classifierProfileStatus(available), "available");
  assert.deepEqual(
    filterAvailableClassifierValues(
      [unsupported, available],
      { legacy: 0.75, ready: 0.5, removed: 1 },
    ),
    { ready: 0.5 },
  );
});

test("classifier profiles keep promotion creation order with stable fallback", async () => {
  const { orderPromotedClassifiers } = await loadClassifierCompatibility();
  const input = [
    classifier("newer", { promoted_at: "2026-07-08T18:28:37+00:00" }),
    classifier("missing-time"),
    classifier("older", { promoted_at: "2026-07-08T18:28:32+00:00" }),
    classifier("invalid-time", { promoted_at: "not-a-date" }),
  ];

  assert.deepEqual(
    orderPromotedClassifiers(input).map((item) => item.classifier_key),
    ["older", "newer", "missing-time", "invalid-time"],
  );
  assert.deepEqual(
    input.map((item) => item.classifier_key),
    ["newer", "missing-time", "older", "invalid-time"],
  );
});

test("classifier score count is shown as one tracks value", async () => {
  const { formatClassifierScoredTracks } = await loadClassifierCompatibility();

  assert.equal(formatClassifierScoredTracks(37), "37 tracks");
  assert.equal(formatClassifierScoredTracks(undefined), "0 tracks");
});
