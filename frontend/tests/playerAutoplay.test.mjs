import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const trackPanelPath = fileURLToPath(new URL("../src/TrackPanel.tsx", import.meta.url));
const trackRowsPath = fileURLToPath(new URL("../src/TrackRows.tsx", import.meta.url));
const searchHookPath = fileURLToPath(new URL("../src/useSearchPlaylist.ts", import.meta.url));

test("library preview audio is controlled by explicit play state", () => {
  const source = readFileSync(trackPanelPath, "utf8");
  const previewAudio = source.match(/<audio\b[\s\S]*?src=\{`\/media\/\$\{preview\.id\}`\}[\s\S]*?\/>/)?.[0] || "";

  assert.match(source, /audioRef/);
  assert.match(source, /playingTrackId === preview\.id/);
  assert.match(previewAudio, /onPlay=/);
  assert.match(previewAudio, /onPause=/);
});

test("preview audio play events cannot re-enable a paused track", () => {
  const source = readFileSync(trackPanelPath, "utf8");
  const previewAudio = source.match(/<audio\b[\s\S]*?src=\{`\/media\/\$\{preview\.id\}`\}[\s\S]*?\/>/)?.[0] || "";

  assert.match(previewAudio, /onPlay=\{\(\) => \{\s*if \(playingTrackId === preview\.id\) onPreviewPlaying\(preview\.id\);\s*}}/);
});

test("track preview buttons toggle between play and pause icons", () => {
  const rowsSource = readFileSync(trackRowsPath, "utf8");
  const hookSource = readFileSync(searchHookPath, "utf8");

  assert.match(rowsSource, /Pause/);
  assert.match(rowsSource, /playingTrackId === track\.id/);
  assert.match(rowsSource, /trackPreviewActive/);
  assert.match(hookSource, /function togglePreview/);
  assert.match(hookSource, /setPlayingTrackId\(null\)/);
});
