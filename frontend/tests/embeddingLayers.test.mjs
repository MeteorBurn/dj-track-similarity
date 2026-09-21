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

function harness(api) {
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
  const compiled = ts.transpileModule(readFileSync(new URL("../src/useEmbeddingLayers.ts", import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(compiled, { module, exports: module.exports, AbortController,
    require: name => name === "react" ? react : name === "./api" ? { api } : {
      errorText: error => error.message, isAbortError: error => error.name === "AbortError",
    },
  });
  return {
    render(family = "muq", identity = "db-a", catalog = "a", refresh = 0) {
      cursor = 0;
      const value = module.exports.useEmbeddingLayers(family, identity, catalog, refresh);
      const pending = effects; effects = []; pending.forEach(fn => fn());
      return value;
    },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

test("embedding layer coverage binds selection and pending requests to the current family and catalog", async () => {
  const coverageCalls = [];
  const coverage = harness({ embeddingLayers(family, options) { const task = deferred(); coverageCalls.push({ family, options, ...task }); return task.promise; } });
  const flush = () => new Promise(resolve => setImmediate(resolve));
  const counts = (catalog_uuid, count, stored) => ({ catalog_uuid, default_layer: count, note: null,
    layers: Array.from({ length: count }, (_, i) => ({ layer: i + 1, track_count: stored.includes(i + 1) ? 10 : 0, label: null, source: null })) });
  let picker = coverage.render();
  assert.equal(coverageCalls[0].family, "muq");
  assert.equal(picker.layer, null);
  coverageCalls[0].resolve(counts("a", 13, [7, 13])); await flush();
  picker = coverage.render();
  assert.equal(picker.layer, 13);
  picker.selectLayer(1); picker = coverage.render();
  assert.equal(picker.layer, 13);
  picker.selectLayer(7); picker = coverage.render();
  assert.equal(picker.layer, 7);
  assert.equal(picker.trackCount, 10);
  coverage.render("muq", "db-a", "a", "first-refresh");
  coverageCalls.at(-1).resolve(counts("a", 13, [7, 13])); await flush();
  picker = coverage.render("muq", "db-a", "a", "first-refresh");
  assert.equal(picker.layer, 7);
  coverage.render("muq", "db-a", "a", "refreshed-summary");
  const outdatedCoverage = coverageCalls.at(-1);
  picker = coverage.render("muq", "db-b", "b", "refreshed-summary");
  assert.equal(picker.layer, null);
  assert.equal(picker.layers, null);
  assert.equal(outdatedCoverage.options.signal.aborted, true);
  outdatedCoverage.resolve(counts("a", 13, [7, 13])); await flush();
  picker = coverage.render("muq", "db-b", "b", "refreshed-summary");
  assert.equal(picker.layers, null);
  coverageCalls.at(-1).resolve(counts("b", 13, [13])); await flush();
  picker = coverage.render("muq", "db-b", "b", "refreshed-summary");
  assert.equal(picker.layers.length, 13);
  assert.equal(picker.layer, 13);
  const callsBeforeClap = coverageCalls.length;
  picker = coverage.render("clap", "db-b", "b", "refreshed-summary");
  assert.equal(picker.layered, false);
  assert.equal(picker.layer, null);
  assert.equal(coverageCalls.length, callsBeforeClap);
  picker = coverage.render("mert_v2", "db-b", "b", "refreshed-summary");
  assert.equal(coverageCalls.at(-1).family, "mert_v2");
  coverageCalls.at(-1).resolve(counts("b", 24, [12, 24])); await flush();
  picker = coverage.render("mert_v2", "db-b", "b", "refreshed-summary");
  assert.equal(picker.layer, 24);
  coverage.unmount();
});
