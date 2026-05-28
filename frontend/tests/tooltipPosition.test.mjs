import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

async function loadTooltipModule() {
  const sourcePath = new URL("../src/tooltip.ts", import.meta.url);
  if (!existsSync(sourcePath)) {
    throw new Error("frontend/src/tooltip.ts does not exist yet");
  }
  const tempDir = mkdtempSync(join(tmpdir(), "tooltip-test-"));
  const modulePath = join(tempDir, "tooltip.cjs");
  writeFileSync(modulePath, transpile(readFileSync(sourcePath, "utf8")), "utf8");
  return import(pathToFileURL(modulePath).href);
}

function transpile(source) {
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true
    }
  }).outputText;
}

test("tooltip position is clamped inside the viewport", async () => {
  const { placeTooltip } = await loadTooltipModule();
  const placement = placeTooltip(
    { left: 585, top: 8, width: 24, height: 24 },
    { width: 260, height: 58 },
    { width: 599, height: 1074 }
  );

  assert.equal(placement.left, 331);
  assert.equal(placement.top, 40);
  assert.equal(placement.placement, "bottom");
});

test("tooltip prefers top placement when there is room", async () => {
  const { placeTooltip } = await loadTooltipModule();
  const placement = placeTooltip(
    { left: 220, top: 260, width: 80, height: 34 },
    { width: 180, height: 42 },
    { width: 599, height: 1074 }
  );

  assert.equal(placement.left, 170);
  assert.equal(placement.top, 210);
  assert.equal(placement.placement, "top");
});
