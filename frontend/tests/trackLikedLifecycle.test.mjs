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

function textContent(node) {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textContent).join("");
  return node?.props ? textContent(node.props.children) : "";
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
  const switchCalls = [];
  const api = {
    databaseDialog: async () => ({ path: `${catalog}.sqlite`, exists: true }),
    switchDatabase: async (path, options) => {
      switchCalls.push([path, options.create]);
      return { selected: true, path, catalog_uuid: catalog };
    },
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
    return {
      library: find(tree, "LibraryPanel"), search: find(tree, "SearchPlaylistPanel"),
      confirmation: find(tree, "ConfirmationDialog"), notice: textContent(find(tree, "notice").children),
    };
  }
  async function choose(nextCatalog, rerender = true) {
    catalog = nextCatalog;
    render().library.onChooseDatabase();
    await flush();
    return rerender ? render() : undefined;
  }
  return { render, choose, likeCalls, switchCalls, api, startMutation: () => (mutation = deferred()) };
}

test("a missing library file is opened only after confirmation, and then created", async () => {
  const h = harness();
  await h.choose("A");
  assert.deepEqual(h.switchCalls, [["A.sqlite", false]]);
  h.api.databaseDialog = async () => ({ path: "B.sqlite", exists: false });

  let ui = await h.choose("B");
  const notice = ui.notice;
  assert.ok(ui.confirmation, "a missing file asks before anything is created");
  assert.equal(h.switchCalls.length, 1, "no switch before the answer");
  ui.confirmation.onCancel();
  ui = h.render();
  assert.equal(ui.confirmation, undefined);
  assert.equal(h.switchCalls.length, 1);
  assert.equal(ui.library.databasePath, "A.sqlite");
  assert.equal(ui.notice, notice);

  ui = await h.choose("B");
  ui.confirmation.onConfirm();
  await flush();
  ui = h.render();
  assert.deepEqual(h.switchCalls.at(-1), ["B.sqlite", true]);
  assert.equal(ui.library.databasePath, "B.sqlite");
  assert.equal(ui.library.busy, false);
});

test("genres are written into the source audio files only after confirmation", async () => {
  const h = harness();
  const genreStarts = [];
  h.api.librarySummary = async () => ({ maest_analysis: 3 });
  h.api.genreTagJobStart = async () => {
    genreStarts.push(true);
    return { job_id: "genre-job", total: 3, status: "running", events: [], errors: [] };
  };
  let ui = await h.choose("A");

  ui.library.onWriteMaestGenres();
  ui = h.render();
  assert.ok(ui.confirmation, "writing into source files asks first");
  assert.equal(genreStarts.length, 0, "nothing is written before the answer");
  ui.confirmation.onCancel();
  ui = h.render();
  assert.equal(ui.confirmation, undefined);
  assert.equal(genreStarts.length, 0, "a declined write never starts");

  ui.library.onWriteMaestGenres();
  h.render().confirmation.onConfirm();
  await flush();
  assert.equal(genreStarts.length, 1);
});

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

  const comparison = harness();
  const secondArm = deferred();
  let searches = 0;
  const searchResponse = { results: [{ track, score: 0.75 }], execution: { run_id: "run", feedback_capability: "absent" } };
  comparison.api.librarySummary = async () => ({ tracks: 1, sonara: 1, clap: 1, mulan: 1 });
  comparison.api.textSearch = async () => ++searches === 1 ? searchResponse : secondArm.promise;
  ui = await comparison.choose("A");
  ui.search.onTextCompareModelsChange(true);
  ui.search.onTogglePreset(ui.search.promptPresets[0].key);
  ui = comparison.render();
  ui.search.handleTextSearch();
  await flush();
  ui = comparison.render();
  const firstResult = ui.search.textComparison.find((arm) => arm.status === "success").results[0];
  const firstLike = comparison.startMutation();
  const likedResult = ui.search.toggleLiked(firstResult.track);
  firstLike.resolve({ ...track, liked: true });
  await likedResult;
  ui = comparison.render();
  assert.equal(ui.search.textComparison.find((arm) => arm.status === "success").results[0].track.liked, true);

  // The second response was captured before the like, and must not roll it back.
  secondArm.resolve(searchResponse);
  await flush();
  ui = comparison.render();
  assert.equal(ui.search.results[0].track.liked, true);
  for (const arm of ui.search.textComparison) {
    assert.equal(arm.results[0].track.liked, true);
    assert.equal(arm.results[0].score, 0.75);
  }
  const unlike = comparison.startMutation();
  const unlikedResult = ui.search.toggleLiked(ui.search.textComparison[0].results[0].track);
  unlike.resolve(track);
  await unlikedResult;
  ui = comparison.render();
  assert.deepEqual(comparison.likeCalls.map((args) => args[1]), [true, false]);
  for (const arm of ui.search.textComparison) assert.equal(arm.results[0].track.liked, false);

  const otherIdentity = { ...track, track_uuid: "replacement" };
  const replacedLike = comparison.startMutation();
  const replacedResult = ui.search.toggleLiked(otherIdentity);
  replacedLike.resolve({ ...otherIdentity, liked: true });
  await replacedResult;
  for (const arm of comparison.render().search.textComparison) assert.equal(arm.results[0].track.liked, false);

  // Returning to the same catalog must not revive an earlier session's mutation.
  for (const lateError of [false, true]) {
    const obsoleteLike = comparison.startMutation();
    const obsoleteResult = ui.search.toggleLiked(track);
    await comparison.choose("B");
    ui = await comparison.choose("A");
    ui.search.handleTextSearch();
    await flush();
    ui = comparison.render();
    const notice = ui.notice;
    if (lateError) obsoleteLike.reject(new Error("obsolete like error"));
    else obsoleteLike.resolve({ ...track, liked: true });
    assert.equal(await obsoleteResult, null);
    ui = comparison.render();
    assert.equal(ui.notice, notice);
    assert.equal(ui.search.results[0].track.liked, false);
    for (const arm of ui.search.textComparison) assert.equal(arm.results[0].track.liked, false);
  }
});

test("random seeds ignore obsolete catalog responses without clearing a newer request", async () => {
  for (const kind of ["Sonara", "Embedding"]) {
    for (const lateError of [false, true]) {
      const h = harness();
      const calls = [];
      h.api[`random${kind}Track`] = (payload, options) => {
        const pending = deferred();
        calls.push({ payload, signal: options?.signal, ...pending });
        return pending.promise;
      };
      const oldTrack = { track_id: 7, catalog_uuid: "A", track_uuid: "a7", file_path: "a.wav" };
      const currentTrack = { ...oldTrack, catalog_uuid: "B", track_uuid: "b7" };
      let ui = await h.choose("A");
      if (kind === "Embedding") {
        ui.search.onSeedSearchModelChange("clap");
        ui = h.render();
      }
      ui.search[`handleAddRandom${kind}Track`]();
      if (kind === "Embedding") assert.equal(calls[0].payload.analysis_family, "clap");
      await h.choose("B", false);
      assert.equal(calls[0].signal?.aborted, true, "database reset cancels before rerender");
      if (!lateError) {
        calls[0].resolve(oldTrack);
        await flush();
      }
      ui = h.render();
      assert.equal(ui.search.seedTracks.length, 0);
      ui.search[`handleAddRandom${kind}Track`]();
      const notice = h.render().notice;
      if (lateError) {
        calls[0].reject(new Error("obsolete catalog error"));
        await flush();
      }
      ui = h.render();
      assert.equal(ui.search.busy, true, "obsolete finally leaves the new request pending");
      assert.equal(ui.notice, notice);
      calls[1].resolve(currentTrack);
      await flush();
      ui = h.render();
      assert.deepEqual([...ui.search.seedTracks], [currentTrack]);
      assert.equal(ui.search.busy, false);

      ui.search.removeSeed(currentTrack.track_id);
      ui = h.render();
      ui.search[`handleAddRandom${kind}Track`]();
      calls[2].resolve(oldTrack);
      await flush();
      ui = h.render();
      assert.equal(ui.search.seedTracks.length, 0, "a current request must still validate the returned catalog");
      assert.equal(ui.search.busy, false);
    }
  }
});
