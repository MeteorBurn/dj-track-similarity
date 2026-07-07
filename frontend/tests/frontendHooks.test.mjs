import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));

test("App delegates library, search playlist, and activity state to hooks", () => {
  const appSource = readFileSync(join(srcDir, "App.tsx"), "utf8");

  assert.match(appSource, /useLibraryState/);
  assert.match(appSource, /useSearchPlaylist/);
  assert.match(appSource, /useActivityLog/);
  assert.match(appSource, /useConfirmation/);
  assert.doesNotMatch(appSource, /const \[tracks, setTracks\] = useState/);
  assert.doesNotMatch(appSource, /const \[playlist, setPlaylist\] = useState/);
  assert.doesNotMatch(appSource, /const \[activityLog, setActivityLog\] = useState/);
  assert.doesNotMatch(appSource, /const \[confirmation, setConfirmation\] = useState/);
});

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

  assert.match(source, /const \[searchMode, setSearchMode\]/);
  assert.match(source, /api\.tracks\(\{[\s\S]*searchMode/);
  assert.match(source, /api\.filteredTracks\(\{[\s\S]*searchMode/);
});

test("search playlist hook owns seed and playlist state", () => {
  const hookPath = join(srcDir, "useSearchPlaylist.ts");
  assert.equal(existsSync(hookPath), true, "useSearchPlaylist.ts exists");
  const source = readFileSync(hookPath, "utf8");

  assert.match(source, /const \[seeds, setSeeds\]/);
  assert.match(source, /const \[playlist, setPlaylist\]/);
  assert.match(source, /function addSeed/);
  assert.match(source, /function togglePlaylist/);
});
