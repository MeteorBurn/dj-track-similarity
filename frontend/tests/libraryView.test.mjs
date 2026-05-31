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
  const transpiled = transpile(readFileSync(sourcePath, "utf8"));
  const modulePath = join(tempDir, "libraryView.cjs");
  writeFileSync(modulePath, transpiled, "utf8");
  return import(pathToFileURL(modulePath).href);
}

function loadExportViewModule() {
  const sourcePath = new URL("../src/exportView.ts", import.meta.url);
  if (!existsSync(sourcePath)) {
    throw new Error("frontend/src/exportView.ts does not exist yet");
  }
  const tempDir = mkdtempSync(join(tmpdir(), "export-view-test-"));
  const modulePath = join(tempDir, "exportView.cjs");
  writeFileSync(modulePath, transpile(readFileSync(sourcePath, "utf8")), "utf8");
  return import(pathToFileURL(modulePath).href);
}

function loadPlaylistViewModule() {
  const sourcePath = new URL("../src/playlistView.ts", import.meta.url);
  if (!existsSync(sourcePath)) {
    throw new Error("frontend/src/playlistView.ts does not exist yet");
  }
  const tempDir = mkdtempSync(join(tmpdir(), "playlist-view-test-"));
  const modulePath = join(tempDir, "playlistView.cjs");
  writeFileSync(modulePath, transpile(readFileSync(sourcePath, "utf8")), "utf8");
  return import(pathToFileURL(modulePath).href);
}

function loadSyncopatedRhythmModule() {
  const sourcePath = new URL("../src/syncopatedRhythm.ts", import.meta.url);
  if (!existsSync(sourcePath)) {
    throw new Error("frontend/src/syncopatedRhythm.ts does not exist yet");
  }
  const tempDir = mkdtempSync(join(tmpdir(), "syncopated-rhythm-test-"));
  writeTranspiledModule(new URL("../src/maestGenres.ts", import.meta.url), join(tempDir, "maestGenres.js"));
  const modulePath = join(tempDir, "syncopatedRhythm.cjs");
  writeFileSync(modulePath, transpile(readFileSync(sourcePath, "utf8")), "utf8");
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
  const playlist = [{ id: 3, title: "Already in set", path: "D:/Music/gamma.wav" }];
  const visible = [
    { id: 2, title: "Broken", path: "D:/Music/alpha.wav" },
    { id: 3, title: "Already in set", path: "D:/Music/gamma.wav" },
    { id: 4, title: "Garage", path: "D:/Music/delta.wav" }
  ];

  const next = appendVisibleTracksToPlaylist(playlist, visible);

  assert.deepEqual(next.map((track) => track.id), [3, 2, 4]);
});

test("liked library filter toggles and describes liked track count", async () => {
  const { likedTracksFilterTitle, toggleLikedTracksFilter } = await loadLibraryViewModule();

  assert.equal(toggleLikedTracksFilter(false), true);
  assert.equal(toggleLikedTracksFilter(true), false);
  assert.equal(likedTracksFilterTitle(false, 3), "Показать только лайкнутые треки. Доступно: 3.");
  assert.equal(likedTracksFilterTitle(true, 3), "Вернуться ко всей библиотеке. Лайкнутых треков: 3.");
});

test("library search mode toggles between substring and FTS semantics", async () => {
  const { librarySearchModeTitle, toggleLibrarySearchMode } = await loadLibraryViewModule();

  assert.equal(toggleLibrarySearchMode("like"), "fts");
  assert.equal(toggleLibrarySearchMode("fts"), "like");
  assert.equal(librarySearchModeTitle("like"), "Substring LIKE search. Finds partial text inside artist, title, album, path, and metadata.");
  assert.equal(librarySearchModeTitle("fts"), "FTS token search. Faster on broad text queries, but does not match arbitrary substrings inside one token.");
});

test("library track order can be reversed without mutating the loaded page", async () => {
  const { orderedLibraryTracks } = await loadLibraryViewModule();
  const tracks = [
    { id: 1, title: "First", path: "D:/Music/first.wav" },
    { id: 2, title: "Second", path: "D:/Music/second.wav" },
    { id: 3, title: "Third", path: "D:/Music/third.wav" }
  ];

  const forward = orderedLibraryTracks(tracks, "forward");
  const reverse = orderedLibraryTracks(tracks, "reverse");

  assert.deepEqual(forward.map((track) => track.id), [1, 2, 3]);
  assert.deepEqual(reverse.map((track) => track.id), [3, 2, 1]);
  assert.deepEqual(tracks.map((track) => track.id), [1, 2, 3]);
});

test("library page helpers report one-based pages and clamp requested page offsets", async () => {
  const { libraryCurrentPageNumber, libraryPageCount, libraryPageOffsetForNumber } = await loadLibraryViewModule();

  assert.equal(libraryPageCount(0, 200), 0);
  assert.equal(libraryPageCount(401, 200), 3);
  assert.equal(libraryCurrentPageNumber(0, 0, 200), 0);
  assert.equal(libraryCurrentPageNumber(401, 400, 200), 3);
  assert.equal(libraryPageOffsetForNumber(1, 401, 200), 0);
  assert.equal(libraryPageOffsetForNumber(3, 401, 200), 400);
  assert.equal(libraryPageOffsetForNumber(20, 401, 200), 400);
  assert.equal(libraryPageOffsetForNumber(-4, 401, 200), 0);
});

test("export directory validation rejects blank paths", async () => {
  const { exportDirectoryError } = await loadExportViewModule();

  assert.equal(exportDirectoryError(""), "Укажите папку экспорта");
  assert.equal(exportDirectoryError("   "), "Укажите папку экспорта");
  assert.equal(exportDirectoryError("D:/Exports"), null);
});

test("playlist pagination slices pages and clamps stale offsets", async () => {
  const { playlistPage } = await loadPlaylistViewModule();
  const tracks = Array.from({ length: 405 }, (_, index) => ({ id: index + 1, title: `Track ${index + 1}` }));

  const first = playlistPage(tracks, 0, 200);
  const third = playlistPage(tracks, 400, 200);
  const clamped = playlistPage(tracks.slice(0, 120), 400, 200);

  assert.deepEqual(first.items.map((track) => track.id).slice(0, 3), [1, 2, 3]);
  assert.equal(first.pageStart, 1);
  assert.equal(first.pageEnd, 200);
  assert.equal(first.canGoForward, true);
  assert.deepEqual(third.items.map((track) => track.id), [401, 402, 403, 404, 405]);
  assert.equal(third.pageStart, 401);
  assert.equal(third.pageEnd, 405);
  assert.equal(third.canGoForward, false);
  assert.equal(clamped.offset, 0);
  assert.equal(clamped.pageStart, 1);
  assert.equal(clamped.pageEnd, 120);
});

test("syncopated rhythm label uses stored MAEST flag", async () => {
  const { hasMaestSyncopatedRhythm } = await loadSyncopatedRhythmModule();

  assert.equal(hasMaestSyncopatedRhythm({ maest_syncopated_rhythm: true }), true);
  assert.equal(hasMaestSyncopatedRhythm({ maest_syncopated_rhythm: false }), false);
  assert.equal(hasMaestSyncopatedRhythm({ maest_genres: [{ label: "Breakbeat", score: 0.9 }] }), false);
});
