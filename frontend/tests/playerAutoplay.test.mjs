import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const flush = () => new Promise((resolve) => setImmediate(resolve));

function playbackHarness() {
  const slots = []; let cursor = 0; let effects = [];
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (value) => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
    },
    useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
    useEffect(fn, deps) {
      const index = cursor++; const old = slots[index];
      if (!old || deps.some((value, n) => !Object.is(value, old.deps[n]))) {
        slots[index] = { deps, cleanup: old?.cleanup };
        effects.push(() => { old?.cleanup?.(); slots[index].cleanup = fn(); });
      }
    },
  };
  class Audio {
    currentTime = 0; duration = Infinity; paused = true; ended = false;
    error = null; playCalls = 0; loadCalls = 0; listeners = new Map();
    constructor(src) { this.src = src; }
    addEventListener(name, fn) { this.listeners.set(name, fn); }
    removeEventListener(name, fn) { if (this.listeners.get(name) === fn) this.listeners.delete(name); }
    emit(name) { this.listeners.get(name)?.(); }
    play() { this.playCalls++; this.paused = false; this.emit("play"); return this.playResult ?? Promise.resolve(); }
    pause() { this.paused = true; this.emit("pause"); }
    load() { this.loadCalls++; this.currentTime = 0; this.ended = false; }
    getAttribute(name) { return this[name]; }
    removeAttribute(name) { this[name] = undefined; }
  }
  const h = { infos: [], ended: [], errors: [], audio: null, ui: null, key: null };
  const api = { previewInfo(trackId, { signal }) {
    const info = { trackId, signal, ...deferred() }; h.infos.push(info); return info.promise;
  } };
  const modules = new Map();
  function load(name) {
    if (name === "react") return react;
    if (name === "./api") return { api };
    if (modules.has(name)) return modules.get(name);
    const module = { exports: {} }; modules.set(name, module.exports);
    vm.runInNewContext(ts.transpileModule(readFileSync(new URL(`../src/${name.slice(2)}.ts`, import.meta.url), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText, { module, exports: module.exports, require: load, AbortController, Error });
    return module.exports;
  }
  const { useAudioPreview } = load("./useAudioPreview");
  h.position = load("./previewPosition").readPreviewPosition;
  h.options = {
    databaseKey: "catalog-A",
    onEnded(track) { h.ended.push(track.track_id); h.onEnd?.(track); },
    onError(message) { h.errors.push(message); },
  };
  h.render = () => {
    cursor = 0; h.ui = useAudioPreview(h.options);
    if (h.key !== h.ui.sourceKey || !h.ui.sourceUrl) {
      h.key = h.ui.sourceKey;
      h.audio = h.ui.sourceUrl ? new Audio(h.ui.sourceUrl) : null;
    }
    h.ui.previewAudioRef.current = h.audio;
    const queued = effects; effects = []; queued.forEach((fn) => fn());
    return h.ui;
  };
  h.unmount = () => { for (const slot of slots) slot?.cleanup?.(); };
  h.render();
  return h;
}

test("stream playback starts before metadata and uses the source timeline across seeks", async () => {
  const h = playbackHarness(); const track = { track_id: 7 };
  h.ui.togglePreview(track); h.render();
  assert.equal(h.audio.playCalls, 1, "unresolved metadata must not delay playback");
  assert.equal(h.audio.src, "/media/7?start=0");
  h.audio.currentTime = 7; h.audio.emit("timeupdate");
  assert.deepEqual({ ...h.position() }, { trackId: 7, currentTime: 7, duration: 0 });
  h.infos[0].resolve({ duration_seconds: 300 }); await flush();
  const originalAudio = h.audio;
  h.ui.seekPreview(track, 120); h.render();
  assert.equal(originalAudio.src, undefined, "seek releases the old response");
  assert.ok(originalAudio.loadCalls > 0);
  assert.equal(h.audio.src, "/media/7?start=120");
  assert.equal(h.audio.currentTime, 0, "never seek inside the nonseekable WAV response");
  h.audio.currentTime = 2; h.audio.duration = 180; h.audio.emit("durationchange");
  assert.deepEqual({ ...h.position() }, { trackId: 7, currentTime: 122, duration: 300 });
  h.audio.duration = Infinity; h.audio.emit("durationchange");
  assert.equal(h.position().duration, 300);
  assert.equal(h.infos.length, 1, "seeks retain the same source metadata");
  h.unmount();
});

test("paused and rapid seeks retain playback intent and reject stale media events", async () => {
  const h = playbackHarness(); const track = { track_id: 7 };
  h.ui.togglePreview(track); h.render();
  h.infos[0].resolve({ duration_seconds: 300 }); await flush();
  const oldAudio = h.audio; const stale = Object.fromEntries(oldAudio.listeners);
  h.ui.togglePreview(track); h.render();
  oldAudio.paused = false; stale.play();
  assert.equal(oldAudio.paused, true, "a late play event cannot override explicit pause");
  h.ui.seekPreview(track, 80); h.render();
  assert.equal(h.audio.playCalls, 0);
  assert.equal(h.ui.playingTrackId, null);
  assert.equal(h.position().currentTime, 80);
  h.ui.togglePreview(track); h.render();
  assert.equal(h.audio.playCalls, 1);
  h.ui.seekPreview(track, 100); h.ui.seekPreview(track, 120); h.render();
  assert.equal(h.audio.src, "/media/7?start=120");
  for (const name of ["pause", "ended", "error", "timeupdate"]) stale[name]();
  h.render();
  assert.equal(h.ui.playingTrackId, 7);
  assert.equal(h.position().currentTime, 120);
  assert.deepEqual(h.ended, []);
  assert.deepEqual(h.errors, []);
  h.unmount();
});

test("track changes, database changes, stop and unmount invalidate pending preview work", async () => {
  const h = playbackHarness();
  h.ui.togglePreview({ track_id: 1 }); h.render();
  const firstAudio = h.audio; const staleEnded = firstAudio.listeners.get("ended");
  h.ui.togglePreview({ track_id: 2 }); h.render();
  assert.equal(h.infos[0].signal.aborted, true);
  h.infos[0].resolve({ duration_seconds: 999 }); await flush(); staleEnded();
  assert.deepEqual({ ...h.position() }, { trackId: 2, currentTime: 0, duration: 0 });
  const secondAudio = h.audio;
  h.options.databaseKey = "catalog-B"; h.render(); h.render();
  assert.equal(secondAudio.src, undefined);
  assert.equal(h.infos[1].signal.aborted, true);
  h.ui.togglePreview({ track_id: 2 }); h.render();
  h.infos[1].resolve({ duration_seconds: 888 }); await flush();
  assert.equal(h.position().duration, 0, "same numeric id in another catalog is a new selection");
  h.ui.stopPreview(); h.render();
  assert.equal(h.infos[2].signal.aborted, true);
  h.infos[2].resolve({ duration_seconds: 777 }); await flush();
  assert.equal(h.position().trackId, null);
  h.ui.togglePreview({ track_id: 3 }); h.render(); const lastAudio = h.audio;
  h.unmount(); h.infos[3].resolve({ duration_seconds: 666 }); await flush();
  assert.equal(lastAudio.src, undefined);
  assert.equal(h.infos[3].signal.aborted, true);
  assert.equal(h.position().trackId, null);
  assert.deepEqual(h.ended, []);
});

test("actual end advances once, terminal seeks avoid empty streams, and play failures stop intent", async () => {
  const h = playbackHarness(); const track = { track_id: 7 };
  h.ui.togglePreview(track); h.render();
  h.infos[0].resolve({ duration_seconds: 100 }); await flush();
  const ended = h.audio.listeners.get("ended");
  h.audio.currentTime = 100; h.audio.ended = true; h.audio.paused = true;
  h.audio.emit("pause"); ended(); ended(); h.render();
  assert.deepEqual(h.ended, [7]);
  assert.equal(h.ui.playingTrackId, null);
  h.ui.togglePreview(track); h.render();
  assert.equal(h.audio.src, "/media/7?start=0");
  h.ui.togglePreview(track); h.ui.seekPreview(track, 100); h.render();
  assert.equal(h.ui.sourceUrl, undefined, "known EOF must not request an empty server stream");
  assert.equal(h.position().currentTime, 100);
  assert.equal(h.ui.playingTrackId, null);
  h.ui.togglePreview(track); h.render();
  h.ui.togglePreview(track); h.render();
  h.audio.currentTime = 8;
  h.audio.playResult = Promise.reject(new Error("playback rejected"));
  h.ui.togglePreview(track); await flush(); h.render();
  h.audio.emit("durationchange");
  assert.equal(h.ui.playingTrackId, null);
  assert.equal(h.position().currentTime, 8, "source release after failure keeps the last position");
  assert.equal(h.errors.length, 1);
  assert.match(h.errors[0], /playback rejected/);
  h.unmount();
});
