import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const dialogPath = fileURLToPath(new URL("../src/TrackMetadataDialog.tsx", import.meta.url));

test("metadata uses current SONARA Core field names and reader labels", () => {
  const source = readFileSync(dialogPath, "utf8");
  const expected = new Map([
    ["detected_bpm", "BPM"],
    ["raw_bpm", "Raw BPM"],
    ["onset_density_per_second", "Onset density"],
    ["detected_key_name", "Key"],
    ["detected_key_camelot", "Camelot"],
    ["energy_score", "Energy"],
    ["danceability_score", "Danceability"],
    ["spectral_centroid_hz", "Spectral centroid"],
    ["integrated_loudness_lufs", "Integrated loudness"],
    ["true_peak_dbtp", "True peak"],
    ["vocal_probability", "Vocal probability"],
    ["mood_happy_score", "Happy"],
  ]);

  for (const [field, label] of expected) {
    assert.match(
      source,
      new RegExp(`feature\\("${field}",\\s*"${label}"`),
      `${field} should use the current v7 label`,
    );
  }
});

test("metadata descriptions keep model outputs as ranking signals", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /SONARA energy ranking signal/);
  assert.match(source, /SONARA danceability ranking signal/);
  assert.match(source, /SONARA valence ranking signal/);
  assert.match(source, /SONARA acousticness ranking signal/);
  assert.match(source, /Probability returned by the bundled SONARA vocal model/);
});

test("metadata header and file block are driven by the v7 detail", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /metadata-track-title">\{displayTrack\(track\)\}/);
  assert.match(source, /<strong>File and Mutagen tags<\/strong>/);
  assert.match(source, /\["Audio Length", formatDuration\(track\.file\.audio_duration_seconds \?\? track\.audio_duration_seconds\)\]/);
  assert.match(source, /\["File Path", track\.file_path\]/);
});

test("metadata reads exact file_tags fields without legacy metadata fallback", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /if \(!track\.file_tags\) return \[\];/);
  for (const field of [
    "genres",
    "tag_bpm",
    "tag_key",
    "comment",
    "year",
    "label",
    "catalog_number",
    "country",
    "isrc",
    "track_number",
    "disc_number",
  ]) {
    assert.match(source, new RegExp(`${field}:\\s*"`));
  }
  assert.doesNotMatch(source, /track\.metadata|track\.genre_scores|track\.genres/);
});

test("metadata exposes current analysis coverage including MuQ", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /\["sonara", "maest", "mert", "muq", "clap"\] as const/);
  assert.match(source, /trackHasAnalysis\(track, model\)/);
  assert.match(source, /track\.classifier_scores_detail\.length > 0/);
});

test("metadata shows exact embedding and classifier detail records", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /track\.embeddings\.map\(\(embedding\)/);
  assert.match(source, /embedding\.analysis_family\.toUpperCase\(\)/);
  assert.match(source, /embedding\.model_name/);
  assert.match(source, /embedding\.dim/);
  assert.match(source, /track\.classifier_scores_detail\.map\(\(score\)/);
  assert.match(source, /score\.feature_set/);
  assert.match(source, /score\.model_id/);
});

test("metadata keeps MAEST syncopated rhythm on the detailed MAEST payload", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /const genres = track\.maest\?\.genres \?\? \[\];/);
  assert.match(source, /syncopatedRhythm: hasMaestSyncopatedRhythm\(track\)/);
  assert.match(source, /SYNCOPATED_RHYTHM_LABEL/);
});
