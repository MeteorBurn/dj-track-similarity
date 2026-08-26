import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

async function renderDialog(props) {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const { ScanImportDialog } = await server.ssrLoadModule("/src/ScanImportDialog.tsx");
    return renderToStaticMarkup(
      createElement(ScanImportDialog, {
        busy: false,
        stageRunning: false,
        maxWorkers: 16,
        sonaraBpmRange: { bpmMin: 70, bpmMax: 180 },
        sonaraBpmRangeLocked: false,
        onSonaraBpmRangeChange: () => {},
        onChooseFolder: async () => null,
        onClose: () => {},
        onStart: async () => {},
        ...props,
      })
    );
  } finally {
    await server.close();
  }
}

test("the scan dialog is where the analysis range is chosen", async () => {
  const markup = await renderDialog({});

  assert.match(markup, /Диапазон BPM для анализа SONARA/);
  assert.match(markup, /value="70"/);
  assert.match(markup, /value="180"/);
  assert.match(markup, /первый анализ SONARA закрепит его за всей базой/);
});

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

test("the dialog offers the tool presets and marks the active one", async () => {
  const markup = await renderDialog({ sonaraBpmRange: { bpmMin: 79, bpmMax: 192 } });

  for (const label of ["Rekordbox", "VirtualDJ", "Mixed In Key"]) {
    assert.ok(markup.includes(label), `preset ${label} should be offered`);
  }
  assert.match(markup, /aria-pressed="true"[^>]*>Mixed In Key</);
  assert.match(markup, /79–192/);
});

test("a range outside the presets reads as a custom range", async () => {
  const markup = await renderDialog({ sonaraBpmRange: { bpmMin: 90, bpmMax: 200 } });

  assert.match(markup, /Свой диапазон/);
  assert.doesNotMatch(markup, /aria-pressed="true"[^>]*>(Rekordbox|VirtualDJ|Mixed In Key)</);
});

test("a fixed library cannot switch preset", async () => {
  const markup = await renderDialog({
    sonaraBpmRange: { bpmMin: 70, bpmMax: 180 },
    sonaraBpmRangeLocked: true,
  });

  const chips = markup.match(/<button[^>]*scan-import-bpm-preset-chip[^>]*>/g);
  assert.equal(chips?.length, 3);
  for (const chip of chips) {
    assert.match(chip, /disabled/);
  }
});
