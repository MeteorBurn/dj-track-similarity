import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const dialogPath = fileURLToPath(new URL("../src/TrackMetadataDialog.tsx", import.meta.url));
const stylesPath = fileURLToPath(new URL("../src/styles.css", import.meta.url));

function cssRule(source, selector) {
  return source.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{[^}]*\\}`))?.[0] || "";
}

test("spectral centroid uses the canonical display label", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /spectral_centroid_mean:\s*"Spectral Centroid"/);
  assert.doesNotMatch(source, /spectral_centroid_mean:\s*"Brightness"/);
});

test("sonara mean feature display labels omit mean while keeping database keys", () => {
  const source = readFileSync(dialogPath, "utf8");
  const labelsSource = source.match(/const sonaraFeatureLabels:[\s\S]*?};/)?.[0] || "";
  const labelEntries = [...labelsSource.matchAll(/^\s*(\w+_mean):\s*"([^"]+)"/gm)];
  const labelsByKey = new Map(labelEntries.map(([, key, label]) => [key, label]));

  assert.equal(labelsByKey.get("rms_mean"), "RMS");
  assert.equal(labelsByKey.get("mfcc_mean"), "MFCC");
  assert.equal(labelsByKey.get("chroma_mean"), "Chroma");
  for (const [key, label] of labelsByKey) {
    assert.ok(!/\bmean\b/i.test(label), `${key} label should not include mean: ${label}`);
  }
});

test("rms max uses uppercase RMS display label", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /rms_max:\s*"RMS max"/);
});

test("displayed sonara fields have built-in UI descriptions", () => {
  const source = readFileSync(dialogPath, "utf8");
  const displayedKeys = [
    "bpm",
    "beats",
    "onset_frames",
    "onset_density",
    "n_beats",
    "rms_mean",
    "rms_max",
    "loudness_lufs",
    "dynamic_range_db",
    "spectral_centroid_mean",
    "zero_crossing_rate",
    "duration_sec",
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "key",
    "key_confidence",
    "predominant_chord",
    "chord_change_rate",
    "dissonance",
    "spectral_bandwidth_mean",
    "spectral_rolloff_mean",
    "spectral_flatness_mean",
    "spectral_contrast_mean",
    "mfcc_mean",
    "chroma_mean"
  ];

  for (const key of displayedKeys) {
    assert.match(source, new RegExp(`${key}:\\s*"[^"]+"`), `${key} needs a UI description`);
  }
  assert.match(source, /description:\s*sonaraFeatureDescriptions\[key\]/);
  assert.doesNotMatch(source, /featureRecord\.description/);
  assert.match(source, /spectral_contrast_mean:\s*"Peak-valley ratio per band \(7 values\)"/);
  assert.match(source, /mfcc_mean:\s*"Timbre fingerprint \(13 coefficients\)"/);
  assert.match(source, /chroma_mean:\s*"Pitch class distribution \(12 values\)"/);
});

test("metadata dialog uses the track title as the only header title", () => {
  const source = readFileSync(dialogPath, "utf8");
  const dialogTitleBlock = source.match(/<div className="dialog-title">[\s\S]*?<\/div>/)?.[0] || "";

  assert.match(dialogTitleBlock, /metadata-track-title/);
  assert.match(dialogTitleBlock, /displayTrack\(track\)/);
  assert.doesNotMatch(dialogTitleBlock, /Теги и жанры/);
  assert.doesNotMatch(dialogTitleBlock, /basename\(track\.path\)/);
});

test("metadata dialog names the mutagen tag block", () => {
  const source = readFileSync(dialogPath, "utf8");
  const mutagenBlock = source.match(/<div className="mutagen-block">[\s\S]*?<\/div>/)?.[0] || "";

  assert.match(mutagenBlock, /<strong>Mutagen tags<\/strong>/);
  assert.match(mutagenBlock, /metadata-grid mutagen-grid/);
});

test("metadata dialog does not scroll the mutagen tag grid", () => {
  const styles = readFileSync(stylesPath, "utf8");
  const dialogRule = cssRule(styles, ".metadata-dialog");
  const mutagenBlockRule = cssRule(styles, ".mutagen-block");
  const mutagenGridRule = cssRule(styles, ".mutagen-grid");

  assert.match(dialogRule, /display:\s*flex;/);
  assert.match(dialogRule, /flex-direction:\s*column;/);
  assert.match(dialogRule, /gap:\s*10px;/);
  assert.match(dialogRule, /overflow-y:\s*auto;/);
  assert.match(mutagenBlockRule, /flex:\s*0 0 auto;/);
  assert.match(mutagenBlockRule, /overflow:\s*visible;/);
  assert.match(mutagenGridRule, /max-height:\s*none;/);
  assert.match(mutagenGridRule, /overflow:\s*visible;/);
  assert.doesNotMatch(mutagenGridRule, /scrollbar-gutter:\s*stable;/);
});

test("metadata dialog keeps SONARA as the scrollable feature block", () => {
  const styles = readFileSync(stylesPath, "utf8");
  const sonaraBlockRule = cssRule(styles, ".sonara-block");
  const sonaraFeatureGroupsRule = cssRule(styles, ".sonara-feature-groups");
  const tagGridRule = cssRule(styles, ".tag-grid");

  assert.match(sonaraBlockRule, /flex:\s*1 1 420px;/);
  assert.match(sonaraBlockRule, /min-height:\s*240px;/);
  assert.match(sonaraBlockRule, /overflow:\s*hidden;/);
  assert.match(sonaraFeatureGroupsRule, /flex:\s*1 1 auto;/);
  assert.match(sonaraFeatureGroupsRule, /overflow:\s*auto;/);
  assert.match(sonaraFeatureGroupsRule, /padding-right:\s*6px;/);
  assert.match(sonaraFeatureGroupsRule, /scrollbar-gutter:\s*stable;/);
  assert.match(tagGridRule, /max-height:\s*260px;/);
  assert.match(tagGridRule, /overflow:\s*auto;/);
});

test("metadata dialog exposes a compact copy button for file path", () => {
  const source = readFileSync(dialogPath, "utf8");
  const styles = readFileSync(stylesPath, "utf8");
  const rowRule = cssRule(styles, ".metadata-file-path-row");
  const buttonRule = cssRule(styles, "button.metadata-copy-path-button");

  assert.match(source, /import \{ Check, Copy, X \} from "lucide-react";/);
  assert.match(source, /const \[filePathCopied, setFilePathCopied\] = useState\(false\);/);
  assert.match(source, /className="metadata-file-path-row"/);
  assert.match(source, /className="metadata-file-path-value"/);
  assert.match(source, /className="icon-button metadata-copy-path-button"/);
  assert.match(source, /aria-label=\{`Copy file path: \$\{track\.path\}`\}/);
  assert.match(source, /copyTextToClipboard\(track\.path\)/);
  assert.match(source, /navigator\.clipboard\.writeText\(text\)/);
  assert.match(source, /textarea\.focus\(\);/);
  assert.match(source, /document\.execCommand\("copy"\)/);
  assert.match(source, /textarea\.setSelectionRange\(0, textarea\.value\.length\);/);
  assert.match(rowRule, /display:\s*inline-flex;/);
  assert.match(rowRule, /flex-wrap:\s*wrap;/);
  assert.match(buttonRule, /background:\s*transparent;/);
  assert.match(buttonRule, /color:\s*var\(--text-faint\);/);
  assert.match(buttonRule, /height:\s*18px;/);
  assert.match(buttonRule, /min-width:\s*18px;/);
  assert.match(buttonRule, /width:\s*18px;/);
});

test("mutagen bpm and key labels omit tag suffix", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /bpm:\s*"BPM"/);
  assert.match(source, /key:\s*"Key"/);
  assert.doesNotMatch(source, /"BPM tag"/);
  assert.doesNotMatch(source, /"Key tag"/);
});

test("metadata dialog shows genre bpm key and comment from stored mutagen tags", () => {
  const source = readFileSync(dialogPath, "utf8");
  const orderSource = source.match(/const trackTagOrder = \[([\s\S]*?)\];/)?.[1] || "";
  const orderedKeys = [...orderSource.matchAll(/"([^"]+)"/g)].map((match) => match[1]);

  assert.deepEqual(orderedKeys, ["genre", "bpm", "key", "comment"]);
  assert.match(source, /comment:\s*"Comment"/);
});

test("metadata dialog keeps SONARA core duration before BPM and formats BPM with two decimals", () => {
  const source = readFileSync(dialogPath, "utf8");
  const coreGroup = source.match(/title:\s*"Core",[\s\S]*?keys:\s*\[([^\]]+)\]/)?.[1] || "";

  assert.ok(coreGroup.indexOf('"duration_sec"') < coreGroup.indexOf('"bpm"'));
  assert.ok(coreGroup.indexOf('"bpm"') < coreGroup.indexOf('"beats"'));
  assert.match(source, /if \(key === "bpm" && typeof value === "number"\) return value\.toFixed\(2\);/);
});

test("metadata dialog shows analysis availability badges", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /analysis-badge-row/);
  assert.match(source, /readableAnalysisBadges\(track\)/);
  assert.match(source, /analysis-badge/);
  assert.match(source, /CLASSIFIERS/);
});
