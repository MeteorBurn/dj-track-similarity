import type { SheetSage2TimelineEvent } from "./api";

export type SheetSage2Interval = { start: number; end: number; label: string };

export function buildSheetSage2Timeline(events: SheetSage2TimelineEvent[]) {
  const beats: { time: number; meter: [number, number]; position: number }[] = [];
  const tempo: { start: number; end: number; bpm: number }[] = [];
  const notes: NonNullable<SheetSage2TimelineEvent["melody"]> = [];
  const structure: SheetSage2Interval[] = [];
  const chord: SheetSage2Interval[] = [];
  const key: SheetSage2Interval[] = [];
  const meters: { time: number; label: string | null }[] = [];
  for (const event of events) {
    const rhythm = event.rhythm;
    if (rhythm) {
      const label = rhythm.numerator != null && rhythm.denominator != null ? `${rhythm.numerator}/${rhythm.denominator}` : null;
      if (!meters.length || meters[meters.length - 1].label !== label) meters.push({ time: event.time_s, label });
    }
    if (rhythm?.numerator != null && rhythm.denominator != null) {
      const position = rhythm.eighth_position * rhythm.denominator / 8;
      if (Number.isInteger(position)) beats.push({ time: event.time_s, meter: [rhythm.numerator, rhythm.denominator], position });
    }
    for (const [name, intervals] of [["structure", structure], ["chord", chord], ["key", key]] as const) {
      const interval = event[name];
      if (interval) intervals.push({ start: event.time_s, end: interval.end_s, label: interval.label });
    }
    notes.push(...(event.melody ?? []));
  }
  for (let i = 1; i < beats.length; i++) {
    const left = beats[i - 1], right = beats[i];
    // Same quarter-note normalization and consecutive-beat rule as persisted features.
    if (right.time > left.time && left.meter[0] === right.meter[0] && left.meter[1] === right.meter[1]
      && right.position === (left.position + 1) % left.meter[0]) {
      tempo.push({ start: left.time, end: right.time, bpm: 240 / (right.meter[1] * (right.time - left.time)) });
    }
  }
  return { beats, tempo, notes, structure, chord, key, meters };
}
