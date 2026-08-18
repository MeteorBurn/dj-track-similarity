import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const jobUiPath = fileURLToPath(new URL("../src/jobUi.tsx", import.meta.url));

test("scan progress shows the skipped track count", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const statusBlock = source.match(/function ScanProcessStatus[\s\S]*?function UnifiedEventList/)?.[0] || "";

  assert.match(statusBlock, /job\.skipped \? <span>skip \{job\.skipped\}<\/span>/);
});

test("analysis progress keeps the active classifier key", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const modelProgressBlock = source.match(/function ModelProgress[\s\S]*?function GenreTagProcessStatus/)?.[0] || "";

  assert.match(modelProgressBlock, /label: model\.toUpperCase\(\)/);
  assert.doesNotMatch(modelProgressBlock, /classifierProgressRow/);
});

test("classifier progress does not aggregate several classifier rows", () => {
  const source = readFileSync(jobUiPath, "utf8");

  assert.doesNotMatch(source, /classifierProgressRow|Math\.min\(\.\.\.items|Math\.max\(\.\.\.items/);
});

test("analysis runtime label shows the active classifier key", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const runtimeBlock = source.match(/function analysisRuntimeLabel[\s\S]*?function AnalysisProcessStatus/)?.[0] || "";

  assert.match(runtimeBlock, /job\.classifier_keys\?\.\[0\]/);
  assert.match(runtimeBlock, /return job\.classifier_keys\[0\]\.toUpperCase\(\)/);
});

test("analysis status shows only settings that belong to the active stage", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const statusBlock = source.match(/function AnalysisProcessStatus[\s\S]*?function GenreTagProcessStatus/)?.[0] || "";

  assert.match(statusBlock, /sonaraJob \? <span>SONARA \{job\.sonara_mode === "staged" \? "Staged" : "Direct"\}/);
  assert.match(statusBlock, /sonaraJob \? <span>BatchSize \{job\.sonara_batch_size/);
  assert.doesNotMatch(statusBlock, /sonaraOutputs|sonara_outputs/);
  assert.match(statusBlock, /!sonaraJob && !classifierJob \? <span>Track batch/);
  assert.match(statusBlock, /!sonaraJob && !classifierJob && job\.inference_batch_size \? <span>Inference batch/);
  assert.match(statusBlock, /classifierJob \? <span>classifier/);
});

test("stage indicator reports active and cancelled core jobs", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const indicatorBlock = source.match(/export function stageIndicatorLabel[\s\S]*?\n}/)?.[0] || "";

  assert.match(indicatorBlock, /genreTagJob && \["queued", "running"\]\.includes\(genreTagJob\.state\)/);
  assert.match(indicatorBlock, /return "Идет запись жанров"/);
  assert.doesNotMatch(indicatorBlock, /audio(Dedup|Doctor)/);
  assert.match(indicatorBlock, /return "Этап остановлен"/);
});

test("unified event log brackets the source label before each message", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const eventListBlock = source.match(/function UnifiedEventList[\s\S]*?function sourceLabel/)?.[0] || "";

  assert.match(eventListBlock, /<strong>\{event\.level\}<\/strong>/);
  assert.match(eventListBlock, /<span>\[\{sourceLabel\(event\.source\)\}\]: \{event\.message\}/);
  assert.doesNotMatch(eventListBlock, /sourceLabel\(event\.source\):/);
});
