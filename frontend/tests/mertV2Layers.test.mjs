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
  const compiled = ts.transpileModule(readFileSync(new URL("../src/useMertV2Layers.ts", import.meta.url), "utf8"), {
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
      const value = module.exports.useMertV2Layers(identity, catalog, layerOrRefresh);
      const pending = effects; effects = []; pending.forEach(fn => fn());
      return value;
    },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

test("MERT-v2 layer coverage binds selection and pending requests to the current catalog", async () => {
  const coverageCalls = [];
  const coverage = harness({ mertV2Layers(options) { const task = deferred(); coverageCalls.push({ options, ...task }); return task.promise; } });
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
