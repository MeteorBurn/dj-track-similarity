import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));

test("top header meta omits liked track count", () => {
  const source = readFileSync(appPath, "utf8");
  const metaBlock = source.match(/<div className="meta"[^>]*>([\s\S]*?)<\/div>/)?.[1] || "";

  assert.match(metaBlock, /librarySummary\.tracks/);
  assert.match(metaBlock, /librarySummary\.clap/);
  assert.doesNotMatch(metaBlock, /librarySummary\.liked/);
  assert.doesNotMatch(metaBlock, /\|\s*liked/);
});

test("top header meta renders summary values as badges", () => {
  const appSource = readFileSync(appPath, "utf8");
  const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");
  const metaBlock = appSource.match(/<div className="meta"[^>]*>([\s\S]*?)<\/div>/)?.[1] || "";
  const badgeRule = styles.match(/\.meta-badge\s*{([\s\S]*?)}/)?.[1] || "";
  const labelRule = styles.match(/\.meta-badge span\s*{([\s\S]*?)}/)?.[1] || "";
  const valueRule = styles.match(/\.meta-badge strong\s*{([\s\S]*?)}/)?.[1] || "";

  assert.equal((metaBlock.match(/className="meta-badge/g) || []).length, 6);
  assert.match(metaBlock, /<span>tracks<\/span>/);
  assert.match(metaBlock, /<span>sonara<\/span>/);
  assert.match(metaBlock, /<span>class<\/span>/);
  assert.match(metaBlock, /<strong>\{librarySummary\.tracks\}<\/strong>/);
  assert.match(metaBlock, /<strong>\{librarySummary\.classifiers\}<\/strong>/);
  assert.doesNotMatch(metaBlock, /trackCountLabel/);
  assert.match(badgeRule, /border-radius:\s*999px/);
  assert.match(badgeRule, /background:/);
  assert.match(badgeRule, /min-height:\s*22px/);
  assert.match(badgeRule, /padding:\s*3px 7px/);
  assert.match(labelRule, /font-size:\s*9px/);
  assert.match(valueRule, /font-size:\s*11px/);
});

test("topbar log button opens a separate large log frame", () => {
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
  assert.match(actionsBlock, /log-frame-button[\s\S]*notice/);
  assert.doesNotMatch(librarySource, /UnifiedLog/);
  assert.match(styles, /\.log-frame-button/);
  assert.match(dialogRule, /width:\s*min\(1120px,\s*calc\(100vw - 32px\)\)/);
  assert.match(dialogRule, /height:\s*min\(760px,\s*calc\(100vh - 48px\)\)/);
  assert.match(contentRule, /flex:\s*1 1 auto/);
});
