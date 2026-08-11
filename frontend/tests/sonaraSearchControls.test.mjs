import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const panelSource = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");
const embeddingTabSource = readFileSync(new URL("../src/EmbeddingSearchTab.tsx", import.meta.url), "utf8");
const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

test("SONARA tab exposes backend modes and custom vocalness and aggression modifiers", () => {
  assert.match(panelSource, /sonaraModeOptions/);
  assert.match(panelSource, /value=\{filters\.sonaraMode\}/);
  assert.match(panelSource, /key: "vocalness", label: "Vocal"/);
  assert.match(panelSource, /key: "aggression", label: "Aggression"/);
  assert.match(panelSource, /handleSonaraSearch/);
  assert.match(panelSource, /title=\{helpText\.sonaraMode\}/);
  assert.match(panelSource, /Balanced: универсальный поиск/);
  assert.match(panelSource, /DJ transition: ищет следующий трек для сета/);
});

test("SONARA modifiers put practical musical directions first and LUFS last", () => {
  const order = ["energy", "valence", "aggression", "vocalness", "acousticness", "brightness", "rhythm_density", "dynamic_range", "loudness"];
  const positions = order.map((key) => panelSource.indexOf(`key: "${key}"`));
  assert.ok(positions.every((position) => position >= 0));
  assert.deepEqual([...positions].sort((left, right) => left - right), positions);
});

test("zero-valued SONARA custom controls visibly show that they are off", () => {
  assert.match(panelSource, /const isOff = value === 0;/);
  assert.match(panelSource, /className=\{isOff \? "range-control is-off" : "range-control"\}/);
  assert.match(panelSource, /className="sonara-control-off">Off<\/small>/);
  assert.match(stylesSource, /\.sonara-custom-controls \.range-control\.is-off\s*\{[^}]*opacity:\s*0\.6/s);
  assert.match(stylesSource, /\.sonara-control-off\s*\{/);
});

test("each SONARA modifier has an independent score and an off button that resets it to zero", () => {
  assert.match(panelSource, /className="sonara-modifier-score">\{formatSigned\(value\)\}<\/em>/);
  assert.match(panelSource, /aria-label=\{`Reset \$\{control\.label\} modifier to zero`\}/);
  assert.match(panelSource, /disabled=\{isOff \|\| customSonaraDisabled\}/);
  assert.match(panelSource, /onClick=\{\(\) => setSonaraModifierValue\(control\.key, 0\)\}/);
  assert.match(stylesSource, /\.sonara-modifier-grid \.range-control span\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) auto auto/s);
  assert.match(stylesSource, /\.sonara-control-off\s*\{[^}]*min-height:\s*0/s);
  assert.match(stylesSource, /\.sonara-control-off:disabled\s*\{[^}]*opacity:\s*1/s);
});

test("SONARA modifiers use a softer distinct accent", () => {
  assert.match(panelSource, /className="range-grid modifier-grid sonara-modifier-grid"/);
  assert.match(panelSource, /className="sonara-modifier-range"/);
  assert.match(stylesSource, /--modifier-accent:\s*#8b5ca7;/);
  assert.match(stylesSource, /--modifier-accent:\s*#c4b5fd;/);
  assert.match(stylesSource, /\.sonara-modifier-range\s*\{[^}]*accent-color:\s*var\(--modifier-accent\)/s);
});

test("SONARA mixer and modifiers have short guidance and separated sections", () => {
  assert.match(panelSource, /<small>— приоритизирует виды сходства\.<\/small>/);
  assert.match(panelSource, /<small>— направляют характер выдачи\.<\/small>/);
  assert.match(panelSource, /className="custom-control-header sonara-modifier-header"/);
  assert.match(stylesSource, /\.custom-control-copy\s*\{[^}]*align-items:\s*baseline[^}]*display:\s*flex/s);
  assert.match(stylesSource, /\.sonara-modifier-header\s*\{[^}]*margin-top:\s*6px/s);
});

test("SONARA mode and limit share one compact styled row", () => {
  assert.match(panelSource, /className="search-filter-grid sonara-search-filter-grid"/);
  assert.match(panelSource, /className="sonara-mode-select"/);
  assert.match(
    stylesSource,
    /\.search-workflow-section \.sonara-search-filter-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.4fr\)\s*minmax\(0,\s*0\.8fr\)/s,
  );
  assert.match(stylesSource, /\.sonara-mode-select\s*\{[^}]*appearance:\s*none/s);
  assert.match(stylesSource, /\.sonara-mode-select\s*\{[^}]*background-color:\s*var\(--accent-strong-bg\)/s);
  assert.match(stylesSource, /\.sonara-mode-select\s*\{[^}]*border-color:\s*var\(--accent-border\)/s);
  assert.match(stylesSource, /\.sonara-mode-select\s*\{[^}]*box-shadow:\s*none/s);
  assert.match(stylesSource, /\.sonara-mode-select\s*\{[^}]*color:\s*var\(--accent-active-text\)/s);
  assert.match(stylesSource, /\.sonara-mode-select:hover:not\(:disabled\)/);
  assert.match(stylesSource, /\.sonara-mode-select:focus-visible/);
});

test("MERT and MUQ use one typed generic embedding search component and handler", () => {
  assert.match(panelSource, /activeSearchTab === "mert" \|\| activeSearchTab === "muq"/);
  assert.match(panelSource, /<EmbeddingSearchTab/);
  assert.match(panelSource, /analysisFamily=\{activeSearchTab\}/);
  assert.match(panelSource, /handleEmbeddingSearch: \(analysisFamily: EmbeddingSource\) => Promise<void>/);
  assert.match(panelSource, /await handleEmbeddingSearch\(analysisFamily\)/);
  assert.doesNotMatch(panelSource, /handleMertSearch/);
});

test("MUQ remains visible at zero coverage and shows a non-blocking current-data reason", () => {
  assert.match(panelSource, /muq: \{ label: "MUQ"/);
  assert.match(panelSource, /currentEmbeddingCount=\{embeddingCounts\[activeSearchTab\]\}/);
  assert.match(embeddingTabSource, /No current \$\{label\} embeddings are available in the selected catalog/);
  assert.match(embeddingTabSource, /disabled=\{busy \|\| pending \|\| Boolean\(missingReason\)\}/);
  assert.match(embeddingTabSource, /\{error \? <span className="embedding-search-requirement error">\{error\}<\/span> : null\}/);
});

test("embedding search keeps a bounded result limit without a similarity threshold", () => {
  assert.match(embeddingTabSource, /Number\.isFinite\(event\.currentTarget\.valueAsNumber\)/);
  assert.match(embeddingTabSource, /Math\.round\(Math\.max\(1, Math\.min\(500,/);
  assert.doesNotMatch(embeddingTabSource, /minSimilarity|similarityHelp|onMinSimilarityChange/);
  assert.doesNotMatch(embeddingTabSource, /Number\(event\.target\.value\)/);
});
