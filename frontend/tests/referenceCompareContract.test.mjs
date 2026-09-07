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
  const controller = new AbortController();
  const calls = [];
  const { api } = loadApiModule(async (path, options) => {
    calls.push({ path, options });
    return jsonResponse({ seed_track_id: 7, groups: [] });
  });

  await api.referenceCompare({ seed_track_id: 7, models: ["clap", "muq", "sonara"], limit: 12 }, { signal: controller.signal });

  assert.equal(calls[0].path, "/api/reference/compare");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.signal, controller.signal);
  assert.deepEqual(JSON.parse(calls[0].options.body), { seed_track_id: 7, models: ["clap", "muq", "sonara"], limit: 12 });
});

test("reference compare verdict client stores MuQ verdict with exact identities and notes", async () => {
  const controller = new AbortController();
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
    },
    candidate: {
      track_id: 9,
      catalog_uuid: "catalog-a",
      track_uuid: "candidate-uuid",
    },
    model: "muq",
    verdict: "palette",
    notes: "shared acoustic palette",
  }, { signal: controller.signal });

  assert.equal(calls[0].path, "/api/reference/compare/verdict");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.signal, controller.signal);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    seed: {
      track_id: 3,
      catalog_uuid: "catalog-a",
      track_uuid: "seed-uuid",
    },
    candidate: {
      track_id: 9,
      catalog_uuid: "catalog-a",
      track_uuid: "candidate-uuid",
    },
    model: "muq",
    verdict: "palette",
    notes: "shared acoustic palette",
  });
});

// Execute the component and client; only hooks, the clock, and transport are
// controlled. Fetch intentionally can finish after abort to expose stale writes.
function panelHarness() {
  const cells = [];
  const effects = [];
  const timers = new Map();
  const intervals = new Map();
  const requests = [];
  let cursor = 0;
  let timerId = 0;
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!(index in cells)) cells[index] = initial;
      return [cells[index], (value) => {
        cells[index] = typeof value === "function" ? value(cells[index]) : value;
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in cells)) cells[index] = { current: initial };
      return cells[index];
    },
    useEffect(effect, dependencies) {
      const index = cursor++;
      const previous = cells[index];
      if (!previous || !dependencies || dependencies.some((value, key) => value !== previous.dependencies[key])) {
        effects.push(() => {
          previous?.cleanup?.();
          cells[index] = { dependencies, cleanup: effect() };
        });
      }
    },
  };
  const clock = {
    setTimeout(callback, delay) {
      assert.ok(Number.isFinite(delay) && delay > 0, "waiting must have a finite deadline");
      timers.set(++timerId, callback);
      return timerId;
    },
    clearTimeout(id) { timers.delete(id); },
    setInterval(callback) { intervals.set(++timerId, callback); return timerId; },
    clearInterval(id) { intervals.delete(id); },
  };
  const { api } = loadApiModule((path, options) => new Promise((resolve, reject) => {
    requests.push({ path, options, resolve: (body) => resolve(jsonResponse(body)), reject });
  }));
  const element = (type, props) => ({ type, props });
  const searchSurface = { exports: {} };
  vm.runInNewContext(ts.transpileModule(readFileSync(join(srcDir, "searchSurfaceState.ts"), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { module: searchSurface, exports: searchSurface.exports });
  const dependencies = {
    react: hooks,
    "react/jsx-runtime": { jsx: element, jsxs: element },
    "lucide-react": new Proxy({}, { get: () => () => null }),
    "./api": { api },
    "./TrackRows": { ResultRow: () => null },
    "./trackDisplay": { displayTrack: (track) => track.title },
    "./searchSurfaceState": searchSurface.exports,
  };
  const module = { exports: {} };
  const compiled = ts.transpileModule(readFileSync(join(srcDir, "ReferenceComparePanel.tsx"), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(compiled, {
    module, exports: module.exports, Error, AbortController, DOMException, ...clock, window: clock,
    require(name) {
      assert.ok(name in dependencies, `Unexpected dependency: ${name}`);
      return dependencies[name];
    },
  });
  const props = {
    seedTracks: [{ track_id: 7, catalog_uuid: "catalog-a", track_uuid: "seed-a", title: "Seed" }],
    busy: false, seedSet: new Set(), playlistSet: new Set(), playingTrackId: null, previewTrackId: null,
    onSeed() {}, onToggleLiked() {}, onTogglePlaylist() {}, onPreview() {}, onSeekPreview() {}, onDetails() {}, onActivity() {},
  };
  function render() {
    cursor = 0;
    const tree = module.exports.ReferenceComparePanel(props);
    if (effects.length) {
      effects.splice(0).forEach((effect) => effect());
      return render();
    }
    return tree;
  }
  function nodes(tree) {
    if (!tree || typeof tree !== "object") return [];
    if (Array.isArray(tree)) return tree.flatMap(nodes);
    if (typeof tree.type === "function") return nodes(tree.type(tree.props));
    return [tree, ...nodes(tree.props?.children)];
  }
  const all = () => nodes(render());
  const text = (value) => typeof value === "string" ? value : Array.isArray(value)
    ? value.map(text).join(" ") : value && typeof value === "object" ? text(value.props?.children) : "";
  return {
    props, requests, timers, intervals, all,
    action(pattern) {
      const button = all().find((node) => node.type === "button" && pattern.test(text(node.props.children)));
      assert.ok(button, `Missing action: ${pattern}`);
      return button.props;
    },
    verdicts: () => all().filter((node) => node.type === "button" && "aria-pressed" in node.props),
    expire() {
      assert.ok(timers.size > 0, "pending requests need a deadline");
      const callbacks = [...timers.values()];
      timers.clear();
      callbacks.forEach((callback) => callback());
    },
    unmount() { cells.forEach((cell) => cell?.cleanup?.()); },
  };
}

test("reference panel restores saved verdicts and rejects late compare and verdict results", async () => {
  const panel = panelHarness();
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  const candidate = { track_id: 9, catalog_uuid: "catalog-a", track_uuid: "candidate-a", title: "Candidate" };
  const response = {
    seed_track_id: 7,
    groups: [{ model: "muq", available: true, reason: null, results: [{ target: candidate, track: candidate, score: 0.8, score_breakdown: null, saved_verdict: "palette" }] }],
  };
  const run = () => panel.action(/compare/i).onClick();
  try {
    run();
    assert.equal(panel.requests.length, 1);
    assert.equal(panel.action(/compar/i).disabled, true);
    assert.ok(panel.requests[0].options.signal, "pending comparison must support cancellation");
    assert.equal(panel.requests[0].options.signal.aborted, false);
    panel.action(/cancel/i).onClick();
    assert.equal(panel.requests[0].options.signal.aborted, true);
    assert.equal(panel.action(/compare/i).disabled, false);
    assert.equal(panel.timers.size, 0);
    panel.requests[0].resolve(response);
    await flush();
    assert.equal(panel.verdicts().length, 0, "cancelled response must not repopulate results");

    run();
    panel.expire();
    await flush();
    assert.equal(panel.requests[1].options.signal.aborted, true);
    assert.equal(panel.action(/compare/i).disabled, false);
    assert.ok(panel.all().some((node) => node.props.role === "alert"), "deadline must explain failure");
    panel.requests[1].resolve(response);
    await flush();
    assert.equal(panel.verdicts().length, 0);

    run();
    panel.requests[2].reject(new Error("synthetic transport failure"));
    await flush();
    assert.equal(panel.action(/compare/i).disabled, false);
    assert.ok(panel.all().some((node) => node.props.children === "synthetic transport failure"));
    assert.equal(panel.timers.size, 0);

    run();
    panel.requests[3].resolve(response);
    await flush();
    assert.ok(panel.verdicts().length > 0, "completed comparison must display candidates");
    assert.equal(panel.action(/compare/i).disabled, false);
    assert.equal(panel.timers.size, 0);
    const restored = panel.verdicts().filter((node) => node.props["aria-pressed"]);
    assert.equal(restored.length, 1, "accepted comparison must restore its saved verdict");
    restored[0].props.onClick();
    assert.equal(panel.requests[4].path, "/api/reference/compare/verdict");
    const restoredPayload = JSON.parse(panel.requests[4].options.body);
    assert.equal(restoredPayload.verdict, "palette");
    assert.equal(restoredPayload.model, "muq");
    assert.deepEqual(restoredPayload.candidate, {
      track_id: candidate.track_id, catalog_uuid: candidate.catalog_uuid, track_uuid: candidate.track_uuid,
    });
    assert.ok(panel.verdicts().every((node) => node.props.disabled));

    run();
    assert.equal(panel.requests[4].options.signal.aborted, true, "a new comparison invalidates old verdict saves");
    panel.requests[5].resolve({
      ...response,
      groups: [{ ...response.groups[0], results: [{ ...response.groups[0].results[0], saved_verdict: "groove" }] }],
    });
    await flush();
    panel.requests[4].resolve({ id: 1, source: "reference_compare:muq" });
    await flush();
    const refreshed = panel.verdicts().filter((node) => node.props["aria-pressed"]);
    assert.equal(refreshed.length, 1);
    assert.ok(panel.verdicts().every((node) => !node.props.disabled));
    refreshed[0].props.onClick();
    assert.equal(JSON.parse(panel.requests[6].options.body).verdict, "groove", "late save must not replace the refreshed verdict");
    panel.requests[6].resolve({ id: 1, source: "reference_compare:muq" });
    await flush();

    run();
    panel.props.seedTracks = [{ ...panel.props.seedTracks[0], catalog_uuid: "catalog-b" }];
    panel.all();
    assert.equal(panel.requests[7].options.signal.aborted, true);
    panel.requests[7].resolve(response);
    await flush();
    assert.equal(panel.verdicts().length, 0, "same numeric ID in another catalog is a different seed");
    assert.equal(panel.action(/compare/i).disabled, false);

    run();
    panel.all();
    panel.unmount();
    assert.equal(panel.requests[8].options.signal.aborted, true);
    assert.equal(panel.timers.size, 0);
    assert.equal(panel.intervals.size, 0);
  } finally {
    panel.unmount();
  }
});
