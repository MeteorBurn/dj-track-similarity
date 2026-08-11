import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const jobUiPath = fileURLToPath(new URL("../src/jobUi.tsx", import.meta.url));

test("analysis progress collapses classifier rows into one CLASSIFIERS row", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const modelProgressBlock = source.match(/function ModelProgress[\s\S]*?function GenreTagProcessStatus/)?.[0] || "";

  assert.match(modelProgressBlock, /classifierProgressRow/);
  assert.match(modelProgressBlock, /label:\s*"CLASSIFIERS"/);
  assert.doesNotMatch(modelProgressBlock, /model\.replace\([^)]*\)\.toUpperCase\(\)/);
});

test("classifier aggregate advances once after all classifier rows advance", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const aggregateBlock = source.match(/function classifierProgressRow[\s\S]*?function [A-Z]/)?.[0] || "";

  assert.match(aggregateBlock, /Math\.min\(\.\.\.items\.map\(\(item\) => item\.processed\)\)/);
  assert.match(aggregateBlock, /Math\.min\(\.\.\.items\.map\(\(item\) => item\.analyzed\)\)/);
  assert.match(aggregateBlock, /Math\.max\(\.\.\.items\.map\(\(item\) => item\.failed\)\)/);
  assert.match(aggregateBlock, /Math\.max\(\.\.\.items\.map\(\(item\) => item\.total\)\)/);
});

test("analysis runtime label hides active classifier key behind CLASSIFIERS", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const runtimeBlock = source.match(/function analysisRuntimeLabel[\s\S]*?function AnalysisProcessStatus/)?.[0] || "";

  assert.match(runtimeBlock, /job\.classifier_keys\?\.length/);
  assert.match(runtimeBlock, /return "CLASSIFIERS"/);
  assert.doesNotMatch(runtimeBlock, /job\.current_model.*CLASSIFIERS/);
});

test("analysis status shows only settings that belong to the active stage", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const statusBlock = source.match(/function AnalysisProcessStatus[\s\S]*?function GenreTagProcessStatus/)?.[0] || "";

  assert.match(statusBlock, /sonaraJob \? <span>SONARA batch \{job\.sonara_batch_size/);
  assert.doesNotMatch(statusBlock, /sonaraOutputs|sonara_outputs/);
  assert.match(statusBlock, /!sonaraJob && !classifierJob \? <span>Track batch/);
  assert.match(statusBlock, /!sonaraJob && !classifierJob && job\.inference_batch_size \? <span>Inference batch/);
  assert.match(statusBlock, /classifierJob \? <span>profiles/);
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
