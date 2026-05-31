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

  assert.match(runtimeBlock, /classifierKeySet\.has\(job\.current_model\)/);
  assert.match(runtimeBlock, /now CLASSIFIERS/);
});
