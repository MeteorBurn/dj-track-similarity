import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src/", import.meta.url));

test("frontend exposes audio doctor api endpoints and types", () => {
  const source = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");

  assert.match(source, /export type AudioDoctorJobStatus/);
  assert.match(source, /export type AudioDoctorJobPayload/);
  assert.match(source, /\/api\/audio-doctor\/jobs/);
  assert.match(source, /audioDoctorXlsxUrl/);
});

test("topbar opens audio doctor before audio dedup", () => {
  const source = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  const actionsBlock = source.match(/<div className="topbar-actions">([\s\S]*?)<\/div>/)?.[1] || "";
  const doctorIndex = actionsBlock.indexOf("audio-doctor-launch-button");
  const dedupIndex = actionsBlock.indexOf("audio-dedup-launch-button");

  assert.notEqual(doctorIndex, -1);
  assert.notEqual(dedupIndex, -1);
  assert.ok(doctorIndex < dedupIndex);
});

test("audio doctor dialog keeps safe controls and hover hints", () => {
  const source = readFileSync(new URL("../src/AudioDoctorDialog.tsx", import.meta.url), "utf8");

  assert.match(source, /Selected DB/);
  assert.match(source, /Folder/);
  assert.match(source, /APPLY REPAIR/);
  assert.match(source, /keep-id3/i);
  assert.match(source, /title="[^"]*Purpose:/);
  assert.doesNotMatch(source, /APPLY DELETE/);
});
