export type ClapPromptPreset = {
  key: string;
  label: string;
  query: string;
  negativeQuery: string;
};

export const defaultClapPromptPresetKey = "breaks_broken";

export const clapPromptPresets: ClapPromptPreset[] = [
  {
    key: "breaks_broken",
    label: "Breaks / Syncopated drums",
    query: [
      "breakbeat.",
      "This audio is a breakbeat track.",
      "This audio is a syncopated drum track.",
      "A breakbeat track with broken drums, syncopated percussion, irregular groove, shuffled hits, and off-grid rhythmic movement.",
      "An electronic club track with chopped drum breaks, uneven accents, and a restless rhythmic feel."
    ].join("\n"),
    negativeQuery: [
      "This audio is a straight four-on-the-floor house track.",
      "This audio has a steady minimal kick pattern.",
      "This audio is a smooth regular house groove.",
      "This audio has simple even drum timing and a steady kick."
    ].join("\n")
  },
  {
    key: "deep_warmup",
    label: "Deep Warm-up",
    query: [
      "deep warm-up.",
      "This audio is a deep warm-up club track.",
      "This audio is a restrained late-night electronic track.",
      "A deep warm-up club track with restrained energy, warm pads, subtle groove, soft low end, and late-night opening atmosphere.",
      "A low-pressure electronic dance track with smooth drums, muted textures, and patient opening-set movement."
    ].join("\n"),
    negativeQuery: [
      "This audio is a peak-time festival dance track.",
      "This audio has an aggressive drop and loud rave lead.",
      "This audio is a high-intensity club banger.",
      "This audio has hard drums, bright synth leads, and maximal energy."
    ].join("\n")
  },
  {
    key: "vocals_speech",
    label: "Vocals / Speech",
    query: [
      "vocals and speech.",
      "This audio is a vocal music track.",
      "This audio is a track with prominent human voice.",
      "A music recording with singing vocals, spoken speech, or a clear human voice present in the mix.",
      "A track where voice presence, sung phrases, spoken words, or vocal texture are defining audible features."
    ].join("\n"),
    negativeQuery: [
      "This audio is an instrumental electronic dance track.",
      "This audio is an instrumental club track focused on drums, bass, and texture.",
      "This audio is a rhythm-focused electronic track with percussion and low-end as the main elements.",
      "This audio is an instrumental ambient or club recording."
    ].join("\n")
  },
  {
    key: "vocals_music",
    label: "Vocals with Music",
    query: [
      "vocal music track.",
      "This audio is a music track with vocals.",
      "This audio is a song with singing over instrumental music.",
      "A full music track with prominent vocals, drums, bass, harmony, and produced instrumental backing.",
      "A vocal-led recording where singing or spoken phrases sit clearly over a musical arrangement."
    ].join("\n"),
    negativeQuery: [
      "This audio is speech or spoken word without music.",
      "This audio is an instrumental electronic dance track.",
      "This audio is isolated a cappella vocals without instrumental backing.",
      "This audio is beatless ambient instrumental music."
    ].join("\n")
  },
  {
    key: "instrumental",
    label: "Instrumental",
    query: [
      "instrumental electronic dance music.",
      "This audio is an instrumental electronic dance track.",
      "This audio is an instrumental club track.",
      "An instrumental club track focused on drums, bass, rhythm, harmony, and production texture.",
      "An electronic dance recording where percussion, low-end, and instrumental sound design carry the track."
    ].join("\n"),
    negativeQuery: [
      "This audio contains prominent singing vocals.",
      "This audio is a vocal pop song.",
      "This audio is rap music with spoken vocals.",
      "This audio is speech or spoken word."
    ].join("\n")
  },
  {
    key: "acoustic_organic",
    label: "Acoustic / Organic",
    query: [
      "acoustic organic music.",
      "This audio is an acoustic organic track.",
      "This audio is a natural instrument recording.",
      "An organic acoustic music recording with natural instruments, live performance feel, warm acoustic texture, and human timing.",
      "A track with live instrumental timbres, natural dynamics, and an earthy performance character."
    ].join("\n"),
    negativeQuery: [
      "This audio is a synthetic electronic club track.",
      "This audio is digital drum machine music.",
      "This audio has an industrial electronic sound.",
      "This audio is a heavily programmed electronic dance track."
    ].join("\n")
  },
  {
    key: "ambient_drone",
    label: "Ambient / Drone",
    query: [
      "ambient drone.",
      "This audio is an ambient drone track.",
      "This audio is a spacious atmospheric electronic piece.",
      "Ambient drone music with spacious texture, slow atmospheric movement, long evolving sound design, and minimal percussion.",
      "A slow electronic soundscape with sustained tones, soft layers, and an expansive meditative atmosphere."
    ].join("\n"),
    negativeQuery: [
      "This audio is a fast dance floor track.",
      "This audio has peak-time club drums.",
      "This audio is aggressive rhythmic techno.",
      "This audio has driving percussion, hard kick drums, and high club energy."
    ].join("\n")
  }
];

export function promptQueriesFromText(query: string, negativeQuery: string, useNegativePrompt = true) {
  return {
    positiveQueries: promptLinesFromText(query),
    negativeQueries: useNegativePrompt ? promptLinesFromText(negativeQuery) : []
  };
}

function promptLinesFromText(value: string) {
  return value
    .split(/\r?\n/)
    .map((line) => normalizePrompt(line))
    .filter(Boolean);
}

function normalizePrompt(value: string) {
  return value.trim().replace(/\s+/g, " ").replace(/\s*,\s*/g, ", ");
}
