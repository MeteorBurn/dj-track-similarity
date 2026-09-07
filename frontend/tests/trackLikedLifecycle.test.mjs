import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const flush = () => new Promise((done) => setImmediate(done));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function harness() {
  const slots = [];
  let cursor = 0;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
      return [slots[index], (value) => {
        slots[index] = typeof value === "function" ? value(slots[index]) : value;
      }];
    },
    useRef(initial) { return slots[cursor++] ??= { current: initial }; },
    useMemo: (fn) => fn(),
    useCallback: (fn) => fn,
    useEffect: () => {},
  };
  let catalog = "A";
  let mutation;
  const likeCalls = [];
  const api = {
    chooseDatabase: async () => ({ selected: true, path: `${catalog}.sqlite`, catalog_uuid: catalog }),
    classifiers: async () => [],
    tracks: async () => ({ items: [], total: 0, offset: 0, limit: 200 }),
    librarySummary: async () => ({}),
    latestScanJob: async () => null,
    latestAnalysisJob: async () => null,
    latestAnalysisPipeline: async () => null,
    genreTagJobLatest: async () => null,
    latestDatabaseValidationJob: async () => null,
    latestDatabaseOptimizationJob: async () => null,
    setTrackLiked: (...args) => { likeCalls.push(args); return mutation.promise; },
  };
  const modules = new Map();
  const src = fileURLToPath(new URL("../src/", import.meta.url));
  function load(name, from = src) {
    if (name === "react") return react;
    if (name === "react/jsx-runtime") {
      const jsx = (type, props) => ({ type, props });
      return { jsx, jsxs: jsx, Fragment: "fragment" };
    }
    if (name === "lucide-react") return {};
    if (name === "./api" || name === "./apiClient") return { api };
    const base = resolve(from, name);
    const path = [base, `${base}.ts`, `${base}.tsx`].find((candidate) => existsSync(candidate));
    if (!path) throw new Error(`Missing module ${name}`);
    if (modules.has(path)) return modules.get(path);
    const module = { exports: {} };
    modules.set(path, module.exports);
    const compiled = ts.transpileModule(readFileSync(path, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
    }).outputText;
    vm.runInNewContext(compiled, {
      module, exports: module.exports, require: (name) => load(name, dirname(path)),
      console, crypto, AbortController, Error, setTimeout, clearTimeout,
      window: { localStorage: { getItem: () => null } },
    });
    return module.exports;
  }
  const { App } = load("./App");
  function find(node, name) {
    if (node?.type?.name === name || (name === "notice" && node?.props?.className?.startsWith("notice "))) return node.props;
    const children = node?.props?.children;
    for (const child of Array.isArray(children) ? children.flat(Infinity) : [children]) {
      if (child && typeof child === "object") {
        const found = find(child, name);
        if (found) return found;
      }
    }
  }
  function render() {
    cursor = 0;
    const tree = App();
    return { library: find(tree, "LibraryPanel"), search: find(tree, "SearchPlaylistPanel"), notice: find(tree, "notice").children };
  }
  async function choose(nextCatalog, rerender = true) {
    catalog = nextCatalog;
    render().library.onChooseDatabase();
    await flush();
    return rerender ? render() : undefined;
  }
  return { render, choose, likeCalls, startMutation: () => (mutation = deferred()) };
}

test("like responses only update tracks in the current catalog with matching identity", async () => {
  const h = harness();
  const track = { track_id: 1, catalog_uuid: "A", track_uuid: "a", file_path: "a.wav", liked: false };
  let ui = await h.choose("A");
  assert.equal(ui.library.databasePath, "A.sqlite");
  assert.equal(ui.library.busy, false);
  ui.search.togglePlaylist(track);
  ui.search.addSeed(track);
  const pending = h.startMutation();
  const result = ui.search.toggleLiked(track);
  ui = await h.choose("B");
  const other = { ...track, catalog_uuid: "B", track_uuid: "b" };
  ui.search.togglePlaylist(other);
  ui.search.addSeed(other);
  pending.resolve({ ...track, liked: true });
  assert.equal(await result, null);
  ui = h.render();
  assert.equal(ui.search.playlist[0], other);
  assert.equal(ui.search.seedTracks[0], other);

  const valid = h.startMutation();
  const validResult = ui.search.toggleLiked(other);
  const updated = { ...other, liked: true };
  valid.resolve(updated);
  assert.equal(await validResult, updated);
  ui = h.render();
  assert.equal(ui.search.playlist[0], updated);
  assert.equal(ui.search.seedTracks[0], updated);

  // A row replaced by another UUID in the same catalog must not be overwritten.
  const replacement = { ...other, track_uuid: "replacement" };
  ui.search.togglePlaylist(updated);
  ui = h.render();
  ui.search.togglePlaylist(replacement);
  ui.search.addSeed(replacement);
  const sameId = h.startMutation();
  const sameIdResult = ui.search.toggleLiked(other);
  sameId.resolve(updated);
  await sameIdResult;
  ui = h.render();
  assert.equal(ui.search.playlist[0], replacement);
  assert.equal(ui.search.seedTracks[0], replacement);

  const wrongIdentity = h.startMutation();
  const wrongResult = ui.search.toggleLiked(replacement);
  wrongIdentity.resolve(updated);
  assert.equal(await wrongResult, null);

  // Reset invalidates callbacks immediately, before React renders the new catalog.
  const staleError = h.startMutation();
  const staleErrorResult = ui.search.toggleLiked(replacement);
  await h.choose("C", false);
  staleError.reject(new Error("old catalog failed"));
  assert.equal(await staleErrorResult, null);
  ui = h.render();
  assert.equal(ui.library.databasePath, "C.sqlite");
  assert.equal(ui.library.busy, false);
  assert.notEqual(ui.notice, "old catalog failed");
  const callCount = h.likeCalls.length;
  assert.equal(await ui.search.toggleLiked(replacement), null);
  assert.equal(h.likeCalls.length, callCount);
});
