import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function harness(api, hook = "useMertV2Explorer") {
  const slots = []; let cursor = 0; let effects = [];
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
    },
    useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
    useEffect(fn, deps) {
      const index = cursor++, old = slots[index];
      if (!old || deps.some((value, i) => !Object.is(value, old.deps[i]))) {
        slots[index] = { deps, cleanup: old?.cleanup };
        effects.push(() => { old?.cleanup?.(); slots[index].cleanup = fn(); });
      }
    },
  };
  const module = { exports: {} };
  const compiled = ts.transpileModule(readFileSync(new URL(`../src/${hook}.ts`, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(compiled, { module, exports: module.exports, AbortController,
    require: name => name === "react" ? react : name === "./api" ? { api } : {
      errorText: error => error.message, isAbortError: error => error.name === "AbortError",
    },
  });
  return {
    render(identity = "db-a", catalog = "a", layerOrRefresh = 24) {
      cursor = 0;
      const value = module.exports[hook](identity, catalog, layerOrRefresh);
      const pending = effects; effects = []; pending.forEach(fn => fn());
      return value;
    },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

function response(catalog = "a", uuid = "track-a", layer = 24) {
  return { catalog_uuid: catalog, analysis_family: "mert_v2", mert_v2_layer: layer, eligible_count: 1,
    requested_cluster_count: 8, cluster_count: 1,
    projection: { method: "pca", explained_variance_ratio: [1, 0] },
    clusters: [{ id: 0, count: 1, representative_track_id: 1 }],
    points: [{ track: { track_id: 1, track_uuid: uuid, catalog_uuid: catalog, liked: false }, x: 0, y: 0, cluster: 0 }],
  };
}

test("map requests bind catalog, replace stale work, and preserve track identity through actions", async () => {
  const calls = [];
  const h = harness({ embeddingMap(payload, options) { const task = deferred(); calls.push({ payload, options, ...task }); return task.promise; } });
  let ui = h.render();
  const first = ui.buildMap(8);
  assert.equal(JSON.stringify(calls[0].payload), JSON.stringify({ catalog_uuid: "a", analysis_family: "mert_v2", cluster_count: 8, mert_v2_layer: 24 }));
  calls[0].resolve(response()); await first;
  ui = h.render();
  const original = ui.data.points[0].track;
  assert.equal(ui.currentTrack(original), original);
  assert.equal(ui.currentTrack({ ...original, track_uuid: "reused-id" }), null);
  assert.equal(ui.currentTrack({ ...original, catalog_uuid: "other" }), null);
  ui.updateTrack({ ...original, liked: true }); ui = h.render();
  assert.equal(ui.data.points[0].track.liked, true);
  const oldUi = ui;
  const second = ui.buildMap(2);
  ui = h.render();
  assert.equal(ui.data, null);
  assert.equal(oldUi.currentTrack(original), null);
  const newer = ui.buildMap(3);
  assert.equal(calls[1].options.signal.aborted, true);
  calls[2].resolve(response("a", "replacement")); await newer;
  calls[1].resolve(response()); await second;
  ui = h.render();
  assert.equal(ui.data.points[0].track.track_uuid, "replacement");
  const oldCatalogUi = ui;
  const switching = ui.buildMap(8);
  ui = h.render("db-b", "b");
  assert.equal(ui.data, null);
  assert.equal(oldCatalogUi.currentTrack(original), null);
  assert.equal(calls[3].options.signal.aborted, true);
  calls[3].resolve(response()); await switching;
  ui = h.render("db-b", "b");
  assert.equal(ui.data, null);
  const wrongCatalog = ui.buildMap(8);
  calls[4].resolve(response()); await wrongCatalog;
  ui = h.render("db-b", "b");
  assert.match(ui.error, /different catalog/);
  assert.equal(ui.data, null);
  const failed = ui.buildMap(8);
  calls[5].reject(new Error("Unavailable")); await failed;
  ui = h.render("db-b", "b");
  assert.equal(ui.pending, false);
  assert.equal(ui.error, "Unavailable");
  const switchingLayer = ui.buildMap(8);
  const staleLayerCall = calls.at(-1);
  ui = h.render("db-b", "b", 12);
  assert.equal(staleLayerCall.options.signal.aborted, true);
  staleLayerCall.resolve(response("b")); await switchingLayer;
  ui = h.render("db-b", "b", 12);
  assert.equal(ui.data, null);
  const newLayer = ui.buildMap(8);
  assert.equal(calls.at(-1).payload.mert_v2_layer, 12);
  calls.at(-1).resolve(response("b", "layer-12", 12)); await newLayer;
  ui = h.render("db-b", "b", 12);
  assert.equal(ui.data.mert_v2_layer, 12);
  const unmounting = ui.buildMap(8);
  h.unmount();
  assert.equal(calls.at(-1).options.signal.aborted, true);
  calls.at(-1).resolve(response("b", "layer-12", 12)); await unmounting;

  const coverageCalls = [];
  const coverage = harness({ mertV2Layers(options) { const task = deferred(); coverageCalls.push({ options, ...task }); return task.promise; } }, "useMertV2Layers");
  const flush = () => new Promise(resolve => setImmediate(resolve));
  const counts = catalog_uuid => ({ catalog_uuid, layers: Array.from({ length: 24 }, (_, i) => ({ layer: i + 1, track_count: [12, 24].includes(i + 1) ? 10 : 0 })) });
  let picker = coverage.render();
  coverageCalls[0].resolve(counts("a")); await flush();
  picker = coverage.render();
  picker.selectLayer(1); picker = coverage.render();
  assert.equal(picker.layer, 24);
  picker.selectLayer(12); picker = coverage.render();
  assert.equal(picker.layer, 12);
  assert.equal(picker.trackCount, 10);
  coverage.render("db-a", "a", "refreshed-summary");
  const outdatedCoverage = coverageCalls.at(-1);
  picker = coverage.render("db-b", "b", "refreshed-summary");
  assert.equal(picker.layer, 24);
  assert.equal(picker.layers, null);
  assert.equal(outdatedCoverage.options.signal.aborted, true);
  outdatedCoverage.resolve(counts("a")); await flush();
  picker = coverage.render("db-b", "b", "refreshed-summary");
  assert.equal(picker.layers, null);
  coverageCalls.at(-1).resolve(counts("b")); await flush();
  picker = coverage.render("db-b", "b", "refreshed-summary");
  assert.equal(picker.layers.length, 24);
  coverage.unmount();
});
