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

test("reference compare verdict client stores model-specific verdict", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ id: 1, source: "reference_compare:maest" });
  });

  await api.referenceCompareVerdict({ seed_track_id: 3, candidate_track_id: 9, model: "maest", verdict: "genre", notes: "same genre family" });

  assert.equal(calls[0].path, "/api/reference/compare/verdict");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    seed_track_id: 3,
    candidate_track_id: 9,
    model: "maest",
    verdict: "genre",
    notes: "same genre family"
  });
});

test("search panel exposes LAB tab and verdict controls", () => {
  const panelSource = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const referencePanelSource = readFileSync(join(srcDir, "ReferenceComparePanel.tsx"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");

  assert.match(panelSource, /activeSearchTab.*\| "lab"/);
  assert.match(panelSource, />LAB</);
  assert.match(panelSource, /<ReferenceComparePanel/);
  assert.match(referencePanelSource, /referenceCompareVerdictOptions/);
  assert.match(referencePanelSource, /api\.referenceCompare\(/);
  assert.match(referencePanelSource, /api\.referenceCompareVerdict\(/);
  assert.match(styles, /\.reference-compare-panel/);
  assert.match(styles, /\.reference-compare-grid/);
});
