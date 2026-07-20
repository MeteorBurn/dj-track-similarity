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
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  const clientModule = { exports: {} };
  vm.runInNewContext(clientCompiled, {
    module: clientModule,
    exports: clientModule.exports,
    fetch: fetchImpl,
    URLSearchParams,
    Error,
    JSON,
    encodeURIComponent
  });
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

test("API module keeps public types separate from domain client implementation", () => {
  const apiSource = readFileSync(join(srcDir, "api.ts"), "utf8");
  const clientSource = readFileSync(join(srcDir, "apiClient.ts"), "utf8");

  assert.match(apiSource, /export \{ api \} from "\.\/apiClient";/);
  assert.match(clientSource, /const databaseApi = \{/);
  assert.match(clientSource, /const searchApi = \{/);
  assert.match(clientSource, /const helperToolsApi = \{/);
  assert.doesNotMatch(apiSource, /async function request/);
});

function jsonResponse(value = {}) {
  return {
    ok: true,
    json: async () => value,
    text: async () => JSON.stringify(value),
    statusText: "OK"
  };
}

test("tracks client serializes library query controls into the current API query contract", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ items: [], total: 0, limit: 25, offset: 50 });
  });

  await api.tracks({
    query: "deep dub",
    searchMode: "fts",
    preset: "syncopated",
    liked: true,
    classifierMinScores: { break_energy: 0.65 },
    limit: 25,
    offset: 50,
    includeMetadata: true
  });

  const requestUrl = new URL(calls[0].path, "http://frontend.test");

  assert.equal(requestUrl.pathname, "/api/tracks");
  assert.equal(requestUrl.searchParams.get("q"), "deep dub");
  assert.equal(requestUrl.searchParams.get("search_mode"), "fts");
  assert.equal(requestUrl.searchParams.get("preset"), "syncopated");
  assert.equal(requestUrl.searchParams.get("liked"), "true");
  assert.equal(requestUrl.searchParams.get("classifier_min_scores"), JSON.stringify({ break_energy: 0.65 }));
  assert.equal(requestUrl.searchParams.get("limit"), "25");
  assert.equal(requestUrl.searchParams.get("offset"), "50");
  assert.equal(requestUrl.searchParams.get("include_metadata"), "true");
});

test("filtered tracks client sends defaulted domain payloads for library view controls", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ items: [], total: 0 });
  });

  await api.filteredTracks({ query: "", searchMode: undefined, preset: undefined, liked: false, classifierMinScores: undefined });

  assert.equal(calls[0].path, "/api/tracks/filtered");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    query: "",
    search_mode: "like",
    preset: "all",
    liked: false,
    classifier_min_scores: {}
  });
});

test("SONARA timeline client fetches sidecar data for one track", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ energy_curve: { type: "list", length: 3, value: [0.1, 0.4, 0.8] } });
  });

  const timeline = await api.sonaraTimeline(42);

  assert.equal(calls[0].path, "/api/tracks/42/sonara-timeline");
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.equal(calls[0].options.method, undefined);
  assert.equal(timeline.energy_curve.length, 3);
});

test("analysis job client preserves unified job defaults for model and classifier runs", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ job_id: "job-1", state: "queued", errors: [], events: [] });
  });

  await api.analysisJobStart({ models: ["maest", "clap"], limit: null, device: "auto" });

  assert.equal(calls[0].path, "/api/analysis/jobs");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    models: ["maest", "clap"],
    classifier_keys: [],
    limit: null,
    device: "auto",
    top_k: 3,
    track_batch_size: 4,
    inference_batch_size: 24,
    sonara_outputs: []
  });
});

test("analysis job client defaults a SONARA-only request to Core storage", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ job_id: "job-sonara", state: "queued", total: 0, processed: 0, analyzed: 0, failed: 0, errors: [], events: [], cancel_requested: false, workers: 4, device_requested: "auto" });
  });

  await api.analysisJobStart({ models: ["sonara"] });

  assert.deepEqual(JSON.parse(calls[0].options.body), {
    models: ["sonara"],
    classifier_keys: [],
    limit: null,
    device: "auto",
    top_k: 3,
    track_batch_size: 4,
    inference_batch_size: 24,
    sonara_outputs: ["core"]
  });
});

test("CLAP text search client keeps positive and negative prompt arrays separate", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse([]);
  });

  await api.textSearch({
    query: "broken beat",
    positive_queries: ["breakbeat.", "This audio is a syncopated drum track."],
    negative_queries: ["This audio is a straight house track."],
    adaptive_contrast: true,
    preset: "breaks_broken",
    limit: 10,
    min_similarity: 0,
    device: "auto"
  });

  assert.equal(calls[0].path, "/api/search/text");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    query: "broken beat",
    positive_queries: ["breakbeat.", "This audio is a syncopated drum track."],
    negative_queries: ["This audio is a straight house track."],
    adaptive_contrast: true,
    preset: "breaks_broken",
    limit: 10,
    min_similarity: 0,
    device: "auto"
  });
});

test("destructive helper clients pass apply confirmations only through explicit payloads", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ job_id: "job-1", state: "queued", errors: [], events: [] });
  });

  await api.audioDoctorJobStart({ source_mode: "db", apply: true, confirmation: "APPLY REPAIR" });
  await api.audioDedupJobStart({ root: "D:/Music", apply: true, confirmation: "APPLY DELETE" });

  assert.equal(calls[0].path, "/api/audio-doctor/jobs");
  assert.deepEqual(JSON.parse(calls[0].options.body), { source_mode: "db", apply: true, confirmation: "APPLY REPAIR" });
  assert.equal(calls[1].path, "/api/audio-dedup/jobs");
  assert.deepEqual(JSON.parse(calls[1].options.body), { root: "D:/Music", apply: true, confirmation: "APPLY DELETE" });
});

test("API client surfaces backend error text for unknown or invalid payload failures", async () => {
  const { api } = loadApiModule(async () => ({
    ok: false,
    json: async () => ({}),
    text: async () => "{\"detail\":\"Unknown classifier: break_energy\"}",
    statusText: "Bad Request"
  }));

  await assert.rejects(
    api.setBuilderGenerate({
      seed_mode: "auto",
      seed_track_ids: [],
      auto_seed_count: 3,
      mode: "balanced_set",
      limit: 12,
      diversity: 0.35,
      energy_curve: "balanced",
      bpm_mode: "general",
      bpm_change: "medium",
      classifier_preferences: { break_energy: 0.7 }
    }),
    /Unknown classifier: break_energy/
  );
});
