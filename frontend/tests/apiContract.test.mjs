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
  assert.doesNotMatch(apiSource, /async function request/);
});

test("public API types omit generic versioned contract identity fields", () => {
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
    assert.equal(
      new RegExp(`^\\s*${field}:`, "m").test(apiSource),
      false,
      `${field} must not be a public frontend API property`,
    );
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

test("a dropped connection retries a read once and never repeats a write", async () => {
  const attempts = [];
  const { api } = loadApiModule(async (path, options = {}) => {
    attempts.push(path);
    if (attempts.filter((seen) => seen === path).length === 1) {
      throw new TypeError("Failed to fetch");
    }
    return jsonResponse({ job_id: "job-1", state: "running" });
  });

  const job = await api.analysisJob("job-1");
  assert.equal(job.state, "running");
  assert.deepEqual(attempts, ["/api/analysis/jobs/job-1", "/api/analysis/jobs/job-1"]);

  await assert.rejects(
    api.launchRhythmLab(),
    (error) => error instanceof TypeError && error.message === "Failed to fetch",
  );
  assert.equal(attempts.filter((seen) => seen === "/api/rhythm-lab/launch").length, 1);
});

test("rhythm lab client uses status and launch endpoints", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options = {}) => {
    calls.push({ path, options });
    return jsonResponse({ running: false, managed: false, url: "http://127.0.0.1:8777/" });
  });

  await api.rhythmLabStatus();
  await api.launchRhythmLab();

  assert.equal(calls[0].path, "/api/rhythm-lab/status");
  assert.equal(calls[0].options.method, undefined);
  assert.equal(calls[1].path, "/api/rhythm-lab/launch");
  assert.equal(calls[1].options.method, "POST");
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

test("track deletion client sends the current track identity to the delete endpoint", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ track_id: 42 });
  });

  await api.deleteTrack({
    track_id: 42,
    catalog_uuid: "catalog-current",
    track_uuid: "track-current"
  });

  assert.equal(calls[0].path, "/api/tracks/42");
  assert.equal(calls[0].options.method, "DELETE");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    catalog_uuid: "catalog-current",
    track_uuid: "track-current"
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
    positive_queries: ["breakbeat.", "This audio is a syncopated drum track."],
    negative_queries: ["This audio is a straight house track."],
    limit: 10,
    min_similarity: 0,
    device: "auto"
  });

  assert.equal(calls[0].path, "/api/search/text");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    positive_queries: ["breakbeat.", "This audio is a syncopated drum track."],
    negative_queries: ["This audio is a straight house track."],
    limit: 10,
    min_similarity: 0,
    device: "auto"
  });
});

test("text warmup client posts only the family and device, and can be aborted", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ analysis_family: "mulan", device: "auto", seconds: 34.2 });
  });
  const controller = new AbortController();

  const result = await api.textSearchWarmup(
    { analysis_family: "mulan" },
    { signal: controller.signal }
  );

  assert.equal(calls[0].path, "/api/search/text/warmup");
  assert.deepEqual(JSON.parse(calls[0].options.body), { analysis_family: "mulan" });
  assert.equal(calls[0].options.signal, controller.signal);
  assert.equal(result.seconds, 34.2);
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
  await api.randomSonaraTrack({
    exclude_track_ids: [7],
  }, { signal: controller.signal });
  await api.randomEmbeddingTrack({
    analysis_family: "mert",
    exclude_track_ids: [7],
  }, { signal: controller.signal });
  await api.textSearch({
    positive_queries: ["broken beat"],
    negative_queries: [],
    limit: 10,
    min_similarity: 0,
    device: "auto",
  }, { signal: controller.signal });

  assert.deepEqual(
    calls.map(({ path }) => path),
    [
      "/api/tracks/7",
      "/api/search",
      "/api/search/sonara",
      "/api/search/sonara/random-track",
      "/api/search/random-track",
      "/api/search/text"
    ]
  );
  assert.deepEqual(JSON.parse(calls[3].options.body), {
    exclude_track_ids: [7],
  });
  assert.deepEqual(JSON.parse(calls[4].options.body), {
    analysis_family: "mert",
    exclude_track_ids: [7],
  });
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
  await api.resetClassifier("voice_presence");

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
    classifier_key: "voice_presence"
  });
});

test("API client surfaces backend error text for unknown or invalid payload failures", async () => {
  const { api } = loadApiModule(async () => ({
    ok: false,
    json: async () => ({}),
    text: async () => "{\"detail\":\"Unknown classifier: break_energy\"}",
    statusText: "Bad Request"
  }));

  await assert.rejects(
    api.resetAnalysis("mert"),
    /Unknown classifier: break_energy/
  );
});

test("audio dedup client serializes review filters and the confirmed delete batch", async () => {
  const calls = [];
  const { api } = loadApiModule(async (path, options = {}) => {
    calls.push({ path, options });
    return jsonResponse({});
  });

  await api.audioDedupGroups("audio_dedup_report_20260827_120000", {
    offset: 25,
    limit: 25,
    confidence: ["high", "medium"],
    min_fingerprint: 0.9,
    fake_bitrate_only: true,
    path_contains: "vinyl"
  });
  await api.audioDedupDelete("audio_dedup_report_20260827_120000", {
    selections: [{ group_id: 3, track_ids: [7, 9] }],
    deletion_mode: "trash",
    confirmation: "APPLY DELETE"
  });

  const groupsUrl = new URL(calls[0].path, "http://localhost");
  assert.equal(groupsUrl.pathname, "/api/audio-dedup/reports/audio_dedup_report_20260827_120000/groups");
  assert.equal(groupsUrl.searchParams.get("offset"), "25");
  assert.deepEqual(groupsUrl.searchParams.getAll("confidence"), ["high", "medium"]);
  assert.equal(groupsUrl.searchParams.get("min_fingerprint"), "0.9");
  assert.equal(groupsUrl.searchParams.get("fake_bitrate_only"), "true");
  assert.equal(groupsUrl.searchParams.get("path_contains"), "vinyl");

  assert.equal(
    calls[1].path,
    "/api/audio-dedup/reports/audio_dedup_report_20260827_120000/delete"
  );
  assert.equal(calls[1].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    selections: [{ group_id: 3, track_ids: [7, 9] }],
    deletion_mode: "trash",
    confirmation: "APPLY DELETE"
  });
});
