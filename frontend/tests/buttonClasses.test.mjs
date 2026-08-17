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
  "intent-remove"
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

test("server shutdown button uses the destructive intent color", () => {
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const shutdownRule = styles.match(/\.server-shutdown-button\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(shutdownRule, /background:\s*var\(--danger-bg\)/);
  assert.match(shutdownRule, /border-color:\s*var\(--danger-border\)/);
  assert.match(shutdownRule, /color:\s*var\(--danger-text\)/);
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

test("scan action keeps the import trigger beside database maintenance controls", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const rowMatch = source.match(/<div className="scan-action-row">([\s\S]*?)<\/div>/);
  const styleMatch = styles.match(/\.scan-action-row\s*{([\s\S]*?)}/);
  const primaryButtonMatch = styles.match(/\.scan-action-row \.scan-start-button\s*{([\s\S]*?)}/);
  const iconButtonMatch = styles.match(/\.scan-action-row \.icon-button\s*{([\s\S]*?)}/);

  assert.ok(rowMatch, "scan action row markup exists");
  assert.ok(styleMatch, "scan action row styles exist");
  assert.ok(primaryButtonMatch, "scan primary button styles exist");
  assert.ok(iconButtonMatch, "scan icon button styles exist");

  const controlCount = (rowMatch[1].match(/<button\b/g) || []).length;

  assert.equal(controlCount, 5);
  assert.match(styleMatch[1], /display:\s*flex/);
  assert.match(styleMatch[1], /gap:\s*6px/);
  assert.match(primaryButtonMatch[1], /flex:\s*1/);
  assert.match(iconButtonMatch[1], /flex:\s*0 0 34px/);
});

test("analysis controls expose one checkbox-driven Analyze action", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const selectionSource = readFileSync(join(srcDir, "analysisSelection.ts"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");

  assert.match(source, /analysis-model-checkbox/);
  assert.match(source, /analysis-model-name/);
  assert.match(source, /analysis-model-title/);
  assert.match(source, /analysis-model-description/);
  assert.match(source, /analysis-model-count/);
  assert.match(source, /analysis-model-check/);
  assert.match(source, /analyze-selected-button/);
  assert.match(source, />\s*Analyze\s*<\/button>/);
  assert.match(source, /Считает темп, тональность, ритм, динамику, тембр и структуру трека/);
  assert.match(source, /Помогает понять жанровый характер трека/);
  assert.match(source, /Ищет похожее звучание от выбранного seed-трека/);
  assert.match(source, /Связывает текстовое описание с аудио-звучанием/);
  assert.match(source, /maximum=\{16\}/);
  assert.match(source, /value >= maximum/);
  assert.match(source, /className="worker-control analysis-limit"/);
  assert.match(source, /analysis-limit-decrement-button/);
  assert.match(source, /analysis-limit-increment-button/);
  assert.match(source, /analysisLimit >= 100000/);
  assert.doesNotMatch(source, /FFmpeg decode/);
  assert.doesNotMatch(source, /Отдельный анализ по локальным профилям/);
  assert.doesNotMatch(source, /classifiers-analysis-card|CLASSIFIERS selected|availableClassifierProfiles/);
  assert.doesNotMatch(source, /readyClassifiers|notReadyClassifiers|blockerCount/);
  assert.doesNotMatch(source, /visibleClassifierBlockers|className="analysis-muted" key=\{item\.key\}/);
  assert.match(source, /selectedAnalysisModels/);
  assert.doesNotMatch(source, /Run SONARA|Run ML|Run CLASSIFIERS|Run selected pipeline/);
  assert.doesNotMatch(source, /onAnalyzeSonara|onAnalyzeMl|onAnalyzeClassifiers/);
  assert.match(selectionSource, /defaultAnalysisSelections: AnalysisSelection\[\] = \["sonara"\]/);
  assert.match(appSource, /if \(current\.length === 1 && current\.includes\(model\)\) return current/);
  assert.match(appSource, /if \(model === "sonara"\) \{[\s\S]*?return \[model\]/);
  assert.match(appSource, /current\.filter\(\(item\) => item !== "sonara"\)/);
  assert.doesNotMatch(appSource, /SonaraOutput|sonaraOutputs|toggleSonaraOutput/);
  assert.doesNotMatch(source, /sonara-output|Timeline|Fingerprint/);
  assert.doesNotMatch(styles, /\.sonara-output-/);
  assert.match(styles, /\.analysis-model-count\s*{[\s\S]*?align-self:\s*center[\s\S]*?height:\s*34px[\s\S]*?min-height:\s*34px/);
  assert.doesNotMatch(source, /Active SONARA release|Prepare release|sonaraAnalysisBlockedReason/);
  assert.match(appSource, /const childJobId = currentStage \? job\.stages\[currentStage\]\?\.child_job_id : null/);
  assert.doesNotMatch(appSource, /aggregateClassifierJob|currentStage === "classifiers"/);
  assert.match(appSource, /SONARA · Direct · BatchSize \$\{sonaraSettings\.directBatchSize\}/);
  assert.match(appSource, /SONARA · Staged · \$\{sonaraSettings\.staged\.folder\}/);
  assert.match(appSource, /Track batch \$\{analysisTrackBatchSize\} · Inference batch \$\{analysisInferenceBatchSize\}/);
  assert.doesNotMatch(appSource, /CLASSIFIERS · profiles|classifierKeys/);

  const modelRowBlock = source.match(/<div className="analysis-model-row"[\s\S]*?<\/div>/)?.[0] || "";
  const modelCheckIndex = modelRowBlock.indexOf("analysis-model-check");
  const modelNameIndex = modelRowBlock.indexOf("analysis-model-name");
  const modelTitleIndex = modelRowBlock.indexOf("analysis-model-title");
  const modelDescriptionIndex = modelRowBlock.indexOf("analysis-model-description");
  const modelCountIndex = modelRowBlock.indexOf("analysis-model-count");
  const resetButtonIndex = modelRowBlock.indexOf("analysis-reset-button");
  const batchSizeIndex = source.indexOf("Inference batch");
  const analyzeSelectedIndex = source.indexOf("analyze-selected-button");
  const sonaraRowIndex = source.indexOf('{modelRow("sonara")}');
  const sonaraModeIndex = source.indexOf("sonara-analysis-mode");
  const sonaraBatchIndex = source.indexOf('label="BatchSize"');
  const mlRowsIndex = source.indexOf("mlAnalysisModelOrder.map(modelRow)");
  const mlSettingsIndex = source.indexOf('className="analysis-settings-grid ml-analysis-settings"');

  assert.notEqual(modelCheckIndex, -1);
  assert.notEqual(modelNameIndex, -1);
  assert.notEqual(modelTitleIndex, -1);
  assert.notEqual(modelDescriptionIndex, -1);
  assert.notEqual(modelCountIndex, -1);
  assert.notEqual(resetButtonIndex, -1);
  assert.ok(modelCheckIndex < modelNameIndex);
  assert.ok(modelNameIndex < modelTitleIndex);
  assert.ok(modelTitleIndex < modelDescriptionIndex);
  assert.ok(modelNameIndex < modelCountIndex);
  assert.ok(modelCountIndex < resetButtonIndex);
  assert.doesNotMatch(modelRowBlock, /<label\b[\s\S]*analysis-model-check/);
  assert.ok(sonaraRowIndex < sonaraModeIndex);
  assert.ok(sonaraModeIndex < sonaraBatchIndex);
  assert.ok(sonaraBatchIndex < mlRowsIndex);
  assert.ok(mlRowsIndex < mlSettingsIndex);
  assert.match(source, /analysis-family-card sonara-analysis-block/);
  assert.match(source, /analysis-family-card models-analysis-block/);
  assert.doesNotMatch(source, /mlModelsSelected/);
  assert.doesNotMatch(source, /classifiersSelected/);
  assert.doesNotMatch(styles, /\.analysis-family-card\.selected/);
  assert.doesNotMatch(styles, /\.analysis-limit\s*\{[^}]*display:\s*flex/);
  assert.match(styles, /\.ml-analysis-settings \.analysis-device\s*\{[^}]*grid-column:\s*1\s*\/\s*-1;/);
  assert.ok(batchSizeIndex < analyzeSelectedIndex);
});

test("ui class names describe responsibility instead of visual priority", () => {
  const staleClasses = new Set([
    "primary",
    "secondary-mini",
    "meta",
    "meta-badge",
    "track-copy",
    "filters",
    "compact-filters",
    "player",
    "action-row",
    "score",
    "analysis-section-title",
    "search-section",
    "playlist-section"
  ]);
  const failures = [];
  for (const file of sourceFiles(srcDir)) {
    const source = readFileSync(file, "utf8");
    for (const className of source.matchAll(/className=(?:"([^"]+)"|\{`([^`]+)`\})/g)) {
      const value = className[1] || className[2] || "";
      for (const token of value.split(/\s+/).filter(Boolean)) {
        if (staleClasses.has(token)) failures.push(`${file}: ${value}`);
      }
    }
  }
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  assert.deepEqual(failures, []);
  for (const className of staleClasses) {
    assert.doesNotMatch(styles, new RegExp(`\\.${className}(?=[\\s,{:.#])`));
  }
  assert.match(styles, /\.library-summary-badge\s*{/);
  assert.match(styles, /\.track-panel \.panel-title \.library-summary-total-badge\s*{/);
  assert.doesNotMatch(styles, /\.library-summary\s*{/);
  assert.match(styles, /\.track-title-cell\s*{/);
  assert.match(styles, /\.search-filter-grid\s*{/);
  assert.match(styles, /\.analysis-models-heading\s*{/);
  assert.match(styles, /\.search-workflow-section\s*{/);
  assert.match(styles, /\.playlist-export-section\s*{/);
  assert.doesNotMatch(styles, /\.library-preview-player\s*{/);
  assert.match(styles, /\.export-action-row\s*{/);
  assert.match(styles, /\.similarity-score\s*{/);
});

test("class tab exposes per-classifier missing-score analysis controls", () => {
  const searchSource = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const selectionSource = readFileSync(join(srcDir, "analysisSelection.ts"), "utf8");
  const librarySource = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");

  assert.match(searchSource, /classifier-controls/);
  assert.match(searchSource, /type="range"/);
  assert.match(searchSource, /onClassifierMinScoreChange/);
  assert.match(searchSource, /classifier-analyze-button/);
  assert.match(searchSource, /onAnalyzeClassifier/);
  assert.match(searchSource, /classifier-reset-button/);
  assert.match(searchSource, /onResetClassifier/);
  assert.match(searchSource, /orderedClassifierProfiles\.length \? \(/);
  assert.match(searchSource, /orderPromotedClassifiers\(classifiers\)/);
  assert.match(searchSource, /classifierScoringBlockedReason\(classifier\)/);
  assert.match(searchSource, /className="classifier-profile unavailable"/);
  assert.match(searchSource, /classifier-profile-status-reason/);
  assert.match(searchSource, /classifier\.profile_description/);
  assert.match(searchSource, /classifierManifestFacts\(classifier\)/);
  assert.match(searchSource, /className="custom-classifier-profile-title"/);
  assert.match(searchSource, /classifier-profile-facts[\s\S]*classifier-profile-actions/);
  assert.match(searchSource, /classifier-profile-primary-facts/);
  assert.match(searchSource, /classifier-profile-secondary-facts/);
  assert.match(searchSource, /\["Status", "Type", "Models", "Calibrated"\]/);
  assert.doesNotMatch(searchSource, /classifier-profile-labels/);
  assert.match(searchSource, /label: "Status"/);
  assert.match(searchSource, /formatPromotedDate\(promotedAt\)/);
  assert.doesNotMatch(searchSource, /database ready|classifier\.ready|classifier\.not_ready/);
  assert.match(searchSource, /available \{availableClassifierCount\} · blocked \{blockedClassifierCount\}/);
  assert.match(searchSource, /empty-state classifier-empty-state/);
  assert.match(searchSource, /No promoted classifier profiles found/);
  assert.match(searchSource, /models\/classifiers\/<profile>\//);
  assert.doesNotMatch(appSource, /selectedAnalysisModels\.includes\("classifiers"\)|compatibleClassifierKeys/);
  assert.match(appSource, /analysisPipelineStart/);
  assert.match(appSource, /useState<AnalysisSelection\[]>\(defaultAnalysisSelections\)/);
  assert.match(appSource, /tab === "class" && databasePath[\s\S]*refreshClassifierProfilesInBackground/);
  assert.match(appSource, /api\.analyzeClassifier/);
  assert.match(appSource, /api\.resetClassifier/);
  assert.doesNotMatch(appSource, /classifierRequiredModels/);
  assert.doesNotMatch(appSource, /setPendingClassifierAfterAnalysis/);
  assert.doesNotMatch(selectionSource, /"classifiers"/);
  assert.match(appSource, /analysisSelectionOrder/);
  assert.match(librarySource, /mlAnalysisModelOrder/);
  assert.equal(librarySource.includes("classifier" + "Available"), false);
});

test("per-classifier analyze button validates that classifier before reset and scoring", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const handler = appSource.match(/async function handleAnalyzeClassifier[\s\S]*?async function handleEmbeddingSearch/)?.[0] || "";

  const refreshIndex = handler.indexOf("const promotedClassifiers = await api.classifiers()");
  const compatibilityIndex = handler.indexOf("classifierScoringBlockedReason(currentClassifier)");
  const resetIndex = handler.indexOf("api.resetClassifier(currentClassifier.classifier_key)");
  const analyzeIndex = handler.indexOf("api.analyzeClassifier(currentClassifier.classifier_key)");

  assert.notEqual(refreshIndex, -1);
  assert.notEqual(compatibilityIndex, -1);
  assert.notEqual(resetIndex, -1);
  assert.notEqual(analyzeIndex, -1);
  assert.ok(refreshIndex < compatibilityIndex);
  assert.ok(compatibilityIndex < resetIndex);
  assert.ok(resetIndex < analyzeIndex);
  assert.doesNotMatch(handler, /analysisLimit/);
});

test("classifier score reset immediately disables its slider", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const handler = appSource.match(/async function handleResetClassifier[\s\S]*?async function handleEmbeddingSearch/)?.[0] || "";

  assert.match(handler, /setClassifierMinScores/);
  assert.match(handler, /delete next\[classifier\.classifier_key\]/);
  assert.match(handler, /setClassifiers\(\(current\) => current\.map/);
  assert.match(handler, /scored_tracks: 0/);
});

test("initial database load does not wait for classifier readiness before library tracks", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const handler = appSource.match(/async function initializeDatabase[\s\S]*?async function loadLatestJobs/)?.[0] || "";

  const currentIndex = handler.indexOf("const current = await api.currentDatabase()");
  const classifierRequestIndex = handler.indexOf("const promotedClassifiersRequest = api.classifiers()");
  const refreshIndex = handler.indexOf("await refreshLibrary(0, {");
  const classifierAwaitIndex = handler.indexOf("const promotedClassifiers = await promotedClassifiersRequest");

  assert.notEqual(currentIndex, -1);
  assert.notEqual(classifierRequestIndex, -1);
  assert.notEqual(refreshIndex, -1);
  assert.notEqual(classifierAwaitIndex, -1);
  assert.ok(currentIndex < classifierRequestIndex);
  assert.ok(classifierRequestIndex < refreshIndex);
  assert.ok(refreshIndex < classifierAwaitIndex);
});

test("explicit database refresh adopts its catalog scope and suppresses the duplicate dependency-effect refresh", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const effect = appSource.match(/useEffect\(\(\) => \{[\s\S]*?suppressNextLibraryRefresh[\s\S]*?\}, \[[\s\S]*?databaseCatalogUuid[\s\S]*?\]\);/)?.[0] || "";
  const initialize = appSource.match(/async function initializeDatabase[\s\S]*?async function loadLatestJobs/)?.[0] || "";
  const choose = appSource.match(/async function handleChooseDatabase[\s\S]*?async function handleChooseOutputFolder/)?.[0] || "";

  assert.match(appSource, /const suppressNextLibraryRefresh = useRef\(false\)/);
  assert.match(effect, /if \(suppressNextLibraryRefresh\.current\) \{[\s\S]*?suppressNextLibraryRefresh\.current = false;[\s\S]*?return;/);
  assert.match(initialize, /suppressNextLibraryRefresh\.current = true;[\s\S]*?adoptDatabaseScope\(current\.catalog_uuid\);[\s\S]*?setDatabasePath\(current\.path\);[\s\S]*?await refreshLibrary\(0,\s*\{[\s\S]*?databaseKey:\s*current\.catalog_uuid[\s\S]*?refreshSummary:\s*true/);
  assert.match(choose, /suppressNextLibraryRefresh\.current = true;[\s\S]*?resetDatabaseScopedState\(\);[\s\S]*?adoptDatabaseScope\(value\.catalog_uuid\);[\s\S]*?setDatabasePath\(value\.path\);[\s\S]*?await refreshLibrary\(0,\s*\{[\s\S]*?databaseKey:\s*value\.catalog_uuid[\s\S]*?refreshSummary:\s*true/);
});

test("analysis and scan controls use the measured machine defaults", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const scanDialogSource = readFileSync(join(srcDir, "ScanImportDialog.tsx"), "utf8");
  const sonaraSettingsSource = readFileSync(join(srcDir, "sonaraAnalysisSettings.ts"), "utf8");
  const schemaSource = readFileSync(join(srcDir, "..", "..", "src", "dj_track_similarity", "analysis_config.py"), "utf8");
  const apiSchemaSource = readFileSync(join(srcDir, "..", "..", "src", "dj_track_similarity", "api_schemas.py"), "utf8");

  assert.match(scanDialogSource, /workers:\s*8/);
  assert.match(appSource, /analysisTrackBatchSize,\s*setAnalysisTrackBatchSize\]\s*=\s*useState\(8\)/);
  assert.match(appSource, /analysisInferenceBatchSize,\s*setAnalysisInferenceBatchSize\]\s*=\s*useState\(16\)/);
  assert.match(appSource, /loadSonaraAnalysisSettings\(\)/);
  assert.match(sonaraSettingsSource, /mode:\s*"direct"/);
  assert.match(sonaraSettingsSource, /directBatchSize:\s*8/);
  assert.match(sonaraSettingsSource, /processes:\s*4/);
  assert.match(sonaraSettingsSource, /threads:\s*4/);
  assert.match(sonaraSettingsSource, /batchSize:\s*4/);
  assert.match(sonaraSettingsSource, /stageSize:\s*32/);
  assert.match(schemaSource, /DEFAULT_ANALYSIS_TRACK_BATCH_SIZE\s*=\s*8/);
  assert.match(schemaSource, /DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE\s*=\s*16/);
  assert.match(schemaSource, /DEFAULT_SONARA_BATCH_SIZE\s*=\s*8/);
  assert.match(apiSchemaSource, /class ScanRequest[\s\S]*?workers:\s*int\s*=\s*Field\(default=8/);
  assert.match(apiSchemaSource, /class TagRefreshRequest[\s\S]*?workers:\s*int\s*=\s*Field\(default=8/);
});

test("analysis model reset buttons fit inside a full-width row", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const actionsRule = styles.match(/\.analysis-actions\s*{([\s\S]*?)}/)?.[1] || "";
  const rowRule = styles.match(/\.analysis-model-row\s*{([\s\S]*?)}/)?.[1] || "";
  const resetRule = styles.match(/\.analysis-reset-button\s*{([\s\S]*?)}/)?.[1] || "";
  const resetIntentRule = styles.match(/\.analysis-reset-button\.stop-button\s*{([\s\S]*?)}/)?.[1] || "";
  const resetButtonBlock = source.match(/className=\{`icon-button stop-button analysis-reset-button[\s\S]*?<\/button>/)?.[0] || "";

  assert.match(source, /icon-button stop-button analysis-reset-button \$\{model\}-reset-button/);
  assert.doesNotMatch(resetButtonBlock, />\s*Reset\s*</);
  assert.match(actionsRule, /align-self:\s*stretch/);
  assert.match(actionsRule, /width:\s*100%/);
  assert.match(rowRule, /grid-template-columns:\s*34px\s+minmax\(0,\s*1fr\)\s+minmax\(76px,\s*max-content\)\s+34px/);
  assert.match(rowRule, /width:\s*100%/);
  assert.doesNotMatch(rowRule, /82px/);
  assert.doesNotMatch(resetRule, /min-width:\s*96px/);
  assert.doesNotMatch(resetRule, /white-space:\s*nowrap/);
  assert.match(resetIntentRule, /background:\s*var\(--danger-bg\)/);
  assert.match(resetIntentRule, /border-color:\s*var\(--danger-border-hover\)/);
  assert.match(resetIntentRule, /color:\s*var\(--danger-deep-text\)/);
});

test("frontend analysis api uses unified job endpoints only", () => {
  const source = readFileSync(join(srcDir, "apiClient.ts"), "utf8");

  assert.match(source, /\/api\/analysis\/jobs/);
  assert.doesNotMatch(source, /\/api\/sonara\/analyze/);
  assert.doesNotMatch(source, /\/api\/genres\/analyze/);
  assert.doesNotMatch(source, /\/api\/analyze"/);
});

test("model search UI defaults to twenty while API fallbacks remain ten", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const schemaSource = readFileSync(join(srcDir, "..", "..", "src", "dj_track_similarity", "api_schemas.py"), "utf8");

  assert.match(appSource, /const \[filters, setFilters\] = useState<SearchFiltersState>\(\{[\s\S]*?limit:\s*20/);
  assert.match(schemaSource, /class SearchRequest[\s\S]*limit:\s*int\s*=\s*Field\(default=10/);
  assert.match(schemaSource, /class SonaraSearchRequest[\s\S]*limit:\s*int\s*=\s*Field\(default=10/);
  assert.match(schemaSource, /class TextSearchRequest[\s\S]*limit:\s*int\s*=\s*Field\(default=10/);
});

test("model search exposes only current seed controls", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const searchSource = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const apiSource = readFileSync(join(srcDir, "api.ts"), "utf8");
  const schemaSource = readFileSync(join(srcDir, "..", "..", "src", "dj_track_similarity", "api_schemas.py"), "utf8");

  assert.match(appSource, /seed_track_ids:\s*seeds/);
  assert.match(searchSource, /handleSonaraSearch/);
  assert.match(searchSource, /handleEmbeddingSearch/);
  assert.match(searchSource, /activeSearchTab === "mert" \|\| activeSearchTab === "muq"/);
  assert.match(apiSource, /seed_track_ids/);
  assert.match(schemaSource, /seed_track_ids/);
});

test("analysis process status renders per-model progress", () => {
  const source = readFileSync(join(srcDir, "jobUi.tsx"), "utf8");
  const analysisStatus = source.slice(
    source.indexOf("function AnalysisProcessStatus"),
    source.indexOf("type ProgressItem")
  );

  assert.match(source, /model_progress/);
  assert.match(source, /analysis-model-progress/);
  assert.match(source, /Object\.keys\(progress \|\| \{\}\)/);
  assert.ok(
    analysisStatus.indexOf("<ModelProgress job={job} />") < analysisStatus.indexOf('className="analysis-current"'),
    "model progress appears before the current file in the log status"
  );
  assert.doesNotMatch(source, /api\.sonaraJob/);
  assert.doesNotMatch(source, /api\.genreJob/);
});

test("destructive actions use the in-app confirmation dialog", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const dialogSource = readFileSync(join(srcDir, "dialogs.tsx"), "utf8");

  assert.doesNotMatch(appSource, /window\.confirm/);
  assert.match(appSource, /ConfirmationDialog/);
  assert.match(dialogSource, />Да</);
  assert.match(dialogSource, />Нет</);
});

test("non-destructive sonara mixer reset does not request confirmation", () => {
  const source = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const resetBody = source.match(/function resetCustomSonara\(\) \{([\s\S]*?)\n  \}/)?.[1] || "";

  assert.match(source, /sonara-mixer-reset-button/);
  assert.match(resetBody, /setFilters/);
  assert.doesNotMatch(resetBody, /onConfirmAction|ConfirmationRequest/);
});

test("class search tab shows classifier threshold and scoped analysis controls", () => {
  const source = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const classPanel = source.match(/\{activeSearchTab === "class" && \(([\s\S]*?)\n        \)\}/)?.[1] || "";

  assert.match(classPanel, /classifier-controls/);
  assert.match(classPanel, /type="range"/);
  assert.match(classPanel, /classifier-analyze-button/);
  assert.match(classPanel, /if \(blockedReason\)/);
  assert.match(classPanel, /classifier-profile unavailable/);
  assert.match(classPanel, /classifier-profile-status-badge/);
  assert.match(classPanel, /classifier-reset-button/);
  assert.doesNotMatch(classPanel, /classifier-action-row/);
  assert.doesNotMatch(classPanel, />\s*Reset\s*</);
});

test("text search exposes CLAP and MuQ-MuLan retrieval with optional negative contrast", () => {
  const searchSource = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const clapSource = readFileSync(join(srcDir, "ClapSearchTab.tsx"), "utf8");
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const apiSource = readFileSync(join(srcDir, "api.ts"), "utf8");
  const apiClientSource = readFileSync(join(srcDir, "apiClient.ts"), "utf8");
  const schemaSource = readFileSync(join(srcDir, "..", "..", "src", "dj_track_similarity", "api_schemas.py"), "utf8");

  assert.match(searchSource, /<ClapSearchTab/);
  assert.match(clapSource, /clap-presets-button/);
  assert.match(clapSource, /applyClapPromptPreset/);
  assert.match(clapSource, /document\.addEventListener\("pointerdown"/);
  assert.match(clapSource, /clapPresetMenuRef/);
  assert.doesNotMatch(clapSource, /clap-generate-button/);
  assert.match(clapSource, /Text query\s*\n\s*<input\s*\n\s*type="text"/);
  assert.match(clapSource, />\s*Negative\s*</);
  assert.match(clapSource, /Negative\s*\n\s*<input\s*\n\s*type="text"\s*\n\s*className="clap-negative-input"/);
  assert.doesNotMatch(clapSource, /<textarea/);
  assert.doesNotMatch(clapSource, />\s*Avoid\s*</);
  assert.match(clapSource, /clap-negative-input/);
  assert.match(clapSource, /icon-button add-visible-tracks-button clap-negative-toggle/);
  assert.match(clapSource, /clapUseNegativePrompt \? "intent-add active" : ""/);
  assert.match(clapSource, /aria-label="Use negative prompt"/);
  assert.match(clapSource, /clap-negative-checkbox/);
  assert.doesNotMatch(clapSource, /clap-negative-toggle-text/);
  assert.doesNotMatch(clapSource, />\s*Use\s*</);
  assert.match(searchSource, /onClapUseNegativePromptChange/);
  assert.match(searchSource, /textEmbeddingFamily/);
  assert.match(searchSource, /hasStoredTextEmbeddings/);
  assert.match(clapSource, /clap-search-requirement/);
  assert.match(clapSource, /<option value="clap">CLAP<\/option>/);
  assert.match(clapSource, /<option value="mulan">MuQ-MuLan<\/option>/);
  assert.match(clapSource, /disabled=\{busy \|\| !textQuery\.trim\(\) \|\| !hasStoredTextEmbeddings\}/);
  assert.doesNotMatch(clapSource, /WandSparkles/);
  assert.match(clapSource, /ListFilter/);
  assert.match(appSource, /embeddingCounts=\{\{[\s\S]*clap:\s*librarySummary\.clap/);
  assert.doesNotMatch(appSource, /generateClapPrompt/);
  assert.match(appSource, /api\.textSearch/);
  assert.match(appSource, /analysis_family:\s*textEmbeddingFamily/);
  assert.match(appSource, /const\s+\[clapUseNegativePrompt,\s*setClapUseNegativePrompt\]\s*=\s*useState\(true\)/);
  assert.match(appSource, /promptQueriesFromText\(prompt,\s*clapNegativeQuery,\s*clapUseNegativePrompt\)/);
  assert.match(apiClientSource, /request<SearchResult\[\]>\("\/api\/search\/text"/);
  assert.match(appSource, /positive_queries/);
  assert.match(appSource, /negative_queries/);
  assert.match(appSource, /adaptive_contrast:\s*true/);
  assert.match(apiClientSource, /positive_queries\?:\s*string\[\]/);
  assert.match(apiClientSource, /negative_queries\?:\s*string\[\]/);
  assert.match(apiClientSource, /analysis_family\?:\s*"clap" \| "mulan"/);
  assert.match(apiSource, /export \{ api \} from "\.\/apiClient";/);
  assert.match(schemaSource, /positive_queries:\s*list\[str\]/);
  assert.match(schemaSource, /negative_queries:\s*list\[str\]/);
  assert.match(schemaSource, /adaptive_contrast:\s*bool\s*=\s*True/);
  assert.match(schemaSource, /analysis_family:\s*Literal\["clap", "mulan"\]\s*=\s*"clap"/);
});

test("classifier analysis uses only the per-classifier job path", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");

  assert.doesNotMatch(appSource, /classifier_keys: classifierKeys|aggregateClassifier/);
  assert.doesNotMatch(appSource, /startClassifierJobs/);
  assert.match(appSource, /api\.analyzeClassifier/);
  assert.doesNotMatch(appSource, /classifierRequiredModels/);
});

test("documentation title click opens the docs in a separate window", () => {
  const source = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const headerLink = source.match(/<a\b[\s\S]*?>\s*DJ Track Similarity\s*<\/a>/)?.[0] || "";

  assert.match(source, /function openDocumentationWindow/);
  assert.match(source, /window\.open\("\/docs\/", "_blank", "noopener,noreferrer"\)/);
  assert.match(headerLink, /target="_blank"/);
  assert.match(headerLink, /onClick=\{openDocumentationWindow\}/);
});

test("topbar Rhythm Lab control starts or opens the lab", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const apiSource = readFileSync(join(srcDir, "apiClient.ts"), "utf8");
  const actionsBlock = appSource.match(/<div className="topbar-actions">([\s\S]*?)<\/div>/)?.[1] || "";

  assert.match(apiSource, /rhythmLabStatus:\s*\(\)\s*=>/);
  assert.match(apiSource, /\/api\/rhythm-lab\/status/);
  assert.match(apiSource, /launchRhythmLab:\s*\(\)\s*=>/);
  assert.match(apiSource, /\/api\/rhythm-lab\/launch/);
  assert.match(appSource, /function openRhythmLabWindow/);
  assert.match(appSource, /api\.launchRhythmLab\(\)/);
  assert.match(appSource, /window\.open\("about:blank", "_blank"\)/);
  assert.match(appSource, /pendingWindow\.location\.href = result\.url/);
  assert.match(actionsBlock, /rhythm-lab-launch-button[\s\S]*server-shutdown-button[\s\S]*stop-active-stage-button/);
});

test("topbar omits a Rhythm Lab stop control", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const actionsBlock = appSource.match(/<div className="topbar-actions">([\s\S]*?)<\/div>/)?.[1] || "";

  assert.match(actionsBlock, /rhythm-lab-launch-button[\s\S]*server-shutdown-button[\s\S]*stop-active-stage-button/);
  assert.doesNotMatch(actionsBlock, /rhythm-lab-stop-button/);
  assert.doesNotMatch(appSource, /handleStopRhythmLab|api\.stopRhythmLab/);
});

test("audio helper tools are absent from the application client", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const apiSource = readFileSync(join(srcDir, "apiClient.ts"), "utf8");

  assert.doesNotMatch(appSource, /Audio(Dedup|Doctor)/);
  assert.doesNotMatch(apiSource, /audio-(dedup|doctor)/);
});

test("library controls keep pagination left and actions pinned right", () => {
  const source = readFileSync(join(srcDir, "TrackPanel.tsx"), "utf8");
  const pagination = source.match(
    /<div className="library-pagination-controls"[\s\S]*?<\/div>/
  )?.[0] || "";
  const prevIndex = pagination.indexOf("library-page-previous-button");
  const nextIndex = pagination.indexOf("library-page-next-button");
  const inputIndex = pagination.indexOf("library-page-index-input");

  assert.doesNotMatch(source, /library-load-size-(control|button)/);
  assert.notEqual(prevIndex, -1);
  assert.notEqual(nextIndex, -1);
  assert.notEqual(inputIndex, -1);
  assert.equal((pagination.match(/<button\b/g) || []).length, 2);
  assert.equal((pagination.match(/<input\b/g) || []).length, 1);
  assert.match(pagination, /library-page-number-status/);
  assert.match(pagination, /library-range-status/);
  assert.match(pagination, /library-filtered-total-status/);
  assert.ok(prevIndex < nextIndex);
  assert.ok(nextIndex < inputIndex);
  assert.ok(inputIndex < pagination.indexOf("library-page-number-status"));
  assert.ok(pagination.indexOf("library-page-number-status") < pagination.indexOf("library-range-status"));
  assert.ok(pagination.indexOf("library-range-status") < pagination.indexOf("library-filtered-total-status"));
  assert.ok(source.indexOf("library-pagination-controls") < source.indexOf("library-sort-direction-button"));
  const shuffleIndex = source.indexOf("library-playback-shuffle-button");
  const likedIndex = source.indexOf("liked-filter-button");
  const playbackControlsIndex = source.indexOf("library-playback-controls");
  const paginationIndex = source.indexOf("library-pagination-controls");
  const playbackOrderControls = source.match(/<div className="library-playback-order-controls">([\s\S]*?)<\/div>/)?.[1] || "";
  assert.notEqual(shuffleIndex, -1);
  assert.ok(paginationIndex < likedIndex);
  assert.ok(playbackControlsIndex < likedIndex);
  assert.ok(likedIndex < shuffleIndex);
  assert.ok(shuffleIndex < source.indexOf("library-sort-direction-button"));
  assert.match(playbackOrderControls, /library-playback-shuffle-button[\s\S]*library-sort-direction-button/);
  assert.doesNotMatch(playbackOrderControls, /library-preset-button/);
  assert.doesNotMatch(playbackOrderControls, /liked-filter-button/);
  assert.ok(source.indexOf("library-sort-direction-button") < source.indexOf("add-visible-tracks-button"));
});

test("library search exposes an explicit LIKE and FTS segmented toggle", () => {
  const source = readFileSync(join(srcDir, "TrackPanel.tsx"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");

  assert.match(source, /library-search-mode-toggle/);
  assert.match(source, /library-search-like-button/);
  assert.match(source, /library-search-fts-button/);
  assert.match(source, /searchMode === "like"/);
  assert.match(source, /searchMode === "fts"/);
  assert.match(source, /onSearchModeChange\("fts"\)/);
  assert.match(styles, /\.library-search-mode-toggle\s*{/);
  assert.match(styles, /\.library-search-mode-toggle button\s*{/);
});

test("library search placeholder lists fields as path, title, artist, and genre", () => {
  const source = readFileSync(join(srcDir, "TrackPanel.tsx"), "utf8");

  assert.match(source, /placeholder="path, title, artist, genre"/);
});

test("track rows keep analysis availability out of track copy", () => {
  const source = readFileSync(join(srcDir, "TrackRows.tsx"), "utf8");
  const trackListSource = source.match(/export function TrackList[\s\S]*?\n}\n\nfunction formatPlaybackTime/)?.[0] || "";

  assert.doesNotMatch(trackListSource, /trackInfo\(track\)/);
  assert.doesNotMatch(trackListSource, /analysisStatusLabel/);
  assert.match(trackListSource, /PlaybackSeekControl/);
});

test("candidate result rows expose the shared liked toggle", () => {
  const rowsSource = readFileSync(join(srcDir, "TrackRows.tsx"), "utf8");
  const searchSource = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const trackListSource = rowsSource.match(/export function TrackList[\s\S]*?\n}\n\nexport function ResultRow/)?.[0] || "";
  const resultRowSource = rowsSource.match(/export function ResultRow[\s\S]*?\n}\n\nfunction scoreBreakdownTitle/)?.[0] || "";
  const resultListSource = searchSource.match(/<div className="results-list">[\s\S]*?<\/div>\s*<\/section>/)?.[0] || "";
  const searchPanelSource = appSource.match(/<SearchPlaylistPanel[\s\S]*?\/>/)?.[0] || "";

  assert.ok(trackListSource.indexOf("track-liked-button") < trackListSource.indexOf("track-metadata-button"));
  assert.match(resultRowSource, /onToggleLiked/);
  assert.match(resultRowSource, /track-liked-button/);
  assert.match(resultRowSource, /aria-pressed=\{track\.liked\}/);
  assert.ok(resultRowSource.indexOf("<meter") < resultRowSource.indexOf("track-liked-button"));
  assert.ok(resultRowSource.indexOf("similarity-score") < resultRowSource.indexOf("track-liked-button"));
  assert.ok(resultRowSource.indexOf("track-liked-button") < resultRowSource.indexOf("result-metadata-button"));
  assert.ok(resultRowSource.indexOf("result-metadata-button") < resultRowSource.indexOf("result-seed-button"));
  assert.match(resultListSource, /onToggleLiked=\{toggleLiked\}/);
  assert.match(searchPanelSource, /toggleLiked=\{handleToggleTrackLiked\}/);
});

test("library search mode active state highlights the active mode text", () => {
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const activeRule = styles.match(/\.library-search-mode-toggle button\.active\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(activeRule, /background:\s*transparent;/);
  assert.match(activeRule, /color:\s*var\(--accent-hover\);/);
});

test("syncopated library preset uses a danger accent only when active", () => {
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const defaultRule = styles.match(/\.library-preset-button\s*{([\s\S]*?)}/)?.[1] || "";
  const activeRule = styles.match(/\.library-preset-button\.active\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(defaultRule, /background:\s*transparent;/);
  assert.doesNotMatch(defaultRule, /--warning-/);
  assert.match(activeRule, /background:\s*var\(--danger-muted-bg\);/);
  assert.match(activeRule, /border-color:\s*var\(--danger-border-hover\);/);
  assert.match(activeRule, /color:\s*var\(--danger-text\);/);
});

test("library pagination exposes page count, range, and current-selection total", () => {
  const source = readFileSync(join(srcDir, "TrackPanel.tsx"), "utf8");
  const pagination = source.match(
    /<div className="library-pagination-controls"[\s\S]*?<\/div>/
  )?.[0] || "";

  assert.match(pagination, />Prev<\/button>/);
  assert.match(pagination, />Next<\/button>/);
  assert.match(pagination, /className="library-page-index-input"/);
  assert.match(pagination, /className="library-page-number-status"/);
  assert.match(pagination, /\$\{currentPage\} \/ \$\{pageCount\}/);
  assert.match(pagination, /className="library-range-status"/);
  assert.match(pagination, /\$\{rangeStart\}–\$\{rangeEnd\}/);
  assert.match(pagination, /className="library-filtered-total-status"/);
  assert.match(pagination, /\{loading \? "\.\.\." : `\(\$\{total\}\)`\}/);
  assert.doesNotMatch(pagination, /Всего:/);
  assert.doesNotMatch(source, /library-load-cancel-button/);
});

test("library pagination controls share height and keep actions pinned right", () => {
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const controlsRule = styles.match(/\.library-view-controls\s*{([\s\S]*?)}/)?.[1] || "";
  const paginationRule = styles.match(/\.library-pagination-controls\s*{([\s\S]*?)}/)?.[1] || "";
  const controlRule = styles.match(/\.library-pagination-controls \.library-page-previous-button,[\s\S]*?\.library-pagination-controls \.library-page-next-button\s*{([\s\S]*?)}/)?.[1] || "";
  const inputRule = styles.match(/\.library-page-index-input\s*{([\s\S]*?)}/)?.[1] || "";
  const statusRule = styles.match(/\.library-page-number-status,\s*\.library-range-status,\s*\.library-filtered-total-status\s*{([\s\S]*?)}/)?.[1] || "";
  const playbackControlsRule = styles.match(/\.library-playback-controls\s*{([\s\S]*?)}/)?.[1] || "";
  const playbackOrderRule = styles.match(/\.library-playback-order-controls\s*{([\s\S]*?)}/)?.[1] || "";
  const sortRule = styles.match(/\.library-sort-direction-button\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(controlsRule, /gap:\s*6px/);
  assert.match(paginationRule, /display:\s*inline-flex/);
  assert.match(paginationRule, /gap:\s*6px/);
  assert.match(controlRule, /height:\s*34px/);
  assert.match(inputRule, /align-self:\s*start/);
  assert.match(inputRule, /height:\s*34px/);
  assert.match(statusRule, /height:\s*34px/);
  assert.match(statusRule, /font-variant-numeric:\s*tabular-nums/);
  assert.match(playbackControlsRule, /display:\s*flex/);
  assert.match(playbackControlsRule, /gap:\s*6px/);
  assert.match(playbackControlsRule, /margin-left:\s*auto/);
  assert.match(playbackOrderRule, /display:\s*flex/);
  assert.match(playbackOrderRule, /gap:\s*6px/);
  assert.doesNotMatch(playbackOrderRule, /margin-left/);
  assert.doesNotMatch(sortRule, /margin-left/);
  assert.doesNotMatch(styles, /\.library-(load-size|load-cancel)/);
});

test("library panel scrolls its own controls inside the fixed desktop workspace", () => {
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const workspaceRule = styles.match(/\.workspace\s*{([\s\S]*?)}/)?.[1] || "";
  const libraryRule = styles.match(/\.library-panel\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(workspaceRule, /height:\s*calc\(100vh - 86px\)/);
  assert.match(libraryRule, /overflow:\s*auto/);
});

test("database validation starts without opening the log dialog", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const handler = appSource.match(/async function handleValidateDatabase[\s\S]*?async function handleClearDatabase/)?.[0] || "";

  assert.match(handler, /setProcessLogKind\("database_validation"\)/);
  assert.doesNotMatch(handler, /setLogFrameOpen\(/);
});

test("database validation is disabled until the library has tracks", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");
  const validationButton = source.match(/<button className="icon-button database-validation-button"[\s\S]*?<\/button>/)?.[0] || "";

  assert.match(validationButton, /disabled=\{busy \|\| stageRunning \|\| !hasTracks\}/);
});
