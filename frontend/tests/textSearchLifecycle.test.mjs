import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const flush = () => new Promise((resolve) => setImmediate(resolve));
function harness(api) {
  const slots = []; let cursor = 0; let effects = [];
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
      return [slots[index], (value) => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
    },
    useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
    useEffect(fn, deps) {
      const index = cursor++;
      const old = slots[index];
      if (!old || deps.some((value, n) => !Object.is(value, old.deps[n]))) {
        slots[index] = { deps, cleanup: old?.cleanup };
        effects.push(() => { old?.cleanup?.(); slots[index].cleanup = fn(); });
      }
    },
  };
  const modules = new Map();
  function load(name) {
    if (name === "react") return react;
    if (name === "./api") return { api };
    if (modules.has(name)) return modules.get(name);
    const path = fileURLToPath(new URL(`../src/${name.replace("./", "")}.ts`, import.meta.url));
    const source = ts.transpileModule(readFileSync(path, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
    const module = { exports: {} }; modules.set(name, module.exports);
    vm.runInNewContext(source, { module, exports: module.exports, require: load, console, crypto, AbortController, Error });
    return module.exports;
  }
  const { useTextSearch } = load("./useTextSearch");
  const { textPromptPresets } = load("./textPromptPresets");
  textPromptPresets.splice(0, textPromptPresets.length, ...["rhythm/first", "rhythm/second", "bass/first"].map((key) => ({
    key, axis: key.split("/")[0],
    positive: { shared: [`${key} shared`], clap: [`${key} clap`], mulan: [`${key} mulan`] },
    negative: { shared: [`${key} negative`], clap: [`${key} clap negative`] },
    negativeWeight: { clap: 0.7, mulan: 0.3 },
  })));
  const options = { databasePath: "synthetic.sqlite", databaseCatalogUuid: "catalog",
    filters: { limit: 10 }, analysisDevice: "cpu",
    setNotice: () => {}, appendActivity: () => {} };
  const commits = []; let token = 0;
  const requests = {
    beginGenericSearchRequest: () => ({ token: ++token, controller: new AbortController() }),
    genericSearchRequestIsCurrent: (ticket) => ticket.token === token,
    commitGenericSearchResults: (ticket, origin, results) => { if (ticket.token !== token) return false; commits.push({ origin, results }); return true; },
    finishGenericSearchRequest: () => {},
  };
  function render() { cursor = 0; const value = useTextSearch(options); const queued = effects; effects = []; queued.forEach((fn) => fn()); return value; }
  return { render, requests, commits, load };
}
function response(run = "run", capability = "absent") {
  return { results: [{ track: { track_uuid: "track" }, score: 0.3 }], execution: { run_id: run, query_key: "query", feedback_capability: capability } };
}

test("A/B keeps each model's bank and automatic weight while preserving a successful arm on failure", async () => {
  const first = deferred(), second = deferred(); const calls = [];
  const h = harness({ textSearch: (payload) => { calls.push(payload); return calls.length === 1 ? first.promise : second.promise; } });
  let ui = h.render(); ui.togglePromptPreset("rhythm/first"); ui.setTextCompareModels(true);
  ui = h.render(); const running = ui.handleTextSearch(h.requests);
  first.resolve(response()); await flush();
  ui = h.render();
  assert.equal(ui.textComparison[0].status, "success");
  assert.equal(ui.textComparison[1].status, "pending");
  second.reject(new Error("unavailable")); await running;
  ui = h.render();
  assert.equal(ui.textComparison[1].status, "error");
  assert.equal(h.commits.at(-1).results.length, 1);
  const { buildTextSearchArms } = h.load("./textSearchExecution");
  for (const family of ["clap", "mulan"]) {
    const payload = calls.find((call) => call.analysis_family === family);
    assert.deepEqual([...payload.positive_queries], [`rhythm/first ${family}`]);
    assert.deepEqual([...payload.negative_queries], [family === "clap" ? "rhythm/first clap negative" : "rhythm/first negative"]);
    assert.equal(payload.negative_weight, family === "clap" ? 0.7 : 0.3);
    assert.equal(payload.input_mode, "preset");
    assert.equal(payload.use_feedback, true);
    assert.equal(payload.comparison_mode, "product_ab");
    assert.deepEqual([...payload.preset_banks.map((bank) => bank.key)], ["rhythm/first"]);
    assert.deepEqual([...payload.preset_banks[0].positive_queries], [...payload.positive_queries]);
    const single = buildTextSearchArms({ family, compare: false, keys: ["rhythm/first"],
      useNegative: false, limit: 10, device: "cpu", comparisonId: "unused" })[0].payload;
    assert.deepEqual([...single.positive_queries], [...payload.positive_queries]);
    assert.deepEqual([...single.negative_queries], []);
    assert.equal(Object.hasOwn(single, "negative_weight"), false);
    assert.equal(single.use_feedback, true);
    assert.equal(single.input_mode, "preset");
    assert.equal(single.comparison_mode, "single");
  }
  assert.ok(calls[0].comparison_id);
  assert.equal(calls[0].comparison_id, calls[1].comparison_id);
});

test("cancel and per-axis selection changes prevent stale search results from publishing", async () => {
  const first = deferred(), second = deferred(), third = deferred(); const calls = [];
  const responses = [first, second, third];
  const h = harness({ textSearch: (payload) => { calls.push(payload); return responses[calls.length - 1].promise; } });
  let ui = h.render();
  await ui.handleTextSearch(h.requests); assert.equal(calls.length, 0);
  ui.togglePromptPreset("rhythm/first"); ui = h.render();
  const old = ui.handleTextSearch(h.requests);
  ui.cancelTextSearch(); ui = h.render();
  assert.equal(ui.textModelLoadingLabel, null);
  first.resolve(response("old")); await old;
  assert.equal(h.commits.filter((c) => c.results.length).length, 0);
  const stale = ui.handleTextSearch(h.requests);
  ui.togglePromptPreset("bass/first"); ui = h.render();
  ui.togglePromptPreset("rhythm/second"); ui = h.render();
  assert.deepEqual([...ui.selectedPresetKeys].sort(), ["bass/first", "rhythm/second"]);
  second.resolve(response("stale")); await stale;
  assert.equal(h.commits.filter((c) => c.results.length).length, 0);
  const newer = ui.handleTextSearch(h.requests);
  assert.deepEqual([...calls[2].preset_banks.map((bank) => bank.key)].sort(), ["bass/first", "rhythm/second"]);
  third.resolve(response("new")); await newer;
  ui = h.render(); assert.equal(ui.textFeedbackContext.run_id, "new");
  ui.togglePromptPreset("rhythm/second"); ui = h.render();
  assert.deepEqual([...ui.selectedPresetKeys], ["bass/first"]);
  ui.clearPromptPresets(); ui = h.render();
  assert.deepEqual([...ui.selectedPresetKeys], []);
});

test("feedback uses each executed A/B run, serializes revisions and ignores stale completions", async () => {
  for (const [family, invalidate] of [
    ["mulan", (ui) => ui.cancelTextSearch()],
    ["clap", (ui) => ui.togglePromptPreset("rhythm/second")],
    ["mulan", (ui) => ui.changeTextEmbeddingFamily("clap")],
  ]) {
    const lookups = { "run-mulan": deferred(), "run-clap": deferred() };
    const mutation = deferred(); const calls = [], lookupCalls = [];
    const h = harness({ textSearch: async (payload) => response(`run-${payload.analysis_family}`, "ready"),
      textSearchFeedbackLookup: (payload) => { lookupCalls.push(payload); return lookups[payload.run_id].promise; },
      textSearchFeedback: (payload) => { calls.push(payload); return mutation.promise; } });
    let ui = h.render(); ui.togglePromptPreset("rhythm/first"); ui.setTextCompareModels(true); ui = h.render();
    await ui.handleTextSearch(h.requests); ui = h.render();
    assert.deepEqual(lookupCalls.map((payload) => payload.run_id).sort(), ["run-clap", "run-mulan"]);
    for (const payload of lookupCalls) assert.deepEqual([...payload.track_uuids], ["track"]);
    await ui.handleTextResultFeedback({ track_uuid: "track" }, 1, family); assert.equal(calls.length, 0);
    const runId = `run-${family}`;
    lookups[runId].resolve({ query_key: "query", verdicts: { track: { verdict: 1, revision: 4 } } });
    await flush(); ui = h.render();
    const updating = ui.handleTextResultFeedback({ track_uuid: "track" }, 1, family);
    await ui.handleTextResultFeedback({ track_uuid: "track" }, -1, family);
    assert.equal(calls.length, 1);
    assert.deepEqual({ ...calls[0] }, { run_id: runId, track_uuid: "track", expected_revision: 4, verdict: 0 });
    invalidate(ui); h.render();
    // The other arm's lookup and this arm's write both finish after invalidation.
    const otherRunId = family === "clap" ? "run-mulan" : "run-clap";
    lookups[otherRunId].resolve({ query_key: "query", verdicts: { track: { verdict: -1, revision: 2 } } });
    mutation.resolve({ query_key: "query", track_uuid: "track", verdict: 0, revision: 5 });
    await updating; await flush(); ui = h.render();
    assert.equal(Object.keys(ui.textFeedbackVerdicts).length, 0);
    assert.equal(Object.keys(ui.feedbackReady).length, 0);
    assert.equal(Object.keys(ui.executions).length, 0);
    assert.equal(Object.keys(ui.feedbackPending).length, 0);
  }
});
