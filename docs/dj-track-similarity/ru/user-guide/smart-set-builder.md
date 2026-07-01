# Smart Set Builder

> Audience: Диджеи, которые готовят упорядоченный маршрут прослушивания.
> Goal: Понять SET preview и настройки, которые на него влияют.
> Type: how-to

Smart Set Builder создаёт preview, а не готовый сет. Сначала используйте его как упорядоченный shortlist, затем слушайте, удаляйте лишнее и добавляйте preview в current set только явным действием.

## Требования

Лучший маршрут требует сохранённых MERT, MAEST и CLAP audio embeddings плюс SONARA features. Smart Set может использовать MAEST embeddings, но не выбирает треки по MAEST genre labels.

## Seed source и Set mode

- Manual seeds подходят, когда у вас уже есть 1-5 anchor tracks. Это удобно для конкретного звука, лейбла, тайм-слота или перехода. Если у ручных seeds совпадает известный artist, preview отклоняется, чтобы не начинать с однообразного маршрута.
- Auto seeds подходят, когда хочется исследовать feature-complete library. Auto mode выбирает первый anchor из анализированных треков, а остальные waypoint anchors берёт из связанных кандидатов.
- Similar-crate режим держит маршрут ближе к anchors. Более balanced режим помогает пройти через совместимые соседние зоны, а не застрять в одной узкой группе.

## Размер, энергия и темп

- `Track limit` задаёт длину preview. Сначала держите его небольшим, затем увеличивайте, когда маршрут уже звучит цельно.
- `Auto anchors` расширяет auto route через дополнительные waypoint anchors; слишком большое значение может сделать маршрут менее сфокусированным.
- `Energy curve` задаёт общий подъём, спад или ровную линию энергии.
- `Diversity` отталкивает результаты от почти одинаковых треков. Увеличивайте его, если список слишком однообразный; уменьшайте, если нужен плотный crate.
- `BPM mode = general` оставляет обычную transition compatibility, включая half/double tempo matching.
- `BPM mode = low_to_high` или `high_to_low` добавляет реальную BPM-траекторию. `BPM change` задаёт скорость подъёма или спуска.
- `Start BPM` и `Target BPM` можно оставить пустыми: приложение выведет их из первого seed/anchor и диапазона библиотеки. Заполняйте их только для конкретного tempo plan.

## Classifier sliders

Promoted classifiers — необязательные taste modifiers. `Target boost` поднимает треки, похожие на положительный сигнал; `Avoid cut` помогает избегать нежелательного класса; curve controls задают, где по маршруту classifier важнее. Missing classifier scores остаются нейтральными.

`Reset sliders` возвращает настройки к базе, чтобы менять по одному параметру и слышать эффект.

## Защита от повторов

Artist guard оставляет не больше одного трека с известным artist в одном preview.
