import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));

function compileModule(name, requireImpl = () => ({})) {
  const source = readFileSync(join(srcDir, name), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, {
    module,
    exports: module.exports,
    require: requireImpl,
    Map,
    Set,
    Math,
    Number,
    String,
    Object,
    Array,
    JSON,
  });
  return module.exports;
}

const trackDisplay = compileModule("trackDisplay.ts");
function summary(overrides = {}) {
  return {
    track_id: 11,
    catalog_uuid: "catalog-a",
    track_uuid: "track-a",
    file_path: "D:/Music/Artist - Track.flac",
    title: "Track",
    artist: "Artist",
    album: "Album",
    tag_bpm: 128,
    tag_key: "8A",
    audio_duration_seconds: 247.37,
    liked: false,
    analysis_coverage: {
      sonara_core: true,
      maest_analysis: true,
      maest_embedding: true,
      mert: true,
      muq: true,
      clap: false,
    },
    classifier_scores: [],
    ...overrides,
  };
}

function findByClassName(node, className) {
  if (!node || typeof node !== "object") return null;
  if (node.props?.className === className) return node;
  const children = node.props?.children;
  for (const child of Array.isArray(children) ? children : [children]) {
    const found = findByClassName(child, className);
    if (found) return found;
  }
  return null;
}

function findAllByType(node, type, results = []) {
  if (!node || typeof node !== "object") return results;
  if (node.type === type) results.push(node);
  const children = node.props?.children;
  for (const child of Array.isArray(children) ? children : [children]) {
    findAllByType(child, type, results);
  }
  return results;
}

function nodeText(node) {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!node || typeof node !== "object") return "";
  const children = node.props?.children;
  return (Array.isArray(children) ? children : [children]).map(nodeText).join("");
}

test("track display uses the file path stem instead of tags", () => {
  const track = summary();

  assert.equal(trackDisplay.displayTrack(track), "Artist - Track");
  assert.equal(trackDisplay.trackHasAnalysis(track, "sonara"), true);
  assert.equal(trackDisplay.trackHasAnalysis(track, "maest"), true);
  assert.equal(trackDisplay.trackHasAnalysis(track, "muq"), true);
  assert.equal(trackDisplay.trackHasAnalysis(track, "clap"), false);
});

test("track detail identity matching rejects numeric-id and UUID rebinding", () => {
  const track = summary();

  assert.equal(trackDisplay.sameTrackIdentity(track, summary()), true);
  assert.equal(
    trackDisplay.sameTrackIdentity(track, summary({ track_id: 12 })),
    false
  );
  assert.equal(
    trackDisplay.sameTrackIdentity(track, summary({ catalog_uuid: "catalog-b" })),
    false
  );
  assert.equal(
    trackDisplay.sameTrackIdentity(track, summary({ track_uuid: "track-b" })),
    false
  );
});
