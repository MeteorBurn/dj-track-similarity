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

function group(groupId, files) {
  return {
    group_id: groupId,
    confidence: "high",
    score: 1,
    fingerprint_similarity: 1,
    suspected_transcode_count: 0,
    stale_file_count: 0,
    files,
    pairs: [],
    blocked_reasons: []
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

test("a delete batch carries the confirmation phrase the delete endpoint requires", () => {
  const { applyDeleteConfirmation, buildDeleteRequest } = loadAudioDedupView();
  const groups = [group(1, [file(10, "keeper"), file(11, "duplicate")])];

  const built = buildDeleteRequest(groups, { 1: [11] }, "trash");

  assert.equal(built.ok, true);
  assert.equal(built.payload.confirmation, applyDeleteConfirmation);
  assert.equal(built.payload.deletion_mode, "trash");
  assert.deepEqual(JSON.parse(JSON.stringify(built.payload.selections)), [
    { group_id: 1, track_ids: [11] }
  ]);
});
