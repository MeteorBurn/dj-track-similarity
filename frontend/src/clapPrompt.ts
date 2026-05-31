export type ClapPromptPreset = {
  key: string;
  label: string;
  query: string;
  avoidQuery: string;
};

export const defaultClapPromptPresetKey = "adaptive_contrast";

export const clapPromptPresets: ClapPromptPreset[] = [
  {
    key: "adaptive_contrast",
    label: "Adaptive",
    query: "clear defining musical features in a music recording, strong identifiable mood, rhythm, texture, and arrangement",
    avoidQuery: "unrelated generic music, opposite mood and texture, featureless background music"
  },
  {
    key: "vocals_speech",
    label: "Vocals / Speech",
    query: "track with vocals, singing, spoken speech, or a clear human voice present in the music",
    avoidQuery: "instrumental track without voices, no vocals, no speech, pure instrumental music"
  },
  {
    key: "instrumental",
    label: "Instrumental",
    query: "instrumental music with no singing and no spoken voice, focused on rhythm, harmony, and instrumental texture",
    avoidQuery: "track with vocals and speech, song with a prominent human voice, rap or spoken vocals"
  },
  {
    key: "dark_hypnotic",
    label: "Dark / Hypnotic",
    query: "dark hypnotic electronic music with a deep repetitive groove, moody club texture, and shadowy minimal atmosphere",
    avoidQuery: "bright cheerful pop music, upbeat happy acoustic song, light melodic mainstream music"
  },
  {
    key: "peak_time_club",
    label: "Peak-time / Club",
    query: "peak time club track with driving dance floor energy, strong rhythmic impact, heavy momentum, and loud electronic drums",
    avoidQuery: "ambient drone without drums, quiet background music, slow sparse acoustic music"
  },
  {
    key: "ambient_drone",
    label: "Ambient / Drone",
    query: "ambient drone music with spacious texture, slow atmospheric movement, long evolving sound design, and minimal percussion",
    avoidQuery: "peak time club drums, fast dance floor track, aggressive rhythmic techno"
  },
  {
    key: "breaks_broken",
    label: "Breaks / Broken drums",
    query: "breakbeat track with broken drums, syncopated percussion, irregular groove, shuffled hits, and off-grid rhythmic movement",
    avoidQuery: "straight four on the floor beat, steady minimal kick pattern, smooth regular house groove"
  },
  {
    key: "acoustic_organic",
    label: "Acoustic / Organic",
    query: "organic acoustic music with natural instruments, live performance feel, warm acoustic texture, and human timing",
    avoidQuery: "synthetic electronic club track, digital drum machine music, industrial electronic sound"
  },
  {
    key: "industrial_ebm",
    label: "Industrial / EBM",
    query: "industrial EBM track with mechanical percussion, dark electronic body music bassline, machine rhythm, and aggressive energy",
    avoidQuery: "soft acoustic pop song, warm ambient soundscape, gentle organic music"
  }
];

export function promptQueriesFromText(query: string, avoidQuery: string) {
  const prompt = normalizePrompt(query);
  const avoid = normalizePrompt(avoidQuery);
  return {
    positiveQueries: prompt ? [prompt] : [],
    negativeQueries: avoid ? [avoid] : []
  };
}

function normalizePrompt(value: string) {
  return value.trim().replace(/\s+/g, " ").replace(/\s*,\s*/g, ", ");
}
