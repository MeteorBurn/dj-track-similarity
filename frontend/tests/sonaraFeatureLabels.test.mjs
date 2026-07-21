import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const dialogPath = fileURLToPath(new URL("../src/TrackMetadataDialog.tsx", import.meta.url));
const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
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
    "bpm_raw",
    "bpm_candidates",
    "bpm_confidence",
    "tempo_variability",
    "time_signature",
    "time_signature_confidence",
    "embedding_version",
    "fingerprint_version",
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
    "chroma_mean",
    "instrumentalness",
    "mood_happy",
    "mood_aggressive",
    "mood_relaxed",
    "mood_sad"
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
  assert.doesNotMatch(coreGroup, /"beats"|"onset_frames"/);
  assert.match(source, /if \(\(key === "bpm" \|\| key === "bpm_raw"\) && typeof value === "number"\) return value\.toFixed\(2\);/);
});

test("metadata dialog shows analysis availability badges", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /analysis-badge-row/);
  assert.match(source, /readableAnalysisBadges\(track\)/);
  assert.match(source, /analysis-badge/);
  assert.match(source, /CLASSIFIERS/);
});

test("metadata dialog describes the bundled SONARA vocal model", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /title:\s*"Voice",\s*keys:\s*\["vocalness", "instrumentalness"\]/);
  assert.match(source, /title:\s*"Mood",\s*keys:\s*\["mood_happy", "mood_aggressive", "mood_relaxed", "mood_sad"\]/);
  assert.match(source, /vocalness:\s*"Bundled SONARA vocal model score P\(vocal\)/);
  assert.match(source, /instrumentalness:\s*"Bundled SONARA instrumental score \(1 - P\(vocal\)\)"/);
  assert.match(source, /key:\s*"vocalness_model_id", label:\s*"Vocal model"/);
  assert.match(source, /mood_happy:\s*"Heuristic v1 affinity for a happy mood/);
  assert.match(source, /mood_aggressive:\s*"Heuristic v1 affinity for an aggressive mood/);
  assert.match(source, /mood_relaxed:\s*"Heuristic v1 affinity for a relaxed mood/);
  assert.match(source, /mood_sad:\s*"Heuristic v1 affinity for a sad mood/);
});

test("metadata dialog hides a zero-confidence time-signature guess", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /const timeSignatureConfidence = sonaraNumericPayloadValue\(record\.time_signature_confidence\);/);
  assert.match(source, /key === "time_signature" && timeSignatureConfidence === 0\s*\? "Unknown"/);
  assert.match(source, /time_signature:\s*"Detected musical meter; shown as Unknown when confidence is zero"/);
});

test("metadata dialog keeps light rhythm metadata in Core and identity data in Representations", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(
    source,
    /title:\s*"Rhythm metadata",\s*keys:\s*\["tempo_variability", "time_signature", "time_signature_confidence"\]/
  );
  assert.match(source, /tempo_variability:\s*"Within-track tempo variation retained as archival data/);
  assert.match(source, /time_signature_confidence:\s*"Confidence in the detected time signature/);
  assert.match(source, /StoragePresenceBlock title="Representations" fields=\{representationFields\}/);
});

test("main analysis submits the selected SONARA storage outputs", () => {
  const source = readFileSync(appPath, "utf8");

  assert.match(source, /sonara:\s*\{ outputs: sonaraOutputs, batch_size: sonaraBatchSize \}/);
});

test("metadata dialog displays loudness and light structure data with domain units", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /keys:\s*\["true_peak_db", "replaygain_db", "loudness_momentary_max_db", "loudness_range_lu"\]/);
  assert.match(source, /keys:\s*\["intro_end_sec", "outro_start_sec", "energy_curve_hop_sec", "energy_curve_summary"\]/);
  assert.match(source, /key === "true_peak_db"\) return `\$\{value\.toFixed\(2\)\} dBTP`/);
  assert.match(source, /key === "loudness_momentary_max_db"\) return `\$\{value\.toFixed\(2\)\} LUFS`/);
  assert.match(source, /"intro_end_sec"/);
  assert.match(source, /"outro_start_sec"/);
  assert.match(source, /"energy_curve_hop_sec"/);
});

test("metadata dialog does not load Timeline values and lists manifest names only", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /const timelineFields = track\.timeline_fields \|\| \[\];/);
  assert.match(source, /fields\.map\(\(field\) => <code key=\{field\}>\{field\}<\/code>\)/);
  assert.doesNotMatch(source, /api\.sonaraTimeline\(track\.id\)/);
  assert.doesNotMatch(source, /JSON\.stringify\(timeline/);
});

test("metadata dialog shows SONARA analysis provenance outside score controls", () => {
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /readableSonaraProvenanceGroups\(track\.metadata\?\.sonara_provenance\)/);
  assert.match(source, /readableSonaraSignatureGroups\(track\.metadata\?\.sonara_analysis_signature\)/);
  assert.match(source, /package_version/);
  assert.match(source, /schema_version/);
  assert.match(source, /requested_features/);
  assert.match(source, /title: "Provenance"/);
  assert.match(source, /title: "Analysis signature"/);
});
