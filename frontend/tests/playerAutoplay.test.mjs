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

function trackStatsHarness() {
  const react = {
    useState: (initial) => [initial, () => {}],
    useEffect: (effect) => effect(),
  };
  const api = { track: () => assert.fail("Player metadata must come directly from the supplied track") };
  const modules = new Map();
  function load(name) {
    if (name === "react") return react;
    if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
    if (name === "lucide-react") return {};
    if (name === "./api") return { api };
    if (name === "./previewPosition") return {
      usePreviewPosition: () => ({}), previewPositionForTrack: () => ({ currentTime: 0, duration: 0 }),
    };
    if (modules.has(name)) return modules.get(name);
    const extension = ["./PlayerDock", "./TrackRows"].includes(name) ? "tsx" : "ts";
    const module = { exports: {} }; modules.set(name, module.exports);
    vm.runInNewContext(ts.transpileModule(readFileSync(new URL(`../src/${name.slice(2)}.${extension}`, import.meta.url), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
    }).outputText, { module, exports: module.exports, require: load });
    return module.exports;
  }
  const { PlayerDock } = load("./PlayerDock");
  const { TrackList } = load("./TrackRows");
  function stats(tree) {
    const values = {};
    function visit(node) {
      const children = node?.props?.children;
      if (Array.isArray(children) && children[0]?.type === "strong" && children[1]?.type === "span") {
        values[children[1].props.children] = children[0].props.children;
      }
      if (node?.props?.className === "library-track-bpm") values.BPM = children;
      if (node?.props?.className === "library-track-key") values.KEY = children;
      if (node?.props?.className === "player-track-info") values.fileInfo = children.find((child) => child?.type === "span")?.props.children;
      if (node?.props?.className === "library-track-meta") values.fileInfo = children;
      for (const child of Array.isArray(children) ? children.flat(Infinity) : [children]) {
        if (child && typeof child === "object") visit(child);
      }
    }
    visit(tree);
    return values;
  }
  return {
    player: (preview) => stats(PlayerDock({ preview, playing: false, audioRef: { current: null }, onToggle() {}, onSeek() {} })),
    library: (track) => stats(TrackList({ tracks: [track], seedSet: new Set(), playlistSet: new Set(), playingTrackId: null, previewTrackId: null,
      onSeed() {}, onTogglePlaylist() {}, onPreview() {}, onSeekPreview() {}, onDetails() {} })),
  };
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

test("player and library metadata come directly from track summaries", () => {
  const h = trackStatsHarness();
  const track = {
    track_id: 1, catalog_uuid: "A", track_uuid: "a1", file_path: "a.wav", tag_bpm: 99, tag_key: "tag-key",
    sonara_bpm: 128.5, sonara_key_camelot: "8B",
    sonara_core: { detected_bpm: 64.25, detected_key_name: "C minor", detected_key_camelot: "5A" },
    album: "album-from-tags",
    file_size_bytes: 37 * 1024 * 1024, audio_format: "flac", sample_rate_hz: 48000, bit_rate_bps: 320000, bit_depth: 24,
    file: { file_size_bytes: 1024 * 1024, audio_format: "mp3", sample_rate_hz: 96000, bit_rate_bps: 128000, bit_depth: 16 },
  };
  const absent = (values) => {
    assert.ok(Number.isNaN(Number(values.BPM)), "no file-tag or nested-detail BPM fallback");
    assert.notEqual(values.KEY, track.sonara_key_camelot);
    assert.notEqual(values.KEY, track.sonara_core.detected_key_name);
    assert.notEqual(values.KEY, track.sonara_core.detected_key_camelot);
    assert.notEqual(values.KEY, track.tag_key);
  };
  for (const render of [h.player, h.library]) {
    const values = render(track);
    assert.equal(Number(values.BPM), track.sonara_bpm);
    assert.equal(values.KEY, track.sonara_key_camelot);
    absent(render({ ...track, sonara_bpm: null, sonara_key_camelot: null }));
  }
  absent(h.player({ track_id: track.track_id }));
  absent(h.player(null));
  const fileInfo = h.player(track).fileInfo;
  assert.equal(typeof fileInfo, "string", "player technical info is present");
  assert.match(fileInfo, /\b37(?:\.0+)?\s*MB\b/);
  assert.match(fileInfo, /\bflac\b/i);
  assert.doesNotMatch(fileInfo, /\b(?:mp3|wav)\b/i);
  assert.match(fileInfo, /\b48(?:\.0+)?\s*kHz\b/);
  assert.match(fileInfo, /\b320\s*kbps\b/);
  assert.match(fileInfo, /\b24[-\s]*bit\b/);
  const libraryInfo = h.library(track).fileInfo;
  assert.equal(typeof libraryInfo, "string", "library technical info is present");
  assert.equal(libraryInfo, fileInfo);
  for (const preview of [{ ...track, audio_format: null, sample_rate_hz: null, bit_rate_bps: null, bit_depth: null }, { track_id: track.track_id }, null]) {
    const info = h.player(preview).fileInfo;
    assert.equal(typeof info, "string", "empty player technical info is present");
    assert.doesNotMatch(info, /flac|mp3|wav|kHz|kbps|bit|NaN|undefined/i);
    if (preview && "file_path" in preview) {
      assert.match(info, /\b37(?:\.0+)?\s*MB\b/);
      const libraryInfo = h.library(preview).fileInfo;
      assert.equal(typeof libraryInfo, "string", "nullable library technical info is present");
      assert.equal(libraryInfo, info);
    } else assert.doesNotMatch(info, /MB/);
  }
});
