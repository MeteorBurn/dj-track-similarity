import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "vite";

async function loadSettingsModule() {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
  });
  const module = await server.ssrLoadModule("/src/sonaraAnalysisSettings.ts");
  return { module, close: () => server.close() };
}

test("editing one bound keeps the pair at least an octave apart", async () => {
  const { module, close } = await loadSettingsModule();
  try {
    const { applySonaraBpmChange } = module;

    // A valid pair is left alone.
    assert.deepEqual(
      applySonaraBpmChange({ bpmMin: 70, bpmMax: 180 }, { bpmMin: 79 }),
      { bpmMin: 79, bpmMax: 180 }
    );

    // Raising the floor pushes the ceiling up rather than producing a range the
    // backend would reject.
    assert.deepEqual(
      applySonaraBpmChange({ bpmMin: 70, bpmMax: 180 }, { bpmMin: 100 }),
      { bpmMin: 100, bpmMax: 200 }
    );

    // Lowering the ceiling pulls the floor down for the same reason.
    assert.deepEqual(
      applySonaraBpmChange({ bpmMin: 79, bpmMax: 192 }, { bpmMax: 120 }),
      { bpmMin: 60, bpmMax: 120 }
    );
  } finally {
    await close();
  }
});

test("a stored range that breaks the octave rule falls back to the default", async () => {
  const { module, close } = await loadSettingsModule();
  try {
    const defaultRange = { bpmMin: module.defaultSonaraBpmMin, bpmMax: module.defaultSonaraBpmMax };
    assert.deepEqual(module.boundedBpmRange(120, 140), defaultRange);
    assert.deepEqual(module.boundedBpmRange(79, 192), { bpmMin: 79, bpmMax: 192 });
    assert.deepEqual(module.boundedBpmRange("nonsense", null), defaultRange);
  } finally {
    await close();
  }
});

test("every shipped preset is a range the library can actually store", async () => {
  const { module, close } = await loadSettingsModule();
  try {
    const { sonaraBpmPresets, boundedBpmRange } = module;
    assert.equal(sonaraBpmPresets.length, 3);

    for (const preset of sonaraBpmPresets) {
      // The stored Core row requires a full octave; a preset that breaks it
      // would be rejected by the database CHECK at analysis time.
      assert.ok(
        preset.bpmMax >= 2 * preset.bpmMin,
        `${preset.label} (${preset.bpmMin}-${preset.bpmMax}) does not span an octave`
      );
      assert.deepEqual(
        boundedBpmRange(preset.bpmMin, preset.bpmMax),
        { bpmMin: preset.bpmMin, bpmMax: preset.bpmMax },
        `${preset.label} should survive a storage round-trip`
      );
    }
  } finally {
    await close();
  }
});

test("a staging folder is never carried over from a previous session", async () => {
  const { module, close } = await loadSettingsModule();
  try {
    const stored = JSON.stringify({
      mode: "staged",
      staged: { folder: "C:\TracksTemp", processes: 4, threads: 4, batchSize: 4, stageSize: 32 },
    });
    const store = new Map([[module.sonaraAnalysisSettingsStorageKey, stored]]);
    const storage = {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => store.set(key, value),
    };

    // The folder holds temporary copies of source audio, so it is chosen per
    // session rather than restored.
    const loaded = module.loadSonaraAnalysisSettings(storage);
    assert.equal(loaded.staged.folder, "");
    assert.equal(loaded.staged.stageSize, 32, "other staged settings still persist");

    // Saving also clears the stale path, so it cannot reappear later.
    module.saveSonaraAnalysisSettings(
      { ...loaded, staged: { ...loaded.staged, folder: "C:\w" } },
      storage,
    );
    assert.equal(
      JSON.parse(store.get(module.sonaraAnalysisSettingsStorageKey)).staged.folder,
      ""
    );
  } finally {
    await close();
  }
});
