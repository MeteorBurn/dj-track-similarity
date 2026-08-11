import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const trackPanelPath = fileURLToPath(new URL("../src/TrackPanel.tsx", import.meta.url));
const trackRowsPath = fileURLToPath(new URL("../src/TrackRows.tsx", import.meta.url));
const searchHookPath = fileURLToPath(new URL("../src/useSearchPlaylist.ts", import.meta.url));

test("library audio is controlled by explicit play state without a separate preview block", () => {
  const source = readFileSync(trackPanelPath, "utf8");
  const previewAudio = source.match(/<audio\b[\s\S]*?src=\{`\/media\/\$\{preview\.track_id\}`\}[\s\S]*?\/>/)?.[0] || "";

  assert.match(source, /audioRef/);
  assert.match(source, /playingTrackId === preview\.track_id/);
  assert.match(previewAudio, /hidden/);
  assert.match(previewAudio, /onPlay=/);
  assert.match(previewAudio, /onPause=/);
  assert.match(previewAudio, /onTimeUpdate=/);
  assert.match(previewAudio, /onDurationChange=/);
  assert.doesNotMatch(source, /library-preview-player/);
});

test("preview audio play events cannot re-enable a paused track", () => {
  const source = readFileSync(trackPanelPath, "utf8");
  const previewAudio = source.match(/<audio\b[\s\S]*?src=\{`\/media\/\$\{preview\.track_id\}`\}[\s\S]*?\/>/)?.[0] || "";

  assert.match(previewAudio, /onPlay=\{\(\) => \{\s*if \(playingTrackId === preview\.track_id\) onPreviewPlaying\(preview\.track_id\);\s*}}/);
});

test("track preview buttons toggle between play and pause icons", () => {
  const rowsSource = readFileSync(trackRowsPath, "utf8");
  const hookSource = readFileSync(searchHookPath, "utf8");

  assert.match(rowsSource, /Pause/);
  assert.match(rowsSource, /playingTrackId === track\.track_id/);
  assert.match(rowsSource, /trackPreviewActive/);
  assert.match(hookSource, /function togglePreview/);
  assert.match(hookSource, /setPlayingTrackId\(null\)/);
});

test("currently playing library track has a dedicated row state", () => {
  const rowsSource = readFileSync(trackRowsPath, "utf8");
  const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

  assert.match(rowsSource, /className=\{`track-row \$\{trackPreviewActive \? "is-playing" : ""}`\}/);
  assert.match(rowsSource, /aria-current=\{trackPreviewActive \? "true" : undefined}/);
  assert.match(stylesSource, /\.track-row\.is-playing\s*\{[\s\S]*background:\s*var\(--accent-soft-bg\)/);
  assert.doesNotMatch(stylesSource.match(/\.track-row\.is-playing\s*\{([\s\S]*?)}/)?.[1] || "", /box-shadow/);
});

test("selected library preview exposes seek and duration inside its row", () => {
  const panelSource = readFileSync(trackPanelPath, "utf8");
  const rowsSource = readFileSync(trackRowsPath, "utf8");
  const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  const titleCellStyles = stylesSource.match(/\.track-title-cell\.with-playback\s*\{([\s\S]*?)}/)?.[1] || "";
  const playbackStyles = stylesSource.match(/\.track-row-playback\s*\{([\s\S]*?)}/)?.[1] || "";
  const rangeStyles = stylesSource.match(/\.track-row-playback input\[type="range"\]\s*\{([\s\S]*?)}/)?.[1] || "";

  assert.match(panelSource, /function seekPreview\(track: Track, seconds: number\)/);
  assert.match(panelSource, /audio\.currentTime =/);
  assert.match(rowsSource, /className="track-row-playback"/);
  assert.match(rowsSource, /type="range"/);
  assert.match(rowsSource, /formatPlaybackTime\(previewCurrentTime\)/);
  assert.match(rowsSource, /formatPlaybackTime\(previewDuration\)/);
  assert.match(rowsSource, /track-title-cell \$\{trackPreviewSelected \? "with-playback" : ""}/);
  assert.match(titleCellStyles, /align-items:\s*center/);
  assert.match(titleCellStyles, /grid-template-columns:\s*minmax\(0, 0\.7fr\) minmax\(0, 1fr\)/);
  assert.match(playbackStyles, /grid-template-columns:\s*minmax\(0, 1fr\) max-content/);
  assert.match(playbackStyles, /max-width:\s*100%/);
  assert.match(rangeStyles, /min-width:\s*0/);
  assert.match(rangeStyles, /width:\s*100%/);
});
