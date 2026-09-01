import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src/", import.meta.url));
const dialogPath = fileURLToPath(new URL("../src/ScanImportDialog.tsx", import.meta.url));
const settingsPath = fileURLToPath(new URL("../src/scanImportSettings.ts", import.meta.url));
const panelPath = fileURLToPath(new URL("../src/LibraryPanel.tsx", import.meta.url));
const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));

test("scan import dialog exposes required controls", () => {
  assert.equal(existsSync(dialogPath), true, "ScanImportDialog.tsx exists");
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /function ScanImportDialog/);
  assert.match(source, /aria-pressed/);
  assert.match(source, /onChooseFolder/);
  assert.match(source, />OK</);
  assert.match(source, /scan-import-settings[\s\S]*?scan-import-path-row[\s\S]*?scan-import-ok-button/);
  assert.match(source, /<X/);
  assert.doesNotMatch(source, /localStorage|sessionStorage/);
});

test("scan import settings own ephemeral defaults and extended audio formats", () => {
  const source = readFileSync(settingsPath, "utf8");

  assert.match(source, /defaultScanImportSettings/);
  assert.match(source, /minDurationSeconds:\s*"120"/);
  assert.match(source, /maxDurationSeconds:\s*"1200"/);
  assert.match(source, /workers:\s*8/);
  for (const format of ["MP3", "FLAC", "ALAC", "WAV", "AIFF", "M4A", "OGG", "OPUS", "WAVE", "AIF"]) {
    assert.match(source, new RegExp(`label: "${format}"`));
  }
  assert.match(source, /label: "WAV", extensions: \["\.wav"\]/);
  assert.match(source, /label: "WAVE", extensions: \["\.wave"\]/);
  assert.match(source, /label: "AIFF", extensions: \["\.aiff"\]/);
  assert.match(source, /label: "AIF", extensions: \["\.aif"\]/);
  for (const [label, extension] of [
    ["AAC", ".aac"],
    ["APE", ".ape"],
    ["WMA", ".wma"],
    ["WavPack", ".wv"],
  ]) {
    assert.match(
      source,
      new RegExp(`label: "${label}", extensions: \\["\\${extension}"\\]`),
    );
  }
});

test("scan import dialog keeps inactive format chips neutral and formats sorted", () => {
  const source = readFileSync(settingsPath, "utf8");
  const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  const inactiveChip = styles.match(/\.scan-import-format-chip\s*{([\s\S]*?)}/)?.[1] || "";
  const formatOrder = ["AAC", "AIF", "AIFF", "ALAC", "APE", "FLAC", "M4A", "MP3", "OGG", "OPUS", "WAV", "WAVE", "WMA", "WavPack"].map((label) => source.indexOf(`label: "${label}"`));

  assert.match(inactiveChip, /var\(--scan-import-format-off-bg\)/);
  assert.match(inactiveChip, /var\(--scan-import-format-off-border\)/);
  assert.doesNotMatch(source, /scan-import-format-aliases/);
  assert.ok(formatOrder.every((index, position) => position === 0 || index > formatOrder[position - 1]));
});

test("library panel opens the import dialog instead of owning scan parameters", () => {
  const panel = readFileSync(panelPath, "utf8");
  const app = readFileSync(appPath, "utf8");

  assert.match(panel, /onOpenScanDialog/);
  assert.doesNotMatch(panel, /musicRoot/);
  assert.doesNotMatch(panel, /scanWorkers/);
  assert.match(app, /<ScanImportDialog/);
  assert.match(app, /onOpenScanDialog/);
  assert.match(app, /const maxScanWorkers = 16;/);
});

test("scan import closes immediately and shows a centered preparation notice", () => {
  const app = readFileSync(appPath, "utf8");
  const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

  const startHandler = app.match(/async function handleStartScan\(request: ScanRequest\) \{([\s\S]*?)\n  \}/)?.[1] || "";
  const toastStyles = styles.match(/\.scan-import-start-toast\s*\{([\s\S]*?)}/)?.[1] || "";

  assert.match(app, /const \[scanImportStartToast, setScanImportStartToast\] = useState\(false\)/);
  assert.match(app, /const stageRunning = scanImportStartToast \|\| scanRunning/);
  assert.match(startHandler, /setScanImportOpen\(false\);/);
  assert.match(startHandler, /setScanImportStartToast\(true\);/);
  assert.match(startHandler, /setNotice\(\{ kind: "idle", text: "Сканирование директории" \}\);/);
  assert.ok(startHandler.indexOf("setScanImportOpen(false)") < startHandler.indexOf("await api.scan(request)"));
  assert.match(startHandler, /text: "Загрузка треков в базу"/);
  assert.match(app, /className="scan-import-start-toast"/);
  assert.match(app, /Подготавливаем список треков/);
  assert.match(toastStyles, /position:\s*fixed/);
  assert.match(toastStyles, /top:\s*50%/);
  assert.match(toastStyles, /left:\s*50%/);
});
