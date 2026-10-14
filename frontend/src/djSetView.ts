import type { DjSetBuildResponse, DjSetFunnelKey, DjSetSlot, DjSetStage } from "./api";

/** The numbers of a stage the tab edits; its rules are the preset's own. */
export type DjSetStageField = "share" | "intensity_start" | "intensity_end" | "bpm_start" | "bpm_end";

/** The target of one slot, and the stage (by index) it belongs to. */
export type DjSetSlotPlan = { stage: number; intensity: number; bpm: number };

/** The words for what the server defines by key: `short` is the one word a
 * preset card has room for. The numbers and rules of a preset are the
 * server's alone; nothing here repeats them. */
const presetCopy: Record<string, { name: string; short: string; summary: string; stages: Record<string, string> }> = {
  hypnotic_loop: {
    name: "Hypnotic Loop",
    short: "Loop",
    summary: "Темп почти стоит, растёт плотность деталей; в конце сет отпускает.",
    stages: { start: "старт", texture: "фактура", peak: "пик", outro: "выход" },
  },
  textural_blend: {
    name: "Textural Blend",
    short: "Blend",
    summary: "Один темп и одна атмосфера, меняется только грув: прямая бочка переходит в ломаный ритм. Грув ведут классификаторы.",
    stages: { straight: "прямой", broken: "ломаный" },
  },
  melancholic_plateau: {
    name: "Melancholic Plateau",
    short: "Plateau",
    summary: "Ровное плато без пиков: интенсивность дышит в одной полосе, темп стоит. Настроение задаёт ориентир.",
    stages: { start: "старт", deepening: "погружение", dip: "провал", drive: "ход", resolution: "развязка" },
  },
  progressive_acceleration: {
    name: "Progressive Acceleration",
    short: "Accel",
    summary: "Прямой подъём темпа и плотности от первого трека к последнему, без спадов.",
    stages: { groove: "грув", build: "нагнетание", tension: "напряжение", peak: "пик" },
  },
  arch: {
    name: "The Arch",
    short: "Arch",
    summary: "Разогрев, подъём к пику в середине и долгий спад к тихому финалу.",
    stages: { calm: "начало", development: "развитие", climax: "пик", decline: "спад", closing: "финал" },
  },
  twin_summits: {
    name: "Twin Summits",
    short: "Summits",
    summary: "Два пика и намеренная долина между ними: после неё второй пик звучит выше.",
    stages: { opening: "начало", summit_1: "пик I", valley: "долина", summit_2: "пик II", release: "отпускание" },
  },
  staircase: {
    name: "The Staircase",
    short: "Stairs",
    summary: "Террасы: уровень держится несколько треков, потом один переход поднимает весь сет.",
    stages: { terrace_1: "терраса I", terrace_2: "терраса II", terrace_3: "терраса III", terrace_4: "терраса IV" },
  },
  harmonic_spiral: {
    name: "Harmonic Spiral",
    short: "Spiral",
    summary: "Темп стоит, движется тональность: шаги по кругу Camelot со сменой лада. Стартовый ключ задаёт трек в слоте 1, иначе зерно.",
    stages: { anchor: "якорь", step: "шаг", flip: "лад", wide: "шире", back: "возврат" },
  },
  long_descent: {
    name: "The Long Descent",
    short: "Descent",
    summary: "Старт с пика и постепенное снятие слоёв до тихого финала.",
    stages: { inherit: "пик", strip_1: "снятие I", strip_2: "снятие II", strip_3: "снятие III", finish: "финал" },
  },
  genre_drift: {
    name: "Genre Drift",
    short: "Drift",
    summary: "Плотность растёт понемногу, меняется жанр: от minimal/deep-tech к ломаному ритму, без резкой смены. Жанр ведут классификаторы.",
    stages: { home: "дом", neighbour: "рядом", crossover: "стык", territory: "слом", arrival: "финал" },
  },
};

const funnelLabels: Record<DjSetFunnelKey, string> = {
  library: "библиотека",
  sonara: "с SONARA",
  bpm_band: "коридор BPM",
  tempo: "надёжный темп",
  grid: "ровная сетка",
  pool: "порода",
  direction: "смещение",
};

function readable(key: string) {
  return key.replaceAll("_", " ");
}

export function djSetPresetName(preset: string) {
  return presetCopy[preset]?.name ?? readable(preset);
}

export function djSetPresetShortName(preset: string) {
  return presetCopy[preset]?.short ?? readable(preset);
}

export function djSetPresetSummary(preset: string) {
  return presetCopy[preset]?.summary ?? "";
}

type DjSetStageRules = Pick<DjSetStage, "key_step" | "key_flip" | "classifiers">;

/** What a stage asks of its tracks beyond intensity and tempo, one phrase per rule. */
export function djSetStageRules({ key_step, key_flip, classifiers }: DjSetStageRules) {
  const rules: string[] = [];
  if (key_step !== null) {
    const key = key_step === 0 ? "ключ старта" : `ключ ${key_step > 0 ? "+" : "−"}${Math.abs(key_step)} по Camelot`;
    rules.push(key_flip ? `${key}, другой лад` : key);
  }
  for (const { classifier_key, low, high } of classifiers) {
    rules.push(`${classifier_key.replaceAll("_", "-")} ${low}–${high}`);
  }
  return rules;
}

/** The rules of a preset as traces for its thumbnail, one value (0..1) per
 * stage: the key walk, then the middle of every classifier range. */
export function djSetRuleTraces(stages: DjSetStageRules[]): number[][] {
  const traces: number[][] = [];
  if (stages.every((stage) => stage.key_step !== null)) {
    const positions = stages.map((stage) => (stage.key_step ?? 0) + (stage.key_flip ? 0.5 : 0));
    const low = Math.min(...positions);
    const span = Math.max(...positions) - low || 1;
    traces.push(positions.map((position) => 0.15 + ((position - low) / span) * 0.7));
  }
  const classifierKeys = [...new Set(stages.flatMap((stage) => stage.classifiers.map((range) => range.classifier_key)))];
  for (const key of classifierKeys) {
    const ranges = stages.map((stage) => stage.classifiers.find((range) => range.classifier_key === key));
    if (ranges.every((range) => range !== undefined)) {
      traces.push(ranges.map((range) => (range.low + range.high) / 2));
    }
  }
  return traces;
}

export function djSetStageLabel(preset: string, stage: string) {
  return presetCopy[preset]?.stages[stage] ?? readable(stage);
}

export function djSetFunnelLabel(key: DjSetFunnelKey) {
  return funnelLabels[key] ?? key;
}

/** Slots per stage: at least one each, the rest by share — the server's rule. */
function stageCounts(tracks: number, stages: DjSetStage[]) {
  const total = stages.reduce((sum, stage) => sum + stage.share, 0);
  const raw = stages.map((stage) => (stage.share / total) * tracks);
  const counts = raw.map((value) => Math.max(1, Math.floor(value)));
  const sum = () => counts.reduce((value, count) => value + count, 0);
  while (sum() < tracks) {
    let pick = 0;
    raw.forEach((value, index) => {
      if (value - counts[index] > raw[pick] - counts[pick]) pick = index;
    });
    counts[pick] += 1;
  }
  while (sum() > tracks) {
    let pick = -1;
    raw.forEach((value, index) => {
      if (counts[index] > 1 && (pick < 0 || value - counts[index] < raw[pick] - counts[pick])) pick = index;
    });
    if (pick < 0) break;
    counts[pick] -= 1;
  }
  return counts;
}

/** The target of every slot, as the server plans it: a stage's slots run
 * evenly from its start to its end, and a one-slot stage takes the middle. */
export function djSetSlotPlan(tracks: number, stages: DjSetStage[]): DjSetSlotPlan[] {
  const plan: DjSetSlotPlan[] = [];
  stageCounts(tracks, stages).forEach((count, stage) => {
    const { intensity_start, intensity_end, bpm_start, bpm_end } = stages[stage];
    for (let position = 0; position < count; position += 1) {
      const fraction = count === 1 ? 0.5 : position / (count - 1);
      plan.push({
        stage,
        intensity: intensity_start + (intensity_end - intensity_start) * fraction,
        bpm: bpm_start + (bpm_end - bpm_start) * fraction,
      });
    }
  });
  return plan;
}

/** The chip of a set row: where the slot sits in the set, the tempo it got
 * and, on a stage that walks the key, the key it got. */
export function djSetSlotReason(slot: DjSetSlot, preset: string, stages: DjSetStage[]) {
  const walksKey = stages.find((stage) => stage.key === slot.stage)?.key_step != null;
  return [
    `${djSetStageLabel(preset, slot.stage)}${slot.drop_entry ? " (сброс)" : ""}`,
    `${slot.score_breakdown.bpm.toFixed(1)} BPM`,
    ...(walksKey && slot.track.sonara_key_camelot ? [slot.track.sonara_key_camelot] : []),
    ...(slot.pinned ? ["закреплён"] : []),
    ...(slot.out_of_tolerance ? ["темп вне допуска"] : []),
  ].join(" · ");
}

/** What the audit of the built order counted, and what the build ran with. */
export function djSetAuditText(response: DjSetBuildResponse) {
  return [
    djSetPresetName(response.preset),
    `переходов ${response.audit.transitions}`,
    `вне допуска ${response.audit.out_of_tolerance}`,
    ...(response.audit.worst_slot === null ? [] : [`труднее всего вход в слот ${response.audit.worst_slot}`]),
    `зерно ${response.seed}`,
    `${response.elapsed_seconds.toFixed(1)} с`,
  ].join(" · ");
}
