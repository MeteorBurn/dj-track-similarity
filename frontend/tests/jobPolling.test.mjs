import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
  const slots = [], effects = [], timers = new Map(), calls = [], events = [];
  let cursor = 0, timerId = 0, now = 0, state;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (next) => { slots[index] = typeof next === "function" ? next(slots[index]) : next; }];
    },
    useRef(initial) { return slots[cursor++] ??= { current: initial }; },
    useEffect(effect, deps) {
      const index = cursor++;
      const previous = slots[index];
      if (!previous || !deps || deps.some((dep, i) => !Object.is(dep, previous.deps[i]))) {
        effects.push(() => {
          previous?.cleanup?.();
          slots[index] = { deps, cleanup: effect() };
        });
      }
    },
  };
  const schedule = (fn, delay, repeat = false) => {
    const id = ++timerId;
    timers.set(id, { fn, delay, due: now + delay, repeat });
    return id;
  };
  const api = new Proxy({}, { get: (_, method) => (...args) => {
    const pending = deferred();
    calls.push({ method, args, ...pending });
    return pending.promise;
  } });
  const options = {
    classifiers: [], setProcessLogKind() {},
    refreshLibrary: () => { events.push("old refresh"); },
    refreshLibrarySummary: () => { events.push("summary"); },
    refreshClassifierProfilesInBackground: () => { events.push("profiles"); },
    appendActivity: () => { events.push("activity"); },
    promptDatabaseOptimization: () => { events.push("prompt"); },
    setNotice: (notice) => { events.push(notice); },
  };
  const module = { exports: {} };
  const compiled = ts.transpileModule(readFileSync(new URL("../src/useJobState.ts", import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(compiled, {
    module, exports: module.exports, Error,
    window: {
      setTimeout: (fn, delay) => schedule(fn, delay), clearTimeout: (id) => timers.delete(id),
      setInterval: (fn, delay) => schedule(fn, delay, true), clearInterval: (id) => timers.delete(id),
    },
    require: (name) => {
      if (name === "react") return react;
      if (name === "./api") return { api };
      if (name === "./trackDisplay") return { basename: (name) => name };
      if (name === "./jobUi") return {
        analysisJobRequest: (job) => api.analysisJob(job.job_id),
        formatMegabytes: String, optimizationPhaseLabel: () => "running", scanSummary: () => "summary",
      };
      if (name === "./errors") return errorsModule;
      throw new Error(name);
    },
  });
  function render() {
    cursor = 0;
    state = module.exports.useJobState(options);
    while (effects.length) effects.shift()();
    return state;
  }
  async function advance(ms) {
    const end = now + ms;
    while (true) {
      const next = [...timers.entries()].filter(([, timer]) => timer.due <= end).sort((a, b) => a[1].due - b[1].due)[0];
      if (!next) break;
      const [id, timer] = next;
      now = timer.due;
      if (timer.repeat) timer.due += timer.delay;
      else timers.delete(id);
      timer.fn();
      await flush();
      render();
    }
    now = end;
  }
  render();
  const tick = () => {
    const next = Math.min(...[...timers.values()].map((timer) => timer.due));
    return Number.isFinite(next) ? advance(next - now) : flush();
  };
  return { render, tick, calls, events, options, unmount: () => slots.forEach((slot) => slot?.cleanup?.()) };
}

const kinds = ["Scan", "Analysis", "GenreTag", "DatabaseValidation", "DatabaseOptimization", "AnalysisPipeline"];
const job = (id, state = "running") => ({ job_id: id, state, files: [], stages: {}, errors: 0 });

const errorsModule = (() => {
  const m = { exports: {} };
  vm.runInNewContext(
    ts.transpileModule(readFileSync(new URL("../src/errors.ts", import.meta.url), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText,
    { module: m, exports: m.exports, Error, String },
  );
  return m.exports;
})();

test("job polls serialize slow requests, ignore replaced/unmounted replies, and stop after terminal replies", async () => {
  for (const kind of kinds) {
    const h = harness();
    const field = kind[0].toLowerCase() + kind.slice(1) + "Job";
    h.render()[`set${kind}Job`](job("old", "queued"));
    h.render();
    await h.tick();
    assert.equal(h.calls.length, 1, kind);
    await h.tick();
    assert.equal(h.calls.length, 1, `${kind}: request must settle before polling again`);
    h.calls[0].resolve(job("old"));
    await flush();
    assert.equal(h.render()[field].state, "running", kind);
    await h.tick();
    assert.equal(h.calls.length, 2, kind);
    await h.tick();
    assert.equal(h.calls.length, 2, `${kind}: queued-to-running keeps serial polling`);
    h.render()[`set${kind}Job`](job("new"));
    h.render();
    const eventsBeforeCompletion = h.events.length;
    h.calls[1].resolve(job("old", "completed"));
    await flush();
    assert.equal(h.render()[field].job_id, "new", kind);
    assert.equal(h.events.length, eventsBeforeCompletion, `${kind}: obsolete response has no effects`);
    assert.equal(h.events.includes("old refresh"), false, `${kind}: obsolete response has no effects`);
    await h.tick();
    h.options.refreshLibrary = () => { h.events.push("current filters"); };
    h.render();
    h.calls[2].resolve(job("new", "completed"));
    await flush();
    // Polling must stop even before the terminal state is committed by React.
    await h.tick();
    assert.equal(h.render()[field].state, "completed", kind);
    assert.ok(h.events.length > eventsBeforeCompletion, kind);
    if (!["DatabaseValidation", "DatabaseOptimization"].includes(kind)) {
      assert.equal(h.events.filter((event) => event === "current filters").length, 1, kind);
      assert.equal(h.events.includes("old refresh"), false, kind);
    }
    const count = h.events.length;
    await h.tick();
    assert.equal(h.calls.length, 3, kind);
    assert.equal(h.events.length, count, kind);
    h.render()[`set${kind}Job`](job("unmounted"));
    h.render();
    await h.tick();
    h.unmount();
    h.calls[3].reject(new Error("late error"));
    await flush();
    assert.equal(h.events.length, count, `${kind}: cleanup ignores errors`);
  }
});

test("pipeline child adoption is invalidated with its parent and retries after a child failure", async () => {
  const h = harness();
  const parent = { ...job("pipeline"), current_stage: "one", stages: { one: { child_job_id: "child" } } };
  h.render().setAnalysisPipelineJob(parent);
  h.render();
  await h.tick();
  h.calls[0].resolve(parent);
  await flush();
  assert.equal(h.calls[1].args[0], "child");
  h.calls[1].reject(new Error("retry child"));
  await flush();
  h.render();
  await h.tick();
  h.calls[2].resolve(parent);
  await flush();
  assert.equal(h.calls[3].args[0], "child");
  h.render().setAnalysisPipelineJob(job("replacement"));
  h.render();
  const count = h.events.length;
  h.calls[3].resolve(job("child"));
  await flush();
  assert.equal(h.render().analysisJob, null);
  assert.equal(h.events.length, count);
  await h.tick();
  h.calls[4].resolve({ ...parent, job_id: "replacement", state: "completed" });
  await flush();
  assert.equal(h.events.filter((event) => event === "old refresh").length, 1);
  h.render();
  h.calls[5].resolve(job("child"));
  await flush();
  assert.equal(h.render().analysisJob, null);
  assert.equal(h.events.filter((event) => event === "old refresh").length, 1);
  h.unmount();
});
