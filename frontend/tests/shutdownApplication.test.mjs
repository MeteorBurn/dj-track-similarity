import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

import ts from "typescript";


function loadShutdownApplicationModule() {
  const source = readFileSync(new URL("../src/shutdownApplication.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports, Promise, Error });
  return module.exports;
}


test("shutdown closes the application window only after the server acknowledges", async () => {
  const { shutdownApplication } = loadShutdownApplicationModule();
  const calls = [];

  await shutdownApplication({
    requestShutdown: async () => calls.push("acknowledged"),
    onAcknowledged: () => calls.push("fallback-rendered"),
    closeWindow: () => calls.push("closed")
  });

  assert.deepEqual(calls, ["acknowledged", "fallback-rendered", "closed"]);
});


test("shutdown leaves the window open when the server request fails", async () => {
  const { shutdownApplication } = loadShutdownApplicationModule();
  const calls = [];

  await assert.rejects(
    shutdownApplication({
      requestShutdown: async () => {
        calls.push("request-failed");
        throw new Error("offline");
      },
      onAcknowledged: () => calls.push("fallback-rendered"),
      closeWindow: () => calls.push("closed")
    }),
    /offline/
  );

  assert.deepEqual(calls, ["request-failed"]);
});
