import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const defaultSonaraSettings = {
  mode: "direct",
  directBatchSize: 8,
  bpmMin: 70,
  bpmMax: 180,
  staged: { folder: "", processes: 4, threads: 4, batchSize: 4, stageSize: 32 },
};

async function renderDialog(props) {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const { SonaraAnalysisSettingsDialog } = await server.ssrLoadModule("/src/SonaraAnalysisSettingsDialog.tsx");
    return renderToStaticMarkup(
      createElement(SonaraAnalysisSettingsDialog, {
        busy: false,
        stageRunning: false,
        sonaraSettings: defaultSonaraSettings,
        onSonaraSettingsChange: () => {},
        sonaraBpmRange: { bpmMin: 70, bpmMax: 180 },
        sonaraBpmRangeLocked: false,
        onSonaraBpmRangeChange: () => {},
        onChooseSonaraStagingFolder: () => {},
        onClose: () => {},
        ...props,
      })
    );
  } finally {
    await server.close();
  }
}

test("an analysed library shows the range as fixed and disables editing", async () => {
  const markup = await renderDialog({
    sonaraBpmRange: { bpmMin: 79, bpmMax: 192 },
    sonaraBpmRangeLocked: true,
  });

  assert.match(markup, /value="79"/);
  assert.match(markup, /value="192"/);
  assert.match(markup, /сбросьте анализ SONARA/);

  const bpmInputs = markup.match(/<input[^>]*type="number"[^>]*value="(?:79|192)"[^>]*>/g);
  assert.equal(bpmInputs?.length, 2, "both range inputs should render");
  for (const input of bpmInputs) {
    assert.match(input, /disabled/, `range input should be disabled when fixed: ${input}`);
  }
});

test("a running job disables the range even before the library fixes it", async () => {
  const markup = await renderDialog({ stageRunning: true });

  const bpmInputs = markup.match(/<input[^>]*type="number"[^>]*value="(?:70|180)"[^>]*>/g);
  assert.equal(bpmInputs?.length, 2);
  for (const input of bpmInputs) {
    assert.match(input, /disabled/);
  }
});
