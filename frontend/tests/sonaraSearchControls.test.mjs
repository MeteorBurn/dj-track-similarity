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
});

test("zero-valued SONARA custom controls visibly show that they are off", () => {
  assert.match(panelSource, /const isOff = value === 0;/);
  assert.match(panelSource, /className=\{isOff \? "range-control is-off" : "range-control"\}/);
  assert.match(panelSource, /className="sonara-control-off">Off<\/small>/);
  assert.match(stylesSource, /\.sonara-custom-controls \.range-control\.is-off\s*\{[^}]*opacity:\s*0\.6/s);
  assert.match(stylesSource, /\.sonara-control-off\s*\{/);
});

test("SONARA modifiers use a softer distinct accent", () => {
  assert.match(panelSource, /className="range-grid modifier-grid sonara-modifier-grid"/);
  assert.match(panelSource, /className="sonara-modifier-range"/);
  assert.match(stylesSource, /--modifier-accent:\s*#8b5ca7;/);
  assert.match(stylesSource, /--modifier-accent:\s*#c4b5fd;/);
  assert.match(stylesSource, /\.sonara-modifier-range\s*\{[^}]*accent-color:\s*var\(--modifier-accent\)/s);
});

test("SONARA mode, similarity, and limit share one compact styled row", () => {
  assert.match(panelSource, /className="search-filter-grid sonara-search-filter-grid"/);
  assert.match(panelSource, /className="sonara-mode-select"/);
  assert.match(
    stylesSource,
    /\.search-workflow-section \.sonara-search-filter-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.4fr\)\s*repeat\(2,\s*minmax\(0,\s*0\.8fr\)\)/s,
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

test("embedding search controls clamp finite values without turning empty input into zero", () => {
  assert.match(embeddingTabSource, /Number\.isFinite\(event\.currentTarget\.valueAsNumber\)/);
  assert.match(embeddingTabSource, /Math\.max\(0, Math\.min\(1,/);
  assert.match(embeddingTabSource, /Math\.round\(Math\.max\(1, Math\.min\(500,/);
  assert.doesNotMatch(embeddingTabSource, /Number\(event\.target\.value\)/);
});
