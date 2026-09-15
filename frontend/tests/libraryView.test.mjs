import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

function loadLibraryViewModule() {
  const sourcePath = new URL("../src/libraryView.ts", import.meta.url);
  if (!existsSync(sourcePath)) {
    throw new Error("frontend/src/libraryView.ts does not exist yet");
  }
  const tempDir = mkdtempSync(join(tmpdir(), "library-view-test-"));
  writeTranspiledModule(new URL("../src/maestGenres.ts", import.meta.url), join(tempDir, "maestGenres.js"));
  writeTranspiledModule(new URL("../src/syncopatedRhythm.ts", import.meta.url), join(tempDir, "syncopatedRhythm.js"));
  writeTranspiledModule(new URL("../src/libraryLoading.ts", import.meta.url), join(tempDir, "libraryLoading.js"));
  const transpiled = transpile(readFileSync(sourcePath, "utf8"));
  const modulePath = join(tempDir, "libraryView.cjs");
  writeFileSync(modulePath, transpiled, "utf8");
  return import(pathToFileURL(modulePath).href);
}

function writeTranspiledModule(sourcePath, outputPath) {
  writeFileSync(outputPath, transpile(readFileSync(sourcePath, "utf8")), "utf8");
}

function transpile(source) {
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true
    }
  }).outputText;
}

test("visible track add skips duplicates and preserves visible order", async () => {
  const { appendVisibleTracksToPlaylist } = await loadLibraryViewModule();
  const playlist = [{ track_id: 3, catalog_uuid: "catalog-a", track_uuid: "track-3" }];
  const visible = [
    { track_id: 2, catalog_uuid: "catalog-a", track_uuid: "track-2" },
    { track_id: 3, catalog_uuid: "catalog-a", track_uuid: "track-3" },
    { track_id: 4, catalog_uuid: "catalog-a", track_uuid: "track-4" }
  ];

  const next = appendVisibleTracksToPlaylist(playlist, visible);

  assert.deepEqual(next.map((track) => track.track_id), [3, 2, 4]);
});
