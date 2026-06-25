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
  assert.match(source, /Preview score is adjusted weighted RRF\./);
});

test("hybrid preview sends optional transition risk penalty", () => {
  assert.match(source, /const \[hybridTransitionRiskWeight, setHybridTransitionRiskWeight\] = useState\(0\);/);
  assert.match(source, /transition_risk_weight: hybridTransitionRiskWeight/);
  assert.match(source, /record_session: true/);
  assert.match(source, /Risk penalty/);
  assert.match(source, /Optional penalty for diagnostic transition risk/);
});

test("hybrid preview initializes and submits PR-21 feedback state", () => {
  assert.match(source, /setHybridSessionId\(response\.session_id \?\? null\);/);
  assert.match(source, /setHybridFeedbackDrafts\(hybridFeedbackDraftsFromResults\(response\.results\)\);/);
  assert.match(source, /api\.evaluationPairFeedback\(\{/);
  assert.match(source, /seed_track_ids: seeds/);
  assert.match(source, /source: hybridFeedbackSource/);
  assert.match(source, /Evaluation labels:/);
});

test("hybrid preview exposes CLAP as a stored audio source", () => {
  assert.match(source, /const hybridSourceKeys: HybridSearchSource\[\] = \["mert", "maest", "sonara", "clap"\];/);
  assert.match(source, /clap: true/);
  assert.match(source, /label: "CLAP"/);
  assert.match(source, /Uses stored CLAP audio embeddings only, without prompt input\./);
  assert.match(source, /stored MERT, MAEST, SONARA, and CLAP analysis data only/);
});

test("hybrid preview renders PR-22 why-this-track diagnostics", () => {
  assert.match(source, /function HybridWhyThisTrack/);
  assert.match(source, /Why this track\?/);
  assert.match(source, /Unsupervised diagnostic/);
  assert.match(source, /Adjusted score/);
  assert.match(source, /Risk estimate/);
  assert.match(source, /hybridAxisOrder/);
  assert.match(source, /hybrid-source-support/);
  assert.doesNotMatch(source, /confidence|probability|guaranteed|perfect transition/i);
});
