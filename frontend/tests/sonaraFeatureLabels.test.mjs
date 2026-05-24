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
  const labelEntries = [...source.matchAll(/^\s*(\w+_mean):\s*"([^"]+)"/gm)];
  const labelsByKey = new Map(labelEntries.map(([, key, label]) => [key, label]));

  assert.equal(labelsByKey.get("rms_mean"), "RMS");
  assert.equal(labelsByKey.get("mfcc_mean"), "MFCC");
  assert.equal(labelsByKey.get("chroma_mean"), "Chroma");
  for (const [key, label] of labelsByKey) {
    assert.ok(!/\bmean\b/i.test(label), `${key} label should not include mean: ${label}`);
  }
});
