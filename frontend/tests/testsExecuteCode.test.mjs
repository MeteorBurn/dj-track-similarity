import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";

// A frontend test must load the module it checks as running code, not as text.
// Source-text regex assertions pin how a component is written instead of what it
// does: they break on harmless renames and stay green when behaviour breaks.
//
// Three loaders count as executing the module under test:
//   - `server.ssrLoadModule(...)` for React components (see analysisStatus.test.mjs)
//   - `ts.transpileModule(...)` + `vm` for plain modules (see shutdownApplication.test.mjs)
//   - a direct static or dynamic import from `../src/`
//
// The files below predate this rule and still assert on source text only. The
// list may shrink, never grow: convert a file to an executing test when you next
// touch its component, then delete its entry here.
const SOURCE_TEXT_ONLY_LEGACY = [
  "appHeaderMeta.test.mjs",
  "buttonClasses.test.mjs",
  "frontendHooks.test.mjs",
  "jobUi.test.mjs",
  "libraryRendering.test.mjs",
  "playerAutoplay.test.mjs",
  "playlistAddHandler.test.mjs",
  "scanImportDialog.test.mjs",
  "sonaraDisplay.test.mjs",
  "sonaraFeatureLabels.test.mjs",
  "sonaraSearchControls.test.mjs",
  "themeMode.test.mjs"
];

const EXECUTING_LOADERS = [
  /\bssrLoadModule\s*\(/,
  /\btranspileModule\s*\(/,
  /^import\s[\s\S]*?\bfrom\s+"\.\.\/src\//m,
  /\bimport\s*\(\s*["'`]\.\.\/src\//
];

function testFileNames() {
  return readdirSync(new URL(".", import.meta.url))
    .filter((name) => name.endsWith(".test.mjs") && name !== "testsExecuteCode.test.mjs")
    .sort();
}

function executesModuleUnderTest(name) {
  const source = readFileSync(new URL(name, import.meta.url), "utf8");
  return EXECUTING_LOADERS.some((pattern) => pattern.test(source));
}

test("every new frontend test executes the module it checks", () => {
  const legacy = new Set(SOURCE_TEXT_ONLY_LEGACY);
  const offenders = testFileNames()
    .filter((name) => !legacy.has(name))
    .filter((name) => !executesModuleUnderTest(name));

  assert.deepEqual(
    offenders,
    [],
    `These tests only assert on source text. Load the module under test with `
      + `ssrLoadModule, transpileModule, or a direct ../src/ import instead:\n`
      + offenders.map((name) => `  - ${name}`).join("\n")
  );
});

test("the source-text legacy list only holds files that are still source-text only", () => {
  const present = new Set(testFileNames());

  const missing = SOURCE_TEXT_ONLY_LEGACY.filter((name) => !present.has(name));
  assert.deepEqual(missing, [], `Legacy entries name tests that no longer exist: ${missing}`);

  const converted = SOURCE_TEXT_ONLY_LEGACY.filter((name) => executesModuleUnderTest(name));
  assert.deepEqual(
    converted,
    [],
    `These tests now execute their module. Remove them from SOURCE_TEXT_ONLY_LEGACY:\n`
      + converted.map((name) => `  - ${name}`).join("\n")
  );
});

test("the source-text legacy list is sorted and free of duplicates", () => {
  const sorted = [...SOURCE_TEXT_ONLY_LEGACY].sort();
  assert.deepEqual(SOURCE_TEXT_ONLY_LEGACY, sorted, "Keep SOURCE_TEXT_ONLY_LEGACY sorted.");
  assert.equal(
    new Set(SOURCE_TEXT_ONLY_LEGACY).size,
    SOURCE_TEXT_ONLY_LEGACY.length,
    "SOURCE_TEXT_ONLY_LEGACY has duplicate entries."
  );
});
