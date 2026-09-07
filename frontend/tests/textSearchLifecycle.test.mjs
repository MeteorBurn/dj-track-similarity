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
  const options = { databasePath: "synthetic.sqlite", databaseCatalogUuid: "catalog", textQuery: "breakbeat.",
    setTextQuery: (value) => { options.textQuery = value; }, filters: { limit: 10 }, analysisDevice: "cpu",
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

test("A/B preserves successful arm when sibling fails and snapshots a shared override", async () => {
  const first = deferred(), second = deferred(); const calls = [];
  const h = harness({ textSearch: (payload) => { calls.push(payload); return calls.length === 1 ? first.promise : second.promise; } });
  let ui = h.render(); ui.applyPromptPresets(["rhythm/breakbeat"]); ui.setTextCompareModels(true); ui.setNegativeWeightOverride(0.75);
  ui = h.render(); const running = ui.handleTextSearch(h.requests);
  first.resolve(response()); await flush();
  ui = h.render();
  assert.equal(ui.textComparison[0].status, "success");
  assert.equal(ui.textComparison[1].status, "pending");
  second.reject(new Error("unavailable")); await running;
  ui = h.render();
  assert.equal(ui.textComparison[1].status, "error");
  assert.equal(h.commits.at(-1).results.length, 1);
  assert.equal(calls[0].negative_weight, 0.75); assert.equal(calls[1].negative_weight, 0.75);
  assert.equal(calls.every((p) => p.use_feedback === false), true);
  ui.applyPromptPresets(["rhythm/breakbeat"]); ui = h.render();
  assert.equal(ui.negativeWeightOverride, null);
});

test("cancel and input changes prevent old completions from publishing", async () => {
  const first = deferred(), second = deferred(); let n = 0;
  const h = harness({ textSearch: () => ++n === 1 ? first.promise : second.promise });
  let ui = h.render(); const old = ui.handleTextSearch(h.requests);
  ui.cancelTextSearch(); ui = h.render();
  assert.equal(ui.textModelLoadingLabel, null);
  ui.changeTextQuery("piano."); ui = h.render(); const newer = ui.handleTextSearch(h.requests);
  first.resolve(response("old")); await old;
  assert.equal(h.commits.filter((c) => c.results.length).length, 0);
  second.resolve(response("new")); await newer;
  ui = h.render(); assert.equal(ui.textFeedbackContext.run_id, "new");
});

test("feedback waits for revisions, withdraws the known verdict and serializes clicks", async () => {
  const lookup = deferred(), mutation = deferred(); const calls = [];
  const h = harness({ textSearch: async () => response("run", "ready"), textSearchFeedbackLookup: () => lookup.promise,
    textSearchFeedback: (payload) => { calls.push(payload); return mutation.promise; } });
  let ui = h.render(); await ui.handleTextSearch(h.requests); ui = h.render();
  await ui.handleTextResultFeedback({ track_uuid: "track" }, 1, "mulan"); assert.equal(calls.length, 0);
  lookup.resolve({ query_key: "query", verdicts: { track: { verdict: 1, revision: 4 } } }); await flush(); ui = h.render();
  const updating = ui.handleTextResultFeedback({ track_uuid: "track" }, 1, "mulan");
  await ui.handleTextResultFeedback({ track_uuid: "track" }, -1, "mulan");
  assert.equal(calls.length, 1); assert.equal(calls[0].expected_revision, 4); assert.equal(calls[0].verdict, 0);
  ui.cancelTextSearch();
  mutation.resolve({ query_key: "query", track_uuid: "track", verdict: 0, revision: 5 }); await updating;
  ui = h.render(); assert.equal(Object.keys(ui.textFeedbackVerdicts).length, 0);
});
