import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createServer } from "vite";

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));

test("ML staging folder update changes only the ML staged settings", async () => {
  const server = await createServer({
    root: frontendRoot,
    server: { middlewareMode: true, hmr: false },
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const settingsModule = await server.ssrLoadModule("/src/mlAnalysisSettings.ts");
    const current = {
      mode: "staged",
      staged: {
        folder: "D:/old-staging",
        workers: 6,
        stageSize: 96,
      },
    };

    assert.deepEqual(
      settingsModule.withMLStagingFolder(current, "E:/ML-staging"),
      {
        mode: "staged",
        staged: {
          folder: "E:/ML-staging",
          workers: 6,
          stageSize: 96,
        },
      },
    );
  } finally {
    await server.close();
  }
});

test("the ML staging folder is not restored from a previous session", async () => {
  const server = await createServer({
    root: frontendRoot,
    server: { middlewareMode: true, hmr: false },
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const settings = await server.ssrLoadModule("/src/mlAnalysisSettings.ts");
    const stored = JSON.stringify({
      mode: "staged",
      staged: { folder: "C:\w", workers: 8, stageSize: 128 },
    });
    const store = new Map([[settings.mlAnalysisSettingsStorageKey, stored]]);
    const storage = {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => store.set(key, value),
    };

    const loaded = settings.loadMLAnalysisSettings(storage);
    assert.equal(loaded.staged.folder, "");
    assert.equal(loaded.staged.workers, 8, "other staged settings still persist");

    settings.saveMLAnalysisSettings(
      { ...loaded, staged: { ...loaded.staged, folder: "C:\TracksTemp" } },
      storage,
    );
    assert.equal(
      JSON.parse(store.get(settings.mlAnalysisSettingsStorageKey)).staged.folder,
      ""
    );
  } finally {
    await server.close();
  }
});
