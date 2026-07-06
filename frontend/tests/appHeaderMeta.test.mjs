import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));

test("top header meta renders only total track count as a badge", () => {
  const source = readFileSync(appPath, "utf8");
  const summaryBlock = source.match(/<div className="library-summary"[^>]*>([\s\S]*?)<\/div>/)?.[1] || "";

  assert.match(summaryBlock, /librarySummary\.tracks/);
  assert.equal((summaryBlock.match(/className="library-summary-badge/g) || []).length, 1);
  assert.match(summaryBlock, /<span>tracks<\/span>/);
  assert.match(summaryBlock, /<strong>\{librarySummary\.tracks\}<\/strong>/);
  assert.doesNotMatch(summaryBlock, /librarySummary\.sonara/);
  assert.doesNotMatch(summaryBlock, /librarySummary\.maest/);
  assert.doesNotMatch(summaryBlock, /librarySummary\.mert/);
  assert.doesNotMatch(summaryBlock, /librarySummary\.clap/);
  assert.doesNotMatch(summaryBlock, /librarySummary\.classifiers/);
  assert.doesNotMatch(summaryBlock, /librarySummary\.liked/);
  assert.doesNotMatch(summaryBlock, /\|\s*liked/);
});

test("analysis model rows render summary counts near each model", () => {
  const appSource = readFileSync(appPath, "utf8");
  const librarySource = readFileSync(fileURLToPath(new URL("../src/LibraryPanel.tsx", import.meta.url)), "utf8");
  const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");
  const badgeRule = styles.match(/\.library-summary-badge\s*{([\s\S]*?)}/)?.[1] || "";
  const nameRule = styles.match(/\.analysis-model-name\s*{([\s\S]*?)}/)?.[1] || "";
  const nameTextRule = styles.match(/\.analysis-model-title,\s*\n\.analysis-model-description\s*{([\s\S]*?)}/)?.[1] || "";
  const titleRule = styles.match(/\.analysis-model-title\s*{([\s\S]*?)}/)?.[1] || "";
  const descriptionRules = [...styles.matchAll(/\.analysis-model-description\s*{([\s\S]*?)}/g)];
  const descriptionRule = descriptionRules[descriptionRules.length - 1]?.[1] || "";
  const countRule = styles.match(/\.analysis-model-count\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(appSource, /analysisModelCounts/);
  assert.match(appSource, /classifiers:\s*librarySummary\.classifiers/);
  assert.match(librarySource, /analysis-model-count/);
  assert.match(librarySource, /analysis-model-description/);
  assert.match(librarySource, /analysisCounts\[model\]/);
  assert.doesNotMatch(appSource, /trackCountLabel/);
  assert.match(badgeRule, /border-radius:\s*999px/);
  assert.match(badgeRule, /background:/);
  assert.match(badgeRule, /min-height:\s*22px/);
  assert.match(badgeRule, /padding:\s*3px 7px/);
  assert.match(nameRule, /display:\s*grid/);
  assert.match(nameRule, /grid-template-columns:\s*max-content\s+minmax\(0,\s*1fr\)/);
  assert.match(nameRule, /align-items:\s*center/);
  assert.match(nameRule, /justify-content:\s*center/);
  assert.match(nameRule, /min-height:\s*34px/);
  assert.match(nameRule, /text-align:\s*left/);
  assert.match(nameTextRule, /text-overflow:\s*ellipsis/);
  assert.match(titleRule, /font-size:\s*13px/);
  assert.match(titleRule, /font-weight:\s*760/);
  assert.match(descriptionRule, /justify-self:\s*stretch/);
  assert.match(descriptionRule, /text-align:\s*center/);
  assert.match(descriptionRule, /width:\s*100%/);
  assert.match(descriptionRule, /font-size:\s*10px/);
  assert.match(descriptionRule, /font-weight:\s*600/);
  assert.match(countRule, /justify-self:\s*end/);
  assert.match(countRule, /color:\s*var\(--text-strong\)/);
  assert.match(countRule, /font-size:\s*13px/);
  assert.match(countRule, /font-weight:\s*800/);
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
  const iconButtonRule = styles.match(/button\.icon-button\s*{([\s\S]*?)}/)?.[1] || "";
  const processIndicatorRule = styles.match(/\.process-indicator\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(appSource, /logFrameOpen/);
  assert.match(dialogSource, /function LogFrameDialog/);
  assert.match(dialogSource, /<UnifiedLog[\s\S]*className="log-frame-panel"/);
  assert.match(actionsBlock, /log-frame-button[\s\S]*rhythm-lab-launch-button[\s\S]*stop-active-stage-button[\s\S]*process-indicator[\s\S]*notice/);
  assert.doesNotMatch(actionsBlock, /rhythm-lab-stop-button/);
  assert.doesNotMatch(actionsBlock.match(/<button[\s\S]*?log-frame-button[\s\S]*?>/)?.[0] || "", /process-indicator/);
  assert.doesNotMatch(librarySource, /process-indicator/);
  assert.doesNotMatch(librarySource, /stop-active-stage-button/);
  assert.doesNotMatch(librarySource, /UnifiedLog/);
  assert.match(styles, /\.log-frame-button/);
  assert.match(iconButtonRule, /width:\s*34px/);
  assert.match(processIndicatorRule, /width:\s*34px/);
  assert.match(dialogRule, /width:\s*min\(1120px,\s*calc\(100vw - 32px\)\)/);
  assert.match(dialogRule, /height:\s*min\(760px,\s*calc\(100vh - 48px\)\)/);
  assert.match(contentRule, /flex:\s*1 1 auto/);
});
