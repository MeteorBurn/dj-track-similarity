import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src/", import.meta.url));
const dialogPath = fileURLToPath(new URL("../src/ScanImportDialog.tsx", import.meta.url));
const panelPath = fileURLToPath(new URL("../src/LibraryPanel.tsx", import.meta.url));
const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));

test("scan import dialog owns ephemeral defaults and required controls", () => {
  assert.equal(existsSync(dialogPath), true, "ScanImportDialog.tsx exists");
  const source = readFileSync(dialogPath, "utf8");

  assert.match(source, /function ScanImportDialog/);
  assert.match(source, /defaultScanImportSettings/);
  assert.match(source, /minDurationSeconds:\s*"120"/);
  assert.match(source, /maxDurationSeconds:\s*"1200"/);
  assert.match(source, /scanLimit:\s*0/);
  assert.match(source, /workers:\s*8/);
  assert.match(source, /aria-pressed/);
  assert.match(source, /onChooseFolder/);
  assert.match(source, /onStart/);
  assert.match(source, />Старт</);
  assert.match(source, /scan-import-limit-decrement-button/);
  assert.match(source, /scan-import-limit-increment-button/);
  assert.match(source, /limit: settings\.scanLimit > 0 \? settings\.scanLimit : undefined/);
  assert.ok(source.indexOf("Scan limit") < source.indexOf("Min, сек"));
  assert.match(source, /scan-import-settings[\s\S]*?scan-import-path-row[\s\S]*?scan-import-submit-button/);
  assert.match(source, /<X/);
  assert.doesNotMatch(source, /localStorage|sessionStorage/);
  for (const format of ["MP3", "FLAC", "ALAC", "WAV", "AIFF", "M4A", "OGG", "OPUS", "WAVE", "AIF"]) {
    assert.match(source, new RegExp(`label: "${format}"`));
  }
  assert.match(source, /label: "WAV", extensions: \["\.wav"\]/);
  assert.match(source, /label: "WAVE", extensions: \["\.wave"\]/);
  assert.match(source, /label: "AIFF", extensions: \["\.aiff"\]/);
  assert.match(source, /label: "AIF", extensions: \["\.aif"\]/);
});

test("scan import dialog offers extended audio formats", () => {
  const source = readFileSync(dialogPath, "utf8");

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

test("scan import dialog uses neutral inactive format chips and aligned worker controls", () => {
  const source = readFileSync(dialogPath, "utf8");
  const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  const workerControls = styles.match(/\.scan-import-settings \.worker-control\s*{([\s\S]*?)}/)?.[1] || "";
  const settingControls = styles.match(/\.scan-import-settings > label,\s*\n\.scan-import-settings \.worker-control\s*{([\s\S]*?)}/)?.[1] || "";
  const stepper = styles.match(/\.scan-import-settings \.stepper\s*{([\s\S]*?)}/)?.[1] || "";
  const settingInputs = styles.match(/\.scan-import-settings > label > input,\s*\n\.scan-import-settings \.stepper \.icon-button,\s*\n\.scan-import-settings \.stepper input\s*{([\s\S]*?)}/)?.[1] || "";
  const inactiveChip = styles.match(/\.scan-import-format-chip\s*{([\s\S]*?)}/)?.[1] || "";
  const pathRow = styles.match(/\.scan-import-path-row\s*{([\s\S]*?)}/)?.[1] || "";
  const pathButton = styles.match(/\.scan-import-path-row \.icon-button\s*{([\s\S]*?)}/)?.[1] || "";
  const formats = styles.match(/\.scan-import-formats\s*{([\s\S]*?)}/)?.[1] || "";
  const dialog = styles.match(/\.scan-import-dialog\s*{([\s\S]*?)}/)?.[1] || "";
  const description = styles.match(/\.scan-import-description\s*{([\s\S]*?)}/)?.[1] || "";
  const formatOrder = ["MP3", "FLAC", "ALAC", "WAV", "WAVE", "AIFF", "AIF", "M4A", "OGG", "OPUS"].map((label) => source.indexOf(`label: "${label}"`));

  assert.match(source, /scan-import-description/);
  assert.match(source, /<p className="scan-import-description">Выберите папку как источник для загрузки треков в базу: сканирование папок выполняется рекурсивно\.<\/p>\s*<div className="path-row scan-import-path-row">/);
  assert.ok(source.indexOf("scan-import-formats") < source.indexOf("scan-import-settings"));
  assert.doesNotMatch(source, /scan-import-submit-description/);
  assert.match(inactiveChip, /var\(--scan-import-format-off-bg\)/);
  assert.match(inactiveChip, /var\(--scan-import-format-off-border\)/);
  assert.match(inactiveChip, /flex:\s*1 1 0/);
  assert.match(inactiveChip, /min-width:\s*0/);
  assert.match(workerControls, /gap:\s*4px/);
  assert.match(settingControls, /grid-template-rows:\s*18px 36px/);
  assert.match(stepper, /align-items:\s*stretch/);
  assert.match(stepper, /height:\s*36px/);
  assert.match(settingInputs, /height:\s*36px/);
  assert.match(settingInputs, /min-height:\s*36px/);
  assert.match(pathRow, /grid-template-columns:\s*minmax\(0, 1fr\) 34px/);
  assert.match(pathButton, /width:\s*34px/);
  assert.doesNotMatch(source, /scan-import-format-aliases/);
  assert.match(formats, /flex-wrap:\s*nowrap/);
  assert.match(formats, /justify-content:\s*center/);
  assert.match(dialog, /max-width:\s*min\(760px, calc\(100vw - 32px\)\)/);
  assert.match(description, /font-size:\s*13px/);
  assert.match(description, /width:\s*100%/);
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

  const startHandler = app.match(/async function handleStartScan\(request: ScanImportRequest\) \{([\s\S]*?)\n  \}/)?.[1] || "";
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
