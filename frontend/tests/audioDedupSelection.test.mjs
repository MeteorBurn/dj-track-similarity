import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));

function loadAudioDedupView() {
  const source = readFileSync(join(srcDir, "audioDedupView.ts"), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports, Set, Object, Map, Number });
  return module.exports;
}

function group(groupId, files, hiddenFileCount = 0) {
  return {
    group_id: groupId,
    confidence: "high",
    fingerprint_similarity: 1,
    suspected_transcode_count: 0,
    stale_file_count: 0,
    hidden_file_count: hiddenFileCount,
    files,
    pairs: [],
    review_reasons: []
  };
}

function file(trackId, role) {
  return { track_id: trackId, role, size: 1024, stale: false };
}

test("the fingerprint band survives a report that predates the confidence bands", () => {
  const { fingerprintBandText } = loadAudioDedupView();
  const scan = {
    fingerprint_min_similarity: 0.3,
    fingerprint_confidence_high: 0.95,
    fingerprint_confidence_medium: 0.7
  };

  assert.equal(fingerprintBandText("medium", scan), "0.70 – 0.95");
  // Reports and backends older than these fields leave them out entirely, and
  // the review has to keep rendering rather than take the whole page down.
  assert.equal(fingerprintBandText("medium", { fingerprint_min_similarity: 0.45 }), "≥ 0.45");
  assert.equal(fingerprintBandText("medium", {}), "—");
});

test("the spectral chip survives a report that predates the source-rate measurement", () => {
  const { fileSpectralBadge, fileSpecCells } = loadAudioDedupView();
  const base = {
    audio_format: "FLAC",
    bit_rate_bps: 1_000_000,
    sample_rate_hz: 48_000,
    bit_depth: 24,
    size: 40_000_000,
    duration: 300,
    spectral_cutoff_hz: 21_000,
    spectral_sharpness_db: 20,
    suspected_transcode: false,
    spectral_note: "full band"
  };
  const rate = (copy) => fileSpecCells(copy).find((cell) => cell.key === "sample_rate").text;

  // A report written before the measurement existed carries no such key, so the
  // value arrives as undefined. A `!== null` test let it through and rendered
  // "upsampled from NaN kHz" on every copy in the library.
  assert.notEqual(fileSpectralBadge(base, null).kind, "upsampled");
  assert.ok(!/NaN/.test(fileSpectralBadge(base, null).text));
  assert.equal(rate(base), "48,000 Hz");

  const explicitNull = { ...base, effective_source_rate_hz: null };
  assert.notEqual(fileSpectralBadge(explicitNull, null).kind, "upsampled");
  assert.equal(rate(explicitNull), "48,000 Hz");

  const upsampled = { ...base, effective_source_rate_hz: 44_100 };
  assert.equal(fileSpectralBadge(upsampled, null).kind, "upsampled");
  // Historical inferred rates must not overwrite the file's actual sample rate.
  assert.equal(rate(upsampled), rate(base));
});

test("page selection preserves its scope and produces a safe confirmed delete batch", () => {
  const {
    applyDeleteConfirmation,
    buildDeleteRequest,
    invertPageSelection,
    selectFolderOnPage
  } = loadAudioDedupView();
  const plain = (value) => JSON.parse(JSON.stringify(value));
  const groups = [group(1, [
    { ...file(10, "keeper"), path: "M:/Library/Remove/keeper.flac" },
    { ...file(11, "duplicate"), path: "M:/Library/Keep/copy.flac" },
    { ...file(12, "duplicate"), path: "M:/Library/Remove/copy.flac" },
    { ...file(13, "duplicate"), path: "M:/Library/Remove/stale.flac", stale: true },
    { ...file(14, "duplicate"), path: "M:/Library/Keep/another.flac" }
  ])];
  const initial = { 1: [11, 13], 9: [90] };
  const inverted = invertPageSelection(groups, initial);
  assert.deepEqual(plain(inverted), { 1: [10, 12, 14], 9: [90] });
  assert.deepEqual(initial, { 1: [11, 13], 9: [90] });
  assert.deepEqual(plain(invertPageSelection(groups, inverted)), { 1: [11], 9: [90] });

  const previous = { 1: [11], 9: [90] };
  const folder = "  m:\\LIBRARY\\remove\\  ";
  const marked = selectFolderOnPage(groups, previous, folder);
  assert.deepEqual(plain(marked), { 1: [10, 11, 12], 9: [90] });
  assert.deepEqual(previous, { 1: [11], 9: [90] });
  assert.deepEqual(plain(selectFolderOnPage(groups, marked, folder)), plain(marked));
  assert.deepEqual(plain(selectFolderOnPage(groups, marked, "   ")), plain(marked));
  assert.deepEqual(plain(selectFolderOnPage(groups, marked, "Missing")), plain(marked));

  const built = buildDeleteRequest(groups, marked, "trash", "Library");

  assert.equal(built.ok, true);
  assert.equal(built.payload.confirmation, applyDeleteConfirmation);
  assert.equal(built.payload.deletion_mode, "trash");
  // The server re-checks this filter, so a batch that forgets it deletes copies
  // the reviewer never had on screen.
  assert.equal(built.payload.path_filter, "Library");
  assert.deepEqual(plain(built.payload.selections), [
    { group_id: 1, track_ids: [10, 11, 12] },
    { group_id: 9, track_ids: [90] }
  ]);

  const sameFolder = [group(2, [
    { ...file(20, "keeper"), path: "M:/Library/Remove/a.flac" },
    { ...file(21, "duplicate"), path: "M:/Library/Remove/b.flac" }
  ])];
  for (const selection of [
    selectFolderOnPage(sameFolder, {}, folder),
    invertPageSelection(sameFolder, {})
  ]) {
    assert.equal(buildDeleteRequest(sameFolder, selection, "trash", "Library").ok, false);
  }
});
