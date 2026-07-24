import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));

function loadApiModule(fetchImpl) {
  const source = readFileSync(join(srcDir, "api.ts"), "utf8");
  const clientSource = readFileSync(join(srcDir, "apiClient.ts"), "utf8");
  const clientCompiled = ts.transpileModule(clientSource, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
  }).outputText;
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
  }).outputText;
  const clientModule = { exports: {} };
  vm.runInNewContext(clientCompiled, { module: clientModule, exports: clientModule.exports, fetch: fetchImpl, URLSearchParams, Error, JSON, encodeURIComponent });
  const module = { exports: {} };
  vm.runInNewContext(compiled, {
    module,
    exports: module.exports,
    require: (path) => {
      if (path === "./apiClient") return clientModule.exports;
      throw new Error(`Unexpected require: ${path}`);
    },
    fetch: fetchImpl,
    URLSearchParams,
    Error,
    JSON,
    encodeURIComponent
  });
  return module.exports;
}

function jsonResponse(value = {}) {
  return { ok: true, json: async () => value, text: async () => JSON.stringify(value), statusText: "OK" };
}

test("reference compare client serializes model list and seed track", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ seed_track_id: 7, groups: [] });
  });

  await api.referenceCompare({ seed_track_id: 7, models: ["clap", "muq", "sonara"], limit: 12 });

  assert.equal(calls[0].path, "/api/reference/compare");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), { seed_track_id: 7, models: ["clap", "muq", "sonara"], limit: 12 });
});

test("reference compare verdict client stores MuQ verdict with exact v7 identities and notes", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ id: 1, source: "reference_compare:muq" });
  });

  await api.referenceCompareVerdict({
    seed: {
      track_id: 3,
      catalog_uuid: "catalog-a",
      track_uuid: "seed-uuid",
      content_generation: 4,
    },
    candidate: {
      track_id: 9,
      catalog_uuid: "catalog-a",
      track_uuid: "candidate-uuid",
      content_generation: 7,
    },
    model: "muq",
    verdict: "palette",
    notes: "shared acoustic palette",
  });

  assert.equal(calls[0].path, "/api/reference/compare/verdict");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    seed: {
      track_id: 3,
      catalog_uuid: "catalog-a",
      track_uuid: "seed-uuid",
      content_generation: 4,
    },
    candidate: {
      track_id: 9,
      catalog_uuid: "catalog-a",
      track_uuid: "candidate-uuid",
      content_generation: 7,
    },
    model: "muq",
    verdict: "palette",
    notes: "shared acoustic palette",
  });
});

test("reference panel uses v7 ids, exact verdict identities, notes, and stale guards", () => {
  const referencePanelSource = readFileSync(join(srcDir, "ReferenceComparePanel.tsx"), "utf8");

  assert.match(referencePanelSource, /referenceCompareVerdictOptions/);
  assert.match(referencePanelSource, /api\.referenceCompare\(/);
  assert.match(referencePanelSource, /api\.referenceCompareVerdict\(/);
  assert.match(referencePanelSource, /seed_track_id: requestedTrackId/);
  assert.match(referencePanelSource, /seed: trackIdentityPayload\(referenceTrack\)/);
  assert.match(referencePanelSource, /candidate: trackIdentityPayload\(result\.track\)/);
  assert.match(referencePanelSource, /notes: verdictNotes\[key\]\?\.trim\(\) \|\| null/);
  assert.match(referencePanelSource, /referenceCompareResponseIsCurrent/);
  assert.match(referencePanelSource, /activeReferenceIdentityRef/);
  assert.match(referencePanelSource, /result\.track\.track_id/);
  assert.doesNotMatch(referencePanelSource, /result\.track\.id|referenceTrack\.id/);
});

test("reference panel keeps all five model groups visible including MuQ", () => {
  const referencePanelSource = readFileSync(join(srcDir, "ReferenceComparePanel.tsx"), "utf8");

  assert.match(referencePanelSource, /\["clap", "mert", "muq", "maest", "sonara"\]/);
  assert.match(referencePanelSource, /orderedReferenceCompareGroups/);
  assert.match(referencePanelSource, /available: false/);
  assert.match(referencePanelSource, /did not return \$\{model\.toUpperCase\(\)\} availability/);
});
