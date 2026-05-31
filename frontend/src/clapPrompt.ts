export type ClapPromptPreset = {
  key: string;
  label: string;
  positiveHints: string[];
  positiveQueries: string[];
  negativeQueries: string[];
};

export type GeneratedClapPrompt = {
  query: string;
  avoidQuery: string;
  positiveQueries: string[];
  negativeQueries: string[];
  presetKey: string;
};

export const defaultClapPromptPresetKey = "adaptive_contrast";

export const clapPromptPresets: ClapPromptPreset[] = [
  {
    key: "adaptive_contrast",
    label: "Adaptive",
    positiveHints: ["clear defining musical features", "music recording"],
    positiveQueries: ["clear defining musical features in a music recording"],
    negativeQueries: ["unrelated generic music", "opposite mood and texture", "featureless background music"]
  },
  {
    key: "vocals_speech",
    label: "Vocals / Speech",
    positiveHints: ["vocals", "singing or spoken speech", "human voice"],
    positiveQueries: ["track with vocals and speech", "song with a clear human voice", "music with singing or spoken vocals"],
    negativeQueries: ["instrumental track without voices", "no vocals, no speech", "pure instrumental music"]
  },
  {
    key: "instrumental",
    label: "Instrumental",
    positiveHints: ["instrumental music", "no vocals", "no speech"],
    positiveQueries: ["instrumental track with no vocals", "music without singing or spoken voice", "pure instrumental recording"],
    negativeQueries: ["track with vocals and speech", "song with a prominent human voice", "rap or spoken vocals"]
  },
  {
    key: "dark_hypnotic",
    label: "Dark / Hypnotic",
    positiveHints: ["dark hypnotic atmosphere", "deep repetitive groove", "moody club texture"],
    positiveQueries: ["dark hypnotic electronic music", "deep repetitive moody club track", "shadowy minimal groove"],
    negativeQueries: ["bright cheerful pop music", "upbeat happy acoustic song", "light melodic mainstream music"]
  },
  {
    key: "peak_time_club",
    label: "Peak-time / Club",
    positiveHints: ["peak club energy", "driving dance floor groove", "strong rhythmic impact"],
    positiveQueries: ["peak time club track with driving energy", "high energy dance floor music", "powerful rhythmic electronic track"],
    negativeQueries: ["ambient drone without drums", "quiet background music", "slow sparse acoustic music"]
  },
  {
    key: "ambient_drone",
    label: "Ambient / Drone",
    positiveHints: ["ambient atmosphere", "drone texture", "slow spacious sound"],
    positiveQueries: ["ambient drone music with spacious texture", "slow atmospheric electronic music", "long evolving soundscape"],
    negativeQueries: ["peak time club drums", "fast dance floor track", "aggressive rhythmic techno"]
  },
  {
    key: "breaks_broken",
    label: "Breaks / Broken drums",
    positiveHints: ["broken drums", "syncopated breakbeat rhythm", "irregular groove"],
    positiveQueries: ["breakbeat track with broken drums", "syncopated broken rhythm electronic music", "irregular drum groove"],
    negativeQueries: ["straight four on the floor beat", "steady minimal kick pattern", "smooth regular house groove"]
  },
  {
    key: "acoustic_organic",
    label: "Acoustic / Organic",
    positiveHints: ["acoustic instruments", "organic performance", "natural timbre"],
    positiveQueries: ["organic acoustic music with natural instruments", "live instrumental performance", "warm acoustic texture"],
    negativeQueries: ["synthetic electronic club track", "digital drum machine music", "industrial electronic sound"]
  },
  {
    key: "industrial_ebm",
    label: "Industrial / EBM",
    positiveHints: ["industrial percussion", "EBM bassline", "mechanical dark energy"],
    positiveQueries: ["industrial EBM track with mechanical percussion", "dark electronic body music", "aggressive machine rhythm"],
    negativeQueries: ["soft acoustic pop song", "warm ambient soundscape", "gentle organic music"]
  }
];

export function generateClapPrompt({
  currentText,
  presetKey
}: {
  currentText: string;
  presetKey: string;
}): GeneratedClapPrompt {
  const preset = clapPromptPresets.find((item) => item.key === presetKey) || clapPromptPresets[0];
  const current = normalizePrompt(currentText);
  const query = current ? appendPromptHints(current, preset.positiveHints) : preset.positiveQueries[0];
  const positiveQueries = current
    ? uniquePrompts([query, ...preset.positiveQueries])
    : preset.positiveQueries;
  return {
    query,
    avoidQuery: preset.negativeQueries[0] || "",
    positiveQueries,
    negativeQueries: preset.negativeQueries,
    presetKey: preset.key
  };
}

export function promptQueriesFromText(query: string, avoidQuery: string) {
  const prompt = normalizePrompt(query);
  const avoid = normalizePrompt(avoidQuery);
  return {
    positiveQueries: prompt ? [prompt] : [],
    negativeQueries: avoid ? [avoid] : []
  };
}

function appendPromptHints(text: string, hints: string[]) {
  const normalized = text.toLowerCase();
  const additions = hints.filter((hint) => !normalized.includes(hint.toLowerCase()));
  if (!additions.length) return text;
  return `${text}, ${additions.join(", ")}`;
}

function normalizePrompt(value: string) {
  return value.trim().replace(/\s+/g, " ").replace(/\s*,\s*/g, ", ");
}

function uniquePrompts(values: string[]) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const normalized = normalizePrompt(value);
    const key = normalized.toLowerCase();
    if (!normalized || seen.has(key)) continue;
    seen.add(key);
    result.push(normalized);
  }
  return result;
}
