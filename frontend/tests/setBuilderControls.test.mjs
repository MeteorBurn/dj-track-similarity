import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

async function loadTypeScriptModule(relativePath, name) {
  const sourcePath = new URL(relativePath, import.meta.url);
  const tempDir = mkdtempSync(join(tmpdir(), `${name}-`));
  const modulePath = join(tempDir, `${name}.cjs`);
  const compiled = ts.transpileModule(readFileSync(sourcePath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  writeFileSync(modulePath, compiled, "utf8");
  return import(pathToFileURL(modulePath));
}

function setDraft(overrides = {}) {
  return {
    databasePath: "C:/temp/core.sqlite",
    databaseIdentity: "catalog-a",
    seedMode: "manual",
    seedTrackIds: [1, 2],
    autoSeedCount: 5,
    sources: { mert: true, maest: true, muq: true, clap: true },
    useCustomWeights: false,
    weights: { mert: 0.3, maest: 0.18, muq: 0.15, clap: 0.22, sonara_broad: 0.3 },
    mode: "balanced_set",
    limit: 24,
    diversity: 0.25,
    energyCurve: "balanced",
    bpmMode: "general",
    bpmChange: "medium",
    classifierPreferences: {},
    classifierFlows: {},
    randomSeed: 0,
    ...overrides
  };
}

test("set builder slider reset returns fresh maps", async () => {
  const { resetSetBuilderSliders, setBuilderDefaultDiversity, setBuilderDefaultFlow } =
    await loadTypeScriptModule("../src/setBuilderControls.ts", "setBuilderControls");

  const first = resetSetBuilderSliders();
  first.classifierPreferences.break_energy = 0.85;
  first.classifierFlows.break_energy = "rise";
  const second = resetSetBuilderSliders();

  assert.equal(second.diversity, setBuilderDefaultDiversity);
  assert.deepEqual(second.classifierPreferences, {});
  assert.deepEqual(second.classifierFlows, {});
  assert.equal(setBuilderDefaultFlow, "flat");
  assert.notEqual(first.classifierPreferences, second.classifierPreferences);
});

test("SET defaults include MuQ and keep backend raw defaults authoritative", async () => {
  const { buildSetBuilderPayload } = await loadTypeScriptModule("../src/searchSurfaceState.ts", "searchSurfaceState");
  const result = buildSetBuilderPayload(setDraft());

  assert.equal(result.ok, true);
  assert.deepEqual(result.payload.sources, ["mert", "maest", "muq", "clap"]);
  assert.equal(result.payload.weights, null);
  assert.deepEqual(result.payload.seed_track_ids, [1, 2]);
  assert.equal(result.payload.random_seed, 0);
});

test("SET legacy opt-out emits the exact pre-MuQ source and raw-weight profile", async () => {
  const { buildSetBuilderPayload } = await loadTypeScriptModule("../src/searchSurfaceState.ts", "searchSurfaceState");
  const result = buildSetBuilderPayload(setDraft({
    sources: { mert: true, maest: true, muq: false, clap: true },
    useCustomWeights: true
  }));

  assert.equal(result.ok, true);
  assert.deepEqual(result.payload.sources, ["mert", "maest", "clap"]);
  assert.deepEqual(result.payload.weights, {
    mert: 0.3,
    maest: 0.18,
    clap: 0.22,
    sonara_broad: 0.3
  });
});

test("SET validation enforces unique manual seeds and numeric backend bounds", async () => {
  const { buildSetBuilderPayload } = await loadTypeScriptModule("../src/searchSurfaceState.ts", "searchSurfaceState");

  const deduplicated = buildSetBuilderPayload(setDraft({ seedTrackIds: [1, 1, 2] }));
  assert.equal(deduplicated.ok, true);
  assert.deepEqual(deduplicated.payload.seed_track_ids, [1, 2]);

  for (const [override, message] of [
    [{ seedTrackIds: [] }, /1-5 unique seed/],
    [{ seedTrackIds: [1, 2, 3, 4, 5, 6] }, /1-5 unique seed/],
    [{ autoSeedCount: 0 }, /Auto anchors/],
    [{ limit: 501 }, /SET limit/],
    [{ diversity: Number.NaN }, /diversity/],
    [{ randomSeed: 1.5 }, /safe integer/]
  ]) {
    const result = buildSetBuilderPayload(setDraft(override));
    assert.equal(result.ok, false);
    assert.match(result.error, message);
  }

  const autoWithoutSeeds = buildSetBuilderPayload(setDraft({ seedMode: "auto", seedTrackIds: [] }));
  assert.equal(autoWithoutSeeds.ok, true);
  assert.deepEqual(autoWithoutSeeds.payload.seed_track_ids, []);
});

test("Add preview provenance requires a nonempty current SET response signature", async () => {
  const { canAddSetPreview, setBuilderSignature } =
    await loadTypeScriptModule("../src/searchSurfaceState.ts", "searchSurfaceState");
  const current = setBuilderSignature(setDraft());

  assert.equal(canAddSetPreview(current, current, 4), true);
  assert.equal(canAddSetPreview("", current, 4), false);
  assert.equal(canAddSetPreview(`${current}-stale`, current, 4), false);
  assert.equal(canAddSetPreview(current, current, 0), false);
});

test("SET signature includes catalog identity and every request-shaping input", async () => {
  const { setBuilderSignature } = await loadTypeScriptModule("../src/searchSurfaceState.ts", "searchSurfaceState");
  const current = setBuilderSignature(setDraft());

  assert.notEqual(current, setBuilderSignature(setDraft({ databaseIdentity: "catalog-b" })));
  assert.notEqual(current, setBuilderSignature(setDraft({ seedTrackIds: [3] })));
  assert.notEqual(current, setBuilderSignature(setDraft({ sources: { mert: true, maest: true, muq: false, clap: true } })));
});

test("Set Builder UI owns local response provenance and backend response evidence", () => {
  const source = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");

  assert.match(source, /const \[setBuilderResponse, setSetBuilderResponse\]/);
  assert.match(source, /api\.setBuilderGenerate\(setBuilderPayload\.payload, \{ signal: controller\.signal \}\)/);
  assert.match(source, /addGeneratedSetToPlaylist\(setBuilderResponse\.items\.map\(\(item\) => item\.track\)\)/);
  assert.match(source, /setBuilderResponse\.coverage\.missing_muq/);
  assert.match(source, /setBuilderResponse\.sources\.join/);
  assert.match(source, /setBuilderResponse\.weights_used/);
  assert.doesNotMatch(source, /disabled=\{busy \|\| !results\.length\} onClick=\{addGeneratedSetToPlaylist\}/);
});
