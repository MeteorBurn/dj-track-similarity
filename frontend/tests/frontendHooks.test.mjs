import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));

test("confirmation hook owns pending destructive action orchestration", () => {
  const hookPath = join(srcDir, "useConfirmation.ts");
  assert.equal(existsSync(hookPath), true, "useConfirmation.ts exists");
  const source = readFileSync(hookPath, "utf8");

  assert.match(source, /type ConfirmationState/);
  assert.match(source, /function requestConfirmation/);
  assert.match(source, /function confirmPendingAction/);
  assert.match(source, /function cancelConfirmation/);
});

test("library hook sends search mode through paged and filtered track requests", () => {
  const hookPath = join(srcDir, "useLibraryState.ts");
  assert.equal(existsSync(hookPath), true, "useLibraryState.ts exists");
  const source = readFileSync(hookPath, "utf8");

  assert.match(source, /const \[searchModeState, setSearchModeState\]/);
  assert.match(source, /api\.tracks\(\{[\s\S]*searchMode/);
  assert.match(source, /api\.filteredTracks\(\{[\s\S]*searchMode/);
});

test("library hook can adopt an explicit catalog scope before the database state rerender", () => {
  const hookPath = join(srcDir, "useLibraryState.ts");
  const source = readFileSync(hookPath, "utf8");
  const adopter = source.match(/const adoptDatabaseScope[\s\S]*?\}, \[\]\);/)?.[0] || "";

  assert.match(adopter, /databaseKeyRef\.current = nextDatabaseKey/);
  assert.match(adopter, /previousDatabaseScopeRef\.current = nextDatabaseKey/);
  assert.match(source, /canGoForward,\s*adoptDatabaseScope,\s*refreshLibrary/);
});

test("startup initialization is guarded against Strict Mode re-entry", () => {
  const appPath = join(srcDir, "App.tsx");
  const source = readFileSync(appPath, "utf8");
  const startupEffect = source.match(/useEffect\(\(\) => \{[\s\S]*?refreshRhythmLabStatus\(\);[\s\S]*?\}, \[\]\);/)?.[0] || "";

  assert.match(source, /const startupInitializationStarted = useRef\(false\)/);
  assert.match(startupEffect, /if \(startupInitializationStarted\.current\) return;/);
  assert.match(startupEffect, /startupInitializationStarted\.current = true;/);
});
