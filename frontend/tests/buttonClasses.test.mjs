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

test("class tab exposes per-classifier missing-score analysis controls", () => {
  const searchSource = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
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
  assert.match(appSource, /tab === "class" && databasePath[\s\S]*refreshClassifierProfilesInBackground/);
  assert.match(appSource, /api\.analyzeClassifier/);
  assert.match(appSource, /api\.resetClassifier/);
  assert.doesNotMatch(appSource, /classifierRequiredModels/);
  assert.doesNotMatch(appSource, /setPendingClassifierAfterAnalysis/);
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
  const scanSettingsSource = readFileSync(join(srcDir, "scanImportSettings.ts"), "utf8");
  const sonaraSettingsSource = readFileSync(join(srcDir, "sonaraAnalysisSettings.ts"), "utf8");
  const schemaSource = readFileSync(join(srcDir, "..", "..", "src", "dj_track_similarity", "analysis_config.py"), "utf8");
  const apiSchemaSource = readFileSync(join(srcDir, "..", "..", "src", "dj_track_similarity", "api_schemas.py"), "utf8");

  assert.match(scanSettingsSource, /workers:\s*8/);
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
  const textTabSource = readFileSync(join(srcDir, "TextSearchTab.tsx"), "utf8");
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const apiSource = readFileSync(join(srcDir, "api.ts"), "utf8");
  const apiClientSource = readFileSync(join(srcDir, "apiClient.ts"), "utf8");
  const schemaSource = readFileSync(join(srcDir, "..", "..", "src", "dj_track_similarity", "api_schemas.py"), "utf8");

  assert.match(searchSource, /<TextSearchTab/);
  assert.match(textTabSource, /onTogglePreset\(preset\.key\)/);
  assert.match(textTabSource, /document\.addEventListener\("pointerdown"/);
  assert.match(textTabSource, /presetMenuRef/);
  assert.doesNotMatch(textTabSource, /text-generate-button/);
  assert.match(textTabSource, /text-preset-axis-button/);
  assert.match(textTabSource, /text-preset-chip/);
  assert.match(textTabSource, /text-prompt-hint/);
  assert.doesNotMatch(textTabSource, />\s*Avoid\s*</);
  assert.match(textTabSource, /className="text-negative-input"/);
  // The negative bank is switched by a button that reports its own state, not
  // by a checkbox hidden inside a label.
  assert.match(textTabSource, /role="switch"/);
  assert.match(textTabSource, /aria-checked=\{textUseNegativePrompt\}/);
  assert.match(textTabSource, /text-negative-checkbox/);
  assert.doesNotMatch(textTabSource, /text-negative-toggle-text/);
  assert.doesNotMatch(textTabSource, />\s*Use\s*</);
  assert.match(searchSource, /onTextUseNegativePromptChange/);
  assert.match(searchSource, /textEmbeddingFamily/);
  assert.match(searchSource, /hasStoredTextEmbeddings/);
  assert.match(textTabSource, /text-search-requirement/);
  assert.match(textTabSource, /<option value="clap">CLAP<\/option>/);
  assert.match(textTabSource, /<option value="mulan">MuQ-MuLan<\/option>/);
  assert.match(textTabSource, /disabled=\{busy \|\| !textQuery\.trim\(\) \|\| !hasStoredTextEmbeddings\}/);
  assert.doesNotMatch(textTabSource, /WandSparkles/);
  assert.match(textTabSource, /ListFilter/);
  assert.match(appSource, /embeddingCounts=\{\{[\s\S]*clap:\s*librarySummary\.clap/);
  assert.doesNotMatch(appSource, /generateClapPrompt/);
  assert.match(appSource, /api\.textSearch/);
  assert.match(appSource, /analysis_family:\s*textEmbeddingFamily/);
  assert.match(appSource, /const\s+\[textUseNegativePrompt,\s*setTextUseNegativePrompt\]\s*=\s*useState\(true\)/);
  assert.match(appSource, /promptQueriesFromText\(prompt,\s*textNegativeQuery,\s*textUseNegativePrompt\)/);
  assert.match(appSource, /composePromptBanks\(keys,\s*model\)/);
  // Selecting a preset carries the model with it where the measurement is
  // unambiguous, so the choice is not a switch the user has to remember.
  assert.match(appSource, /const advice = modelAdvice\(keys\)/);
  assert.match(appSource, /advice\.kind === "single" \? advice\.model : textEmbeddingFamily/);
  assert.match(appSource, /negative_weight:\s*promptNegativeWeight/);
  assert.match(apiClientSource, /negative_weight\?:\s*number/);
  assert.match(schemaSource, /negative_weight:\s*float \| None/);
  assert.match(apiClientSource, /request<SearchResult\[\]>\("\/api\/search\/text"/);
  // Preset verdicts credit the bank that ranked the list: the client, the
  // schema and the App snapshot must stay one shape.
  assert.match(apiClientSource, /request<TextSearchFeedbackResult>\("\/api\/search\/text\/feedback"/);
  assert.match(apiClientSource, /preset_keys: string\[\]/);
  assert.match(apiClientSource, /verdict: -1 \| 0 \| 1/);
  assert.match(schemaSource, /class TextSearchFeedbackRequest/);
  assert.match(schemaSource, /verdict: Literal\[-1, 0, 1\]/);
  assert.match(appSource, /api\.textSearchFeedback/);
  assert.match(appSource, /textFeedbackContext/);
  assert.match(appSource, /presetKeys: \[\.\.\.selectedPresetKeys\]/);
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

test("library tools row Rhythm Lab control starts or opens the lab", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const apiSource = readFileSync(join(srcDir, "apiClient.ts"), "utf8");
  const librarySource = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");
  const toolsRowBlock = librarySource.match(/<div className="library-tools-row">([\s\S]*?)<\/div>/)?.[1] || "";
  const actionsBlock = appSource.match(/<div className="topbar-actions">([\s\S]*?)<\/div>/)?.[1] || "";

  assert.match(apiSource, /rhythmLabStatus:\s*\(\)\s*=>/);
  assert.match(apiSource, /\/api\/rhythm-lab\/status/);
  assert.match(apiSource, /launchRhythmLab:\s*\(\)\s*=>/);
  assert.match(apiSource, /\/api\/rhythm-lab\/launch/);
  assert.match(appSource, /function openRhythmLabWindow/);
  assert.match(appSource, /api\.launchRhythmLab\(\)/);
  assert.match(appSource, /window\.open\("about:blank", "_blank"\)/);
  assert.match(appSource, /pendingWindow\.location\.href = result\.url/);
  assert.match(appSource, /onLaunchRhythmLab=\{.*handleLaunchRhythmLab.*\}/);
  assert.doesNotMatch(actionsBlock, /rhythm-lab-button/);
  assert.match(toolsRowBlock, /rhythm-lab-button[\s\S]*audio-dedup-button/);
});

test("library tools row omits a Rhythm Lab stop control", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");
  const librarySource = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");

  assert.match(librarySource, /rhythm-lab-button/);
  assert.doesNotMatch(librarySource, /rhythm-lab-stop-button/);
  assert.doesNotMatch(appSource, /handleStopRhythmLab|api\.stopRhythmLab/);
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

  assert.match(validationButton, /disabled=\{stagesDisabled \|\| !hasTracks\}/);
});

test("seed chips use compact pill sizing and a compact removal icon", () => {
  const source = readFileSync(join(srcDir, "SearchPlaylistPanel.tsx"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const chipRule = styles.match(/\.seed-remove-chip\s*{([\s\S]*?)}/)?.[1] || "";
  const seedChip = source.match(/<button className="seed-remove-chip"[\s\S]*?<\/button>/)?.[0] || "";

  assert.match(chipRule, /border-radius:\s*999px;/);
  assert.match(chipRule, /font-size:\s*11px;/);
  assert.match(chipRule, /line-height:\s*1\.15;/);
  assert.match(chipRule, /padding:\s*2px 6px;/);
  assert.match(chipRule, /min-height:\s*0;/);
  assert.match(chipRule, /gap:\s*4px;/);
  assert.match(seedChip, /<X size=\{12\} \/>/);
});
