import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

function loadSetBuilderControls() {
  const sourcePath = new URL("../src/setBuilderControls.ts", import.meta.url);
  if (!existsSync(sourcePath)) {
    throw new Error("frontend/src/setBuilderControls.ts does not exist yet");
  }
  const tempDir = mkdtempSync(join(tmpdir(), "set-builder-controls-"));
  const modulePath = join(tempDir, "setBuilderControls.cjs");
  const compiled = ts.transpileModule(readFileSync(sourcePath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  writeFileSync(modulePath, compiled, "utf8");
  return import(pathToFileURL(modulePath));
}

test("set builder slider reset clears classifier preference maps and restores defaults", async () => {
  const { resetSetBuilderSliders, setBuilderDefaultDiversity, setBuilderDefaultFlow } = await loadSetBuilderControls();

  const first = resetSetBuilderSliders();
  first.classifierPreferences.break_energy = 0.85;
  first.classifierFlows.break_energy = "rise";
  const second = resetSetBuilderSliders();

  assert.equal(second.diversity, setBuilderDefaultDiversity);
  assert.deepEqual(second.classifierPreferences, {});
  assert.deepEqual(second.classifierFlows, {});
  assert.equal(setBuilderDefaultFlow, "flat");
  assert.notEqual(first.classifierPreferences, second.classifierPreferences);
  assert.notEqual(first.classifierFlows, second.classifierFlows);
});

test("set builder UI keeps basic controls separate from advanced controls", () => {
  const source = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");

  assert.match(source, /set-builder-basic-controls/);
  assert.match(source, /set-builder-advanced-toggle-button/);
  assert.match(source, /aria-expanded=\{setAdvancedControlsOpen\}/);
  assert.match(source, /set-builder-advanced-controls/);
});

test("set builder auto anchors are disabled outside auto seed mode", () => {
  const source = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");

  assert.match(source, /Auto anchors/);
  assert.match(source, /autoSeedCountDisabled \? ".*disabled-filter/);
  assert.match(source, /disabled=\{autoSeedCountDisabled\}/);
});

test("set builder basic owns diversity and advanced owns bpm classifier and reset controls", () => {
  const source = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");
  const basic = source.match(/className="set-builder-basic-controls"[\s\S]*?className="set-builder-advanced-header"/)?.[0] || "";
  const advanced = source.match(/className="set-builder-advanced-controls"[\s\S]*?className="set-builder-generate-button"/)?.[0] || "";

  assert.match(basic, /Diversity/);
  assert.match(advanced, /BPM mode/);
  assert.match(advanced, /Start BPM/);
  assert.match(advanced, /set-classifier-controls/);
  assert.match(advanced, /Reset sliders/);
});

test("set builder classifier controls expose preference and flow only", () => {
  const source = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");

  assert.match(source, /Preference/);
  assert.match(source, /Flow/);
  assert.match(source, /classifier_preferences/);
  assert.match(source, /classifier_flows/);
  assert.doesNotMatch(source, /Target boost/);
  assert.doesNotMatch(source, /Avoid cut/);
  assert.doesNotMatch(source, /Curve start/);
  assert.doesNotMatch(source, /Curve end/);
});
