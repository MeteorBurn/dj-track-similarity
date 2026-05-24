import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const dialogPath = fileURLToPath(new URL("../src/TrackMetadataDialog.tsx", import.meta.url));

test("spectral centroid uses the canonical display label", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /spectral_centroid_mean:\s*"Spectral Centroid"/);
  assert.doesNotMatch(source, /spectral_centroid_mean:\s*"Brightness"/);
});

test("sonara mean feature display labels omit mean while keeping database keys", () => {
  const source = readFileSync(dialogPath, "utf8");
  const labelsSource = source.match(/const sonaraFeatureLabels:[\s\S]*?};/)?.[0] || "";
  const labelEntries = [...labelsSource.matchAll(/^\s*(\w+_mean):\s*"([^"]+)"/gm)];
  const labelsByKey = new Map(labelEntries.map(([, key, label]) => [key, label]));

  assert.equal(labelsByKey.get("rms_mean"), "RMS");
  assert.equal(labelsByKey.get("mfcc_mean"), "MFCC");
  assert.equal(labelsByKey.get("chroma_mean"), "Chroma");
  for (const [key, label] of labelsByKey) {
    assert.ok(!/\bmean\b/i.test(label), `${key} label should not include mean: ${label}`);
  }
});

test("rms max uses uppercase RMS display label", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /rms_max:\s*"RMS max"/);
});

test("displayed sonara fields have built-in UI descriptions", () => {
  const source = readFileSync(dialogPath, "utf8");
  const displayedKeys = [
    "bpm",
    "beats",
    "onset_frames",
    "onset_density",
    "n_beats",
    "rms_mean",
    "rms_max",
    "loudness_lufs",
    "dynamic_range_db",
    "spectral_centroid_mean",
    "zero_crossing_rate",
    "duration_sec",
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "key",
    "key_confidence",
    "predominant_chord",
    "chord_change_rate",
    "dissonance",
    "spectral_bandwidth_mean",
    "spectral_rolloff_mean",
    "spectral_flatness_mean",
    "spectral_contrast_mean",
    "mfcc_mean",
    "chroma_mean"
  ];

  for (const key of displayedKeys) {
    assert.match(source, new RegExp(`${key}:\\s*"[^"]+"`), `${key} needs a UI description`);
  }
  assert.match(source, /description:\s*sonaraFeatureDescriptions\[key\]/);
  assert.doesNotMatch(source, /featureRecord\.description/);
  assert.match(source, /spectral_contrast_mean:\s*"Peak-valley ratio per band \(7 values\)"/);
  assert.match(source, /mfcc_mean:\s*"Timbre fingerprint \(13 coefficients\)"/);
  assert.match(source, /chroma_mean:\s*"Pitch class distribution \(12 values\)"/);
});

test("metadata dialog uses the track title as the only header title", () => {
  const source = readFileSync(dialogPath, "utf8");
  const dialogTitleBlock = source.match(/<div className="dialog-title">[\s\S]*?<\/div>/)?.[0] || "";

  assert.match(dialogTitleBlock, /metadata-track-title/);
  assert.match(dialogTitleBlock, /displayTrack\(track\)/);
  assert.doesNotMatch(dialogTitleBlock, /Теги и жанры/);
  assert.doesNotMatch(dialogTitleBlock, /basename\(track\.path\)/);
});

test("metadata dialog names the mutagen tag block", () => {
  const source = readFileSync(dialogPath, "utf8");
  const mutagenBlock = source.match(/<div className="mutagen-block">[\s\S]*?<\/div>/)?.[0] || "";

  assert.match(mutagenBlock, /<strong>Mutagen tags<\/strong>/);
  assert.match(mutagenBlock, /metadata-grid mutagen-grid/);
});
