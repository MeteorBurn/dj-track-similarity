import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
const trackPanelPath = fileURLToPath(new URL("../src/TrackPanel.tsx", import.meta.url));

test("add-visible button adds the loaded page without fetching filtered tracks", () => {
  const source = readFileSync(appPath, "utf8");
  const handler = source.match(/(?:async )?function addVisibleTracksToPlaylist\(\) \{[\s\S]*?\n  \}/)?.[0] || "";

  assert.match(handler, /appendVisibleTracksToPlaylist\(playlist, orderedTracks\)/);
  assert.doesNotMatch(handler, /filteredTracks\(/);
  assert.doesNotMatch(handler, /await /);
});

test("add-visible button describes the current loaded page", () => {
  const source = readFileSync(trackPanelPath, "utf8");

  assert.match(source, /Добавить треки текущей страницы в сет/);
  assert.doesNotMatch(source, /Добавить все отфильтрованные треки в сет/);
});
