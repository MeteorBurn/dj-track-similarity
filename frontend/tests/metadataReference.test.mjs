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

function sonaraFeatures(overrides = {}) {
  const track = detail();
  track.sonara_core = {
    ...track.sonara_core,
    ...overrides,
  };
  const model = metadataDialog.metadataDialogModel(track);
  return new Map(
    Array.from(
      model.coreGroups,
      (group) => Array.from(
        group.features,
        (feature) => [feature.key, feature],
      ),
    ).flat(),
  );
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

test("SONARA tempo metadata uses tempo-specific units and omits raw BPM", () => {
  const features = sonaraFeatures({
    detected_bpm: 127.45889282226563,
    raw_bpm: 63.72944641113281,
    bpm_confidence: 0.9237096309661865,
    bpm_candidates: [{
      bpm: 129.19921875,
      rank: 1,
      score: 7.945353031158447,
    }],
    onset_density_per_second: 5.5766119956970215,
    beat_count: 1280,
    tempo_variability: 0.009005584754049778,
    beat_grid_offset_seconds: 0.4876190423965454,
    beat_grid_stability: 0.98765,
    analyzed_duration_seconds: 459.3149719238281,
  });

  assert.equal(features.get("detected_bpm").value, "127.46");
  assert.equal(features.has("raw_bpm"), false);
  assert.equal(features.get("bpm_confidence").value, "0.924");
  assert.equal(
    features.get("bpm_candidates").value,
    "#1 129.20 (score 7.95)",
  );
  assert.equal(features.get("onset_density_per_second").value, "5.58/s");
  assert.equal(features.get("beat_count").value, "1,280");
  assert.equal(features.get("tempo_variability").value, "0.90%");
  assert.equal(features.get("beat_grid_offset_seconds").value, "488 ms");
  assert.equal(features.get("beat_grid_stability").value, "98.8%");
  assert.equal(features.get("analyzed_duration_seconds").value, "7:39.31");
});

test("SONARA perceptual scores stay decimal while vocal probability is a percentage", () => {
  const features = sonaraFeatures({
    energy_level: 8,
    energy_score: 0.5127902626991272,
    danceability_score: 0.7814155220985413,
    valence_score: 0.4305143356323242,
    acousticness_score: 0.34270256757736206,
    vocal_probability: 0.0013234736397862434,
    mood_happy_score: 0.40928906202316284,
    mood_aggressive_score: 0.505047082901001,
    mood_relaxed_score: 0.3425803780555725,
    mood_sad_score: 0.6289721131324768,
  });

  assert.equal(features.get("energy_level").value, "8/10");
  assert.equal(features.get("energy_score").value, "0.513");
  assert.equal(features.get("danceability_score").value, "0.781");
  assert.equal(features.get("valence_score").value, "0.431");
  assert.equal(features.get("acousticness_score").value, "0.343");
  assert.equal(features.get("vocal_probability").label, "Vocal probability");
  assert.equal(features.get("vocal_probability").value, "0.13%");
  assert.equal(features.get("mood_happy_score").value, "0.409");
  assert.equal(features.get("mood_aggressive_score").value, "0.505");
  assert.equal(features.get("mood_relaxed_score").value, "0.343");
  assert.equal(features.get("mood_sad_score").value, "0.629");
});

test("SONARA probability and variability formatting preserves open boundaries", () => {
  assert.equal(sonaraFeatures({ vocal_probability: 0 }).get("vocal_probability").value, "0%");
  assert.equal(
    sonaraFeatures({ vocal_probability: 0.000000026 }).get("vocal_probability").value,
    "<0.01%",
  );
  assert.equal(
    sonaraFeatures({ vocal_probability: 0.99995 }).get("vocal_probability").value,
    ">99.99%",
  );
  assert.equal(sonaraFeatures({ vocal_probability: 1 }).get("vocal_probability").value, "100%");
  assert.equal(sonaraFeatures({ tempo_variability: 0 }).get("tempo_variability").value, "0%");
  assert.equal(
    sonaraFeatures({ tempo_variability: 0.00005 }).get("tempo_variability").value,
    "<0.01%",
  );
});

test("SONARA tonal and loudness metadata uses meaningful precision", () => {
  const features = sonaraFeatures({
    detected_key_camelot: "8A",
    detected_key_name: "A minor",
    key_confidence: 0.14823633432388306,
    key_candidates: [{
      camelot: "8A",
      key_name: "A minor",
      rank: 1,
      score: 0.26243653893470764,
    }],
    predominant_chord: "Am",
    chord_changes_per_second: 1.7499626874923706,
    dissonance_score: 0.018194174394011498,
    rms_mean: 0.20517976582050324,
    rms_max: 0.525765597820282,
    integrated_loudness_lufs: -14.789587020874023,
    dynamic_range_db: 21.840232849121094,
    true_peak_dbtp: -0.04332813620567322,
    replay_gain_db: 0.6638298034667969,
    max_momentary_loudness_lufs: -11.292563438415527,
    loudness_range_lu: 4.79802131652832,
  });

  assert.equal(features.get("detected_key_camelot").value, "8A");
  assert.equal(features.get("detected_key_name").value, "A minor");
  assert.equal(features.get("key_confidence").value, "0.148");
  assert.equal(
    features.get("key_candidates").value,
    "#1 8A · A minor (0.262)",
  );
  assert.equal(features.get("predominant_chord").value, "Am");
  assert.equal(features.get("chord_changes_per_second").value, "1.75/s");
  assert.equal(features.get("dissonance_score").value, "0.0182");
  assert.equal(features.get("rms_mean").value, "0.205");
  assert.equal(features.get("rms_max").value, "0.526");
  assert.equal(features.get("integrated_loudness_lufs").value, "-14.8 LUFS");
  assert.equal(features.get("dynamic_range_db").value, "21.8 dB");
  assert.equal(features.get("true_peak_dbtp").value, "-0.04 dBTP");
  assert.equal(features.get("replay_gain_db").value, "+0.66 dB");
  assert.equal(features.get("max_momentary_loudness_lufs").value, "-11.3 LUFS");
  assert.equal(features.get("loudness_range_lu").value, "4.8 LU");
});

test("SONARA structure spectral and analysis metadata uses natural display units", () => {
  const features = sonaraFeatures({
    intro_end_seconds: 3.0650339126586914,
    outro_start_seconds: 447.4949645996094,
    leading_silence_seconds: 0.09287981688976288,
    trailing_silence_seconds: 0.9055781960487366,
    energy_curve_hop_seconds: 0.5108389854431152,
    energy_curve_sample_count: 1206,
    energy_curve_min: 0.20326408743858337,
    energy_curve_max: 0.6382578015327454,
    energy_curve_mean: 0.5131758797468076,
    energy_curve_stddev: 0.07051395720072552,
    spectral_centroid_hz: 2078.814697265625,
    spectral_bandwidth_hz: 2462.879638671875,
    spectral_rolloff_hz: 4500.17236328125,
    spectral_flatness: 0.03053215704858303,
    zero_crossing_rate: 0.059822872281074524,
    analyzed_at: "2026-07-30T09:51:32.510995Z",
  });

  assert.equal(features.get("intro_end_seconds").value, "0:03.1");
  assert.equal(features.get("outro_start_seconds").value, "7:27.5");
  assert.equal(features.get("leading_silence_seconds").value, "0.09 s");
  assert.equal(features.get("trailing_silence_seconds").value, "0.91 s");
  assert.equal(features.get("energy_curve_hop_seconds").value, "511 ms");
  assert.equal(features.get("energy_curve_sample_count").value, "1,206");
  assert.equal(features.get("energy_curve_min").value, "0.203");
  assert.equal(features.get("energy_curve_max").value, "0.638");
  assert.equal(features.get("energy_curve_mean").value, "0.513");
  assert.equal(features.get("energy_curve_stddev").value, "0.0705");
  assert.equal(features.get("spectral_centroid_hz").value, "2,079 Hz");
  assert.equal(features.get("spectral_bandwidth_hz").value, "2,463 Hz");
  assert.equal(features.get("spectral_rolloff_hz").value, "4,500 Hz");
  assert.equal(features.get("spectral_flatness").value, "0.0305");
  assert.equal(features.get("zero_crossing_rate").value, "0.0598");
  assert.equal(features.get("analyzed_at").value, "30.07.2026 09:51:32 UTC");
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
