# Поиск и запись тегов

Эта страница описывает search tabs, поверхность classifier filtering и явный
workflow записи genre tags. Используйте ее, когда библиотека уже просканирована
и нужно найти полезных соседей, собрать временный сет или решить, стоит ли
сохранять MAEST genres обратно в файлы.

## Режимы поиска

Search panel имеет отдельные tabs.

Выбирайте tab по намерению:

| Tab | Что делает | Когда использовать |
| --- | --- | --- |
| SONARA | Ищет по объяснимым playlist features и custom mixer weights. | Нужны DJ-transition candidates и контроль rhythm, tempo, timbre, dynamics или harmonic balance. |
| MERT | Ищет от выбранных seed tracks в MERT embedding space. | Нужна audio-model similarity без настройки feature weights. |
| CLAP | Ищет CLAP audio embeddings по text prompt. | Вы знаете нужный sound или mood, но seed track нет. |
| CLASS | Фильтрует по promoted classifier scores. | Нужен переиспользуемый personal signal, обученный в Rhythm Lab. |

Library browser также имеет preset filter `syncopated`. Он выбирает tracks, у
которых сохраненная MAEST metadata содержит `maest_syncopated_rhythm = true`, и
может комбинироваться с обычным library text search и workflow
add-filtered-tracks.

CLASS tab содержит classifier controls, найденные из promoted
`models/classifiers/*/model.json` metadata. Каждый promoted classifier можно
проанализировать из UI, а его slider фильтрует library и add-filtered-tracks
workflow по `track_classifier_scores.score`.

### SONARA search

SONARA - основной explainable seed-search path. Он отправляет selected seed
tracks, optional lookback tracks, limit, minimum similarity, mixer weights и
modifiers в `/api/search/sonara`.

Mixer weights:

- `timbre`
- `rhythm`
- `dynamics`
- `harmonic`
- `tempo`

Modifiers:

- `energy`
- `valence`
- `acousticness`
- `brightness`
- `rhythm_density`
- `dynamic_range`
- `loudness`

Backend все еще принимает preset mode names для compatibility:

```text
balanced, vibe, sound, dj_transition, custom
```

Active UI path использует custom mixer.

Начинайте с SONARA, когда нужны explainable results. Увеличивайте или
уменьшайте mixer weights, чтобы сдвигать поиск к transition fit, rhythmic feel,
harmonic similarity или overall sound.

### MERT search

MERT seed search отправляет seed tracks, lookback tracks, limit и optional
minimum similarity в `/api/search`. Он ранжирует tracks в MERT embedding space.

Используйте MERT после `dj-sim analyze --adapter mert` или соответствующей UI
analysis job. Если results пустые или устарели, проверьте, есть ли у candidate
tracks MERT embeddings.

### CLAP text search

CLAP text search отправляет text prompt, limit, optional minimum similarity и
device в `/api/search/text`. Он ранжирует CLAP audio vectors относительно CLAP
text vector.

Concrete English prompts обычно работают лучше:

```text
Melancholic minimal house with broken drums, warm chords, no vocals
Dark hypnotic techno with sparse percussion and deep rolling bass
Organic microhouse with soft pads, plucked textures, and spacious mood
```

Используйте CLAP для exploratory digging. Включайте в prompt musical texture,
mood, tempo feel, vocal presence или instrumentation вместо reliance только на
genre name.

### CLASS / classifiers

CLASS tab предназначен для classifier-driven workflows, а не similarity search.
Он показывает promoted classifiers, найденные из
`models/classifiers/*/model.json`:

- `Analyze <classifier>` запускает cancellable classifier job.
- Каждый classifier slider фильтрует library server-side по stored classifier
  score.
- Metadata dialog показывает classifier scores, confidence, label, feature set
  и model file ниже SONARA features.

Promoted classifiers требуют promoted model file и feature-complete tracks. Они
не анализируют аудио напрямую; сначала запустите SONARA, MERT и MAEST для
треков, которые нужно оценить.

Используйте CLASS filters после scoring promoted classifier. High score
означает, что model считает track соответствующим positive label профиля; это
workflow hint, а не гарантия.

## Запись тегов

MAEST genre saving пишет одну нормализованную semicolon-separated genre string,
например:

```text
Tech House; Minimal; Techno
```

MAEST category prefixes вроде `Electronic---` удаляются перед записью.

Format-specific genre fields:

- MP3, WAV, AIFF ID3 tags: `TCON`
- FLAC и Vorbis-style tags: `GENRE`
- MP4, M4A, ALAC: `©gen`

WAV genre writing использует Mutagen `WAVE` support, сохраняет значение `TCON`
и проверяет, что сохраненное значение читается после записи. Он не запускает
custom RIFF repair step. Если WAV write или readback fails, этот track
помечается failed, а batch продолжается.

Используйте tag writing только после проверки MAEST labels в приложении. Он
предназначен для сохранения generated genre labels в стандартное поле genre; это
не general metadata editor, и его не нужно использовать для изменения title,
artist, album, BPM, key или custom tags.

