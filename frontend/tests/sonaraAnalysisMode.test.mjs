import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createServer } from "vite";

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));

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
      bpmMin: 70,
      bpmMax: 180,
      staged: {
        // A stored staging path is deliberately not restored: the folder
        // receives temporary copies and must be chosen for each session.
        folder: "",
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
