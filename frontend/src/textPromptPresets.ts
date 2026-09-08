export type TextPromptModel = "clap" | "mulan";

export type PromptVariants = {
  shared: string[];
  clap?: string[];
  mulan?: string[];
};

export type NegativeWeight = number | { clap: number; mulan: number };

export type TextPromptPreset = {
  key: string;
  axis: string;
  label: string;
  hint: string;
  positive: PromptVariants;
  negative?: PromptVariants;
  negativeWeight: NegativeWeight;
};

export type TextPromptCategory = {
  key: string;
  label: string;
};

export type TextPromptAxis = {
  key: string;
  label: string;
  hint: string;
  category: string;
};

export const textPromptCategories: TextPromptCategory[] = [
  { key: "movement", label: "Ритм и движение" },
  { key: "sound", label: "Характер звучания" },
  { key: "emotion", label: "Настроение" }
];

export const textPromptAxes: TextPromptAxis[] = [
  { key: "rhythm", label: "Rhythm", category: "movement", hint: "Рисунок ударных и расположение акцентов." },
  { key: "groove", label: "Groove", category: "movement", hint: "Свинг, микротайминг и ощущение движения." },
  { key: "percussion", label: "Percussion", category: "movement", hint: "Тембр и артикуляция перкуссионных звуков." },
  { key: "bass", label: "Bass", category: "sound", hint: "Характер и движение низких частот." },
  { key: "instruments", label: "Instruments", category: "sound", hint: "Узнаваемые тембры акустических и электрических инструментов, в том числе в сэмплах." },
  { key: "texture", label: "Texture", category: "sound", hint: "Поверхность и плотность звучания." },
  { key: "mood", label: "Mood", category: "emotion", hint: "Эмоциональный характер звучания." }
];

// Add each label after its model-specific banks have been prepared for listening.
export const textPromptPresets: TextPromptPreset[] = [
  {
    key: "rhythm/four-on-the-floor",
    axis: "rhythm",
    label: "4/4",
    hint: "Ровный кик на каждой из четырёх долей такта.",
    positive: {
      shared: [],
      clap: [
        "The track has a four-on-the-floor beat.",
        "A track with a kick on every beat.",
        "This track features four-on-the-floor, kicks, quarter notes.",
        "A track with four-on-the-floor, steady kicks, on-beat hits.",
        "This track features a steady kick drum on every beat.",
        "The track places four evenly spaced kick hits on the four beats of each bar."
      ],
      mulan: [
        "Four-on-the-floor rhythm.",
        "A four-on-the-floor track.",
        "four-on-the-floor, kick, quarter notes",
        "four-on-the-floor, steady kick, on-beat",
        "A kick drum lands on all four beats of each bar.",
        "The kick repeats once per quarter note throughout the four-beat pattern."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "rhythm/breakbeat",
    axis: "rhythm",
    label: "Breakbeat",
    hint: "Ломаный рисунок ударных с синкопированными акцентами.",
    positive: {
      shared: [],
      clap: [
        "The track has a breakbeat drum pattern.",
        "A track with a broken drum rhythm.",
        "This track features breakbeat, syncopation, backbeats.",
        "A track with drum breaks, offbeat accents, percussion.",
        "This track features a broken rhythm with syncopated kick and snare hits.",
        "The track repeats a drum break whose irregular kicks interlock with snare backbeats."
      ],
      mulan: [
        "Breakbeat rhythm.",
        "A breakbeat track.",
        "breakbeat, syncopation, backbeat",
        "drum breaks, offbeat, percussion",
        "The drums repeat a break with irregular kicks and snare backbeats.",
        "The kick and snare interlock in a repeating broken pattern."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "rhythm/syncopated",
    axis: "rhythm",
    label: "Syncopated",
    hint: "Акценты на слабых долях и слабых частях доли.",
    positive: {
      shared: [],
      clap: [
        "The track has a syncopated rhythm.",
        "A track with offbeat rhythmic accents.",
        "This track features syncopation, offbeat accents, weak beats.",
        "A track with syncopated rhythm, weak beats, displaced accents.",
        "This track emphasizes offbeats in its rhythmic pattern.",
        "The track places rhythmic accents on weak beats and offbeat subdivisions."
      ],
      mulan: [
        "Syncopated rhythm.",
        "A syncopated track.",
        "syncopation, offbeat, accents",
        "syncopated rhythm, weak beats, displaced accents",
        "The rhythm places accents on weak beats and offbeat subdivisions.",
        "Rhythmic emphasis shifts away from the expected strong beats."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "rhythm/polyrhythm",
    axis: "rhythm",
    label: "Polyrhythm",
    hint: "Одновременное наложение разных ритмических делений общего временного отрезка.",
    positive: {
      shared: [],
      clap: [
        "The track features polyrhythms.",
        "A track with simultaneous cross-rhythms.",
        "This track features polyrhythm, cross-rhythms, subdivisions.",
        "A track with cross-rhythms, overlapping pulses.",
        "This track layers contrasting rhythmic divisions at the same time.",
        "The track combines cross-rhythms that divide the same time span differently."
      ],
      mulan: [
        "Polyrhythmic pattern.",
        "A polyrhythmic track.",
        "polyrhythm, cross-rhythms, subdivisions",
        "cross-rhythms, overlapping pulses",
        "Different rhythmic divisions overlap within the same time span.",
        "Simultaneous rhythmic layers divide a common duration in contrasting ways."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "rhythm/shuffle",
    axis: "rhythm",
    label: "Shuffle",
    hint: "Повторяющийся рисунок ударов по первой и третьей частям триоли.",
    positive: {
      shared: [],
      clap: [
        "The track has a shuffle beat.",
        "A track with a triplet-based shuffle.",
        "This track features shuffle, triplets, long-short pairs.",
        "A track with shuffle beats, triplet pairs.",
        "This track repeats long-short drum pairs within a triplet-based pulse.",
        "The track places drum hits on the first and third subdivisions of each triplet."
      ],
      mulan: [
        "Shuffle rhythm.",
        "A shuffle-beat track.",
        "shuffle, triplets, long-short",
        "shuffle beat, triplet pairs",
        "Drum hits fall on the first and third parts of each triplet.",
        "The drums repeat long-short pairs over a triplet subdivision."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/straight",
    axis: "groove",
    label: "Straight",
    hint: "Равномерное деление пульса на одинаковые по длительности части.",
    positive: {
      shared: [],
      clap: [
        "The track has a straight groove.",
        "A track with even rhythmic subdivisions.",
        "This track features straight timing, even subdivisions.",
        "A track with straight subdivisions, equal spacing.",
        "This track divides the pulse into equal intervals.",
        "The track spaces its rhythmic subdivisions evenly within each beat."
      ],
      mulan: [
        "Straight groove.",
        "A track with straight subdivisions.",
        "straight, even subdivisions",
        "straight timing, equal spacing",
        "The pulse divides into intervals of the same duration.",
        "Rhythmic subdivisions have equal spacing within each beat."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/swing",
    axis: "groove",
    label: "Swing",
    hint: "Чередование длинных и коротких подразделений доли.",
    positive: {
      shared: [],
      clap: [
        "The track has a swung groove.",
        "A track with a swing feel.",
        "This track features swing, long-short timing, uneven subdivisions.",
        "A track with swung timing, delayed offbeats.",
        "This track alternates long and short subdivisions for a swing feel.",
        "The track delays the offbeat within each pair of swung subdivisions."
      ],
      mulan: [
        "Swung groove.",
        "A track with swing.",
        "swing, long-short, uneven subdivisions",
        "swung timing, delayed offbeats",
        "Paired subdivisions alternate between longer and shorter intervals.",
        "The offbeat lands later within each pair to create a swing feel."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/laid-back",
    axis: "groove",
    label: "Laid-back",
    hint: "Ритмические акценты слегка отстают от основной пульсации.",
    positive: {
      shared: [],
      clap: [
        "The track has a behind-the-beat groove.",
        "A track with laid-back rhythmic timing.",
        "This track features laid-back timing, microtiming, delayed accents.",
        "A track with behind-the-beat phrasing, delayed accents.",
        "This track places rhythmic phrases slightly behind the beat.",
        "The track's rhythmic accents land slightly later than their expected beat positions."
      ],
      mulan: [
        "Behind-the-beat groove.",
        "A track with laid-back timing.",
        "laid-back, behind-the-beat, microtiming",
        "delayed accents, laid-back timing",
        "Rhythmic accents lag slightly behind their expected beat positions.",
        "The phrasing sits just behind the underlying beat."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/driving",
    axis: "groove",
    label: "Driving",
    hint: "Ритмическое движение с выраженным ощущением продвижения вперёд.",
    positive: {
      shared: [],
      clap: [
        "The track has a driving groove.",
        "A track with a propulsive rhythmic feel.",
        "This track features driving grooves, propulsion, momentum.",
        "A track with driving rhythms, rhythmic propulsion.",
        "This track has an insistent, propulsive rhythmic pulse.",
        "The track's beat maintains a continuous sense of forward momentum."
      ],
      mulan: [
        "Driving groove.",
        "A track with rhythmic propulsion.",
        "driving, propulsive, momentum",
        "driving groove, rhythmic propulsion",
        "The rhythm maintains a strong forward push.",
        "The beat creates a continuous sense of rhythmic propulsion."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/bouncy",
    axis: "groove",
    label: "Bouncy",
    hint: "Пружинистое ритмическое движение с ощущением отскока.",
    positive: {
      shared: [],
      clap: [
        "The track has a bouncy groove.",
        "A track with a springy rhythmic feel.",
        "This track features bounce, springiness, rhythmic rebound.",
        "A track with bouncy grooves, rhythmic bounce.",
        "This track's rhythmic movement feels springy.",
        "The track's beat has a clear sense of bounce from one pulse to the next."
      ],
      mulan: [
        "Bouncy groove.",
        "A track with a springy pulse.",
        "bouncy, springy, rebound",
        "bouncy groove, rhythmic bounce",
        "The beat has a clear sense of bounce.",
        "The groove moves with a springy rebound between pulses."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/wooden",
    axis: "percussion",
    label: "Wooden",
    hint: "Деревянный стук и щелчки клавес, кастаньет и вудблоков.",
    positive: {
      shared: [],
      clap: [
        "The track features wooden percussion sounds.",
        "A track with woody knocks and clicks.",
        "This track features wooden percussion, claves, castanets, woodblocks.",
        "A track with woody clicks, hollow knocks, wooden percussion tones.",
        "The track's percussion has the hollow knocking tone of struck woodblocks.",
        "The track uses crisp wooden clicks and short woody knocks as percussion sounds."
      ],
      mulan: [
        "Wooden percussion.",
        "Woody knocks and clicks.",
        "wooden percussion, claves, castanets, woodblocks",
        "woody clicks, hollow knocks, wooden tones",
        "Struck woodblocks give the percussion a hollow wooden knocking tone.",
        "Crisp wooden clicks and short woody knocks shape the percussion sound."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/shakers",
    axis: "percussion",
    label: "Shakers",
    hint: "Шейкеры и маракасы: перекатывающийся, шуршащий звук от встряхивания.",
    positive: {
      shared: [],
      clap: [
        "The track features shaker percussion.",
        "A track with shaken percussion rattles.",
        "This track features shakers, maracas, shaken percussion.",
        "A track with shaker sounds, swishing rattles, maraca tones.",
        "The track's percussion includes the rolling rattle of loose material inside a shaken instrument.",
        "Recognizable shaker sounds form a swishing, rattling percussion part in the track."
      ],
      mulan: [
        "Shaker percussion.",
        "A track with rattling shakers.",
        "shakers, maracas, shaken percussion",
        "shaker sounds, swishing rattles, maraca tones",
        "Loose material rattles inside a shaken percussion instrument.",
        "Shaker rattles are audible as a percussion part in the music."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/machine",
    axis: "percussion",
    label: "Machine",
    hint: "Синтетические тембры драм-машин и электронные ударные звуки.",
    positive: {
      shared: [],
      clap: [
        "The track features drum-machine percussion.",
        "A track with synthesized percussion sounds.",
        "This track features drum machines, electronic drums, synthesized hits.",
        "A track with synthetic percussion, electronic drum tones.",
        "The track uses electronically generated percussion sounds with a synthetic character.",
        "The track's percussion is voiced with the distinctive tones of a drum machine."
      ],
      mulan: [
        "Drum-machine percussion.",
        "Synthesized percussion sounds.",
        "drum machine, electronic drums, synthesized hits",
        "synthetic percussion, electronic drum tones",
        "The percussion uses electronically generated sounds with a synthetic character.",
        "Distinctive drum-machine tones shape the sound of the percussion."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/micro",
    axis: "percussion",
    label: "Micro",
    hint: "Мелкие короткие щелчки, тики и точечные перкуссионные удары.",
    positive: {
      shared: [],
      clap: [
        "The track features tiny percussive clicks.",
        "A track with micro-percussion details.",
        "This track features percussive clicks, ticks, tiny taps.",
        "A track with micro-percussion, short transients, pinpoint hits.",
        "The track uses small clicks and short taps as distinct percussion sounds.",
        "The track's individual percussion hits have a tiny, sharply defined character."
      ],
      mulan: [
        "Micro-percussion.",
        "Tiny percussive clicks and taps.",
        "percussive clicks, ticks, tiny taps",
        "micro-percussion, short transients, pinpoint hits",
        "Small clicks and short taps form distinct percussion details.",
        "Individual percussion sounds have brief attacks and a tiny, sharply defined character."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/tribal",
    axis: "percussion",
    label: "Tribal",
    hint: "Ансамбль ручных барабанов: резонанс мембран, удары ладонями и пальцами.",
    positive: {
      shared: [],
      clap: [
        "The track features tribal-style hand-drum percussion.",
        "A track with an ensemble of resonant hand drums.",
        "This track features hand drums, drumhead resonance, palm slaps.",
        "A track with tribal percussion, finger taps, drumhead tones.",
        "The track's hand-drum ensemble combines rounded drumhead resonance with palm and finger strikes.",
        "The track's percussion carries resonant drumhead tones and the distinct slap of hands on drums."
      ],
      mulan: [
        "Tribal-style hand-drum percussion.",
        "An ensemble of resonant hand drums.",
        "hand drums, drumhead resonance, palm slaps",
        "tribal percussion, finger taps, drumhead tones",
        "An ensemble of hand drums combines rounded drumhead resonance with palm and finger strikes.",
        "Resonant drumhead tones and the slap of hands on drums define the percussion sound."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/guitar",
    axis: "instruments",
    label: "Guitar",
    hint: "Акустическая, классическая или электрогитара: аккорды, риффы и мелодии.",
    positive: {
      shared: [],
      clap: [
        "The track features guitar.",
        "A track with a recognizable guitar part.",
        "This track features guitar, acoustic guitar, electric guitar.",
        "A track with guitar chords, guitar riffs, guitar melodies.",
        "Recognizable guitar tones can be heard within the track.",
        "The music includes strummed guitar chords, picked notes, or a guitar melody."
      ],
      mulan: [
        "Guitar instrumentation.",
        "A track featuring guitar.",
        "guitar, acoustic guitar, electric guitar",
        "guitar chords, guitar riffs, guitar melodies",
        "A guitar part is audible within the music.",
        "The arrangement features acoustic or electric guitar tones."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/piano",
    axis: "instruments",
    label: "Piano",
    hint: "Рояль, пианино или электрическое пиано: узнаваемые фортепианные партии.",
    positive: {
      shared: [],
      clap: [
        "The track features piano.",
        "A track with acoustic or electric piano.",
        "This track features piano, grand piano, upright piano.",
        "A track with electric piano, piano chords, piano melodies.",
        "Recognizable piano notes or chords are audible within the track.",
        "The arrangement includes a melody or accompaniment with a piano timbre."
      ],
      mulan: [
        "Piano instrumentation.",
        "A track featuring piano.",
        "piano, grand piano, upright piano",
        "electric piano, piano chords, piano melodies",
        "A recognizable piano part is audible within the music.",
        "Acoustic or electric piano tones provide melody or accompaniment."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/strings",
    axis: "instruments",
    label: "Strings",
    hint: "Скрипка, альт, виолончель или контрабас; сольные партии и струнные секции, смычок и пиццикато.",
    positive: {
      shared: [],
      clap: [
        "The track features orchestral strings.",
        "A track with violin, viola, or cello.",
        "This track features orchestral strings, violin, viola.",
        "A track with cello, double bass, string ensemble.",
        "A solo orchestral string instrument or a string section is audible in the track.",
        "The arrangement uses bowed or pizzicato orchestral-string timbres."
      ],
      mulan: [
        "Orchestral string instrumentation.",
        "A track featuring violin, viola, or cello.",
        "orchestral strings, violin, viola",
        "cello, double bass, string ensemble",
        "The music features a solo orchestral string part or a string section.",
        "Bowed or pizzicato orchestral-string tones are audible in the arrangement."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/brass",
    axis: "instruments",
    label: "Brass",
    hint: "Медные духовые: труба, тромбон или валторна, по отдельности или в секции.",
    positive: {
      shared: [],
      clap: [
        "The track features brass instruments.",
        "A track with a recognizable brass part.",
        "This track features brass, trumpet, trombone.",
        "A track with brass tones, French horn, brass section.",
        "Trumpet, trombone, or horn tones can be heard within the track.",
        "A brass instrument or brass ensemble contributes melody or accompaniment."
      ],
      mulan: [
        "Brass instrumentation.",
        "A track featuring brass instruments.",
        "brass, trumpet, trombone",
        "brass tones, french horn, brass section",
        "A recognizable brass part is audible within the music.",
        "The arrangement includes a solo brass instrument or a brass ensemble."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/woodwinds",
    axis: "instruments",
    label: "Woodwinds",
    hint: "Деревянные духовые: саксофон, флейта или кларнет, сольные партии и ансамбли.",
    positive: {
      shared: [],
      clap: [
        "The track features woodwind instruments.",
        "A track with a recognizable woodwind part.",
        "This track features woodwinds, saxophone, clarinet.",
        "A track with woodwind tones, flute, reed instruments.",
        "A saxophone, flute, or clarinet part is audible within the track.",
        "The arrangement includes a woodwind soloist or a woodwind ensemble."
      ],
      mulan: [
        "Woodwind instrumentation.",
        "A track featuring woodwind instruments.",
        "woodwinds, saxophone, clarinet",
        "woodwind tones, flute, reed instruments",
        "Recognizable saxophone, flute, or clarinet tones occur in the music.",
        "A solo woodwind part or a woodwind ensemble is audible in the arrangement."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "bass/808",
    axis: "bass",
    label: "808-Bass",
    hint: "Глубокие резонирующие басовые ноты с характерным затухающим хвостом.",
    positive: {
      shared: [],
      clap: [
        "The track features 808 bass tones.",
        "A track with 808-style bass.",
        "This track features 808 bass, resonance, decay.",
        "A track with 808 bass, deep lows, resonant decay.",
        "This track's bass has the characteristic low resonance and decay of an 808.",
        "The track's 808-style bass notes ring out and gradually fade."
      ],
      mulan: [
        "808 bass.",
        "A track with 808-style bass.",
        "808 bass, resonance, decay",
        "808, deep bass, resonant decay",
        "The bass rings out with the decay of an 808 kick.",
        "Deep 808-style bass notes resonate and gradually fade away."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "bass/sub-bass",
    axis: "bass",
    label: "Sub-bass",
    hint: "Глубокий бас в самом низком регистре.",
    positive: {
      shared: [],
      clap: [
        "The track contains deep sub-bass.",
        "A track with bass in the lowest register.",
        "This track features sub-bass, deep bass, low register.",
        "A track with sub-bass, low frequencies.",
        "This track is underpinned by very low bass tones.",
        "The track's bass occupies the lowest audible register."
      ],
      mulan: [
        "Sub-bass.",
        "A track with deep sub-bass.",
        "sub-bass, deep bass, low register",
        "sub-bass, low frequencies",
        "The bass occupies the lowest audible register.",
        "Very low bass tones underpin the sound."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "bass/rolling",
    axis: "bass",
    label: "Rolling-Bass",
    hint: "Перекатывающийся басовый рисунок с повторяющимся движением нот.",
    positive: {
      shared: [],
      clap: [
        "The track has a rolling bassline.",
        "A track with a continuously rolling bass pattern.",
        "This track features rolling bass, repeating notes, note flow.",
        "A track with rolling bassline, recurring pattern.",
        "This track's bass flows through a continuous repeating sequence.",
        "The track's recurring bass figure creates a rolling motion from note to note."
      ],
      mulan: [
        "Rolling bassline.",
        "A track with a rolling bass pattern.",
        "rolling bass, repeating notes, note flow",
        "rolling bassline, recurring pattern",
        "The bass keeps moving through a continuous recurring sequence.",
        "A repeating bass figure creates a rolling motion from note to note."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "bass/reese",
    axis: "bass",
    label: "Reese",
    hint: "Плотный бас с биениями от небольшой расстройки осцилляторов.",
    positive: {
      shared: [],
      clap: [
        "The track features a Reese bass.",
        "A track with detuned Reese bass layers.",
        "This track features reese bass, detuning, beating.",
        "A track with detuned bass, reese, harmonics.",
        "This track's slightly detuned bass layers create audible beating.",
        "The track has the thick, shifting harmonics of a Reese bass."
      ],
      mulan: [
        "Reese bass.",
        "A track with detuned Reese bass.",
        "reese bass, detuning, beating",
        "detuned bass, reese, harmonics",
        "Slight oscillator detuning produces a thick, shifting bass tone.",
        "Closely detuned bass layers create the audible beating of a Reese bass."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "bass/wobble",
    axis: "bass",
    label: "Wobble",
    hint: "Повторяющиеся колебания тембровой окраски баса.",
    positive: {
      shared: [],
      clap: [
        "The track has a wobbling bass tone.",
        "A track with wobble bass.",
        "This track features wobble bass, modulation, tone color.",
        "A track with bass wobble, timbral oscillation.",
        "This track's bass cycles repeatedly between brighter and darker timbres.",
        "The track's bass timbre oscillates back and forth in a repeating cycle."
      ],
      mulan: [
        "Wobble bass.",
        "A track with a wobbling bass tone.",
        "wobble bass, modulation, tone color",
        "bass wobble, timbral oscillation",
        "The bass repeatedly shifts between brighter and darker timbres.",
        "The bass tone color oscillates back and forth in a recurring cycle."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/clean",
    axis: "texture",
    label: "Clean",
    hint: "Чистое, детальное звучание с высокой разборчивостью.",
    positive: {
      shared: [],
      clap: [
        "The track has a clean, high-fidelity sound.",
        "A track with clear hi-fi sound.",
        "This track features hi-fi sound, clarity, definition.",
        "A track with clean sound, high fidelity, detail.",
        "This track reveals fine sonic details with pristine clarity.",
        "The track's sound is clearly defined so that small details remain distinct."
      ],
      mulan: [
        "Clean, hi-fi sound.",
        "A track with high-fidelity sound.",
        "clean, hi-fi, clarity",
        "high fidelity, detail, definition",
        "Small details remain distinct in a pristine recording.",
        "The sound is clear and well-defined, revealing fine sonic details."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/noisy",
    axis: "texture",
    label: "Noisy",
    hint: "Слышимый непрерывный шумовой слой с шипящей фактурой.",
    positive: {
      shared: [],
      clap: [
        "The track has a hissy noise texture.",
        "A track with sustained audible hiss.",
        "This track features noise, hiss, noise floor.",
        "A track with hissy texture, sustained noise.",
        "This track contains a clearly audible layer of sustained hiss.",
        "The track carries a steady wash of hissing noise through the sound."
      ],
      mulan: [
        "Noisy, hissy texture.",
        "A track with sustained hiss.",
        "noisy, hiss, noise floor",
        "hissy texture, sustained noise",
        "A steady wash of hissing noise runs through the sound.",
        "An audible layer of hiss continues through the music."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/distorted",
    axis: "texture",
    label: "Saturated",
    hint: "Слышимое искажение тембра с шероховатым краем звучания.",
    positive: {
      shared: [],
      clap: [
        "The track has an audibly distorted texture.",
        "A track with audible saturation distortion.",
        "This track features distortion, saturation, overdrive.",
        "A track with grit, overdrive, harmonic distortion.",
        "This track's sound has a rough edge from distortion.",
        "The track's tones sound audibly overloaded and distorted."
      ],
      mulan: [
        "Distorted sound.",
        "A track with audible saturation distortion.",
        "distortion, saturation, overdrive",
        "distorted, gritty, harmonic distortion",
        "The signal has a gritty, overdriven character.",
        "Audible distortion gives the tones a rough edge."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/granular",
    axis: "texture",
    label: "Granular",
    hint: "Перекрывающиеся звуковые зёрна, образующие подвижные облака микрофрагментов.",
    positive: {
      shared: [],
      clap: [
        "The track has a granular texture.",
        "A track with overlapping sound grains.",
        "This track features granular texture, audio grains, microfragments.",
        "A track with grain clouds, overlapping grains.",
        "This track's tiny sound fragments form a shifting granular cloud.",
        "The track blends short overlapping sound grains into a continually changing texture."
      ],
      mulan: [
        "Granular texture.",
        "A track with overlapping audio grains.",
        "granular, audio grains, microfragments",
        "grain clouds, overlapping grains",
        "Tiny sound fragments overlap to form a granular cloud.",
        "Short audio grains blend into a continually shifting texture."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/glitchy",
    axis: "texture",
    label: "Glitchy",
    hint: "Короткие обрывы и заикания, дробящие звук на фрагменты.",
    positive: {
      shared: [],
      clap: [
        "The track has a glitchy sound texture.",
        "A track with audible sonic stutters.",
        "This track features glitches, stutters, cuts.",
        "A track with glitches, interruptions, fragmentation.",
        "This track fragments the sound with tiny cuts and stutters.",
        "The track's sound stutters through short repetitions interrupted by abrupt cuts."
      ],
      mulan: [
        "Glitchy, stuttery texture.",
        "A track with audible sonic glitches.",
        "glitchy, stutters, cuts",
        "glitches, interruptions, fragmentation",
        "The sound stutters through short, interrupted repetitions.",
        "Tiny cuts and abrupt glitches break the sound into fragments."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/organic",
    axis: "texture",
    label: "Organic",
    hint: "Естественная фактура с небольшими нерегулярными изменениями тембра.",
    positive: {
      shared: [],
      clap: [
        "The track has an organic sound texture.",
        "A track with natural timbral variation.",
        "This track features organic texture, timbral variation, irregularity.",
        "A track with natural texture, tone fluctuations.",
        "This track's subtle natural variations in timbre give it a lifelike character.",
        "The track's tone color changes in small, irregular ways that sound organic."
      ],
      mulan: [
        "Organic, natural texture.",
        "A track with natural timbral variation.",
        "organic, timbral variation, irregularity",
        "natural texture, tone fluctuations",
        "Minor changes in timbre give the sound a lifelike character.",
        "The tone color varies in small, irregular ways that sound organic."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/metallic",
    axis: "texture",
    label: "Metallic",
    hint: "Металлический звон и характерные резонирующие призвуки.",
    positive: {
      shared: [],
      clap: [
        "The track has a metallic ringing texture.",
        "A track with metal-like sonic resonances.",
        "This track features metallic timbre, ringing, resonance.",
        "A track with metallic tones, resonant overtones.",
        "This track's tones carry metal-like resonances.",
        "The track's ringing overtones give the sound a metallic character."
      ],
      mulan: [
        "Metallic, ringing texture.",
        "A track with metallic resonances.",
        "metallic, ringing, resonance",
        "metallic timbre, resonant overtones",
        "The tones have a resonant metallic edge.",
        "Ringing overtones give the sound a metal-like character."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/dry",
    axis: "texture",
    label: "Dry",
    hint: "Прямой звук с едва слышимым реверберационным послезвучием.",
    positive: {
      shared: [],
      clap: [
        "The track has a dry, direct sound.",
        "A track with dry sound and minimal reverb.",
        "This track features dry sound, direct presence, low reverb.",
        "A track with dry texture, faint reflections.",
        "This track sounds dry, with barely audible room reflections.",
        "The track's dry production leaves very little reverberant decay around the tones."
      ],
      mulan: [
        "Dry, direct sound.",
        "A track with dry sound.",
        "dry, direct, low reverb",
        "dry sound, faint reflections",
        "The sound is direct and dry, with faint room reflections.",
        "The tones have a dry character with barely audible reverberant tails."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/reverberant",
    axis: "texture",
    label: "Reverberant",
    hint: "Выраженное рассеянное послезвучие с тянущимися реверберационными хвостами.",
    positive: {
      shared: [],
      clap: [
        "The track has a reverberant texture.",
        "A track with lingering reverb tails.",
        "This track features reverb, diffuse reflections, decay.",
        "A track with reverberation, reverb tails, diffusion.",
        "This track's tones are surrounded by diffuse reflections.",
        "The track's audible reverb trails linger after the sounds that produce them."
      ],
      mulan: [
        "Reverberant texture.",
        "A track with diffuse reverberation.",
        "reverb, diffuse reflections, decay",
        "reverberant, reverb tails, diffusion",
        "Reverberant reflections blend into a prolonged decay around the sound.",
        "Reverb tails linger after the original tones have faded."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/sparse",
    axis: "texture",
    label: "Sparse",
    hint: "Разреженная фактура с небольшим числом одновременно звучащих слоёв.",
    positive: {
      shared: [],
      clap: [
        "The track has a sparse musical texture.",
        "A track with few simultaneous layers.",
        "This track features sparse layering, low density, few layers.",
        "A track with uncluttered texture, sparse layers.",
        "This track contains only a small number of parts sounding at once.",
        "The track's arrangement stays sparse because few musical layers overlap."
      ],
      mulan: [
        "Sparse, uncluttered texture.",
        "A track with sparse layering.",
        "sparse, low density, few layers",
        "uncluttered, sparse layering",
        "Only a small number of musical parts overlap at once.",
        "The arrangement has a sparse texture with few layers sounding together."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/euphoric",
    axis: "mood",
    label: "Euphoric",
    hint: "Восторг, ликование и эмоциональный подъём.",
    positive: {
      shared: [],
      clap: [
        "The track has a euphoric mood.",
        "An ecstatic track.",
        "This track evokes euphoria, elation, exhilaration.",
        "This track feels uplifting, joyful, jubilant.",
        "This track conveys an overwhelming sense of joy.",
        "The track feels exuberant and full of elation."
      ],
      mulan: [
        "Euphoric mood.",
        "A euphoric track.",
        "euphoric, uplifting, joyful",
        "ecstatic, elated, jubilant",
        "The music conveys intense joy and emotional uplift.",
        "An exuberant mood filled with a sense of elation."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/tense",
    axis: "mood",
    label: "Tense",
    hint: "Тревожное ожидание и эмоциональное напряжение.",
    positive: {
      shared: [],
      clap: [
        "The track has a tense mood.",
        "A suspenseful track.",
        "This track evokes tension, suspense, unease.",
        "This track feels tense, uneasy, apprehensive.",
        "This track conveys anxious anticipation of what comes next.",
        "The track sustains a feeling of unease and apprehension."
      ],
      mulan: [
        "Tense mood.",
        "A tense track.",
        "tense, anxious, apprehensive",
        "suspense, unease, anticipation",
        "The music conveys anxious anticipation and emotional strain.",
        "A suspenseful atmosphere leaves a feeling of unease."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/melancholic",
    axis: "mood",
    label: "Melancholic",
    hint: "Печаль, тоска и задумчивая грусть.",
    positive: {
      shared: [],
      clap: [
        "The track has a melancholic mood.",
        "A wistful track.",
        "This track evokes melancholy, longing, sadness.",
        "This track feels wistful, sorrowful, pensive.",
        "This track conveys a reflective sadness and a sense of longing.",
        "The track carries a lingering feeling of sorrow."
      ],
      mulan: [
        "Melancholic mood.",
        "A melancholic track.",
        "melancholic, wistful, sorrowful",
        "melancholy, longing, sadness",
        "The music conveys reflective sadness and a sense of longing.",
        "A pensive mood with lingering feelings of sorrow."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/aggressive",
    axis: "mood",
    label: "Aggressive",
    hint: "Агрессия, вызов и ощущение враждебности.",
    positive: {
      shared: [],
      clap: [
        "The track has an aggressive mood.",
        "A confrontational track.",
        "This track evokes aggression, anger, defiance.",
        "This track feels hostile, combative, confrontational.",
        "This track conveys anger with a confrontational attitude.",
        "The track expresses a forceful sense of hostility and defiance."
      ],
      mulan: [
        "Aggressive mood.",
        "An aggressive track.",
        "aggressive, confrontational, hostile",
        "anger, defiance, aggression",
        "The music expresses anger and a confrontational attitude.",
        "A combative mood charged with hostility and defiance."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/calm",
    axis: "mood",
    label: "Calm",
    hint: "Спокойствие, умиротворение и безмятежность.",
    positive: {
      shared: [],
      clap: [
        "The track has a calm mood.",
        "A peaceful track.",
        "This track evokes calm, tranquility, serenity.",
        "This track feels peaceful, relaxed, soothing.",
        "This track conveys a sense of inner peace and ease.",
        "The track feels restful and emotionally settled."
      ],
      mulan: [
        "Calm mood.",
        "A calm track.",
        "calm, peaceful, relaxed",
        "serenity, tranquility, ease",
        "The music conveys a restful sense of inner peace.",
        "A soothing mood leaves a feeling of emotional ease."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/dreamy",
    axis: "mood",
    label: "Dreamy",
    hint: "Мечтательность, грёзы и погружение в воображение.",
    positive: {
      shared: [],
      clap: [
        "The track has a dreamy mood.",
        "A dreamlike track.",
        "This track evokes daydreams, reverie, imagination.",
        "This track feels dreamlike, fanciful, otherworldly.",
        "This track invites the mind to wander through imagined scenes.",
        "The track conveys the feeling of being immersed in a daydream."
      ],
      mulan: [
        "Dreamy mood.",
        "A dreamlike track.",
        "dreamy, dreamlike, fanciful",
        "daydreams, reverie, imagination",
        "The music evokes a wandering imagination and vivid daydreams.",
        "A feeling of being absorbed in an imagined world."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/mysterious",
    axis: "mood",
    label: "Mysterious",
    hint: "Загадочность, интрига и любопытство к неизвестному.",
    positive: {
      shared: [],
      clap: [
        "The track has a mysterious mood.",
        "An enigmatic track.",
        "This track evokes mystery, intrigue, curiosity.",
        "This track feels enigmatic, cryptic, intriguing.",
        "This track suggests a hidden story waiting to be discovered.",
        "The track awakens curiosity about something elusive and unknown."
      ],
      mulan: [
        "Mysterious mood.",
        "An enigmatic track.",
        "mysterious, enigmatic, intriguing",
        "mystery, curiosity, intrigue",
        "The music suggests a hidden story waiting to be discovered.",
        "An elusive atmosphere invites curiosity about the unknown."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/playful",
    axis: "mood",
    label: "Playful",
    hint: "Игривость, озорство и добродушный юмор.",
    positive: {
      shared: [],
      clap: [
        "The track has a playful mood.",
        "A mischievous track.",
        "This track evokes playfulness, mischief, amusement.",
        "This track feels whimsical, cheeky, humorous.",
        "This track conveys a teasing attitude and a sense of fun.",
        "The track expresses good-humored mischief and innocent amusement."
      ],
      mulan: [
        "Playful mood.",
        "A mischievous track.",
        "playful, whimsical, cheeky",
        "mischief, amusement, humor",
        "The music conveys a teasing attitude and a sense of fun.",
        "A mood of good-humored mischief and innocent amusement."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/introspective",
    axis: "mood",
    label: "Introspective",
    hint: "Обращённость внутрь себя, самоанализ и размышления о собственных чувствах.",
    positive: {
      shared: [],
      clap: [
        "The track has an introspective mood.",
        "A contemplative track.",
        "This track evokes introspection, contemplation, self-reflection.",
        "This track feels reflective, inward-looking, thoughtful.",
        "This track invites reflection on personal thoughts and feelings.",
        "The track conveys a sense of looking inward and examining one's inner life."
      ],
      mulan: [
        "Introspective mood.",
        "A contemplative track.",
        "introspective, contemplative, reflective",
        "self-reflection, inner thoughts, contemplation",
        "The music invites reflection on personal thoughts and feelings.",
        "An inward-looking mood encourages awareness of one's inner life."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/dark",
    axis: "mood",
    label: "Dark",
    hint: "Зловещее настроение, ощущение угрозы и дурного предчувствия.",
    positive: {
      shared: [],
      clap: [
        "The track has a dark mood.",
        "An ominous track.",
        "This track evokes menace, dread, foreboding.",
        "This track feels ominous, sinister, threatening.",
        "This track conveys a sense of impending danger.",
        "The track suggests a sinister presence and a looming threat."
      ],
      mulan: [
        "Dark mood.",
        "An ominous track.",
        "ominous, sinister, foreboding",
        "menace, dread, threat",
        "The music conveys a sense of impending danger.",
        "A sinister atmosphere suggests a looming threat."
      ]
    },
    negativeWeight: 0
  }
];

/** Mirrors the server fallback when a request has no explicit negative weight. */
export const defaultNegativeWeight = 0.5;

export function presetByKey(key: string): TextPromptPreset | undefined {
  return textPromptPresets.find((preset) => preset.key === key);
}

export function axisByKey(key: string): TextPromptAxis | undefined {
  return textPromptAxes.find((axis) => axis.key === key);
}

type TextPromptOverlap = {
  keys: [string, string];
  description: string;
};

// Shared meanings in the vocabulary, not measured conflicts between models.
const textPromptOverlaps: TextPromptOverlap[] = [
  {
    keys: ["rhythm/shuffle", "groove/swing"],
    description: "Обе метки описывают чередование длинных и коротких подразделений доли. Shuffle уточняет триольный рисунок ударных, Swing — общее ощущение тайминга."
  }
];

export function selectedPromptOverlaps(keys: string[]): TextPromptOverlap[] {
  return textPromptOverlaps.filter((overlap) => overlap.keys.every((key) => keys.includes(key)));
}

export function resolvePromptVariants(
  variants: PromptVariants | undefined,
  model: TextPromptModel
): string[] {
  if (!variants) return [];
  return variants[model] ?? variants.shared;
}

export function resolveNegativeWeight(weight: NegativeWeight, model: TextPromptModel): number {
  return typeof weight === "number" ? weight : weight[model];
}

export type ComposedPromptBanks = {
  positiveText: string;
  negativeText: string;
  negativeWeight: number | null;
};

/** Compose model-specific banks and use the smallest contributing negative weight. */
export function composePromptBanks(
  keys: string[],
  model: TextPromptModel
): ComposedPromptBanks {
  const positive: string[] = [];
  const negative: string[] = [];
  const weights: number[] = [];

  for (const key of keys) {
    const preset = presetByKey(key);
    if (!preset) continue;
    for (const line of resolvePromptVariants(preset.positive, model)) {
      if (!positive.includes(line)) positive.push(line);
    }
    const weight = resolveNegativeWeight(preset.negativeWeight, model);
    const negativeLines = resolvePromptVariants(preset.negative, model);
    if (weight <= 0 || negativeLines.length === 0) continue;
    for (const line of negativeLines) {
      if (!negative.includes(line)) negative.push(line);
    }
    weights.push(weight);
  }

  return {
    positiveText: positive.join("\n"),
    negativeText: negative.join("\n"),
    negativeWeight: weights.length ? Math.min(...weights) : null
  };
}

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
