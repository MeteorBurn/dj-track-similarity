import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const dialogPath = fileURLToPath(new URL("../src/TrackMetadataDialog.tsx", import.meta.url));

test("metadata uses current SONARA Core field names and reader labels", () => {
  const source = readFileSync(dialogPath, "utf8");
  const expected = new Map([
    ["detected_bpm", "BPM"],
    ["onset_density_per_second", "Onset density"],
    ["detected_key_name", "Key"],
    ["detected_key_camelot", "Key camelot"],
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
      `${field} should use the current label`,
    );
  }
});

test("metadata descriptions keep model outputs as ranking signals", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /Relative perceived-intensity ranking signal/);
  assert.match(source, /Relative beat-and-rhythm suitability ranking signal/);
  assert.match(source, /Relative mood-brightness ranking signal/);
  assert.match(source, /Relative acoustic-versus-electronic character ranking signal/);
  assert.match(source, /Probability returned by the bundled vocal model/);
});

test("metadata header and file block are driven by the current detail", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /metadata-track-title">\s*<span>\{displayTrack\(track\)\}<\/span>/);
  assert.match(source, /metadata-track-title[\s\S]*metadata-preview-button/);
  assert.match(source, /className="metadata-dialog-close-actions"/);
  assert.doesNotMatch(source, /metadata-dialog-actions/);
  assert.match(source, /<strong>Track Details<\/strong>/);
  assert.match(source, /<summary>Data<\/summary>/);
  assert.match(source, /\["Audio Length", formatAudioLength\(duration\)\]/);
  assert.match(source, /seconds\.toFixed\(2\)/);
  assert.match(source, /\["Last Scanned", formatTimestamp\(track\.file\.last_scanned_at\)\]/);
  assert.match(source, /\["File Name", displayTrack\(track\)\]/);
  assert.match(source, /\["File Path", track\.file_path\]/);
});

test("metadata reads exact file_tags fields without legacy metadata fallback", () => {
  const source = readFileSync(dialogPath, "utf8");

  for (const field of [
    "genres",
    "tag_bpm",
    "tag_key",
    "year",
    "label",
    "country",
  ]) {
    assert.match(source, new RegExp(`tags\\?\\.${field}|tags\\.${field}`));
  }
  assert.doesNotMatch(source, /catalog_number|disc_number|\bisrc\b/);
  assert.doesNotMatch(source, /track\.metadata|track\.genre_scores|track\.genres/);
});

test("metadata renders MAEST genres in a dedicated block instead of analysis badges", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /className="maest-genres-block"/);
  assert.match(source, /title="MAEST-detected genres"/);
  assert.match(source, /MAEST analysis has not been run for this track/);
  assert.match(source, /maestAnalyzed: track\.maest !== null/);
  assert.match(source, /className="metadata-data-details"/);
  assert.match(source, /className="metadata-scan-analyses-details"/);
  assert.match(source, /<summary>Scan analyses details<\/summary>/);
  assert.match(source, /File scan \(Mutagen\)/);
  assert.match(source, /metadata-scan-analyses-section-title">SONARA/);
  assert.match(source, /className="metadata-classifier-block"/);
  assert.doesNotMatch(source, /metadata-(?:scan|embedding)-details/);
  assert.doesNotMatch(source, /mutagen-(?:block|grid)|tag-grid|metadata-scan-state/);
  assert.doesNotMatch(source, /analysis-badge-row|analysis-badge|readableAnalysisBadges|trackHasAnalysis/);
});

test("metadata shows structural embedding and classifier analysis detail records", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /track\.embeddings\.map\(\(embedding\)/);
  assert.match(source, /embedding\.analysis_family\.toUpperCase\(\)/);
  assert.match(source, /embedding\.dim/);
  assert.match(source, /embedding\.normalization/);
  assert.match(source, /track\.classifier_scores_detail\.map\(\(score\)/);
  assert.match(source, /score\.analyzed_at/);
  assert.doesNotMatch(source, /embedding\.model_(?:name|version)|score\.model_id/);
});

test("metadata keeps MAEST syncopated rhythm on the detailed MAEST payload", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /const genres = track\.maest\?\.genres \?\? \[\];/);
  assert.match(source, /syncopatedRhythm: hasMaestSyncopatedRhythm\(track\)/);
  assert.match(source, /SYNCOPATED_RHYTHM_LABEL/);
  assert.match(source, /className="maest-syncopated-rhythm-indicator"/);
  assert.match(source, /<AudioWaveform size=\{13\} \/>/);
  assert.doesNotMatch(source, /maest-syncopated-rhythm-pill/);
});
