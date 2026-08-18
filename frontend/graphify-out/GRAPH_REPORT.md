# Graph Report - frontend  (2026-08-16)

## Corpus Check
- 61 files · ~35,867 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 475 nodes · 862 edges · 34 communities (21 shown, 13 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 3 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a22fa988`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.tsx
- TrackMetadataDialog.tsx
- api.ts
- SearchPlaylistPanel.tsx
- useLibraryState.ts
- package.json
- sonaraAnalysisSettings.ts
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
- libraryLoading.test.mjs
- playerAutoplay.test.mjs
- referenceCompareContract.test.mjs
- sonaraSearchControls.test.mjs
- appHeaderMeta.test.mjs
- clapPrompt.test.mjs
- helpText.test.mjs
- libraryRendering.test.mjs
- sonaraDisplay.test.mjs
- tooltipPosition.test.mjs
- frontendHooks.test.mjs
- jobUi.test.mjs
- sonaraFeatureLabels.test.mjs

## God Nodes (most connected - your core abstractions)
1. `App()` - 29 edges
2. `displayTrack()` - 18 edges
3. `SearchPlaylistPanel()` - 16 edges
4. `compilerOptions` - 16 edges
5. `useLibraryState()` - 15 edges
6. `formatSonaraCoreValue()` - 14 edges
7. `metadataDialogModel()` - 12 edges
8. `Track` - 11 edges
9. `ReferenceComparePanel()` - 10 edges
10. `readableAudioData()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `App()` --calls--> `analysisStartBlockedByMissingSonara()`  [EXTRACTED]
  src/App.tsx → src/analysisSelection.ts
- `App()` --calls--> `classifierIsAvailable()`  [EXTRACTED]
  src/App.tsx → src/classifierCompatibility.ts
- `App()` --calls--> `classifierScoringBlockedReason()`  [EXTRACTED]
  src/App.tsx → src/classifierCompatibility.ts
- `App()` --calls--> `appendVisibleTracksToPlaylist()`  [EXTRACTED]
  src/App.tsx → src/libraryView.ts
- `App()` --calls--> `createRequestTokenGuard()`  [EXTRACTED]
  src/App.tsx → src/searchSurfaceState.ts

## Import Cycles
- 2-file cycle: `src/api.ts -> src/apiClient.ts -> src/api.ts`

## Communities (34 total, 13 thin omitted)

### Community 0 - "App.tsx"
Cohesion: 0.05
Nodes (55): AnalysisJobStatus, DatabaseValidationJobStatus, GenreTagJobStatus, ScanStats, App(), defaultNotice, DeviceMode, GenericSearchResultState (+47 more)

### Community 1 - "TrackMetadataDialog.tsx"
Cohesion: 0.08
Nodes (49): formatMaestGenreLabel(), hasMaestSyncopatedRhythm(), SYNCOPATED_RHYTHM_LABEL, candidateRank(), copyTextToClipboard(), CoreFeature, CoreFeatureGroup, formatAudioLength() (+41 more)

### Community 2 - "api.ts"
Cohesion: 0.06
Nodes (46): AnalysisCoverage, AnalysisPipelineStatus, AnalysisResetResult, ClassifierResetResult, ClassifierScoreDetail, ClassifierScoreSummary, DatabaseClearResult, DatabaseSelection (+38 more)

### Community 3 - "SearchPlaylistPanel.tsx"
Cohesion: 0.09
Nodes (37): EmbeddingSource, PromotedClassifier, SonaraMixerWeights, SonaraModifiers, SonaraSearchMode, ClapPromptPreset, ClapSearchTab(), classifierIsAvailable() (+29 more)

### Community 4 - "useLibraryState.ts"
Cohesion: 0.13
Nodes (33): Track, createLibraryLoadCoordinator(), LibraryLoadCoordinator, LibraryLoadTicket, libraryPageSize, libraryRequestKey(), LibraryRequestKeyParts, libraryTrackIdentityKey() (+25 more)

### Community 5 - "package.json"
Cohesion: 0.07
Nodes (29): lucide-react, dependencies, lucide-react, react, react-dom, typescript, vite, @vitejs/plugin-react (+21 more)

### Community 6 - "sonaraAnalysisSettings.ts"
Cohesion: 0.09
Nodes (22): AnalysisSelection, analysisSelectionOrder, analysisStartBlockedByMissingSonara(), audioAnalysisModelOrder, defaultAnalysisSelections, mlAnalysisModelOrder, AnalysisModel, DeviceMode (+14 more)

### Community 7 - "ReferenceComparePanel.tsx"
Cohesion: 0.12
Nodes (25): ReferenceCompareGroup, ReferenceCompareModel, ReferenceCompareResponse, ReferenceCompareVerdict, SearchResult, TrackIdentity, api, normalizeLimit() (+17 more)

### Community 8 - "compilerOptions"
Cohesion: 0.09
Nodes (22): DOM, DOM.Iterable, ES2022, src, tests/**/*.ts, compilerOptions, allowJs, allowSyntheticDefaultImports (+14 more)

### Community 9 - "tooltipLayer.tsx"
Cohesion: 0.26
Nodes (10): clamp(), placeTooltip(), RectLike, SizeLike, TooltipPlacement, TooltipPosition, ActiveTooltip, rectToPlainObject() (+2 more)

### Community 10 - "metadataReference.test.mjs"
Cohesion: 0.22
Nodes (8): detail(), metadataDialog, referenceCompare, sonaraFeatures(), srcDir, summary(), syncopatedRhythm, trackDisplay

### Community 11 - "sonaraAnalysisMode.test.mjs"
Cohesion: 0.18
Nodes (10): apiClientPath, apiClientSource, appPath, appSource, frontendRoot, panelPath, panelSource, settingsPath (+2 more)

### Community 13 - "libraryView.test.mjs"
Cohesion: 0.62
Nodes (6): loadExportViewModule(), loadLibraryViewModule(), loadPlaylistViewModule(), loadSyncopatedRhythmModule(), transpile(), writeTranspiledModule()

### Community 14 - "searchPlaylistLayout.test.mjs"
Cohesion: 0.29
Nodes (3): panelSource, styles, trackPanelSource

### Community 15 - "themeMode.test.mjs"
Cohesion: 0.29
Nodes (4): appSource, srcDir, styles, themePath

### Community 18 - "playerAutoplay.test.mjs"
Cohesion: 0.50
Nodes (3): appPath, searchHookPath, trackRowsPath

### Community 20 - "sonaraSearchControls.test.mjs"
Cohesion: 0.50
Nodes (3): embeddingTabSource, panelSource, stylesSource

## Knowledge Gaps
- **149 isolated node(s):** `name`, `version`, `private`, `type`, `dev` (+144 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `displayTrack()` connect `ReferenceComparePanel.tsx` to `App.tsx`, `TrackMetadataDialog.tsx`, `SearchPlaylistPanel.tsx`, `useLibraryState.ts`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Why does `useLibraryState()` connect `useLibraryState.ts` to `App.tsx`?**
  _High betweenness centrality (0.008) - this node is a cross-community bridge._
- **Why does `Track` connect `useLibraryState.ts` to `App.tsx`, `api.ts`, `SearchPlaylistPanel.tsx`, `ReferenceComparePanel.tsx`?**
  _High betweenness centrality (0.007) - this node is a cross-community bridge._
- **What connects `name`, `version`, `private` to the rest of the system?**
  _149 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.054773082942097026 - nodes in this community are weakly interconnected._
- **Should `TrackMetadataDialog.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.07619738751814223 - nodes in this community are weakly interconnected._
- **Should `api.ts` be split into smaller, more focused modules?**
  _Cohesion score 0.05697278911564626 - nodes in this community are weakly interconnected._