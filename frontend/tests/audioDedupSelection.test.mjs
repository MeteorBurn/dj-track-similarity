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

test("a report the listing no longer holds is dropped for the newest one", () => {
  const { reconcileReportId } = loadAudioDedupView();
  const listing = [{ report_id: "newest" }, { report_id: "older" }];

  assert.equal(reconcileReportId(listing, "older"), "older");
  assert.equal(reconcileReportId(listing, "deleted"), "newest");
  assert.equal(reconcileReportId([], "deleted"), null);
  assert.equal(reconcileReportId([], null), null);
});

test("a selection that would delete every copy of a group is refused", () => {
  const { buildDeleteRequest } = loadAudioDedupView();
  const groups = [group(1, [file(10, "keeper"), file(11, "duplicate")])];

  const emptied = buildDeleteRequest(groups, { 1: [10, 11] }, "trash");
  const keeperOnly = buildDeleteRequest(groups, { 1: [10] }, "trash");

  assert.equal(emptied.ok, false);
  assert.match(emptied.error, /все копии/);
  assert.equal(keeperOnly.ok, true, "deleting the suggested keeper stays allowed");
});
