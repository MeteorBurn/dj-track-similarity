import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const dialogPath = fileURLToPath(new URL("../src/TrackMetadataDialog.tsx", import.meta.url));
const apiPath = fileURLToPath(new URL("../src/api.ts", import.meta.url));
const libraryPanelPath = fileURLToPath(new URL("../src/LibraryPanel.tsx", import.meta.url));

test("metadata dialog reads lightweight storage manifests from the track row", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /const timelineFields = track\.timeline_fields \|\| \[\];/);
  assert.match(source, /const representationFields = track\.representation_fields \|\| \[\];/);
  assert.doesNotMatch(source, /sonaraTimeline\(track\.id\)/);
  assert.doesNotMatch(source, /JSON\.stringify\(timeline/);
});

test("metadata dialog renders separate Timeline and Representations presence blocks", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /StoragePresenceBlock title="Timeline" fields=\{timelineFields\}/);
  assert.match(source, /StoragePresenceBlock title="Representations" fields=\{representationFields\}/);
  assert.match(source, /Данные присутствуют/);
});

test("storage presence blocks list exact field names without loading values", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /fields\.map\(\(field\) => <code key=\{field\}>\{field\}<\/code>\)/);
  assert.match(source, /fields\.length \?/);
  assert.match(source, /Timeline данные ещё не рассчитаны/);
  assert.match(source, /Representations ещё не рассчитаны/);
});

test("track API contract exposes both sidecar field manifests", () => {
  const source = readFileSync(apiPath, "utf8");

  assert.match(source, /timeline_fields\?: string\[\] \| null;/);
  assert.match(source, /representation_fields\?: string\[\] \| null;/);
});

test("analysis panel exposes independent SONARA storage checkboxes", () => {
  const source = readFileSync(libraryPanelPath, "utf8");

  assert.match(source, /\["core", "timeline", "representations"\]/);
  assert.match(source, /checked=\{sonaraOutputs\.includes\(output\)\}/);
  assert.match(source, /По умолчанию/);
  assert.match(source, /Явный opt-in/);
  assert.match(source, /native batch/);
});

test("metadata dialog renders saved compact SONARA vectors as component values", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /const compactValues = compactNumericValues\(value\);/);
  assert.match(source, /compactValues\.map\(formatNumber\)\.join\(", "\)/);
  assert.match(source, /flattened\.length <= 64/);
});
