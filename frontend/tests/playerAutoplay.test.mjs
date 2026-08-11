import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
const trackRowsPath = fileURLToPath(new URL("../src/TrackRows.tsx", import.meta.url));
const searchHookPath = fileURLToPath(new URL("../src/useSearchPlaylist.ts", import.meta.url));

test("one global audio element is controlled by explicit play state", () => {
  const source = readFileSync(appPath, "utf8");
  const previewAudio = source.match(/<audio\b[\s\S]*?src=\{`\/media\/\$\{preview\.track_id\}`\}[\s\S]*?\/>/)?.[0] || "";

  assert.match(source, /previewAudioRef/);
  assert.match(source, /playingTrackId === preview\.track_id/);
  assert.match(previewAudio, /hidden/);
  assert.match(previewAudio, /onPlay=/);
  assert.match(previewAudio, /onPause=/);
  assert.match(previewAudio, /onTimeUpdate=/);
  assert.match(previewAudio, /onDurationChange=/);
  assert.doesNotMatch(source, /library-preview-player/);
});

test("preview audio play events cannot re-enable a paused track", () => {
  const source = readFileSync(appPath, "utf8");
  const previewAudio = source.match(/<audio\b[\s\S]*?src=\{`\/media\/\$\{preview\.track_id\}`\}[\s\S]*?\/>/)?.[0] || "";

  assert.match(previewAudio, /onPlay=\{\(\) => \{\s*if \(playingTrackId === preview\.track_id\) markPreviewPlaying\(preview\.track_id\);\s*}}/);
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

  assert.match(rowsSource, /className=\{`track-row \$\{trackPreviewActive \? "is-playing" : ""} \$\{trackPreviewSelected \? "has-playback" : ""}`\}/);
  assert.match(rowsSource, /aria-current=\{trackPreviewActive \? "true" : undefined}/);
  assert.match(stylesSource, /\.track-row\.is-playing\s*\{[\s\S]*background:\s*var\(--accent-soft-bg\)/);
  assert.doesNotMatch(stylesSource.match(/\.track-row\.is-playing\s*\{([\s\S]*?)}/)?.[1] || "", /box-shadow/);
});

test("selected library preview exposes seek and duration next to its play button", () => {
  const appSource = readFileSync(appPath, "utf8");
  const rowsSource = readFileSync(trackRowsPath, "utf8");
  const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  const activeRowStyles = stylesSource.match(/\.track-row\.has-playback\s*\{([\s\S]*?)}/)?.[1] || "";
  const playbackStyles = stylesSource.match(/\.track-row-playback\s*\{([\s\S]*?)}/)?.[1] || "";
  const rangeStyles = stylesSource.match(/\.track-row-playback input\[type="range"\]\s*\{([\s\S]*?)}/)?.[1] || "";

  assert.match(appSource, /function seekPreview\(track: Track, seconds: number\)/);
  assert.match(appSource, /audio\.currentTime =/);
  assert.match(rowsSource, /track-row-playback/);
  assert.match(rowsSource, /type="range"/);
  assert.match(rowsSource, /formatPlaybackTime\(currentTime\)/);
  assert.match(rowsSource, /formatPlaybackTime\(duration\)/);
  assert.match(rowsSource, /trackPreviewSelected \? \(\s*<PlaybackSeekControl/);
  assert.match(activeRowStyles, /grid-template-columns:\s*26px 34px minmax\(92px, 0\.8fr\) minmax\(0, 1fr\)/);
  assert.match(playbackStyles, /grid-template-columns:\s*minmax\(0, 1fr\) max-content/);
  assert.match(playbackStyles, /max-width:\s*100%/);
  assert.match(rangeStyles, /min-width:\s*0/);
  assert.match(rangeStyles, /width:\s*100%/);
});

test("candidate preview replaces similarity meter and score with a seek control", () => {
  const rowsSource = readFileSync(trackRowsPath, "utf8");
  const resultRowSource = rowsSource.match(/export function ResultRow[\s\S]*?\n}\n\nfunction scoreBreakdownTitle/)?.[0] || "";
  const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

  assert.match(resultRowSource, /const trackPreviewSelected = previewTrackId === track\.track_id/);
  assert.match(resultRowSource, /\{trackPreviewSelected \? \([\s\S]*?className="result-row-playback"[\s\S]*?\) : \([\s\S]*?<meter[\s\S]*?similarity-score/);
  assert.match(stylesSource, /\.result-row-playback\s*\{[\s\S]*?grid-column:\s*span 2/);
  assert.match(stylesSource, /\.result-row-playback\s*\{[\s\S]*?grid-column:\s*2 \/ -1;[\s\S]*?grid-row:\s*2;/);
});
