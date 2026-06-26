import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const source = readFileSync(fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url)), "utf8");
const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");

function cssRule(selector) {
  return styles.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{[^}]*\\}`))?.[0] || "";
}

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

test("hybrid preview keeps diagnostics in a separate selected-result panel", () => {
  assert.match(source, /function HybridResultDetails/);
  assert.match(source, /const \[hybridSelectedResultId, setHybridSelectedResultId\] = useState<number \| null>\(null\);/);
  assert.match(source, /const selectedHybridResult = showHybridResults/);
  assert.match(source, /selected=\{selectedHybridResult\?\.track\.id === result\.track\.id\}/);
  assert.match(source, /onSelect=\{\(\) => setHybridSelectedResultId\(result\.track\.id\)\}/);
  assert.match(source, /selectTitle=\{`Show Hybrid diagnostics for \$\{displayTrack\(result\.track\)\}`\}/);
  assert.match(source, /\{selectedHybridResult \? \(\s*<HybridResultDetails/);
  assert.match(source, /className="hybrid-result-details"/);
  assert.match(source, /className="hybrid-result-summary-content"/);
  assert.match(source, /<HybridFeedbackControls/);
  assert.doesNotMatch(source, /rowSlot=\{[\s\S]*<HybridResultDetails/);
  assert.doesNotMatch(source, /hybridExpandedRows|toggleHybridResultDetails|<details|<summary/);
});

test("hybrid preview layout wraps controls and hardens overflow", () => {
  const selectedRowRule = cssRule(".result-row.selected");
  const selectableRowRule = cssRule(".result-row.selectable");

  assert.match(selectableRowRule, /cursor:\s*pointer;/);
  assert.match(selectedRowRule, /border-color:\s*var\(--accent-soft-border\);/);
  assert.match(styles, /\.hybrid-preview-panel\s*\{[\s\S]*min-width:\s*0;[\s\S]*overflow:\s*hidden;/);
  assert.match(styles, /\.hybrid-source-grid\s*\{[\s\S]*display:\s*flex;[\s\S]*flex-wrap:\s*wrap;/);
  assert.match(styles, /\.hybrid-classifier-toggle-grid\s*\{[\s\S]*display:\s*flex;[\s\S]*flex-wrap:\s*wrap;/);
  assert.match(styles, /\.hybrid-result-details\s*\{[\s\S]*display:\s*grid;[\s\S]*min-width:\s*0;[\s\S]*overflow-wrap:\s*anywhere;/);
  assert.match(styles, /\.hybrid-result-summary-content\s*\{[\s\S]*display:\s*inline-flex;[\s\S]*flex-wrap:\s*wrap;/);
  assert.doesNotMatch(styles, /minmax\(320px,\s*1\.35fr\)/);
});
