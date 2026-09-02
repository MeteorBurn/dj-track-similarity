import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
const trackPanelPath = fileURLToPath(new URL("../src/TrackPanel.tsx", import.meta.url));

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
  assert.match(actionsBlock, /log-frame-button[\s\S]*server-shutdown-button[\s\S]*stop-active-stage-button[\s\S]*process-indicator[\s\S]*notice/);
  assert.doesNotMatch(actionsBlock, /rhythm-lab-button/);
  assert.doesNotMatch(actionsBlock.match(/<button[\s\S]*?log-frame-button[\s\S]*?>/)?.[0] || "", /process-indicator/);
  assert.doesNotMatch(librarySource, /process-indicator/);
  assert.doesNotMatch(librarySource, /stop-active-stage-button/);
  assert.doesNotMatch(librarySource, /UnifiedLog/);
  assert.match(styles, /\.log-frame-button/);
  assert.match(iconButtonRule, /width:\s*34px/);
  assert.match(processIndicatorRule, /width:\s*34px/);
  assert.match(dialogRule, /width:\s*min\(1440px,\s*calc\(100vw - 32px\)\)/);
  assert.match(dialogRule, /height:\s*min\(900px,\s*calc\(100vh - 32px\)\)/);
  assert.match(contentRule, /flex:\s*1 1 auto/);
});

test("mobile topbar keeps actions compact and gives status its own row", () => {
  const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");
  const mobileStyles = styles.match(/@media \(max-width: 720px\)\s*{([\s\S]*)$/)?.[1] || "";
  const actionsRule = mobileStyles.match(/\.topbar-actions\s*{([\s\S]*?)}/)?.[1] || "";
  const noticeRule = mobileStyles.match(/\.topbar-actions \.notice\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(actionsRule, /align-items:\s*center/);
  assert.match(actionsRule, /flex-direction:\s*row/);
  assert.match(actionsRule, /flex-wrap:\s*wrap/);
  assert.doesNotMatch(actionsRule, /flex-direction:\s*column/);
  assert.match(noticeRule, /flex:\s*1 0 100%/);
  assert.match(noticeRule, /max-width:\s*none/);
  assert.match(noticeRule, /width:\s*100%/);
});
