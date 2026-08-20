import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const dialogPath = fileURLToPath(new URL("../src/TrackMetadataDialog.tsx", import.meta.url));
const apiPath = fileURLToPath(new URL("../src/api.ts", import.meta.url));

test("metadata dialog accepts only the current detail response", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /import type \{ SonaraCore, TrackDetail \} from "\.\/api";/);
  assert.match(source, /track: TrackDetail;/);
  assert.doesNotMatch(source, /Track\s*\|\s*TrackDetail/);
  assert.doesNotMatch(source, /\.metadata\b|\.path\b|representation_fields/);
});

test("metadata dialog reads every current detail surface directly", () => {
  const source = readFileSync(dialogPath, "utf8");

  for (const field of [
    "track.file",
    "track.file_tags",
    "track.sonara_core",
    "track.maest",
    "track.embeddings",
    "track.classifier_scores_detail",
  ]) {
    assert.ok(source.includes(field), `missing detailed consumer: ${field}`);
  }
});

test("SONARA metadata shows feature groups only", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, />SONARA features</);
  assert.doesNotMatch(source, /SONARA · Timeline|SONARA · Embedding|SONARA · Fingerprint/);
  assert.doesNotMatch(source, /optional_outputs/);
  assert.doesNotMatch(source, /Representations|representation_fields/);
});

test("API exposes all current SONARA output statuses", () => {
  const source = readFileSync(apiPath, "utf8");

  assert.match(source, /output_kind: "core" \| "embedding" \| "fingerprint";/);
  assert.doesNotMatch(source, /timeline|sonara_embedding/);
});

test("metadata has no timeline loader or manifest", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.doesNotMatch(source, /TimelinePresenceBlock|timelineFields|sonaraTimeline/);
});

test("metadata copies the canonical file_path", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /copyTextToClipboard\(track\.file_path\)/);
  assert.match(source, /Copy file path/);
  assert.match(source, /copyTextToClipboard\(displayTrack\(track\)\)/);
  assert.match(source, /Copy file name/);
  assert.doesNotMatch(source, /track\.path/);
});

test("metadata opens the containing folder for the canonical track id", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /api\.revealTrackFile\(track\.track_id\)/);
  assert.match(source, /Open containing folder/);
});
