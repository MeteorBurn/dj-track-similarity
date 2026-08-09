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

test("public API types omit versioned contract identity fields", () => {
  const apiSource = readFileSync(join(srcDir, "api.ts"), "utf8");
  const forbiddenFields = [
    "schema_version",
    "contract_hash",
    "source_contract_hashes",
    "release_hash",
    "manifest_version",
    "model_version",
    "feature_manifest_hash",
    "required_outputs_hash",
    "sonara_release_hash",
  ];

  for (const field of forbiddenFields) {
    assert.equal(apiSource.includes(field), false, `${field} must not be part of the public frontend API`);
  }
});

function jsonResponse(value = {}) {
  return {
    ok: true,
    json: async () => value,
    text: async () => JSON.stringify(value),
    statusText: "OK"
  };
}

test("rhythm lab client uses explicit status, launch, and stop endpoints", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options = {}) => {
    calls.push({ path, options });
    return jsonResponse({ running: false, managed: false, url: "http://127.0.0.1:8777/" });
  });

  await api.rhythmLabStatus();
  await api.launchRhythmLab();
  await api.stopRhythmLab();

  assert.equal(calls[0].path, "/api/rhythm-lab/status");
  assert.equal(calls[0].options.method, undefined);
  assert.equal(calls[1].path, "/api/rhythm-lab/launch");
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[2].path, "/api/rhythm-lab/stop");
  assert.equal(calls[2].options.method, "POST");
});

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
    offset: 50
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
  assert.equal(requestUrl.searchParams.get("include_metadata"), null);
});

test("filtered tracks client sends defaulted domain payloads for library view controls", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse([]);
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

test("SONARA status client reads neutral current-output counts", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({
      catalog_uuid: "catalog-current",
      total_tracks: 12,
      outputs: [
        { output_kind: "core", present_count: 10, missing_count: 2 },
        { output_kind: "embedding", present_count: 7, missing_count: 5 }
      ]
    });
  });

  const status = await api.sonaraStatus();

  assert.equal(calls[0].path, "/api/analysis/sonara/status");
  assert.equal(calls[0].options.method, undefined);
  assert.equal(status.catalog_uuid, "catalog-current");
  assert.equal(status.total_tracks, 12);
  assert.deepEqual(status.outputs, [
    { output_kind: "core", present_count: 10, missing_count: 2 },
    { output_kind: "embedding", present_count: 7, missing_count: 5 }
  ]);
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

test("detail and generic search clients forward AbortSignal unchanged", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse(path.startsWith("/api/tracks/") ? {} : []);
  });
  const controller = new AbortController();

  await api.track(7, { signal: controller.signal });
  await api.search({
    analysis_family: "mert",
    seed_track_ids: [7],
    limit: 10,
    min_similarity: 0,
    epsilon: null,
    noise: 0,
  }, { signal: controller.signal });
  await api.sonaraSearch({
    seed_track_ids: [7],
    limit: 10,
    mode: "balanced",
    mixer_weights: null,
    modifiers: null,
    min_similarity: 0,
  }, { signal: controller.signal });
  await api.textSearch({
    query: "broken beat",
    positive_queries: ["broken beat"],
    negative_queries: [],
    adaptive_contrast: true,
    preset: "manual",
    limit: 10,
    min_similarity: 0,
    device: "auto",
  }, { signal: controller.signal });

  assert.deepEqual(
    calls.map(({ path }) => path),
    ["/api/tracks/7", "/api/search", "/api/search/sonara", "/api/search/text"]
  );
  for (const call of calls) {
    assert.equal(call.options.signal, controller.signal);
  }
});

test("liked mutation serializes the exact optimistic track identity", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({});
  });

  await api.setTrackLiked({
    track_id: 41,
    catalog_uuid: "catalog-current",
    track_uuid: "track-current",
    content_generation: 7,
    file_path: "D:/Music/example.wav",
    title: "Example",
    artist: "Artist",
    album: null,
    tag_bpm: 128,
    tag_key: "8A",
    audio_duration_seconds: 320,
    liked: false,
    analysis_coverage: {
      sonara_core: true,
      maest_analysis: true,
      maest_embedding: true,
      mert: true,
      muq: true,
      clap: true
    },
    classifier_scores: {}
  }, true);

  assert.equal(calls[0].path, "/api/tracks/41/liked");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    catalog_uuid: "catalog-current",
    track_uuid: "track-current",
    expected_content_generation: 7,
    liked: true
  });
});

test("MuQ search and resets serialize only current field names", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse([]);
  });

  await api.search({
    analysis_family: "muq",
    seed_track_ids: [11, 12],
    limit: 25,
    min_similarity: 0.2,
    epsilon: null,
    noise: 0
  });
  await api.resetAnalysis("muq");
  await api.resetClassifiers(["voice_presence"]);

  assert.equal(calls[0].path, "/api/search");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    analysis_family: "muq",
    seed_track_ids: [11, 12],
    limit: 25,
    min_similarity: 0.2,
    epsilon: null,
    noise: 0
  });
  assert.equal(calls[1].path, "/api/analysis/reset");
  assert.deepEqual(JSON.parse(calls[1].options.body), { analysis_family: "muq" });
  assert.equal(calls[2].path, "/api/classifiers/reset");
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    classifier_keys: ["voice_presence"]
  });
});

test("SET Hybrid and Audio Dedup preserve MuQ profiles and omit undefined fields", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({});
  });

  await api.setBuilderGenerate({
    seed_mode: "manual",
    seed_track_ids: [3],
    auto_seed_count: 5,
    sources: ["mert", "maest", "muq", "clap"],
    weights: null,
    mode: "balanced_set",
    limit: 24,
    diversity: 0.35,
    energy_curve: "balanced",
    bpm_mode: "general",
    bpm_change: "medium",
    random_seed: 0
  });
  await api.hybridSearch({
    seed_track_ids: [3],
    sources: ["mert", "maest", "muq", "sonara", "clap"],
    weights: null,
    per_source: 30,
    limit: 25,
    include_diagnostics: true,
    record_session: false
  });
  await api.audioDedupJobStart({
    root: "D:/Music",
    sources: ["mert", "maest", "muq", "clap"],
    weights: {
      mert: 0.43,
      maest: 0.32,
      muq: 0.12,
      clap: 0.04
    },
    apply: false
  });

  assert.equal(calls[0].path, "/api/set-builder/generate");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    seed_mode: "manual",
    seed_track_ids: [3],
    auto_seed_count: 5,
    sources: ["mert", "maest", "muq", "clap"],
    weights: null,
    mode: "balanced_set",
    limit: 24,
    diversity: 0.35,
    energy_curve: "balanced",
    bpm_mode: "general",
    bpm_change: "medium",
    random_seed: 0
  });
  assert.equal(calls[1].path, "/api/search/hybrid");
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    seed_track_ids: [3],
    sources: ["mert", "maest", "muq", "sonara", "clap"],
    weights: null,
    per_source: 30,
    limit: 25,
    include_diagnostics: true,
    record_session: false
  });
  assert.equal(calls[2].path, "/api/audio-dedup/jobs");
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    root: "D:/Music",
    sources: ["mert", "maest", "muq", "clap"],
    weights: {
      mert: 0.43,
      maest: 0.32,
      muq: 0.12,
      clap: 0.04
    },
    apply: false
  });
  for (const call of calls) {
    assert.equal(Object.values(JSON.parse(call.options.body)).includes(undefined), false);
  }
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
