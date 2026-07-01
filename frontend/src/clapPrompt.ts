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
    key: "dark_hypnotic",
    label: "Dark / Hypnotic",
    query: "dark hypnotic electronic music with a deep repetitive groove, restrained club pressure, shadowy texture, and minimal atmosphere",
    negativeQuery: "bright cheerful pop music, upbeat happy acoustic song, light melodic mainstream music"
  },
  {
    key: "peak_time_club",
    label: "Peak-time / Club",
    query: "peak time club track with driving dance floor energy, strong rhythmic impact, heavy momentum, and loud electronic drums",
    negativeQuery: "ambient drone without drums, quiet background music, slow sparse acoustic music"
  },
  {
    key: "ambient_drone",
    label: "Ambient / Drone",
    query: "ambient drone music with spacious texture, slow atmospheric movement, long evolving sound design, and minimal percussion",
    negativeQuery: "peak time club drums, fast dance floor track, aggressive rhythmic techno"
  },
  {
    key: "breaks_broken",
    label: "Breaks / Broken drums",
    query: "breakbeat track with broken drums, syncopated percussion, irregular groove, shuffled hits, and off-grid rhythmic movement",
    negativeQuery: "straight four on the floor beat, steady minimal kick pattern, smooth regular house groove"
  },
  {
    key: "dub_techno",
    label: "Dub Techno",
    query: "dub techno with deep sub bass, chord stabs, tape delay, spacious reverb, steady pulse, and smoky club atmosphere",
    negativeQuery: "dry acoustic song, bright festival EDM, vocal pop hook, aggressive distorted industrial rhythm"
  },
  {
    key: "acid_303",
    label: "Acid / 303",
    query: "acid electronic track with squelchy resonant 303 bassline, evolving filter movement, club drums, and psychedelic machine groove",
    negativeQuery: "organic acoustic instruments, smooth deep house without acid bass, ambient pad music without drums"
  },
  {
    key: "electro_bass",
    label: "Electro / Bass",
    query: "electro track with broken machine funk, punchy synthetic bass, robotic percussion, crisp snares, and futuristic dance floor groove",
    negativeQuery: "straight four on the floor techno, acoustic live drums, soft ambient drone, vocal pop song"
  },
  {
    key: "tribal_percussive",
    label: "Tribal / Percussive",
    query: "percussive club track with tribal drums, rolling hand percussion, syncopated rhythm layers, and physical dance floor momentum",
    negativeQuery: "minimal ambient texture, sparse beatless drone, vocal ballad, smooth straight kick pattern without percussion layers"
  },
  {
    key: "deep_warmup",
    label: "Deep Warm-up",
    query: "deep warm-up club track with restrained energy, warm pads, subtle groove, soft low end, and late-night opening atmosphere",
    negativeQuery: "peak time banger, aggressive drop, loud festival lead, high intensity rave drums"
  },
  {
    key: "leftfield_weird",
    label: "Leftfield / Weird",
    query: "leftfield electronic music with unusual texture, odd rhythm, experimental sound design, strange mood, and non-obvious arrangement",
    negativeQuery: "formulaic mainstream pop, predictable club anthem, generic background music, polished radio song"
  },
  {
    key: "acoustic_organic",
    label: "Acoustic / Organic",
    query: "organic acoustic music with natural instruments, live performance feel, warm acoustic texture, and human timing",
    negativeQuery: "synthetic electronic club track, digital drum machine music, industrial electronic sound"
  },
  {
    key: "industrial_ebm",
    label: "Industrial / EBM",
    query: "industrial EBM track with mechanical percussion, dark electronic body music bassline, machine rhythm, and aggressive energy",
    negativeQuery: "soft acoustic pop song, warm ambient soundscape, gentle organic music"
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
