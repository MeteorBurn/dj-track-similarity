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
  if (name === "lucide-react") return { Check: () => null, Copy: () => null, FolderOpen: () => null, X: () => null };
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
  if (name === "./apiClient") return { api: { revealTrackFile: async () => ({}) } };
  throw new Error(`Unexpected require: ${name}`);
});

const metadataDialogUi = compileModule("TrackMetadataDialog.tsx", (name) => {
  if (name === "lucide-react") {
    return {
      AudioWaveform: () => null,
      Check: () => null,
      Copy: () => null,
      FolderOpen: () => null,
      Pause: () => null,
      Play: () => null,
      Trash2: () => null,
      X: () => null,
    };
  }
  if (name === "react") return { Fragment: Symbol("Fragment"), useState: (value) => [value, () => {}] };
  if (name === "react/jsx-runtime") {
    return {
      Fragment: Symbol("Fragment"),
      jsx: (type, props) => ({ type, props }),
      jsxs: (type, props) => ({ type, props }),
    };
  }
  if (name === "./syncopatedRhythm") return { ...syncopatedRhythm, formatMaestGenreLabel: (value) => value };
  if (name === "./trackDisplay") return trackDisplay;
  if (name === "./apiClient") return { api: { revealTrackFile: async () => ({}) } };
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

function detail() {
  return {
    ...summary(),
    file: {
      file_size_bytes: 40 * 1024 * 1024,
      file_modified_ns: 1,
      audio_format: "audio/flac",
      sample_rate_hz: 48000,
      channel_count: 2,
      bit_rate_bps: 1000000,
      bit_depth: 24,
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
      bpm_min: 70,
      bpm_max: 180,
      analysis_schema_version: 6,
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

function expectedLocalTimestamp(value) {
  const date = new Date(value);
  const milliseconds = date.getMilliseconds();
  const hasFractionalSeconds = /\.(\d+)/.test(value) && milliseconds !== 0;
  const pad2 = (part) => String(part).padStart(2, "0");
  const pad3 = (part) => String(part).padStart(3, "0");
  return [
    `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}.${date.getFullYear()}`,
    `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}${hasFractionalSeconds ? `.${pad3(milliseconds)}` : ""}`,
  ].join(" ");
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

test("metadata dialog delegates its destructive track action to the current detail", () => {
  const track = detail();
  let deleted = null;
  const tree = metadataDialogUi.TrackMetadataDialog({
    track,
    onClose: () => {},
    onDelete: (value) => { deleted = value; },
    onPreview: () => {},
    playingTrackId: null,
  });

  const deleteButton = findByClassName(tree, "icon-button intent-remove metadata-delete-button");
  assert.ok(deleteButton);
  deleteButton.props.onClick();
  assert.equal(deleted, track);
});

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
  assert.equal(metadataDialog.metadataDialogModel({ ...detail(), maest: null }).maestAnalyzed, false);
});

test("metadata model maps detailed file tags MuQ and classifiers", () => {
  const model = metadataDialog.metadataDialogModel(detail());
  const trackDetailsEntries = Array.from(
    model.trackDetailsEntries,
    ([label, value]) => [label, value],
  );

  assert.deepEqual(trackDetailsEntries, [
    ["File Name", "Artist - Track"],
    ["File Path", "D:/Music/Artist - Track.flac"],
    ["File Size", "40.00 MB"],
  ]);
  assert.deepEqual(Array.from(model.tagEntries, ([label, value]) => [label, value]), [
    ["Title", "Track"],
    ["Artist", "Artist"],
    ["Album", "Album"],
    ["Year", "2026"],
    ["Country", "UA"],
    ["Label", "Label"],
    ["Genre", "Breakbeat"],
    ["Duration", "4:07"],
    ["BPM", "128"],
    ["Key", "8A"],
    ["Comment", "Club mix"],
  ]);
  assert.deepEqual(Array.from(model.audioEntries, ([label, value]) => [label, value]), [
    ["Audio Format", "audio/flac"],
    ["Audio Length", "247.37"],
    ["Sample Rate", "48,000 Hz"],
    ["Bit Rate", "1000 kbps"],
    ["Bit Depth", "24-bit"],
    ["Channels", "Stereo (2)"],
  ]);
  assert.deepEqual(Array.from(model.scanEntries, ([label, value]) => [label, value]), [
    ["Last Scanned", expectedLocalTimestamp("2026-07-24T10:00:00.123456Z")],
    ["Missing Since", "-"],
  ]);
  assert.deepEqual(Array.from(model.sonaraAnalysisEntries, ([label, value]) => [label, value]), [
    ["Analyzed at", expectedLocalTimestamp("2026-07-24T10:01:00Z")],
  ]);
  assert.deepEqual(Array.from(model.sonaraProvenanceEntries, ([label, value]) => [label, value]), [
    ["Analysis schema", "v6"],
  ]);
  assert.equal(model.analysisBadges, undefined);
  assert.equal(model.syncopatedRhythm, true);
  assert.equal(model.maestAnalyzed, true);
  assert.equal(new Map(model.audioEntries).has("Audio Codec"), false);
  assert.equal(model.embeddings[0].label, "MUQ");
  assert.match(model.embeddings[0].value, /1024D/);
  assert.ok(model.embeddings[0].value.includes(expectedLocalTimestamp("2026-07-24T10:03:00Z")));
  assert.doesNotMatch(model.embeddings[0].value, /legacy-embedding-version/);
  assert.equal(
    model.classifierScores[0].value,
    "present (high) · score 0.700000",
  );
  assert.deepEqual(Array.from(model.classifierAnalysisEntries, ([label, value]) => [label, value]), [
    ["Voice Presence", expectedLocalTimestamp("2026-07-24T10:04:00Z")],
  ]);

  assert.equal(new Map(model.audioEntries).get("Audio Format"), "audio/flac");
});

test("SONARA BPM candidates begin with the analysis range label", () => {
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
    bpm_min: 70,
    bpm_max: 180,
  });

  assert.equal(features.get("detected_bpm").value, "127.46");
  assert.equal(features.has("raw_bpm"), false);
  assert.equal(features.get("bpm_confidence").value, "0.92");
  assert.equal(
    features.get("bpm_candidates").value,
    "Analysis range (70–180 BPM): #1 129.20 (score 7.95)",
  );
  assert.equal(features.get("onset_density_per_second").value, "5.58/s");
  assert.equal(features.get("beat_count").value, "1,280");
  assert.equal(features.get("tempo_variability").value, "0.90%");
  assert.equal(features.get("beat_grid_offset_seconds").value, "488 ms");
  assert.equal(features.get("beat_grid_stability").value, "98.8%");
  assert.equal(features.get("analyzed_duration_seconds").value, "7:39");
  assert.equal(features.has("bpm_analysis_range"), false);

  const model = metadataDialog.metadataDialogModel({
    ...detail(),
    sonara_core: {
      ...detail().sonara_core,
      bpm_min: 70,
      bpm_max: 180,
    },
  });
  const tempo = model.coreGroups.find((group) => group.title === "Tempo");
  assert.ok(tempo);
});

test("SONARA clock fields use whole-second m:ss and h:mm:ss positions", () => {
  const inspected = sonaraFeatures({
    analyzed_duration_seconds: 584.421875,
    intro_end_seconds: 0.5108389854431152,
    outro_start_seconds: 559.8795776367188,
  });
  const common = sonaraFeatures({
    intro_end_seconds: 18,
    outro_start_seconds: 199,
  });
  const hour = sonaraFeatures({ analyzed_duration_seconds: 3723 });
  const carry = sonaraFeatures({ analyzed_duration_seconds: 59.6 });

  assert.equal(inspected.get("analyzed_duration_seconds").value, "9:44");
  assert.equal(inspected.get("intro_end_seconds").value, "0:01");
  assert.equal(inspected.get("outro_start_seconds").value, "9:20");
  assert.equal(common.get("intro_end_seconds").value, "0:18");
  assert.equal(common.get("outro_start_seconds").value, "3:19");
  assert.equal(hour.get("analyzed_duration_seconds").value, "1:02:03");
  assert.equal(carry.get("analyzed_duration_seconds").value, "1:00");
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
  assert.equal(features.get("energy_score").value, "0.51");
  assert.equal(features.get("danceability_score").value, "0.78");
  assert.equal(features.get("valence_score").value, "0.43");
  assert.equal(features.get("acousticness_score").value, "0.34");
  assert.equal(features.get("vocal_probability").label, "Vocal probability");
  assert.equal(features.get("vocal_probability").value, "0.13%");
  assert.equal(features.get("mood_happy_score").value, "0.409");
  assert.equal(features.get("mood_aggressive_score").value, "0.505");
  assert.equal(features.get("mood_relaxed_score").value, "0.343");
  assert.equal(features.get("mood_sad_score").value, "0.629");
});

test("SONARA model-backed groups precede Vector summaries and use dedicated formatting", () => {
  const track = detail();
  track.sonara_core = {
    ...track.sonara_core,
    energy_score: 0.7,
    mood_aggressive_score: 0.505047082901001,
    aggression_score: 0.6189124584197998,
    aggression_confidence: 0.9123457074165344,
    aggression_forcefulness: 0.6432198286056519,
    aggression_harshness: 0.4789124131202698,
    aggression_tension: 0.731246829032898,
    aggression_rhythm: 0.8567891120910645,
    vector_summaries: [{ vector_type: "mfcc_mean", dim: 13 }],
  };

  const model = metadataDialog.metadataDialogModel(track);
  const titles = Array.from(model.coreGroups, (group) => group.title);
  const vectorSummariesIndex = titles.indexOf("Vector summaries");
  assert.deepEqual(
    titles.slice(vectorSummariesIndex - 4, vectorSummariesIndex + 1),
    ["Perceptual", "Mood", "Aggression", "Vocalness", "Vector summaries"],
  );

  const mood = model.coreGroups.find((group) => group.title === "Mood");
  const vocalness = model.coreGroups.find((group) => group.title === "Vocalness");
  const aggression = model.coreGroups.find((group) => group.title === "Aggression");
  assert.equal(
    mood.features.some((feature) => feature.key === "vocal_probability"),
    false,
  );
  assert.equal(
    mood.features.find((feature) => feature.key === "mood_aggressive_score").label,
    "Aggressive",
  );
  assert.deepEqual(
    Array.from(vocalness.features, (feature) => feature.key),
    ["vocal_probability"],
  );
  assert.deepEqual(
    Array.from(aggression.features, (feature) => [feature.key, feature.value]),
    [
      ["aggression_score", "0.619"],
      ["aggression_confidence", "0.912"],
      ["aggression_forcefulness", "0.643"],
      ["aggression_harshness", "0.479"],
      ["aggression_tension", "0.731"],
      ["aggression_rhythm", "0.857"],
    ],
  );
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

test("SONARA tonal metadata separates musical and Camelot keys", () => {
  const tonalCore = {
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
  };
  const features = sonaraFeatures(tonalCore);

  assert.equal(features.get("detected_key_name").value, "A minor");
  assert.equal(features.get("detected_key_camelot").value, "8A");
  assert.equal(features.get("key_confidence").value, "0.15");
  assert.equal(
    features.get("key_candidates").value,
    "#1 8A · A minor (0.26)",
  );
  assert.equal(features.get("predominant_chord").value, "Am");
  assert.equal(features.get("chord_changes_per_second").value, "1.75/s");
  assert.equal(features.get("dissonance_score").value, "0.018");
  const tonal = metadataDialog.metadataDialogModel({
    ...detail(),
    sonara_core: { ...detail().sonara_core, ...tonalCore },
  }).coreGroups.find((group) => group.title === "Tonal");
  assert.deepEqual(Array.from(tonal.features, (feature) => feature.key), [
    "detected_key_name",
    "key_confidence",
    "key_candidates",
    "detected_key_camelot",
    "predominant_chord",
    "chord_changes_per_second",
    "dissonance_score",
  ]);
});

test("SONARA loudness metadata uses meaningful precision", () => {
  const features = sonaraFeatures({
    rms_mean: 0.20517976582050324,
    rms_max: 0.525765597820282,
    integrated_loudness_lufs: -14.789587020874023,
    dynamic_range_db: 21.840232849121094,
    true_peak_dbtp: -0.04332813620567322,
    replay_gain_db: 0.6638298034667969,
    max_momentary_loudness_lufs: -11.292563438415527,
    loudness_range_lu: 4.79802131652832,
  });

  assert.equal(features.get("rms_mean").value, "0.205");
  assert.equal(features.get("rms_max").value, "0.526");
  assert.equal(features.get("integrated_loudness_lufs").value, "-14.8 LUFS");
  assert.equal(features.get("dynamic_range_db").value, "21.8 dB");
  assert.equal(features.get("true_peak_dbtp").value, "-0.04 dBTP");
  assert.equal(features.get("replay_gain_db").value, "+0.66 dB");
  assert.equal(features.get("max_momentary_loudness_lufs").value, "-11.3 LUFS");
  assert.equal(features.get("loudness_range_lu").value, "4.8 LU");
  const loudness = metadataDialog.metadataDialogModel({
    ...detail(),
    sonara_core: { ...detail().sonara_core, integrated_loudness_lufs: -14.8, loudness_range_lu: 4.8, dynamic_range_db: 21.8, max_momentary_loudness_lufs: -11.3, true_peak_dbtp: -0.04, rms_mean: 0.205, rms_max: 0.526, replay_gain_db: 0.66 },
  }).coreGroups.find((group) => group.title === "Loudness");
  assert.deepEqual(Array.from(loudness.features, (feature) => feature.key), [
    "integrated_loudness_lufs",
    "loudness_range_lu",
    "dynamic_range_db",
    "max_momentary_loudness_lufs",
    "true_peak_dbtp",
    "rms_mean",
    "rms_max",
    "replay_gain_db",
  ]);
});

test("SONARA structure and spectral metadata uses natural display units", () => {
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
  });

  assert.equal(features.get("intro_end_seconds").value, "0:03");
  assert.equal(features.get("outro_start_seconds").value, "7:27");
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
  assert.equal(features.has("analyzed_at"), false);
});

test("Reference Compare ordering preserves MuQ-MuLan or supplies a model-scoped reason", () => {
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
  const mulan = groups.find((group) => group.model === "mulan");

  assert.deepEqual(models, ["clap", "mert", "muq", "mulan", "maest", "sonara"]);
  assert.equal(muq.available, false);
  assert.match(muq.reason, /MUQ availability/);
  assert.equal(mulan.available, false);
  assert.match(mulan.reason, /MULAN availability/);

  const returnedMulan = { model: "mulan", available: true, reason: null, results: [] };
  const withMulan = referenceCompare.orderedReferenceCompareGroups({
    seed_track_id: 11,
    groups: [returnedMulan],
  });
  assert.equal(withMulan.find((group) => group.model === "mulan"), returnedMulan);
});

test("Reference Compare freshness includes catalog UUID track UUID and response seed", () => {
  const identity = referenceCompare.referenceTrackIdentityKey(summary());
  const otherCatalog = referenceCompare.referenceTrackIdentityKey(summary({ catalog_uuid: "catalog-b" }));
  const otherTrack = referenceCompare.referenceTrackIdentityKey(summary({ track_uuid: "track-b" }));

  assert.notEqual(identity, otherCatalog);
  assert.notEqual(identity, otherTrack);
  assert.equal(referenceCompare.referenceCompareRequestIsCurrent(2, 2, identity, identity), true);
  assert.equal(referenceCompare.referenceCompareRequestIsCurrent(1, 2, identity, identity), false);
  assert.equal(referenceCompare.referenceCompareRequestIsCurrent(2, 2, identity, otherCatalog), false);
  assert.equal(referenceCompare.referenceCompareResponseIsCurrent(2, 2, identity, identity, 11, 11), true);
  assert.equal(referenceCompare.referenceCompareResponseIsCurrent(2, 2, identity, identity, 11, 12), false);
});
