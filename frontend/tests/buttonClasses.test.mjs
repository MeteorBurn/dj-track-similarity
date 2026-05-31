import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));
const styleTokens = new Set([
  "active",
  "icon-button",
  "intent-add",
  "intent-remove",
  "primary",
  "secondary-mini"
]);

function sourceFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return entry.isFile() && /\.(tsx|jsx)$/.test(entry.name) ? [path] : [];
  });
}

function buttonTags(source) {
  return source.match(/<button\b[\s\S]*?>/g) || [];
}

function classNameValue(tag) {
  const start = tag.indexOf("className=");
  if (start === -1) return "";
  const valueStart = start + "className=".length;
  const opener = tag[valueStart];
  if (opener === '"' || opener === "'") {
    const end = tag.indexOf(opener, valueStart + 1);
    return tag.slice(valueStart + 1, end);
  }
  if (opener !== "{") return "";
  let depth = 0;
  for (let index = valueStart; index < tag.length; index += 1) {
    if (tag[index] === "{") depth += 1;
    if (tag[index] === "}") {
      depth -= 1;
      if (depth === 0) return tag.slice(valueStart + 1, index);
    }
  }
  return "";
}

function semanticClassTokens(value) {
  return (value.match(/[A-Za-z][A-Za-z0-9_-]*/g) || [])
    .filter((token) => !styleTokens.has(token))
    .filter((token) => /(?:button|tab|chip)$/.test(token));
}

test("every button has a semantic class name", () => {
  const failures = [];
  for (const file of sourceFiles(srcDir)) {
    const source = readFileSync(file, "utf8");
    if (!statSync(file).isFile()) continue;
    for (const tag of buttonTags(source)) {
      const className = classNameValue(tag);
      const semantics = semanticClassTokens(className);
      if (!className || semantics.length === 0) {
        failures.push(`${file}: ${tag.replace(/\s+/g, " ")}`);
      }
    }
  }
  assert.deepEqual(failures, []);
});

test("every button exposes tooltip text", () => {
  const failures = [];
  for (const file of sourceFiles(srcDir)) {
    const source = readFileSync(file, "utf8");
    if (!statSync(file).isFile()) continue;
    for (const tag of buttonTags(source)) {
      if (!/\btitle=/.test(tag)) {
        failures.push(`${file}: ${tag.replace(/\s+/g, " ")}`);
      }
    }
  }
  assert.deepEqual(failures, []);
});

test("button tooltip text uses compact viewport-level styling", () => {
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const rule = styles.match(/\.ui-tooltip\s*{([\s\S]*?)}/)?.[1] || "";

  assert.doesNotMatch(styles, /\.app-shell\s+\[title\][^{]*::after/);
  assert.match(rule, /position:\s*fixed/);
  assert.match(rule, /font-size:\s*12px/);
  assert.match(rule, /line-height:\s*1\.25/);
  assert.match(rule, /max-width:\s*min\(260px,\s*calc\(100vw - 16px\)\)/);
  assert.match(rule, /overflow-wrap:\s*anywhere/);
});

test("genre save button is placed between refresh tags and database clear", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");

  const refreshIndex = source.indexOf("refresh-tags-button");
  const genreSaveIndex = source.indexOf("genre-save-button");
  const clearIndex = source.indexOf("database-clear-button");

  assert.notEqual(refreshIndex, -1);
  assert.notEqual(genreSaveIndex, -1);
  assert.notEqual(clearIndex, -1);
  assert.ok(refreshIndex < genreSaveIndex);
  assert.ok(genreSaveIndex < clearIndex);
});

test("scan action row reserves one line for all scan controls", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const rowMatch = source.match(/<div className="scan-action-row">([\s\S]*?)<\/div>/);
  const styleMatch = styles.match(/\.scan-action-row\s*{([\s\S]*?)}/);

  assert.ok(rowMatch, "scan action row markup exists");
  assert.ok(styleMatch, "scan action row styles exist");

  const controlCount = (rowMatch[1].match(/<button\b/g) || []).length;
  const declaredIconColumns = Number(styleMatch[1].match(/repeat\((\d+),\s*42px\)/)?.[1] || 0);

  assert.equal(controlCount, 4);
  assert.equal(declaredIconColumns, controlCount - 1);
});

test("analysis controls use model checkboxes and one selected-run button", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");

  assert.match(source, /analysis-model-checkbox/);
  assert.match(source, /analysis-model-name/);
  assert.match(source, /analysis-model-check/);
  assert.match(source, /analyze-selected-button/);
  assert.match(source, />\s*Analyze\s*<\/button>/);
  assert.doesNotMatch(source, /Analyze selected/);
  assert.match(source, /selectedAnalysisModels/);
  assert.doesNotMatch(source, /onSonaraAnalyze/);
  assert.doesNotMatch(source, /onGenreAnalyze/);
  assert.doesNotMatch(source, /onAnalyze: \(adapter/);

  const modelNameIndex = source.indexOf("analysis-model-name");
  const modelCheckboxIndex = source.indexOf("analysis-model-checkbox");
  const resetButtonIndex = source.indexOf("analysis-reset-button");
  const batchSizeIndex = source.indexOf("Embedding batch size");
  const analyzeSelectedIndex = source.indexOf("analyze-selected-button");

  assert.ok(modelNameIndex < modelCheckboxIndex);
  assert.ok(modelCheckboxIndex < resetButtonIndex);
  assert.ok(batchSizeIndex < analyzeSelectedIndex);
});

test("analysis model reset buttons fit inside a full-width row", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const actionsRule = styles.match(/\.analysis-actions\s*{([\s\S]*?)}/)?.[1] || "";
  const rowRule = styles.match(/\.analysis-model-row\s*{([\s\S]*?)}/)?.[1] || "";
  const resetRule = styles.match(/\.analysis-reset-button\s*{([\s\S]*?)}/)?.[1] || "";

  assert.doesNotMatch(source, /icon-button\s+analysis-reset-button/);
  assert.match(actionsRule, /align-self:\s*stretch/);
  assert.match(actionsRule, /width:\s*100%/);
  assert.match(rowRule, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s+36px\s+minmax\(96px,\s*max-content\)/);
  assert.match(rowRule, /width:\s*100%/);
  assert.doesNotMatch(rowRule, /82px/);
  assert.match(resetRule, /display:\s*inline-flex/);
  assert.match(resetRule, /min-width:\s*96px/);
  assert.match(resetRule, /white-space:\s*nowrap/);
});

test("frontend analysis api uses unified job endpoints only", () => {
  const source = readFileSync(join(srcDir, "api.ts"), "utf8");

  assert.match(source, /\/api\/analysis\/jobs/);
  assert.doesNotMatch(source, /\/api\/sonara\/analyze/);
  assert.doesNotMatch(source, /\/api\/genres\/analyze/);
  assert.doesNotMatch(source, /\/api\/analyze"/);
});

test("analysis process status renders per-model progress", () => {
  const source = readFileSync(join(srcDir, "jobUi.tsx"), "utf8");

  assert.match(source, /model_progress/);
  assert.match(source, /analysis-model-progress/);
  assert.doesNotMatch(source, /api\.sonaraJob/);
  assert.doesNotMatch(source, /api\.genreJob/);
});

test("destructive actions use the in-app confirmation dialog", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");

  assert.doesNotMatch(appSource, /window\.confirm/);
  assert.match(appSource, /ConfirmationDialog/);
  assert.match(appSource, />Да</);
  assert.match(appSource, />Нет</);
});

test("non-destructive sonara mixer reset does not request confirmation", () => {
  const source = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const resetBody = source.match(/function resetCustomSonara\(\) \{([\s\S]*?)\n  \}/)?.[1] || "";

  assert.match(source, /sonara-mixer-reset-button/);
  assert.match(resetBody, /setFilters/);
  assert.doesNotMatch(resetBody, /onConfirmAction|ConfirmationRequest/);
});

test("documentation title click opens the docs in a separate window", () => {
  const source = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const headerLink = source.match(/<a\b[\s\S]*?>\s*DJ Track Similarity\s*<\/a>/)?.[0] || "";

  assert.match(source, /function openDocumentationWindow/);
  assert.match(source, /window\.open\("\/docs\/", "_blank", "noopener,noreferrer"\)/);
  assert.match(headerLink, /target="_blank"/);
  assert.match(headerLink, /onClick=\{openDocumentationWindow\}/);
});

test("library controls keep pagination left and actions pinned right", () => {
  const source = readFileSync(join(srcDir, "TrackPanel.tsx"), "utf8");
  const titleActions = source.match(/<div className="panel-title-actions track-panel-actions">([\s\S]*?)<\/div>/)?.[1] || "";
  const controls = source.match(/<div className="library-view-controls">([\s\S]*?)<\/div>/)?.[1] || "";

  const rangeIndex = controls.indexOf("library-range-status");
  const sortIndex = controls.indexOf("library-sort-direction-button");
  const addIndex = controls.indexOf("add-visible-tracks-button");
  const prevIndex = controls.indexOf("library-page-previous-button");
  const nextIndex = controls.indexOf("library-page-next-button");
  const inputIndex = controls.indexOf("library-page-index-input");
  const statusIndex = controls.indexOf("library-page-number-status");

  assert.equal(titleActions.indexOf("library-range-status"), -1);
  assert.equal(titleActions.indexOf("library-sort-direction-button"), -1);
  assert.equal(titleActions.indexOf("add-visible-tracks-button"), -1);
  assert.notEqual(rangeIndex, -1);
  assert.notEqual(sortIndex, -1);
  assert.notEqual(addIndex, -1);
  assert.notEqual(prevIndex, -1);
  assert.notEqual(nextIndex, -1);
  assert.notEqual(inputIndex, -1);
  assert.notEqual(statusIndex, -1);
  assert.ok(prevIndex < nextIndex);
  assert.ok(nextIndex < inputIndex);
  assert.ok(inputIndex < statusIndex);
  assert.ok(statusIndex < rangeIndex);
  assert.ok(rangeIndex < sortIndex);
  assert.ok(sortIndex < addIndex);
});

test("library range status shows only filtered total in the controls row", () => {
  const source = readFileSync(join(srcDir, "TrackPanel.tsx"), "utf8");
  const titleActions = source.match(/<div className="panel-title-actions track-panel-actions">([\s\S]*?)<\/div>/)?.[1] || "";
  const controls = source.match(/<div className="library-view-controls">([\s\S]*?)<\/div>/)?.[1] || "";
  const status = source.match(/<span className="library-range-status"[^>]*>([\s\S]*?)<\/span>/)?.[1] || "";

  assert.equal(titleActions.indexOf("library-range-status"), -1);
  assert.notEqual(controls.indexOf("library-range-status"), -1);
  assert.match(status, /\$\{total\}/);
  assert.doesNotMatch(status, /pageStart|pageEnd|-/);
});

test("library controls share button height and text-only counters", () => {
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const controlsRule = styles.match(/\.library-view-controls\s*{([\s\S]*?)}/)?.[1] || "";
  const controlRule = styles.match(/\.library-view-controls \.secondary-mini\s*{([\s\S]*?)}/)?.[1] || "";
  const inputRule = styles.match(/\.library-page-index-input\s*{([\s\S]*?)}/)?.[1] || "";
  const pageRule = styles.match(/\.library-page-number-status\s*{([\s\S]*?)}/)?.[1] || "";
  const rangeRule = styles.match(/\.library-range-status\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(controlsRule, /gap:\s*6px/);
  assert.match(controlRule, /height:\s*34px/);
  assert.match(inputRule, /align-self:\s*start/);
  assert.match(inputRule, /height:\s*34px/);
  assert.match(pageRule, /align-self:\s*start/);
  assert.match(pageRule, /height:\s*34px/);
  assert.match(rangeRule, /margin-left:\s*auto/);
  assert.match(rangeRule, /height:\s*34px/);
  assert.match(rangeRule, /color:\s*#4c5747/);
  assert.doesNotMatch(pageRule, /min-width:\s*52px/);
  assert.doesNotMatch(rangeRule, /border:/);
  assert.doesNotMatch(rangeRule, /font-weight:/);
  assert.doesNotMatch(rangeRule, /font-size:/);
});
