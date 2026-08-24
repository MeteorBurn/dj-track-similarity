# Graph Report - frontend  (2026-08-21)

## Corpus Check
- 67 files · ~48,273 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 647 nodes · 1244 edges · 47 communities (31 shown, 16 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 31 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7d446d88`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- jobUi.tsx
- TrackMetadataDialog.tsx
- apiClient.ts
- SearchPlaylistPanel.tsx
- useLibraryState.ts
- package.json
- LibraryPanel.tsx
- ReferenceComparePanel.tsx
- compilerOptions
- tooltipLayer.tsx
- metadataReference.test.mjs
- sonaraAnalysisMode.test.mjs
- buttonClasses.test.mjs
- libraryView.test.mjs
- searchPlaylistLayout.test.mjs
- themeMode.test.mjs
- apiContract.test.mjs
- App
- playerAutoplay.test.mjs
- referenceCompareContract.test.mjs
- sonaraSearchControls.test.mjs
- appHeaderMeta.test.mjs
- textPromptPresets.ts
- helpText.test.mjs
- libraryRendering.test.mjs
- sonaraDisplay.test.mjs
- tooltipPosition.test.mjs
- frontendHooks.test.mjs
- jobUi.test.mjs
- sonaraFeatureLabels.test.mjs
- api.ts
- App.tsx
- TrackRows.tsx
- mlAnalysisSettings.ts
- sonaraAnalysisSettings.ts
- dialogs.tsx
- ScanImportDialog.tsx
- useSearchPlaylist.ts
- scanImportDialog.test.mjs
- useConfirmation
- playlistAddHandler.test.mjs
- textPromptPresets.test.mjs
- mlAnalysisSettings.test.mjs

## God Nodes (most connected - your core abstractions)
1. `App()` - 82 edges
2. `appendActivity()` - 34 edges
3. `displayTrack()` - 24 edges
4. `SearchPlaylistPanel()` - 23 edges
5. `run()` - 21 edges
6. `useLibraryState()` - 18 edges
7. `compilerOptions` - 16 edges
8. `refreshLibrary()` - 14 edges
9. `metadataDialogModel()` - 12 edges
10. `formatSonaraCoreValue()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `copyFileName()` --indirect_call--> `track()`  [INFERRED]
  src/TrackMetadataDialog.tsx → tests/libraryLoading.test.mjs
- `App()` --calls--> `requestConfirmation()`  [EXTRACTED]
  src/App.tsx → src/useConfirmation.ts
- `App()` --calls--> `analysisJobRequest()`  [EXTRACTED]
  src/App.tsx → src/jobUi.tsx
- `App()` --calls--> `stageIndicatorLabel()`  [EXTRACTED]
  src/App.tsx → src/jobUi.tsx
- `App()` --calls--> `loadMLAnalysisSettings()`  [EXTRACTED]
  src/App.tsx → src/mlAnalysisSettings.ts

## Import Cycles
- 2-file cycle: `src/api.ts -> src/apiClient.ts -> src/api.ts`

## Communities (47 total, 16 thin omitted)

### Community 0 - "jobUi.tsx"
Cohesion: 0.10
Nodes (28): ACTIVE_JOB_STATES, ActivityEvent, analysisJobRequest(), AnalysisProcessStatus(), analysisRuntimeLabel(), AUDIO_MODELS, calculateEta(), calculateProgressPercent() (+20 more)

### Community 1 - "TrackMetadataDialog.tsx"
Cohesion: 0.06
Nodes (56): SonaraCore, formatMaestGenreLabel(), hasMaestSyncopatedRhythm(), SYNCOPATED_RHYTHM_LABEL, candidateRank(), copyTextToClipboard(), CoreFeature, CoreFeatureDescriptor (+48 more)

### Community 2 - "apiClient.ts"
Cohesion: 0.07
Nodes (29): AnalysisPipelineRequest, AnalysisPipelineStatus, AnalysisResetResult, ClassifierResetResult, DatabaseClearResult, EmbeddingRandomTrackPayload, ReferenceComparePayload, ScanRequest (+21 more)

### Community 3 - "SearchPlaylistPanel.tsx"
Cohesion: 0.08
Nodes (38): EmbeddingSource, PromotedClassifier, classifierIsAvailable(), classifierProfileStatus(), classifierScoringBlockedReason(), filterAvailableClassifierValues(), formatClassifierScoredTracks(), orderPromotedClassifiers() (+30 more)

### Community 4 - "useLibraryState.ts"
Cohesion: 0.10
Nodes (40): LibrarySummary, Track, createLibraryLoadCoordinator(), LibraryLoadCoordinator, LibraryLoadTicket, libraryPageSize, libraryRequestKey(), LibraryRequestKeyParts (+32 more)

### Community 5 - "package.json"
Cohesion: 0.07
Nodes (29): lucide-react, dependencies, lucide-react, react, react-dom, typescript, vite, @vitejs/plugin-react (+21 more)

### Community 6 - "LibraryPanel.tsx"
Cohesion: 0.18
Nodes (11): AnalysisSelection, analysisSelectionOrder, analysisStartBlockedByMissingSonara(), audioAnalysisModelOrder, defaultAnalysisSelections, mlAnalysisModelOrder, AnalysisModel, DeviceMode (+3 more)

### Community 7 - "ReferenceComparePanel.tsx"
Cohesion: 0.16
Nodes (21): ReferenceCompareGroup, ReferenceCompareModel, ReferenceCompareResponse, ReferenceCompareVerdict, TrackIdentity, api, normalizeLimit(), orderedReferenceCompareGroups() (+13 more)

### Community 8 - "compilerOptions"
Cohesion: 0.09
Nodes (22): DOM, DOM.Iterable, ES2022, src, tests/**/*.ts, compilerOptions, allowJs, allowSyntheticDefaultImports (+14 more)

### Community 9 - "tooltipLayer.tsx"
Cohesion: 0.26
Nodes (10): clamp(), placeTooltip(), RectLike, SizeLike, TooltipPlacement, TooltipPosition, ActiveTooltip, rectToPlainObject() (+2 more)

### Community 10 - "metadataReference.test.mjs"
Cohesion: 0.15
Nodes (9): detail(), metadataDialog, metadataDialogUi, referenceCompare, sonaraFeatures(), srcDir, summary(), syncopatedRhythm (+1 more)

### Community 11 - "sonaraAnalysisMode.test.mjs"
Cohesion: 0.18
Nodes (10): apiClientPath, apiClientSource, apiPath, apiSource, appPath, appSource, frontendRoot, panelPath (+2 more)

### Community 13 - "libraryView.test.mjs"
Cohesion: 0.62
Nodes (6): loadExportViewModule(), loadLibraryViewModule(), loadPlaylistViewModule(), loadSyncopatedRhythmModule(), transpile(), writeTranspiledModule()

### Community 14 - "searchPlaylistLayout.test.mjs"
Cohesion: 0.25
Nodes (5): appSource, embeddingTabSource, panelSource, styles, trackPanelSource

### Community 17 - "App"
Cohesion: 0.07
Nodes (66): App(), addVisibleTracksToPlaylist(), adoptClassifierProfiles(), beginGenericSearchRequest(), cancelGenericSearchRequest(), cancelTrackDetailRequest(), commitGenericSearchResults(), finishGenericSearchRequest() (+58 more)

### Community 18 - "playerAutoplay.test.mjs"
Cohesion: 0.50
Nodes (3): appPath, searchHookPath, trackRowsPath

### Community 20 - "sonaraSearchControls.test.mjs"
Cohesion: 0.50
Nodes (3): embeddingTabSource, panelSource, stylesSource

### Community 22 - "textPromptPresets.ts"
Cohesion: 0.11
Nodes (26): applyPromptPresets(), changeTextEmbeddingFamily(), togglePromptPreset(), ClapSearchTab(), axisByKey(), ComposedPromptBanks, composePromptBanks(), defaultNegativeWeight (+18 more)

### Community 34 - "api.ts"
Cohesion: 0.08
Nodes (24): AnalysisCoverage, ClassifierScoreDetail, ClassifierScoreSummary, DatabaseSelection, EmbeddingSearchPayload, EmbeddingSummary, FileTags, FileTechnical (+16 more)

### Community 35 - "App.tsx"
Cohesion: 0.11
Nodes (17): defaultNotice, DeviceMode, GenericSearchResultState, genreTagJobSummary(), GuardedRequestTicket, Notice, openRhythmLabWindow(), ResetAdapter (+9 more)

### Community 36 - "TrackRows.tsx"
Cohesion: 0.22
Nodes (13): emptyPreviewPosition, listeners, PreviewPosition, previewPositionForTrack(), readPreviewPosition(), subscribePreviewPosition(), usePreviewPosition(), contrastParts() (+5 more)

### Community 37 - "mlAnalysisSettings.ts"
Cohesion: 0.18
Nodes (12): boundedInteger(), cloneDefaults(), defaultMLAnalysisSettings, loadMLAnalysisSettings(), MLAnalysisMode, MLAnalysisSettings, mlAnalysisSettingsStorageKey, objectValue() (+4 more)

### Community 38 - "sonaraAnalysisSettings.ts"
Cohesion: 0.19
Nodes (11): boundedInteger(), cloneDefaults(), defaultSonaraAnalysisSettings, loadSonaraAnalysisSettings(), objectValue(), saveSonaraAnalysisSettings(), SonaraAnalysisMode, SonaraAnalysisSettings (+3 more)

### Community 39 - "dialogs.tsx"
Cohesion: 0.20
Nodes (8): AnalysisJobStatus, DatabaseValidationJobStatus, GenreTagJobStatus, ScanStats, ConfirmationRequest, ConfirmationDialog(), LogFrameDialog(), ConfirmationState

### Community 40 - "ScanImportDialog.tsx"
Cohesion: 0.38
Nodes (6): boundValue(), defaultScanImportSettings(), scanFormats, ScanImportDialog(), ScanImportRequest, ScanImportSettings

### Community 41 - "useSearchPlaylist.ts"
Cohesion: 0.40
Nodes (4): SearchResult, TrackDetail, TrackSummary, ActivityAppender

### Community 42 - "scanImportDialog.test.mjs"
Cohesion: 0.40
Nodes (4): appPath, dialogPath, panelPath, srcDir

## Knowledge Gaps
- **180 isolated node(s):** `name`, `version`, `private`, `type`, `dev` (+175 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `App()` connect `App` to `jobUi.tsx`, `App.tsx`, `useLibraryState.ts`, `mlAnalysisSettings.ts`, `sonaraAnalysisSettings.ts`, `tooltipLayer.tsx`, `useConfirmation`, `textPromptPresets.ts`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Why does `displayTrack()` connect `App` to `jobUi.tsx`, `TrackMetadataDialog.tsx`, `SearchPlaylistPanel.tsx`, `App.tsx`, `TrackRows.tsx`, `useLibraryState.ts`, `ReferenceComparePanel.tsx`, `useSearchPlaylist.ts`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Why does `useLibraryState()` connect `useLibraryState.ts` to `App`, `App.tsx`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **What connects `name`, `version`, `private` to the rest of the system?**
  _180 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `jobUi.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.10084033613445378 - nodes in this community are weakly interconnected._
- **Should `TrackMetadataDialog.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.059395801331285206 - nodes in this community are weakly interconnected._
- **Should `apiClient.ts` be split into smaller, more focused modules?**
  _Cohesion score 0.06666666666666667 - nodes in this community are weakly interconnected._