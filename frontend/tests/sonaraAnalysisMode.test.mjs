import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createServer } from "vite";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
const apiClientPath = fileURLToPath(new URL("../src/apiClient.ts", import.meta.url));
const panelPath = fileURLToPath(new URL("../src/LibraryPanel.tsx", import.meta.url));
const settingsPath = fileURLToPath(new URL("../src/sonaraAnalysisSettings.ts", import.meta.url));
const stylesPath = fileURLToPath(new URL("../src/styles.css", import.meta.url));
const frontendRoot = fileURLToPath(new URL("../", import.meta.url));

const appSource = readFileSync(appPath, "utf8");
const apiClientSource = readFileSync(apiClientPath, "utf8");
const panelSource = readFileSync(panelPath, "utf8");
const settingsSource = existsSync(settingsPath) ? readFileSync(settingsPath, "utf8") : "";
const stylesSource = readFileSync(stylesPath, "utf8");

test("SONARA settings default to Direct Mode and keep an empty staging folder", () => {
  assert.match(settingsSource, /mode:\s*"direct"/);
  assert.match(settingsSource, /directBatchSize:\s*8/);
  assert.match(settingsSource, /folder:\s*""/);
  assert.match(settingsSource, /processes:\s*4/);
  assert.match(settingsSource, /threads:\s*4/);
  assert.match(settingsSource, /batchSize:\s*4/);
  assert.match(settingsSource, /stageSize:\s*32/);
});

test("SONARA settings persist as one localStorage object", () => {
  assert.match(settingsSource, /localStorage/);
  assert.match(settingsSource, /JSON\.parse/);
  assert.match(settingsSource, /JSON\.stringify/);
  assert.match(appSource, /loadSonaraAnalysisSettings/);
  assert.match(appSource, /saveSonaraAnalysisSettings/);
});

test("SONARA settings clamp persisted custom values to supported ranges", async () => {
  const server = await createServer({
    root: frontendRoot,
    server: { middlewareMode: true, hmr: false },
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const settingsModule = await server.ssrLoadModule("/src/sonaraAnalysisSettings.ts");
    const storage = {
      getItem: () => JSON.stringify({
        mode: "staged",
        directBatchSize: 99,
        staged: {
          folder: "C:\\TracksTemp",
          processes: 0,
          threads: 99,
          batchSize: 0,
          stageSize: 999,
        },
      }),
    };

    assert.deepEqual(settingsModule.loadSonaraAnalysisSettings(storage), {
      mode: "staged",
      directBatchSize: 16,
      staged: {
        folder: "C:\\TracksTemp",
        processes: 1,
        threads: 64,
        batchSize: 1,
        stageSize: 512,
      },
    });

    const localStorageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
    try {
      Object.defineProperty(globalThis, "localStorage", {
        configurable: true,
        get: () => { throw new Error("storage blocked"); },
      });
      assert.deepEqual(
        settingsModule.loadSonaraAnalysisSettings(),
        settingsModule.defaultSonaraAnalysisSettings,
      );
      assert.doesNotThrow(() => settingsModule.saveSonaraAnalysisSettings(
        settingsModule.defaultSonaraAnalysisSettings,
      ));
    } finally {
      if (localStorageDescriptor) {
        Object.defineProperty(globalThis, "localStorage", localStorageDescriptor);
      } else {
        delete globalThis.localStorage;
      }
    }
  } finally {
    await server.close();
  }
});

test("Staged Mode requires a chosen folder before analysis starts", () => {
  assert.match(appSource, /sonaraSettings\.mode === "staged"/);
  assert.match(appSource, /sonaraSettings\.staged\.folder\.trim\(\)/);
  assert.match(appSource, /Выберите папку staging/);
});

test("analysis API carries separate Direct and Staged SONARA settings", () => {
  assert.match(apiClientSource, /direct_batch_size:\s*number/);
  assert.match(apiClientSource, /processes:\s*number/);
  assert.match(apiClientSource, /threads:\s*number/);
  assert.match(apiClientSource, /stage_size:\s*number/);
  assert.match(appSource, /direct_batch_size:\s*sonaraSettings\.directBatchSize/);
  assert.match(appSource, /stage_size:\s*sonaraSettings\.staged\.stageSize/);
});

test("SONARA panel exposes mode, read-only folder picker, and editable staged values", () => {
  assert.match(panelSource, />Direct</);
  assert.match(panelSource, />Staged</);
  assert.match(panelSource, /staging-folder-picker-button/);
  assert.match(panelSource, /readOnly/);
  assert.match(panelSource, /sonaraSettings\.mode !== "staged"/);
  for (const label of ["Processes", "Threads", "BatchSize", "StageSize"]) {
    assert.match(panelSource, new RegExp(`label="${label}"`));
  }
});

test("SONARA mode buttons fill the available mode-control width", () => {
  const segmentedRule = stylesSource.match(/\.segmented\.sonara-mode-segmented\s*{([\s\S]*?)}/)?.[1] || "";
  const buttonRule = stylesSource.match(/\.sonara-mode-button\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(segmentedRule, /width:\s*100%;/);
  assert.match(buttonRule, /width:\s*100%;/);
});
