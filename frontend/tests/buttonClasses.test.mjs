import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));
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
  const primaryButtonMatch = styles.match(/\.scan-action-row \.scan-settings-button\s*{([\s\S]*?)}/);
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
  assert.match(source, /className="scan-settings-button"[\s\S]*?<Music4 size=\{15\}/);
  assert.doesNotMatch(source, /scan-start-button/);
  assert.doesNotMatch(styles, /scan-start-button/);
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
  assert.match(source, /model !== "sonara" && analysisCounts\.sonara < 1/);
  assert.match(appSource, /if \(librarySummary\.sonara < 1\) \{\s*setSelectedAnalysisModels\(\["sonara"\]\);/);
  assert.doesNotMatch(source, /mlModelsSelected/);
  assert.doesNotMatch(source, /classifiersSelected/);
  assert.doesNotMatch(styles, /\.analysis-family-card\.selected/);
  assert.doesNotMatch(styles, /\.analysis-limit\s*\{[^}]*display:\s*flex/);
  assert.match(styles, /\.ml-analysis-settings \.analysis-device\s*\{[^}]*grid-column:\s*1\s*\/\s*-1;/);
  assert.ok(batchSizeIndex < analyzeSelectedIndex);
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
  assert.match(searchSource, /activeSearchTab === "similarity"/);
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
  assert.match(clapSource, /onTogglePreset\(preset\.key\)/);
  assert.match(clapSource, /document\.addEventListener\("pointerdown"/);
  assert.match(clapSource, /presetMenuRef/);
  assert.doesNotMatch(clapSource, /clap-generate-button/);
  assert.match(clapSource, /Prompt bank\s*\n\s*<textarea/);
  assert.match(clapSource, /clap-preset-axis-button/);
  assert.match(clapSource, /clap-preset-chip/);
  assert.match(clapSource, /clap-prompt-hint/);
  assert.doesNotMatch(clapSource, />\s*Avoid\s*</);
  assert.match(clapSource, /className="clap-negative-input"/);
  assert.match(clapSource, /clap-toolbar-button clap-negative-toggle/);
  // The picker and the negative toggle share one toolbar under the prompt bank
  // instead of floating beside the two textareas.
  assert.match(clapSource, /className="clap-prompt-toolbar"/);
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
  assert.match(appSource, /composePromptBanks\(keys,\s*model\)/);
  // Selecting a preset carries the model with it where the measurement is
  // unambiguous, so the choice is not a switch the user has to remember.
  assert.match(appSource, /const advice = modelAdvice\(keys\)/);
  assert.match(appSource, /advice\.kind === "single" \? advice\.model : textEmbeddingFamily/);
  assert.match(appSource, /negative_weight:\s*promptNegativeWeight/);
  assert.match(apiClientSource, /negative_weight\?:\s*number/);
  assert.match(schemaSource, /negative_weight:\s*float \| None/);
  assert.match(apiClientSource, /request<SearchResult\[\]>\("\/api\/search\/text"/);
  assert.match(appSource, /positive_queries/);
  assert.match(appSource, /negative_queries/);
  assert.match(apiClientSource, /positive_queries:\s*string\[\]/);
  assert.match(apiClientSource, /negative_queries\?:\s*string\[\]/);
  assert.match(apiClientSource, /analysis_family\?:\s*"clap" \| "mulan"/);
  assert.match(apiSource, /export \{ api \} from "\.\/apiClient";/);
  assert.match(schemaSource, /positive_queries:\s*list\[str\]/);
  assert.match(schemaSource, /negative_queries:\s*list\[str\]/);
  assert.match(schemaSource, /analysis_family:\s*Literal\["clap", "mulan"\]\s*=\s*"clap"/);
  // The bank is the only prompt field: no second copy of it as one string, and
  // no switch that reduces it to its first line.
  const afterTextRequest = schemaSource.split("class TextSearchRequest")[1];
  const textRequestSchema = afterTextRequest.slice(0, afterTextRequest.indexOf("class "));
  const textSearchPayloadType = apiClientSource.split("type TextSearchPayload = {")[1].split("};")[0];
  for (const retired of [/adaptive_contrast/, /preset/, /query/]) {
    assert.doesNotMatch(textRequestSchema, retired);
    assert.doesNotMatch(textSearchPayloadType, retired);
  }
});

test("selected text presets stay beside the picker with destructive badge intent", () => {
  const source = readFileSync(join(srcDir, "ClapSearchTab.tsx"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const chipRule = styles.match(/\.clap-preset-chip\s*{([\s\S]*?)}/)?.[1] || "";

  const selectedPresetIndex = source.indexOf("selectedPresets.map");
  const negativeToggleIndex = source.indexOf("clap-toolbar-button clap-negative-toggle");

  assert.ok(selectedPresetIndex !== -1, "selected presets are rendered");
  assert.ok(negativeToggleIndex !== -1, "negative toggle is rendered");
  assert.ok(
    selectedPresetIndex < negativeToggleIndex,
    "selected presets render beside the picker before the negative toggle"
  );
  assert.match(chipRule, /background:\s*var\(--danger-muted-bg\)/);
  assert.match(chipRule, /border:\s*1px solid var\(--danger-muted-border\)/);
  assert.match(chipRule, /color:\s*var\(--danger-text\)/);
  assert.match(chipRule, /line-height:\s*1\.15/);
  assert.match(chipRule, /padding:\s*2px 6px/);
  assert.match(chipRule, /height:\s*auto/);
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

test("database validation starts without opening the log dialog", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const handler = appSource.match(/async function handleValidateDatabase[\s\S]*?async function handleClearDatabase/)?.[0] || "";

  assert.match(handler, /setProcessLogKind\("database_validation"\)/);
  assert.doesNotMatch(handler, /setLogFrameOpen\(/);
});

test("track deletion clears deletion-scoped UI state before a library refresh can fail", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const handler = appSource.match(/async function handleDeleteTrack[\s\S]*?async function handleResetAnalysis/)?.[0] || "";

  assert.match(
    handler,
    /async \(\) => \{\s*const result = await api\.deleteTrack\(track\);\s*cancelTrackDetailRequest\(\);\s*resetSearchPlaylistState\(\);/,
  );
});

test("database validation is disabled until the library has tracks", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");
  const validationButton = source.match(/<button className="icon-button database-validation-button"[\s\S]*?<\/button>/)?.[0] || "";

  assert.match(validationButton, /disabled=\{busy \|\| stageRunning \|\| !hasTracks\}/);
});
