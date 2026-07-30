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
const syncopatedRhythm = compileModule("syncopatedRhythm.ts", (name) => {
  if (name === "./maestGenres") return { formatMaestGenreLabel: (value) => value };
  throw new Error(`Unexpected require: ${name}`);
});

const metadataDialog = compileModule("TrackMetadataDialog.tsx", (name) => {
  if (name === "lucide-react") return { Check: () => null, Copy: () => null, X: () => null };
  if (name === "react") return { Fragment: Symbol("Fragment"), useState: () => [false, () => {}] };
  if (name === "react/jsx-runtime") {
    return { Fragment: Symbol("Fragment"), jsx: () => null, jsxs: () => null };
  }
  if (name === "./syncopatedRhythm") {
    return {
      ...syncopatedRhythm,
      formatMaestGenreLabel: (value) => value,
    };
  }
  if (name === "./trackDisplay") return trackDisplay;
  throw new Error(`Unexpected require: ${name}`);
});

const referenceCompare = compileModule("ReferenceComparePanel.tsx", (name) => {
  if (name === "lucide-react") return { Search: () => null };
  if (name === "react") {
    return {
      useEffect: () => {},
      useRef: (value) => ({ current: value }),
      useState: (value) => [value, () => {}],
    };
  }
  if (name === "react/jsx-runtime") {
    return { Fragment: Symbol("Fragment"), jsx: () => null, jsxs: () => null };
  }
  if (name === "./api") return { api: {} };
  if (name === "./TrackRows") return { ResultRow: () => null };
  if (name === "./trackDisplay") return { displayTrack: () => "Track" };
  throw new Error(`Unexpected require: ${name}`);
});

function summary(overrides = {}) {
  return {
    track_id: 11,
    catalog_uuid: "catalog-a",
    track_uuid: "track-a",
    content_generation: 3,
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
      timeline: true,
      sonara_embedding: true,
      fingerprint: true,
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

function detail() {
  return {
    ...summary(),
    file: {
      file_size_bytes: 40 * 1024 * 1024,
      file_modified_ns: 1,
      audio_format: "audio/flac",
      audio_codec: "FLAC",
      sample_rate_hz: 48000,
      channel_count: 2,
      bit_rate_bps: 1000000,
      audio_duration_seconds: 247.37,
      last_scanned_at: "2026-07-24T10:00:00.123456Z",
      missing_since: null,
    },
    file_tags: {
      title: "Track",
      artist: "Artist",
      album: "Album",
      tag_bpm: 128,
      tag_key: "8A",
      comment: "Club mix",
      year: 2026,
      label: "Label",
      country: "UA",
      track_number: "1",
      genres: ["Breakbeat"],
      tags_read_at: "2026-07-24T10:00:00Z",
    },
    sonara_core: {
      detected_bpm: 128.125,
      raw_bpm: 128.125,
      bpm_confidence: 0.92,
      bpm_candidates: [{ bpm: 128.125, score: 0.92 }],
      vocal_probability: 0.35,
      vector_summaries: [],
      analyzed_at: "2026-07-24T10:01:00Z",
    },
    maest: {
      syncopated_rhythm: true,
      genres: [{ rank: 1, genre_name: "Breakbeat", score: 0.91 }],
      analyzed_at: "2026-07-24T10:02:00Z",
    },
    embeddings: [{
      analysis_family: "muq",
      model_version: "legacy-embedding-version",
      dim: 1024,
      normalization: "l2",
      analyzed_at: "2026-07-24T10:03:00Z",
    }],
    classifier_scores_detail: [{
      classifier_key: "voice_presence",
      score: 0.7,
      predicted_class: "present",
      score_bucket: "high",
      confidence: 0.8,
      probabilities: { present: 0.8 },
      feature_set: "muq",
      feature_names: ["muq:embedding_0", "sonara:energy_score", "muq:embedding_1"],
      positive_label: "present",
      analyzed_at: "2026-07-24T10:04:00Z",
    }],
    optional_outputs: {
      timeline_fields: ["beats", "energy_curve"],
      sonara_embedding_available: true,
      audio_fingerprint_available: true,
    },
  };
}

test("track display and analysis coverage use only current summary fields", () => {
  const track = summary({ title: null, artist: null });

  assert.equal(trackDisplay.displayTrack(track), "Artist - Track.flac");
  assert.equal(trackDisplay.trackHasAnalysis(track, "sonara"), true);
  assert.equal(trackDisplay.trackHasAnalysis(track, "maest"), true);
  assert.equal(trackDisplay.trackHasAnalysis(track, "muq"), true);
  assert.equal(trackDisplay.trackHasAnalysis(track, "clap"), false);
});

test("track detail identity matching rejects numeric-id rebinding and generation drift", () => {
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
  assert.equal(
    trackDisplay.sameTrackIdentity(track, summary({ content_generation: 4 })),
    false
  );
});

test("App aborts superseded detail requests and commits only the clicked identity", () => {
  const source = readFileSync(join(srcDir, "App.tsx"), "utf8");

  assert.match(source, /trackDetailRequestGuard\.current\.begin\(\)/);
  assert.match(source, /trackDetailAbortController\.current\?\.abort\(\)/);
  assert.match(source, /api\.track\(track\.track_id,\s*\{\s*signal: controller\.signal/);
  assert.match(source, /databaseCatalogUuidRef\.current !== track\.catalog_uuid/);
  assert.match(source, /!sameTrackIdentity\(track, fullTrack\)/);
  assert.match(source, /trackDetailRequestGuard\.current\.isCurrent\(token\)/);
});

test("syncopated rhythm reads the detailed MAEST record", () => {
  assert.equal(syncopatedRhythm.hasMaestSyncopatedRhythm(detail()), true);
  assert.equal(syncopatedRhythm.hasMaestSyncopatedRhythm({ ...detail(), maest: null }), false);
});

test("metadata model maps detailed file tags optional outputs MuQ and classifiers", () => {
  const model = metadataDialog.metadataDialogModel(detail());
  const entries = Array.from(
    model.primaryEntries,
    ([label, value]) => [label, value],
  );

  assert.deepEqual(entries, [
    ["File Path", "D:/Music/Artist - Track.flac"],
    ["File Name", "Artist - Track.flac"],
    ["File Size", "40.00 MB"],
    ["Title", "Track"],
    ["Artist", "Artist"],
    ["Album", "Album"],
    ["Year", "2026"],
    ["Country", "UA"],
    ["Label", "Label"],
    ["Genre", "Breakbeat"],
    ["BPM", "128"],
    ["Key", "8A"],
    ["Comment", "Club mix"],
    ["Audio Length", "4:07 (247.37 sec.)"],
    ["Audio Format", "audio/flac"],
    ["Audio Codec", "FLAC"],
    ["Sample Rate", "48,000 Hz"],
    ["Bit Rate", "1000 kbps"],
    ["Channels", "2"],
    ["Last Scanned", "24.07.2026 10:00:00"],
    ["Missing Since", "-"],
  ]);
  assert.equal(model.tagEntries, undefined);
  assert.equal(model.timelineFields.join(","), "beats,energy_curve");
  assert.equal(model.sonaraEmbeddingAvailable, true);
  assert.equal(model.audioFingerprintAvailable, true);
  assert.equal(model.syncopatedRhythm, true);
  assert.equal(model.embeddings[0].label, "MUQ");
  assert.match(model.embeddings[0].value, /1024D/);
  assert.doesNotMatch(model.embeddings[0].value, /legacy-embedding-version/);
  assert.match(model.classifierScores[0].value, /muq/);
  assert.deepEqual(
    model.classifierScores[0].featureNames,
    ["muq:embedding_0", "sonara:energy_score", "muq:embedding_1"]
  );
  assert.ok(model.analysisBadges.some((badge) => badge.key === "muq"));
  assert.ok(model.analysisBadges.some((badge) => badge.key === "classifiers"));
});

test("Reference Compare ordering preserves MuQ or supplies a model-scoped reason", () => {
  const groups = referenceCompare.orderedReferenceCompareGroups({
    seed_track_id: 11,
    groups: [{
      model: "mert",
      available: true,
      reason: null,
      results: [],
    }],
  });
  const models = Array.from(groups, (group) => group.model);
  const muq = groups.find((group) => group.model === "muq");

  assert.deepEqual(models, ["clap", "mert", "muq", "maest", "sonara"]);
  assert.equal(muq.available, false);
  assert.match(muq.reason, /MUQ availability/);

  const returnedMuq = { model: "muq", available: true, reason: null, results: [] };
  const withMuq = referenceCompare.orderedReferenceCompareGroups({
    seed_track_id: 11,
    groups: [returnedMuq],
  });
  assert.equal(withMuq.find((group) => group.model === "muq"), returnedMuq);
});

test("Reference Compare freshness includes catalog UUID track UUID generation and response seed", () => {
  const identity = referenceCompare.referenceTrackIdentityKey(summary());
  const otherCatalog = referenceCompare.referenceTrackIdentityKey(summary({ catalog_uuid: "catalog-b" }));
  const otherGeneration = referenceCompare.referenceTrackIdentityKey(summary({ content_generation: 4 }));

  assert.notEqual(identity, otherCatalog);
  assert.notEqual(identity, otherGeneration);
  assert.equal(referenceCompare.referenceCompareRequestIsCurrent(2, 2, identity, identity), true);
  assert.equal(referenceCompare.referenceCompareRequestIsCurrent(1, 2, identity, identity), false);
  assert.equal(referenceCompare.referenceCompareRequestIsCurrent(2, 2, identity, otherCatalog), false);
  assert.equal(referenceCompare.referenceCompareResponseIsCurrent(2, 2, identity, identity, 11, 11), true);
  assert.equal(referenceCompare.referenceCompareResponseIsCurrent(2, 2, identity, identity, 11, 12), false);
});
