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

test("candidate result rows reserve stable columns for all icon actions", () => {
  const resultRowRule = cssRule(".result-row");
  const resultMeterRule = cssRule(".result-row meter");

  assert.equal(gridColumnCount(resultRowRule), 8);
  assert.match(resultRowRule, /minmax\(56px,\s*0\.46fr\)/);
  assert.match(resultRowRule, /minmax\(42px,\s*max-content\)/);
  assert.match(resultMeterRule, /width:\s*100%/);
});

test("primary search tabs expose all seven v7 workflows with roving ARIA relationships", () => {
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

test("narrow layout stacks SET and Hybrid source controls into one column", () => {
  assert.match(
    styles,
    /@media \(max-width: 720px\)[\s\S]*?\.set-source-grid,\s*\.hybrid-source-grid\s*\{[\s\S]*?grid-template-columns:\s*1fr;/
  );
});

test("Left Right Home End navigation wraps for both tablists", async () => {
  const { primarySearchTabs, setWorkflowTabs, tabAfterKey } = await loadSearchSurfaceState();

  assert.deepEqual(primarySearchTabs, ["set", "sonara", "mert", "muq", "clap", "class", "lab"]);
  assert.equal(tabAfterKey(primarySearchTabs, "set", "ArrowLeft"), "lab");
  assert.equal(tabAfterKey(primarySearchTabs, "lab", "ArrowRight"), "set");
  assert.equal(tabAfterKey(primarySearchTabs, "muq", "Home"), "set");
  assert.equal(tabAfterKey(primarySearchTabs, "muq", "End"), "lab");
  assert.equal(tabAfterKey(setWorkflowTabs, "builder", "ArrowRight"), "hybrid");
  assert.equal(tabAfterKey(setWorkflowTabs, "hybrid", "ArrowRight"), "builder");
  assert.equal(tabAfterKey(setWorkflowTabs, "hybrid", "Enter"), null);
});
