import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

function loadSetBuilderControls() {
  const sourcePath = new URL("../src/setBuilderControls.ts", import.meta.url);
  if (!existsSync(sourcePath)) {
    throw new Error("frontend/src/setBuilderControls.ts does not exist yet");
  }
  const tempDir = mkdtempSync(join(tmpdir(), "set-builder-controls-"));
  const modulePath = join(tempDir, "setBuilderControls.cjs");
  const compiled = ts.transpileModule(readFileSync(sourcePath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  writeFileSync(modulePath, compiled, "utf8");
  return import(pathToFileURL(modulePath));
}

test("set builder slider reset clears classifier maps and restores defaults", async () => {
  const { resetSetBuilderSliders, setBuilderDefaultDiversity, setBuilderDefaultCurve } = await loadSetBuilderControls();

  const first = resetSetBuilderSliders();
  first.classifierTargets.break_energy = 0.85;
  first.classifierAvoid.voice_presence = 0.65;
  first.classifierCurves.break_energy = { start: 0.2, end: 0.9 };
  const second = resetSetBuilderSliders();

  assert.equal(second.diversity, setBuilderDefaultDiversity);
  assert.deepEqual(second.classifierTargets, {});
  assert.deepEqual(second.classifierAvoid, {});
  assert.deepEqual(second.classifierCurves, {});
  assert.deepEqual(setBuilderDefaultCurve, { start: 0.5, end: 0.5 });
  assert.notEqual(first.classifierTargets, second.classifierTargets);
  assert.notEqual(first.classifierAvoid, second.classifierAvoid);
  assert.notEqual(first.classifierCurves, second.classifierCurves);
});
