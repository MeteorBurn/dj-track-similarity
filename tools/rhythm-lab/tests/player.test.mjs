import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function harness() {
  const elements = new Map();
  class Element {
    listeners = new Map(); dataset = {}; style = { setProperty() {} };
    currentTime = 0; duration = Infinity; paused = true; ended = false; volume = 1;
    value = ""; playCalls = 0;
    constructor(id) { this.id = id; }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
    emit(name) { this.listeners.get(name)?.(); }
    setAttribute(name, value) { this[name] = value; }
    removeAttribute(name) { delete this[name]; }
    cloneNode() { return new Element(this.id); }
    replaceWith(element) { elements.set(this.id, element); }
    play() { this.playCalls++; this.paused = false; this.emit("play"); return this.playResult ?? Promise.resolve(); }
    pause() { this.paused = true; this.emit("pause"); }
    load() { this.currentTime = 0; this.ended = false; }
  }
  const requests = [], changes = [];
  const document = { getElementById(id) {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  } };
  const context = vm.createContext({ document, AbortController, URLSearchParams, fetch(url, options) {
    const request = { url, signal: options.signal, ...deferred() };
    requests.push(request);
    return request.promise;
  } });
  vm.runInContext(readFileSync(new URL("../rhythm_lab/static/player.js", import.meta.url), "utf8"), context);
  const player = context.createRhythmPlayer({ onChange: change => changes.push(change) });
  const item = id => ({ track_id: id, catalog_uuid: "catalog-a", track_uuid: `uuid-${id}`, title: `Track ${id}` });
  const queue = { items: [item(1), item(2)], offset: 0, total: 2, limit: 2, endpoint: "/api/tracks", params: {} };
  return {
    player, requests, changes, item, queue,
    element: id => document.getElementById(`player${id}`),
    select: (id, context = queue) => player.select(item(id), context, id - 1),
    respond(index, data, ok = true) { requests[index].resolve({ ok, statusText: "failed", json: async () => data }); },
    input(id, value) { const element = document.getElementById(`player${id}`); element.value = String(value); element.emit("input"); },
  };
}

test("RH streams immediately and seeks on the source timeline while playing or paused", { timeout: 1000 }, async () => {
  const h = harness();
  await h.select(1);
  const initial = h.element("Audio");
  assert.equal(initial.src, "/media/1?start=0");
  assert.equal(initial.playCalls, 1, "metadata must not delay playback");
  assert.equal(h.requests[0].url, "/api/tracks/1/preview-info");
  assert.equal(h.element("Seek").disabled, true);
  h.respond(0, { duration_seconds: 300 }); await flush();
  assert.equal(h.element("Seek").max, "300");
  h.input("Volume", 0.25);
  h.input("Seek", 120);
  const sought = h.element("Audio");
  assert.equal(initial.src, undefined, "seeking cancels the preceding response");
  assert.equal(sought.src, "/media/1?start=120");
  assert.equal(sought.currentTime, 0, "do not seek within a streamed WAV");
  assert.equal(sought.volume, 0.25);
  assert.equal(sought.playCalls, 1);
  sought.currentTime = 2; sought.emit("timeupdate");
  assert.equal(h.element("Seek").value, "122");
  assert.equal(h.element("Duration").textContent, "5:00", "ignore stream duration");
  h.element("Toggle").emit("click");
  h.input("Seek", 200);
  assert.equal(h.element("Audio").src, "/media/1?start=200");
  assert.equal(h.element("Audio").playCalls, 0);
  h.element("Toggle").emit("click");
  assert.equal(h.element("Audio").playCalls, 1);
  assert.equal(h.requests.length, 1, "seeks reuse metadata");
});

test("RH discards stale metadata, media events, play rejections and queue responses after selection or reset", { timeout: 1000 }, async () => {
  const h = harness();
  await h.select(1);
  assert.equal(h.requests.length, 1, "selection starts an independent metadata request");
  const old = h.element("Audio");
  h.element("Toggle").emit("click");
  const rejected = deferred(); old.playResult = rejected.promise;
  h.element("Toggle").emit("click");
  await h.select(2);
  assert.equal(h.requests[0].signal.aborted, true);
  assert.equal(old.src, undefined);
  h.respond(0, { duration_seconds: 999 });
  rejected.reject(new Error("old stream failed"));
  old.currentTime = 88;
  for (const event of ["error", "ended", "timeupdate", "pause"]) old.emit(event);
  await flush();
  assert.equal(h.element("Error").hidden, true);
  assert.equal(h.element("Seek").disabled, true);
  assert.equal(h.changes.at(-1).track.track_id, 2);
  assert.equal(h.changes.at(-1).playing, true);
  h.player.reset();
  assert.equal(h.requests[1].signal.aborted, true);
  h.respond(1, { duration_seconds: 500 }); await flush();
  assert.equal(h.player.current(), null);
  assert.equal(h.element("Audio").src, undefined);
  assert.equal(h.element("Seek").disabled, true);
  await h.select(1, { ...h.queue, items: [h.item(1)], limit: 1 });
  h.element("Next").emit("click");
  const queueRequest = h.requests.at(-1);
  h.player.reset();
  assert.equal(queueRequest.signal.aborted, true);
  queueRequest.resolve({ ok: true, json: async () => ({ items: [h.item(2)], offset: 1, total: 2 }) });
  await flush();
  assert.equal(h.player.current(), null);
});

test("RH retries failed streams at their source position and restarts finished tracks", { timeout: 1000 }, async () => {
  const h = harness();
  await h.select(1);
  assert.equal(h.requests.length, 1, "selection starts an independent metadata request");
  h.respond(0, { duration_seconds: 300 }); await flush();
  h.input("Seek", 100);
  const failed = h.element("Audio");
  failed.currentTime = 7; failed.emit("error");
  assert.equal(failed.src, undefined);
  assert.equal(h.changes.at(-1).playing, false);
  assert.equal(h.element("Error").hidden, false);
  h.element("Toggle").emit("click");
  assert.equal(h.element("Audio").src, "/media/1?start=107");
  assert.equal(h.element("Error").hidden, true);
  const ended = h.element("Audio");
  ended.currentTime = 193; ended.ended = true; ended.paused = true; ended.emit("ended");
  assert.equal(h.changes.at(-1).playing, false);
  h.element("Toggle").emit("click");
  assert.equal(h.element("Audio").src, "/media/1?start=0");
  h.input("Seek", 300);
  assert.equal(h.element("Audio").src, undefined, "the exact end must not request an empty stream");
  assert.equal(h.changes.at(-1).playing, false);
  h.element("Toggle").emit("click");
  assert.equal(h.element("Audio").src, "/media/1?start=0");
  await h.select(2);
  h.respond(1, { detail: "Source audio is missing" }, false); await flush();
  h.element("Audio").emit("error");
  assert.match(h.element("Error").textContent, /Source audio is missing/);
  await h.select(1);
  h.element("Audio").emit("error");
  h.respond(2, { detail: "Library is unavailable" }, false); await flush();
  assert.match(h.element("Error").textContent, /Library is unavailable/);
});
