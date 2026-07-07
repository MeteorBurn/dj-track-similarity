import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src/", import.meta.url));

test("frontend exposes audio doctor api endpoints and types", () => {
  const source = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
  const clientSource = readFileSync(new URL("../src/apiClient.ts", import.meta.url), "utf8");

  assert.match(source, /export type AudioDoctorJobStatus/);
  assert.match(source, /export type AudioDoctorJobPayload/);
  assert.match(clientSource, /\/api\/audio-doctor\/jobs/);
  assert.match(clientSource, /audioDoctorXlsxUrl/);
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

test("topbar exposes a separate server shutdown button", () => {
  const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  const apiSource = readFileSync(new URL("../src/apiClient.ts", import.meta.url), "utf8");
  const actionsBlock = appSource.match(/<div className="topbar-actions">([\s\S]*?)<\/div>/)?.[1] || "";

  assert.match(apiSource, /shutdownServer:\s*\(\)\s*=>/);
  assert.match(apiSource, /\/api\/server\/shutdown/);
  assert.match(apiSource, /X-DJ-Track-Similarity-Action/);
  assert.match(appSource, /async function handleShutdownServer/);
  assert.match(actionsBlock, /server-shutdown-button[\s\S]*stop-active-stage-button/);
  assert.match(actionsBlock, /title="Остановить текущий сервер"/);
  assert.match(actionsBlock, /aria-label="Остановить текущий сервер"/);
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

test("audio doctor apply mode rejects every confirmation except APPLY REPAIR", () => {
  const source = readFileSync(new URL("../src/AudioDoctorDialog.tsx", import.meta.url), "utf8");
  const startBlock = source.match(/async function start\(\) \{[\s\S]*?await onStart\(\{[\s\S]*?\n    \}\);/)?.[0] || "";

  assert.match(startBlock, /applyMode && confirmation\.trim\(\) !== "APPLY REPAIR"/);
  assert.match(startBlock, /setLocalError\('Для apply mode нужно ввести "APPLY REPAIR"'\)/);
  assert.match(startBlock, /apply: applyMode/);
  assert.match(startBlock, /confirmation: applyMode \? confirmation\.trim\(\) : null/);
  assert.doesNotMatch(startBlock, /APPLY DELETE/);
});

test("audio dedup apply mode rejects every confirmation except APPLY DELETE", () => {
  const source = readFileSync(new URL("../src/AudioDedupDialog.tsx", import.meta.url), "utf8");
  const startBlock = source.match(/async function start\(\) \{[\s\S]*?await onStart\(\{[\s\S]*?\n    \}\);/)?.[0] || "";

  assert.match(source, /Apply delete safe candidates/);
  assert.match(source, /placeholder="APPLY DELETE"/);
  assert.match(source, /Required exact confirmation for destructive apply mode/);
  assert.match(startBlock, /applyMode && confirmation\.trim\(\) !== "APPLY DELETE"/);
  assert.match(startBlock, /setLocalError\('Для apply mode нужно ввести "APPLY DELETE"'\)/);
  assert.match(startBlock, /apply: applyMode/);
  assert.match(startBlock, /confirmation: applyMode \? confirmation\.trim\(\) : null/);
  assert.doesNotMatch(startBlock, /APPLY REPAIR/);
});
