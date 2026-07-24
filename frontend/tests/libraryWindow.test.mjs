import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

async function loadLibraryWindowModule() {
  const source = readFileSync(new URL("../src/libraryWindow.ts", import.meta.url), "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true
    }
  }).outputText;
  const tempDir = mkdtempSync(join(tmpdir(), "library-window-test-"));
  const modulePath = join(tempDir, "libraryWindow.cjs");
  writeFileSync(modulePath, output, "utf8");
  return import(pathToFileURL(modulePath).href);
}

test("window bounds stay empty for an empty library", async () => {
  const { libraryWindowBounds } = await loadLibraryWindowModule();

  assert.deepEqual(libraryWindowBounds(0, 100), {
    start: 0,
    end: 0,
    hasPrevious: false,
    hasNext: false
  });
});

test("thousands of summaries produce at most 120 rendered rows", async () => {
  const { visibleLibraryWindow } = await loadLibraryWindowModule();
  const tracks = Array.from({ length: 5000 }, (_, index) => index + 1);

  const first = visibleLibraryWindow(tracks, 0);
  const middle = visibleLibraryWindow(tracks, 2400);
  const last = visibleLibraryWindow(tracks, 99999);

  assert.equal(first.items.length, 120);
  assert.equal(middle.items.length, 120);
  assert.equal(last.items.length, 80);
  assert.equal(first.hasPrevious, false);
  assert.equal(first.hasNext, true);
  assert.equal(middle.start, 2400);
  assert.equal(last.start, 4920);
  assert.equal(last.end, 5000);
  assert.equal(last.hasNext, false);
});

test("window navigation moves by bounded non-overlapping slices", async () => {
  const { shiftLibraryWindow } = await loadLibraryWindowModule();

  const second = shiftLibraryWindow(350, 0, 1);
  const third = shiftLibraryWindow(350, second.start, 1);
  const back = shiftLibraryWindow(350, third.start, -1);

  assert.deepEqual(second, { start: 120, end: 240, hasPrevious: true, hasNext: true });
  assert.deepEqual(third, { start: 240, end: 350, hasPrevious: true, hasNext: false });
  assert.equal(back.start, 120);
});
