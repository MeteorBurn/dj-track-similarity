export type ClapPromptPreset = {
  key: string;
  label: string;
  query: string;
  negativeQuery: string;
};

export const defaultClapPromptPresetKey = "adaptive_contrast";

export const clapPromptPresets: ClapPromptPreset[] = [
  {
    key: "adaptive_contrast",
    label: "Adaptive",
    query: "clear defining musical features in a music recording, identifiable groove, mood, texture, arrangement, and production character",
    negativeQuery: "unrelated generic music, opposite mood and texture, featureless background music, vague indistinct recording"
  },
  {
    key: "breaks_broken",
    label: "Breaks / Syncopated drums",
    query: "breakbeat track with broken drums, syncopated percussion, irregular groove, shuffled hits, and off-grid rhythmic movement",
    negativeQuery: "straight four on the floor beat, steady minimal kick pattern, smooth regular house groove"
  },
  {
    key: "deep_warmup",
    label: "Deep Warm-up",
    query: "deep warm-up club track with restrained energy, warm pads, subtle groove, soft low end, and late-night opening atmosphere",
    negativeQuery: "peak time banger, aggressive drop, loud festival lead, high intensity rave drums"
  },
  {
    key: "vocals_speech",
    label: "Vocals / Speech",
    query: "track with vocals, singing, spoken speech, or a clear human voice present in the music",
    negativeQuery: "instrumental track without voices, no vocals, no speech, pure instrumental music"
  },
  {
    key: "instrumental",
    label: "Instrumental",
    query: "instrumental music with no singing and no spoken voice, focused on rhythm, harmony, and instrumental texture",
    negativeQuery: "track with vocals and speech, song with a prominent human voice, rap or spoken vocals"
  },
  {
    key: "acoustic_organic",
    label: "Acoustic / Organic",
    query: "organic acoustic music with natural instruments, live performance feel, warm acoustic texture, and human timing",
    negativeQuery: "synthetic electronic club track, digital drum machine music, industrial electronic sound"
  },
  {
    key: "ambient_drone",
    label: "Ambient / Drone",
    query: "ambient drone music with spacious texture, slow atmospheric movement, long evolving sound design, and minimal percussion",
    negativeQuery: "peak time club drums, fast dance floor track, aggressive rhythmic techno"
  }
];

export function promptQueriesFromText(query: string, negativeQuery: string, useNegativePrompt = true) {
  const prompt = normalizePrompt(query);
  const negative = useNegativePrompt ? normalizePrompt(negativeQuery) : "";
  return {
    positiveQueries: prompt ? [prompt] : [],
    negativeQueries: negative ? [negative] : []
  };
}

function normalizePrompt(value: string) {
  return value.trim().replace(/\s+/g, " ").replace(/\s*,\s*/g, ", ");
}
