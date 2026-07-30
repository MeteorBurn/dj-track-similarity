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
    "track.optional_outputs",
  ]) {
    assert.ok(source.includes(field), `missing detailed consumer: ${field}`);
  }
});

test("SONARA storage is shown as Core Timeline Embedding and Fingerprint", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, />SONARA · Core</);
  assert.match(source, /<strong>SONARA · Timeline<\/strong>/);
  assert.match(source, /title="SONARA · Embedding"/);
  assert.match(source, /title="SONARA · Fingerprint"/);
  assert.match(source, /track\.optional_outputs\.timeline_fields/);
  assert.match(source, /track\.optional_outputs\.sonara_embedding_available/);
  assert.match(source, /track\.optional_outputs\.audio_fingerprint_available/);
  assert.doesNotMatch(source, /Representations|representation_fields/);
});

test("API keeps the four independent SONARA output identifiers", () => {
  const source = readFileSync(apiPath, "utf8");

  assert.match(source, /export type SonaraOutput = "core" \| "timeline" \| "embedding" \| "fingerprint";/);
  assert.doesNotMatch(source, /SonaraOutput[^\n]*representations/);
});

test("metadata lists timeline manifest names without loading timeline values", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /fields\.map\(\(field\) => <code key=\{field\}>\{field\}<\/code>\)/);
  assert.doesNotMatch(source, /api\.sonaraTimeline|JSON\.stringify\(timeline/);
});

test("metadata copies the canonical file_path", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /copyTextToClipboard\(track\.file_path\)/);
  assert.match(source, /aria-label=\{`Copy file path: \$\{track\.file_path\}`\}/);
  assert.doesNotMatch(source, /track\.path/);
});
