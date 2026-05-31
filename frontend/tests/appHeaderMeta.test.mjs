import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));

test("top header meta renders only total track count as a badge", () => {
  const source = readFileSync(appPath, "utf8");
  const metaBlock = source.match(/<div className="meta"[^>]*>([\s\S]*?)<\/div>/)?.[1] || "";

  assert.match(metaBlock, /librarySummary\.tracks/);
  assert.equal((metaBlock.match(/className="meta-badge/g) || []).length, 1);
  assert.match(metaBlock, /<span>tracks<\/span>/);
  assert.match(metaBlock, /<strong>\{librarySummary\.tracks\}<\/strong>/);
  assert.doesNotMatch(metaBlock, /librarySummary\.sonara/);
  assert.doesNotMatch(metaBlock, /librarySummary\.maest/);
  assert.doesNotMatch(metaBlock, /librarySummary\.mert/);
  assert.doesNotMatch(metaBlock, /librarySummary\.clap/);
  assert.doesNotMatch(metaBlock, /librarySummary\.classifiers/);
  assert.doesNotMatch(metaBlock, /librarySummary\.liked/);
  assert.doesNotMatch(metaBlock, /\|\s*liked/);
});

test("analysis model rows render summary counts near each model", () => {
  const appSource = readFileSync(appPath, "utf8");
  const librarySource = readFileSync(fileURLToPath(new URL("../src/LibraryPanel.tsx", import.meta.url)), "utf8");
  const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");
  const badgeRule = styles.match(/\.meta-badge\s*{([\s\S]*?)}/)?.[1] || "";
  const countRule = styles.match(/\.analysis-model-count\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(appSource, /analysisModelCounts/);
  assert.match(appSource, /classifiers:\s*librarySummary\.classifiers/);
  assert.match(librarySource, /analysis-model-count/);
  assert.match(librarySource, /analysisCounts\[model\]/);
  assert.doesNotMatch(appSource, /trackCountLabel/);
  assert.match(badgeRule, /border-radius:\s*999px/);
  assert.match(badgeRule, /background:/);
  assert.match(badgeRule, /min-height:\s*22px/);
  assert.match(badgeRule, /padding:\s*3px 7px/);
  assert.match(countRule, /justify-self:\s*end/);
  assert.match(countRule, /font-variant-numeric:\s*tabular-nums/);
});

test("topbar log and process controls are separate actions", () => {
  const appSource = readFileSync(appPath, "utf8");
  const dialogSource = readFileSync(fileURLToPath(new URL("../src/dialogs.tsx", import.meta.url)), "utf8");
  const librarySource = readFileSync(fileURLToPath(new URL("../src/LibraryPanel.tsx", import.meta.url)), "utf8");
  const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");
  const actionsBlock = appSource.match(/<div className="topbar-actions">([\s\S]*?)<\/div>/)?.[1] || "";
  const dialogRule = styles.match(/\.log-frame-dialog\s*{([\s\S]*?)}/)?.[1] || "";
  const contentRule = styles.match(/\.log-frame-content\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(appSource, /logFrameOpen/);
  assert.match(dialogSource, /function LogFrameDialog/);
  assert.match(dialogSource, /<UnifiedLog[\s\S]*className="log-frame-panel"/);
  assert.match(actionsBlock, /log-frame-button[\s\S]*stop-active-stage-button[\s\S]*process-indicator[\s\S]*notice/);
  assert.doesNotMatch(actionsBlock.match(/<button[\s\S]*?log-frame-button[\s\S]*?>/)?.[0] || "", /process-indicator/);
  assert.doesNotMatch(librarySource, /process-indicator/);
  assert.doesNotMatch(librarySource, /stop-active-stage-button/);
  assert.doesNotMatch(librarySource, /UnifiedLog/);
  assert.match(styles, /\.log-frame-button/);
  assert.match(dialogRule, /width:\s*min\(1120px,\s*calc\(100vw - 32px\)\)/);
  assert.match(dialogRule, /height:\s*min\(760px,\s*calc\(100vh - 48px\)\)/);
  assert.match(contentRule, /flex:\s*1 1 auto/);
});
