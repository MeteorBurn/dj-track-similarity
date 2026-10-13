import { Fragment, useState } from "react";
import type { SheetSage2Features as Features, SheetSage2MelodySource } from "./api";

type Metric = { label: string; value: string | string[]; description: string };
type Group = { title: string; rows: Metric[]; distributions: Metric[] };

function value(value: number | string | null, unit = "") {
  if (value == null || (typeof value === "number" && !Number.isFinite(value))) return "–";
  return `${typeof value === "number" ? value.toLocaleString("en-US", { maximumFractionDigits: 3 }) : value}${unit}`;
}

function fraction(amount: number | null) {
  return amount == null ? "–" : value(amount * 100, "%");
}

function position(seconds: number | null) {
  if (seconds == null || !Number.isFinite(seconds)) return "–";
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function distribution(items: Record<string, number>, kind: "duration" | "count" | "interval") {
  const entries = Object.entries(items);
  if (!entries.length) return "–";
  if (kind === "interval") entries.sort(([a], [b]) => Number(a) - Number(b));
  return entries.map(([label, amount]) => {
    if (kind === "interval") {
      const step = Number(label);
      return `${step > 0 ? "+" : ""}${step} пт → ${value(amount)}`;
    }
    const name = label.replace(/:(major|maj)$/, " major").replace(/:(minor|min)$/, " minor");
    return kind === "duration" ? `${name} ${position(amount)}` : `${name} × ${value(amount)}`;
  });
}

function metric(label: string, formatted: string | string[], description: string): Metric {
  return { label, value: formatted, description };
}

function groups(features: Features, source: SheetSage2MelodySource): Group[] {
  const f = features;
  const melody = (key: "event_count" | "pitch_min" | "pitch_median" | "pitch_max" | "pitch_range" | "duration_min" | "duration_median" | "duration_mean" | "duration_max" | "duration_std" | "density_per_second" | "coverage_fraction" | "interval_pair_count" | "interval_abs_mean") => f[`melody_${source}_${key}`];
  return [
    { title: "Rhythm", rows: [
      metric("BPM median", value(f.bpm_median), "Медианный темп, четвертей в минуту."),
      metric("BPM min / max", `${value(f.bpm_min)} / ${value(f.bpm_max)}`, "Минимум и максимум локального темпа."),
      metric("BPM deviation", value(f.bpm_std), "Стандартное отклонение локального темпа."),
      metric("Dominant meter", value(f.dominant_meter), "Размер с наибольшей суммарной длительностью."),
      metric("Beats", value(f.beat_count), "Количество распознанных долей."),
      metric("Downbeats", value(f.downbeat_count), "Количество первых долей такта."),
      metric("Meter changes", value(f.meter_change_count), "Количество смен размера."),
    ], distributions: [metric("Meter durations", distribution(f.meter_durations_s, "duration"), "Размер – суммарная длительность (мин:с).")] },
    { title: "Harmony", rows: [
      metric("Dominant key", value(f.dominant_key), "Тональность с наибольшей суммарной длительностью."),
      metric("Dominant chord", value(f.dominant_chord), "Аккорд с наибольшей суммарной длительностью."),
      metric("Chord segments", value(f.chord_segment_count), "Количество сегментов с аккордами."),
      metric("Unique chords", value(f.chord_unique_count), "Количество разных обозначений аккордов."),
      metric("Chord changes", value(f.chord_change_count), "Смены между соседними аккордами."),
      metric("Change rate", value(f.chord_change_rate_per_minute, " / min"), "Частота смен аккордов по всему треку."),
      metric("Key changes", value(f.key_change_count), "Количество смен тональности."),
      metric("Major / minor", `${fraction(f.major_fraction)} / ${fraction(f.minor_fraction)}`, "Доли общей длительности трека; неразмеченные участки не входят ни в одну долю."),
    ], distributions: [
      metric("Key durations", distribution(f.key_durations_s, "duration"), "Тональность – суммарная длительность (мин:с)."),
      metric("Chord durations", distribution(f.chord_durations_s, "duration"), "Аккорд – суммарная длительность (мин:с)."),
    ] },
    { title: "Structure", rows: [
      metric("Sections", value(f.section_count), "Количество распознанных секций."),
      metric("Intro end", position(f.intro_end_s), "Конец первого сегмента intro от начала трека (мин:с)."),
      metric("First chorus", position(f.first_chorus_start_s), "Начало первого сегмента chorus от начала трека (мин:с)."),
      metric("Outro start", position(f.outro_start_s), "Начало первого сегмента outro от начала трека (мин:с)."),
    ], distributions: [
      metric("Section counts", distribution(f.section_counts, "count"), "Тип секции × количество."),
      metric("Section durations", distribution(f.section_durations_s, "duration"), "Тип секции – суммарная длительность (мин:с)."),
    ] },
    { title: "Melody", rows: [
      metric("Note events", value(melody("event_count")), "Количество нотных событий."),
      metric("Pitch min / median / max", (["pitch_min", "pitch_median", "pitch_max"] as const).map(k => value(melody(k))).join(" / "), "Высота нот в MIDI."),
      metric("Pitch range", value(melody("pitch_range"), " st"), "Диапазон высот в полутонах."),
      metric("Duration min / median / mean / max", (["duration_min", "duration_median", "duration_mean", "duration_max"] as const).map(k => value(melody(k))).join(" / ") + " s", "Длительности нот в секундах."),
      metric("Duration deviation", value(melody("duration_std"), " s"), "Стандартное отклонение длительности нот."),
      metric("Note density", value(melody("density_per_second"), " / s"), "Нотных событий в секунду общей длительности трека."),
      metric("Coverage", fraction(melody("coverage_fraction")), "Доля трека, покрытая распознанными нотными интервалами."),
      metric("Interval pairs", value(melody("interval_pair_count")), "Пары последовательных неперекрывающихся нот внутри каждой партии."),
      metric("Mean absolute interval", value(melody("interval_abs_mean"), " st"), "Средний абсолютный интервал в полутонах."),
    ], distributions: [metric("Interval histogram", distribution(f[`melody_${source}_interval_histogram`], "interval"), "Интервал в полутонах → количество пар. Плюс – вверх, минус – вниз, 0 – повтор ноты; партии не смешиваются.")] },
  ];
}

function Rows({ rows }: { rows: Metric[] }) {
  return <dl className="metadata-grid sonara-feature-grid">
    {rows.map(row => <Fragment key={row.label}>
      <dt title={row.label}>{row.label}</dt>
      <dd>
        <span className="sonara-feature-value" title={Array.isArray(row.value) ? row.value.join(" / ") : row.value}>
          {Array.isArray(row.value) ? row.value.join(" / ") : row.value}
        </span>
        <span className="sonara-feature-description sonara-feature-description-separated sonara-feature-description-aligned" title={row.description}> # {row.description}</span>
      </dd>
    </Fragment>)}
  </dl>;
}

export function SheetSage2Features({ features }: { features: Features | null }) {
  const [source, setSource] = useState<SheetSage2MelodySource>("all");
  if (!features) return <span className="metadata-empty-state">SheetSage2 features ещё не рассчитаны</span>;
  return <div className="sonara-feature-groups sheetsage-feature-groups">
    {groups(features, source).map(group => <section className="feature-group sonara-feature-group" key={group.title}>
      <span className="sonara-feature-group-title">{group.title}</span>
      {group.title === "Melody" && <div className="feature-badges" role="group" aria-label="Источник мелодии">
        {(["all", "vocal", "instrumental"] as const).map(item => <button type="button" className="feature-badge" aria-pressed={source === item} onClick={() => setSource(item)} key={item}>{item === "all" ? "All" : item === "vocal" ? "Vocal" : "Instrumental"}</button>)}
      </div>}
      <Rows rows={[...group.rows, ...group.distributions]} />
    </section>)}
  </div>;
}
