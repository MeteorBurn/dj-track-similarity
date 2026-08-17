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
