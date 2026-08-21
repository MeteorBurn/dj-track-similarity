export type TextPromptModel = "clap" | "mulan";

/** Model-specific wording, falling back to the shared bank. */
export type PromptVariants = {
  shared: string[];
  clap?: string[];
  mulan?: string[];
};

export type NegativeWeight = number | { clap: number; mulan: number };

export type MeasuredPreset = {
  /** ROC-AUC on the labelled Rhythm Lab pool, per scripts/text_prompt_benchmark.py. */
  clap?: number;
  mulan?: number;
  note?: string;
};

export type TextPromptPreset = {
  key: string;
  axis: string;
  label: string;
  hint: string;
  positive: PromptVariants;
  negative?: PromptVariants;
  /**
   * Hard-negative weight for this preset. The benchmark showed one global
   * constant cannot work: named competing classes keep improving up to 0.75-1.0,
   * while an invented negative bank only removes signal, so those presets carry
   * a weight of 0 and no negatives at all.
   */
  negativeWeight: NegativeWeight;
  measured?: MeasuredPreset;
  /**
   * Overrides the axis model for this one label, where its own cross-check
   * contradicts the axis. Used where the axis winner ranks this label the wrong
   * way round: the axis average hides an outright inversion.
   */
  model?: TextPromptModel;
};

export type TextPromptAxis = {
  key: string;
  label: string;
  hint: string;
  /**
   * Model measured to rank this axis best, by the share of the reference in the
   * first hundred rows (scripts/text_fusion_benchmark.py). Rank fusion was
   * measured and rejected: mixing drags the stronger model toward the weaker one
   * on the axes where the gap is widest, so the choice is made per axis instead.
   *
   * Absent where the measurement cannot carry the claim: space has no reference
   * at all, low has one label, and harmony's two models sit 0.017 apart.
   */
  model?: TextPromptModel;
};

export const textPromptAxes: TextPromptAxis[] = [
  { key: "groove", label: "Грув", hint: "Рисунок ритма: брейки, ровная бочка, халфтайм, свинг, полиритмия. Замер: MuQ-MuLan 0.630 против CLAP 0.497.", model: "mulan" },
  { key: "low", label: "Низ", hint: "Характер баса и низа: саб, кислота, рииз, сухой панч. Эталон есть у одной метки — модель не рекомендуется." },
  { key: "texture", label: "Фактура", hint: "Тембр и обработка: даб, металл, глитч, lo-fi, чистый продакшн. Замер: CLAP 0.343 против MuQ-MuLan 0.230.", model: "clap" },
  { key: "harmony", label: "Гармония", hint: "Аккорды и плотность смен: модальность, диссонанс, дрон, джаз. Лад минор-мажор берётся из SONARA: обе текстовые модели на нём на уровне случайности. Модели разошлись на 0.017 — рекомендации нет." },
  { key: "voice", label: "Голос", hint: "Присутствие и характер голоса: вокал, речь, нарезки, хор, инструментал. Рекомендации нет: все одиннадцать меток оси сверялись с одним и тем же числом SONARA — вероятностью вокала. Оно отвечает «голос есть или нет» и не отличает женский лид от хора, шёпота или речи, поэтому средним по оси нельзя выбирать модель для конкретной метки." },
  { key: "instruments", label: "Инструменты", hint: "Конкретные инструменты и машины. Рекомендации нет: все двадцать одна метка оси сверялись с одним и тем же числом SONARA — акустичностью. Оно отвечает «звучит ли живо», а не «нашёлся ли ситар», и в электронной библиотеке штрафует метку ровно за верную находку: сэмпл ситара внутри трека акустичность не поднимает. Сверяйся ушами. Наблюдение с двух прослушиваний, не замер: CLAP берёт метку там, где инструмент реально играют (калимба), MuQ-MuLan — там, где он приходит сэмплом внутри электроники (ситар)." },
  { key: "space", label: "Пространство", hint: "Сухо, комната, пещера, дилей, ширина стерео. Ни одной метки с эталоном — надёжность неизвестна." },
  { key: "energy", label: "Энергия", hint: "Интенсивность и роль в сете: разогрев, пик, финал, эмбиент. Замер: CLAP 0.453 против MuQ-MuLan 0.360.", model: "clap" },
  { key: "style", label: "Стиль", hint: "Жанры и сцены. Дополняют таксономию MAEST, а не дублируют её. Замер: MuQ-MuLan 0.463 против CLAP 0.384.", model: "mulan" }
];

export const textPromptPresets: TextPromptPreset[] = [
  {
    key: "groove/breakbeat",
    axis: "groove",
    label: "Breakbeat",
    hint: "Ломаные драмы, синкопы, off-grid. Замер: MuQ-MuLan ROC-AUC 0.955.",
    positive: {
      shared: [
        "A breakbeat track.",
        "A track with broken drums and syncopated percussion.",
        "An electronic club track built on chopped drum breaks and uneven accents.",
        "Downtempo electro with a stuttering beat and an off-grid rhythm."
      ]
    },
    negative: {
      shared: [
        "A four-on-the-floor house track.",
        "A techno track with a steady straight kick on every beat.",
        "A minimal house groove with even drum timing.",
        "A straight driving dance track with a regular kick pattern."
      ]
    },
    negativeWeight: 0.75,
    measured: { mulan: 0.955, clap: 0.84 }
  },
  {
    key: "groove/four-on-the-floor",
    axis: "groove",
    label: "Four-on-the-floor",
    hint: "Ровная бочка на каждую долю, прямой танцевальный грув.",
    positive: {
      shared: [
        "A four-on-the-floor house track.",
        "A techno track with a steady kick on every beat.",
        "A driving dance track with an even, regular drum pattern.",
        "A club track with a straight pumping kick and steady hi-hats."
      ]
    },
    negative: {
      shared: [
        "A breakbeat track with broken drums.",
        "A track with syncopated off-grid percussion.",
        "A halftime track with a slow, sparse beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/halftime",
    axis: "groove",
    label: "Halftime",
    hint: "Замедленный тяжёлый бит, много воздуха между ударами.",
    positive: {
      shared: [
        "A halftime track.",
        "A downtempo electronic track with a slow, heavy beat.",
        "A track with a sparse halftime drum pattern and a wide bassline.",
        "A slow-moving club track with space between the drum hits."
      ]
    },
    negative: {
      shared: [
        "A fast four-on-the-floor dance track.",
        "A high-tempo drum and bass track.",
        "A driving uptempo techno track."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/shuffle",
    axis: "groove",
    label: "Shuffle / Swing",
    hint: "Свинговый, качающий грув, катящиеся хэты.",
    positive: {
      shared: [
        "A shuffled house track.",
        "A track with a swung groove and rolling hi-hats.",
        "A garage track with a shuffling, bouncing rhythm.",
        "A club track with swing timing and loose, springy drums."
      ]
    },
    negative: {
      shared: [
        "A rigid quantized techno track with straight timing.",
        "A track with stiff mechanical drum timing."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/polyrhythm",
    axis: "groove",
    label: "Polyrhythm / Tribal",
    hint: "Слоистая перкуссия, ручные барабаны, переплетённые рисунки.",
    positive: {
      shared: [
        "A tribal percussion track.",
        "A track with layered polyrhythmic hand drums.",
        "An electronic track built on dense interlocking percussion.",
        "A club track with congas, bongos and shakers driving the groove."
      ]
    },
    negative: {
      shared: [
        "A minimal track with a simple kick and hi-hat pattern.",
        "A sparse track with almost no percussion."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "low/sub",
    axis: "low",
    label: "Sub / Rolling bass",
    hint: "Глубокий саб, катящаяся непрерывная басовая линия.",
    positive: {
      shared: [
        "A track with deep sub bass.",
        "A club track with a rolling, continuous bassline.",
        "A deep electronic track where a low sine bass carries the groove.",
        "A track with heavy low-end weight and a smooth rolling bass."
      ]
    },
    negative: {
      shared: [
        "A thin, bright track dominated by high frequencies.",
        "A track with a short, dry, plucked bass."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "low/acid",
    axis: "low",
    label: "Acid 303",
    hint: "Резонансная 303, фильтровые свипы, кислотная линия.",
    positive: {
      shared: [
        "An acid techno track.",
        "A track with a squelchy resonant 303 bassline.",
        "An electronic track with a screaming acid bass and filter sweeps.",
        "A club track built around a wriggling acid synth line."
      ]
    },
    negative: {
      shared: [
        "A track with a clean, plain sine bass.",
        "A soft ambient track with sustained pads."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "low/dry-punch",
    axis: "low",
    label: "Dry punchy bass",
    hint: "Короткий сухой бас, стаккато-стабы, tech house.",
    positive: {
      shared: [
        "A track with a short, dry, punchy bass.",
        "A tech house track with a tight plucked bassline.",
        "A club track with staccato bass stabs and dry low end.",
        "A groove built on short muted bass notes."
      ]
    },
    negative: {
      shared: [
        "A track with a long, droning sustained bass.",
        "A track with a smooth continuous sub bass."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/dub",
    axis: "texture",
    label: "Dubby / Tape",
    hint: "Ленточные дилеи, пружинный ревер, аккордовые стабы в дымке.",
    positive: {
      shared: [
        "A dub techno track.",
        "A track with tape delay, spring reverb and warm chord stabs.",
        "A hazy electronic track with echoing chords fading into the mix.",
        "A deep track with saturated tape texture and washed-out delays."
      ]
    },
    negative: {
      shared: [
        "A clean, dry digital production with sharp transients.",
        "A bright modern track with tight, short sounds."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/metallic",
    axis: "texture",
    label: "Metallic / Industrial",
    hint: "Металлическая перкуссия, скрежет, индустриальная грязь.",
    positive: {
      shared: [
        "An industrial techno track.",
        "A track with metallic percussion and clanging hits.",
        "A harsh electronic track built on scraping metal textures.",
        "A dark club track with distorted, gritty machine sounds."
      ]
    },
    negative: {
      shared: [
        "A warm, soft, melodic electronic track.",
        "A gentle acoustic recording with natural timbre."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/granular",
    axis: "texture",
    label: "Granular / Glitch",
    hint: "Гранулярные текстуры, клики, цифровые артефакты.",
    positive: {
      shared: [
        "A glitch electronic track.",
        "A track with granular textures and stuttering digital artifacts.",
        "An abstract electronic piece built on chopped micro-sounds.",
        "A track with clicks, cuts and fragmented digital debris."
      ]
    },
    negative: {
      shared: [
        "A smooth continuous track with clean sustained tones.",
        "A straightforward club track with conventional drums."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/lo-fi",
    axis: "texture",
    label: "Lo-fi / Hiss",
    hint: "Шипение ленты, треск винила, узкая полоса, пыль.",
    positive: {
      shared: [
        "A lo-fi track.",
        "A track with tape hiss, vinyl crackle and a dusty tone.",
        "A murky recording with limited bandwidth and soft saturation.",
        "A warm degraded track that sounds like an old cassette."
      ]
    },
    negative: {
      shared: [
        "A clean, crisp, high-fidelity studio production.",
        "A polished modern mix with wide clear high end."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/clean",
    axis: "texture",
    label: "Clean / Hi-fi",
    hint: "Чистый современный продакшн, широкий прозрачный микс. CLAP инвертирует против спектрального роллоффа (0.372), MuQ-MuLan даёт 0.621 — ось перекрыта.",
    positive: {
      shared: [
        "A clean hi-fi electronic track.",
        "A polished studio production with crisp, detailed high end.",
        "A modern club track with a wide, clear, precise mix.",
        "A track with sharp transients and a transparent sound."
      ]
    },
    negative: {
      shared: [
        "A lo-fi track with tape hiss and vinyl crackle.",
        "A murky distorted recording with limited bandwidth."
      ]
    },
    negativeWeight: 0.5,
    model: "mulan"
  },
  {
    key: "voice/vocal-led",
    axis: "voice",
    label: "Vocal-led",
    hint: "Голос как заметный элемент. Замер: CLAP 0.910, MuQ-MuLan 0.879.",
    positive: {
      shared: [
        "A vocal music track.",
        "A track with singing vocals.",
        "A track with spoken words and a human voice.",
        "A club track with vocal hooks and chopped vocal samples."
      ]
    },
    negative: {
      shared: [
        "An instrumental electronic dance track.",
        "An instrumental club track with drums, bass and texture only.",
        "A wordless instrumental recording.",
        "An instrumental techno track with percussion only."
      ]
    },
    negativeWeight: { clap: 0.85, mulan: 0.45 },
    measured: { clap: 0.91, mulan: 0.879, note: "CLAP выигрывает на этой оси" },
    model: "clap"
  },
  {
    key: "voice/spoken",
    axis: "voice",
    label: "Spoken word",
    hint: "Разговорная речь, монолог, семплы говорящего голоса.",
    positive: {
      shared: [
        "A spoken word track.",
        "A recording with a talking voice over music.",
        "A track with a narrated monologue and sparse instrumental.",
        "An electronic track with sampled speech in the foreground."
      ]
    },
    negative: {
      shared: [
        "A track with sung melodic vocals.",
        "An instrumental club track with drums and bass only."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/chopped",
    axis: "voice",
    label: "Chopped vocals",
    hint: "Нарезанные вокальные фразы как перкуссия.",
    positive: {
      shared: [
        "A track with chopped vocal samples.",
        "A house track with short cut-up vocal phrases as percussion.",
        "A club track with stuttering, pitched vocal chops.",
        "A groove built from sliced vocal fragments."
      ]
    },
    negative: {
      shared: [
        "A track with a full sung lead vocal performance.",
        "An instrumental track with drums and bass only."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/instrumental",
    axis: "voice",
    label: "Instrumental",
    hint: "Инструментальные треки без голоса.",
    positive: {
      shared: [
        "An instrumental electronic dance track.",
        "An instrumental club track with drums, bass and texture only.",
        "A wordless instrumental recording.",
        "An instrumental techno track with percussion and low end."
      ]
    },
    negative: {
      shared: [
        "A track with prominent singing vocals.",
        "A vocal pop song.",
        "A rap track with spoken vocals.",
        "A recording of speech."
      ]
    },
    negativeWeight: 0.6
  },
  {
    key: "instruments/live",
    axis: "instruments",
    label: "Live instruments",
    hint: "Живая игра, натуральный тембр. Замер: CLAP 0.792, MuQ-MuLan 0.778.",
    positive: {
      shared: [
        "An acoustic music track.",
        "A track with live instruments played by a musician.",
        "A recording with guitar, piano, strings or brass played live.",
        "A track with natural acoustic instrument timbre and human timing."
      ]
    },
    negative: {
      shared: [
        "A fully programmed electronic dance track.",
        "A drum machine and synthesizer track.",
        "A sequenced digital studio production."
      ]
    },
    negativeWeight: 0.75,
    measured: { clap: 0.792, mulan: 0.778, note: "у MuQ-MuLan позитив без негатива ниже случайного" }
  },
  {
    key: "instruments/piano",
    axis: "instruments",
    label: "Piano",
    hint: "Фортепиано ведёт гармонию или мелодию.",
    positive: {
      shared: [
        "A piano track.",
        "A track with an acoustic piano melody.",
        "A house track with warm piano chords.",
        "A recording where the piano carries the harmony."
      ]
    },
    negative: {
      shared: [
        "A synth-only electronic track.",
        "A percussion-only track with drums and bass."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "instruments/guitar",
    axis: "instruments",
    label: "Guitar",
    hint: "Гитарный рифф, перебор, гитарная линия поверх бита.",
    positive: {
      shared: [
        "A guitar track.",
        "A track with a plucked electric guitar riff.",
        "A recording with acoustic guitar strumming.",
        "An electronic track with a guitar line over the beat."
      ]
    },
    negative: {
      shared: [
        "A synth-only electronic track.",
        "A track with piano as the only melodic instrument."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "instruments/strings-brass",
    axis: "instruments",
    label: "Strings / Brass",
    hint: "Струнные и духовые, оркестровые аранжировки.",
    positive: {
      shared: [
        "A track with a string arrangement.",
        "A recording with violins and cellos playing a theme.",
        "A track with a brass section and horn stabs.",
        "An orchestral arrangement over an electronic beat."
      ]
    },
    negative: {
      shared: [
        "A stripped-back drum and bass groove with no melody.",
        "A synth-only electronic track."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "space/dry",
    axis: "space",
    label: "Dry / Close",
    hint: "Сухой микс, всё близко, короткие хвосты.",
    positive: {
      shared: [
        "A dry mix with close, tight sounds.",
        "A track with very short reverb tails.",
        "An intimate production where every element sits close.",
        "A tight club track with controlled, compact sounds."
      ]
    },
    negative: {
      shared: [
        "A track drenched in long cavernous reverb.",
        "A washed-out ambient track with huge space."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "space/roomy",
    axis: "space",
    label: "Roomy",
    hint: "Естественная комната вокруг инструментов.",
    positive: {
      shared: [
        "A track with a natural room sound.",
        "A recording with a warm ambient room around the drums.",
        "A track with short, natural reverb on the instruments.",
        "A production that sounds recorded in a real space."
      ]
    },
    negative: {
      shared: [
        "A completely dry studio mix with tight close sounds.",
        "A track with a huge cathedral reverb."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "space/cavernous",
    axis: "space",
    label: "Cavernous",
    hint: "Огромный ревер, длинные хвосты, всё в дымке.",
    positive: {
      shared: [
        "A track with huge cavernous reverb.",
        "A spacious electronic track with long echoing tails.",
        "A distant, washed-out production with deep space.",
        "A track where reverb blurs the whole arrangement."
      ]
    },
    negative: {
      shared: ["A dry, tight mix with close, controlled sounds."]
    },
    negativeWeight: 0.5
  },
  {
    key: "energy/warm-up",
    axis: "energy",
    label: "Warm-up",
    hint: "Сдержанная энергия: приглушённый кик, мягкие пэды, сабовый низ.",
    positive: {
      shared: [
        "A deep, restrained club track.",
        "A track with a muted kick, soft pads and a slow build.",
        "A low-intensity electronic track with sub-heavy low end.",
        "A patient groove with quiet drums and a plain arrangement."
      ]
    },
    negative: {
      shared: [
        "A peak-time festival track with a loud drop.",
        "A high-energy club banger with bright synth leads.",
        "An aggressive track with hard, loud drums."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "energy/peak",
    axis: "energy",
    label: "Peak time",
    hint: "Максимальная энергия: громко, ярко, плотно.",
    positive: {
      shared: [
        "A peak-time club track.",
        "A loud, driving track with hard kicks and bright leads.",
        "A high-energy dance track with a big drop.",
        "An intense club track with a maximal arrangement."
      ]
    },
    negative: {
      shared: [
        "A quiet, restrained deep track with muted drums.",
        "An ambient beatless piece with sustained tones."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "energy/closing",
    axis: "energy",
    label: "Closing",
    hint: "Финальная часть сета: медленно, тепло, меланхолично.",
    positive: {
      shared: [
        "A slow closing track.",
        "An emotional electronic track with a fading, gentle groove.",
        "A warm, melancholic track with soft drums.",
        "A reflective track with sparse percussion and long chords."
      ]
    },
    negative: {
      shared: [
        "A loud peak-time club banger.",
        "An aggressive high-tempo dance track."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "energy/ambient",
    axis: "energy",
    label: "Ambient",
    hint: "Без бита: дроны, длинные тона, атмосфера.",
    positive: {
      shared: [
        "An ambient track.",
        "A beatless electronic piece with sustained drones.",
        "A slow atmospheric soundscape with soft evolving layers.",
        "A meditative track built on long tones and texture."
      ]
    },
    negative: {
      shared: [
        "A dance floor track with driving drums.",
        "A rhythmic club track with a steady kick."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/minimal-deep-tech",
    axis: "style",
    label: "Minimal / Deep-tech",
    hint: "Замер: MuQ-MuLan 0.880 без негативов; негативы там только мешали.",
    positive: {
      shared: [
        "A minimal tech house track.",
        "A funky deep tech groove with tight drums and crisp hi-hats.",
        "A stripped-back club track with dry percussion and subtle vocal chops.",
        "A spacious minimal house track with a rolling bassline."
      ]
    },
    negativeWeight: 0,
    measured: { mulan: 0.88, clap: 0.691, note: "негативный банк на замере ронял ROC-AUC" }
  },
  {
    key: "style/electro",
    axis: "style",
    label: "Electro",
    hint: "808-грув, синкопированный электро-бит, холодные синты.",
    positive: {
      shared: [
        "An electro track.",
        "A track with 808 drums and a robotic electro groove.",
        "A machine funk track with syncopated electro drums.",
        "A retro-futuristic electronic track with cold synths."
      ]
    },
    negative: {
      shared: [
        "A four-on-the-floor house track.",
        "An organic acoustic recording with live instruments."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/experimental",
    axis: "style",
    label: "Experimental",
    hint: "Абстрактное и странное. Замер: CLAP 0.977, MuQ-MuLan 0.971.",
    positive: {
      shared: [
        "An experimental electronic track.",
        "An abstract track with fractured rhythm and unusual texture.",
        "A minimal experimental recording with strange rhythmic movement.",
        "An unconventional electronic piece with an odd, unsettled groove."
      ]
    },
    negative: {
      shared: [
        "A functional club track with a standard dance groove.",
        "A straightforward house track for the dance floor.",
        "A conventional techno track with a steady beat."
      ]
    },
    negativeWeight: 0.5,
    measured: { clap: 0.977, mulan: 0.971 }
  },
  {
    key: "groove/amen-break",
    axis: "groove",
    label: "Amen break",
    hint: "Нарезанный amen, джангловые барабаны.",
    positive: {
      shared: [
        "An amen break track.",
        "A track built on a chopped amen drum break.",
        "Jungle drums cut from a fast breakbeat sample.",
        "Rapid snare rolls and ghost notes cut from sampled vinyl drums."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/two-step",
    axis: "groove",
    label: "Two-step",
    hint: "Скачущий гаражный рисунок с обрезанным киком.",
    positive: {
      shared: [
        "A two-step garage track.",
        "A track with a skipping two-step drum pattern.",
        "Garage drums with a clipped kick and snare.",
        "The kick skips beats while the snare lands on two and four."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/boom-bap",
    axis: "groove",
    label: "Boom bap",
    hint: "Пыльный хип-хоп бит, свингующие кик и снейр.",
    positive: {
      shared: [
        "A boom bap track.",
        "A hip hop beat with a dusty kick and snare.",
        "A slow swung drum pattern with vinyl texture.",
        "A heavy kick and a cracking snare over sampled vinyl noise."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/gallop",
    axis: "groove",
    label: "Gallop",
    hint: "Галопирующий триольный рисунок.",
    positive: {
      shared: [
        "A galloping rhythm track.",
        "A track with a triplet galloping drum pattern.",
        "A rolling three-note figure drives the drums forward.",
        "Drums canter in a repeated triplet pattern."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/triplet-swing",
    axis: "groove",
    label: "Triplet swing",
    hint: "Катящиеся триольные хэты.",
    positive: {
      shared: [
        "A triplet swing groove.",
        "A track with rolling triplet hi-hats.",
        "The hi-hats roll in threes with a loose swing.",
        "A shuffled groove where every beat divides into three."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/broken-techno",
    axis: "groove",
    label: "Broken techno",
    hint: "Техно со спотыкающимся, сбитым киком.",
    positive: {
      shared: [
        "A broken techno track.",
        "A techno track with an off-grid kick pattern.",
        "Club techno with a stumbling, irregular beat.",
        "The kick lands off the grid and the groove stumbles forward."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "low/reese",
    axis: "low",
    label: "Reese bass",
    hint: "Широкий расстроенный рычащий бас.",
    positive: {
      shared: [
        "A reese bass track.",
        "A track with a wide detuned growling bassline.",
        "A menacing low growl built from two detuned saw waves beating against each other.",
        "The bassline snarls and modulates slowly under the drums."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "low/distorted",
    axis: "low",
    label: "Distorted bass",
    hint: "Перегруженный, грязный низ.",
    positive: {
      shared: [
        "A track with a distorted overdriven bass.",
        "A club track with a gritty saturated low end.",
        "The low end clips and fuzzes into harmonic grit.",
        "A crunchy bass tone with broken, torn edges."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "low/walking",
    axis: "low",
    label: "Walking bass",
    hint: "Шагающая басовая линия четвертями.",
    positive: {
      shared: [
        "A track with a walking bassline.",
        "A jazzy bassline moving in steady quarter notes.",
        "An upright bass walks a steady line under the chords.",
        "The bass steps note by note through the changes."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "low/fm",
    axis: "low",
    label: "FM bass",
    hint: "Металлический цифровой FM-бас.",
    positive: {
      shared: [
        "A track with a metallic FM bass.",
        "A bassline with a sharp digital FM timbre.",
        "A hard bell-like bass with a glassy digital edge.",
        "The bass tone rings with metallic overtones and a fast decay."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/saturated",
    axis: "texture",
    label: "Saturated",
    hint: "Тёплое аналоговое насыщение, компрессия в потолок.",
    positive: {
      shared: [
        "A saturated overdriven mix.",
        "A track pushed into warm analog distortion.",
        "The mix is pushed hard into tape and tube warmth.",
        "Everything is compressed and glued into one thick driven sound."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/glassy",
    axis: "texture",
    label: "Glassy",
    hint: "Стеклянные, кристальные верхи. CLAP инвертирует против спектрального центроида (0.294) — ось перекрыта на MuQ-MuLan.",
    positive: {
      shared: [
        "A glassy bright track.",
        "A track with crystalline shimmering synth tones.",
        "High bell-like tones ring with a clear brittle sheen.",
        "Chimes and glass-toned synths sparkle in the high register."
      ]
    },
    negativeWeight: 0,
    model: "mulan"
  },
  {
    key: "texture/wooden",
    axis: "texture",
    label: "Wooden",
    hint: "Деревянная сухая перкуссия.",
    positive: {
      shared: [
        "A track with wooden acoustic percussion timbre.",
        "Dry knocking wooden hits carry the rhythm.",
        "Woodblock, rimshot and hollow tom sounds carry the pulse.",
        "Short dry mallet hits with a mid-range knock and a quick decay."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/resonant",
    axis: "texture",
    label: "Resonant filter",
    hint: "Резонансные фильтровые свипы.",
    positive: {
      shared: [
        "A resonant filtered track.",
        "A track with sharp resonant filter sweeps.",
        "A filter sweep sings as its resonance peaks.",
        "A whistling filter peak rides over the chords."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/hazy",
    axis: "texture",
    label: "Hazy",
    hint: "Всё за мягким фильтром, размытая дымка.",
    positive: {
      shared: [
        "A hazy blurred track.",
        "A track where every element sits behind a soft filter.",
        "The high end is rolled off and everything sounds veiled.",
        "A smeared foggy mix where edges blur together."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "harmony/modal",
    axis: "harmony",
    label: "Modal",
    hint: "Модальность, дорийский колорит, одна тональная плоскость.",
    positive: {
      shared: [
        "A modal track.",
        "A track built on one scale with a dorian colour.",
        "The harmony stays inside one mode with a raised sixth.",
        "Chords circle inside a single scale for the whole track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "harmony/dissonant",
    axis: "harmony",
    label: "Dissonant",
    hint: "Диссонанс, неразрешённая гармония, атональность.",
    positive: {
      shared: [
        "A dissonant atonal track.",
        "A track with clashing unresolved harmony.",
        "Notes rub against each other in tense unresolved clusters.",
        "Sharp clashing intervals hold the harmony in tension."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "harmony/drone",
    axis: "harmony",
    label: "One-chord drone",
    hint: "Один аккорд на весь трек.",
    positive: {
      shared: [
        "A single chord drone track.",
        "A track that stays on one sustained harmony.",
        "One sustained chord holds under the whole arrangement.",
        "A continuous held tone anchors the track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "harmony/jazz",
    axis: "harmony",
    label: "Jazz chords",
    hint: "Расширенные джазовые аккорды, септимы и ноны.",
    positive: {
      shared: [
        "A track with extended jazz chords.",
        "Lush seventh and ninth chord voicings.",
        "Rich seventh, ninth and thirteenth voicings colour the chords.",
        "Complex jazz harmony moves under the melody."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "harmony/blues",
    axis: "harmony",
    label: "Blues",
    hint: "Блюзовые ноты, двенадцатитактовая форма.",
    positive: {
      shared: [
        "A bluesy track.",
        "A track with blue notes and a twelve bar feel.",
        "Bent blue notes over a shuffling twelve bar progression.",
        "A gritty blues feel with flattened thirds and sevenths."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "harmony/detuned",
    axis: "harmony",
    label: "Detuned",
    hint: "Расстроенный, микротональный строй.",
    positive: {
      shared: [
        "A detuned track.",
        "A track with microtonal drifting tuning.",
        "Oscillators drift slightly out of tune against each other.",
        "The pitch wavers and slides, sounding slightly warped."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "voice/female-lead",
    axis: "voice",
    label: "Female lead",
    hint: "Женский ведущий вокал.",
    positive: {
      shared: [
        "A track with a female lead vocal.",
        "A woman sings the lead melody.",
        "A high female voice carries the main melody.",
        "A female singer is the focus of the arrangement."
      ]
    },
    negative: {
      shared: ["An instrumental club track with drums and bass only."]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/male-lead",
    axis: "voice",
    label: "Male lead",
    hint: "Мужской ведущий вокал.",
    positive: {
      shared: [
        "A track with a male lead vocal.",
        "A man sings the lead melody.",
        "A low male voice carries the main melody.",
        "A male singer is the focus of the arrangement."
      ]
    },
    negative: {
      shared: ["An instrumental club track with drums and bass only."]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/choir",
    axis: "voice",
    label: "Choir",
    hint: "Хор, многоголосие.",
    positive: {
      shared: [
        "A track with a choir.",
        "Layered voices sing sustained harmony.",
        "A group of singers holds long chords together.",
        "Massed choral voices swell behind the music."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "voice/chant",
    axis: "voice",
    label: "Chant",
    hint: "Повторяющийся вокальный чант.",
    positive: {
      shared: [
        "A track with a repeated vocal chant.",
        "A crowd chants a short phrase over the beat.",
        "A short vocal line is repeated like a football chant.",
        "Group voices shout the same phrase again and again."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "voice/whispered",
    axis: "voice",
    label: "Whispered",
    hint: "Шёпот, придыхание близко к микрофону.",
    positive: {
      shared: [
        "A track with whispered vocals.",
        "A breathy close whisper over the beat.",
        "An intimate whispered voice sits close to the microphone.",
        "Soft breathy speech murmurs through the track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "voice/vocoder",
    axis: "voice",
    label: "Vocoder / Talkbox",
    hint: "Роботизированный голос через вокодер или токбокс.",
    positive: {
      shared: [
        "A track with vocoder vocals.",
        "A robotic talkbox voice carries the melody.",
        "A synthesised voice sings through a vocoder.",
        "Machine-processed vocals with a robotic formant tone."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "voice/dialogue",
    axis: "voice",
    label: "Dialogue sample",
    hint: "Семпл речи из фильма или записи.",
    positive: {
      shared: [
        "A track with a sampled movie dialogue.",
        "A spoken film line sits over the music.",
        "A spoken line from a film is sampled into the track.",
        "Recorded speech from a movie plays over the music."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/rhodes",
    axis: "instruments",
    label: "Rhodes",
    hint: "Электропиано Rhodes, тремоло-аккорды.",
    positive: {
      shared: [
        "A track with a Rhodes electric piano.",
        "Warm tremolo electric piano chords.",
        "A soft electric piano with a bell-like attack.",
        "Tremolo keys comp warm chords under the melody."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/organ",
    axis: "instruments",
    label: "Organ",
    hint: "Хаммонд, вращающиеся драубары.",
    positive: {
      shared: [
        "A track with a Hammond organ.",
        "Swirling drawbar organ chords.",
        "A drawbar organ with a rotary speaker swirl.",
        "Sustained organ chords with a warm rotating tone."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/marimba",
    axis: "instruments",
    label: "Marimba",
    hint: "Деревянные мэллет-мелодии.",
    positive: {
      shared: [
        "A track with marimba.",
        "Wooden mallet melodies ring through the track.",
        "Wooden bars struck with mallets play a rolling melody.",
        "Round warm mallet tones bounce through the arrangement."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/vibraphone",
    axis: "instruments",
    label: "Vibraphone",
    hint: "Металлические мэллеты с вибрато.",
    positive: {
      shared: [
        "A track with vibraphone.",
        "Soft metallic mallet chords with slow vibrato.",
        "Metal bars struck with mallets ring with slow vibrato.",
        "Shimmering mallet chords with a long metallic sustain."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/kalimba",
    axis: "instruments",
    label: "Kalimba",
    hint: "Калимба, щипковые язычки.",
    positive: {
      shared: [
        "A track with kalimba.",
        "Plucked thumb piano notes carry the melody.",
        "Small metal tines plucked by thumbs ring out.",
        "A tiny bright plucked tone repeats a simple figure."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/nylon-guitar",
    axis: "instruments",
    label: "Nylon guitar",
    hint: "Классическая гитара, перебор.",
    positive: {
      shared: [
        "A track with nylon string guitar.",
        "Fingerpicked classical guitar lines.",
        "Soft nylon strings plucked close to the bridge.",
        "A warm mellow acoustic guitar plays arpeggios."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/slap-bass",
    axis: "instruments",
    label: "Slap bass",
    hint: "Слэповый фанковый бас.",
    positive: {
      shared: [
        "A track with slap bass.",
        "A funk bassline played with thumb slaps.",
        "A percussive popped and slapped electric bass.",
        "The bass snaps and pops with a bright funk attack."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/upright-bass",
    axis: "instruments",
    label: "Upright bass",
    hint: "Контрабас, деревянный акустический низ.",
    positive: {
      shared: [
        "A track with an upright double bass.",
        "A woody acoustic bass plays the groove.",
        "A large acoustic bass plucked with fingers.",
        "A round woody acoustic bass tone underpins the chords."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/saxophone",
    axis: "instruments",
    label: "Saxophone",
    hint: "Саксофон.",
    positive: {
      shared: [
        "A track with saxophone.",
        "A breathy sax melody over the groove.",
        "A reed instrument plays a warm expressive solo.",
        "A saxophone line breathes over the arrangement."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/trumpet",
    axis: "instruments",
    label: "Trumpet",
    hint: "Труба, яркая медь.",
    positive: {
      shared: [
        "A track with trumpet.",
        "A bright brass trumpet line.",
        "A brass instrument plays a bright piercing line.",
        "A muted or open trumpet cuts through the mix."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/flute",
    axis: "instruments",
    label: "Flute",
    hint: "Флейта, воздушная мелодия.",
    positive: {
      shared: [
        "A track with flute.",
        "An airy flute melody floats over the beat.",
        "A woodwind plays a light breathy melody.",
        "A soft airy pipe tone floats above the groove."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/sitar",
    axis: "instruments",
    label: "Sitar",
    hint: "Ситар, гудящие струны.",
    positive: {
      shared: [
        "A track with sitar.",
        "A buzzing plucked string drone from a sitar.",
        "A long-necked plucked instrument with sympathetic string buzz.",
        "A twanging Indian string tone with heavy resonance."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/kora",
    axis: "instruments",
    label: "Kora / Ngoni",
    hint: "Западноафриканские щипковые.",
    positive: {
      shared: [
        "A track with kora or ngoni.",
        "West African plucked string patterns.",
        "A gourd harp is plucked in cascading patterns.",
        "Rolling West African string figures ripple over the groove."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/steel-drum",
    axis: "instruments",
    label: "Steel drums",
    hint: "Ярко звенящие стил-пэны. Прежняя пометка на MuQ-MuLan снята: она опиралась на инверсию против акустичности SONARA, а этот эталон не отличает стил-пэн от любого другого живого инструмента.",
    positive: {
      shared: [
        "A track with steel drums.",
        "Bright metallic steel pan melodies.",
        "Tuned metal pans struck with rubber sticks.",
        "Bright ringing Caribbean pan tones carry the melody."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/congas",
    axis: "instruments",
    label: "Congas / Bongos",
    hint: "Ручные барабаны латинской перкуссии.",
    positive: {
      shared: [
        "A track with congas and bongos.",
        "Hand drums drive the percussion.",
        "Hand-struck barrel drums drive a rolling pattern.",
        "Open and muted hand drum tones layer over the beat."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/tabla",
    axis: "instruments",
    label: "Tabla",
    hint: "Индийские ручные барабаны.",
    positive: {
      shared: [
        "A track with tabla.",
        "Indian hand drum patterns carry the rhythm.",
        "Tuned hand drums with sliding bass strokes.",
        "Fast intricate Indian hand drum phrasing."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/live-drums",
    axis: "instruments",
    label: "Live drum kit",
    hint: "Живая установка, человеческий тайминг.",
    positive: {
      shared: [
        "A track with a live drum kit.",
        "A drummer plays with human timing and dynamics.",
        "An acoustic kit recorded in a room with real cymbals.",
        "Kick, snare and hats breathe with a human feel."
      ]
    },
    negative: {
      shared: ["A drum machine and synthesizer track."]
    },
    negativeWeight: 0.5
  },
  {
    key: "instruments/808",
    axis: "instruments",
    label: "808",
    hint: "Гулкие 808-кики и клэпы.",
    positive: {
      shared: [
        "A track with 808 drums.",
        "Booming 808 kicks and crisp claps.",
        "A long sliding sub kick with a sharp snap.",
        "Deep sustained drum machine bass tones."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/909",
    axis: "instruments",
    label: "909",
    hint: "Классический 909-набор.",
    positive: {
      shared: [
        "A track with 909 drums.",
        "A classic 909 kick, clap and open hat.",
        "A punchy analog drum machine with a bright clap.",
        "Crisp machine hats and a tight tuned kick."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/modular",
    axis: "instruments",
    label: "Modular",
    hint: "Модульный синтез, патчи и секвенции.",
    positive: {
      shared: [
        "A track with modular synthesis.",
        "Patched analog bleeps and evolving modular sequences.",
        "Self-generating patch sequences shift over time.",
        "Unstable analog voltages create evolving electronic textures."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "space/dub-delay",
    axis: "space",
    label: "Dub delay",
    hint: "Даб-эхо, уходящие повторы.",
    positive: {
      shared: [
        "A track soaked in dub delay.",
        "Echoes repeat and fade across the mix.",
        "A single hit repeats and dissolves into feedback.",
        "Tape echo trails wander across the stereo field."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "space/gated",
    axis: "space",
    label: "Gated reverb",
    hint: "Обрезанный гейтом ревер.",
    positive: {
      shared: [
        "A track with gated reverb.",
        "Reverb tails cut off abruptly.",
        "A big reverb slams shut right after each hit.",
        "Short bursts of room sound clipped tight to the beat."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "space/wide",
    axis: "space",
    label: "Wide stereo",
    hint: "Широкая стереокартина.",
    positive: {
      shared: [
        "A wide stereo track.",
        "Sounds spread far across the stereo field.",
        "Synths and pads stretch to the far left and right.",
        "A very broad stereo image with movement across the field."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "energy/building",
    axis: "energy",
    label: "Building",
    hint: "Постепенное нарастание напряжения.",
    positive: {
      shared: [
        "A track that slowly builds tension.",
        "Layers add up toward a release.",
        "Elements enter one by one and the pressure rises.",
        "The arrangement grows steadily toward a peak."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "energy/hypnotic",
    axis: "energy",
    label: "Hypnotic",
    hint: "Гипнотическая петля, почти без изменений.",
    positive: {
      shared: [
        "A hypnotic looping track.",
        "A repeating pattern barely changes for minutes.",
        "A single loop repeats with tiny gradual changes.",
        "The groove locks in and stays there, trance-like."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "energy/aggressive",
    axis: "energy",
    label: "Aggressive",
    hint: "Жёстко, громко, с напором.",
    positive: {
      shared: [
        "An aggressive hard track.",
        "Distorted drums hit with force.",
        "Loud harsh drums and a driving forceful energy.",
        "A hard-hitting track with sharp attacking sounds."
      ]
    },
    negative: {
      shared: ["A quiet restrained deep track with muted drums."]
    },
    negativeWeight: 0.5
  },
  {
    key: "energy/sparse",
    axis: "energy",
    label: "Sparse",
    hint: "Мало элементов, много воздуха.",
    positive: {
      shared: [
        "A sparse minimal track.",
        "Few elements with wide space between them.",
        "Only a few sounds, with long gaps between them.",
        "An open arrangement with plenty of silence."
      ]
    },
    negative: {
      shared: ["A dense busy arrangement with many layers."]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/tech-house",
    axis: "style",
    label: "Tech house",
    hint: "Плотные тех-хаусовые барабаны, катящийся бас.",
    positive: {
      shared: [
        "A tech house track.",
        "Tight tech house drums with a rolling bassline.",
        "A groovy club track with punchy drums and a bouncing bassline.",
        "Stripped back house with a techno edge."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/deep-house",
    axis: "style",
    label: "Deep house",
    hint: "Тёплые аккорды, мягкий свингующий бит.",
    positive: {
      shared: [
        "A deep house track.",
        "Warm chords over a soft swung house beat.",
        "Deep pads and jazzy chords over a laid-back beat.",
        "A smooth club track with a mellow deep atmosphere."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/jazzy-house",
    axis: "style",
    label: "Jazzy house",
    hint: "Хаус с джазовыми аккордами и живыми семплами.",
    positive: {
      shared: [
        "A jazzy house track.",
        "House drums with jazz chords and live instrument samples.",
        "House rhythms under improvised jazz keys and horns.",
        "A club track coloured by acoustic jazz playing."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/afro-house",
    axis: "style",
    label: "Afro house",
    hint: "Африканская перкуссия и чанты поверх хауса.",
    positive: {
      shared: [
        "An afro house track.",
        "House drums with African percussion and chants.",
        "Layered hand percussion over a rolling four four groove.",
        "Tribal drums and call and response vocals in a club track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/progressive",
    axis: "style",
    label: "Progressive",
    hint: "Долгие развивающиеся билды, мелодичные слои.",
    positive: {
      shared: [
        "A progressive house track.",
        "Long evolving builds with melodic synth layers.",
        "A long arrangement that unfolds gradually over many minutes.",
        "Melodic synth layers build and recede in slow waves."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/ambient-techno",
    axis: "style",
    label: "Ambient techno",
    hint: "Мягкие пэды над отдалённым пульсом.",
    positive: {
      shared: [
        "An ambient techno track.",
        "Soft pads over a distant steady pulse.",
        "Washed pads drift over a muted machine pulse.",
        "A dreamy electronic track with a gentle steady beat."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/industrial",
    axis: "style",
    label: "Industrial",
    hint: "Машинный шум и тяжёлые удары.",
    positive: {
      shared: [
        "An industrial track.",
        "Harsh machine noise and pounding drums.",
        "Metallic clanging percussion and distorted machine textures.",
        "A brutal mechanical track built out of noise."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/ebm",
    axis: "style",
    label: "EBM",
    hint: "Жёсткий секвенированный бас, холодный вокал.",
    positive: {
      shared: [
        "An EBM track.",
        "Stiff sequenced bass with cold vocals.",
        "Rigid sequenced synth bass with a marching beat.",
        "Cold body music with shouted processed vocals."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/idm",
    axis: "style",
    label: "IDM",
    hint: "Изощрённая программация, странная мелодика.",
    positive: {
      shared: [
        "An IDM track.",
        "Intricate programmed drums and odd melodic patterns.",
        "Glitched complex drum programming with melodic detail.",
        "Experimental electronic music with intricate rhythmic edits."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/jungle",
    axis: "style",
    label: "Jungle",
    hint: "Быстрые нарезанные брейки и глубокий саб.",
    positive: {
      shared: [
        "A jungle track.",
        "Fast chopped breakbeats with deep sub bass.",
        "Chopped amen breaks race over a heavy sub bassline.",
        "Ragga-influenced breakbeat music at high tempo."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/drum-and-bass",
    axis: "style",
    label: "Drum & bass",
    hint: "Быстрый two-step брейк и катящийся саб.",
    positive: {
      shared: [
        "A drum and bass track.",
        "Fast two-step breaks with a rolling sub bassline.",
        "Fast breakbeats at high tempo over a deep bassline.",
        "Rolling drums around one hundred seventy beats per minute."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/uk-garage",
    axis: "style",
    label: "UK garage",
    hint: "Свингующие гаражные барабаны, вокальные нарезки.",
    positive: {
      shared: [
        "A UK garage track.",
        "Swung garage drums with clipped vocal chops.",
        "Shuffled syncopated drums with pitched vocal cuts.",
        "A bouncy garage groove with a skipping snare."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/footwork",
    axis: "style",
    label: "Footwork",
    hint: "Быстрые заикающиеся триоли.",
    positive: {
      shared: [
        "A footwork track.",
        "Fast stuttering triplet drum patterns.",
        "Rapid triplet kick patterns with chopped vocal samples.",
        "Frantic Chicago dance rhythms at high tempo."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/broken-beat",
    axis: "style",
    label: "Broken beat",
    hint: "Джазовые синкопы с живым ощущением.",
    positive: {
      shared: [
        "A broken beat track.",
        "Jazzy syncopated club rhythms with a live feel.",
        "Syncopated club drums with a loose jazzy swing.",
        "West London style broken rhythms with soulful chords."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/trip-hop",
    axis: "style",
    label: "Trip hop",
    hint: "Медленные пыльные биты, дымная атмосфера.",
    positive: {
      shared: [
        "A trip hop track.",
        "Slow dusty beats with a smoky atmosphere.",
        "Slow heavy drums under a hazy cinematic mood.",
        "Downtempo beats with sampled strings and vinyl crackle."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/downtempo",
    axis: "style",
    label: "Downtempo",
    hint: "Медленный электронный грув для слушания.",
    positive: {
      shared: [
        "A downtempo track.",
        "A slow electronic groove made for listening.",
        "A relaxed electronic groove at a slow tempo.",
        "Chilled beats made for listening rather than dancing."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/bass-music",
    axis: "style",
    label: "Bass music",
    hint: "Разреженные барабаны, тяжёлый вес низа.",
    positive: {
      shared: [
        "A bass music track.",
        "Sparse drums with heavy weighted low end.",
        "Wide open drums with an enormous low end focus.",
        "Sound system music built around weight and space."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/dub-reggae",
    axis: "style",
    label: "Dub reggae",
    hint: "Оффбитовый скэнк, эхо и тяжёлый бас.",
    positive: {
      shared: [
        "A dub reggae track.",
        "Offbeat skank chords with heavy echo and bass.",
        "Offbeat guitar chops drenched in spring reverb.",
        "A heavy reggae bassline with delay-soaked drops."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/disco",
    axis: "style",
    label: "Disco",
    hint: "Живые струнные, ровная бочка, фанковая гитара.",
    positive: {
      shared: [
        "A disco track.",
        "Live strings, four on the floor drums and funk guitar.",
        "Live drums, funk guitar and lush string arrangements.",
        "A groovy seventies dance track played by a real band."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/funk",
    axis: "style",
    label: "Funk",
    hint: "Синкопированные живые бас и гитара.",
    positive: {
      shared: [
        "A funk track.",
        "Syncopated live bass and guitar with tight drums.",
        "Tight live drums with a slapping bass and rhythm guitar.",
        "A groove-driven band track with horn stabs."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/soundtrack",
    axis: "style",
    label: "Soundtrack",
    hint: "Кинематографично, оркестровое напряжение.",
    positive: {
      shared: [
        "A cinematic soundtrack piece.",
        "Orchestral tension written for picture.",
        "Orchestral textures written to underscore a scene.",
        "Filmic strings and brass building dramatic tension."
      ]
    },
    negativeWeight: 0
  }
];

export const defaultTextPromptModel: TextPromptModel = "mulan";

/**
 * Weight applied to hard negatives when the request carries none.
 *
 * Mirrors CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT in src/dj_track_similarity/search.py,
 * which is what the server falls back to. The benchmark showed no single value
 * fits every concept, so presets carry their own and this is only the floor for
 * a hand-written bank.
 */
export const defaultNegativeWeight = 0.5;

/** Bounds accepted by TextSearchRequest.negative_weight. */
export const negativeWeightRange = { min: 0, max: 2, step: 0.05 } as const;

export function presetsForAxis(axisKey: string): TextPromptPreset[] {
  return textPromptPresets.filter((preset) => preset.axis === axisKey);
}

export function presetByKey(key: string): TextPromptPreset | undefined {
  return textPromptPresets.find((preset) => preset.key === key);
}

export function axisByKey(key: string): TextPromptAxis | undefined {
  return textPromptAxes.find((axis) => axis.key === key);
}

/** The model measured to rank this one label best, or undefined if untested. */
export function modelForPreset(key: string): TextPromptModel | undefined {
  const preset = presetByKey(key);
  if (!preset) return undefined;
  return preset.model ?? axisByKey(preset.axis)?.model;
}

/**
 * The model measured to rank every selected preset best, or null.
 *
 * Rank fusion was measured and rejected, so the two models are never combined:
 * mixing drags the stronger model toward the weaker one exactly where the gap
 * is widest. The choice is made per axis instead. A selection spanning axes
 * with different winners returns null, because one search runs against one
 * embedding family and no single answer is right for all of them.
 */
export function recommendedModel(keys: string[]): TextPromptModel | null {
  let choice: TextPromptModel | null = null;
  for (const key of keys) {
    const model = modelForPreset(key);
    if (!model) continue;
    if (choice && choice !== model) return null;
    choice = model;
  }
  return choice;
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

/**
 * Merge the selected presets into one editable bank.
 *
 * Presets whose measured negative weight is zero contribute no negatives at all,
 * and the merged weight is the smallest contributing one, so combining a
 * calibrated preset with a cautious one never subtracts more than the cautious
 * preset was measured to tolerate.
 */
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
