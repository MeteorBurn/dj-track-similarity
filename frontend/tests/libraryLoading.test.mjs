import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

const libraryStateSource = readFileSync(
  new URL("../src/useLibraryState.ts", import.meta.url),
  "utf8"
);

async function loadLibraryLoadingModule() {
  const source = readFileSync(new URL("../src/libraryLoading.ts", import.meta.url), "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true
    }
  }).outputText;
  const tempDir = mkdtempSync(join(tmpdir(), "library-loading-test-"));
  const modulePath = join(tempDir, "libraryLoading.cjs");
  writeFileSync(modulePath, output, "utf8");
  return import(pathToFileURL(modulePath).href);
}

function track(trackId, catalogUuid = "catalog-a") {
  return {
    track_id: trackId,
    catalog_uuid: catalogUuid,
    track_uuid: `track-${trackId}`,
    file_path: `D:/Music/${trackId}.wav`,
    title: `Track ${trackId}`,
    artist: null,
    album: null,
    tag_bpm: null,
    tag_key: null,
    audio_duration_seconds: null,
    liked: false,
    analysis_coverage: {
      sonara_core: false,
      maest_analysis: false,
      maest_embedding: false,
      mert: false,
      muq: false,
      clap: false
    },
    classifier_scores: []
  };
}

test("library uses one fixed 200-track page per API request", async () => {
  const { libraryPageSize } = await loadLibraryLoadingModule();

  assert.equal(libraryPageSize, 200);
  assert.match(libraryStateSource, /limit:\s*libraryPageSize/);
  assert.match(libraryStateSource, /offset:\s*effectiveOffset/);
  assert.doesNotMatch(libraryStateSource, /LibraryLoadSize|libraryChunkPlan|loadSize/);
});

test("chunk aggregation is catalog-aware and replaces a repeated identity", async () => {
  const { libraryTracksBelongToCatalog, mergeLibraryTracks } = await loadLibraryLoadingModule();
  const oldTrack = track(1);
  const unrelatedCatalogTrack = {
    ...track(1, "catalog-b"),
    track_uuid: oldTrack.track_uuid
  };
  const current = [oldTrack, track(2)];
  const incoming = [
    { ...track(1), liked: true },
    track(2),
    unrelatedCatalogTrack,
    track(3),
    track(3)
  ];

  const merged = mergeLibraryTracks(current, incoming);

  assert.equal(merged.length, 4);
  assert.equal(merged[0].liked, true);
  assert.equal(merged[2].catalog_uuid, "catalog-b");
  assert.equal(merged[3].track_id, 3);
  assert.equal(libraryTracksBelongToCatalog(merged, "catalog-a"), false);
  assert.equal(libraryTracksBelongToCatalog(merged.slice(0, 2), "catalog-a"), true);
});

test("new requests abort prior work and reject stale commits", async () => {
  const { createLibraryLoadCoordinator } = await loadLibraryLoadingModule();
  const coordinator = createLibraryLoadCoordinator();
  const first = coordinator.start("catalog-a:first");
  const second = coordinator.start("catalog-a:second");
  const committed = [];

  if (coordinator.isCurrent(first)) committed.push("first");
  if (coordinator.isCurrent(second)) committed.push("second");

  assert.equal(first.signal.aborted, true);
  assert.equal(coordinator.isCurrent(first), false);
  assert.equal(coordinator.isCurrent(second), true);
  assert.deepEqual(committed, ["second"]);
  assert.equal(coordinator.cancel(), true);
  assert.equal(second.signal.aborted, true);
  assert.equal(coordinator.isCurrent(second), false);
});

test("request keys include catalog, filters, scores, and page offset", async () => {
  const { libraryRequestKey } = await loadLibraryLoadingModule();
  const common = {
    databaseKey: "catalog-a",
    query: "breaks",
    searchMode: "fts",
    preset: "syncopated",
    liked: true,
    classifierMinScores: { voice: 0.8, energy: 0.4 }
  };

  const firstPage = libraryRequestKey({ ...common, offset: 0 });
  const secondPage = libraryRequestKey({ ...common, offset: 200 });
  const reorderedScores = libraryRequestKey({
    ...common,
    classifierMinScores: { energy: 0.4, voice: 0.8 },
    offset: 0
  });
  const otherCatalog = libraryRequestKey({ ...common, databaseKey: "catalog-b", offset: 0 });

  assert.notEqual(firstPage, secondPage);
  assert.equal(firstPage, reorderedScores);
  assert.notEqual(firstPage, otherCatalog);
});

test("equivalent classifier score state does not clear the visible library", async () => {
  const { sameClassifierMinScores } = await loadLibraryLoadingModule();
  const setter = libraryStateSource.match(
    /const setClassifierMinScores:[\s\S]*?setClassifierMinScoresState\(resolved\);\s*\};/
  )?.[0] || "";

  assert.equal(sameClassifierMinScores({}, {}), true);
  assert.equal(
    sameClassifierMinScores(
      { voice_presence: 0.7, break_energy: 0.4 },
      { break_energy: 0.4, voice_presence: 0.7 }
    ),
    true
  );
  assert.equal(
    sameClassifierMinScores(
      { voice_presence: 0.7 },
      { voice_presence: 0.6 }
    ),
    false
  );
  assert.equal(
    sameClassifierMinScores(
      { voice_presence: 0.7 },
      { voice_presence: 0.7, break_energy: 0.4 }
    ),
    false
  );
  assert.match(setter, /if \(sameClassifierMinScores\(current, resolved\)\) return;/);
  assert.ok(
    setter.indexOf("sameClassifierMinScores(current, resolved)") < setter.indexOf("clearVisibleLibraryResult()")
  );
});
