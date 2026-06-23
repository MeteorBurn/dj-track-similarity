import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const source = readFileSync(fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url)), "utf8");

test("hybrid preview clears stale state when preview inputs change", () => {
  assert.match(source, /const hybridInputKey = formatHybridInputKey/);
  assert.match(source, /const showHybridResults = showHybridDiagnostics && hybridResults\.length > 0;/);
  assert.match(
    source,
    /useEffect\(\(\) => \{[\s\S]*setHybridError\(""\);[\s\S]*setHybridResults\(\[\]\);[\s\S]*setHybridWarnings\(\[\]\);[\s\S]*setHybridLimitations\(\[\]\);[\s\S]*setHybridWeightsUsed\(\{\}\);[\s\S]*setHybridPreviewKey\(""\);[\s\S]*\}, \[hybridInputKey\]\);/
  );
});

test("hybrid preview clears current rows before backend errors are shown", () => {
  assert.match(
    source,
    /catch \(error\) \{[\s\S]*setHybridResults\(\[\]\);[\s\S]*setHybridWarnings\(\[\]\);[\s\S]*setHybridLimitations\(\[\]\);[\s\S]*setHybridWeightsUsed\(\{\}\);[\s\S]*setHybridPreviewKey\(""\);[\s\S]*setHybridError\(message\);[\s\S]*\}/
  );
});

test("hybrid backend limitations stay out of the default result area", () => {
  assert.doesNotMatch(source, /\[\.\.\.hybridWarnings,\s*\.\.\.hybridLimitations\]/);
  assert.match(source, /title=\{hybridDiagnosticTitle\}/);
  assert.match(source, /Preview score is weighted RRF, not confidence\./);
});
