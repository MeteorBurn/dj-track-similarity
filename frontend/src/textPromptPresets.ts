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
  { key: "groove", label: "Groove", hint: "Кач и микротайминг: свинг, шафл, триоли, расхлябанность или жёсткость сетки. Рисунок бита — на оси Rhythm. Эталона нет — проверяй ушами." },
  { key: "rhythm", label: "Rhythm", hint: "Рисунок бита: брейки, ровная бочка, халфтайм, two-step, полиритмия. На ручных метках breakbeat: MuQ-MuLan 0.949 против CLAP 0.853.", model: "mulan" },
  { key: "percussion", label: "Percussion", hint: "Характер перкуссии: кликовая, деревянная, глитчевая, шейкеры, хэты. Тембр и поведение ударных, не рисунок. Эталона нет." },
  { key: "bass", label: "Bass", hint: "Характер баса: саб, кислота, рииз, FM, резина, перегруз. Эталон есть у одной метки — модель не рекомендуется." },
  { key: "synths", label: "Synths", hint: "Характер синтезаторов: квирки, пластик, вода, пилы, блипы, пэды, модуляр. Эталона нет." },
  { key: "instruments", label: "Instruments", hint: "Конкретные инструменты и машины. Рекомендации нет: все метки оси сверялись с одним и тем же числом SONARA — акустичностью. Оно отвечает «звучит ли живо», а не «нашёлся ли ситар», и в электронной библиотеке штрафует метку ровно за верную находку: сэмпл ситара внутри трека акустичность не поднимает. Сверяйся ушами. Наблюдение с двух прослушиваний, не замер: CLAP берёт метку там, где инструмент реально играют (калимба), MuQ-MuLan — там, где он приходит сэмплом внутри электроники (ситар)." },
  { key: "organic", label: "Organic", hint: "Происхождение звука: живое ↔ синтетическое, как континуум. Замер живого полюса на ручных метках: MuQ-MuLan 0.827, CLAP 0.814 — паритет, рекомендации нет." },
  { key: "texture", label: "Texture", hint: "Обработка поверхности: лента, пыль, сатурация, глитч, дымка, чистота. Замер до разделения с Timbre: CLAP 0.343 против MuQ-MuLan 0.230.", model: "clap" },
  { key: "timbre", label: "Timbre", hint: "Окраска тона: металл, стекло, резонанс, тепло и холод. Тембровые слова работают лучше в связке с источником — см. оси Percussion, Bass и Synths." },
  { key: "space", label: "Space", hint: "Сухо, комната, пещера, дилей, ширина стерео. Ни одной метки с эталоном — надёжность неизвестна." },
  { key: "harmony", label: "Harmony", hint: "Аккорды и плотность смен: модальность, диссонанс, дрон, джаз. Лад минор-мажор берётся из SONARA: обе текстовые модели на нём на уровне случайности. Модели разошлись на 0.017 — рекомендации нет." },
  { key: "movement", label: "Movement", hint: "Движение внутри звука: арпеджио, свипы, морфинг, качание сайдчейна, шагающие линии. Структура трека во времени текстовым моделям не слышна — обе смотрят 10-секундными окнами; это территория SONARA." },
  { key: "density", label: "Density", hint: "Плотность аранжировки: воздух и пустота ↔ стена слоёв. Частично проверяемо по SONARA onset density." },
  { key: "complexity", label: "Complexity", hint: "Детализация программинга: простой луп ↔ микро-редактура. Ортогональна Density: минимал бывает изощрённым." },
  { key: "mood", label: "Mood", hint: "Настроение: мрак, эйфория, меланхолия, жуть, игривость. Эталона нет — проверяй ушами." },
  { key: "energy", label: "Energy", hint: "Уровень мощности: сдержанно ↔ на всю. Роль в сете — на оси Function. Старый замер оси распался при её разделении — рекомендации нет." },
  { key: "tension", label: "Tension", hint: "Давление и ожидание: нарастание, гипнотическое плато, тревога. Не громкость — тихий трек тоже умеет давить." },
  { key: "abstract", label: "Abstract", hint: "Функциональность ↔ абстракция. Единственная метка с эталоном закреплена за CLAP: 0.980 против 0.957 на ручных метках; для оси целиком рекомендации нет." },
  { key: "voice", label: "Vocals", hint: "Присутствие и характер голоса: вокал, речь, нарезки, хор, инструментал. Рекомендации нет, и эталона у оси тоже нет: вероятность вокала SONARA исключена из сверки TEXT — её процент не отражает реальное наличие голоса в треке. Надёжность этих меток проверяй только ушами." },
  { key: "function", label: "Function", hint: "Роль в сете: разогрев, пик, финал, интерлюдия, DJ tool. Слышима косвенно — через энергию, плотность и настроение." },
  { key: "style", label: "Style", hint: "Жанры и сцены — грубый слой поверх тонких осей, описан звучанием, без опоры на файловые теги. На ручных метках minimal/deep-tech: MuQ-MuLan 0.928 против CLAP 0.781.", model: "mulan" }
];

export const textPromptPresets: TextPromptPreset[] = [
  {
    key: "rhythm/breakbeat",
    axis: "rhythm",
    label: "Breakbeat",
    hint: "Ломаные драмы: рубленые брейки, синкопы, доли мимо сетки. Ровный кик уходит в негативы, поэтому хаус и техно из выдачи вымываются. Тег-банк, замер на этой библиотеке: MuQ-MuLan 0.949, CLAP 0.853.",
    positive: {
      shared: [
        "breakbeat.",
        "breakbeat, broken beat, chopped drum breaks.",
        "syncopated drums, off-grid rhythm, shuffled hits.",
        "breaks, jungle drums, uneven drum pattern."
      ]
    },
    negative: {
      shared: [
        "four-on-the-floor, house, techno.",
        "steady kick, straight beat, even drum timing.",
        "minimal house groove, regular kick pattern."
      ]
    },
    negativeWeight: 1.0,
    measured: { mulan: 0.949, clap: 0.853 }
  },
  {
    key: "rhythm/four-on-the-floor",
    axis: "rhythm",
    label: "Four-on-the-floor",
    hint: "Кик на каждую долю: хаус, техно, любой прямой танцевальный бит. Метка про рисунок барабанов, а не про темп или жанр — темп задавай отдельно.",
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
    key: "rhythm/halftime",
    axis: "rhythm",
    label: "Halftime",
    hint: "Бит вдвое реже: тяжёлые редкие удары, много воздуха между ними. Темп банк не задаёт, поэтому придут и медленные треки, и быстрые с халфтайм-рисунком.",
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
    hint: "Свинг и кач: доли смещены, хэты катятся неровно. Жёстко квантованное техно вычитается негативами, гаражное и хаусовое поднимается.",
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
    key: "rhythm/polyrhythm",
    axis: "rhythm",
    label: "Polyrhythm / Tribal",
    hint: "Слоистая перкуссия: ручные барабаны, шейкеры, переплетённые рисунки. Пересекается с Afro house и Congas — здесь про плотность рисунка, а не про происхождение сэмплов.",
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
    key: "bass/sub",
    axis: "bass",
    label: "Sub / Rolling bass",
    hint: "Глубокий саб: непрерывная катящаяся линия, вес в самом низу. Метка про низ, а не про жанр — придёт и dub techno, и bass music.",
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
    key: "bass/acid",
    axis: "bass",
    label: "Acid 303",
    hint: "Резонансная 303: скрипучая линия, фильтровые свипы, кислотный характер. Тембр редкий и узнаваемый, выдача обычно чистая.",
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
    key: "bass/dry-punch",
    axis: "bass",
    label: "Dry punchy bass",
    hint: "Короткий сухой бас: стаккато-стабы, tech house, ничего не тянется. Прямая противоположность Sub — их негативы вычитают друг друга.",
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
    hint: "Ленточные дилеи, пружинный ревер, аккордовые стабы в дымке. Тянет dub techno целиком, а не только обработку.",
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
    key: "timbre/metallic",
    axis: "timbre",
    label: "Metallic / Industrial",
    hint: "Металлическая перкуссия, скрежет, машинная грязь. Пересекается с Industrial: здесь тембр, там жанр.",
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
    hint: "Гранулярка и глитч: клики, микронарезка, цифровые артефакты. Обычно приходит вместе с IDM и Experimental.",
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
    hint: "Шипение ленты, треск винила, узкая полоса, пыль. Ловит не только приём, но и просто слабые оцифровки — проверяй, что это эстетика, а не качество файла.",
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
    hint: "Чистый современный продакшн: широкий прозрачный микс, острые транзиенты. CLAP инвертирует против спектрального роллоффа (0.372), MuQ-MuLan даёт 0.621 — ось перекрыта.",
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
    hint: "Голос как заметный элемент: пение, речь, вокальные хуки. Пол и характер голоса метка не различает — для этого бери узкие метки оси. Тег-банк, замер на ручных метках Rhythm Lab: MuQ-MuLan 0.904, CLAP 0.897 — победителя нет, прежняя привязка к CLAP снята.",
    positive: {
      shared: [
        "vocals.",
        "vocal, vocals, singing.",
        "female vocal, male vocal, singer.",
        "vocal music, sung lyrics, voice."
      ]
    },
    negative: {
      shared: [
        "instrumental.",
        "instrumental, instrumental music.",
        "instrumental club track, drums and bass only."
      ]
    },
    negativeWeight: { clap: 1.0, mulan: 0.75 },
    measured: { clap: 0.897, mulan: 0.904 }
  },
  {
    key: "voice/spoken",
    axis: "voice",
    label: "Spoken word",
    hint: "Разговорная речь: монолог, начитка, семплы говорящего голоса. От Dialogue sample отличается тем, что речь ведёт трек, а не вставлена фрагментом.",
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
    hint: "Нарезанные вокальные фразы в роли перкуссии. Классика хауса и гаража; полноценный лид вычитается негативами.",
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
    hint: "Треки без голоса. Работает как фильтр: ставь вместе с другой меткой, чтобы убрать из выдачи вокальные версии.",
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
    key: "organic/acoustic",
    axis: "organic",
    label: "Organic / Acoustic",
    hint: "Живой полюс оси: натуральный тембр, игра руками, человеческий тайминг. Тег-банк, замер на этой библиотеке: MuQ-MuLan 0.827, CLAP 0.814.",
    positive: {
      shared: [
        "acoustic.",
        "acoustic, live instruments, band.",
        "guitar, piano, strings, brass.",
        "live drums, organic, unplugged."
      ]
    },
    negative: {
      shared: [
        "electronic, drum machine, synthesizer.",
        "programmed beats, sequenced synths.",
        "edm, club, digital production."
      ]
    },
    negativeWeight: { clap: 1.0, mulan: 0.75 },
    measured: { clap: 0.814, mulan: 0.827 }
  },
  {
    key: "instruments/piano",
    axis: "instruments",
    label: "Piano",
    hint: "Акустическое фортепиано ведёт гармонию или мелодию. Электропиано ищи меткой Rhodes.",
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
    hint: "Гитара: рифф, перебор, линия поверх бита. Нейлон и классика — отдельной меткой Nylon guitar.",
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
    hint: "Струнные и духовые, оркестровые аранжировки. Метка широкая: синтетические струнные тоже попадут.",
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
    hint: "Сухой микс: всё близко, хвосты короткие, воздуха между элементами нет.",
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
    hint: "Естественная комната вокруг инструментов: короткий натуральный ревер, ощущение живой записи.",
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
    hint: "Огромный ревер: длинные хвосты, аранжировка размыта пространством. Часто вытягивает эмбиент целиком.",
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
    key: "function/warm-up",
    axis: "function",
    label: "Warm-up",
    hint: "Разогрев: приглушённый кик, мягкие пэды, сабовый низ, сдержанная динамика.",
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
    key: "function/peak",
    axis: "function",
    label: "Peak time",
    hint: "Пик: громко, ярко, плотно, с дропом.",
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
    key: "function/closing",
    axis: "function",
    label: "Closing",
    hint: "Финал сета: медленно, тепло, меланхолично, барабаны разрежены.",
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
    key: "function/ambient",
    axis: "function",
    label: "Ambient",
    hint: "Без бита: дроны, длинные тона, атмосфера. Танцевальные треки вычитаются негативами.",
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
    hint: "Минимал и дип-тек: сухая перкуссия, катящийся бас, вокальные обрезки. Тег-банк, замер на этой библиотеке: MuQ-MuLan 0.928, CLAP 0.781. Прежний вывод про вредные негативы относился к старому банку: с тег-негативами вычитание помогает.",
    positive: {
      shared: [
        "minimal tech house.",
        "minimal house, deep tech, micro house.",
        "tech house, minimal techno, groovy.",
        "stripped-back club track, rolling bassline, dry drums."
      ]
    },
    negative: {
      shared: [
        "big room, progressive house, trance.",
        "hard techno, industrial.",
        "ambient, beatless."
      ]
    },
    negativeWeight: { clap: 1.0, mulan: 0.75 },
    measured: { mulan: 0.928, clap: 0.781 }
  },
  {
    key: "style/electro",
    axis: "style",
    label: "Electro",
    hint: "Электро: 808-грув, синкопированный машинный бит, холодные синты.",
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
    key: "abstract/experimental",
    axis: "abstract",
    label: "Experimental",
    hint: "Абстрактное и странное: рваный ритм, необычная фактура. Замер на этой библиотеке: CLAP 0.980, MuQ-MuLan 0.957 — CLAP впереди на всех весах, метка закреплена за ним.",
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
    measured: { clap: 0.980, mulan: 0.957 },
    model: "clap"
  },
  {
    key: "rhythm/amen-break",
    axis: "rhythm",
    label: "Amen break",
    hint: "Нарезанный amen: быстрые сбивки, ghost-ноты, барабаны с винила. Уже, чем Breakbeat: тянет именно семплированную живую установку, а не любые ломаные драмы.",
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
    key: "rhythm/two-step",
    axis: "rhythm",
    label: "Two-step",
    hint: "Гаражный скачущий рисунок: кик пропускает доли, снейр на 2 и 4. Пересекается с UK garage — здесь только барабаны, там жанр целиком.",
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
    hint: "Пыльный хип-хоп-бит: тяжёлый кик, трескучий снейр, винил в фоне. Обычно приходит вместе с trip hop и downtempo.",
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
    hint: "Галоп: повторяющаяся триольная фигура, барабаны скачут вперёд. Метка узкая — если такого в библиотеке нет, выдача сползёт в общий триольный свинг.",
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
    hint: "Триоли в хэтах: доля делится на три, грув катится. От Shuffle отличается тем, что описывает деление доли, а не общий кач.",
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
    key: "rhythm/broken-techno",
    axis: "rhythm",
    label: "Broken techno",
    hint: "Техно со сбитым киком: темп клубный, но кик спотыкается. Ставь, когда трек не лёг ни в Breakbeat, ни в Four-on-the-floor.",
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
    key: "bass/reese",
    axis: "bass",
    label: "Reese bass",
    hint: "Широкий рычащий бас из двух расстроенных пил, медленная модуляция. Тянет за собой jungle и drum & bass, где этот тембр — норма.",
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
    key: "bass/distorted",
    axis: "bass",
    label: "Distorted bass",
    hint: "Перегруженный грязный низ: клиппинг, сатурация, рваные края. Часто вытягивает индастриал и хард-техно целиком, а не только бас.",
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
    key: "movement/walking-bass",
    axis: "movement",
    label: "Walking bass",
    hint: "Шагающий бас четвертями, джазовая манера. Почти всегда указывает на живую игру, а не на клубный трек.",
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
    key: "bass/fm",
    axis: "bass",
    label: "FM bass",
    hint: "Металлический цифровой FM-бас: колокольная атака, быстрый спад. Соседствует с Glassy — оба про яркие цифровые обертоны.",
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
    hint: "Аналоговая сатурация: лента и лампа, всё склеено компрессией в один плотный звук. Соседствует с Distorted bass — здесь про весь микс, там только про низ.",
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
    key: "timbre/glassy",
    axis: "timbre",
    label: "Glassy",
    hint: "Стеклянные кристальные верхи: колокольчики, звонкие синты. CLAP инвертирует против спектрального центроида (0.294) — ось перекрыта на MuQ-MuLan.",
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
    key: "percussion/wooden",
    axis: "percussion",
    label: "Wooden",
    hint: "Сухая деревянная перкуссия: вудблок, римшот, полые томы, короткий спад.",
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
    key: "timbre/resonant",
    axis: "timbre",
    label: "Resonant filter",
    hint: "Резонансный фильтр: свип поёт на пике, характерный свист поверх аккордов. Пересекается с Acid 303 — там тот же приём, но на басу.",
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
    hint: "Всё за мягким фильтром: верх срезан, элементы размыты. Близко к Cavernous, но про фильтрацию, а не про ревер.",
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
    hint: "Модальность: одна гамма на весь трек, дорийский колорит. Про статичную гармонию — сюда же попадут долгие клубные ваны.",
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
    hint: "Диссонанс: неразрешённые созвучия, атональные кластеры. Часто пересекается с Experimental и Industrial.",
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
    hint: "Один аккорд или тон на весь трек. Пересекается с Ambient и Hypnotic — здесь именно про гармонию, а не про отсутствие бита.",
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
    hint: "Расширенные джазовые аккорды: септимы, ноны, тринадцатые. CLAP ранжирует эту метку против плотности смен аккордов наоборот, поэтому она закреплена за MuQ-MuLan.",
    positive: {
      shared: [
        "A track with extended jazz chords.",
        "Lush seventh and ninth chord voicings.",
        "Rich seventh, ninth and thirteenth voicings colour the chords.",
        "Complex jazz harmony moves under the melody."
      ]
    },
    negativeWeight: 0,
    model: "mulan"
  },
  {
    key: "harmony/blues",
    axis: "harmony",
    label: "Blues",
    hint: "Блюзовые ноты и двенадцатитактовая форма. Указывает на живую музыку чаще, чем на клубную.",
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
    hint: "Расстроенный строй: осцилляторы плывут, высота качается. Не путать с Reese: там расстройка — тембр баса, здесь характер всего трека.",
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
    hint: "Женский ведущий вокал. Банк описывает высокий поющий голос, поэтому обработанный или высокий мужской вокал тоже подойдёт под описание.",
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
    hint: "Мужской ведущий вокал: низкий голос ведёт мелодию. Границу между мужским и женским текстовые модели держат нестрого — проверяй ушами.",
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
    hint: "Хор: многоголосие, длинные аккорды голосами. Часто приходит вместе с Soundtrack и Ambient.",
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
    hint: "Повторяющийся чант: короткая фраза, скандирование группой. Пересекается с Afro house.",
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
    hint: "Шёпот и придыхание близко к микрофону. Метка узкая — в электронной библиотеке находок будет мало.",
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
    hint: "Вокодер и токбокс: роботизированный голос с синтетическими формантами. Соседствует с Electro.",
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
    hint: "Семпл речи из фильма или записи поверх музыки. Голос здесь вставка, а не ведущая партия.",
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
    hint: "Rhodes: тёплое электропиано, тремоло, колокольная атака.",
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
    hint: "Хаммонд: драубары, вращающийся динамик, тянущиеся аккорды.",
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
    hint: "Маримба: круглые деревянные мэллеты, катящаяся мелодия. Рядом стоит Vibraphone — там металл вместо дерева.",
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
    hint: "Вибрафон: металлические мэллеты, медленное вибрато, длинный сустейн.",
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
    hint: "Калимба: щипковые язычки, маленький яркий тон.",
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
    hint: "Классическая гитара: нейлон, перебор пальцами, мягкий тон.",
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
    hint: "Слэп-бас: щелчки большим пальцем, яркая фанковая атака.",
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
    hint: "Контрабас: деревянный акустический низ, щипок пальцами.",
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
    hint: "Саксофон: дыхание в трости, экспрессивное соло поверх грува.",
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
    hint: "Труба: яркая пронзительная медь, открытая или под сурдиной.",
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
    hint: "Флейта: лёгкая воздушная мелодия с придыханием.",
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
    hint: "Ситар: гудящие струны и сильный резонанс. Наблюдение с прослушивания, не замер: сэмпл ситара внутри электроники чаще берёт MuQ-MuLan.",
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
    hint: "Кора и нгони: западноафриканские щипковые, каскадные фигуры.",
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
    hint: "Стил-пэн: настроенные металлические пэны, звонкий карибский тон. Прежняя пометка на MuQ-MuLan снята: она опиралась на инверсию против акустичности SONARA, а этот эталон не отличает стил-пэн от любого другого живого инструмента.",
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
    hint: "Конги и бонго: ручные барабаны, открытые и заглушённые тоны.",
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
    hint: "Табла: индийские ручные барабаны, скользящие басовые удары.",
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
    hint: "Живая установка: человеческий тайминг, настоящие тарелки, комната. Драм-машина вычитается негативами.",
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
    hint: "808: гулкий скользящий кик-саб и сухой клэп.",
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
    hint: "909: классический кик, клэп и открытый хэт аналоговой машины.",
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
    key: "synths/modular",
    axis: "synths",
    label: "Modular",
    hint: "Модульный синтез: патчи, самоиграющие секвенции, плывущие напряжения.",
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
    hint: "Даб-эхо: повторы уходят в обратную связь и растворяются. Пересекается с Dubby / Tape.",
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
    hint: "Гейтед-ревер: большой хвост обрублен гейтом сразу после удара.",
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
    hint: "Широкое стерео: элементы разнесены по краям панорамы. Моно и узкие миксы уйдут вниз выдачи.",
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
    key: "tension/building",
    axis: "tension",
    label: "Building",
    hint: "Постепенное нарастание: слои входят по одному, давление растёт к дропу.",
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
    key: "tension/hypnotic",
    axis: "tension",
    label: "Hypnotic",
    hint: "Гипнотическая петля: рисунок почти не меняется минутами.",
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
    hint: "Жёстко и громко: перегруженные барабаны, напор, острая атака.",
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
    key: "density/sparse",
    axis: "density",
    label: "Sparse",
    hint: "Мало элементов, много воздуха и пауз. Противоположность плотной аранжировке.",
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
    hint: "Тех-хаус: плотные барабаны, катящийся бас, клубная функциональность.",
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
    hint: "Дип-хаус: тёплые аккорды, мягкий свингующий бит, спокойная атмосфера.",
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
    hint: "Джазовый хаус: живые клавиши и духовые поверх хаусовых барабанов.",
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
    hint: "Афро-хаус: ручная перкуссия и чанты поверх ровного грува. Пересекается с Polyrhythm и Chant.",
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
    hint: "Прогрессив: долгие билды, мелодичные слои, развитие на много минут.",
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
    hint: "Эмбиент-техно: мягкие пэды над отдалённым ровным пульсом.",
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
    hint: "Индастриал: машинный шум, тяжёлые удары, металл. Пересекается с Metallic.",
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
    hint: "EBM: жёсткий секвенированный бас, маршевый бит, холодный обработанный вокал.",
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
    hint: "IDM: изощрённая программация барабанов, странная мелодика, глитчи.",
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
    hint: "Джангл: быстрые нарезанные брейки и глубокий саб, регги-влияние.",
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
    hint: "Драм-энд-бэйс: быстрый two-step брейк и катящийся саб около 170 ударов.",
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
    hint: "UK garage: свингующие барабаны, скачущий снейр, вокальные нарезки.",
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
    hint: "Футворк: быстрые заикающиеся триоли, нарезанный вокал, чикагский рисунок.",
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
    hint: "Broken beat: джазовые синкопы, живое ощущение, соул-аккорды.",
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
    hint: "Трип-хоп: медленные пыльные биты, дымная кинематографичная атмосфера.",
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
    hint: "Даунтемпо: медленный электронный грув для слушания, а не для танцпола.",
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
    hint: "Bass music: разреженные барабаны, вес и пространство, звук саунд-системы.",
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
    hint: "Даб-регги: оффбитовый скэнк, эхо, тяжёлый бас.",
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
    hint: "Диско: живые струнные, ровная бочка, фанковая гитара, играет настоящая группа.",
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
    hint: "Фанк: синкопированные живые бас и гитара, плотные барабаны, духовые стабы.",
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
    hint: "Саундтрек: кинематографично, оркестровое напряжение, музыка под картинку.",
    positive: {
      shared: [
        "A cinematic soundtrack piece.",
        "Orchestral tension written for picture.",
        "Orchestral textures written to underscore a scene.",
        "Filmic strings and brass building dramatic tension."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "bass/wobble",
    axis: "bass",
    label: "Wobble bass",
    hint: "Вобл-бас: LFO ведёт фильтр, тон качается в такт. Тянет за собой dubstep и bass music, ровный саб при этом уходит вниз.",
    positive: {
      shared: [
        "A track with a wobbling bassline.",
        "A bass tone swept by an LFO in time with the beat.",
        "The bass warps and wobbles as the filter opens and closes.",
        "A rubbery modulated bass lurches under the drums."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/reverse",
    axis: "texture",
    label: "Reversed",
    hint: "Реверс: звуки развёрнуты задом наперёд, вместо атаки — нарастание. Обычно поднимает треки с реверс-тарелками и всасывающими переходами.",
    positive: {
      shared: [
        "A track with reversed sounds.",
        "Backwards cymbals swell into the downbeat.",
        "Sounds play backwards and rise into every transition.",
        "Reversed samples suck the arrangement toward the next section."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "movement/arpeggio",
    axis: "movement",
    label: "Arpeggios",
    hint: "Арпеджио: аккорд разложен по нотам, секвенция бежит через гармонию. Пересекается с Trance и Modular.",
    positive: {
      shared: [
        "An arpeggiated electronic track.",
        "A synth arpeggio runs through the chords.",
        "Chord notes are played one after another in a fast sequence.",
        "A rippling arpeggiated pattern carries the harmony."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "voice/rap",
    axis: "voice",
    label: "Rap / MC",
    hint: "Читка: рифмованные строки в ритм под бит. Отделяет рэп от пения — поющий лид вычитается негативами.",
    positive: {
      shared: [
        "A rap track.",
        "A rapper delivers rhymes over the beat.",
        "Rhythmic rapped verses ride on top of the drums.",
        "An MC chats over a heavy sound system beat."
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
    key: "synths/pads",
    axis: "synths",
    label: "Synth pads",
    hint: "Синтезаторные пэды: длинные тянущиеся аккорды в фоне. Пересекается с Ambient techno и Warm-up.",
    positive: {
      shared: [
        "A track with synth pads.",
        "Long sustained synth chords hold behind the beat.",
        "Soft evolving pad layers fill the background.",
        "Warm held synth chords drift under the arrangement."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/dark",
    axis: "mood",
    label: "Dark / Menacing",
    hint: "Мрачно и угрожающе: холодный минорный тон, давящая атмосфера. Метка про настроение, а не про громкость — тихий зловещий трек тоже подойдёт.",
    positive: {
      shared: [
        "A dark menacing electronic track.",
        "A cold ominous groove with a heavy atmosphere.",
        "A brooding club track with a threatening mood.",
        "Shadowy minor tones press down on the arrangement."
      ]
    },
    negative: {
      shared: [
        "A bright uplifting dance track with happy chords.",
        "A warm sunny groove with a cheerful mood."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/acid-house",
    axis: "style",
    label: "Acid house",
    hint: "Эйсид-хаус: скрипящая 303 поверх сырых барабанов драм-машины. От метки Acid 303 отличается тем, что описывает трек целиком, а не тембр баса.",
    positive: {
      shared: [
        "An acid house track.",
        "A house groove built on a squelching 303 bassline.",
        "Late eighties acid house with raw drum machine drums.",
        "A hypnotic club track with a wriggling acid line."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/detroit-techno",
    axis: "style",
    label: "Detroit techno",
    hint: "Детройтское техно: тёплые струнные и джазовые аккорды поверх машинного грува.",
    positive: {
      shared: [
        "A Detroit techno track.",
        "Warm strings and machine drums in the Detroit style.",
        "Soulful analog chords over a stripped machine groove.",
        "Futuristic techno with jazzy synth harmony."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/hard-techno",
    axis: "style",
    label: "Hard techno",
    hint: "Хард-техно: быстрый перегруженный кик, металлические удары, напор без пауз.",
    positive: {
      shared: [
        "A hard techno track.",
        "Fast distorted kick drums pound at high tempo.",
        "Relentless loud kicks with metallic percussion hits.",
        "A raw fast club track built on a hard driving kick."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/trance",
    axis: "style",
    label: "Trance",
    hint: "Транс: длинные арпеджио и парящие пэды поверх ровного бита, долгие эйфорические билды.",
    positive: {
      shared: [
        "A trance track.",
        "Long melodic synth arpeggios over a driving beat.",
        "Uplifting synth melodies build over a rolling bassline.",
        "A euphoric electronic track with sweeping pads."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/clicky",
    axis: "percussion",
    label: "Clicky",
    hint: "Кликовая микроперкуссия: тики, щелчки, минимальная точность.",
    positive: {
      shared: [
        "clicky percussion.",
        "clicky, ticking, micro percussion.",
        "tiny clicks and ticks carry the rhythm.",
        "dry clicky hits, short and precise."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/splashy",
    axis: "percussion",
    label: "Splashy",
    hint: "Расплёскивающиеся тарелки и открытые хэты, рыхлая верхушка.",
    positive: {
      shared: [
        "splashy cymbals.",
        "splashy, washy cymbals and loose hats.",
        "cymbal wash spills over the groove.",
        "open hats splash across the beat."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/glitchy",
    axis: "percussion",
    label: "Glitchy micro",
    hint: "Глитч-перкуссия: клики-и-каты, микромонтаж, цифровой мусор в роли ударных.",
    positive: {
      shared: [
        "glitchy micro percussion.",
        "glitch percussion, clicks and cuts.",
        "stuttering micro-edited percussion details.",
        "tiny digital debris used as drums."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/rattling",
    axis: "percussion",
    label: "Rattling shakers",
    hint: "Шейкеры и трещотки: сухое шуршание ведёт грув.",
    positive: {
      shared: [
        "rattling shakers.",
        "shakers, maracas, rattling percussion.",
        "a rattling shaker layer drives the groove.",
        "dry rattles and shakes fill the rhythm."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/tight-hats",
    axis: "percussion",
    label: "Tight hats",
    hint: "Точные закрытые хэты: сухо, коротко, машинная дисциплина.",
    positive: {
      shared: [
        "crisp tight hi-hats.",
        "tight, precise closed hats.",
        "a needle-sharp hat pattern, controlled and dry.",
        "crisp hats tick with machine precision."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "bass/rubbery",
    axis: "bass",
    label: "Rubbery",
    hint: "Резиновый бас: пружинит, тянется и отскакивает.",
    positive: {
      shared: [
        "rubbery bass.",
        "rubbery, elastic, bouncing bassline.",
        "a springy rubber-band bass wobbles under the groove.",
        "elastic bass notes bounce and snap back."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "synths/quirky",
    axis: "synths",
    label: "Quirky digital",
    hint: "Квирки: странные игривые цифровые блипы с характером.",
    positive: {
      shared: [
        "quirky digital synths.",
        "quirky, playful digital blips.",
        "odd cartoonish synth accents, digital character.",
        "weird little synth noises with a wry digital personality."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "synths/plasticky",
    axis: "synths",
    label: "Plasticky",
    hint: "Пластиковые, нарочито искусственные пресетные тембры.",
    positive: {
      shared: [
        "plasticky synths.",
        "plastic, toy-like synth tones.",
        "cheap plastic preset sounds, deliberately artificial.",
        "toybox synths with a hollow plastic bounce."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "synths/watery",
    axis: "synths",
    label: "Watery",
    hint: "Водянистые текучие пэды и капли.",
    positive: {
      shared: [
        "watery synth pads.",
        "liquid, watery, flowing synth textures.",
        "droplet-like synth tones ripple through the mix.",
        "underwater filtered pads, fluid and soft."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "synths/buzzy",
    axis: "synths",
    label: "Buzzy saw",
    hint: "Жужжащие пилы: сырой зазубренный край.",
    positive: {
      shared: [
        "buzzy sawtooth synths.",
        "buzzy, raspy sawtooth stabs.",
        "a buzzing saw lead cuts through the mix.",
        "harsh sawtooth buzz with a raw edge."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "synths/bleepy",
    axis: "synths",
    label: "Bleepy",
    hint: "Блипы: редкие компьютерные пики и синусовые точки.",
    positive: {
      shared: [
        "bleepy minimal synths.",
        "bleeps, blips, short synth accents.",
        "sparse computer bleeps punctuate the groove.",
        "little sine blips ping across the stereo field."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "organic/synthetic",
    axis: "organic",
    label: "Synthetic",
    hint: "Синтетический полюс оси: только машины, ни одного живого источника.",
    positive: {
      shared: [
        "fully synthetic sound.",
        "synthetic, programmed, digital character.",
        "machine-made electronic sound, zero acoustic sources.",
        "a purely electronic palette of synthesizers and drum machines."
      ]
    },
    negative: {
      shared: [
        "acoustic instruments played by hand.",
        "a live band recording."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "organic/hybrid",
    axis: "organic",
    label: "Hybrid",
    hint: "Середина оси: живые сэмплы, вплетённые в программный грув.",
    positive: {
      shared: [
        "hybrid acoustic-electronic blend.",
        "sampled acoustic textures inside an electronic track.",
        "organic samples woven into a programmed groove.",
        "electronic production with acoustic instrument fragments."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "timbre/warm",
    axis: "timbre",
    label: "Warm / Rounded",
    hint: "Тёплый полюс тона: округлые мягкие тембры, мягкий верх.",
    positive: {
      shared: [
        "warm rounded tone.",
        "warm, soft, rounded timbres.",
        "mellow rounded tones with gentle highs.",
        "a warm tonal palette, smooth and full."
      ]
    },
    negative: {
      shared: [
        "cold brittle thin tones.",
        "icy harsh digital timbre."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/cold",
    axis: "timbre",
    label: "Cold / Brittle",
    hint: "Холодный полюс тона: ледяные тонкие тембры с жёстким краем.",
    positive: {
      shared: [
        "cold brittle tone.",
        "cold, icy, brittle timbres.",
        "thin frosty tones with hard edges.",
        "a cold clinical tonal palette."
      ]
    },
    negative: {
      shared: [
        "warm rounded mellow tones.",
        "soft cozy analog warmth."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "movement/evolving",
    axis: "movement",
    label: "Evolving",
    hint: "Медленный морфинг: текстуры постоянно и незаметно меняются.",
    positive: {
      shared: [
        "slowly evolving textures.",
        "evolving, morphing, gradually shifting sound.",
        "textures transform subtly over time.",
        "a subtly evolving arrangement in constant slow motion."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "movement/sweeping",
    axis: "movement",
    label: "Sweeping",
    hint: "Свипы: длинные проезды фильтра и волны слоёв.",
    positive: {
      shared: [
        "sweeping filter movement.",
        "filter sweeps, risers, moving resonance.",
        "long filter sweeps glide through the track.",
        "synth layers swell and sweep across the mix."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "movement/pumping",
    axis: "movement",
    label: "Pumping",
    hint: "Сайдчейн-дыхание: весь микс качается в такт бочке.",
    positive: {
      shared: [
        "pumping sidechain groove.",
        "sidechain pumping, breathing compression.",
        "the whole mix breathes in time with the kick.",
        "pumping ducked pads swell between the kicks."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "density/dense",
    axis: "density",
    label: "Dense / Layered",
    hint: "Плотный полюс: стена слоёв, всё пространство заполнено.",
    positive: {
      shared: [
        "dense layered arrangement.",
        "dense, thick, layered production.",
        "a wall of sound with many simultaneous layers.",
        "a packed busy mix, every space filled."
      ]
    },
    negative: {
      shared: [
        "sparse minimal arrangement.",
        "skeletal stripped-back groove."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "density/busy",
    axis: "density",
    label: "Busy percussion",
    hint: "Событийная плотность: ударные события повсюду, гиперактивный рисунок.",
    positive: {
      shared: [
        "busy detailed percussion.",
        "busy, eventful, densely programmed drums.",
        "constant rhythmic activity, hits everywhere.",
        "a hyperactive pattern packed with events."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "complexity/intricate",
    axis: "complexity",
    label: "Intricate",
    hint: "Изощрённый программинг: детали, которые раскрываются при близком слушании.",
    positive: {
      shared: [
        "intricate detailed programming.",
        "intricate, micro-edited, finely detailed production.",
        "tiny details reward close listening.",
        "elaborate programmed patterns full of subtle edits."
      ]
    },
    negative: {
      shared: [
        "a plain simple repetitive loop.",
        "a primitive straightforward beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "complexity/simple",
    axis: "complexity",
    label: "Simple loop",
    hint: "Простой полюс: один сырой луп, намеренно без украшений.",
    positive: {
      shared: [
        "a simple repetitive loop.",
        "simple, raw, primitive loop structure.",
        "one plain pattern repeats with little variation.",
        "a straightforward unadorned beat, intentionally basic."
      ]
    },
    negative: {
      shared: [
        "intricate micro-detailed programming.",
        "an elaborate ornate arrangement."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "complexity/micro-edited",
    axis: "complexity",
    label: "Micro-edited",
    hint: "Хирургический микромонтаж: барабаны нарезаны на крошечные точные фрагменты.",
    positive: {
      shared: [
        "micro-edited drum details.",
        "micro edits, tiny cuts, precise slicing.",
        "drums are chopped into tiny precise fragments.",
        "surgical micro-editing all over the groove."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/melancholic",
    axis: "mood",
    label: "Melancholic",
    hint: "Меланхолия: тоска, задумчивость, горько-сладкие аккорды.",
    positive: {
      shared: [
        "melancholic mood.",
        "melancholic, wistful, longing.",
        "a sad reflective mood hangs over the track.",
        "bittersweet melancholy in the chords and tone."
      ]
    },
    negative: {
      shared: [
        "euphoric uplifting joyful mood.",
        "bright cheerful party energy."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/euphoric",
    axis: "mood",
    label: "Euphoric",
    hint: "Эйфория: руки вверх, сияющая кульминация.",
    positive: {
      shared: [
        "euphoric mood.",
        "euphoric, uplifting, blissful.",
        "hands-in-the-air euphoric energy.",
        "a radiant joyful climax feeling."
      ]
    },
    negative: {
      shared: [
        "dark brooding menacing mood.",
        "sad melancholic atmosphere."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/eerie",
    axis: "mood",
    label: "Eerie",
    hint: "Жуть: призрачная, тревожащая атмосфера.",
    positive: {
      shared: [
        "eerie mood.",
        "eerie, haunting, unsettling.",
        "a ghostly haunted atmosphere creeps in.",
        "sinister tones make the skin crawl."
      ]
    },
    negative: {
      shared: [
        "warm friendly cheerful mood.",
        "a bright sunny playful track."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/playful",
    axis: "mood",
    label: "Playful",
    hint: "Игривость: лёгкий, дерзкий, с хитрецой характер.",
    positive: {
      shared: [
        "playful mood.",
        "playful, cheeky, mischievous.",
        "a fun quirky attitude runs through the track.",
        "a lighthearted bouncy character, tongue in cheek."
      ]
    },
    negative: {
      shared: [
        "a grim serious heavy mood.",
        "a dark menacing atmosphere."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/late-night",
    axis: "mood",
    label: "Late-night",
    hint: "Поздняя ночь: дымно, интимно, чувственно.",
    positive: {
      shared: [
        "late-night mood.",
        "sensual, smoky, after-midnight feel.",
        "a dim intimate late-night atmosphere.",
        "slow seductive energy for the small hours."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "energy/driving",
    axis: "energy",
    label: "Driving",
    hint: "Драйв: непрерывный толчок вперёд, момент не отпускает.",
    positive: {
      shared: [
        "driving relentless energy.",
        "driving, propulsive, forward push.",
        "a relentless forward-driving groove.",
        "constant momentum pushing the floor."
      ]
    },
    negative: {
      shared: [
        "a laid-back unhurried easy pace.",
        "gentle floating calm."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "energy/restrained",
    axis: "energy",
    label: "Restrained",
    hint: "Сдержанность: сила под поверхностью, тихая контролируемая интенсивность.",
    positive: {
      shared: [
        "restrained energy.",
        "restrained, subdued, simmering.",
        "held-back power under the surface.",
        "quiet controlled intensity, understated drive."
      ]
    },
    negative: {
      shared: [
        "explosive full-throttle intensity.",
        "loud maximal peak energy."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "tension/uneasy",
    axis: "tension",
    label: "Uneasy",
    hint: "Тревога: ползучее беспокойство, задержанное дыхание.",
    positive: {
      shared: [
        "uneasy tension.",
        "tense, nervous, apprehensive.",
        "a creeping unease runs underneath.",
        "suspenseful pressure, a held breath."
      ]
    },
    negative: {
      shared: [
        "relaxed calm resolved ease.",
        "a carefree easy-going groove."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "abstract/deconstructed",
    axis: "abstract",
    label: "Deconstructed",
    hint: "Деконструкция: клубные элементы разобраны и собраны заново.",
    positive: {
      shared: [
        "deconstructed club.",
        "deconstructed, fragmented club music.",
        "club elements torn apart and reassembled.",
        "post-club rhythm sculpture, broken forms."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "abstract/concrete",
    axis: "abstract",
    label: "Concrete collage",
    hint: "Конкретная музыка: коллаж из полевых записей и найденных звуков.",
    positive: {
      shared: [
        "musique concrete collage.",
        "sound collage, found sounds, tape experiments.",
        "an abstract collage of field recordings and noises.",
        "concrete sounds arranged into abstract music."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "function/dj-tool",
    axis: "function",
    label: "DJ tool",
    hint: "Инструмент для сведения: функциональный луп без песенной формы.",
    positive: {
      shared: [
        "dj tool.",
        "dj tool, loop, transition material.",
        "a functional stripped loop made for mixing.",
        "minimal percussion tool for blending between tracks."
      ]
    },
    negative: {
      shared: [
        "a full song with verses and hooks.",
        "a cinematic listening piece."
      ]
    },
    negativeWeight: 0.5
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
export type ModelAdvice =
  | { kind: "single"; model: TextPromptModel }
  | { kind: "conflict"; models: TextPromptModel[] }
  | { kind: "unmeasured" };

/**
 * What the measurements say about the model for a selection, or why they say
 * nothing.
 *
 * The two silent cases are different and used to look identical. "conflict"
 * means the selected axes were each measured, and measured onto opposite
 * models, so no single answer exists and mixing them was measured and
 * rejected. "unmeasured" means no selected label has a reference behind it at
 * all, which covers a third of the vocabulary and every pair drawn from it.
 */
export function modelAdvice(keys: string[]): ModelAdvice {
  const models = new Set<TextPromptModel>();
  for (const key of keys) {
    const model = modelForPreset(key);
    if (model) models.add(model);
  }
  if (models.size === 1) return { kind: "single", model: [...models][0] };
  if (models.size > 1) return { kind: "conflict", models: [...models].sort() };
  return { kind: "unmeasured" };
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
