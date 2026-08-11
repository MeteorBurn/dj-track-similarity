import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const helpPath = fileURLToPath(new URL("../src/helpText.ts", import.meta.url));

function loadHelpText() {
  const source = readFileSync(helpPath, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports });
  return module.exports.helpText;
}

test("MuQ help describes current seed search", () => {
  const helpText = loadHelpText();

  assert.match(helpText.muqAnalyze, /seed-поиска/);
});

test("CLAP analysis help keeps text-to-audio separate from stored audio-to-audio evidence", () => {
  const helpText = loadHelpText();

  assert.match(helpText.clapAnalyze, /Text-to-audio/);
  assert.match(helpText.clapAnalyze, /audio-to-audio CLAP evidence/);
});

test("SONARA modifier help describes heard results instead of metric jargon", () => {
  const helpText = loadHelpText();
  assert.match(helpText.sonaraModifierEnergy, /насколько трек ощущается активным/);
  assert.match(helpText.sonaraModifierValence, /эмоциональный тон/);
  assert.match(helpText.sonaraModifierAggression, /жёсткость и напряжение/);
  assert.match(helpText.sonaraModifierVocalness, /слышимое присутствие голоса/);
  assert.match(helpText.sonaraModifierAcousticness, /живых\/органических инструментов/);
  assert.match(helpText.sonaraModifierBrightness, /хай-хэтов/);
  assert.match(helpText.sonaraModifierRhythmDensity, /Это не BPM/);
  assert.match(helpText.sonaraModifierDynamicRange, /не общая громкость/);
  assert.match(helpText.sonaraModifierLoudness, /нормализации/);
  assert.doesNotMatch(helpText.sonaraModifierBrightness, /спектральн/);
});

test("SONARA mixer help describes the audible similarity each weight controls", () => {
  const helpText = loadHelpText();
  assert.match(helpText.sonaraMixerTimbre, /характер и текстура звука/);
  assert.match(helpText.sonaraMixerRhythm, /ударные и грув/);
  assert.match(helpText.sonaraMixerDynamics, /силы и развития внутри трека/);
  assert.match(helpText.sonaraMixerHarmonic, /аккордов и напряжения/);
  assert.match(helpText.sonaraMixerTempo, /удобство сведения/);
  assert.doesNotMatch(helpText.sonaraMixerTimbre, /0 — не учитывать/);
});

test("SONARA mode help describes ready-made modes and manual control", () => {
  const helpText = loadHelpText();

  assert.match(helpText.sonaraMode, /готовый сценарий поиска/);
  assert.match(helpText.sonaraMode, /Custom mixer включает ручную настройку/);
});
