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
  assert.match(statusBlock, /sonaraJob && sonaraOutputs \? <span>\{sonaraOutputs\}<\/span>/);
  assert.match(statusBlock, /!sonaraJob && !classifierJob \? <span>Track batch/);
  assert.match(statusBlock, /!sonaraJob && !classifierJob && job\.inference_batch_size \? <span>Inference batch/);
  assert.match(statusBlock, /classifierJob \? <span>profiles/);
});

test("stage indicator prioritizes running destructive helper jobs and cancelled states", () => {
  const source = readFileSync(jobUiPath, "utf8");
  const indicatorBlock = source.match(/export function stageIndicatorLabel[\s\S]*?\n}/)?.[0] || "";

  assert.match(indicatorBlock, /audioDedupJob && \["queued", "running"\]\.includes\(audioDedupJob\.state\)/);
  assert.match(indicatorBlock, /return "Идет поиск дублей"/);
  assert.match(indicatorBlock, /audioDoctorJob && \["queued", "running"\]\.includes\(audioDoctorJob\.state\)/);
  assert.match(indicatorBlock, /return "Идет Audio Doctor"/);
  assert.match(indicatorBlock, /audioDedupJob\?\.state === "cancelled"/);
  assert.match(indicatorBlock, /audioDoctorJob\?\.state === "cancelled"/);
  assert.match(indicatorBlock, /return "Этап остановлен"/);
});
