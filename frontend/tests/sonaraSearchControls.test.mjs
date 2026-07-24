import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const panelSource = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");
const embeddingTabSource = readFileSync(new URL("../src/EmbeddingSearchTab.tsx", import.meta.url), "utf8");
const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

test("SONARA tab exposes backend modes and custom vocalness modifier", () => {
  assert.match(panelSource, /sonaraModeOptions/);
  assert.match(panelSource, /value=\{filters\.sonaraMode\}/);
  assert.match(panelSource, /key: "vocalness", label: "Vocal"/);
  assert.match(panelSource, /handleSonaraSearch/);
});

test("SONARA mode, similarity, and limit share one compact styled row", () => {
  assert.match(panelSource, /className="search-filter-grid sonara-search-filter-grid"/);
  assert.match(panelSource, /className="sonara-mode-select"/);
  assert.match(
    stylesSource,
    /\.search-workflow-section \.sonara-search-filter-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.4fr\)\s*repeat\(2,\s*minmax\(0,\s*0\.8fr\)\)/s,
  );
  assert.match(stylesSource, /\.sonara-mode-select\s*\{[^}]*appearance:\s*none/s);
  assert.match(stylesSource, /\.sonara-mode-select\s*\{[^}]*background-color:\s*var\(--surface-muted\)/s);
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

test("MUQ remains visible at zero coverage and shows a non-blocking current-contract reason", () => {
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
