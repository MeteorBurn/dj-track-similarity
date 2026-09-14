import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
const trackRowsPath = fileURLToPath(new URL("../src/TrackRows.tsx", import.meta.url));
const searchHookPath = fileURLToPath(new URL("../src/useSearchPlaylist.ts", import.meta.url));

function trackStatsHarness() {
  const react = {
    useState: (initial) => [initial, () => {}],
    useEffect: (effect) => effect(),
  };
  const api = { track: () => assert.fail("Player metadata must come directly from the supplied track") };
  const modules = new Map();
  function load(name) {
    if (name === "react") return react;
    if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
    if (name === "lucide-react") return {};
    if (name === "./api") return { api };
    if (name === "./previewPosition") return {
      usePreviewPosition: () => ({}), previewPositionForTrack: () => ({ currentTime: 0, duration: 0 }),
    };
    if (modules.has(name)) return modules.get(name);
    const extension = ["./PlayerDock", "./TrackRows"].includes(name) ? "tsx" : "ts";
    const module = { exports: {} }; modules.set(name, module.exports);
    vm.runInNewContext(ts.transpileModule(readFileSync(new URL(`../src/${name.slice(2)}.${extension}`, import.meta.url), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
    }).outputText, { module, exports: module.exports, require: load });
    return module.exports;
  }
  const { PlayerDock } = load("./PlayerDock");
  const { TrackList } = load("./TrackRows");
  function stats(tree) {
    const values = {};
    function visit(node) {
      const children = node?.props?.children;
      if (Array.isArray(children) && children[0]?.type === "strong" && children[1]?.type === "span") {
        values[children[1].props.children] = children[0].props.children;
      }
      if (node?.props?.className === "library-track-bpm") values.BPM = children;
      if (node?.props?.className === "library-track-key") values.KEY = children;
      if (node?.props?.className === "player-track-info") values.fileInfo = children.find((child) => child?.type === "span")?.props.children;
      if (node?.props?.className === "library-track-meta") values.fileInfo = children;
      for (const child of Array.isArray(children) ? children.flat(Infinity) : [children]) {
        if (child && typeof child === "object") visit(child);
      }
    }
    visit(tree);
    return values;
  }
  return {
    player: (preview) => stats(PlayerDock({ preview, playing: false, audioRef: { current: null }, onToggle() {}, onSeek() {} })),
    library: (track) => stats(TrackList({ tracks: [track], seedSet: new Set(), playlistSet: new Set(), playingTrackId: null, previewTrackId: null,
      onSeed() {}, onTogglePlaylist() {}, onPreview() {}, onSeekPreview() {}, onDetails() {} })),
  };
}

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

test("ending a library preview starts the next visible track", () => {
  const source = readFileSync(appPath, "utf8");
  const previewAudio = source.match(/<audio\b[\s\S]*?src=\{`\/media\/\$\{preview\.track_id\}`\}[\s\S]*?\/>/)?.[0] || "";

  assert.match(source, /function handleLibraryPreviewEnded\(track: \w+\)/);
  assert.match(previewAudio, /onEnded=\{\(\) => \{\s*handleLibraryPreviewEnded\(preview\);\s*}}/);
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

test("player and library metadata come directly from track summaries", () => {
  const h = trackStatsHarness();
  const track = {
    track_id: 1, catalog_uuid: "A", track_uuid: "a1", file_path: "a.wav", tag_bpm: 99, tag_key: "tag-key",
    sonara_bpm: 128.5, sonara_key_camelot: "8B",
    sonara_core: { detected_bpm: 64.25, detected_key_name: "C minor", detected_key_camelot: "5A" },
    album: "album-from-tags",
    file_size_bytes: 37 * 1024 * 1024, audio_format: "flac", sample_rate_hz: 48000, bit_rate_bps: 320000, bit_depth: 24,
    file: { file_size_bytes: 1024 * 1024, audio_format: "mp3", sample_rate_hz: 96000, bit_rate_bps: 128000, bit_depth: 16 },
  };
  const absent = (values) => {
    assert.ok(Number.isNaN(Number(values.BPM)), "no file-tag or nested-detail BPM fallback");
    assert.notEqual(values.KEY, track.sonara_key_camelot);
    assert.notEqual(values.KEY, track.sonara_core.detected_key_name);
    assert.notEqual(values.KEY, track.sonara_core.detected_key_camelot);
    assert.notEqual(values.KEY, track.tag_key);
  };
  for (const render of [h.player, h.library]) {
    const values = render(track);
    assert.equal(Number(values.BPM), track.sonara_bpm);
    assert.equal(values.KEY, track.sonara_key_camelot);
    absent(render({ ...track, sonara_bpm: null, sonara_key_camelot: null }));
  }
  absent(h.player({ track_id: track.track_id }));
  absent(h.player(null));
  const fileInfo = h.player(track).fileInfo;
  assert.equal(typeof fileInfo, "string", "player technical info is present");
  assert.match(fileInfo, /\b37(?:\.0+)?\s*MB\b/);
  assert.match(fileInfo, /\bflac\b/i);
  assert.doesNotMatch(fileInfo, /\b(?:mp3|wav)\b/i);
  assert.match(fileInfo, /\b48(?:\.0+)?\s*kHz\b/);
  assert.match(fileInfo, /\b320\s*kbps\b/);
  assert.match(fileInfo, /\b24[-\s]*bit\b/);
  const libraryInfo = h.library(track).fileInfo;
  assert.equal(typeof libraryInfo, "string", "library technical info is present");
  assert.equal(libraryInfo, fileInfo);
  for (const preview of [{ ...track, audio_format: null, sample_rate_hz: null, bit_rate_bps: null, bit_depth: null }, { track_id: track.track_id }, null]) {
    const info = h.player(preview).fileInfo;
    assert.equal(typeof info, "string", "empty player technical info is present");
    assert.doesNotMatch(info, /flac|mp3|wav|kHz|kbps|bit|NaN|undefined/i);
    if (preview && "file_path" in preview) {
      assert.match(info, /\b37(?:\.0+)?\s*MB\b/);
      const libraryInfo = h.library(preview).fileInfo;
      assert.equal(typeof libraryInfo, "string", "nullable library technical info is present");
      assert.equal(libraryInfo, info);
    } else assert.doesNotMatch(info, /MB/);
  }
});

test("selected library preview exposes seek and duration next to its play button", () => {
  const appSource = readFileSync(appPath, "utf8");
  const rowsSource = readFileSync(trackRowsPath, "utf8");
  const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  const activeRowStyles = stylesSource.match(/\.track-row\.has-playback\s*\{([\s\S]*?)}/)?.[1] || "";
  const playbackStyles = stylesSource.match(/\.track-row-playback\s*\{([\s\S]*?)}/)?.[1] || "";
  const rangeStyles = stylesSource.match(/\.track-row-playback input\[type="range"\]\s*\{([\s\S]*?)}/)?.[1] || "";

  assert.match(appSource, /function seekPreview\(track: \w+, seconds: number\)/);
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
