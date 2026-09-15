import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const noop = () => undefined;

function panelProps(overrides) {
  return {
    databasePath: "library.sqlite",
    onChooseDatabase: noop,
    musicRoot: "music",
    onMusicRootChange: noop,
    busy: false,
    stageRunning: false,
    canStartScan: true,
    hasTracks: true,
    maestGenreTrackCount: 0,
    scanWorkers: 1,
    maxScanWorkers: 4,
    adjustScanWorkers: noop,
    onScanWorkersChange: noop,
    analysisLimit: 0,
    onAnalysisLimitChange: noop,
    analysisDevice: "auto",
    onAnalysisDeviceChange: noop,
    analysisTrackBatchSize: 1,
    maxAnalysisTrackBatchSize: 4,
    adjustAnalysisTrackBatchSize: noop,
    onAnalysisTrackBatchSizeChange: noop,
    analysisInferenceBatchSize: 1,
    maxAnalysisInferenceBatchSize: 4,
    adjustAnalysisInferenceBatchSize: noop,
    onAnalysisInferenceBatchSizeChange: noop,
    sonaraSettings: {
      mode: "direct",
      directBatchSize: 8,
      staged: {
        folder: "",
        processes: 4,
        threads: 4,
        batchSize: 4,
        stageSize: 32,
      },
    },
    onSonaraSettingsChange: noop,
    mlSettings: {
      mode: "direct",
      staged: {
        folder: "",
        workers: 4,
        stageSize: 64,
      },
    },
    onMLSettingsChange: noop,
    onChooseSonaraStagingFolder: noop,
    onChooseMLStagingFolder: noop,
    helpText: {},
    onChooseFolder: noop,
    onScan: noop,
    onRefreshTags: noop,
    onWriteMaestGenres: noop,
    onClearDatabase: noop,
    libraryTrackCount: 0,
    analysisCounts: {},
    selectedStages: ["sonara"],
    onToggleStage: noop,
    scanRootSelected: true,
    onStart: noop,
    onResetAnalysis: noop,
    ...overrides,
  };
}

function validationButton(markup) {
  const button = markup.match(/<button[^>]*class="icon-button database-validation-button"[^>]*>/);
  assert.ok(button, "the database validation button is rendered");
  return button[0];
}

test("database validation stays disabled until the library has tracks", async () => {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const { LibraryPanel } = await server.ssrLoadModule("/src/LibraryPanel.tsx");
    const emptyLibrary = renderToStaticMarkup(createElement(LibraryPanel, panelProps({ hasTracks: false })));
    const loadedLibrary = renderToStaticMarkup(createElement(LibraryPanel, panelProps({ hasTracks: true })));

    assert.match(validationButton(emptyLibrary), /\sdisabled=""/);
    assert.doesNotMatch(validationButton(loadedLibrary), /\sdisabled=""/);
  } finally {
    await server.close();
  }
});
