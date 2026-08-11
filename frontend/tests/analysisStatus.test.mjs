import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

test("pipeline child analysis status is not rendered as a duplicate standalone job", async () => {
  const server = await createServer({
    server: { middlewareMode: true },
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const { LibraryPanel } = await server.ssrLoadModule("/src/LibraryPanel.tsx");
    const noop = () => undefined;
    const analysisJob = {
      job_id: "analysis-child",
      state: "running",
      adapter_name: "sonara",
      device_requested: "auto",
      total: 10,
      processed: 4,
      analyzed: 4,
      failed: 0,
      errors: [],
      events: [],
      cancel_requested: false,
      workers: 1,
    };
    const pipelineJob = {
      job_id: "pipeline",
      state: "running",
      order: ["sonara", "ml"],
      stages: {
        sonara: { name: "sonara", state: "running", child_job_id: "analysis-child" },
        ml: { name: "ml", state: "queued", child_job_id: null },
      },
      current_stage: "sonara",
      cancel_requested: false,
    };
    const markup = renderToStaticMarkup(createElement(LibraryPanel, {
      databasePath: "library.sqlite",
      onChooseDatabase: noop,
      musicRoot: "music",
      onMusicRootChange: noop,
      busy: false,
      stageRunning: true,
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
      sonaraBatchSize: 1,
      onSonaraBatchSizeChange: noop,
      classifiers: [],
      analysisJob,
      pipelineJob,
      helpText: {},
      onChooseFolder: noop,
      onScan: noop,
      onRefreshTags: noop,
      onWriteMaestGenres: noop,
      onClearDatabase: noop,
      analysisCounts: {},
      selectedAnalysisModels: ["sonara"],
      onToggleAnalysisModel: noop,
      onAnalyzeSelected: noop,
      onResetAnalysis: noop,
      onResetClassifiers: noop,
    }));

    assert.equal((markup.match(/class="analysis-muted"/g) || []).length, 1);
    assert.doesNotMatch(markup, />Job running · 4\/10/);
    assert.match(markup, />Pipeline running · sonara:running → ml:queued/);
  } finally {
    await server.close();
  }
});
