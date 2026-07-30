import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { mkdtempSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");
const panelSource = readFileSync(fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url)), "utf8");

async function loadSearchSurfaceState() {
  const sourcePath = new URL("../src/searchSurfaceState.ts", import.meta.url);
  const tempDir = mkdtempSync(join(tmpdir(), "search-layout-state-"));
  const modulePath = join(tempDir, "searchSurfaceState.cjs");
  const compiled = ts.transpileModule(readFileSync(sourcePath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  writeFileSync(modulePath, compiled, "utf8");
  return import(pathToFileURL(modulePath));
}

function cssRule(selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return styles.match(new RegExp(`${escapedSelector}\\s*{([\\s\\S]*?)}`))?.[1] || "";
}

function gridColumnCount(rule) {
  const value = rule.match(/grid-template-columns:\s*([^;]+);/)?.[1] || "";
  return value
    .replace(/minmax\([^)]*\)/g, "minmax")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .length;
}

test("desktop workspace keeps library track and search panels equal width", () => {
  const topbarRule = cssRule(".topbar");
  const workspaceRule = cssRule(".workspace");
  const resultsRule = cssRule(".search-workflow-section .results-list");
  const workflowRule = cssRule(".search-workflow-section");

  assert.match(topbarRule, /max-width:\s*1880px/);
  assert.match(workspaceRule, /max-width:\s*1880px/);
  assert.match(workspaceRule, /grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/);
  assert.doesNotMatch(workspaceRule, /1\.24fr/);
  assert.match(workflowRule, /min-width:\s*0/);
  assert.match(resultsRule, /min-height:\s*280px/);
  assert.match(resultsRule, /max-height:\s*min\(520px,\s*52vh\)/);
  assert.doesNotMatch(resultsRule, /max-height:\s*160px/);
});

test("set and export is a closed disclosure with 20-track pagination", () => {
  const disclosure = panelSource.match(
    /<details[\s\S]*?className="playlist-export-disclosure"[\s\S]*?<\/details>/
  )?.[0] || "";
  const openingTag = disclosure.match(/^<details[^>]*>/)?.[0] || "";
  const summary = disclosure.match(
    /<summary className="playlist-export-summary"[\s\S]*?<\/summary>/
  )?.[0] || "";
  const disclosureRule = cssRule(".playlist-export-disclosure");
  const listRule = cssRule(".playlist-export-section .playlist-list");
  const pageControlsRule = cssRule(".playlist-page-controls");

  assert.doesNotMatch(openingTag, /\sopen(?:=|\s|>)/);
  assert.match(panelSource, /const \[playlistExportOpen, setPlaylistExportOpen\] = useState\(false\)/);
  assert.match(panelSource, /const playlistPageSize = 20/);
  assert.match(openingTag, /onToggle=\{\(event\) =>/);
  assert.match(disclosure, /setPlaylistExportOpen\(event\.currentTarget\.open\)/);
  assert.match(summary, /Сет и экспорт/);
  assert.match(summary, /panel-counter">\{playlist\.length\}/);
  assert.ok(disclosure.indexOf("playlist-export-summary") < disclosure.indexOf("playlist-export-section"));
  assert.match(disclosure, /\{playlistExportOpen \? \(/);
  assert.match(disclosure, /playlistPageState\.items\.map\(\(track, index\)/);
  assert.match(disclosure, /playlistPageState\.pageStart\}–\{playlistPageState\.pageEnd\} из \{playlistPageState\.total\}/);
  assert.match(disclosure, /playlist-page-previous-button/);
  assert.match(disclosure, /playlist-page-next-button/);
  assert.doesNotMatch(panelSource, /playlistWindowStart|playlistVirtualHeight|playlist-list-virtualized/);
  assert.match(disclosureRule, /flex:\s*0 0 auto/);
  assert.match(disclosureRule, /margin-bottom:\s*2px/);
  assert.match(disclosureRule, /margin-top:\s*auto/);
  assert.match(listRule, /max-height:\s*min\(360px,\s*34vh\)/);
  assert.match(listRule, /overflow-y:\s*auto/);
  assert.match(listRule, /scrollbar-gutter:\s*stable/);
  assert.match(pageControlsRule, /display:\s*flex/);
  assert.match(styles, /\.playlist-export-summary-toggle::before\s*{[\s\S]*?content:\s*"Развернуть"/);
  assert.match(styles, /\.playlist-export-disclosure\[open\] \.playlist-export-summary-toggle::before\s*{[\s\S]*?content:\s*"Свернуть"/);
});

test("candidate result rows reserve stable columns for all icon actions", () => {
  const resultRowRule = cssRule(".result-row");
  const resultMeterRule = cssRule(".result-row meter");

  assert.equal(gridColumnCount(resultRowRule), 8);
  assert.match(resultRowRule, /minmax\(56px,\s*0\.46fr\)/);
  assert.match(resultRowRule, /minmax\(42px,\s*max-content\)/);
  assert.match(resultMeterRule, /width:\s*100%/);
});

test("primary search tabs expose all seven workflows with roving ARIA relationships", () => {
  assert.match(panelSource, /primarySearchTabs\.map/);
  assert.match(panelSource, /id=\{`search-tab-\$\{tab\}`\}/);
  assert.match(panelSource, /aria-controls=\{`search-panel-\$\{tab\}`\}/);
  assert.match(panelSource, /tabIndex=\{activeSearchTab === tab \? 0 : -1\}/);
  assert.match(panelSource, /onKeyDown=\{handlePrimaryTabKeyDown\}/);
  assert.match(panelSource, /muq: \{ label: "MUQ"/);
});

test("nested SET tabs are independently labelled and switching only updates tab state", () => {
  assert.match(panelSource, /role="tablist" aria-label="SET workflow"/);
  assert.match(panelSource, /id=\{`set-workflow-tab-\$\{tab\}`\}/);
  assert.match(panelSource, /aria-controls=\{`set-workflow-panel-\$\{tab\}`\}/);
  assert.match(panelSource, /id="set-workflow-panel-builder"[\s\S]*aria-labelledby="set-workflow-tab-builder"/);
  assert.match(panelSource, /id="set-workflow-panel-hybrid"[\s\S]*aria-labelledby="set-workflow-tab-hybrid"/);
  assert.match(panelSource, /onClick=\{\(\) => setActiveSetWorkflowTab\(tab\)\}/);
  assert.doesNotMatch(panelSource, /onClick=\{\(\) => \{[\s\S]*setActiveSetWorkflowTab\(tab\)[\s\S]*api\./);
});

test("SET seed source uses one select aligned with conditionally enabled Auto anchors", () => {
  const seedRowStart = panelSource.indexOf('className="set-builder-seed-row"');
  const seedRowEnd = panelSource.indexOf('className="search-filter-grid set-builder-grid set-builder-basic-grid"', seedRowStart);
  const seedRow = panelSource.slice(seedRowStart, seedRowEnd);
  const rowRule = cssRule(".set-builder-seed-row");
  const alignedControlsRule = cssRule(".set-builder-seed-source-control select,\n.set-builder-auto-anchors-control input");

  assert.match(seedRow, /className="set-builder-seed-mode-select"/);
  assert.match(seedRow, /value=\{setSeedMode\}/);
  assert.match(seedRow, /onChange=\{\(event\) => setSetSeedMode\(event\.target\.value as SetBuilderSeedMode\)\}/);
  assert.match(seedRow, /setSeedModeOptions\.map/);
  assert.doesNotMatch(seedRow, /set-builder-seed-mode-button|aria-pressed/);
  assert.match(panelSource, /const autoSeedCountDisabled = setSeedMode !== "auto"/);
  assert.match(seedRow, /disabled=\{autoSeedCountDisabled\}/);
  assert.match(rowRule, /grid-template-columns:\s*minmax\(0,\s*1\.15fr\)\s*minmax\(112px,\s*0\.85fr\)/);
  assert.match(alignedControlsRule, /min-height:\s*34px/);
  assert.match(alignedControlsRule, /width:\s*100%/);
  assert.match(
    styles,
    /@media \(max-width: 360px\)[\s\S]*?\.set-builder-seed-row\s*\{[\s\S]*?grid-template-columns:\s*1fr;/
  );
});

test("SET BPM trajectory controls stay visible outside the Advanced disclosure", () => {
  const bpmGridIndex = panelSource.indexOf('className="search-filter-grid set-builder-grid set-builder-bpm-grid"');
  const secondaryGridIndex = panelSource.indexOf('className="search-filter-grid set-builder-grid set-builder-secondary-grid"');
  const advancedHeaderIndex = panelSource.indexOf('className="set-builder-advanced-header"');
  const advancedControlsIndex = panelSource.indexOf('className="set-builder-advanced-controls"');
  const advancedActionsIndex = panelSource.indexOf('className="set-builder-actions"');
  const bpmGrid = panelSource.slice(bpmGridIndex, advancedHeaderIndex);
  const secondaryGrid = panelSource.slice(secondaryGridIndex, advancedHeaderIndex);
  const advancedControls = panelSource.slice(advancedControlsIndex, advancedActionsIndex);
  const bpmGridRule = cssRule(".search-workflow-section .set-builder-bpm-grid");

  assert.notEqual(bpmGridIndex, -1);
  assert.ok(bpmGridIndex < secondaryGridIndex);
  assert.ok(secondaryGridIndex < advancedHeaderIndex);
  assert.match(bpmGrid, />\s*BPM mode\s*</);
  assert.match(bpmGrid, />\s*BPM change\s*</);
  assert.match(bpmGrid, />\s*Start BPM\s*</);
  assert.match(bpmGrid, />\s*Target BPM\s*</);
  assert.match(secondaryGrid, />\s*Track limit\s*</);
  assert.match(secondaryGrid, />\s*Diversity\s*</);
  assert.match(bpmGridRule, /align-items:\s*end/);
  assert.match(bpmGridRule, /grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/);
  assert.doesNotMatch(advancedControls, />\s*(?:BPM mode|BPM change|Start BPM|Target BPM)\s*</);
  assert.match(advancedControls, />\s*Random seed\s*</);
});

test("SET source controls share the compact application checkbox and field treatment", () => {
  const hiddenCheckboxRule = cssRule('.set-check-toggle input[type="checkbox"]');
  const checkboxRule = cssRule(".set-control-checkbox");

  assert.match(panelSource, /set-check-toggle set-custom-weights-toggle/);
  assert.match(panelSource, /set-check-toggle hybrid-custom-weights-toggle/);
  assert.match(panelSource, /set-check-toggle set-source-toggle/);
  assert.match(panelSource, /set-check-toggle hybrid-source-toggle/);
  assert.ok((panelSource.match(/className="set-control-checkbox"/g) || []).length >= 6);
  assert.match(panelSource, /set-weight-control/);
  assert.match(panelSource, /hybrid-weight-control/);
  assert.match(hiddenCheckboxRule, /opacity:\s*0/);
  assert.match(hiddenCheckboxRule, /min-height:\s*0/);
  assert.match(hiddenCheckboxRule, /position:\s*absolute/);
  assert.match(checkboxRule, /height:\s*15px/);
  assert.match(checkboxRule, /width:\s*15px/);
  assert.match(styles, /\.set-custom-weights-toggle\.active,\s*\.hybrid-custom-weights-toggle\.active\s*\{/);
  assert.match(styles, /\.hybrid-source-row \.hybrid-source-toggle\.active\s*\{/);
});

test("SET classifier controls mirror CLASS availability and keep Flow compact", () => {
  const setClassifierStart = panelSource.indexOf("{orderedClassifierProfiles.length ? (");
  const setClassifierEnd = panelSource.indexOf('className="set-builder-reset-sliders-button"', setClassifierStart);
  const setClassifierBlock = panelSource.slice(setClassifierStart, setClassifierEnd);
  const classifierGridRule = cssRule(".set-classifier-grid");
  const flowRule = cssRule(".set-builder-controls .set-classifier-flow-control select");

  assert.match(setClassifierBlock, /orderedClassifierProfiles\.map\(\(classifier\)/);
  assert.match(setClassifierBlock, /classifierScoringBlockedReason\(classifier\)/);
  assert.match(setClassifierBlock, /if \(blockedReason\)/);
  assert.match(setClassifierBlock, /classifierProfileStatus\(classifier\)/);
  assert.match(setClassifierBlock, /className="classifier-profile unavailable"/);
  assert.match(setClassifierBlock, /classifier-profile-status-reason/);
  assert.match(setClassifierBlock, /classifier-profile available set-classifier-profile/);
  assert.match(setClassifierBlock, /available \{availableClassifierCount\} · blocked \{blockedClassifierCount\}/);
  assert.match(setClassifierBlock, /ready \{classifier\.ready \|\| 0\} · not ready \{classifier\.not_ready \|\| 0\}/);
  assert.match(setClassifierBlock, /className="set-classifier-flow-control"/);
  assert.match(panelSource, /filterAvailableClassifierValues\(\s*availableClassifierProfiles,\s*setClassifierPreferences/s);
  assert.match(panelSource, /compactSignedScoreMap\(availableSetClassifierPreferences\)/);
  assert.match(classifierGridRule, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s*minmax\(86px,\s*96px\)/);
  assert.match(flowRule, /min-height:\s*26px/);
  assert.match(flowRule, /font-size:\s*11px/);
});

test("Hybrid Preview uses the compact workbench sizing and neutral surface", () => {
  const panelRule = cssRule(".hybrid-preview-panel");
  const sourceGridRule = cssRule(".hybrid-source-grid");
  const sourceRowRule = cssRule(".hybrid-source-row");
  const previewGridRule = cssRule(".search-workflow-section .hybrid-preview-grid");
  const previewButtonRule = cssRule(".hybrid-preview-panel .hybrid-preview-button");

  assert.match(panelRule, /background:\s*var\(--surface\)/);
  assert.match(panelRule, /border:\s*1px solid var\(--border-soft\)/);
  assert.match(panelRule, /gap:\s*6px/);
  assert.match(panelRule, /padding:\s*7px/);
  assert.doesNotMatch(panelRule, /gradient|box-shadow/);
  assert.match(sourceGridRule, /minmax\(86px,\s*1fr\)/);
  assert.match(sourceRowRule, /grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(sourceRowRule, /padding:\s*4px/);
  assert.match(previewGridRule, /repeat\(3,\s*minmax\(0,\s*1fr\)\)/);
  assert.match(styles, /\.hybrid-custom-weights-toggle\s*\{[^}]*min-height:\s*28px/s);
  assert.match(previewButtonRule, /min-height:\s*32px/);
  assert.match(previewButtonRule, /margin-bottom:\s*0/);
});

test("responsive layout keeps SET sources stacked and reserves Hybrid pairs for phones", () => {
  assert.match(
    styles,
    /@media \(max-width: 720px\)[\s\S]*?\.set-source-grid\s*\{[\s\S]*?grid-template-columns:\s*1fr;/
  );
  assert.match(
    styles,
    /@media \(max-width: 480px\)[\s\S]*?\.hybrid-source-grid,\s*\.search-workflow-section \.set-builder-bpm-grid,\s*\.search-workflow-section \.hybrid-preview-grid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\);/
  );
});

test("Left Right Home End navigation wraps for both tablists", async () => {
  const { primarySearchTabs, setWorkflowTabs, tabAfterKey } = await loadSearchSurfaceState();

  assert.deepEqual(primarySearchTabs, ["set", "lab", "sonara", "mert", "muq", "clap", "class"]);
  assert.equal(tabAfterKey(primarySearchTabs, "set", "ArrowLeft"), "class");
  assert.equal(tabAfterKey(primarySearchTabs, "set", "ArrowRight"), "lab");
  assert.equal(tabAfterKey(primarySearchTabs, "lab", "ArrowRight"), "sonara");
  assert.equal(tabAfterKey(primarySearchTabs, "muq", "Home"), "set");
  assert.equal(tabAfterKey(primarySearchTabs, "muq", "End"), "class");
  assert.equal(tabAfterKey(setWorkflowTabs, "builder", "ArrowRight"), "hybrid");
  assert.equal(tabAfterKey(setWorkflowTabs, "hybrid", "ArrowRight"), "builder");
  assert.equal(tabAfterKey(setWorkflowTabs, "hybrid", "Enter"), null);
});
