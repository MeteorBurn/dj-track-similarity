# Идеи

Эта страница хранит крупные идеи и продуктовые заметки по рабочим процессам.
Часть идей уже может иметь первую реализацию, а следующие расширения остаются
экспериментальными. Это не обещание коммерческого продукта и не research
benchmark; цель страницы — объяснить направление и текущие ограничения.

## Smart Set Builder по seed-трекам

Первая версия Smart Set Builder добавляет вкладку SET, которая генерирует
упорядоченный DJ set preview из `1-5` manual seed-треков или `1-5` случайных,
но связанных auto anchors, выбранных backend при каждом запуске. Цель — не
просто найти "ещё похожие треки", а собрать последовательность для
прослушивания, digging или подготовки сета.

Seed-треки здесь означают треки, выбранные как отправная точка: например, "вот
такой грув", "вот такая темнота", "вот такой break", "вот такая абстрактная
фактура". Auto mode делает то же самое без ручного выбора: система сама
семплирует связанные anchors из треков, у которых есть полный набор нужных
признаков.

## Первая версия без новой модели

Первая версия не обучает новую модель. Она комбинирует уже сохранённые сигналы:

- MERT similarity для музыкальной и аудиальной близости.
- MAEST embeddings для дополнительного audio-model agreement.
- CLAP audio embeddings из сохранённого анализа; текстовый prompt в SET v1 не
  используется.
- Широкий блок SONARA features: rhythm/tempo, dynamics, perception, tonal
  texture, spectral/timbre values и сохранённые summary statistics для больших
  массивов вроде MFCC/chroma.
- Promoted classifier scores, например `abstract_edge`, `break_energy` или
  `voice_presence`, как необязательные target, avoid или mood-curve сигналы.
- BPM/key из file tags, а при их отсутствии SONARA fallback, как мягкий сигнал
  порядка переходов.

MAEST genre labels специально не используются для выбора треков. SET может
использовать MAEST embeddings, но не должен подменять similarity жанровыми
лейблами.

## Как работает auto mode

В auto mode backend не берёт один и тот же фиксированный набор треков навсегда.
Каждый запуск выбирает `1-5` random related anchors из feature-complete треков.
Anchors должны быть связаны между собой и с выбранным режимом, но выбор остаётся
случайным, поэтому повторный запуск может дать другой сет.

После выбора anchors алгоритм строит кандидатный pool по MERT, MAEST, CLAP и
SONARA similarity, применяет mode-specific scoring, diversity, classifier
signals, мягкую совместимость BPM/key и правила артиста. Затем он упорядочивает
preview как DJ-последовательность. API-only поле `random_seed` можно передать
только если нужно воспроизвести конкретный randomized run.

## Режимы

### `similar_crate` (`Similar crate - close`)

Режим близкой подборки. Он держится рядом с seed/anchor зоной и сильнее ценит
согласие MERT, CLAP, MAEST embeddings и SONARA similarity.

Пояснение: это режим "дай мне ящик похожего материала". Он нужен, когда
исходная зона уже правильная и хочется меньше риска.

### `weird_adjacent` (`Weird adjacent - odd`)

Режим странных, но релевантных соседей. Он сохраняет связь с anchors, но
разрешает больше бокового движения по фактуре, classifier signals и model
disagreement.

Пояснение: такой трек может быть не очевидным клоном seed-трека, а полезным
переходом в соседнюю музыкальную область.

### `balanced_set` (`Balanced set - flow`)

DJ-ориентированный режим. Он балансирует similarity, diversity, bridge-треки,
BPM/key переходы, energy curve и ограничения по исполнителям.

Пояснение: здесь важен не только выбор отдельных хороших кандидатов, но и их
порядок. Два трека могут быть хорошими отдельно, но плохо работать рядом из-за
энергии, темпа или слишком похожей фактуры.

### `discovery` (`Discovery - wide`)

Режим более широкого поиска. Он даёт больше novelty/diversity и допускает
рискованные кандидаты, но всё ещё подчиняется anchors и выбранным правилам.

Пояснение: это режим "покажи полезные гипотезы", особенно когда пользователь
ищет новые positives для будущих classifier-профилей.

## UI controls

Текущая вкладка SET подписывает каждую основную настройку:

- `Seed source`: `Manual - selected` использует выбранные seed chips;
  `Auto - random related` каждый запуск выбирает новые связанные anchors.
- `Set mode`: выбирает один из режимов выше.
- `Track limit`: длина preview, по умолчанию `24`; seed/anchor позиции входят
  в этот лимит.
- `Auto anchors`: сколько random related anchors брать в auto mode, `1-5`.
- `Energy curve`: `Balanced - steady`, `Warmup - build`, `Peak - intense` или
  `Wave - rise/fall`.
- `Diversity`: `0.00-1.00`; ниже = ближе к anchors, выше = шире подборка при
  сохранении режима.
- Classifier sliders: `Target boost`, `Avoid cut`, `Curve start`, `Curve end`.
- `Reset sliders`: сбрасывает только `Diversity` и classifier sliders; seed
  source, mode, limit, auto anchors и energy curve не меняются.

## Объяснимый результат

Сгенерированный результат объясняет, почему каждый трек попал в список.
Например:

- `seed_anchor`: manual seed или auto anchor.
- `similar_to_seed`: трек близок к одному или нескольким anchors.
- `bridge`: трек может связывать разные зоны или соседние части списка.
- `weird_adjacent`: трек не очевидно похож, но находится рядом по важным
  признакам.
- `discovery`: трек выбран как более широкая гипотеза.
- `classifier_match`: трек выбран из-за совпадения с promoted classifier.
- `mood_shift`: трек помогает двигать classifier или energy curve.

Preview также показывает model scores, SONARA group scores, classifier scores и
transition metadata. Это нужно, чтобы пользователь мог быстро понять причину
выбора, оставить трек, удалить его или отправить на дальнейшую разметку.

Ограничение по исполнителям строгое: один известный исполнитель может появиться
в одном SET preview максимум один раз. Manual seeds остаются отмеченными как
`seed_anchor`, но повтор известного исполнителя среди manual seeds отклоняется.

## API shape

Текущий endpoint:

```text
POST /api/set-builder/generate
```

Поля входа:

- `seed_mode`: `manual` или `auto`.
- `seed_track_ids`: `1-5` manual seed IDs.
- `auto_seed_count`: `1-5` anchors для auto mode.
- `limit`: длина preview.
- `mode`: `similar_crate`, `weird_adjacent`, `balanced_set` или `discovery`.
- `diversity`: насколько сильно разрешено отходить от anchor зоны.
- `energy_curve`: `warmup`, `balanced`, `peak` или `wave`.
- `classifier_targets`: какие promoted classifier scores считать желательными.
- `classifier_avoid`: какие promoted classifier scores считать нежелательными.
- `classifier_curves`: start/end target intensity для promoted classifiers.
- `random_seed`: необязательное API-only поле для воспроизведения одного
  randomized run.

Поля выхода:

- ordered track rows;
- selection reason;
- similarity, SONARA group, transition, classifier и diversity scores;
- relevant classifier scores;
- transition metadata для порядка сета.

## Возможные расширения позже

После первой версии можно добавить:

- отправку выбранных треков в Rhythm Lab;
- отметку кандидатов как reviewed;
- экспорт XLSX lists;
- исключение уже reviewed/exported кандидатов;
- сохранение sessions генерации;
- iterative active-learning workflow, где пользователь слушает кандидатов,
  размечает удачные и постепенно улучшает promoted classifiers.

Пояснение: это превращает генератор списков в рабочий цикл. Сначала система
предлагает кандидатов, потом пользователь проверяет их, а затем эти решения
становятся данными для следующих classifier-профилей и будущих подборок.
