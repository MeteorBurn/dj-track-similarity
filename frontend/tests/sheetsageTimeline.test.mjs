import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

test("SheetSage2 timeline preserves stored gaps and derives tempo only from consecutive beats in one meter", () => {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(
    readFileSync(new URL("../src/sheetsageTimelineData.ts", import.meta.url), "utf8"),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
  ).outputText, { module, exports: module.exports });
  const event = (time_s, eighth_position, numerator = 4, denominator = 4, extra = {}) => ({
    time_s,
    rhythm: { numerator, denominator, eighth_position, timestamp_anchor: true },
    ...extra,
  });
  const instrumental = { pitch_midi: 60, source_track: "instrumental", start_s: 0, end_s: 0.2, duration_steps: 2 };
  const vocal = { pitch_midi: 55, source_track: "vocal", start_s: 0.5, end_s: 0.9, duration_steps: 4 };
  const events = [
    event(0, 0, 4, 4, {
      structure: { label: "intro", end_s: 0.7 },
      chord: { label: "C:maj", end_s: 0.4 },
      key: { label: "C:major", end_s: 1 },
      melody: [instrumental],
    }),
    event(0.25, 1), // Eighth subdivision, not an additional quarter-note beat.
    event(0.5, 2, 4, 4, { chord: { label: "F:maj", end_s: 1 }, melody: [vocal] }),
    event(1.5, 6, 4, 4, { // Missing position 2 must not become a false slow-tempo segment.
      structure: { label: "chorus", end_s: 2.5 },
      key: { label: "A:minor", end_s: 3 },
    }),
    event(2, 0), // Last beat to next downbeat remains a valid pair.
    event(3, 0, 6, 8), // A meter change cannot be joined to the previous beat.
    event(3.25, 1, 6, 8),
    event(3.375, 0, null, null), // Unresolved meter supplies no tempo evidence.
    event(3.5, 2, 6, 8),
  ];

  const result = module.exports.buildSheetSage2Timeline(events);
  const actual = JSON.parse(JSON.stringify(result));
  assert.deepEqual(actual.beats, [
    { time: 0, meter: [4, 4], position: 0 },
    { time: 0.5, meter: [4, 4], position: 1 },
    { time: 1.5, meter: [4, 4], position: 3 },
    { time: 2, meter: [4, 4], position: 0 },
    { time: 3, meter: [6, 8], position: 0 },
    { time: 3.25, meter: [6, 8], position: 1 },
    { time: 3.5, meter: [6, 8], position: 2 },
  ]);
  assert.deepEqual(actual.tempo, [
    { start: 0, end: 0.5, bpm: 120 },
    { start: 1.5, end: 2, bpm: 120 },
    { start: 3, end: 3.25, bpm: 120 },
    { start: 3.25, end: 3.5, bpm: 120 },
  ]);
  assert.deepEqual(actual.structure, [
    { start: 0, end: 0.7, label: "intro" },
    { start: 1.5, end: 2.5, label: "chorus" },
  ]);
  assert.deepEqual(actual.chord, [
    { start: 0, end: 0.4, label: "C:maj" },
    { start: 0.5, end: 1, label: "F:maj" },
  ]);
  assert.deepEqual(actual.key, [
    { start: 0, end: 1, label: "C:major" },
    { start: 1.5, end: 3, label: "A:minor" },
  ]);
  assert.deepEqual(actual.notes, [instrumental, vocal]);
});
