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
   * Overrides the axis model for this one label. Empty across the vocabulary
   * today: which model ranks a label best is decided by running both against
   * the same bank and recording the verdicts, not by declaring it here.
   */
  model?: TextPromptModel;
};

/**
 * A divider in the picker. Purely presentational: a category never reaches the
 * bank, the request or the score.
 */
export type TextPromptCategory = {
  key: string;
  label: string;
};

export type TextPromptAxis = {
  key: string;
  label: string;
  hint: string;
  /** Which picker block this axis is drawn under. */
  category: string;
  /**
   * Model measured to rank this axis best. Absent across the vocabulary today:
   * the two models are compared by running both on the same bank and recording
   * which one the listener kept, and that measurement fills this field. Rank
   * fusion was measured and rejected, so a search never mixes the two.
   */
  model?: TextPromptModel;
};

export const textPromptCategories: TextPromptCategory[] = [
  { key: "rhythm-motion", label: "Rhythm & Motion" },
  { key: "musical-elements", label: "Musical Elements" },
  { key: "sound-character", label: "Sound Character" },
  { key: "style-context", label: "Style & Context" }
];

/**
 * Ordered the way a track gets described: how it moves, what makes the sound,
 * how that sound is coloured and placed, and what the track is for. The picker
 * renders this order under the category dividers.
 */
export const textPromptAxes: TextPromptAxis[] = [
  { key: "rhythm", label: "Rhythm", category: "rhythm-motion", hint: "Рисунок бита: что делают барабаны и куда попадают удары. Про рисунок, а не про кач — кач на оси Groove." },
  { key: "groove", label: "Groove", category: "rhythm-motion", hint: "Кач и микротайминг: свинг, шафл, жёсткая сетка или расхлябанность. Про то, как смещены доли, а не какой рисунок." },
  { key: "percussion", label: "Percussion", category: "rhythm-motion", hint: "Характер перкуссии: чем ударили и как это звучит. Про тембр и поведение ударных, а не про их рисунок." },
  { key: "bass", label: "Bass", category: "musical-elements", hint: "Характер низа: чем сделан бас и как он движется." },
  { key: "synths", label: "Synths", category: "musical-elements", hint: "Характер синтезаторов и движение внутри синтезаторного звука: пэды, стабы, арпеджио, свипы." },
  { key: "instruments", label: "Instruments", category: "musical-elements", hint: "Конкретные инструменты, которые слышно в треке: и сыгранные вживую, и сэмпл внутри электроники." },
  { key: "voice", label: "Vocals", category: "musical-elements", hint: "Присутствие и характер голоса: ведущий вокал, речь, нарезки, хор, инструментал." },
  { key: "timbre", label: "Timbre", category: "sound-character", hint: "Окраска тона: тёплый, стеклянный, полый, металлический. Про сам тон, а не про обработку — обработка на оси Texture." },
  { key: "texture", label: "Texture", category: "sound-character", hint: "Обработка поверхности и происхождение материала: лента, сатурация, глитч, акустика или синтетика." },
  { key: "space", label: "Space", category: "sound-character", hint: "Пространство вокруг звука: сухо, комната, пещера, дилей. Стерео-ширины здесь нет — звук сводится в моно." },
  { key: "field-fx", label: "Field & FX", category: "sound-character", hint: "Немузыкальные звуки внутри трека: дождь, толпа, сирена, радио, шорох винила." },
  { key: "mood", label: "Mood", category: "style-context", hint: "Настроение: мрак, эйфория, меланхолия, жуть, гипноз. Про чувство, а не про напор — напор на оси Energy." },
  { key: "energy", label: "Energy", category: "style-context", hint: "Уровень напора: тихо, мягко, громко, с толчком вперёд. Про громкость и напор, а не про настроение." },
  { key: "abstract", label: "Abstract", category: "style-context", hint: "Функциональность против абстракции: от прямого танцевального инструмента до коллажа из полевых записей." },
  { key: "function", label: "DJ Function", category: "style-context", hint: "Роль в сете, слышимая через сам звук: разогрев, пик, инструмент для сведения, интерлюдия." },
  { key: "style", label: "Genres", category: "style-context", hint: "Жанры и сцены — грубый слой поверх тонких осей. Банки собраны из имён жанров и соседних сцен." }
];

export const textPromptPresets: TextPromptPreset[] = [
  {
    key: "rhythm/four-on-the-floor",
    axis: "rhythm",
    label: "Four-on-the-floor",
    hint: "Кик на каждую долю: ровный танцевальный пульс без пропусков. Про рисунок барабанов, а не про жанр — жанр на оси Genres.",
    positive: {
      shared: [
        "four on the floor.",
        "four on the floor, straight kick, steady dance beat.",
        "A bass drum lands on every beat with hi-hats filling the gaps.",
        "An even kick pulse marks each beat while an open hat lifts between them."
      ],
      mulan: [
        "four on the floor.",
        "four on the floor, straight kick, four four beat.",
        "four on the floor, house beat, techno beat, disco beat.",
        "A four-on-the-floor track."
      ]
    },
    negative: {
      shared: [
        "breakbeat, broken beat, chopped drum breaks.",
        "syncopated drums landing off the grid.",
        "halftime drums with one snare late in the bar."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/breakbeat",
    axis: "rhythm",
    label: "Breakbeat",
    hint: "Ломаные драмы: рубленые брейки, кик и снейр мимо сетки, шаг спотыкается. Про рисунок барабанов — сцену breaks ищи на оси Genres.",
    positive: {
      shared: [
        "breakbeat.",
        "breakbeat, broken drums, chopped drum breaks.",
        "The kick and snare tumble between the beats instead of marking them.",
        "A funk drum loop cut apart, its snare cracking between the kicks."
      ],
      mulan: [
        "breakbeat.",
        "breaks, breakbeat, big beat.",
        "breakbeat, nu skool breaks, jungle, drum and bass.",
        "A breakbeat track."
      ]
    },
    negative: {
      shared: [
        "four on the floor, house, techno.",
        "a steady kick drum on every beat.",
        "even drum timing locked to the pulse."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/amen-break",
    axis: "rhythm",
    label: "Amen break",
    hint: "Нарезанный amen: стремительные сбивки малого, ghost-ноты, звонкий райд и живая установка, снятая с винила.",
    positive: {
      shared: [
        "amen break.",
        "amen break, chopped drum break, sampled drum loop.",
        "Fast snare rolls and ghost notes cut from a sampled drum kit.",
        "A ringing ride and a tight snare rearranged into rapid fills."
      ],
      clap: [
        "amen break.",
        "The sound of a sampled drum kit chopped into fast snare rolls and ghost notes.",
        "A recording of a vinyl drum break with a bright ride cymbal and a cracking snare.",
        "The sound of rapid snare fills and tumbling toms cut from an old drum record."
      ],
      mulan: [
        "amen break.",
        "amen break, jungle, hardcore breaks.",
        "amen break, jungle, ragga jungle, drum and bass, breakcore.",
        "An amen break track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "rhythm/broken-rhythm",
    axis: "rhythm",
    label: "Broken rhythm",
    hint: "Барабаны спотыкаются: кик уходит с сильной доли, снейр отвечает поздно, такт качается набок. Сцену broken beat ищи на оси Genres.",
    positive: {
      shared: [
        "broken rhythm.",
        "broken rhythm, broken beat, stumbling drums.",
        "The kick slips off the downbeat and the snare answers a beat late.",
        "Drums lurch and trip through the bar in a lopsided pattern."
      ],
      mulan: [
        "broken rhythm.",
        "broken beat, bruk, broken techno.",
        "broken beat, bruk, jazzy club drums, tumbling percussion.",
        "A track built on tumbling, off-kilter drums."
      ]
    },
    negative: {
      shared: [
        "four on the floor, straight kick on every beat.",
        "even machine drums locked to a regular pulse."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/two-step",
    axis: "rhythm",
    label: "Two-step",
    hint: "Гаражный скок: кик пропускает доли, снейр щёлкает на 2 и 4, между ударами дырки. Про барабаны — сцену UK garage ищи на оси Genres.",
    positive: {
      shared: [
        "two step.",
        "two step, skipping drums, clipped kick and snare.",
        "The kick skips beats while the snare cracks on two and four.",
        "A springy drum pattern that hops over the beats and leaves air between hits."
      ],
      mulan: [
        "two step.",
        "two step, uk garage, skippy garage drums.",
        "two step, uk garage, speed garage, future garage.",
        "A two-step garage track."
      ]
    },
    negative: {
      shared: [
        "four on the floor, a kick drum on every beat.",
        "even, marching drums with a filled-in pulse."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/halftime",
    axis: "rhythm",
    label: "Halftime",
    hint: "Снейр съезжает на третью долю, кик редкий, хэты быстрые — бит ощущается вдвое медленнее музыки. Сцена halftime — на оси Genres.",
    positive: {
      shared: [
        "halftime.",
        "halftime, half time drums, sparse backbeat.",
        "The snare waits and lands once on the third beat of the bar.",
        "Fast hi-hats skitter over a sparse kick and a heavy, slow-feeling backbeat."
      ],
      mulan: [
        "halftime.",
        "halftime, half time drums, heavy backbeat.",
        "halftime, sparse kick, snare on the third beat, fast hi-hats.",
        "A halftime drum pattern."
      ]
    },
    negative: {
      shared: [
        "double time drums with a snare on every other beat.",
        "a fast rolling breakbeat with busy snares."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/double-time",
    axis: "rhythm",
    label: "Double-time",
    hint: "Барабаны удваиваются: снейр и хэты сыплются вдвое чаще пульса, сбивки катятся без передышки.",
    positive: {
      shared: [
        "double time.",
        "double time, doubled drums, busy snare pattern.",
        "The snare and hi-hats fill in twice inside every beat.",
        "Hi-hats and snares rattle at twice the rate of the underlying pulse."
      ]
    },
    negative: {
      shared: [
        "halftime drums with a sparse kick and a heavy backbeat.",
        "a slow, heavy beat with long gaps between the hits."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/boom-bap",
    axis: "rhythm",
    label: "Boom bap",
    hint: "Пыльный бит: тяжёлый кик, трескучий снейр на 2 и 4, шорох винила под каждым ударом.",
    positive: {
      shared: [
        "boom bap.",
        "boom bap, dusty kick and snare, sampled drum loop.",
        "A heavy kick and a cracking snare trade on two and four.",
        "Loose sampled drums with vinyl noise under every hit."
      ],
      clap: [
        "boom bap.",
        "The sound of a dusty kick drum and a cracking snare over vinyl noise.",
        "A recording of a sampled drum kit with a thick low kick and a snappy rimshot snare.",
        "The sound of a dusty drum loop lifted from a crackling record."
      ],
      mulan: [
        "boom bap.",
        "boom bap, hip hop, golden era hip hop.",
        "boom bap, hip hop, trip hop, downtempo, instrumental hip hop.",
        "A boom bap track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "rhythm/gallop",
    axis: "rhythm",
    label: "Gallop",
    hint: "Галоп в барабанах: две быстрые ноты и длинная, фигура повторяется каждую долю и толкает бит вперёд.",
    positive: {
      shared: [
        "galloping drums.",
        "galloping drums, cantering kick pattern, short short long drum figure.",
        "Two quick hits and a longer one repeat through the bar, driving forward.",
        "A repeated cantering figure in the kick pushes each beat into the next."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "rhythm/syncopated",
    axis: "rhythm",
    label: "Syncopated",
    hint: "Акценты падают между долями и тянут против пульса. Про то, куда попадают удары; микротайминг и кач — на оси Groove.",
    positive: {
      shared: [
        "syncopated.",
        "syncopated drums, accents between the beats, off-beat hits.",
        "The accents fall between the beats and pull against the pulse.",
        "Kick and percussion push into the gaps, landing just off the count."
      ]
    },
    negative: {
      shared: [
        "every hit landing squarely on the beat.",
        "a plain drum pattern marching with the pulse."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/triplet-rhythm",
    axis: "rhythm",
    label: "Triplet rhythm",
    hint: "Доля делится на три: барабаны катятся тройками, хэты и томы сыплются по три. Про деление доли, а не про кач — свинг и шафл на оси Groove.",
    positive: {
      shared: [
        "triplet rhythm.",
        "triplet rhythm, three against the beat, rolling triplets.",
        "Every beat splits into three and the drums roll in threes.",
        "Hi-hats and toms tumble in groups of three across the bar."
      ]
    },
    negative: {
      shared: [
        "drums split into two and four even sixteenths.",
        "a plain duple pattern with hits on the straight subdivisions."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/polyrhythm",
    axis: "rhythm",
    label: "Polyrhythm",
    hint: "Несколько рисунков разной длины крутятся одновременно и расходятся: слоистая ручная перкуссия, кроссритм.",
    positive: {
      shared: [
        "polyrhythm.",
        "polyrhythm, cross rhythm, interlocking percussion.",
        "Two drum patterns of different lengths cycle against each other.",
        "Layered hand drums and shakers weave figures that keep sliding apart."
      ],
      clap: [
        "polyrhythm.",
        "The sound of congas, bongos and shakers playing interlocking patterns at once.",
        "A recording of several hand drums cycling against each other in different lengths.",
        "The sound of layered wooden percussion crossing over a steady low drum."
      ],
      mulan: [
        "polyrhythm.",
        "polyrhythm, cross rhythm, tribal percussion.",
        "polyrhythm, congas, bongos, djembe, shakers, interlocking hand drums.",
        "A polyrhythmic percussion track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "rhythm/ametric",
    axis: "rhythm",
    label: "Ametric / free time",
    hint: "Пульса нет: удары приходят вразнобой и растворяются, музыка дышит в своём времени.",
    positive: {
      shared: [
        "free time.",
        "free time, ametric, rubato drift.",
        "Sounds enter and decay wherever they please, drifting at their own speed.",
        "The music breathes in its own time and the hits fall where they land."
      ],
      clap: [
        "free time.",
        "The sound of cymbals, gongs and mallets ringing at irregular intervals.",
        "A recording of loose percussion drifting freely, each hit arriving whenever it comes.",
        "The sound of struck metal and skin decaying into silence at random moments."
      ]
    },
    negative: {
      shared: [
        "a steady four on the floor pulse.",
        "drums locked to a regular metronomic beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/tresillo",
    axis: "rhythm",
    label: "Tresillo",
    hint: "Кик ложится схемой 3-3-2: акценты на 1, 4 и 7 из восьми, рисунок косит поперёк такта. Основа клаве и латинских грувов.",
    positive: {
      shared: [
        "tresillo.",
        "tresillo, three three two pattern, clave figure.",
        "The kick falls in a three three two figure that cuts across the bar.",
        "A lopsided eight-count where the accents land on one, four and seven."
      ]
    },
    negative: {
      shared: [
        "four on the floor, a kick evenly spaced on every beat.",
        "drums marking each beat with the same weight."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "rhythm/dembow",
    axis: "rhythm",
    label: "Dembow",
    hint: "Дембоу: короткая петля «бум-ч-бум-чик» — кик на долю, снейр со сдвигом, и так по кругу. Сцены reggaeton и dancehall — на оси Genres.",
    positive: {
      shared: [
        "dembow.",
        "dembow, boom ch boom chick, looping kick and rimshot.",
        "A kick on the beat answered by a snare on the offbeat, over and over.",
        "A short drum loop where the rimshot leans between the kick drum hits."
      ],
      mulan: [
        "dembow.",
        "dembow, reggaeton, dancehall.",
        "dembow, reggaeton, moombahton, dancehall, latin club.",
        "A dembow rhythm track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "rhythm/odd-meter",
    axis: "rhythm",
    label: "Odd meter",
    hint: "Такт кончается не там, где ждёшь: счёт на пять или семь, петля каждый круг сдвигается.",
    positive: {
      shared: [
        "odd meter.",
        "odd meter, odd time signature, uneven bar length.",
        "The bar turns over after five or seven counts and starts again.",
        "The loop lands a beat early each time and the count keeps shifting."
      ],
      mulan: [
        "odd meter.",
        "odd meter, odd time signature, polymeter.",
        "odd meter, five four time, seven eight time, shifting bar length.",
        "An odd meter track."
      ]
    },
    negative: {
      shared: [
        "a plain four four bar repeating evenly.",
        "drums cycling in even eight beat loops."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/unswung",
    axis: "groove",
    label: "Unswung",
    hint: "Доли делятся ровно пополам: удар точно в центре клетки, хэты идут одинаковыми парами. Про микротайминг, а не про рисунок — он на оси Rhythm.",
    positive: {
      shared: [
        "straight timing.",
        "straight timing, even eighths, drums on the exact beat.",
        "Every hit sits dead centre on its subdivision, evenly spaced across the bar.",
        "The hi-hats divide each beat into two halves of identical length."
      ]
    },
    negative: {
      shared: [
        "a swung groove with a shuffled hi-hat lilt.",
        "triplet feel dragging every second hit late."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/tight",
    axis: "groove",
    label: "Tight",
    hint: "Всё сидит собранно: удары ложатся впритык к пульсу и друг к другу, разброса почти нет. Про точность попадания, а не про звук барабанов.",
    positive: {
      shared: [
        "tight timing.",
        "tight timing, locked drums, crisp unison hits.",
        "Kick, snare and hats sit flush against the pulse with hairline accuracy.",
        "The whole kit speaks as one, each stroke clipped and squarely placed."
      ]
    },
    negative: {
      shared: [
        "loose sloppy drum timing wandering around the beat.",
        "hits scattered early and late around the pulse."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/quantized",
    axis: "groove",
    label: "Quantized",
    hint: "Машинная сетка: каждый удар защёлкнут в клетку и повторяется точь-в-точь такт за тактом.",
    positive: {
      shared: [
        "quantized.",
        "quantized, grid locked, machine exact drums.",
        "Programmed drums snapped to the grid with identical spacing every bar.",
        "The same hit returns at the same instant bar after bar, machine perfect."
      ]
    },
    negative: {
      shared: [
        "hand played drums with human timing drift.",
        "a humanized groove with hits nudged around the grid."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/loose",
    axis: "groove",
    label: "Loose",
    hint: "Расхлябанный тайминг: удары гуляют то раньше, то позже, грув слегка шатает и заваливается.",
    positive: {
      shared: [
        "loose timing.",
        "loose timing, sloppy drums, wandering placement.",
        "Hits scatter early and late around the beat rather than settling on it.",
        "The groove wobbles, with the snare arriving a hair off each time."
      ]
    },
    negative: {
      shared: [
        "machine exact drums snapped to the grid.",
        "tight programmed timing with identical spacing."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/humanized",
    axis: "groove",
    label: "Humanized",
    hint: "Живая рука: удары чуть плавают по времени и силе, ghost-ноты каждый раз другие. Про исполнение, а не про то, чем сыграно.",
    positive: {
      shared: [
        "humanized.",
        "humanized, hand played feel, shifting velocities.",
        "Each hit lands a touch differently, with velocity and placement breathing.",
        "Small imperfections in the playing keep every bar slightly unlike the last."
      ]
    },
    negative: {
      shared: [
        "machine exact drums locked rigidly to the grid.",
        "an identical programmed loop repeating unchanged."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/laid-back",
    axis: "groove",
    label: "Laid-back",
    hint: "Грув тянется позади сетки: снейр приходит чуть позже, бит звучит лениво и расслабленно.",
    positive: {
      shared: [
        "laid back.",
        "laid back, behind the beat, dragging groove.",
        "The snare arrives a fraction late and the groove leans backwards.",
        "Drums drag lazily behind the pulse, unhurried and relaxed."
      ]
    },
    negative: {
      shared: [
        "drums rushing ahead of the pulse, urgent and eager.",
        "a groove leaning forward on top of the beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/pushing",
    axis: "groove",
    label: "Pushing",
    hint: "Грув толкает вперёд: удары приходят чуть раньше сетки, всё будто торопится.",
    positive: {
      shared: [
        "pushing.",
        "pushing, ahead of the beat, driving forward.",
        "The snare arrives a fraction early and the groove leans forward.",
        "Drums press on top of the pulse, urgent and eager to move."
      ]
    },
    negative: {
      shared: [
        "a laid back groove dragging behind the beat.",
        "drums arriving late and leaning backwards."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/swing",
    axis: "groove",
    label: "Swing",
    hint: "Каждый второй удар приходит позже: доля делится неровно, хэты идут длинно-короткими парами. Про кач, а не про рисунок — он на оси Rhythm.",
    positive: {
      shared: [
        "swung groove.",
        "swung groove, swing timing, uneven eighths.",
        "Every second hit lands late, giving the beat a long-short lilt.",
        "The hi-hats lope along in lopsided pairs on each beat."
      ]
    },
    negative: {
      shared: [
        "straight timing with evenly divided eighths.",
        "machine exact drums on the dead centre of the grid."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/shuffle",
    axis: "groove",
    label: "Shuffle",
    hint: "Хэты катятся тройками, грув пружинит и подпрыгивает между долями. Про кач и смещение долей, а не про рисунок — рисунок на оси Rhythm.",
    positive: {
      shared: [
        "shuffle groove.",
        "shuffle groove, shuffled hi-hats, bouncing lopsided drums.",
        "The hi-hats roll in threes and the groove bounces from beat to beat.",
        "A springy drum feel where every beat divides unevenly and rolls onward."
      ],
      clap: [
        "shuffle groove.",
        "The sound of a drum kit playing a shuffled beat with rolling hi-hats.",
        "A recording of hi-hats and a snare bouncing in an uneven, springy pattern.",
        "The sound of drums lilting in threes with a loose, rolling bounce."
      ]
    },
    negative: {
      shared: [
        "straight timing with hits evenly spaced on the grid.",
        "stiff machine drums marching squarely on the beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "groove/rolling",
    axis: "groove",
    label: "Rolling",
    hint: "Грув катится без остановки: шестнадцатые текут сплошным потоком, такт перетекает в такт.",
    positive: {
      shared: [
        "rolling groove.",
        "rolling groove, continuous sixteenths, flowing drums.",
        "The hats and percussion run in a continuous stream that keeps flowing.",
        "One bar spills into the next with a smooth, tumbling forward motion."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "groove/pumping",
    axis: "groove",
    label: "Pumping",
    hint: "Всё «дышит» в такт: на кике звук проседает и тут же поднимается обратно между ударами.",
    positive: {
      shared: [
        "pumping groove.",
        "pumping groove, ducking under the kick, breathing pads.",
        "Everything dips when the kick lands and swells back up between hits.",
        "The whole mix breathes in time with the beat, rising and falling."
      ],
      clap: [
        "pumping groove.",
        "The sound of a synth pad ducking sharply under every kick drum hit.",
        "A recording where the bass and chords dip and swell in time with the drums.",
        "The sound of a mix breathing, pressed down on each beat and released."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "percussion/live-drums",
    axis: "percussion",
    label: "Live drums",
    hint: "Живые барабаны: человек за установкой, дыхание тарелок, плавающая динамика ударов, комнатное эхо.",
    positive: {
      shared: [
        "live drums.",
        "acoustic drum kit played by a drummer, snare buzz and kick beater thud.",
        "strokes drifting slightly early and late, ghost notes and ride wash breathing.",
        "sticks on a real kit in a room, cymbals decaying into the walls."
      ],
      clap: [
        "live drums.",
        "A recording of an acoustic drum kit, sticks striking coated snare heads.",
        "The sound of a snare rattling its wires while a kick drum beater thumps skin.",
        "A room recording of ride and hi-hat cymbals ringing and decaying naturally."
      ],
      mulan: [
        "live drums.",
        "acoustic drums, live band, drum kit, session drummer.",
        "jazz drums, funk breaks, soul rhythm section, organic groove.",
        "a human drummer playing with loose feel and shifting dynamics."
      ]
    },
    negative: {
      shared: [
        "programmed drum machine locked to a rigid quantized grid.",
        "sampled one-shots triggered identically every bar.",
        "dry electronic drums cut short in a dead studio space.",
        "sequenced pattern with fixed velocity on every hit."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/808-drums",
    axis: "percussion",
    label: "808 drums",
    hint: "Звук Roland TR-808: длинный гудящий кик-тон, сухой клэп, короткие металлические хэты, ковбелл.",
    positive: {
      shared: [
        "808 drums.",
        "long booming kick tone that sinks in pitch and rings on under the beat.",
        "thin dry clap, short cowbell ping and sizzling metallic closed hats.",
        "analogue drum machine voices, every drum a tuned electronic circuit."
      ],
      clap: [
        "808 drums.",
        "The sound of a drum machine kick as a low sine tone decaying slowly.",
        "A recording of a synthetic handclap, a cowbell strike and thin metallic hi-hats.",
        "The sound of tuned analogue percussion circuits, synthetic and electronic throughout."
      ],
      mulan: [
        "808 drums.",
        "roland tr-808, drum machine, analog drums, boom bap, trap.",
        "electro, hip hop, miami bass, classic house machine percussion.",
        "a track built on booming 808 kick tones and dry machine claps."
      ]
    },
    negative: {
      shared: [
        "acoustic kit recorded with microphones in a live room.",
        "hand drums and shakers played by a percussionist.",
        "sampled breakbeat chopped from a soul record.",
        "909 drum machine with its snappy noise snare."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/909-drums",
    axis: "percussion",
    label: "909 drums",
    hint: "Звук Roland TR-909: щёлкающий сухой кик, шумовой снейр, звенящие открытые хэты и райд.",
    positive: {
      shared: [
        "909 drums.",
        "snappy punchy kick with a sharp attack transient and a short tight decay.",
        "noise-based snare hiss, ringing open hats and a bright metallic ride.",
        "classic house and techno machine kit, dry snappy and mechanical."
      ],
      clap: [
        "909 drums.",
        "The sound of a drum machine kick with a sharp click at its attack.",
        "A recording of a white noise snare burst and long hissing open hi-hats.",
        "The sound of bright metallic machine cymbals hissing open across the bar."
      ],
      mulan: [
        "909 drums.",
        "roland tr-909, drum machine, techno drums, house drums.",
        "acid house, hard techno, rave percussion, classic club kit.",
        "a track driven by punchy 909 kicks and hissing open hats."
      ]
    },
    negative: {
      shared: [
        "808 drums with long booming sub kick tones.",
        "acoustic kit played by a drummer in a room.",
        "hand drums, congas and shakers.",
        "sampled funk breakbeat with vinyl noise."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/hand-percussion",
    axis: "percussion",
    label: "Hand percussion",
    hint: "Барабаны, по которым бьют ладонями: конги, бонго, джембе, дарбука. Кожа, пальцы, открытые и глухие удары.",
    positive: {
      shared: [
        "hand percussion.",
        "palms and fingertips slapping stretched skin on congas and bongos.",
        "open ringing tones alternating with muted slaps and low bass strokes.",
        "djembe, darbuka and tambourine played by hand, warm and skin-toned."
      ],
      clap: [
        "hand percussion.",
        "The sound of bare hands striking conga and bongo drum heads.",
        "A recording of fingers slapping taut skin, open tones ringing between muted slaps.",
        "The sound of a djembe and a darbuka struck by palms, with jingling tambourine."
      ],
      mulan: [
        "hand percussion.",
        "congas, bongos, djembe, darbuka, tambourine.",
        "latin percussion, afro cuban, world percussion, acoustic groove.",
        "a groove carried by hand-played skin drums and small percussion."
      ]
    },
    negative: {
      shared: [
        "drum machine kick and snare on a quantized grid.",
        "sticks on a snare drum and cymbals.",
        "synthetic electronic percussion voices.",
        "sampled machine hi-hats and claps."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/tribal-percussion",
    axis: "percussion",
    label: "Tribal percussion",
    hint: "Плотный слой этнических барабанов: несколько шкур в перекличке, низкие тамы и полиритмия поверх бита.",
    positive: {
      shared: [
        "tribal percussion.",
        "layered skin drums answering each other in dense interlocking polyrhythm.",
        "deep toms, talking drums and hollow log drums rolling low under the groove.",
        "a ritual drum ensemble, rows of drums pounding together in one dense mass."
      ],
      clap: [
        "tribal percussion.",
        "The sound of many skin drums struck together in a large ensemble.",
        "A recording of deep toms and hollow log drums booming in overlapping waves.",
        "The sound of a drum circle, layered hides and hollow wood answering each other."
      ],
      mulan: [
        "tribal percussion.",
        "tribal drums, ethnic percussion, afro house, world drums.",
        "shamanic, ritual, polyrhythmic, organic house percussion.",
        "a dense ensemble of ethnic skin drums layered across the groove."
      ]
    },
    negative: {
      shared: [
        "single dry drum machine loop with sparse hits.",
        "clean electronic kit with synthetic voices.",
        "acoustic jazz kit with sticks and ride cymbal.",
        "minimal clicks and tiny digital blips."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/wooden",
    axis: "percussion",
    label: "Wooden",
    hint: "Деревянный тембр ударных: вудблок, клавес, римшот по ободу, глухие томы, гуиро. Сухое дерево, короткий отзвук.",
    positive: {
      shared: [
        "wooden.",
        "woodblock and claves knocking, dry hardwood struck with a short hollow ring.",
        "rimshots on the stick side of the snare, hollow toms and temple blocks.",
        "guiro scrapes and hollow shell knocks, a dark dry timbre of struck hardwood."
      ],
      clap: [
        "wooden.",
        "The sound of a woodblock and claves being struck, dry and hollow.",
        "A recording of a rimshot on a drum rim, wood on wood with short resonance.",
        "The sound of hollow wooden toms and temple blocks knocking in a musical groove."
      ],
      mulan: [
        "wooden.",
        "woodblock, claves, rimshot, temple blocks, guiro.",
        "minimal percussion, organic house, dub techno percussion, dry acoustic groove.",
        "a groove built on knocking hardwood percussion and hollow rim hits."
      ]
    },
    negative: {
      shared: [
        "bright metallic cymbals and ringing bells.",
        "glassy chimes and shimmering metal percussion.",
        "steel drum and gong resonance.",
        "sizzling metal hi-hats dominating the top end."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/clicky",
    axis: "percussion",
    label: "Clicky",
    hint: "Верх из коротких щелчков: сухие транзиенты, тик и цок почти без хвоста, ближе к пластику, чем к металлу.",
    positive: {
      shared: [
        "clicky.",
        "sharp dry transients that vanish on contact, ticking and snapping in the top end.",
        "hard plastic taps and stick tips on the rim, each hit gone the instant it lands.",
        "granular digital blips and edge tones cutting cleanly through the mix."
      ],
      clap: [
        "clicky.",
        "The sound of short dry clicks and ticks that stop dead on impact.",
        "A recording of hard plastic tapping and snapping, each hit ending instantly.",
        "The sound of sharp transient blips and edge tones over a beat."
      ],
      mulan: [
        "clicky.",
        "clicks, ticks, glitch percussion, minimal techno percussion.",
        "microhouse, clicks and cuts, dry digital percussion, minimal.",
        "a beat topped with short snapping clicks, each one over instantly."
      ]
    },
    negative: {
      shared: [
        "long ringing cymbal wash and sustained decay.",
        "boomy resonant drums with heavy tails.",
        "reverb-soaked percussion smearing into the mix.",
        "splashy crashes hanging over the beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/micro-percussion",
    axis: "percussion",
    label: "Micro percussion",
    hint: "Крошечные детали на заднем плане: еле слышные тики, шорохи и пылинки между основными ударами.",
    positive: {
      shared: [
        "micro percussion.",
        "tiny quiet events crowding the gaps between the main drum hits.",
        "rim ticks, muted taps and grains of noise sitting low under the groove.",
        "intricate small-grain detail, delicate and only just above the noise floor."
      ],
      clap: [
        "micro percussion.",
        "The sound of very small quiet taps and ticks between louder drum hits.",
        "A recording of faint rustles and tiny grains of percussion low in the mix.",
        "The sound of delicate hairline knocks scattered across the stereo field."
      ],
      mulan: [
        "micro percussion.",
        "microhouse, minimal techno, intricate percussion, detailed groove.",
        "glitch, idm, granular percussion, subtle background texture.",
        "a groove filled with tiny quiet percussive details under the main beat."
      ]
    },
    negative: {
      shared: [
        "loud front-and-centre drums dominating the mix.",
        "heavy crashing cymbals and big room toms.",
        "a dense wall of drums packed shoulder to shoulder.",
        "a simple sparse kit carrying only kick and snare."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/rattling-shakers",
    axis: "percussion",
    label: "Rattling shakers",
    hint: "Шейкеры, маракасы, кабаса: сыпучий шорох зёрен, непрерывное шуршание поверх грува.",
    positive: {
      shared: [
        "rattling shakers.",
        "seeds and beads hissing inside a gourd, shaken in a steady wash.",
        "maracas, cabasa and egg shaker rustling continuously over the groove.",
        "a dry granular rustle riding high above the drums, all seeds and gourd."
      ],
      clap: [
        "rattling shakers.",
        "The sound of a shaker full of seeds being rattled back and forth.",
        "A recording of maracas and a cabasa hissing with beads sliding over metal.",
        "The sound of dry grains rustling in a steady continuous rhythm."
      ],
      mulan: [
        "rattling shakers.",
        "shaker, maracas, cabasa, egg shaker, tambourine.",
        "latin percussion, afro house, organic house, acoustic groove topper.",
        "a steady rustling shaker riding above the drums."
      ]
    },
    negative: {
      shared: [
        "metallic hi-hat cymbals clipped tight and closed.",
        "ringing bells and chime percussion.",
        "hard clicking sticks with a short dead tail.",
        "white noise hats sequenced by a drum machine."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/tight-hats",
    axis: "percussion",
    label: "Tight hats",
    hint: "Закрытые хэты, зажатые почти в ноль: короткий цок без хвоста, аккуратный ровный верх.",
    positive: {
      shared: [
        "tight hats.",
        "closed hi-hat cymbals clamped shut, each stroke choked off immediately.",
        "a short crisp tick that dies on contact, clean and controlled in the top end.",
        "disciplined dry strokes, every hat gated to the same tiny length."
      ],
      clap: [
        "tight hats.",
        "The sound of closed hi-hat cymbals struck and immediately choked shut.",
        "A recording of crisp short cymbal ticks cut off the instant they sound.",
        "The sound of a hi-hat pedal held tight, producing dry clipped strokes."
      ],
      mulan: [
        "tight hats.",
        "closed hi-hats, tight hats, crisp percussion, dry top end.",
        "tech house, minimal techno, deep house, controlled groove.",
        "a clean top end of tightly closed hi-hats, dry and clipped short."
      ]
    },
    negative: {
      shared: [
        "open hi-hats ringing long between beats.",
        "splashy crash cymbals washing over everything.",
        "loose sizzling cymbals with long decay.",
        "reverb-drenched hats smearing into the next bar."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/splashy-cymbals",
    axis: "percussion",
    label: "Splashy cymbals",
    hint: "Разливающиеся тарелки: крэши и открытые хэты с длинным шипящим хвостом, заливающим верх.",
    positive: {
      shared: [
        "splashy cymbals.",
        "crash and open hi-hat cymbals spraying a long hissing wash across the top.",
        "bright metal shimmering and bleeding into the next bar before it fades.",
        "loose sizzling ride and china cymbals ringing wide and unrestrained."
      ],
      clap: [
        "splashy cymbals.",
        "The sound of a crash cymbal struck hard and ringing out in a long wash.",
        "A recording of open hi-hats sizzling and bleeding into each other.",
        "The sound of bright metal cymbals shimmering with a long noisy decay."
      ],
      mulan: [
        "splashy cymbals.",
        "crash cymbals, open hi-hats, ride cymbal, cymbal wash.",
        "breakbeat, jungle, disco drums, live cymbal-heavy groove.",
        "a top end flooded with wide splashing cymbal decay."
      ]
    },
    negative: {
      shared: [
        "tightly closed hi-hats choked to a short tick.",
        "dry clipped percussion cut short on every hit.",
        "knocking wooden percussion carrying the top end instead.",
        "a muted controlled top end kept short and clean."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/offbeat-hats",
    axis: "percussion",
    label: "Offbeat hats",
    hint: "Хэт стоит между долями, на «и», поверх ровного кика. Про место хэта, а не про ритм трека — рисунок бита на оси Rhythm.",
    positive: {
      shared: [
        "offbeat hats.",
        "hi-hats landing on the upbeats, between the kicks rather than with them.",
        "steady four-on-the-floor kick answered by a hat in every gap.",
        "kick and hat trading places, the cymbal always on the and of each beat."
      ],
      clap: [
        "offbeat hats.",
        "The sound of a hi-hat cymbal struck between each kick drum thump.",
        "A recording of a steady kick with a cymbal answering in every gap.",
        "The sound of cymbal strokes falling on the upbeats over an even pulse."
      ],
      mulan: [
        "offbeat hats.",
        "offbeat hi-hats, upbeat hats, house drums, four on the floor.",
        "house, tech house, disco, garage, classic club drum pattern.",
        "hi-hats sitting on the upbeats above a steady kick."
      ]
    },
    negative: {
      shared: [
        "hi-hats locked onto the same beat as the kick.",
        "hats running in dense unbroken sixteenths.",
        "hats sitting flat on the downbeats beside the snare.",
        "syncopated broken kick with scattered cymbals."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "percussion/stuttering",
    axis: "percussion",
    label: "Stuttering",
    hint: "Ударные заикаются: быстрые повторы одного удара, роллы и ретриггеры, будто заело на одном месте.",
    positive: {
      shared: [
        "stuttering.",
        "a single drum hit retriggered in bursts, repeating before it can decay.",
        "buzz rolls, machine-gun snare flams and glitch repeats stumbling over the beat.",
        "the groove trips and hiccups, chopped fragments looping on themselves."
      ],
      clap: [
        "stuttering.",
        "The sound of a drum hit repeating rapidly in a machine-gun burst.",
        "A recording of a snare buzz roll and glitched retriggered stutters.",
        "The sound of a short percussive fragment looping on itself and hiccupping."
      ],
      mulan: [
        "stuttering.",
        "stutter edits, glitch percussion, drum rolls, retrigger.",
        "breakcore, idm, footwork, glitch hop, chopped drums.",
        "drums that stumble and repeat themselves in rapid bursts."
      ]
    },
    negative: {
      shared: [
        "steady even drums holding one unchanged pattern.",
        "a smooth flowing groove running unbroken through the bar.",
        "sparse simple beat with wide space between hits.",
        "a metronomic kit playing straight ahead from start to finish."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/sub-bass",
    axis: "bass",
    label: "Sub bass",
    hint: "Самый низ: чистый глубокий тон, который больше чувствуешь телом, чем слышишь. Почти без гармоник и характера.",
    positive: {
      shared: [
        "sub bass.",
        "a deep pure low tone felt in the chest more than heard in the ears.",
        "clean sine weight sitting under everything, nearly a bare fundamental.",
        "the floor of the mix rumbling, subsonic and perfectly smooth."
      ],
      clap: [
        "sub bass.",
        "The sound of a very deep low frequency tone rumbling under the music.",
        "A recording of a smooth sine wave in the lowest register, felt as pressure.",
        "The sound of subsonic weight filling a room, deep and pure in tone."
      ],
      mulan: [
        "sub bass.",
        "sub bass, deep bass, low end, sine bass.",
        "dubstep, drum and bass, deep house, dub techno.",
        "a deep clean low tone anchoring the bottom of the track."
      ]
    },
    negative: {
      shared: [
        "thin bright bass sitting high in the midrange.",
        "gritty distorted low end full of harmonics.",
        "an upright double bass plucked with a woody attack.",
        "buzzing saw bass with an aggressive edge."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/dub-bass",
    axis: "bass",
    label: "Dub bass",
    hint: "Даб-бас: жирный округлый тон, длинные ноты с ленивым спадом, много пространства и эхо вокруг.",
    positive: {
      shared: [
        "dub bass.",
        "fat rounded low notes held long and left to decay into open space.",
        "soft filtered attack, warm weight sliding lazily between a few pitches.",
        "echo and spring reverb trailing off the low end, heavy and unhurried."
      ],
      clap: [
        "dub bass.",
        "The sound of a fat round bass note ringing out into echo and reverb.",
        "A recording of warm low tones decaying slowly with tape delay trails.",
        "The sound of a heavy soft bass sliding between pitches in a wide space."
      ],
      mulan: [
        "dub bass.",
        "dub bass, reggae bass, dub techno, roots.",
        "dub, dubwise, steppers, deep dub techno, echo chamber.",
        "a fat warm bass drifting through echo and long decay."
      ]
    },
    negative: {
      shared: [
        "a busy bassline running constant sixteenths.",
        "sharp aggressive distorted low end.",
        "a tight dry bass pinned close in a small dead room.",
        "bright plucked bass with hard attack."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/rolling-bass",
    axis: "bass",
    label: "Rolling bass",
    hint: "Бас катится непрерывно: череда коротких нот без пауз, ровный поток, который тянет трек вперёд.",
    positive: {
      shared: [
        "rolling bass.",
        "a continuous chain of short muted low notes tumbling forward into each other.",
        "each note cut off by the next, an unbroken low current under the drums.",
        "a round synth bass running the same figure over and over, always moving."
      ],
      mulan: [
        "rolling bass.",
        "rolling bass, rolling groove, liquid drum and bass.",
        "drum and bass, tech house, minimal, rolling techno.",
        "a continuous rolling bassline driving the track forward."
      ]
    },
    negative: {
      shared: [
        "long held bass notes with wide silence between them.",
        "sparse stabs punctuating the bar.",
        "static drone holding one unchanging pitch.",
        "a bass that falls silent for long stretches."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/walking-bass",
    axis: "bass",
    label: "Walking bass",
    hint: "Ходячий бас: контрабас шагает по нотам, по одной на долю, обводя гармонию. Джаз, свинг, соул.",
    positive: {
      shared: [
        "walking bass.",
        "an upright bass stepping one note per beat, outlining the chord changes.",
        "fingers pulling thick gut strings, woody attack and a little string buzz.",
        "stepwise motion up and down through passing tones, swinging and human."
      ],
      clap: [
        "walking bass.",
        "The sound of an upright double bass plucked one note at a time.",
        "A recording of thick strings pulled by fingers, woody and buzzing slightly.",
        "The sound of a bass stepping up and down through a chord progression."
      ],
      mulan: [
        "walking bass.",
        "double bass, upright bass, jazz bass, acoustic bass.",
        "jazz, swing, soul jazz, bebop, nu jazz.",
        "an upright bass walking one note per beat under the changes."
      ]
    },
    negative: {
      shared: [
        "synthetic electronic bass from a machine.",
        "one repeated low note held through the bar.",
        "a deep sub tone holding a single pitch under the track.",
        "distorted electric bass with heavy overdrive."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/pulsing-bass",
    axis: "bass",
    label: "Pulsing bass",
    hint: "Бас пульсирует: одна нота ритмично дышит и качается по громкости, будто её накачивают.",
    positive: {
      shared: [
        "pulsing bass.",
        "one low note breathing in and out, swelling and ducking in steady time.",
        "a throbbing low end pumped rhythmically by a sidechain envelope.",
        "hypnotic repetition of the same pitch, alive through volume movement alone."
      ],
      clap: [
        "pulsing bass.",
        "The sound of a low bass tone swelling and fading in a steady rhythmic pulse.",
        "A recording of a bass note throbbing as it is pumped in and out.",
        "The sound of a single deep pitch breathing rhythmically under the beat."
      ],
      mulan: [
        "pulsing bass.",
        "pulsing bass, sidechain bass, throbbing low end, hypnotic bass.",
        "progressive house, melodic techno, trance, deep techno.",
        "one low note pulsing and breathing under the groove."
      ]
    },
    negative: {
      shared: [
        "a bassline stepping through many different pitches.",
        "a flat static low tone holding perfectly still.",
        "plucked acoustic bass walking the changes.",
        "sharply articulated stabs with hard attack."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/punchy-bass",
    axis: "bass",
    label: "Punchy bass",
    hint: "Бас бьёт: резкая атака, плотный удар в грудь, короткий хвост. Скорее толчок, чем гул.",
    positive: {
      shared: [
        "punchy bass.",
        "a hard immediate attack landing like a thump against the chest.",
        "tight compact low notes that hit and stop dead.",
        "muscular impact with a snappy leading edge and short controlled decay."
      ],
      clap: [
        "punchy bass.",
        "The sound of a low note hitting hard and stopping immediately.",
        "A recording of a tight bass thump with a sharp leading edge.",
        "The sound of compact low impacts striking with force and short decay."
      ],
      mulan: [
        "punchy bass.",
        "punchy bass, tight bass, hard hitting low end.",
        "tech house, techno, electro, bass house.",
        "a tight bass that lands hard and shuts off immediately."
      ]
    },
    negative: {
      shared: [
        "soft woolly bass with a slow gradual attack.",
        "long sustained low drone smeared by reverb.",
        "loose boomy low end blurring into the next note.",
        "a smooth sine sub held long and even beneath the mix."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/rubbery-bass",
    axis: "bass",
    label: "Rubbery bass",
    hint: "Резиновый бас: упругий, пружинящий тон, ноты слегка проскальзывают по высоте и отскакивают.",
    positive: {
      shared: [
        "rubbery bass.",
        "elastic springy low notes that bend and snap back into place.",
        "portamento glides sliding between pitches, bouncy and pliable.",
        "a soft round synth low end flexing and rebounding like stretched rubber."
      ],
      clap: [
        "rubbery bass.",
        "The sound of a springy synth bass note bending and snapping back.",
        "A recording of a bass gliding between pitches with an elastic bounce.",
        "The sound of a soft round low note stretching and rebounding."
      ],
      mulan: [
        "rubbery bass.",
        "rubbery bass, elastic bass, bouncy bass, sliding synth bass.",
        "electro funk, uk garage, tech house, boogie.",
        "a springy elastic bass bending and bouncing between notes."
      ]
    },
    negative: {
      shared: [
        "rigid stiff bass with a fixed unmoving pitch.",
        "hard distorted low end with a brittle edge.",
        "a deep pure sine tone holding one flat timbre.",
        "a stiff acoustic bass guitar with a blunt fingered attack."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/acid-303",
    axis: "bass",
    label: "Acid 303",
    hint: "Звук TB-303: кислотная линия со скользящим резонансным фильтром, глайды и акценты, писк и щёлкающий резонанс.",
    positive: {
      shared: [
        "acid 303.",
        "a resonant filter sweeping up and down across a squelching monosynth line.",
        "glides and accents linking notes, the cutoff whistling as it opens.",
        "an accented monosynth line screaming as the resonance climbs toward self-oscillation."
      ],
      mulan: [
        "acid 303.",
        "roland tb-303, acid bassline, 303, squelchy synth bass.",
        "acid house, acid techno, acid trance, rave.",
        "a squelching resonant 303 line sliding through a filter sweep."
      ]
    },
    negative: {
      shared: [
        "plucked acoustic bass guitar or upright bass.",
        "a clean deep sub tone sitting still beneath the track.",
        "a detuned saw bass growling wide with slow phase movement.",
        "static bass holding one timbre throughout."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/reese-bass",
    axis: "bass",
    label: "Reese bass",
    hint: "Reese: расстроенные пилы, бьющиеся друг о друга, широкий рычащий бас с фазовым биением поперёк стерео.",
    positive: {
      shared: [
        "reese bass.",
        "detuned sawtooth layers beating against each other into a wide growl.",
        "phase movement swirling across the stereo field, thick and menacing.",
        "a snarling low drone that churns and shifts as the detune sweeps."
      ],
      mulan: [
        "reese bass.",
        "reese bass, detuned saw bass, growling bass, neurofunk bass.",
        "drum and bass, jungle, neurofunk, darkstep.",
        "a wide detuned growling bass churning across the stereo field."
      ]
    },
    negative: {
      shared: [
        "a clean narrow sine bass on a single oscillator.",
        "a soft fingered electric bass with natural string decay.",
        "short punchy bass stabs with hard attack.",
        "resonant filter squelch sliding between notes."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/fm-bass",
    axis: "bass",
    label: "FM bass",
    hint: "FM-синтез в басу: металлический, звонкий тон с колокольными обертонами, часто с щелчком в атаке.",
    positive: {
      shared: [
        "fm bass.",
        "metallic bell-like overtones ringing inside the low note.",
        "bright inharmonic partials with a hard clanging attack transient.",
        "digital synthesis timbre, bright and slightly cold above the fundamental."
      ],
      mulan: [
        "fm bass.",
        "fm bass, dx7 bass, digital bass, metallic synth bass.",
        "electro, techno, drum and bass, uk bass, idm.",
        "a metallic digital bass ringing with bell-like overtones."
      ]
    },
    negative: {
      shared: [
        "warm analogue bass with soft rounded harmonics.",
        "a fingered electric bass guitar with a warm woody body.",
        "a pure sine sub carrying only its fundamental.",
        "a thick detuned saw growl swirling across the mix."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/wobble-bass",
    axis: "bass",
    label: "Wobble bass",
    hint: "Воблер: бас качается от LFO, фильтр открывается и закрывается ритмично — тот самый «вау-вау» в низу.",
    positive: {
      shared: [
        "wobble bass.",
        "an lfo swinging the filter open and shut, making the low end talk.",
        "rhythmic wah movement chewing the bass into repeated surges.",
        "the tone morphs bar by bar, yawning wide then clamping down again."
      ],
      mulan: [
        "wobble bass.",
        "wobble bass, lfo bass, dubstep bass, filter modulation.",
        "dubstep, brostep, bassline, uk bass, riddim.",
        "a bass chewed by an lfo, opening and closing in rhythm."
      ]
    },
    negative: {
      shared: [
        "steady bass tone held under one unchanging filter setting.",
        "a plain deep sub resting flat beneath the mix.",
        "a dry plucked bass guitar with a plain unmodulated tone.",
        "short dry stabs that end before the tone can move."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "bass/distorted-bass",
    axis: "bass",
    label: "Distorted bass",
    hint: "Перегруженный низ: клиппинг, грязь и хрип в басу, гармоники прут наверх, тон рвётся и скрежещет.",
    positive: {
      shared: [
        "distorted bass.",
        "the low end driven into clipping, gritty harmonics tearing upward.",
        "fuzz and saturation rasping over the note, harsh and overdriven.",
        "a snarling crunched low tone pushed past the point of clean."
      ],
      clap: [
        "distorted bass.",
        "The sound of a bass tone overdriven into gritty buzzing distortion.",
        "A recording of a low note clipping and rasping with fuzz.",
        "The sound of a heavily saturated low end tearing and crunching."
      ],
      mulan: [
        "distorted bass.",
        "distorted bass, overdriven bass, fuzz bass, saturated low end.",
        "industrial techno, hard techno, drum and bass, breakcore.",
        "a bass driven hard into gritty overdriven distortion."
      ]
    },
    negative: {
      shared: [
        "a clean smooth bass running well inside its headroom.",
        "a pure deep sine sub with a polished tone.",
        "a clean electric bass fingered softly with a warm round tone.",
        "gentle rounded synth bass sitting quietly in the mix."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/analog",
    axis: "synths",
    label: "Analog",
    hint: "Аналоговое тепло: осцилляторы слегка плывут по строю, резонансный фильтр скругляет верх, тон густой и живой.",
    positive: {
      shared: [
        "analog synth.",
        "Warm oscillators drift slightly out of tune against each other.",
        "A resonant low-pass filter rounds the top off every note.",
        "Thick round electronic tones with a soft, slightly unstable pitch."
      ],
      mulan: [
        "analog synth.",
        "analog synth, warm oscillators, resonant filter.",
        "analog synthesizer, vintage synth, detuned oscillators, subtractive synth, warm keys.",
        "Detuned oscillators drifting under a resonant filter."
      ]
    },
    negative: {
      shared: [
        "The sound of a crisp digital synthesizer with glassy, precise tones.",
        "Hard brittle electronic tones with perfectly stable pitch."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/digital",
    axis: "synths",
    label: "Digital",
    hint: "Цифровой тон: чистый и стеклянный, строй идеально ровный, край жёсткий, верх кристально яркий.",
    positive: {
      shared: [
        "digital synth.",
        "Crisp glassy tones with perfectly stable pitch.",
        "Sharp wavetable notes cut in with machine-like precision.",
        "Clean high harmonics sit above a precise, sterile tone."
      ],
      mulan: [
        "digital synth.",
        "digital synth, wavetable, glassy tone.",
        "digital synthesizer, wavetable synth, crystalline keys, bright electronic, clean tone.",
        "Bright crystalline synth tones with a hard clean edge."
      ]
    },
    negative: {
      shared: [
        "The sound of a warm analog synthesizer with drifting, unstable oscillators.",
        "Soft round vintage tones rolled off by a resonant filter."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/modular",
    axis: "synths",
    label: "Modular",
    hint: "Модульный патч: сигнал бродит по патч-кордам, тон непредсказуемо меняется, слышны клики и самозарождающиеся линии.",
    positive: {
      shared: [
        "modular synth.",
        "A patched voltage line wanders and lands somewhere new each pass.",
        "Clicks, bursts and slow voltage shifts reshape the tone as it plays.",
        "A self-generating electronic patch that keeps mutating."
      ],
      mulan: [
        "modular synth.",
        "modular synth, eurorack, patch cables, generative.",
        "modular synthesizer, eurorack, west coast synthesis, generative patch, experimental electronics.",
        "A generative eurorack patch that keeps mutating."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "synths/fm",
    axis: "synths",
    label: "FM",
    hint: "FM-синтез: металлические колокольные обертоны, звонкий щелчок в атаке, яркость меняется по ходу ноты.",
    positive: {
      shared: [
        "fm synth.",
        "Bell-like metallic overtones ring out of each note.",
        "A hard clangorous attack decays into a glassy electric-piano tone.",
        "Bright inharmonic partials that shift as the note sustains."
      ],
      mulan: [
        "fm synth.",
        "fm synth, metallic bells, electric piano.",
        "fm synthesis, digital bells, clangorous keys, glassy electric piano, bright synth.",
        "Metallic bell overtones ringing over a glassy keyboard tone."
      ]
    },
    negative: {
      shared: [
        "The sound of a warm analog saw wave through a resonant filter.",
        "Thick round subtractive synth tones with drifting oscillators."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/pads",
    axis: "synths",
    label: "Pads",
    hint: "Пэды: длинные держащиеся аккорды с медленной атакой, ковром лежащие под всем остальным.",
    positive: {
      shared: [
        "synth pad.",
        "Long held chords swell in slowly and hang under everything.",
        "A sustained chord bed with a slow attack and a slow release.",
        "Slowly moving chords that stay under the whole arrangement."
      ],
      mulan: [
        "synth pad.",
        "synth pad, sustained chords, slow attack.",
        "synth pads, ambient chords, warm chord bed, atmospheric keys, lush pad.",
        "A slow swelling chord bed that hangs under everything."
      ]
    },
    negative: {
      shared: [
        "Short clipped chord hits that stop the instant they land.",
        "Tight plucked notes that decay immediately."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/stabs",
    axis: "synths",
    label: "Stabs",
    hint: "Стабы: короткие аккордовые удары, обрубленные сразу после атаки; ритмические тычки, а не подложка.",
    positive: {
      shared: [
        "synth stab.",
        "Short clipped chord hits punch in and stop immediately.",
        "Chords land on the offbeat and cut off after a fraction of a second.",
        "Sharp organ-like chord punches with a hard, abrupt end."
      ],
      clap: [
        "synth stab.",
        "The sound of a short keyboard chord chopped off right after its attack.",
        "A recording of sharp clipped organ punches ending abruptly.",
        "The sound of brief chord jabs, hard attack and immediate silence."
      ]
    },
    negative: {
      shared: [
        "Long sustained chords that swell in slowly and hang for bars.",
        "A soft chord bed with a slow attack and a long tail."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/plucks",
    axis: "synths",
    label: "Plucks",
    hint: "Плаки: короткие щипковые ноты с резкой атакой и быстрым затуханием, звенят поверх грува.",
    positive: {
      shared: [
        "synth pluck.",
        "Short plucked notes with a sharp attack and a fast decay.",
        "Single bright notes strike and fall away almost at once.",
        "A crisp percussive keyboard tone that rings briefly and dies."
      ],
      clap: [
        "synth pluck.",
        "The sound of a plucked electronic string ringing briefly and fading.",
        "A recording of short bright plucked tones with a sharp attack.",
        "The sound of a crisp percussive keyboard note that decays fast."
      ]
    },
    negative: {
      shared: [
        "Long sustained chords hanging under the whole arrangement.",
        "A continuous unchanging tone that holds for minutes."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/drones",
    axis: "synths",
    label: "Drones",
    hint: "Дрон: одна непрерывная нота держится без пауз, тон почти не меняется, гармония стоит на месте.",
    positive: {
      shared: [
        "drone.",
        "One continuous tone holds steady underneath the whole track.",
        "A single sustained note stays at the same pitch for minutes.",
        "An unbroken low hum that barely changes across the whole passage."
      ],
      mulan: [
        "drone.",
        "drone, sustained tone, static harmony.",
        "drone music, sustained synth, ambient drone, static harmony, continuous tone.",
        "One unbroken sustained tone holding under everything."
      ]
    },
    negative: {
      shared: [
        "Repeating note patterns stepping up and down constantly.",
        "Short clipped notes hitting one after another."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/bleepy",
    axis: "synths",
    label: "Bleepy",
    hint: "Блипы: маленькие чистые электронные пики и щелчки, тонкие синусные тоны в верхнем регистре.",
    positive: {
      shared: [
        "bleepy synth.",
        "Small pure electronic beeps ping in the upper register.",
        "Thin sine tones blip and skip in short patterns.",
        "Tiny bright chirps and clicks scatter across the beat."
      ],
      clap: [
        "bleepy synth.",
        "The sound of small electronic beeps and blips in the high register.",
        "A recording of thin pure sine tones chirping in short bursts.",
        "The sound of tiny bright electronic pips scattering across a beat."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "synths/buzzy-saw",
    axis: "synths",
    label: "Buzzy saw",
    hint: "Жужжащая пила: густой расстроенный пилообразный тон с шершавыми верхами, гудит и режет насквозь.",
    positive: {
      shared: [
        "buzzy saw synth.",
        "A thick detuned saw wave buzzes with a rough, grainy top end.",
        "Harsh sawtooth tones rasp and cut through the mix.",
        "A fat raspy lead humming with dense high harmonics."
      ],
      clap: [
        "buzzy saw synth.",
        "The sound of a rough buzzing sawtooth wave with a grainy edge.",
        "A recording of a thick detuned saw lead rasping in the midrange.",
        "The sound of a harsh electronic buzz dense with high harmonics."
      ]
    },
    negative: {
      shared: [
        "Thin pure sine tones with a smooth rounded top.",
        "Small soft electronic beeps with a clean, gentle edge."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/quirky-digital",
    axis: "synths",
    label: "Quirky digital",
    hint: "Чудаковатый цифровой тембр: кривые пиксельные звуки, скачущие огибающие, игрушечные и слегка нелепые.",
    positive: {
      shared: [
        "quirky digital synth.",
        "Odd pixelated tones jump between registers in a playful way.",
        "Cartoonish squeaks and warbles bend and stumble between the notes.",
        "Toy-like digital sounds with lopsided, jumping envelopes."
      ],
      clap: [
        "quirky digital synth.",
        "The sound of odd cartoonish electronic squeaks and wobbles.",
        "A recording of toy-like pixelated tones jumping between registers.",
        "The sound of playful glitchy digital warbles with lopsided envelopes."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "synths/plasticky",
    axis: "synths",
    label: "Plasticky",
    hint: "Пластиковый тембр: гладкий, дешёвый, слегка резиновый; звук лёгкий и полый, как из бюджетного пресета.",
    positive: {
      shared: [
        "plasticky synth.",
        "Smooth rubbery tones with a thin, hollow body.",
        "A cheap moulded keyboard sound with a slick, brittle surface.",
        "Glossy synthetic notes that feel light and hollow."
      ],
      clap: [
        "plasticky synth.",
        "The sound of a cheap plastic keyboard tone, slick and hollow.",
        "A recording of smooth rubbery electronic notes with a thin body.",
        "The sound of glossy synthetic tones with a brittle moulded surface."
      ]
    },
    negative: {
      shared: [
        "The sound of a warm analog synthesizer with a thick, full body.",
        "Rich round vintage tones with drifting oscillators."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/watery",
    axis: "synths",
    label: "Watery",
    hint: "Водянистый синт: хорус и фейзер размывают тон, звук течёт и переливается. Про модуляцию, а не про запись воды.",
    positive: {
      shared: [
        "watery synth.",
        "Chorus and phasing smear the tone into a liquid shimmer.",
        "Layered detuned copies slide against each other and make the note ripple.",
        "A flanged keyboard tone that swirls and folds under itself."
      ],
      clap: [
        "watery synth.",
        "The sound of a chorused electronic tone rippling and swirling.",
        "A recording of a phased synth tone bending slowly under itself.",
        "The sound of a flanged keyboard tone smeared into a wet, swirling blur."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "synths/arpeggiated",
    axis: "synths",
    label: "Arpeggiated",
    hint: "Арпеджио: аккорд разложен в бегущую цепочку нот, рисунок повторяется и переливается.",
    positive: {
      shared: [
        "arpeggiated synth.",
        "A chord is broken into a running line of single notes.",
        "The same note pattern climbs and falls over and over.",
        "A stepped sequencer line cycles through a repeating figure."
      ],
      mulan: [
        "arpeggiated synth.",
        "arpeggio, sequenced synth, repeating pattern.",
        "arpeggiated synth, sequencer line, rolling arpeggio, synth pattern, electronic sequence.",
        "A chord broken into a repeating run of single notes."
      ]
    },
    negative: {
      shared: [
        "Long held chords that hang still under the track.",
        "A single sustained tone that stays at one pitch."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/oscillating",
    axis: "synths",
    label: "Oscillating",
    hint: "Осцилляция: тон качается сам по себе — LFO ровными циклами гнёт громкость, высоту или фильтр.",
    positive: {
      shared: [
        "oscillating synth.",
        "The tone pulses in a steady cycle, rising and falling on its own.",
        "A slow wobble bends the pitch and volume back and forth.",
        "A repeating tremolo throbs through the held note."
      ],
      clap: [
        "oscillating synth.",
        "The sound of an electronic tone throbbing in a steady cycle.",
        "A recording of a synth whose pitch wobbles slowly back and forth.",
        "The sound of a pulsing tremolo moving through a sustained note."
      ]
    },
    negative: {
      shared: [
        "A flat sustained tone that stays completely still.",
        "One unchanging note held at a constant level."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "synths/sweeping",
    axis: "synths",
    label: "Sweeping",
    hint: "Свип: фильтр медленно едет вверх или вниз, тембр открывается и закрывается за одну фразу.",
    positive: {
      shared: [
        "sweeping filter.",
        "A filter opens slowly and pulls the brightness up across the phrase.",
        "The tone closes down again as the cutoff travels back.",
        "Resonance whistles as the sweep passes through the harmonics."
      ],
      clap: [
        "sweeping filter.",
        "The sound of a filter sweep opening slowly across an electronic tone.",
        "A recording of a resonant cutoff travelling up through the harmonics.",
        "The sound of a synth brightening and closing as the filter moves."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/piano",
    axis: "instruments",
    label: "Piano",
    hint: "Акустическое фортепиано: молоточки по струнам, педальный сустейн, широкая динамика. Электропиано — метка Rhodes.",
    positive: {
      shared: [
        "piano.",
        "acoustic piano, felt hammers striking steel strings, wooden soundboard resonance.",
        "sustained pedal chords ring and decay across a wide dynamic range.",
        "bright hammered keys play a melody and comp chords over the beat."
      ],
      clap: [
        "The sound of a piano.",
        "The sound of an acoustic grand piano, felt hammers striking steel strings inside a wooden case.",
        "A recording of piano chords held on the sustain pedal, ringing and then decaying.",
        "A recording of hammered keys, soft under the fingers then loud and percussive."
      ],
      mulan: [
        "piano.",
        "piano, acoustic piano, grand piano, keys.",
        "piano, keys, jazz, house, soul, ballad, solo instrument.",
        "A track led by acoustic piano chords."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/rhodes",
    axis: "instruments",
    label: "Rhodes",
    hint: "Электропиано: удар по металлическим язычкам, колокольная атака, тёплое тремоло. Молоточковый рояль — метка Piano.",
    positive: {
      shared: [
        "rhodes.",
        "rhodes electric piano, hammers on metal tines, bell-like attack, soft bloom.",
        "warm tremolo chords wobble slowly between the speakers.",
        "mellow tine keys comp chords that bark slightly when struck hard."
      ],
      clap: [
        "The sound of a Rhodes electric piano.",
        "The sound of small metal tines struck by hammers, a bell-like attack blooming into a warm sustain.",
        "A recording of Rhodes chords with a slow tremolo panning left and right.",
        "A recording of soft mellow tine keys that growl through an amplifier when struck hard."
      ],
      mulan: [
        "rhodes.",
        "rhodes, fender rhodes, electric piano, suitcase rhodes, keys.",
        "rhodes, electric piano, jazz funk, soul, deep house, downtempo, neo soul.",
        "A track led by warm tremolo Rhodes chords."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/organ",
    axis: "instruments",
    label: "Organ",
    hint: "Хаммонд и родня: драубары, ровный тянущийся тон, щелчок клавиши, вращающийся динамик.",
    positive: {
      shared: [
        "organ.",
        "hammond organ, drawbar tone holding steady while the key is held down.",
        "a rotary speaker swirls the chords faster and slower.",
        "a percussive key click starts each note, then the tone sits flat and sustained."
      ],
      clap: [
        "The sound of an organ.",
        "The sound of a Hammond drawbar organ, a steady tone held flat for as long as the key stays down.",
        "A recording of organ chords through a rotary speaker, the tone swirling and shifting in pitch.",
        "A recording of a gospel organ, stacked sustained chords swelling and filling the room."
      ],
      mulan: [
        "organ.",
        "organ, hammond organ, drawbar organ, tonewheel organ, keys.",
        "organ, gospel, soul jazz, ska, funk, house, psychedelic.",
        "A track led by swirling organ chords."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/clavinet",
    axis: "instruments",
    label: "Clavinet",
    hint: "Клавинет: струна, прижатая и отпущенная — сухой цепкий щипок, фанковые стаккато-аккорды, вау-педаль.",
    positive: {
      shared: [
        "clavinet.",
        "clavinet, a keyboard whose strings are struck and damped, a short twangy pluck.",
        "tight staccato funk comping with a wah pedal opening and closing.",
        "a dry percussive keyboard riff, every note plucked short and clipped."
      ],
      clap: [
        "The sound of a clavinet.",
        "The sound of a clavinet, keys plucking short twangy strings with a hard percussive attack.",
        "A recording of clavinet funk comping, tight muted chops through a wah pedal.",
        "A recording of a dry electric keyboard riff, each note snapping short and damped tight."
      ],
      mulan: [
        "clavinet.",
        "clavinet, hohner clavinet, clav, funk keys.",
        "clavinet, funk, disco, soul, boogie, wah, seventies groove.",
        "A track driven by a funky clavinet riff."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/acoustic-guitar",
    axis: "instruments",
    label: "Acoustic guitar",
    hint: "Стальные струны на деревянной деке: бой медиатором, скрип пальцев по ладам. Нейлон — метка Nylon guitar.",
    positive: {
      shared: [
        "acoustic guitar.",
        "steel strings ringing over a hollow wooden body, bright and woody.",
        "strummed open chords with a pick, fingers squeaking along the frets.",
        "a warm wooden strum sits under the beat with real string resonance."
      ],
      clap: [
        "The sound of an acoustic guitar.",
        "The sound of steel strings strummed over a hollow wooden body, bright and ringing.",
        "A recording of an acoustic guitar being picked, fingers squeaking as they slide along the frets.",
        "A recording of open chords strummed with a plectrum, the wooden body resonating after each stroke."
      ],
      mulan: [
        "acoustic guitar.",
        "acoustic guitar, steel string guitar, strummed guitar, folk guitar.",
        "acoustic guitar, folk, singer songwriter, americana, balearic, downtempo, tropical house.",
        "A track led by a strummed acoustic guitar."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/nylon-guitar",
    axis: "instruments",
    label: "Nylon guitar",
    hint: "Нейлон под подушечками пальцев: мягкая округлая атака, перебор, тихий тёплый тон. Сталь — метка Acoustic guitar.",
    positive: {
      shared: [
        "nylon guitar.",
        "nylon strings plucked with bare fingertips, a soft rounded attack and mellow tone.",
        "fingerpicked arpeggios on a classical guitar, warm and quiet.",
        "gentle nylon string picking, close-miked, the wooden body breathing behind it."
      ],
      clap: [
        "The sound of a nylon string guitar.",
        "The sound of soft nylon strings plucked by bare fingertips, rounded and mellow with a gentle attack.",
        "A recording of classical guitar fingerpicking, arpeggios rolling quietly across the strings.",
        "A recording of a bossa nova nylon guitar, muted chords brushed close to the bridge."
      ],
      mulan: [
        "nylon guitar.",
        "nylon string guitar, classical guitar, spanish guitar, fingerpicked.",
        "nylon guitar, bossa nova, flamenco, latin, downtempo, balearic, lounge.",
        "A track led by fingerpicked nylon guitar."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/electric-guitar",
    axis: "instruments",
    label: "Electric guitar",
    hint: "Звукосниматели через усилитель: сустейн, подтяжки, перегруз или чистые фанковые чопы с хорусом.",
    positive: {
      shared: [
        "electric guitar.",
        "pickups through an amplifier, bent notes sustaining into a singing lead tone.",
        "overdriven power chords, palm-muted chugs, feedback at the end of a phrase.",
        "clean chopped chords with chorus and spring reverb over the groove."
      ],
      clap: [
        "The sound of an electric guitar.",
        "The sound of an electric guitar through an amplifier, notes bending and sustaining into feedback.",
        "A recording of a distorted guitar riff, overdriven power chords and palm-muted chugging.",
        "A recording of clean funk guitar chops, a thin bright tone through a phaser."
      ],
      mulan: [
        "electric guitar.",
        "electric guitar, distorted guitar, guitar riff, guitar solo, wah guitar.",
        "electric guitar, rock, funk, disco, psychedelic, post punk, indie dance.",
        "A track built on an electric guitar riff."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/strings",
    axis: "instruments",
    label: "Strings",
    hint: "Смычковые: скрипки и виолончели, вибрато, легато-свеллы, пиццикато. Метка широкая — синтетические струнные тоже попадут.",
    positive: {
      shared: [
        "strings.",
        "bowed violins and cellos, hair drawn across the strings, vibrato on the long notes.",
        "a string section swells in legato unison, then plucks short pizzicato notes.",
        "layered violins and low cellos hold a sustained line over the arrangement."
      ],
      clap: [
        "The sound of strings.",
        "The sound of a bowed violin section, hair dragging across strings with vibrato on the held notes.",
        "A recording of cellos and violins swelling together in a long legato line.",
        "A recording of pizzicato strings, short plucked notes over sustained bowed harmony."
      ],
      mulan: [
        "strings.",
        "strings, string section, violin, cello, synth strings.",
        "strings, orchestral, cinematic, disco strings, symphonic, chamber, soundtrack.",
        "A track carrying a string arrangement."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/brass",
    axis: "instruments",
    label: "Brass",
    hint: "Медная секция: губы в мундштуке, унисонные стэбы, тромбоновые глиссандо. Соло трубы — метка Trumpet.",
    positive: {
      shared: [
        "brass.",
        "a horn section stabs in unison, lips buzzing into metal mouthpieces.",
        "bright blaring hits punch on the offbeat, then hold a fat sustained chord.",
        "trombones slide under the melody while high horns blare over the groove."
      ],
      clap: [
        "The sound of a brass section.",
        "The sound of horns blown in unison, lips buzzing into metal mouthpieces, bright and blaring.",
        "A recording of brass stabs punching short and loud, breath audible at the front of each hit.",
        "A recording of trombones sliding between notes beneath a wall of bright sustained horns."
      ],
      mulan: [
        "brass.",
        "brass, horn section, brass stabs, horns, trombone.",
        "brass, funk, soul, disco, big band, ska, afrobeat, salsa.",
        "A track with a brass section."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/upright-bass",
    axis: "instruments",
    label: "Upright bass",
    hint: "Контрабас: большой деревянный корпус, щипок пальцами, короткий деревянный удар, шагающая линия.",
    positive: {
      shared: [
        "upright bass.",
        "a large hollow wooden body, thick strings plucked by hand, a thumping woody attack.",
        "a walking acoustic bassline, each note fat, short and slightly buzzing.",
        "double bass notes decay quickly, the wood resonating under the fingers."
      ],
      clap: [
        "The sound of an upright double bass.",
        "The sound of thick strings plucked on a large wooden double bass, a woody thump and quick decay.",
        "A recording of a walking acoustic bassline, fingers pulling the strings against the fingerboard.",
        "A recording of a bowed double bass, a deep dark tone sustained under the harmony."
      ],
      mulan: [
        "upright bass.",
        "upright bass, double bass, acoustic bass, walking bass.",
        "upright bass, jazz, bossa nova, swing, soul jazz, broken beat, downtempo.",
        "A track with an acoustic upright bassline."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/slap-bass",
    axis: "instruments",
    label: "Slap bass",
    hint: "Слэп: большой палец бьёт струну о лады, указательный дёргает её обратно — щелчки, поп и глухие призрачные ноты.",
    positive: {
      shared: [
        "slap bass.",
        "the thumb strikes the string against the frets, the finger pops it back with a bright snap.",
        "a percussive funk bassline full of muted ghost notes and metallic clicks.",
        "an electric bass snapping and popping hard against the beat."
      ],
      clap: [
        "The sound of slap bass.",
        "The sound of a bass string slapped by the thumb and popped by the finger, bright and metallic.",
        "A recording of a funk bass being slapped, sharp clicks and muted ghost notes between the pops.",
        "A recording of an electric bass played percussively, strings snapping against the frets."
      ],
      mulan: [
        "slap bass.",
        "slap bass, funk bass, popping bass, electric bass.",
        "slap bass, funk, disco, boogie, jazz fusion, acid jazz, eighties.",
        "A funk track driven by slap bass."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/saxophone",
    axis: "instruments",
    label: "Saxophone",
    hint: "Трость гудит в мундштуке: дыхание вокруг каждой ноты, подтяжки, рык, щелчки клапанов.",
    positive: {
      shared: [
        "saxophone.",
        "a reed buzzes against the mouthpiece, breath audible around every note.",
        "an expressive sax solo bends and growls over the groove.",
        "a honking baritone sax riff repeats while the keys click between notes."
      ],
      clap: [
        "The sound of a saxophone.",
        "The sound of a reed buzzing in a saxophone mouthpiece, breathy and vocal with an audible growl.",
        "A recording of a saxophone solo, notes bending and swelling with the player's breath.",
        "A recording of a honking baritone saxophone riff, keys clicking between the phrases."
      ],
      mulan: [
        "saxophone.",
        "saxophone, sax, tenor sax, alto sax, baritone sax.",
        "saxophone, jazz, acid jazz, soul, funk, lounge, house.",
        "A track with a saxophone solo."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/trumpet",
    axis: "instruments",
    label: "Trumpet",
    hint: "Труба: губы в маленьком мундштуке, яркий пронзительный тон, носовой звук под сурдиной. Вся секция — метка Brass.",
    positive: {
      shared: [
        "trumpet.",
        "lips buzz into a small cup mouthpiece, a brilliant piercing tone cutting through.",
        "a muted trumpet plays a nasal wah-inflected line close to the microphone.",
        "bright valved phrases climb over the groove, breath at the front of each note."
      ],
      clap: [
        "The sound of a trumpet.",
        "The sound of a trumpet, lips buzzing into a small cup mouthpiece, brilliant and piercing.",
        "A recording of a muted trumpet, a nasal buzzing tone played close to the microphone.",
        "A recording of a flugelhorn melody, round and warm with valves clicking between notes."
      ],
      mulan: [
        "trumpet.",
        "trumpet, muted trumpet, cornet, flugelhorn.",
        "trumpet, jazz, latin jazz, salsa, hip hop, nu jazz, cinematic.",
        "A track with a trumpet melody."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/flute",
    axis: "instruments",
    label: "Flute",
    hint: "Воздух по краю отверстия: чистый тон в оболочке из придыхания, трели, бамбуковые скольжения.",
    positive: {
      shared: [
        "flute.",
        "air blown across an open hole, a pure tone wrapped in breath noise.",
        "a light woodwind melody trills and flutters above the beat.",
        "a wooden bamboo flute bends between notes, breathy and hollow."
      ],
      clap: [
        "The sound of a flute.",
        "The sound of air blown across the edge of a flute, a pure whistling tone with breath around it.",
        "A recording of a flute melody, light and airy with fluttering trills.",
        "A recording of a bamboo flute, hollow and breathy, sliding between notes."
      ],
      mulan: [
        "flute.",
        "flute, bamboo flute, bansuri, panpipes, woodwind.",
        "flute, jazz, tropical, balearic, downtempo, spiritual jazz, world.",
        "A track with an airy flute melody."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/marimba",
    axis: "instruments",
    label: "Marimba",
    hint: "Деревянные бруски и мягкие мэллеты над резонаторными трубами: тёплый глухой тон, быстрое затухание. Металл — метка Vibraphone.",
    positive: {
      shared: [
        "marimba.",
        "wooden bars struck with soft yarn mallets over long wooden resonator tubes.",
        "a warm dark rolling mallet melody with a soft rounded attack.",
        "hollow wooden tones bounce through the arrangement, each note dying away quickly."
      ],
      clap: [
        "The sound of a marimba.",
        "The sound of wooden bars struck by soft mallets, warm hollow tones ringing through wooden resonators.",
        "A recording of a marimba melody, round dark wooden notes rolling one after another.",
        "A recording of soft mallets rolling on low wooden bars, a woody hum under each stroke."
      ],
      mulan: [
        "marimba.",
        "marimba, wooden mallets, mallet percussion, xylophone.",
        "marimba, afrobeat, tropical house, minimal, downtempo, latin, cinematic.",
        "A track with a rolling marimba melody."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/vibraphone",
    axis: "instruments",
    label: "Vibraphone",
    hint: "Алюминиевые бруски: длинный звенящий сустейн, моторное вибрато, педаль. Дерево — метка Marimba.",
    positive: {
      shared: [
        "vibraphone.",
        "aluminium bars struck with mallets, a long shimmering metallic sustain.",
        "motor-driven vibrato wobbles the chords as they ring out and decay.",
        "cool metallic mallet chords held on the pedal, dissolving slowly."
      ],
      clap: [
        "The sound of a vibraphone.",
        "The sound of metal bars struck with mallets, ringing with a slow motor-driven vibrato.",
        "A recording of vibraphone chords held on the pedal, a long shimmering metallic decay.",
        "A recording of soft mallets on aluminium bars, cool metallic tones pulsing as they fade."
      ],
      mulan: [
        "vibraphone.",
        "vibraphone, vibes, mallet keys, tuned metal bars.",
        "vibraphone, jazz, lounge, bossa nova, deep house, nu jazz, cinematic.",
        "A track with shimmering vibraphone chords."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/kalimba",
    axis: "instruments",
    label: "Kalimba",
    hint: "Металлические язычки на дощечке, щипок большими пальцами: крошечный звонкий тон с быстрым затуханием и лёгким дребезгом.",
    positive: {
      shared: [
        "kalimba.",
        "short metal tongues bolted to a small wooden board, plucked by the thumbnails.",
        "tiny bright plinking notes with a quick decay and a faint buzzing rattle.",
        "an interlocking mbira figure repeats, small, hollow and toy-like."
      ],
      clap: [
        "The sound of a kalimba.",
        "The sound of metal tongues plucked by thumbs on a small wooden board, bright and plinking.",
        "A recording of a thumb piano, tiny plinking notes with a soft buzzing rattle behind them.",
        "A recording of an mbira, interlocking plucked figures over a hollow gourd resonance."
      ],
      mulan: [
        "kalimba.",
        "kalimba, thumb piano, mbira, likembe.",
        "kalimba, african, downtempo, chillout, balearic, ambient, folk.",
        "A track with a plucked kalimba figure."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/steel-drums",
    axis: "instruments",
    label: "Steel drums",
    hint: "Настроенные вмятины на крышке бочки, резиновые палочки: яркий звенящий металл с тремоло-роллами.",
    positive: {
      shared: [
        "steel drums.",
        "tuned dents hammered into an oil drum lid, struck with rubber-tipped sticks.",
        "bright shimmering metal pan notes rolled in fast tremolo.",
        "ringing Caribbean pan melodies with a splashy metallic overtone."
      ],
      clap: [
        "The sound of steel drums.",
        "The sound of a steel pan struck with rubber-tipped sticks, bright ringing metal full of overtones.",
        "A recording of a steel pan melody rolled in fast tremolo, shimmering and splashy.",
        "A recording of a Caribbean steel band, tuned oil drums ringing together."
      ],
      mulan: [
        "steel drums.",
        "steel drums, steel pan, steelpan, pan.",
        "steel drums, calypso, soca, caribbean, tropical house, dub, reggae.",
        "A track with bright steel pan melodies."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/sitar",
    axis: "instruments",
    label: "Sitar",
    hint: "Ситар: щипок на плоском порожке даёт жужжание, резонирующие струны звенят под мелодией, ноты скользят между ладов.",
    positive: {
      shared: [
        "sitar.",
        "a long-necked plucked string buzzing on a wide flat bridge, gourd resonance behind it.",
        "notes slide and bend across curved frets while sympathetic strings ring underneath.",
        "a droning string is strummed between phrases, twanging and metallic."
      ],
      clap: [
        "The sound of a sitar.",
        "The sound of a sitar, plucked strings buzzing on a flat bridge with sympathetic strings ringing behind.",
        "A recording of sitar notes bent and slid across curved frets, twanging and metallic.",
        "A recording of a droning Indian string instrument, a gourd body humming under the melody."
      ],
      mulan: [
        "sitar.",
        "sitar, indian classical, raga, tanpura drone.",
        "sitar, psychedelic, indian, ethnic, downtempo, world, sixties.",
        "A track with a buzzing sitar line."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/kora",
    axis: "instruments",
    label: "Kora",
    hint: "Кора: двадцать одна струна над большой калебасой, арфовые каскады пальцами — мягко и текуче. Ngoni суше и щипковее.",
    positive: {
      shared: [
        "kora.",
        "twenty-one strings over a large gourd covered in hide, plucked with thumbs and forefingers.",
        "cascading harp-like arpeggios ripple in soft rounded tones.",
        "a rolling West African harp figure flows continuously under the melody."
      ],
      clap: [
        "The sound of a kora.",
        "The sound of a kora, many strings plucked over a large calabash gourd, soft and harp-like.",
        "A recording of cascading kora arpeggios, thumbs and fingers rippling across two rows of strings.",
        "A recording of a West African gourd harp, rounded notes flowing in continuous patterns."
      ],
      mulan: [
        "kora.",
        "kora, gourd harp, mande music, griot.",
        "kora, senegal, gambia, mande, afro house, world music, acoustic.",
        "A track with rippling kora arpeggios."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/ngoni",
    axis: "instruments",
    label: "Ngoni",
    hint: "Нгони: маленькая лютня с кожаной декой, несколько струн, сухой носовой щипок и быстрые повторяющиеся риффы. Kora мягче.",
    positive: {
      shared: [
        "ngoni.",
        "a small canoe-shaped wooden lute with a hide top, a few strings plucked hard.",
        "dry twanging notes snap out in fast repeating riffs.",
        "a nasal buzzing West African lute drives a looping figure."
      ],
      clap: [
        "The sound of an ngoni.",
        "The sound of an ngoni, a few strings plucked over a hide-covered wooden body, dry and twanging.",
        "A recording of fast repeating ngoni riffs, nasal buzzing notes snapping short.",
        "A recording of a West African skin-topped lute, plucked hard with a percussive attack."
      ],
      mulan: [
        "ngoni.",
        "ngoni, donso ngoni, xalam, african lute.",
        "ngoni, mali, bambara, wassoulou, desert blues, afrobeat, folk.",
        "A track driven by a plucked ngoni riff."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/congas",
    axis: "instruments",
    label: "Congas",
    hint: "Конги: высокие бочонки под ладонями, глубокий открытый тон и резкие слэпы, тумбао. Маленькая спаренная пара — метка Bongos.",
    positive: {
      shared: [
        "congas.",
        "tall barrel drums struck with flat palms, deep round open tones and sharp slaps.",
        "a rolling tumbao pattern of heel and toe strokes with muted fills.",
        "large hand drums ring low and warm underneath the beat."
      ],
      clap: [
        "The sound of congas.",
        "The sound of tall barrel drums struck by open palms, deep round tones with cracking slaps.",
        "A recording of a conga pattern, heel and toe strokes rolling between muted and open hits.",
        "A recording of large hand drums, a low warm skin tone ringing after each stroke."
      ],
      mulan: [
        "congas.",
        "congas, conga drums, tumbao, latin percussion.",
        "congas, latin, salsa, afro cuban, latin house, tribal house, disco.",
        "A track with rolling conga patterns."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/bongos",
    axis: "instruments",
    label: "Bongos",
    hint: "Бонго: маленькая спаренная пара под пальцами — высокий сухой цокот, мартильо. Большие бочонки — метка Congas.",
    positive: {
      shared: [
        "bongos.",
        "a small joined pair of drums played with fingertips, high, dry and snapping.",
        "a fast martillo pattern chatters between the two little heads.",
        "tight high-pitched hand drums cut through the top of the groove."
      ],
      clap: [
        "The sound of bongos.",
        "The sound of a small pair of hand drums struck with fingertips, high pitched, dry and snapping.",
        "A recording of a fast bongo pattern chattering between a small head and a slightly larger one.",
        "A recording of tight little hand drums, sharp finger taps with a thumb sliding on the skin."
      ],
      mulan: [
        "bongos.",
        "bongos, bongo drums, martillo, latin percussion.",
        "bongos, latin, afro cuban, mambo, lounge, tribal house, disco.",
        "A track with chattering bongo patterns."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "instruments/tabla",
    axis: "instruments",
    label: "Tabla",
    hint: "Табла: звонкий настроенный удар по чёрному пятну и низкий бас, который гнут ладонью. Общая категория — Hand percussion на оси Percussion.",
    positive: {
      shared: [
        "tabla.",
        "a small pitched wooden drum rings clear while a deep metal drum bends under the palm.",
        "fast fingertip strokes spell out rolling patterns on a black-spotted head.",
        "a sliding low boom answers bright ringing taps."
      ],
      clap: [
        "The sound of tabla.",
        "The sound of tabla, a bright ringing pitched stroke answered by a deep metal drum bent with the palm.",
        "A recording of fast tabla fingerwork, crisp tuned taps rolling in intricate patterns.",
        "A recording of Indian drums, a low booming stroke sliding in pitch under ringing accents."
      ],
      mulan: [
        "tabla.",
        "tabla, indian percussion, indian classical, raga.",
        "tabla, indian, world, downtempo, psychedelic, asian underground, ambient.",
        "A track with intricate tabla patterns."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "voice/instrumental",
    axis: "voice",
    label: "Instrumental",
    hint: "Мелодию ведут инструменты: синты, клавиши, пэды — линию играют, а не поют. Голос впереди — это метка Vocal-led.",
    positive: {
      shared: [
        "instrumental.",
        "instrumental, instrumental music, instrumental version, dub mix.",
        "the lead melody is played on synths and keys through the whole track.",
        "drums, bass, chords and pads carry the arrangement from start to end."
      ],
      clap: [
        "The sound of instrumental music, the melody played on keys.",
        "The sound of a synthesizer lead over drums and bass.",
        "The sound of pads, chords and percussion carrying the tune together.",
        "A recording of a dub mix where echoing chords answer the drums."
      ]
    },
    negative: {
      shared: [
        "vocals, singing, a human voice.",
        "a singer performs the lead melody.",
        "sung lyrics over a beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/vocal-led",
    axis: "voice",
    label: "Vocal-led",
    hint: "Голос впереди: спетые фразы, хуки, ведущая партия поверх музыки. Про присутствие голоса; регистр и характер — на узких метках оси.",
    positive: {
      shared: [
        "vocals.",
        "vocal, vocals, singing, sung hook.",
        "a lead voice sits at the front of the mix and carries the tune.",
        "sung phrases, held notes and audible breath ride over the beat."
      ],
      clap: [
        "The sound of a person singing over music.",
        "The sound of a lead voice at the front of the mix.",
        "The sound of sung phrases and held notes over drums.",
        "A recording of a singer carrying the melody with audible breath."
      ]
    },
    negative: {
      shared: [
        "instrumental.",
        "an instrumental club track, the melody played on synths.",
        "drums, bass and pads run through with the lead line on keys."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/female-lead",
    axis: "voice",
    label: "Female lead",
    hint: "Высокий ведущий голос: светлый верхний регистр, головной звук, лёгкое дыхание. Граница проходит по регистру, а не по полу — проверяй ушами.",
    positive: {
      shared: [
        "female vocal.",
        "high register singing, soprano and alto range, bright upper voice.",
        "a high bright voice carries the lead melody in the upper range.",
        "airy head voice, light upper register, clear high singing tone."
      ],
      clap: [
        "The sound of a high voice singing the lead melody.",
        "The sound of singing in a bright upper register.",
        "The sound of an airy head voice over music.",
        "A recording of a clear high singing voice carrying the tune."
      ]
    },
    negative: {
      shared: [
        "a deep low voice sings in the chest register.",
        "low baritone singing, dark heavy vocal tone."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/male-lead",
    axis: "voice",
    label: "Male lead",
    hint: "Низкий ведущий голос: грудной регистр, тёмный плотный тембр. Граница проходит по регистру, а не по полу — проверяй ушами.",
    positive: {
      shared: [
        "male vocal.",
        "low register singing, baritone and tenor range, dark chest voice.",
        "a deep chest voice carries the lead melody in the lower range.",
        "thick low singing, gravelly delivery, heavy weight in the tone."
      ],
      clap: [
        "The sound of a low voice singing the lead melody.",
        "The sound of singing in a deep chest register.",
        "The sound of a dark heavy voice over music.",
        "A recording of a gravelly low singing voice carrying the tune."
      ]
    },
    negative: {
      shared: [
        "a high bright voice sings in the upper register.",
        "airy head voice, light soprano singing."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/backing",
    axis: "voice",
    label: "Backing vocals",
    hint: "Подпевки позади основного звука: дубли, гармонии, ad lib, стеки голосов. Голос впереди микса — это метка Vocal-led.",
    positive: {
      shared: [
        "backing vocals.",
        "backing vocals, harmony vocals, doubled voices, ad libs.",
        "layered harmony voices sit low in the mix and answer each phrase.",
        "stacked oohs and ad libs fill the background behind the music."
      ],
      clap: [
        "The sound of backing vocals behind the music.",
        "The sound of layered harmony voices singing together.",
        "The sound of doubled voices answering in the background.",
        "A recording of stacked ad libs and harmony singing low in the mix."
      ]
    },
    negative: {
      shared: [
        "a solo singer holds the lead melody front and centre.",
        "one dry close vocal take sits on top of the mix."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/wordless",
    axis: "voice",
    label: "Wordless vocals",
    hint: "Голос без слов: мычание, вокализ, «оо» и «аа» на открытых гласных. Голос работает как инструмент, а не как текст.",
    positive: {
      shared: [
        "wordless vocals.",
        "wordless vocals, vocalise, humming, oohs and aahs.",
        "a voice hums a melody on open vowels through the track.",
        "textural singing on loose syllables, breathy melodic humming."
      ],
      clap: [
        "The sound of humming over music.",
        "The sound of a voice singing on open vowels.",
        "The sound of wordless vocalising and soft oohs.",
        "A recording of a person humming a melody."
      ]
    },
    negative: {
      shared: [
        "sung lyrics, a verse and a chorus with words.",
        "a rapper delivers rhymed lines over the beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/spoken",
    axis: "voice",
    label: "Spoken word",
    hint: "Речь ведёт трек: монолог, начитка, нарратив поверх скупой подложки. Речь вставкой — это метка Dialogue sample.",
    positive: {
      shared: [
        "spoken word.",
        "spoken word, narration, monologue, talking voice.",
        "a voice talks in plain speech over a sparse backing.",
        "a narrated monologue runs across the whole track."
      ],
      clap: [
        "The sound of speech over music.",
        "The sound of a person narrating over a beat.",
        "The sound of a talking voice in the foreground.",
        "A recording of a spoken monologue with sparse music behind it."
      ]
    },
    negative: {
      shared: [
        "sung melodic vocals, a singer holds the tune.",
        "rapped bars locked tightly to the drum pattern."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/dialogue",
    axis: "voice",
    label: "Dialogue sample",
    hint: "Речевой семпл вставкой: реплика из фильма поверх музыки. Голос здесь фрагмент, а не ведущая партия — партия на метке Spoken word.",
    positive: {
      shared: [
        "dialogue sample.",
        "dialogue sample, movie sample, sampled speech, film quote.",
        "a spoken line lifted from a film drops in over the music.",
        "a short recorded conversation appears between the drums."
      ],
      clap: [
        "The sound of a spoken film line over music.",
        "The sound of sampled speech dropped into a beat.",
        "The sound of a short recorded conversation between musical phrases.",
        "A recording of dialogue from a movie playing over the track."
      ]
    },
    negative: {
      shared: [
        "a sung lead melody performed all the way through.",
        "continuous narration across the whole track."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/rap",
    axis: "voice",
    label: "Rap / MC",
    hint: "Читка в ритм: рифмованные строки, флоу, MC поверх бита. Спетый мелодический лид — это метка Vocal-led.",
    positive: {
      shared: [
        "rap.",
        "rap, hip hop vocals, mc, emcee, bars.",
        "rhymed lines are delivered in tight rhythm over the drums.",
        "an mc chats over a heavy sound system beat, verses and hooks."
      ],
      clap: [
        "The sound of rapping over a beat.",
        "The sound of a person rapping rhymed verses.",
        "The sound of an mc talking in rhythm over drums.",
        "A recording of rapped bars over heavy drums and bass."
      ]
    },
    negative: {
      shared: [
        "a singer holds long sung notes and melodic phrases.",
        "a calm spoken monologue drifting loosely over the music."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/chopped",
    axis: "voice",
    label: "Chopped vocals",
    hint: "Нарезанные вокальные фразы в роли перкуссии: стабы, заикания, питч-сдвиг. Целая спетая партия — это метка Vocal-led.",
    positive: {
      shared: [
        "chopped vocals.",
        "chopped vocals, vocal chops, cut-up vocal samples, stutter edits.",
        "short sliced vocal fragments are played like a percussion part.",
        "pitched vocal stabs stutter and repeat across the groove."
      ],
      clap: [
        "The sound of chopped up vocal samples in a beat.",
        "The sound of short stuttering vocal fragments.",
        "The sound of sliced voice used as percussion.",
        "A recording of pitched vocal stabs repeating over a groove."
      ]
    },
    negative: {
      shared: [
        "a full sustained lead vocal performance, long sung phrases.",
        "one long vocal take runs unbroken over the groove."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/whispered",
    axis: "voice",
    label: "Whispered vocals",
    hint: "Шёпот вплотную к микрофону: воздух, шипящие, тихое бормотание вместо пения.",
    positive: {
      shared: [
        "whispered vocals.",
        "whispered vocals, whispering, breathy delivery, murmured voice.",
        "a breathy whisper sits close to the microphone above the beat.",
        "soft murmured speech, air and sibilance around every word."
      ],
      clap: [
        "The sound of whispering over music.",
        "The sound of a breathy whisper close to the microphone.",
        "The sound of soft murmured speech.",
        "A recording of a person whispering with audible breath and sibilance."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "voice/chant",
    axis: "voice",
    label: "Chant",
    hint: "Скандирование: короткая фраза, которую группа повторяет в унисон; мантра, отклик на зов.",
    positive: {
      shared: [
        "chant.",
        "chant, chanting, mantra, group chant, call and response.",
        "a group repeats one short phrase again and again over the beat.",
        "many voices land the same syllables together, flat and percussive."
      ],
      clap: [
        "The sound of a group chanting.",
        "The sound of a mantra repeated over and over.",
        "The sound of voices shouting the same phrase in unison.",
        "A recording of many voices repeating one short line over drums."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "voice/choir",
    axis: "voice",
    label: "Choir",
    hint: "Хор: много голосов держат длинные аккорды широкой гармонией. Одиночный солист — это метка Vocal-led.",
    positive: {
      shared: [
        "choir.",
        "choir, choral, gospel choir, massed voices, sacred vocals.",
        "many voices hold long chords together in wide harmony.",
        "a choral swell rises behind the music in sustained block harmony."
      ],
      clap: [
        "The sound of a choir singing.",
        "The sound of many voices holding sustained harmony.",
        "The sound of a choral swell behind music.",
        "A recording of massed singers holding long chords together."
      ]
    },
    negative: {
      shared: [
        "a single solo singer alone on the melody.",
        "one unaccompanied voice carries the tune by itself."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/vocoder",
    axis: "voice",
    label: "Vocoder",
    hint: "Вокодер: синтезатор как несущая, голос как модулятор — роботизированные форманты и аккорды голосом. Трубка во рту — метка Talkbox.",
    positive: {
      shared: [
        "vocoder.",
        "vocoder, vocoded vocals, robot voice, electro vocals.",
        "a synth carrier is shaped by a voice into robotic harmonised speech.",
        "a chorded machine voice sings with buzzy electronic formants."
      ],
      clap: [
        "The sound of a vocoder voice over music.",
        "The sound of a robotic voice made from a synthesizer and speech.",
        "The sound of vocoded singing with buzzy electronic formants.",
        "A recording of a machine voice singing chords in an electro track."
      ]
    },
    negative: {
      shared: [
        "a plain untreated human singing voice.",
        "a guitar or synth pushed through a tube into the mouth."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "voice/talkbox",
    axis: "voice",
    label: "Talkbox",
    hint: "Токбокс: звук гитары или синта идёт по трубке в рот, губы лепят гласные — «уа-уа» речь инструментом. Голос через синтез — метка Vocoder.",
    positive: {
      shared: [
        "talkbox.",
        "talkbox, tube vocal effect, mouth-shaped guitar, funk talk box.",
        "a plastic tube carries a synth into the mouth, which forms the vowels.",
        "a single melodic line bends through mouth shapes into wah-like speech."
      ],
      clap: [
        "The sound of a talkbox over music.",
        "The sound of a guitar shaped into vowels by a mouth tube.",
        "The sound of a wah-like talking instrument sliding between vowels.",
        "A recording of a talk box lead line in a funk track."
      ]
    },
    negative: {
      shared: [
        "a plain untreated singing voice recorded straight to the microphone.",
        "a synthesizer carrier modulated by speech into chorded robot vocals."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/warm",
    axis: "timbre",
    label: "Warm / Rounded",
    hint: "Округлый мягкий тон: полные нижние середины, придавленный верх, мягкая атака. Про сам тембр, а не про обработку — плёнка и сатурация на оси Texture.",
    positive: {
      shared: [
        "warm, rounded tone.",
        "Low mids sit full and soft, and the top end is gently rolled off.",
        "Round bass notes and mellow pads with soft, unhurried attacks.",
        "Every sound has a padded edge and a full, cushioned body."
      ],
      mulan: [
        "warm.",
        "warm, mellow, rounded, soft.",
        "warm, cozy, rounded, full-bodied, gentle.",
        "A warm, rounded tonal palette."
      ]
    },
    negative: {
      shared: [
        "cold, brittle, icy tone.",
        "thin frosty tones with a hard, brittle edge."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/cold",
    axis: "timbre",
    label: "Cold / Brittle",
    hint: "Ледяной тонкий тон с жёстким краем: мало тела, острый верх, стерильная клиническая окраска.",
    positive: {
      shared: [
        "cold, brittle tone.",
        "Thin icy tones with a hard edge and very little body.",
        "Sounds are lean and clinical, with a scarce, dry low end and a keen edge.",
        "A frosty, austere palette that feels chilled and fragile."
      ],
      mulan: [
        "cold.",
        "cold, icy, brittle, clinical.",
        "cold, frosty, sterile, thin, glacial, austere.",
        "A cold, brittle tonal palette."
      ]
    },
    negative: {
      shared: [
        "warm, mellow, rounded tone.",
        "soft full-bodied warmth with gentle highs."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/bright",
    axis: "timbre",
    label: "Bright / Sharp",
    hint: "Верх режет вперёд: звонкие тарелки, хай-хэты и лиды, быстрые острые атаки, всё блестит и колет.",
    positive: {
      shared: [
        "bright, sharp tone.",
        "The top end cuts forward with sharp attacks and vivid, ringing highs.",
        "Cymbals, hats and lead tones sit high and glinting above everything else.",
        "A forward, incisive sound with fast, biting attacks."
      ],
      mulan: [
        "bright.",
        "bright, sharp, crisp, vivid.",
        "bright, piercing, shiny, high-register, cutting, brilliant.",
        "A bright, sharp-edged tonal palette."
      ]
    },
    negative: {
      shared: [
        "dark, muted, muffled tone.",
        "a dull palette with the highs rolled away."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/dark",
    axis: "timbre",
    label: "Dark / Muted",
    hint: "Тон уведён вниз и затемнён: глухой верх, тяжёлые нижние середины, притупленная атака. Про окраску, а не про фильтрацию — размытие это Hazy на оси Texture.",
    positive: {
      shared: [
        "dark, muted tone.",
        "The tone sits low and shaded, with dulled highs and heavy lower mids.",
        "Muted stabs and covered pads with blunt, softened attacks.",
        "A shadowed, subdued palette weighted toward the bottom of the register."
      ],
      mulan: [
        "dark.",
        "dark, moody, muted, shadowy.",
        "dark, sombre, dusky, brooding, low-register, subdued.",
        "A dark, subdued tonal palette."
      ]
    },
    negative: {
      shared: [
        "bright, sharp, crisp tone.",
        "glinting high tones with fast biting attacks."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/metallic",
    axis: "timbre",
    label: "Metallic",
    hint: "Звенящий металл: удары по листу, пружины, наковальня, колокольные обертоны, долгий гул. Про окраску звука, а не про гитарную тяжесть.",
    positive: {
      shared: [
        "metallic tone.",
        "Struck metal rings out: sheet metal, springs, anvils and bell-like clangs.",
        "Tones carry clanging inharmonic overtones and a long, humming decay.",
        "Sounds carry the hard ring of steel bars and struck metal plates."
      ],
      clap: [
        "metallic tone.",
        "The sound of struck metal ringing with a long clanging decay.",
        "A recording of metal bars, springs and sheet metal being struck.",
        "The sound of bell-like metal resonance with harsh inharmonic overtones."
      ],
      mulan: [
        "metallic tone.",
        "metallic percussion, clanging hits, ringing steel.",
        "metallic, struck metal, springs, scrap metal, bell overtones, clang.",
        "A track with metallic ringing percussion."
      ]
    },
    negative: {
      shared: [
        "wooden tone with a soft, dry knock.",
        "struck wood and hand drums with a short, dull decay."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/glassy",
    axis: "timbre",
    label: "Glassy",
    hint: "Стеклянные кристальные верхи: колокольчики, челеста, звонкие синты с хрупким блеском.",
    positive: {
      shared: [
        "glassy tone.",
        "Crystalline bell tones and chimes ring clear in the high register.",
        "Glockenspiel, celesta and glass-toned synths sparkle with a hard, tinkling sheen.",
        "High tones ring transparent and delicate, with a fine shimmering edge."
      ],
      mulan: [
        "glassy.",
        "glassy, crystalline, bell-like, shimmering.",
        "glassy, chimes, glockenspiel, celesta, crystal synth, delicate.",
        "A glassy, crystalline tonal palette."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "timbre/woody",
    axis: "timbre",
    label: "Woody",
    hint: "Деревянный корпус звучит: маримба, вудблок, римшот, ручные барабаны. Про окраску тона; про рисунок ударных — метка Wooden на оси Percussion.",
    positive: {
      shared: [
        "woody tone.",
        "Wooden bodies resonate: marimba, woodblock, rimshot and hand drums.",
        "Dry mid-range knocks with a short natural decay that dies quickly.",
        "Struck wood and marimba bars give every tone a soft wooden body."
      ],
      clap: [
        "woody tone.",
        "The sound of a marimba and struck wooden bars ringing softly.",
        "A recording of wooden hand drums and woodblocks with a dry knock.",
        "The sound of wood resonating with a full mid-range body."
      ]
    },
    negative: {
      shared: [
        "metallic clanging tone with a long ringing decay.",
        "struck steel and bell-like overtones ringing long."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/hollow",
    axis: "timbre",
    label: "Hollow",
    hint: "Полый трубчатый тон: середина как будто выбрана, звук гудит внутри пустой трубы.",
    positive: {
      shared: [
        "hollow tone.",
        "Tones sound scooped and tube-like, as if ringing inside an empty pipe.",
        "A boxy square-wave colour with the middle of the spectrum scooped away.",
        "Cupped, tubular timbres that ring around an empty centre."
      ],
      clap: [
        "hollow tone.",
        "The sound of a tone ringing inside an empty tube, cupped and open.",
        "The sound of hollow, tubular resonance with a scooped, empty centre.",
        "A recording of a hollow boxy drum ringing with an open tube tone."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "timbre/nasal",
    axis: "timbre",
    label: "Nasal",
    hint: "Зажатый гнусавый тон: язычковый, жужжащий, с горбом в верхней середине. Гобой и казу.",
    positive: {
      shared: [
        "nasal tone.",
        "A pinched, honking mid-range tone that sounds squeezed through a narrow throat.",
        "Reedy, buzzing timbres with a strong bump in the upper mids.",
        "Oboe-like and kazoo-like colours, narrow and pressed, sitting forward in the mids."
      ],
      clap: [
        "nasal tone.",
        "The sound of a pinched, honking reed tone squeezed through a narrow tube.",
        "A recording of a nasal, buzzing instrument with a strong mid-range peak.",
        "The sound of a reedy, whining tone pressed into the upper mids."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "timbre/resonant",
    axis: "timbre",
    label: "Resonant",
    hint: "Резонанс поёт: узкая полоса звенит поверх остального, свист на пике свипа, долгий послезвук. Пересекается с Acid 303.",
    positive: {
      shared: [
        "resonant tone.",
        "One narrow band rings out and sings above the rest of the tone.",
        "A squelching filter peak whistles as the cutoff opens, ringing on after each note.",
        "Tones ring around a single whistling peak, hovering at the edge of self-oscillation."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "timbre/smooth",
    axis: "timbre",
    label: "Smooth / Silky",
    hint: "Шелковистый тон: ровная гладкая поверхность, мягкая атака, плавные тянущиеся линии.",
    positive: {
      shared: [
        "smooth, silky tone.",
        "Sine-like pads and legato strings glide with an even, glossy surface.",
        "Creamy Rhodes chords and velvety leads move in soft, continuous curves.",
        "Every tone has a slick, frictionless surface and a gentle, gliding attack."
      ],
      mulan: [
        "smooth.",
        "smooth, silky, velvety, sleek.",
        "smooth, creamy, glossy, flowing, gliding, refined.",
        "A smooth, silky tonal palette."
      ]
    },
    negative: {
      shared: [
        "rough, abrasive, gritty tone.",
        "harsh scraping timbre with a jagged edge."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/rough",
    axis: "timbre",
    label: "Rough / Abrasive",
    hint: "Шершавый резкий тон: жужжание, скрежет, пила с занозами. Про саму окраску; про перегруз обработкой — Distorted на оси Texture.",
    positive: {
      shared: [
        "rough, abrasive tone.",
        "Harsh buzzing tones with a scraping, sandpapered edge.",
        "Raspy sawtooth leads and gritty timbres that grate against the ear.",
        "Coarse, splintered surfaces cover every note, and the attacks land hard and dry."
      ],
      clap: [
        "rough, abrasive tone.",
        "The sound of a harsh rasping buzz with a scraping edge.",
        "A recording of a coarse, grating tone scraping across a hard surface.",
        "The sound of a gritty, sandpapered timbre rasping over every note."
      ]
    },
    negative: {
      shared: [
        "smooth, silky, velvety tone.",
        "soft creamy timbre with gentle edges."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "timbre/detuned",
    axis: "timbre",
    label: "Detuned / Unstable",
    hint: "Расстроенный плывущий тон: осцилляторы бьются друг о друга, высота гуляет вверх-вниз, мутный хорус.",
    positive: {
      shared: [
        "detuned, unstable tone.",
        "Oscillators drift apart and beat against each other in a slow wavering pulse.",
        "Chords beat and phase against themselves, wandering a little above and below the note.",
        "Notes waver out of tune, thick with a queasy, seasick chorus."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/clean",
    axis: "texture",
    label: "Clean / Hi-fi",
    hint: "Чистый современный продакшн: широкая полоса, острые транзиенты, прозрачный тихий фон, всё разложено по местам.",
    positive: {
      shared: [
        "clean, hi-fi production.",
        "A pristine studio recording with full bandwidth and sharp, precise transients.",
        "Every element is separated, detailed and transparent from the lows to the highs.",
        "A polished modern mix with a wide, quiet, immaculate surface."
      ],
      mulan: [
        "hi-fi.",
        "hi-fi, clean, polished, pristine.",
        "hi-fi, studio production, crisp, detailed, transparent, high fidelity.",
        "A clean, high fidelity studio production."
      ]
    },
    negative: {
      shared: [
        "a lo-fi recording with tape hiss and vinyl crackle.",
        "a murky, dull transfer with narrow bandwidth."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/raw",
    axis: "texture",
    label: "Raw",
    hint: "Сырой необработанный звук: грубые склейки, неровный баланс, горячие уровни, шум комнаты. Записано, а не собрано.",
    positive: {
      shared: [
        "raw production.",
        "An unpolished take with ragged edges, room bleed and levels pushed hot.",
        "The recording is left as it was played: hard cuts, uneven balance, audible handling.",
        "A blunt, unfinished mix that sounds captured rather than assembled."
      ]
    },
    negative: {
      shared: [
        "a polished, immaculate studio production.",
        "a clean modern mix with careful balance and precise edits."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/lo-fi",
    axis: "texture",
    label: "Lo-fi",
    hint: "Узкая полоса и пыль: срезанный верх, зернистая муть, дешёвый тракт. Ловит и слабые оцифровки — проверяй, что это приём, а не качество файла.",
    positive: {
      shared: [
        "lo-fi.",
        "A dusty low-bandwidth recording with softened highs and a thin, boxy midrange.",
        "The sound is narrow and grainy, dubbed down through cheap home gear.",
        "A muffled, degraded transfer with a rolled-off top and a small, squashed image."
      ],
      mulan: [
        "lo-fi.",
        "lo-fi, dusty, degraded, muffled.",
        "lo-fi, bedroom recording, low bandwidth, grainy, murky, worn.",
        "A lo-fi, degraded recording."
      ]
    },
    negative: {
      shared: [
        "a clean, crisp, high fidelity studio production.",
        "a polished modern mix with a wide, clear top end."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/tape-worn",
    axis: "texture",
    label: "Tape-worn",
    hint: "Изношенная лента: детонация, плывущая высота, стёртый верх, мягкая компрессия, отпечаток соседнего витка.",
    positive: {
      shared: [
        "tape-worn.",
        "The recording wobbles with wow and flutter, as if the tape has been played thin.",
        "Pitch drifts gently, the highs are worn away and print-through ghosts appear.",
        "A magnetic tape sound: soft compression, faded top end and a wavering pitch."
      ],
      clap: [
        "tape-worn.",
        "The sound of an old magnetic tape wobbling with wow and flutter.",
        "A recording played back from a worn cassette, pitch drifting and highs faded.",
        "The sound of an unsteady reel dragging, with the top end dulled by wear."
      ]
    },
    negative: {
      shared: [
        "a clean, steady digital recording with rock-solid pitch.",
        "a crisp modern transfer with an even, stable top end."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/noisy",
    axis: "texture",
    label: "Noisy / Hissy",
    hint: "Громкий шумовой фон: шипение ленты, поверхностный шум пластинки, статика и гул под музыкой.",
    positive: {
      shared: [
        "noisy, hissy recording.",
        "A steady blanket of tape hiss sits behind the music the whole way through.",
        "Record surface noise and analogue hum crackle under every element.",
        "The noise floor is loud: broadband hiss, static and a grainy background wash."
      ],
      clap: [
        "noisy, hissy recording.",
        "The sound of steady analogue hiss and mains hum behind the music.",
        "A recording with loud record surface noise, static and broadband hiss.",
        "The sound of a hissing noise floor and crackling background static."
      ]
    },
    negative: {
      shared: [
        "a quiet, clean digital recording with a silent background.",
        "a pristine mix with a very low noise floor."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/saturated",
    axis: "texture",
    label: "Saturated",
    hint: "Аналоговая сатурация: пульт и лампа, уровни идут горячо, гармоники цветут, всё склеено в одно плотное тело.",
    positive: {
      shared: [
        "saturated.",
        "Levels run hot into analogue drive until the whole mix glues together.",
        "Console and valve saturation thickens every element into one dense, breathing body.",
        "The harmonics bloom and every peak is pressed down and softened."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/distorted",
    axis: "texture",
    label: "Distorted",
    hint: "Сигнал загнан в клиппинг: фузз, хруст, разорванные транзиенты. Про обработку; про шершавость самого тона — Rough на оси Timbre.",
    positive: {
      shared: [
        "distorted.",
        "The signal is driven into clipping until it breaks up and buzzes.",
        "Grinding fuzz tears the sound apart and smears the transients into crunch.",
        "Everything is pushed past the limit into a broken, crunching roar."
      ],
      clap: [
        "distorted.",
        "The sound of an audio signal clipping and breaking up into buzzing fuzz.",
        "A recording driven hard into overdrive, crunching and tearing at the peaks.",
        "The sound of heavy distortion, harsh and ragged, with the peaks squared off."
      ]
    },
    negative: {
      shared: [
        "a clean, undistorted recording with intact transients.",
        "an unclipped mix that stays below the limit."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/granular",
    axis: "texture",
    label: "Granular",
    hint: "Гранулярка: звук раздроблен на мельчайшие зёрна и пересобран в мерцающее облако частиц.",
    positive: {
      shared: [
        "granular.",
        "Sound is shattered into tiny grains and rebuilt into a drifting cloud.",
        "Micro-fragments of audio scatter and overlap into a smeared, particulate wash.",
        "A texture made of thousands of tiny audio particles smeared across time."
      ],
      clap: [
        "granular.",
        "The sound of audio broken into tiny grains scattering into a cloud.",
        "A recording of shattered micro-fragments overlapping into a drifting particle wash.",
        "The sound of grains of audio smearing and overlapping across a texture."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/glitchy",
    axis: "texture",
    label: "Glitchy",
    hint: "Глитч: звук заикается, выпадает и повторяется очередями, цифровые артефакты и клики рвут воспроизведение.",
    positive: {
      shared: [
        "glitchy.",
        "The audio stutters and jumps, dropping out and repeating in rapid bursts.",
        "Clicks, buffer errors and digital artefacts break the playback apart.",
        "Sound skips like a damaged file, cutting and restarting mid-note."
      ],
      clap: [
        "glitchy.",
        "The sound of digital audio stuttering, skipping and dropping out.",
        "A recording full of clicks, buffer errors and digital artefacts.",
        "The sound of a damaged file cutting out and repeating in rapid bursts."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/bitcrushed",
    axis: "texture",
    label: "Bitcrushed",
    hint: "Биткрашер: разрядность и частота дискретизации срезаны, алиасинг свистит, ступенчатая цифровая грязь.",
    positive: {
      shared: [
        "bitcrushed.",
        "The sample rate is crushed down until the sound turns coarse and quantized.",
        "Aliasing whistles over a gritty, stair-stepped signal with a hard quantized edge.",
        "An eight-bit console texture: reduced resolution, ringing overtones and a stepped top end."
      ],
      clap: [
        "bitcrushed.",
        "The sound of audio crushed to a low bit depth, coarse and buzzing.",
        "A recording downsampled until it aliases, whistling with a shrill ringing overtone.",
        "The sound of an eight-bit game console, gritty and quantized."
      ]
    },
    negative: {
      shared: [
        "a clean, high fidelity digital transfer at full resolution.",
        "a polished modern mix with fine, continuous detail."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/hazy",
    axis: "texture",
    label: "Hazy / Blurred",
    hint: "Всё за мягким фильтром: верх снят, элементы размыты и слипаются. Про фильтрацию, а не про тёмную окраску тона — это Dark на оси Timbre.",
    positive: {
      shared: [
        "hazy, blurred.",
        "Everything sits behind a soft low-pass filter, veiled and set back.",
        "Elements bleed into each other and the edges of every sound dissolve.",
        "A foggy, out-of-focus mix where transients melt into a soft wash."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/reverse",
    axis: "texture",
    label: "Reversed",
    hint: "Реверс: звуки развёрнуты задом наперёд, вместо атаки — нарастание, всасывающие переходы.",
    positive: {
      shared: [
        "reversed.",
        "Sounds run backwards, swelling from silence into the beat instead of striking.",
        "Backwards cymbals and sucked-in risers pull the arrangement into each transition.",
        "Samples play in reverse, so every tail arrives before its hit."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "texture/acoustic",
    axis: "texture",
    label: "Acoustic",
    hint: "Живой источник: реальные инструменты сняты микрофонами, дерево и кожа звучат в комнате. Про происхождение звука, не про конкретный инструмент.",
    positive: {
      shared: [
        "acoustic.",
        "The whole sound world is played on real instruments captured by microphones.",
        "Wood, string and skin resonate in a real room with air around them.",
        "Every sound is physically played and breathes with the room it was recorded in."
      ],
      clap: [
        "acoustic.",
        "The sound of real instruments played in a room and captured by microphones.",
        "A recording of physical instruments resonating with natural air and room tone.",
        "The sound of wood, string and skin vibrating, recorded live."
      ],
      mulan: [
        "acoustic.",
        "acoustic, unplugged, live instruments, played by hand.",
        "acoustic, live band, natural recording, room sound, close-miked, earthy.",
        "An acoustic recording of live played instruments."
      ]
    },
    negative: {
      shared: [
        "a fully synthesized track built from electronic sound sources.",
        "programmed synthesizer and drum machine sounds."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/organic",
    axis: "texture",
    label: "Organic",
    hint: "Живой неровный материал: сыгранные руками партии, дыхание, полевые записи, время гуляет. Звук как будто вырос, а не собран.",
    positive: {
      shared: [
        "organic.",
        "Hand-played parts breathe and drift, with the timing pushing and pulling.",
        "Living material runs through it: breath, hand claps, rustle and captured surroundings.",
        "The sound feels grown rather than built, uneven and alive in its detail."
      ],
      mulan: [
        "organic.",
        "organic, earthy, handmade, natural.",
        "organic, live percussion, field recording, breathing, human, textured.",
        "An organic, hand-played sound world."
      ]
    },
    negative: {
      shared: [
        "a rigid machine-programmed track locked to an unchanging grid.",
        "stiff synthetic sources with mechanical timing."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/synthetic",
    axis: "texture",
    label: "Synthetic",
    hint: "Полностью машинный материал: осцилляторы, драм-машины, сэмплеры, точная искусственная поверхность.",
    positive: {
      shared: [
        "synthetic.",
        "Every sound is generated electronically by oscillators, drum machines and samplers.",
        "The material is artificial and precise, built from waveforms rather than played.",
        "A fully electronic sound world with a machine-made surface."
      ],
      mulan: [
        "synthetic.",
        "synthetic, electronic, artificial, machine-made.",
        "synthetic, synthesizer, drum machine, programmed, digital, plastic.",
        "A fully synthetic electronic sound world."
      ]
    },
    negative: {
      shared: [
        "live instruments recorded in a room with microphones.",
        "a hand-played recording of wood, string and skin."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "texture/hybrid",
    axis: "texture",
    label: "Hybrid",
    hint: "Половина сыграна руками, половина синтезирована: живые записи нарезаны в программированный грув и обработаны вместе с ним.",
    positive: {
      shared: [
        "hybrid production.",
        "Live playing and machine parts share the same arrangement, trading places.",
        "Recorded instruments are chopped into a programmed groove and processed alongside it.",
        "Half the material is performed and half is generated, blended into one sound."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "space/dry-close",
    axis: "space",
    label: "Dry / Close",
    hint: "Сухо и близко: источник стоит прямо у уха, атака мгновенная, всё компактно и упёрто в лицо.",
    positive: {
      shared: [
        "dry close sound.",
        "Every sound sits right at the ear, tight and immediate.",
        "A close-miked recording where each hit lands flat and instantly.",
        "Compact sounds that stop the moment they are struck."
      ],
      clap: [
        "dry close sound.",
        "The sound of an instrument recorded right up against the microphone.",
        "A close, tight recording where every hit stops the instant it lands.",
        "The sound of a dead, absorbent studio booth, flat and immediate."
      ]
    },
    negative: {
      shared: [
        "The sound of a huge stone hall with long echoing tails.",
        "A distant, washed-out recording swimming in room sound."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "space/small-room",
    axis: "space",
    label: "Small room",
    hint: "Маленькая комната: короткое плотное отражение сразу за ударом, слышны близкие стены и низкий потолок.",
    positive: {
      shared: [
        "small room sound.",
        "A short tight reflection follows each hit almost immediately.",
        "Close walls answer every sound with a quick boxy slap.",
        "A modest bedroom-sized space with a low ceiling around the kit."
      ],
      clap: [
        "small room sound.",
        "The sound of drums recorded in a small boxy room with close walls.",
        "A recording where a short slapback returns within a fraction of a second.",
        "The sound of a tight low-ceilinged space answering every note."
      ]
    },
    negative: {
      shared: [
        "The sound of a vast stone hall with long trailing echoes.",
        "A huge cathedral space swallowing every hit."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "space/roomy",
    axis: "space",
    label: "Roomy",
    hint: "Комнатная акустика: вокруг инструментов слышна живая комната, естественный хвост тянется чуть дольше удара.",
    positive: {
      shared: [
        "roomy sound.",
        "A natural room breathes around the drums after every hit.",
        "Reflections ring on for a beat, giving the kit an audible floor and walls.",
        "A live recording made in a large wooden room with real ambience."
      ],
      clap: [
        "roomy sound.",
        "The sound of a drum kit recorded live in a large wooden room.",
        "A recording where natural ambience rings on for a beat behind each hit.",
        "The sound of a real room breathing around the instruments."
      ]
    },
    negative: {
      shared: [
        "A dead close-miked recording that stops the instant each hit lands.",
        "Tight compact sounds sitting right at the ear."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "space/spacious-airy",
    axis: "space",
    label: "Spacious / Airy",
    hint: "Просторно и воздушно: между элементами много воздуха, верхи мерцают в лёгкой дымке, звук дышит.",
    positive: {
      shared: [
        "spacious airy sound.",
        "Air opens up between the elements and the top end shimmers.",
        "A light haze surrounds the sounds and lets them breathe.",
        "An open, high-ceilinged mix where everything has space to float."
      ],
      clap: [
        "spacious airy sound.",
        "The sound of a large bright hall with soft air around every note.",
        "A recording where a light shimmer hangs above the instruments.",
        "The sound of an open high-ceilinged space, gentle and unhurried."
      ]
    },
    negative: {
      shared: [
        "A tight dry recording with everything pressed against the ear.",
        "Compact close sounds that stop the moment they land."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "space/cavernous",
    axis: "space",
    label: "Cavernous",
    hint: "Пещера: огромный хвост тянется секундами, отражения размывают аранжировку в общий гул.",
    positive: {
      shared: [
        "cavernous sound.",
        "Enormous tails trail for seconds after every hit.",
        "Reflections smear the arrangement into one rolling roar.",
        "A vast stone space swallows each note whole."
      ],
      clap: [
        "cavernous sound.",
        "The sound of a huge underground cavern with long echoing tails.",
        "A recording made in a vast stone cathedral, reflections rolling for seconds.",
        "The sound of an enormous empty hall swallowing every note."
      ]
    },
    negative: {
      shared: [
        "A dry close recording where every sound stops instantly.",
        "Tight compact hits pressed right against the ear."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "space/distant",
    axis: "space",
    label: "Distant",
    hint: "Далеко: источник отодвинут вглубь, атака смягчена и приглушена, будто слышно из соседнего помещения.",
    positive: {
      shared: [
        "distant sound.",
        "The source sits far back, its attack softened and dulled.",
        "Music heard faintly through a wall from the next room.",
        "Everything is pushed deep into the background, small and muffled."
      ],
      clap: [
        "distant sound.",
        "The sound of music playing far away in another room.",
        "A recording of a band heard faintly from across a large field.",
        "The sound of a source pushed deep into the background, dull and small."
      ]
    },
    negative: {
      shared: [
        "A close-miked sound pressed right up against the ear.",
        "An immediate front-and-centre recording with a sharp attack."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "space/dub-delay",
    axis: "space",
    label: "Dub delay",
    hint: "Даб-эхо: одиночный удар повторяется всё тише, повторы уходят в обратную связь и растворяются.",
    positive: {
      shared: [
        "dub delay.",
        "A single hit repeats and fades step by step into feedback.",
        "Echoes pile up, smear together and dissolve.",
        "Repeats trail off behind the beat, each one darker than the last."
      ],
      clap: [
        "dub delay.",
        "The sound of a single drum hit echoing away into feedback.",
        "A recording where each repeat returns darker and quieter than the last.",
        "The sound of tape echo repeats smearing together and dissolving."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "space/gated-reverb",
    axis: "space",
    label: "Gated reverb",
    hint: "Гейтед-ревер: большой хвост обрублен гейтом сразу после удара — вспышка пространства и резкая тишина.",
    positive: {
      shared: [
        "gated reverb.",
        "A big tail slams shut a fraction of a second after each hit.",
        "Bursts of room sound are chopped tight to the beat.",
        "Every snare bursts into a large space and then drops to silence."
      ],
      clap: [
        "gated reverb.",
        "The sound of a snare exploding into a large room that cuts off instantly.",
        "A recording where each burst of ambience is chopped short by a gate.",
        "The sound of a big space flaring open and slamming shut on every hit."
      ]
    },
    negative: {
      shared: [
        "Long reverb tails ringing on for seconds after each hit.",
        "A vast hall where every sound decays slowly."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/crowd-noise",
    axis: "field-fx",
    label: "Crowd noise",
    hint: "Гул толпы: невнятный ропот множества голосов, зал или улица под музыкой. Хлопки — это метка Applause.",
    positive: {
      shared: [
        "crowd noise.",
        "crowd noise, crowd murmur, chatter, a room full of people.",
        "The sound of a crowd talking and cheering, a wash of many voices.",
        "A music track with crowd noise in the background."
      ],
      clap: [
        "Crowd noise.",
        "The sound of a large crowd murmuring, many overlapping voices in a room.",
        "A recording of a busy club crowd, chatter, shouts and cheering under the music.",
        "A music track with the sound of a crowd in it."
      ]
    },
    negative: {
      shared: [
        "The sound of hands clapping, a burst of applause.",
        "A single speaking voice recorded close to the microphone."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/applause",
    axis: "field-fx",
    label: "Applause",
    hint: "Аплодисменты: хлопки ладоней, овация внутри трека. Ровный гул голосов без хлопков — метка Crowd noise.",
    positive: {
      shared: [
        "applause.",
        "applause, clapping, hands clapping, ovation.",
        "The sound of an audience clapping, a burst of sharp hand claps.",
        "A music track with applause in it."
      ],
      clap: [
        "Applause.",
        "The sound of an audience applauding, dense sharp claps from many hands.",
        "A recording of clapping and cheering at the end of a live performance.",
        "A music track with the sound of applause in it."
      ]
    },
    negative: {
      shared: [
        "The sound of a crowd murmuring and talking quietly.",
        "The sound of heavy rain drumming on a roof."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/siren",
    axis: "field-fx",
    label: "Siren",
    hint: "Сирена: воющий подъём и спад полицейской или воздушной тревоги в записи внутри трека, а не синтезаторный райзер.",
    positive: {
      shared: [
        "siren.",
        "siren, police siren, air raid siren, alarm.",
        "The sound of a siren wailing, a loud rising and falling tone in the street.",
        "A music track with a siren in it."
      ],
      clap: [
        "Siren.",
        "The sound of a police siren wailing past, a loud rising and falling tone.",
        "A recording of an air raid siren, a slow howling sweep over a city.",
        "A music track with the sound of a siren in it."
      ]
    },
    negative: {
      shared: [
        "A rising synthesizer sweep, a filtered white noise riser.",
        "A bell ringing, a metallic alarm clock."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/rain",
    axis: "field-fx",
    label: "Rain",
    hint: "Дождь: ровное влажное шипение и стук капель в записи под музыкой. Легко путается с аплодисментами и треском винила.",
    positive: {
      shared: [
        "rain.",
        "rain, rainfall, downpour, drizzle.",
        "The sound of rain falling on a roof, a steady wet hiss with scattered drops.",
        "A music track with the sound of rain in it."
      ],
      clap: [
        "Rain.",
        "The sound of rain falling, a steady wet hiss of water on pavement.",
        "A recording of a rain shower with scattered drops and distant runoff.",
        "A music track with the sound of rain in it."
      ]
    },
    negative: {
      shared: [
        "The sound of an audience clapping.",
        "Vinyl crackle, dust and pops from a record surface."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/thunder",
    axis: "field-fx",
    label: "Thunder",
    hint: "Гром: раскат и долгий низкий рокот грозы в записи внутри трека.",
    positive: {
      shared: [
        "thunder.",
        "thunder, thunderclap, rolling thunder, storm.",
        "The sound of thunder rumbling in the distance during a storm.",
        "A music track with thunder in it."
      ],
      clap: [
        "Thunder.",
        "The sound of a thunderclap, a sharp crack followed by a long low rumble.",
        "A recording of a storm, distant thunder rolling behind falling rain.",
        "A music track with the sound of thunder in it."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "field-fx/birds",
    axis: "field-fx",
    label: "Birds",
    hint: "Птицы: щебет и посвисты снаружи, полевая запись внутри трека.",
    positive: {
      shared: [
        "birds.",
        "birds, birdsong, chirping birds, dawn chorus.",
        "The sound of birds singing outdoors, high chirps and whistles.",
        "A music track with birdsong in it."
      ],
      clap: [
        "Birds.",
        "The sound of birds chirping in a forest, high whistles and calls.",
        "A recording of a dawn chorus, many small birds singing outdoors.",
        "A music track with the sound of birds in it."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "field-fx/water",
    axis: "field-fx",
    label: "Water",
    hint: "Вода: реальная запись ручья, волн, капель внутри трека. Синтезаторная «водянистость» — метка Watery на оси Synths.",
    positive: {
      shared: [
        "water.",
        "water, running water, stream, waves, dripping water.",
        "The sound of water flowing, splashing and dripping in a real recording.",
        "A music track with the sound of water in it."
      ],
      clap: [
        "Water.",
        "The sound of running water, a stream splashing over stones.",
        "A recording of waves on a shore and water dripping into a pool.",
        "A music track with the sound of real water in it."
      ]
    },
    negative: {
      shared: [
        "A watery synthesizer pad, phaser modulation, liquid filter sweep.",
        "The sound of heavy rain falling on a roof."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/wind",
    axis: "field-fx",
    label: "Wind",
    hint: "Ветер: гулкий шум порывов в полевой записи. Похож на дождь и на шумовой свип синтезатора.",
    positive: {
      shared: [
        "wind.",
        "wind, gusts, howling wind, blowing air.",
        "The sound of wind blowing outdoors, a low rushing roar with gusts.",
        "A music track with the sound of wind in it."
      ],
      clap: [
        "Wind.",
        "The sound of wind howling outdoors, a broad rushing roar with gusts.",
        "A recording of wind moving through trees and around a microphone.",
        "A music track with the sound of wind in it."
      ]
    },
    negative: {
      shared: [
        "The sound of rain hissing on wet pavement.",
        "A filtered white noise sweep from a synthesizer."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/fire",
    axis: "field-fx",
    label: "Fire",
    hint: "Огонь: сухой треск и шипение горящего дерева в записи внутри трека. Не путать с треском винила.",
    positive: {
      shared: [
        "fire.",
        "fire, campfire, crackling flames, burning wood.",
        "The sound of a fire crackling, dry pops and hiss from burning wood.",
        "A music track with the sound of fire in it."
      ],
      clap: [
        "Fire.",
        "The sound of a fire crackling, dry pops and snaps of burning wood.",
        "A recording of a campfire, flames hissing with irregular sharp crackles.",
        "A music track with the sound of a real fire in it."
      ]
    },
    negative: {
      shared: [
        "Vinyl crackle, surface noise and dust from a record.",
        "The sound of rain falling steadily on a roof."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/vinyl-crackle",
    axis: "field-fx",
    label: "Vinyl crackle",
    hint: "Треск винила: пыль, щелчки и шипение иглы под музыкой. Соседка Lo-fi на оси Texture, но здесь — сам шум пластинки.",
    positive: {
      shared: [
        "vinyl crackle.",
        "vinyl crackle, record surface noise, dust and pops, needle hiss.",
        "The sound of a record playing with crackle and clicks under the music.",
        "A music track with vinyl crackle running through it."
      ],
      clap: [
        "Vinyl crackle.",
        "The sound of a vinyl record crackling, dust, clicks and surface hiss.",
        "A recording of a needle riding a worn record, steady crackle beneath the music.",
        "A music track with the sound of vinyl crackle in it."
      ]
    },
    negative: {
      shared: [
        "The sound of a wood fire crackling.",
        "The sound of rain tapping on a window."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/radio-voice",
    axis: "field-fx",
    label: "Radio voice",
    hint: "Радиоголос: речь сквозь приёмник или рацию — узкая полоса, статика. Живое исполнение голоса — на оси Vocals.",
    positive: {
      shared: [
        "radio voice.",
        "radio voice, radio broadcast, shortwave transmission, announcer.",
        "The sound of a voice through a radio, band-limited and crackling with static.",
        "A music track with a radio voice in it."
      ],
      clap: [
        "Radio voice.",
        "The sound of a voice coming through a radio speaker, thin and band-limited.",
        "A recording of a shortwave broadcast, an announcer buried in static and tuning noise.",
        "A music track with the sound of a radio transmission in it."
      ]
    },
    negative: {
      shared: [
        "A clean sung vocal performance recorded in a studio.",
        "A rapper delivering a verse close to the microphone."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/telephone",
    axis: "field-fx",
    label: "Telephone",
    hint: "Телефон: звонок аппарата и голос в трубке с узкой полосой линии. Церковный или сигнальный колокол — метка Bell.",
    positive: {
      shared: [
        "telephone.",
        "telephone, phone ringing, dial tone, a voice on the phone.",
        "The sound of a telephone ringing and a voice heard down the line.",
        "A music track with a telephone sound in it."
      ],
      clap: [
        "Telephone.",
        "The sound of a telephone ringing, a repeating electric bell in a room.",
        "A recording of a voice down a phone line, thin and squeezed through the earpiece.",
        "A music track with the sound of a telephone in it."
      ]
    },
    negative: {
      shared: [
        "A church bell ringing over a town.",
        "A voice through a radio broadcast with static."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/machinery",
    axis: "field-fx",
    label: "Machinery",
    hint: "Машинерия: гул мотора, лязг и шипение цеха в записи под музыкой.",
    positive: {
      shared: [
        "machinery.",
        "machinery, machines, engine, motor, factory noise.",
        "The sound of machinery running, a mechanical hum with rhythmic clanking.",
        "A music track with machine noise in it."
      ],
      clap: [
        "Machinery.",
        "The sound of heavy machinery running, a droning motor with rhythmic metallic clanks.",
        "A recording of a factory floor, hissing steam, whirring gears and hammering metal.",
        "A music track with the sound of machinery in it."
      ]
    },
    negative: {
      shared: [
        "The sound of cars and trucks passing on a road.",
        "A metallic percussion hit made by a drum machine."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/traffic",
    axis: "field-fx",
    label: "Traffic",
    hint: "Трафик: шорох проезжающих машин, гудки и уличный гул города в записи внутри трека.",
    positive: {
      shared: [
        "traffic.",
        "traffic, cars passing, street noise, city ambience.",
        "The sound of traffic on a road, cars rushing past with distant horns.",
        "A music track with street traffic in it."
      ],
      clap: [
        "Traffic.",
        "The sound of traffic passing on a wet road, tyres rushing by with distant horns.",
        "A recording of a busy city street, engines, brakes and car horns.",
        "A music track with the sound of traffic in it."
      ]
    },
    negative: {
      shared: [
        "The sound of factory machinery clanking indoors.",
        "The sound of wind gusting through trees."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "field-fx/bell",
    axis: "field-fx",
    label: "Bell",
    hint: "Колокол: удар по металлу — церковный, сигнальный, ручной. Настроенные колокольчики в мелодии — на оси Instruments.",
    positive: {
      shared: [
        "bell.",
        "bell, church bell, hand bell, struck metal bell.",
        "The sound of a bell being struck, a metallic clang ringing out and decaying.",
        "A music track with a ringing bell in it."
      ],
      clap: [
        "Bell.",
        "The sound of a church bell tolling over a town, a heavy metallic clang.",
        "A recording of a hand bell or signal bell being struck, ringing and fading.",
        "A music track with the sound of a struck bell in it."
      ]
    },
    negative: {
      shared: [
        "A melody played on tuned bells, glockenspiel or celesta.",
        "A telephone ringing indoors."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/dark",
    axis: "mood",
    label: "Dark",
    hint: "Мрак: холодный минорный тон, тяжёлая тень над аранжировкой. Про окраску настроения; открытая угроза — на метке Menacing.",
    positive: {
      shared: [
        "dark mood.",
        "dark, gloomy, shadowy, cold minor tone.",
        "low minor chords sit under a heavy grey atmosphere.",
        "muted pads and a dull low bass hold the harmony in shadow."
      ]
    },
    negative: {
      shared: [
        "bright uplifting major chords, sunny mood.",
        "an open, hopeful harmony that keeps everything lit."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/menacing",
    axis: "mood",
    label: "Menacing",
    hint: "Угроза: звучит опасно, будто что-то надвигается. Не просто мрачно — есть враждебность; общая мрачность на метке Dark.",
    positive: {
      shared: [
        "menacing mood.",
        "menacing, sinister, ominous, threatening.",
        "a hostile presence looms over the track, ready to strike.",
        "growling low tones and hard metallic stabs feel dangerous."
      ]
    },
    negative: {
      shared: [
        "a playful, cheerful mood with bouncy light melodies.",
        "warm consonant chords that sound safe and welcoming."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/melancholic",
    axis: "mood",
    label: "Melancholic",
    hint: "Меланхолия: горько-сладкие минорные аккорды, одинокая мелодия дрожит и опадает — тихая печаль без драмы.",
    positive: {
      shared: [
        "melancholic mood.",
        "melancholic, wistful, longing, bittersweet.",
        "minor chords with a soft ache linger over the groove.",
        "a lone minor melody wavers and falls away."
      ]
    },
    negative: {
      shared: [
        "euphoric joyful celebration mood.",
        "a bright cheerful party atmosphere."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/euphoric",
    axis: "mood",
    label: "Euphoric",
    hint: "Эйфория: широкие мажорные аккорды раскрываются в сияющую кульминацию, синты взмывают — руки вверх.",
    positive: {
      shared: [
        "euphoric mood.",
        "euphoric, blissful, ecstatic, rapturous.",
        "wide major chords open up into a radiant climax.",
        "soaring synth lines burst into a bright ringing release."
      ]
    },
    negative: {
      shared: [
        "dark brooding menacing mood.",
        "a heavy, sad atmosphere with slow minor harmony."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/eerie",
    axis: "mood",
    label: "Eerie",
    hint: "Жуть: призрачная, тревожащая атмосфера, от которой мурашки. Про потустороннее; прямая угроза — на метке Menacing.",
    positive: {
      shared: [
        "eerie mood.",
        "eerie, haunting, ghostly, uncanny.",
        "hollow ringing tones drift through an empty space.",
        "thin detuned whistles and creaking noises unsettle the listener."
      ],
      clap: [
        "eerie mood.",
        "The sound of hollow metallic ringing in a cold empty hall.",
        "A recording of distant creaks, faint rattles and thin high tones.",
        "The sound of a wavering detuned drone in a haunted room."
      ]
    },
    negative: {
      shared: [
        "a cosy, familiar mood with friendly major melodies.",
        "cheerful daylight music with a simple singalong tune."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/playful",
    axis: "mood",
    label: "Playful",
    hint: "Игривость: лёгкий дерзкий характер, подмигивающие мелодии, звуки-игрушки, кач с хитрецой.",
    positive: {
      shared: [
        "playful mood.",
        "playful, cheeky, quirky, mischievous.",
        "bouncy little melodies wink at the listener.",
        "toy-like sounds and rubbery bass keep the tone light."
      ]
    },
    negative: {
      shared: [
        "a grim, solemn mood with heavy brooding chords.",
        "a severe, humourless atmosphere pressing down on the track."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/dreamy",
    axis: "mood",
    label: "Dreamy",
    hint: "Мечтательность: размытые пэды, парящие аккорды, всё как сквозь дымку. Про ощущение, а не про реверб — пространство на оси Space.",
    positive: {
      shared: [
        "dreamy mood.",
        "dreamy, ethereal, floating, hazy.",
        "soft blurred pads drift and hang in the air.",
        "chords smear together and lose their edges."
      ],
      mulan: [
        "dreamy mood.",
        "dreamy, ethereal, atmospheric.",
        "dreamy, ethereal, floaty, hazy, celestial, weightless mood.",
        "soft chords drifting in a warm haze."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/hypnotic",
    axis: "mood",
    label: "Hypnotic",
    hint: "Гипноз: круговое повторение, взгляд расфокусирован, время растворяется. Про состояние транса, а не про нагнетание — давление на оси Tension.",
    positive: {
      shared: [
        "hypnotic mood.",
        "hypnotic, mesmerising, entrancing, meditative.",
        "a looping figure circles endlessly and pulls the mind in.",
        "tiny repeating changes dissolve the sense of time."
      ],
      mulan: [
        "hypnotic mood.",
        "hypnotic, mesmerising, meditative.",
        "hypnotic, repetitive, circular, mesmerising, meditative, looping mood.",
        "one short phrase circling over an unchanging pulse."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/psychedelic",
    axis: "mood",
    label: "Psychedelic",
    hint: "Психоделика: звук плывёт и закручивается, фазеры, обратная лента, гуляющий строй. Про искажение восприятия, а не про жанр.",
    positive: {
      shared: [
        "psychedelic mood.",
        "psychedelic, trippy, kaleidoscopic, mind-bending.",
        "swirling phased textures wobble and turn inside out.",
        "reversed sounds and drifting pitch melt the picture."
      ],
      clap: [
        "psychedelic mood.",
        "The sound of swirling phaser sweeps over a wobbling drone.",
        "A recording of reversed tape and warbling detuned tones.",
        "The sound of echoes spiralling outward through a slow flanging wash."
      ],
      mulan: [
        "psychedelic mood.",
        "psychedelic, trippy, hallucinatory.",
        "psychedelic, trippy, kaleidoscopic, hallucinatory, mind-bending mood.",
        "warped, wobbling tones that bend out of shape."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/mysterious",
    axis: "mood",
    label: "Mysterious",
    hint: "Загадка: полутени и недосказанность, мелодия обрывками, гармония без ответа. Мягче жути — откровенно пугающее на метке Eerie.",
    positive: {
      shared: [
        "mysterious mood.",
        "mysterious, enigmatic, secretive, veiled.",
        "muted half-lit chords hold an unresolved question in the harmony.",
        "a melody appears in fragments and slips back into the mix."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/introspective",
    axis: "mood",
    label: "Introspective",
    hint: "Интроспекция: тихая одинокая мелодия, редкие аккорды, камерно и неспешно — обращено внутрь, а не к залу.",
    positive: {
      shared: [
        "introspective mood.",
        "introspective, contemplative, inward, private.",
        "a single quiet melody moves slowly with plenty of room around it.",
        "sparse chords and small details in a close, still arrangement."
      ]
    },
    negative: {
      shared: [
        "euphoric crowd-facing party mood.",
        "a loud celebratory festival atmosphere."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/uplifting",
    axis: "mood",
    label: "Uplifting",
    hint: "Подъём: светлые мажорные аккорды идут вверх, надежда и движение к свету. Мягче эйфории — пик восторга на метке Euphoric.",
    positive: {
      shared: [
        "uplifting mood.",
        "uplifting, hopeful, positive, anthemic.",
        "rising major chords lift the track toward the light.",
        "a bright singing lead line carries the harmony upward."
      ],
      mulan: [
        "uplifting mood.",
        "uplifting, hopeful, feel-good.",
        "uplifting, hopeful, anthemic, triumphant, positive, sunlit mood.",
        "big warm chords opening out over a steady beat."
      ]
    },
    negative: {
      shared: [
        "gloomy overcast mood, heavy and downcast.",
        "cold minor harmony sinking lower and lower."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "mood/deep",
    axis: "mood",
    label: "Deep",
    hint: "Глубина: тёплые приглушённые аккорды далеко внизу, округлый тяжёлый низ, подводная тяга. Про настроение, а не про жанр — дип-хаус на оси Genres.",
    positive: {
      shared: [
        "deep mood.",
        "deep, submerged, warm, weighty.",
        "warm muted chords sit far under a rounded, heavy low end.",
        "long low tails give the music an underwater pull."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/immersive",
    axis: "mood",
    label: "Immersive",
    hint: "Погружение: звук обступает со всех сторон и держит внимание. Про эффект вовлечения, а не про размер зала — пространство на оси Space.",
    positive: {
      shared: [
        "immersive mood.",
        "immersive, enveloping, absorbing, all-surrounding.",
        "dense layers close in from every side and hold the attention.",
        "a continuous unbroken field of sound covers everything else."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "mood/late-night",
    axis: "mood",
    label: "Late-night",
    hint: "Поздняя ночь: интимно, чувственно, дымно — тёплые аккорды вблизи. Про близость, а не про рассвет — утро на метке After-hours.",
    positive: {
      shared: [
        "late-night mood.",
        "late-night, smoky, sensual, intimate.",
        "warm electric piano chords played close and hushed.",
        "a velvet, low-lit tone for the small hours after midnight."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "energy/quiet",
    axis: "energy",
    label: "Quiet",
    hint: "Тихо: низкий уровень, малый динамический размах, всё звучит вполсилы и на цыпочках.",
    positive: {
      shared: [
        "quiet.",
        "Everything plays at a low level, barely above a whisper.",
        "A hushed recording with a small dynamic range.",
        "Faint instruments held far down in volume."
      ],
      mulan: [
        "quiet.",
        "quiet, hushed, low volume.",
        "quiet, hushed, subdued, low volume, understated, minimal loudness.",
        "A hushed track played far down in volume."
      ]
    },
    negative: {
      shared: [
        "A loud full-volume track pushed hard into the ceiling.",
        "Blaring drums at maximum level."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "energy/soft",
    axis: "energy",
    label: "Soft",
    hint: "Мягко: сглаженные атаки, скруглённые края, звук ложится плавно и никуда не давит.",
    positive: {
      shared: [
        "soft.",
        "Rounded attacks and smooth edges on every sound.",
        "Instruments enter gently and settle at a low, unforced level.",
        "A cushioned, feathered touch across the whole arrangement."
      ],
      mulan: [
        "soft.",
        "soft, gentle, smooth, rounded attack.",
        "soft, gentle, smooth, light touch, rounded attacks, easy dynamics, cushioned playing.",
        "Rounded gentle attacks with smooth edges."
      ]
    },
    negative: {
      shared: [
        "Hard sharp attacks slamming at full volume.",
        "Harsh distorted drums hitting with force."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "energy/loud",
    axis: "energy",
    label: "Loud",
    hint: "Громко: уровень на пределе, всё плотно сжато и упирается в потолок, динамики почти не осталось.",
    positive: {
      shared: [
        "loud.",
        "Everything is pushed hard against the ceiling of the mix.",
        "Drums hit at full volume with the level pinned high.",
        "A dense, heavily compressed wall of sound at maximum level."
      ],
      mulan: [
        "loud.",
        "loud, high volume, full blast.",
        "loud, high volume, maximal, blaring, full blast, heavily compressed.",
        "A wall of sound pinned at maximum level."
      ]
    },
    negative: {
      shared: [
        "A hushed recording held at a very low level throughout.",
        "Instruments played gently at the bottom of the level scale."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "energy/driving",
    axis: "energy",
    label: "Driving",
    hint: "Драйв: постоянный толчок вперёд, ровный ход без пауз. Про напор, а не про громкость — громкость на метке Loud.",
    positive: {
      shared: [
        "driving.",
        "A steady pulse pushes under every bar and keeps the track moving ahead.",
        "Insistent repeated hits carry the groove forward, each bar leaning into the next.",
        "Relentless forward motion, tight and unbroken through every bar."
      ],
      mulan: [
        "driving.",
        "driving, propulsive, relentless, forward motion.",
        "driving, propulsive, relentless, insistent, forward momentum, unstoppable groove.",
        "A relentless forward push that keeps rolling."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "abstract/conventional",
    axis: "abstract",
    label: "Conventional",
    hint: "Нижний полюс оси: обычный рабочий трек — привычная структура, ровный грув, знакомый ход вещей.",
    positive: {
      shared: [
        "conventional.",
        "conventional, straightforward, functional dance music.",
        "a familiar arrangement runs to a standard structure with a steady groove.",
        "a steady kick, a clean breakdown and a familiar drop land where expected."
      ]
    },
    negative: {
      shared: [
        "experimental, avant-garde sound art with an unsettled shape.",
        "a fractured piece of strange texture that drifts off the grid."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "abstract/leftfield",
    axis: "abstract",
    label: "Leftfield",
    hint: "Слегка вбок от нормы: кривые мелодии и неожиданные тембры на груве, за которым ещё можно идти.",
    positive: {
      shared: [
        "leftfield.",
        "leftfield, leftfield electronic, outsider dance, oddball club.",
        "an off-centre dance track with skewed melodies and unexpected sound choices.",
        "wonky tunes and awkward timbres over a groove that still moves."
      ],
      mulan: [
        "leftfield.",
        "leftfield, leftfield techno, leftfield house, outsider house.",
        "leftfield, wonky, off-kilter, oddball electronics, skewed pop.",
        "A leftfield electronic track."
      ]
    },
    negative: {
      shared: [
        "conventional functional dance music built to a standard formula.",
        "a plain club track that runs exactly the way the genre expects."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "abstract/abstract",
    axis: "abstract",
    label: "Abstract",
    hint: "Звук, который слушают, а не танцуют: плывущие формы, текстура вместо мелодии, открытая структура.",
    positive: {
      shared: [
        "abstract.",
        "abstract electronic, abstract sound, formless texture, open form.",
        "sound shapes drift and morph where a melody would normally sit.",
        "a piece built from drifting texture, unfixed pitch and loose shape."
      ]
    },
    negative: {
      shared: [
        "a straightforward dance track with a clear tune and a steady groove.",
        "conventional functional club music aimed squarely at the floor."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "abstract/experimental",
    axis: "abstract",
    label: "Experimental",
    hint: "Эксперимент со звуком: рваный ритм, непривычная фактура, необычные шумы вместо привычных партий.",
    positive: {
      shared: [
        "experimental.",
        "experimental electronic, avant-garde, sound art.",
        "a fractured beat and unfamiliar timbres pull the track off its usual path.",
        "an odd unsettled groove and sounds that sit outside the usual palette."
      ],
      clap: [
        "The sound of an experimental electronic recording.",
        "The sound of a beat breaking apart into rattling electronic noise.",
        "The sound of unstable machine tones sliding under a stumbling pulse.",
        "A recording of avant-garde electronic sound experiments."
      ]
    },
    negative: {
      shared: [
        "a functional club track with a standard dance groove.",
        "a straightforward house track aimed at the dance floor.",
        "a conventional techno track holding one steady beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "abstract/deconstructed",
    axis: "abstract",
    label: "Deconstructed",
    hint: "Клубные детали разобраны и собраны заново: бочка, сирена и вокальный стаб висят вне сетки, куски сменяют друг друга.",
    positive: {
      shared: [
        "deconstructed club.",
        "deconstructed club, post-club, industrial club, club edits.",
        "kick, siren and vocal stab are pulled apart and stacked into shifting blocks.",
        "sirens, stabs and vocal shards hang loose of the grid between blocks."
      ],
      mulan: [
        "deconstructed club.",
        "deconstructed club, post-club, industrial club, hyperpop.",
        "deconstructed club, ballroom, gabber, noise techno, club edits.",
        "A deconstructed club track."
      ]
    },
    negative: {
      shared: [
        "a conventional club groove that holds one steady pattern throughout.",
        "a straightforward dance track that stays on the grid from start to end."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "abstract/fragmented",
    axis: "abstract",
    label: "Fragmented",
    hint: "Музыка кусками: резкие обрывы, паузы, склейки. Фразы начинаются и обрываются, в аранжировке остаются дыры.",
    positive: {
      shared: [
        "fragmented.",
        "fragmented, broken form, stop-start, abrupt edits.",
        "the music breaks into short pieces separated by gaps and hard cuts.",
        "phrases start and stop abruptly, leaving holes in the arrangement."
      ]
    },
    negative: {
      shared: [
        "a continuous flowing groove that runs unbroken through the track.",
        "a conventional arrangement moving smoothly from one section to the next."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "abstract/sound-collage",
    axis: "abstract",
    label: "Sound collage",
    hint: "Собрано склейкой из разных записей: монтаж, стыки, слои чужих звуков. Про способ сборки, а не про конкретные звуки — они на оси Field & FX.",
    positive: {
      shared: [
        "sound collage.",
        "sound collage, tape collage, cut-up montage, audio assemblage.",
        "unrelated recordings are pasted next to each other into one piece.",
        "layers of spliced tape and stray noises are stacked into a montage."
      ],
      clap: [
        "The sound of a collage of spliced recordings.",
        "The sound of unrelated noises pasted next to each other.",
        "The sound of one recording cutting straight into another.",
        "A recording of many different sounds montaged into one piece."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "abstract/musique-concrete",
    axis: "abstract",
    label: "Musique concrète",
    hint: "Конкретная музыка: записанные предметы — металл, двери, вода — замедлены, развёрнуты и смонтированы в пьесу.",
    positive: {
      shared: [
        "musique concrete.",
        "musique concrete, acousmatic, tape music, electroacoustic composition.",
        "recorded objects are slowed, reversed and layered into a composed piece.",
        "scraped metal, doors and water are treated on tape as musical material."
      ],
      clap: [
        "The sound of objects recorded and treated as music.",
        "The sound of scraped metal, doors and water reversed and slowed.",
        "The sound of a rattling object slowed down into a low drone.",
        "A recording of everyday objects composed into an acousmatic piece."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "abstract/field-recording",
    axis: "abstract",
    label: "Field recording",
    hint: "Материал трека — записи с места: открытый воздух, тон комнаты, шипение и шорох микрофона. Конкретные звуки вроде дождя — на оси Field & FX.",
    positive: {
      shared: [
        "field recording.",
        "field recording, location recording, phonography, ambient documentary.",
        "raw location audio carries the piece: open air, room tone, distant space.",
        "microphone hiss and handling noise stay in, the capture presented as music."
      ],
      clap: [
        "The sound of a field recording used as music.",
        "The sound of open air, room tone and distant background captured on location.",
        "The sound of a microphone left running in a real place, hiss included.",
        "A recording made on location and presented as a composition."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "abstract/found-sounds",
    axis: "abstract",
    label: "Found sounds",
    hint: "Инструменты собраны из бытовых предметов: металл, пластик, бумага — их бьют, трут и роняют в ритм.",
    positive: {
      shared: [
        "found sounds.",
        "found sounds, found objects, junk percussion, object music.",
        "everyday objects are struck and rubbed to make the parts of the track.",
        "kitchen metal, plastic and paper become the rhythm and the melody."
      ],
      clap: [
        "The sound of everyday objects struck and rubbed as instruments.",
        "The sound of junk metal, plastic and paper played rhythmically.",
        "The sound of found objects tapped, scraped and dropped in time.",
        "A recording of household things used to build a beat."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "abstract/sampled",
    axis: "abstract",
    label: "Sampled",
    hint: "Трек собран из чужих записей: нарезки, винильные лупы, поднятые фразы. Про способ сборки, а не про жанр.",
    positive: {
      shared: [
        "sampled.",
        "sampled, sample-based, sample flip, crate digging, plunderphonics.",
        "the track is assembled from chopped pieces of other records.",
        "vinyl loops and lifted phrases carry the groove and the chords."
      ],
      mulan: [
        "sampled.",
        "sample based, sampling, plunderphonics, sample flip.",
        "sampled, hip hop sampling, disco loop, vinyl chops, crate digging.",
        "A sample-based track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "function/set-opener",
    axis: "function",
    label: "Set opener",
    hint: "Открытие сета: спокойно и просторно, длинное тихое вступление, барабаны мягкие и редкие, воздуха много.",
    positive: {
      shared: [
        "set opener.",
        "a calm, spacious piece with a long, slowly emerging introduction.",
        "wide open pads and sparse drums that stay soft and unhurried.",
        "an uncrowded arrangement with plenty of empty space around it."
      ]
    },
    negative: {
      shared: [
        "a hard-hitting floor track at full pressure with a huge drop.",
        "a crowded arrangement pushed to maximum loudness."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/warm-up",
    axis: "function",
    label: "Warm-up",
    hint: "Разогрев: глубокий низкий грув, приглушённый кик, мягкий округлый низ, барабаны отодвинуты — заметно ниже полной мощности.",
    positive: {
      shared: [
        "warm-up track.",
        "a deep, low-slung groove with a muted kick and a soft round low end.",
        "low-intensity dance music with the drums held back in the mix.",
        "an understated, steady arrangement that stays well below full power."
      ]
    },
    negative: {
      shared: [
        "a peak-hour banger with screaming leads and a huge drop.",
        "aggressive hard-hitting drums at maximum intensity."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/groove-builder",
    axis: "function",
    label: "Groove builder",
    hint: "Набор кача: плотная слоистая аранжировка, перкуссия и бас копятся поверх ровной петли — катится и густеет без взрыва.",
    positive: {
      shared: [
        "groove builder.",
        "a steady rolling groove that keeps thickening layer by layer.",
        "percussion and bass accumulate over a patient repeating loop.",
        "a thickening mid-set roller with more percussion piling on top."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "function/energy-lift",
    axis: "function",
    label: "Energy lift",
    hint: "Подъём энергии: трек толкает вперёд, барабаны жёстче и ярче, бас плотнее — напор выше предыдущего.",
    positive: {
      shared: [
        "energy lift.",
        "a driving track that pushes the floor a step harder.",
        "insistent drums and a firmer bass carry the groove forward.",
        "forward momentum with brighter, harder percussion."
      ]
    },
    negative: {
      shared: [
        "a cooling, stripped-back track with quiet restrained drums.",
        "a quiet holding pattern that eases the floor back down."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/bridge-track",
    axis: "function",
    label: "Bridge track",
    hint: "Переходный трек: ровный и неприметный, средняя интенсивность, слабые хуки. Честной слуховой приметы у этой роли почти нет.",
    positive: {
      shared: [
        "bridge track.",
        "a plain, even groove with a modest arrangement and small hooks.",
        "steady mid-level drums under a simple repeating bass figure.",
        "unshowy dance music that holds a middle intensity throughout."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "function/tension-builder",
    axis: "function",
    label: "Tension builder",
    hint: "Нагнетание: давление копится и держится долго — фильтр ползёт вверх, гул растёт, разрядка всё не наступает.",
    positive: {
      shared: [
        "tension builder.",
        "a long rising sweep holds pressure over a relentless loop.",
        "an unresolved drone tightens while the drums keep pushing.",
        "the arrangement coils upward and stays wound tight."
      ]
    },
    negative: {
      shared: [
        "a settled, resolved groove that feels relaxed and easy.",
        "a relaxed passage where the harmony comes to rest."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/peak-time",
    axis: "function",
    label: "Peak time",
    hint: "Пик: плотно, громко, напористо, с крупным хуком — максимальное давление на танцпол.",
    positive: {
      shared: [
        "peak time.",
        "a loud, dense club track with hard kicks and bright leads.",
        "a maximal arrangement at full pressure with a big hook.",
        "driving high-intensity dance music aimed at a packed floor."
      ]
    },
    negative: {
      shared: [
        "a quiet, low-intensity track with soft muted drums.",
        "a beatless piece of sustained tones and slow atmosphere."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/reset-track",
    axis: "function",
    label: "Reset track",
    hint: "Сброс: аранжировка раздевается, интенсивность падает, воздух возвращается — чтобы дальше строить заново.",
    positive: {
      shared: [
        "reset track.",
        "a stripped, cooling groove that clears the air.",
        "the arrangement thins out to bare drums and space.",
        "intensity drops to a calm, uncluttered pulse."
      ]
    },
    negative: {
      shared: [
        "a thick, relentless floor track pushing at full force.",
        "a crowded peak-hour arrangement with a giant hook."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/after-hours",
    axis: "function",
    label: "After-hours",
    hint: "Афтерхаус: мутный медленно вращающийся грув, даб-эхо, ровный наркотический пульс — под утро, когда зал редеет.",
    positive: {
      shared: [
        "after-hours.",
        "a murky, slow-turning groove for the last hours before dawn.",
        "dub echoes and a narcotic, unchanging pulse.",
        "stripped, drifting music for a thinning floor at daybreak."
      ]
    },
    negative: {
      shared: [
        "a bright peak-hour anthem for a packed daytime floor.",
        "a big-room festival track with a loud triumphant hook."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/set-closer",
    axis: "function",
    label: "Set closer",
    hint: "Финал: медленно и тепло, крупные эмоциональные аккорды, редкая перкуссия, поющая мелодия — прощание с залом.",
    positive: {
      shared: [
        "set closer.",
        "a slow, warm final track with big emotional chords.",
        "sparse percussion under a long singing melody line.",
        "a farewell tone as the last chords ring out and fade."
      ]
    },
    negative: {
      shared: [
        "a hard, driving peak-hour track that keeps pushing.",
        "an aggressive club workout at maximum pressure."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/dj-tool",
    axis: "function",
    label: "DJ tool",
    hint: "Инструмент сведения: одна повторяющаяся фигура барабанов и баса без песенной формы — ровно, предсказуемо, чтобы мешать поверх.",
    positive: {
      shared: [
        "dj tool.",
        "a functional stripped loop built for mixing.",
        "a single repeating figure of drums and bass running unchanged end to end.",
        "utilitarian club material with an even, predictable arrangement."
      ]
    },
    negative: {
      shared: [
        "a finished song with verses, a chorus and a big hook.",
        "a fully arranged track with a lead melody and clear sections."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/percussion-tool",
    axis: "function",
    label: "Percussion tool",
    hint: "Перкуссионный тул: только барабаны и перкуссия — шейкеры, конги, хэты, сухие удары. Про роль; тембр ударных — на оси Percussion.",
    positive: {
      shared: [
        "percussion tool.",
        "a drums-only loop of shakers, congas and hats.",
        "bare percussion over a plain kick, all rhythm and attack.",
        "an unadorned rhythm layer of skins, shells and metal."
      ],
      clap: [
        "percussion tool.",
        "The sound of a bare drum machine loop with shakers and hats.",
        "A recording of hand drums, rimshots and claps looping alone.",
        "The sound of dry percussion hits repeating over a plain kick."
      ]
    },
    negative: {
      shared: [
        "a melodic arrangement with chords, pads and a lead line.",
        "a full song built around a sung melody."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "function/interlude",
    axis: "function",
    label: "Interlude",
    hint: "Интерлюдия: короткая передышка без бита — дроны, длинные тона, мягкие пэды и медленные наплывы между треками.",
    positive: {
      shared: [
        "interlude.",
        "a short beatless passage of drifting atmosphere.",
        "sustained drones and long held tones fill the space alone.",
        "a quiet stretch of soft pads and slow swells."
      ],
      clap: [
        "interlude.",
        "The sound of a slow atmospheric wash over a still room.",
        "A recording of sustained drones and distant room tone.",
        "The sound of a soft pad swelling and fading into silence."
      ]
    },
    negative: {
      shared: [
        "a driving dance floor track with a steady kick.",
        "a busy club rhythm with a hard, insistent beat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/rominimal",
    axis: "style",
    label: "RoMinimal",
    hint: "Румынский минимал: длинные гипнотические лупы, дабовые хвосты и почти пустая сетка.",
    positive: {
      shared: [
        "rominimal.",
        "rominimal, romanian minimal, hypnotic minimal.",
        "dub techno, hypnotic romanian club scene, long unbroken loop with dubby tails and sparse percussion.",
        "A rominimal track."
      ],
      clap: [
        "RoMinimal.",
        "RoMinimal, Romanian minimal, hypnotic minimal.",
        "Dub techno, hypnotic Romanian club scene, long unbroken loop with dubby tails and sparse percussion.",
        "A RoMinimal track."
      ]
    },
    negative: {
      shared: [
        "tech house, deep tech, punchy peak-time groove.",
        "micro house clicks, glitch edits, busy chopped percussion."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/microhouse",
    axis: "style",
    label: "Microhouse",
    hint: "Микрохаус: мелкая кликовая перкуссия, цифровые щелчки и микромонтаж поверх хаусовой сетки.",
    positive: {
      shared: [
        "microhouse.",
        "micro house, clicks and cuts, glitch house.",
        "glitch electronic, laptop dance music, tiny clipped percussion, digital pops and micro-edited grains.",
        "A microhouse track."
      ]
    },
    negative: {
      shared: [
        "rominimal, dub techno, long hypnotic loop.",
        "tech house, big room house, loud club groove."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/minimal-house",
    axis: "style",
    label: "Minimal House",
    hint: "Минимал-хаус: мало элементов, сухие барабаны, тёплый хаусовый кач и один повторяющийся луп.",
    positive: {
      shared: [
        "minimal house.",
        "minimal house, stripped house, reduced house groove.",
        "warm dry house drums, one repeating bassline, a shaker, a single chord stab, few elements.",
        "A minimal house track."
      ]
    },
    negative: {
      shared: [
        "minimal techno, hard techno, machine techno.",
        "big room house, progressive house, layered chords."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/deep-tech",
    axis: "style",
    label: "Deep Tech",
    hint: "Дип-тек: катящийся сабовый бас, приглушённые аккорды и вокальные обрезки, тёмный функциональный кач.",
    positive: {
      shared: [
        "deep tech.",
        "deep tech, deep tech house, bassy tech house.",
        "tech house, underground club music, rolling sub bassline, muted chords, clipped vocal snippets.",
        "A deep tech track."
      ],
      mulan: [
        "deep tech.",
        "deep tech house, bass house, moody tech house.",
        "tech house, bass-driven club music, dark rolling groove, dubby chords, chopped vocal hooks.",
        "A deep tech house track."
      ]
    },
    negative: {
      shared: [
        "rominimal, micro house, sparse clicking loop.",
        "hard techno, trance, big euphoric breakdown."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/dub-techno",
    axis: "style",
    label: "Dub Techno",
    hint: "Даб-техно: хрипящие аккордовые стабы в длинном эхе, гул низа, почти неподвижная сетка.",
    positive: {
      shared: [
        "dub techno.",
        "dub techno, dubby techno, echo chamber techno.",
        "hypnotic electronic dub, chord stabs soaked in long delay, tape hiss and deep room tone.",
        "A dub techno track."
      ]
    },
    negative: {
      shared: [
        "dub reggae, offbeat skank, live bass and drums.",
        "hard techno, industrial techno, loud driving kick and rave stabs."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/tech-house",
    axis: "style",
    label: "Tech House",
    hint: "Тех-хаус: плотные барабаны, катящийся бас, клубная функциональность.",
    positive: {
      shared: [
        "tech house.",
        "tech house, minimal tech house, groovy house.",
        "house, techno, club, rolling bassline.",
        "A tech house track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/deep-house",
    axis: "style",
    label: "Deep House",
    hint: "Дип-хаус: тёплые аккорды, мягкий свингующий бит, спокойная атмосфера.",
    positive: {
      shared: [
        "deep house.",
        "deep house, soulful house, warm house.",
        "house, warm chords, mellow swung groove.",
        "A deep house track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/jazzy-house",
    axis: "style",
    label: "Jazzy House",
    hint: "Джазовый хаус: живые клавиши и духовые поверх хаусовых барабанов.",
    positive: {
      shared: [
        "jazzy house.",
        "jazz house, nu jazz house, jazz-funk house.",
        "house, jazz chords, live keys, horns.",
        "A jazzy house track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/afro-house",
    axis: "style",
    label: "Afro House",
    hint: "Афро-хаус: ручная перкуссия и чанты поверх ровного грува. Пересекается с Polyrhythm и Chant.",
    positive: {
      shared: [
        "afro house.",
        "afro house, afro tech, tribal house.",
        "house, African percussion, chants, hand drums.",
        "An afro house track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/progressive-house",
    axis: "style",
    label: "Progressive House",
    hint: "Прогрессив-хаус: долгие билды, слои мелодичных синтов, развитие на много минут.",
    positive: {
      shared: [
        "progressive house.",
        "progressive house, melodic house, deep progressive.",
        "melodic techno, long builds, layered synths.",
        "A progressive house track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/acid-house",
    axis: "style",
    label: "Acid House",
    hint: "Эйсид-хаус: визжащая резонансная 303 поверх сырых барабанов драм-машины. Метка Acid 303 на оси Bass — про тембр, а не про трек.",
    positive: {
      shared: [
        "acid house.",
        "acid house, chicago acid, 303 house.",
        "acid, squelchy resonant bassline, raw drum machine.",
        "An acid house track."
      ],
      clap: [
        "Acid house.",
        "Acid house, Chicago acid, 303 house.",
        "Acid, squelchy resonant bassline, raw drum machine.",
        "An acid house track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/electro",
    axis: "style",
    label: "Electro",
    hint: "Электро: 808-грув, синкопированный машинный бит, холодные синты.",
    positive: {
      shared: [
        "electro.",
        "electro, machine funk, Detroit electro.",
        "electro funk, breakdance, 808 drum machine.",
        "An electro track."
      ]
    },
    negative: {
      shared: [
        "four-on-the-floor house, a steady straight kick under a club groove.",
        "breaks, big beat, sampled funk drum break."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/minimal-techno",
    axis: "style",
    label: "Minimal Techno",
    hint: "Минимал-техно: сухая машинная петля, минимум элементов, гипнотика без мелодии.",
    positive: {
      shared: [
        "minimal techno.",
        "minimal techno, stripped techno, hypnotic techno.",
        "loopy after-hours techno, stripped machine groove, dry kick, filtered hats, one repeating blip.",
        "A minimal techno track."
      ]
    },
    negative: {
      shared: [
        "hard techno, industrial techno, distorted kick.",
        "detroit techno, warm strings, soulful chord pads."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/detroit-techno",
    axis: "style",
    label: "Detroit Techno",
    hint: "Детройтское техно: тёплые струнные и джазовые аккорды поверх машинного грува, душевность внутри электроники.",
    positive: {
      shared: [
        "Detroit techno.",
        "Detroit techno, deep techno, hi-tech soul.",
        "techno, hi-tech jazz, warm analog strings, sweeping pads, jazzy seventh chords over a machine groove.",
        "A Detroit techno track."
      ]
    },
    negative: {
      shared: [
        "hard techno, schranz, harsh pounding kick.",
        "minimal techno, dry stripped loop."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/ambient-techno",
    axis: "style",
    label: "Ambient Techno",
    hint: "Эмбиент-техно: мягкие пэды над отдалённым ровным пульсом — техно для слушания, а не для пика.",
    positive: {
      shared: [
        "ambient techno.",
        "ambient techno, atmospheric techno, deep listening techno.",
        "electronic listening music, soft pads, distant muted kick, hazy reverb tails, dubbed-out space.",
        "An ambient techno track."
      ]
    },
    negative: {
      shared: [
        "hard techno, peak time club track, loud distorted kick.",
        "beatless ambient drone, still pad."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/broken-techno",
    axis: "style",
    label: "Broken Techno",
    hint: "Броукен-техно: техно с ломаным электро-битом вместо ровной бочки. Здесь про сцену — сам рисунок на оси Rhythm.",
    positive: {
      shared: [
        "broken techno.",
        "broken techno, electro techno, shuffled machine techno.",
        "electro-leaning club techno, cold synth stabs, dry snapping snares, metallic hats, machine drums.",
        "A broken techno track."
      ]
    },
    negative: {
      shared: [
        "four-on-the-floor techno, straight kick, minimal techno.",
        "broken beat, nu jazz, live jazzy chords over syncopation."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/industrial-techno",
    axis: "style",
    label: "Industrial Techno",
    hint: "Индастриал-техно: перегруженные металлические барабаны, шум и лязг, мрачная тяжесть.",
    positive: {
      shared: [
        "industrial techno.",
        "industrial techno, noise techno, power noise.",
        "industrial, rhythmic noise, distorted metallic drums, clanging steel, harsh machine hiss.",
        "An industrial techno track."
      ]
    },
    negative: {
      shared: [
        "hard techno, clean punchy kick, bright rave stab.",
        "minimal techno, dub techno, soft hypnotic loop."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/hard-techno",
    axis: "style",
    label: "Hard Techno",
    hint: "Хард-техно: колотящая бочка и рейв-стабы, лобовая мощность без индастриал-грязи.",
    positive: {
      shared: [
        "hard techno.",
        "hard techno, schranz, hard groove techno.",
        "rave techno, pounding kick drum, bright rave stabs.",
        "A hard techno track."
      ]
    },
    negative: {
      shared: [
        "minimal techno, sparse hypnotic loop, restrained quiet groove.",
        "industrial techno, noise, corroded distorted texture."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/ebm",
    axis: "style",
    label: "EBM",
    hint: "EBM: жёсткий секвенированный бас, маршевый бит, холодный обработанный вокал.",
    positive: {
      shared: [
        "EBM.",
        "EBM, electronic body music, body music.",
        "industrial dance, new beat, stiff sequenced bassline, marching drum machine, shouted processed vocals.",
        "An EBM track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/idm",
    axis: "style",
    label: "IDM",
    hint: "IDM: изощрённая программация барабанов, странная мелодика, глитчи. Музыка для слушания, а не для пола.",
    positive: {
      shared: [
        "IDM.",
        "IDM, intelligent dance music, braindance.",
        "glitch, home listening electronica, intricate drum programming, detuned melodic synths, crunchy processed percussion.",
        "An IDM track."
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
        "trance.",
        "trance, uplifting trance, progressive trance.",
        "psytrance, rave, euphoric arpeggios, sweeping pads.",
        "A trance track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/breaks",
    axis: "style",
    label: "Breaks",
    hint: "Брейкс: клубная сцена на ломаном бите — nu skool breaks, big beat. Здесь про сцену, сам рисунок брейка — на оси Rhythm.",
    positive: {
      shared: [
        "breaks.",
        "breaks, nu skool breaks, big beat, breakbeat.",
        "florida breaks, progressive breaks, chopped funk drum break.",
        "A breaks track."
      ]
    },
    negative: {
      shared: [
        "drum and bass, jungle, rolling amen break.",
        "four-on-the-floor house, straight techno kick."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/broken-beat",
    axis: "style",
    label: "Broken Beat",
    hint: "Броукен-бит: западнолондонский брук — джазовые аккорды и рваная синкопа. Сам рисунок бита — на оси Rhythm.",
    positive: {
      shared: [
        "broken beat.",
        "broken beat, bruk, west london broken beat.",
        "nu jazz, future jazz, jazzy syncopated club music.",
        "A broken beat track."
      ]
    },
    negative: {
      shared: [
        "breakbeat rave, big beat, chopped funk break.",
        "drum and bass, jungle."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/jungle",
    axis: "style",
    label: "Jungle",
    hint: "Джангл: нарезанные брейки и глубокий саб, регги-влияние и рейвовая сырость.",
    positive: {
      shared: [
        "jungle.",
        "jungle, ragga jungle, breakbeat hardcore.",
        "jungle techno, chopped amen breaks, deep sub bass, ragga vocal samples.",
        "A jungle track."
      ]
    },
    negative: {
      shared: [
        "drum and bass, neurofunk, clean polished modern breakbeat.",
        "big beat, nu skool breaks, blunt chopped funk break."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/drum-and-bass",
    axis: "style",
    label: "Drum & Bass",
    hint: "Драм-энд-бэйс: катящийся брейк и глубокий саб, чистая современная продакшн-сцена.",
    positive: {
      shared: [
        "drum and bass.",
        "drum and bass, liquid funk, neurofunk.",
        "dnb, rolling breakbeat, deep sub bassline, tight snares, reese bass.",
        "A drum and bass track."
      ]
    },
    negative: {
      shared: [
        "jungle, ragga jungle, chopped amen break.",
        "halftime drum and bass, wonky experimental bass."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/halftime-dnb",
    axis: "style",
    label: "Halftime DnB",
    hint: "Халфтайм-днб: сцена нейрофанка и вонки-баса вокруг драм-энд-бэйса. Сам рисунок халфтайма — на оси Rhythm.",
    positive: {
      shared: [
        "halftime drum and bass.",
        "halftime dnb, neurofunk, wonky bass, experimental drum and bass.",
        "dubstep-adjacent drum and bass, autonomic, deep experimental bass scene, dark and spacious.",
        "A halftime drum and bass track."
      ]
    },
    negative: {
      shared: [
        "liquid funk, rolling drum and bass, classic jungle.",
        "four-on-the-floor techno, straight house groove."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/uk-garage",
    axis: "style",
    label: "UK Garage",
    hint: "UK garage: свингующие барабаны, скачущий бас и обрезки вокала; включает speed garage и 4x4. Скиппи-ветка — метка 2-step.",
    positive: {
      shared: [
        "UK garage.",
        "UK garage, UKG, speed garage, garage house.",
        "bassline, swung shuffled drums, pitched vocal chops, organ bass.",
        "A UK garage track."
      ]
    },
    negative: {
      shared: [
        "2-step garage, sparse skippy shuffled garage drums.",
        "deep house, soulful house, smooth warm house chords."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/2-step-garage",
    axis: "style",
    label: "2-Step Garage",
    hint: "2-step: скиппи-ветка UK garage — редкие кик и снейр вразнобой, свинг и порезанный вокал.",
    positive: {
      shared: [
        "2-step garage.",
        "2-step, two step garage, skippy garage.",
        "underground UK dance music, sparse shuffled kick and snare, swung hats, chopped and pitched vocal snippets.",
        "A 2-step garage track."
      ]
    },
    negative: {
      shared: [
        "speed garage, bassline, four-to-the-floor garage house.",
        "drum and bass, jungle, rolling chopped breakbeat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/footwork",
    axis: "style",
    label: "Footwork",
    hint: "Футворк: заикающиеся триольные удары, нарезанный вокал, чикагский рисунок.",
    positive: {
      shared: [
        "footwork.",
        "footwork, juke, ghettotech.",
        "Chicago dance music, stuttering triplet kicks, chopped vocals.",
        "A footwork track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/bass-music",
    axis: "style",
    label: "Bass Music",
    hint: "Bass music: разреженные барабаны, вес и пространство, звук саунд-системы.",
    positive: {
      shared: [
        "bass music.",
        "bass music, dubstep, UK bass.",
        "sound system music, sparse drums, heavy sub weight.",
        "A bass music track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/trip-hop",
    axis: "style",
    label: "Trip Hop",
    hint: "Трип-хоп: пыльные тяжёлые биты, дымная нуарная атмосфера, сэмплы и глухой бас.",
    positive: {
      shared: [
        "trip hop.",
        "trip hop, abstract hip hop, bristol sound.",
        "dusty sampled drums, smoky noir atmosphere, muffled breaks, deep bass, murky sampled strings.",
        "A trip hop track."
      ],
      clap: [
        "Trip hop.",
        "Trip hop, abstract hip hop, Bristol sound.",
        "Dusty sampled drums, smoky noir atmosphere, muffled breaks, deep bass, murky sampled strings.",
        "A trip hop track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/downtempo",
    axis: "style",
    label: "Downtempo",
    hint: "Даунтемпо: расслабленный электронный грув для слушания, а не для танцпола.",
    positive: {
      shared: [
        "downtempo.",
        "downtempo, chillout, lounge.",
        "head-nodding electronic groove, soft rounded drums, warm bass, mellow keys, hazy relaxed atmosphere.",
        "A downtempo track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/ambient",
    axis: "style",
    label: "Ambient",
    hint: "Эмбиент: длинные пэды и медленно меняющаяся текстура, музыка-пространство без клубной пульсации.",
    positive: {
      shared: [
        "ambient.",
        "ambient, ambient music, drone, soundscape.",
        "atmospheric electronic, long sustained pads, gradually evolving texture, deep reverb, still harmonic drift.",
        "An ambient track."
      ]
    },
    negative: {
      shared: [
        "ambient techno, steady kick drum, club beat.",
        "downtempo groove, drums and bassline."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/dub-reggae",
    axis: "style",
    label: "Dub Reggae",
    hint: "Даб-регги: оффбитовый скэнк, эхо, тяжёлый бас, живая ритм-секция и пружинный ревер.",
    positive: {
      shared: [
        "dub reggae.",
        "dub, reggae, roots reggae.",
        "sound system, offbeat skank, heavy bass, spring reverb echo.",
        "A dub reggae track."
      ],
      clap: [
        "Dub reggae.",
        "Dub, reggae, roots reggae.",
        "Sound system, offbeat skank, heavy bass, spring reverb echo.",
        "A dub reggae track."
      ]
    },
    negative: {
      shared: [
        "dub techno, four-on-the-floor techno, machine drums.",
        "trip hop, downtempo, dusty sampled breakbeat."
      ]
    },
    negativeWeight: 0.5
  },
  {
    key: "style/disco",
    axis: "style",
    label: "Disco",
    hint: "Диско: живые струнные, ровная бочка, фанковая гитара, играет настоящая группа.",
    positive: {
      shared: [
        "disco.",
        "disco, nu disco, boogie.",
        "live string section, four-on-the-floor kick, chicken-scratch guitar, congas, seventies dance orchestra.",
        "A disco track."
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
        "funk.",
        "funk, soul, boogie.",
        "live band groove, slap bass, rhythm guitar, horn stabs.",
        "A funk track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/experimental-electronic",
    axis: "style",
    label: "Experimental Electronic",
    hint: "Экспериментальная электроника: звук как композиция, а не как танцевальный инструмент. Соседка Experimental на оси Abstract.",
    positive: {
      shared: [
        "experimental electronic.",
        "experimental electronic, electroacoustic, sound art, avant-garde electronic.",
        "musique concrete, tape music, granular processing, unstable shifting textures, abstract composition.",
        "An experimental electronic track."
      ]
    },
    negativeWeight: 0
  },
  {
    key: "style/cinematic",
    axis: "style",
    label: "Cinematic / Soundtrack",
    hint: "Саундтрек: кинематографично, оркестровое напряжение, музыка под картинку.",
    positive: {
      shared: [
        "film soundtrack.",
        "soundtrack, film score, cinematic.",
        "orchestral film music, dramatic strings and brass.",
        "A cinematic soundtrack track."
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
