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

test("frontend analysis api uses unified job endpoints only", () => {
  const source = readFileSync(join(srcDir, "apiClient.ts"), "utf8");

  assert.match(source, /\/api\/analysis\/jobs/);
  assert.doesNotMatch(source, /\/api\/sonara\/analyze/);
  assert.doesNotMatch(source, /\/api\/genres\/analyze/);
  assert.doesNotMatch(source, /\/api\/analyze"/);
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
