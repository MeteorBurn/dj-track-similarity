# UI language and label glossary

The browser interface mixes Russian and English. It grew that way over the course of development
rather than by design, so which label reads in which language is not a rule you can predict, and it
is expected to keep moving. This documentation is English throughout and names every control by its
English name. Use the tables below to find the on-screen string for any control a page mentions.

The Russian column is the exact text rendered in the interface. Where the string appears only as a
hover title or an accessible name, the Where column says so. The next section lists the parts of
the interface that are already English, where the page and the screen agree without translation.

## What stays in English

The interface keeps these tokens in English, so the documentation and the screen agree on them
without translation:

- model and family names: `SONARA`, `MAEST`, `MERT`, `MuQ`, `MuQ-MuLan`, `CLAP`
- tab labels: `LAB`, `SONARA`, `SIMILARITY`, `PROMPT`, `CLASS`
- SONARA search modes: `Balanced`, `Vibe`, `Sound`, `DJ transition`, `Custom mixer`
- analysis mode buttons: `Direct`, `Staged`
- numeric field labels: `Limit`, `Mode`, `Model`, `Device`, `Track batch`, `Inference batch`,
  `BatchSize`, `StageSize`, `Processes`, `Threads`, `Workers`
- SONARA mixer sliders: `Timbre`, `Rhythm`, `Dynamics`, `Harmonic`, `Tempo`
- SONARA modifier sliders: `Energy`, `Valence`, `Acoustic`, `Bright`, `Density`, `Range`, `LUFS`,
  `Vocal`, `Aggression`
- action buttons that carry no Russian text: `Reset`, `Prev`, `Next`, `LIKE`, `FTS`,
  `Add Random Track`, `Collection`, `M3U`, `CSV`
- the track detail dialog section titles: `Track Details`, `Tags`, `File scan (Mutagen)`, `SONARA`,
  `Embedding analyses`, `Classifier analyses`

## Panel headings

The workspace is three columns. Each carries a numbered heading.

| Russian | English meaning | Where |
| --- | --- | --- |
| `1. База и анализ` | Database and analysis | Left column heading |
| `2. Библиотека и прослушивание` | Library and listening | Middle column heading |
| `3. Поиск и прослушивание` | Search and listening | Right column heading |

## Top bar

Six controls sit to the right of the title. All six are icon-only, so the Russian string appears as
a hover title and as the accessible name.

| Russian | English meaning | Icon |
| --- | --- | --- |
| `Открыть HTML документацию` | Open the HTML documentation | Title link "DJ Track Similarity" |
| `Переключить тему` | Toggle the theme | Sun or moon |
| `Открыть лог` | Open the log | Scroll |
| `Запустить Rhythm Lab` / `Открыть Rhythm Lab` | Start Rhythm Lab / Open Rhythm Lab | Flask |
| `Остановить все серверы и закрыть вкладку` | Stop every server and close the tab | Power |
| `Остановить текущий scan или анализ` | Stop the current scan or analysis | Square |

The flask title changes with the Rhythm Lab process state. `Запустить` appears when no process is
running, `Открыть` when one is.

A status line follows the buttons. It reports whichever stage is running, and falls back to the
idle text when none is:

| Russian | English meaning | When |
| --- | --- | --- |
| `Готово к работе` | Ready | Nothing is running |
| `Идет сканирование` | Scanning | A scan is queued or running |
| `Прогрев моделей` | Model warm-up | Analysis is loading model weights, before any track is decoded |
| `Идет анализ` | Analysing | An analysis job is queued or running |
| `Идет запись жанров` | Writing genres | The genre tag job is queued or running |
| `Этап остановлен` | Stage stopped | The stage was cancelled |
| `Процесс не запущен` | No process running | The process box has no active job |

After the backend accepts a shutdown, the whole page is replaced by one titled `Серверы
остановлены` (the servers are stopped), which adds that the tab can be closed by hand when the
browser did not close it.

## Panel 1, database and analysis

The panel opens with the database path row, then three stage cards that share one selection:
**DATABASE**, **SONARA**, and **ML models**. Checking one clears the other two. Below the cards sits
one settings button per stage, a standalone row of four maintenance icons, the shared **Track
limit** stepper, and the single **Start** button that runs whichever stage is checked.

### Database path row

| Russian | English meaning | Where |
| --- | --- | --- |
| `Выберите SQLite базу` | Choose a SQLite database | Placeholder in the path field |
| `Выбрать SQLite базу` | Choose a SQLite database | Database picker button |

### DATABASE stage card

| Russian | English meaning | Where |
| --- | --- | --- |
| `Загружает новые треки из выбранной папки в базу.` | Loads new tracks from the selected folder into the database | Description on the DATABASE row |
| `Очистить базу` | Clear the database | Trash button on the DATABASE row |
| `Настройки загрузки треков в базу` | Track import settings | Button under the DATABASE row, opens the [track import dialog](#scan-dialog) |
| `Открыть параметры загрузки треков в базу` | Open the track import parameters | Title of the settings button above |

The DATABASE checkbox is never disabled by track count; it stays available even on an empty
library. Its live count is the number of tracks already loaded.

### Library tools row

A standalone row of four icon buttons sits below the DATABASE card's settings button. None of them
belong to the stage selection; each stays disabled until the library holds at least one track (the
picker and settings button above are the only DATABASE-card controls that ignore that rule).

| Russian | English meaning | Where |
| --- | --- | --- |
| `Обновить теги` | Refresh tags | Refresh button |
| `Сохранить жанры` | Save genres | Writes MAEST genres to files |
| `Проверить базу` | Validate the database | Shield button |
| `Найти и разобрать дубликаты` | Find and review duplicates | Opens Audio Dedup |

### Analysis cards

| Russian | English meaning | Where |
| --- | --- | --- |
| `Анализ` | Analysis | Section heading above the SONARA and ML models cards |
| `Один запуск обработает выбранную стадию и пропустит уже готовые результаты` | One run processes the selected stage and skips finished results | Note under the heading |
| `ML-модели` | ML models | Heading of the ML models card |
| `Выберите нужные способы анализа звучания` | Choose the sound analysis you need | Note under the ML heading |
| `Сбросить SONARA` | Reset SONARA | Trash button on the SONARA row |
| `Сбросить MAEST` and the same form for MERT, MUQ, MULAN, CLAP | Reset that family | Trash button on each model row |
| `Настройки анализа SONARA` | SONARA analysis settings | Button on the SONARA card, opens the [SONARA settings dialog](#sonara-settings-dialog) |
| `Открыть параметры анализа SONARA` | Open the SONARA analysis parameters | Title of the settings button above |
| `Настройки анализа ML моделями` | ML models analysis settings | Button on the ML models card, opens the [ML analysis settings dialog](#ml-analysis-settings-dialog) |
| `Открыть параметры анализа ML-моделей` | Open the ML models analysis parameters | Title of the settings button above |
| `Читать исходные аудиофайлы напрямую` | Read the source audio files directly | Title of the `Direct` button inside the ML analysis settings dialog, and of the same toggle inside the SONARA settings dialog |
| `Копировать входные файлы во временную SSD-папку` | Copy input files into a temporary SSD folder | Title of the `Staged` button inside the ML analysis settings dialog, and of the same toggle inside the SONARA settings dialog |
| `Папка для временных staging-копий ML` | Folder for temporary ML staging copies | ML staging path field, ML analysis settings dialog |
| `Choose Folder для ML staging-копий` | Choose a folder for the ML staging copies | ML folder picker, ML analysis settings dialog |

The SONARA checkbox is disabled while the library holds zero tracks. Each ML model checkbox stays
disabled until the library holds at least one SONARA row. Neither disabled state carries its own
message, because the checkbox is simply unclickable, so there is no notice to translate.

SONARA's own staging-folder field and picker (`Папка для временных staging-копий SONARA` and
`Choose Folder для staging-копий`) moved out of this panel into the
[SONARA settings dialog](#sonara-settings-dialog) below. The ML card's own Device, Mode, staging
folder, and batch-size controls moved out of this panel the same way, into the
[ML analysis settings dialog](#ml-analysis-settings-dialog) below.

### Track limit and Start

| Russian | English meaning | Where |
| --- | --- | --- |
| `Лимит треков` | Track limit | Stepper label below the three stage cards |
| `0 = все треки; применяется отдельно к каждой стадии анализа` | 0 means every track, applied per analysis stage | Note under `Лимит треков` |
| `Укажите папку с треками в настройках загрузки.` | Set a source folder in the import settings | Warning shown above `Старт` when DATABASE is checked but the track import settings carry no folder yet |
| `Старт` | Start | The single button at the bottom of the panel that runs the checked stage |
| `Запустить отмеченную стадию` | Run the selected stage | Title of the `Старт` button |

One numeric stepper now backs all three stages: it caps the scan when DATABASE runs, and it caps
each analysis family the same way it always did when SONARA or an ML model runs. `Старт` replaces
the former `Analyze` button. Its tooltip no longer names SONARA and ML, because it can just as well
start a scan.

On page load, and whenever the library becomes empty, such as right after **Clear the
database**, the stage selection snaps back to DATABASE. If the library has tracks but no SONARA
row, it snaps to SONARA instead.

The model rows carry one-line Russian descriptions:

| Model | Russian description | English meaning |
| --- | --- | --- |
| SONARA | `Считает темп, тональность, ритм, динамику, тембр и структуру трека.` | Computes tempo, key, rhythm, dynamics, timbre, and structure |
| MAEST | `Помогает понять жанровый характер трека.` | Helps read the genre character of a track |
| MERT | `Ищет похожее звучание от выбранного seed-трека.` | Finds similar sound from a chosen seed track |
| MUQ | `Сохраняет дополнительный слой аудио-признаков.` | Stores an additional layer of audio features |
| MULAN | `Связывает текстовое описание с отдельными аудио-эмбеддингами.` | Links a text description to its own audio embeddings |
| CLAP | `Связывает текстовое описание с аудио-звучанием.` | Links a text description to audio sound |

## Panel 2, library and listening

| Russian | English meaning | Where |
| --- | --- | --- |
| `Общее количество треков в библиотеке` | Total tracks in the library | Title of the `tracks` badge |
| `Пагинация библиотеки` | Library pagination | Group label around `Prev` and `Next` |
| `Предыдущая страница библиотеки` | Previous library page | `Prev` title |
| `Следующая страница библиотеки` | Next library page | `Next` title |
| `Текущая страница / всего страниц` | Current page over total pages | Page counter title |
| `Диапазон треков на текущей странице` | Track range on the current page | Range readout title |
| `Общее число треков в текущей выборке` | Total tracks in the current selection | Filtered total title |
| `Показать список лайкнутых треков` | Show the liked tracks | Heart button |
| `Показать только треки с сохранённым MAEST-флагом syncopated rhythm` | Show only tracks with the stored MAEST syncopated-rhythm flag | Waveform button |
| `Включить случайный порядок воспроизведения на текущей странице` | Shuffle playback order on the current page | Shuffle button |
| `Показать загруженные треки в обратном порядке` | Reverse the loaded tracks | Sort direction button |
| `Добавить треки текущей страницы в сет. Уже добавленные треки будут пропущены.` | Add the current page to the set, skipping tracks already in it | Plus button |
| `Выберите SQLite базу данных.` | Choose a SQLite database | Empty state with no database |
| `В текущем запросе треков нет.` | No tracks match the current query | Empty state with a database |

Row actions repeat for every track:

| Russian | English meaning |
| --- | --- |
| `Лайкнуть` / `Убрать лайк` | Like / remove the like |
| `Теги и жанры` | Tags and genres, opens the track detail dialog |
| `В сет` / `Убрать из сета` | Add to the set / remove from the set |
| `Перемотать preview` | Seek the preview |

The library search box uses the English placeholder `path, title, artist, genre` with the `LIKE` and
`FTS` mode buttons beside it.

## Panel 3, search and listening

The five tabs render in this order: `LAB`, `SONARA`, `SIMILARITY`, `PROMPT`, `CLASS`. The internal
key for `PROMPT` is still `text`, so the API path stays `/api/search/text`.

| Russian | English meaning | Where |
| --- | --- | --- |
| `Убрать seed: <track>` | Remove that seed | Seed chip |
| `Сбросить SONARA mixer и modifiers` | Reset the SONARA mixer and modifiers | `Reset` button in the SONARA tab |
| `— приоритизирует виды сходства.` | Prioritizes kinds of similarity | Note beside `Mixer` |
| `— направляют характер выдачи.` | Steers the character of the results | Note beside `Modifiers` |
| `Добавить случайный SONARA-ready трек из базы в seed` | Add a random SONARA-ready track as a seed | SONARA tab random button |
| `Найти похожие треки через SONARA по выбранным seed-трекам` | Find similar tracks with SONARA from the chosen seeds | SONARA search button |
| `Найти треки через <model> по текстовому описанию звучания.` | Find tracks with that model from a written sound description | PROMPT search button when embeddings exist |
| `Запустите анализ <model> для библиотеки, затем повторите текстовый поиск.` | Run that model over the library, then search again | PROMPT search button with no stored embeddings |
| `Удалить рассчитанные данные <profile>` | Delete the calculated data for that profile | CLASS reset button |

The SIMILARITY tab keeps English throughout: `Add Random Track`, `Model`, `Limit`, and the model
options `MAEST`, `MERT`, `MuQ`, `MuQ-MuLan`.

### PROMPT tab

| Russian | English meaning | Where |
| --- | --- | --- |
| `Выбрать пресеты по осям. Несколько пресетов складываются в один банк.` | Pick presets by axis, several presets merge into one bank | Preset picker button |
| `<n> выбрано` / `не выбрано` | n selected / none selected | Preset counter |
| `Убрать все пресеты и очистить банк` | Clear every preset and empty the bank | Clear button |
| `Ось измерена на <model> — модель переключится сама.` | The axis was measured on that model, so the model switches by itself | Axis note |
| `Замера у оси нет — модель останется прежней. Проверяй ушами.` | The axis has no measurement, the model stays, check by ear | Axis note |
| `Переключить на <model>` | Switch to that model | Model advice button |
| `Модель` | Model | Evidence block key |
| `Замер` | Measurement | Evidence block key |
| `Без замера` | Unmeasured | Evidence block key |
| `Надёжность метки на размеченных примерах: ROC-AUC <value>.` | Label reliability on the labelled examples, ROC-AUC value | Measured chip |
| `Сколько непустых строк уйдёт в банк. Строки усредняются в один вектор.` | How many non-empty lines enter the bank, averaged into one vector | Line counter |
| `Применять Negative как hard-negative запросы.` | Apply the Negative field as hard-negative queries | Negatives toggle |
| `выключены` | disabled | Negative state readout |
| `<model> загружается — первый поиск не будет ждать веса.` | That model is loading, so the first search will not wait for weights | Warmup banner |
| `Прогреть <model> не удалось — веса загрузит сам поиск.` | Warming that model up failed, so the search itself will load the weights | Warmup banner after a failure |
| `По делу: трек соответствует выбранным пресетам.` | On point, the track matches the chosen presets | Thumbs-up title on a result row |
| `Мимо: трек не соответствует выбранным пресетам.` | Off target, the track does not match the chosen presets | Thumbs-down title on a result row |

Both feedback titles continue with the same sentence: the verdict is written to the database and
feeds the preset tuner, and clicking again clears it.

The `Prompt bank`, `Negative`, `Model`, and `Limit` field labels stay English.

### Current set and export

| Russian | English meaning | Where |
| --- | --- | --- |
| `Сет и экспорт` | Set and export | Collapsed disclosure heading |
| `Развернуть или свернуть текущий сет и экспорт` | Expand or collapse the current set and export | Disclosure title |
| `Сет пуст` | The set is empty | Empty state |
| `Экспорт сохранит текущий сет` | Export saves the current set | Note when the set has entries |
| `Пагинация сета` | Set pagination | Group label |
| `Предыдущая страница сета` / `Следующая страница сета` | Previous / next set page | `Prev` and `Next` |
| `Убрать из сета` | Remove from the set | Trash button on a set row |
| `Выбрать папку экспорта` | Choose the export folder | Folder picker |
| `Сохранить текущий сет в Rhythm Lab Collection` | Save the current set as a Rhythm Lab collection | `Collection` button |
| `Экспортировать текущий сет в M3U` | Export the current set as M3U | `M3U` button |
| `Экспортировать текущий сет в CSV` | Export the current set as CSV | `CSV` button |

## Scan dialog

The dialog opens from `Настройки загрузки треков в базу` on the DATABASE card. It only edits
settings now. It does not start a scan itself.

| Russian | English meaning | Where |
| --- | --- | --- |
| `Настройка параметров загрузки треков в базу` | Track import settings | Dialog title |
| `Форматы и длительность решают, что попадёт в базу.` | Formats and duration decide what enters the database | Subtitle |
| `Форматы файлов` | File formats | Section heading |
| `<n> из 14` | n of 14 | Selected format counter |
| `Включить <format>` / `Исключить <format>` | Include / exclude that format | Format badge title |
| `Границы отбора` | Selection bounds | Section heading |
| `Min, сек` / `Max, сек` | Minimum / maximum seconds | Duration fields |
| `Папка с треками` | Music folder | Section heading |
| `Выберите папку как источник для загрузки треков в базу: сканирование папок выполняется рекурсивно.` | Choose the source folder, scanning is recursive | Description |
| `Папка не выбрана` | No folder selected | Placeholder |
| `Выбрать папку на сервере` | Choose a folder on the server | Folder picker |
| `Закрыть` | Close | Title of the `X` button and of the footer `OK` button |

There is no longer a `Scan limit` stepper in this dialog, and no validation on its `OK` button. `OK`
just closes the dialog and keeps whatever is set. The shared `Лимит треков` (Track limit) stepper on
the main panel covers the scan too, once DATABASE is checked and `Старт` is pressed. Pressing
`Старт` with DATABASE checked closes this dialog if it is open and hands off to three more strings. A
centered toast reads `Подготавливаем список треков…` (preparing the track list). The status line
reads `Сканирование директории` (scanning the directory), and changes to `Загрузка треков в базу`
(loading tracks into the database) once the API returns the scan job.

This dialog no longer carries a BPM-range section. SONARA's BPM range moved to the
[SONARA settings dialog](#sonara-settings-dialog) below.

Every setting in this dialog except the folder persists in browser storage under
`dj-track-similarity.scan-import-settings`. The folder follows the same per-session rule as the
SONARA and ML staging folders: it is never restored from storage, so every session asks for it
again.

## SONARA settings dialog

The dialog opens from `Настройки анализа SONARA` on the SONARA card.

| Russian | English meaning | Where |
| --- | --- | --- |
| `Настройки анализа SONARA` | SONARA analysis settings | Dialog title |
| `Режим чтения файлов и диапазон BPM решают, как проходит нативный анализ SONARA.` | The file-reading mode and BPM range decide how native SONARA analysis runs | Subtitle |
| `Диапазон BPM для анализа SONARA` | BPM range for SONARA analysis | First section heading |
| `Диапазон BPM определяет, в каких пределах SONARA ищет темп трека. Правильный диапазон помогает избежать ошибок вроде 64 вместо 128 BPM. Для большинства библиотек подойдут готовые диапазоны Rekordbox, VirtualDJ или Mixed In Key, при необходимости можно задать свой.` | The BPM range bounds the tempo SONARA searches for. The right range avoids errors like 64 instead of 128 BPM. Rekordbox, VirtualDJ, or Mixed In Key fit most libraries; set your own when they do not | Description under the BPM heading |
| `Свой диапазон` | Custom range | Shown when no preset matches |
| `Пресеты диапазона BPM` | BPM range presets | Group label over Rekordbox, VirtualDJ, Mixed In Key |
| `Выберите пресет или введите свой диапазон. Задаётся один раз: первый анализ SONARA закрепит его за всей базой. Верхняя граница должна быть минимум вдвое больше нижней.` | Pick a preset or type your own range. It is set once, the first SONARA analysis locks it for the whole database, and the upper bound must be at least twice the lower | Hint below the BPM controls, unlocked |
| `База уже проанализирована этим диапазоном. Чтобы задать другой, сбросьте анализ SONARA.` | The database was analysed with this range. Reset SONARA analysis to change it | Hint below the BPM controls, locked |
| `Режим анализа` | Analysis mode | Second section heading |
| `Direct — треки декодируются и анализируются прямо с исходного диска. Staged ускоряет анализ за счёт временного копирования треков на более быстрый накопитель и обработки уже с него. Для Staged рекомендуется выбрать директорию на самом быстром доступном накопителе, желательно SSD. Это особенно полезно для библиотек, где исходный диск не успевает за скоростью анализа.` | Direct decodes and analyses tracks straight from the source disk. Staged speeds analysis up by temporarily copying tracks to a faster drive and processing them from there; pick the fastest available drive, ideally an SSD, which helps most when the source disk cannot keep up | Description under the mode heading |
| `Папка для временных staging-копий SONARA` | Folder for temporary SONARA staging copies | Staging path field, Staged mode only |
| `Choose Folder для staging-копий` | Choose a folder for the staging copies | SONARA folder picker |
| `Закрыть` | Close | Title of the `X` button and the footer `OK` button |

## ML analysis settings dialog

The dialog opens from `Настройки анализа ML моделями` on the ML models card. It mirrors the SONARA
settings dialog's pattern but adds a third section. Device comes first, because SONARA runs on CPU
only and has no device choice of its own. Analysis mode comes second, and batch sizes come third.

| Russian | English meaning | Where |
| --- | --- | --- |
| `Настройки анализа ML моделями` | ML models analysis settings | Dialog title |
| `Device и режим чтения файлов решают, как MAEST, MERT, MuQ, MuLan и CLAP считают эмбеддинги.` | Device and the file-reading mode decide how MAEST, MERT, MuQ, MuLan, and CLAP compute embeddings | Subtitle |
| `Устройство` | Device | First section heading |
| `Устройство, на котором MAEST, MERT, MuQ, MuLan и CLAP считают эмбеддинги. AUTO выберет CUDA, если PyTorch видит GPU, иначе CPU. У SONARA такого выбора нет — это нативный Rust-анализ признаков, который всегда идёт на CPU.` | The device MAEST, MERT, MuQ, MuLan, and CLAP use to compute embeddings. AUTO picks CUDA when PyTorch sees a GPU, otherwise CPU. SONARA has no such choice. It is a native Rust feature analysis that always runs on CPU | Description under the Device heading |
| `Режим анализа` | Analysis mode | Second section heading |
| `Direct — треки декодируются и передаются в ML-модели прямо с исходного диска. Staged ускоряет анализ за счёт временного копирования треков партиями на более быстрый накопитель и обработки уже с него; в отличие от SONARA здесь нет отдельных Processes/Threads — копированием партий управляет один параметр Workers, а инференс сразу проходит по всем выбранным моделям. Для Staged рекомендуется выбрать директорию на самом быстром доступном накопителе, желательно SSD.` | Direct reads tracks straight off the source disk and feeds them to the ML models. Staged copies tracks onto a faster drive first and analyzes them from there, in batches. Batch copying here uses a single Workers parameter, not SONARA's separate Processes and Threads. Inference always covers every selected model at once. For Staged, pick a directory on the fastest available drive, ideally an SSD | Description under the Analysis mode heading |
| `Папка для временных staging-копий ML` | Folder for temporary ML staging copies | Staging path field, Staged mode only |
| `Choose Folder для ML staging-копий` | Choose a folder for the ML staging copies | ML folder picker |
| `Размер батчей` | Batch sizes | Third section heading |
| `Track batch — сколько треков декодировать и держать в памяти за один job batch. Тип: целое число 1-64. Измеренный дефолт для этой машины: 8. Inference batch — сколько окон или семплов MAEST, MERT, MuQ и CLAP прогоняют за один forward pass модели. Тип: целое число 1-128. Измеренный дефолт для RTX 3090: 16. Оба параметра действуют одинаково в режимах Direct и Staged.` | Track batch is how many tracks to decode and hold in memory per job batch. Type: integer 1-64. Measured default for this machine: 8. Inference batch is how many windows or samples MAEST, MERT, MuQ, and CLAP run through in one model forward pass. Type: integer 1-128. Measured default for an RTX 3090: 16. Both parameters work the same way in Direct and Staged mode | Description under the Batch sizes heading |
| `Закрыть` | Close | Title of the `X` button and the footer `OK` button |

Track batch and Inference batch stay disabled until the library holds at least one track. Device,
Mode, and the staging controls stay adjustable regardless, the same way they did in panel 1 before
this dialog existed.

## Track detail dialog

This dialog opens from the tag button on any row. Its section titles are English while its actions
and empty states are Russian.

| Russian | English meaning | Where |
| --- | --- | --- |
| `Теги и анализ трека` | Track tags and analysis | Dialog accessible name |
| `Удалить из базы` | Delete from the database | Trash button in the header |
| `Core данные ещё не рассчитаны` | Core data has not been calculated yet | SONARA empty state |
| `Classifier scores ещё не рассчитаны` | Classifier scores have not been calculated yet | Classifier empty state |
| `SONARA features ещё не рассчитаны` | SONARA features have not been calculated yet | Feature group empty state |
| `Embedding-анализы ещё не рассчитаны` | Embedding analyses have not been calculated yet | Embedding empty state |
| `Classifier analyses ещё не рассчитаны` | Classifier analyses have not been calculated yet | Classifier analysis empty state |

The file path row keeps English titles: `Copy file path`, `Copy file name`, `Copied`, and
`Open containing folder`.

## Audio Dedup reviewer

| Russian | English meaning | Where |
| --- | --- | --- |
| `Дубликаты` | Duplicates | Dialog title |
| `Отчёт строится без изменений на диске. Удаление выполняется только по вашему выбору и подтверждению.` | The report changes nothing on disk. Deletion happens only on your choice and confirmation | Subtitle |
| `Поиск` | Search | Section heading |
| `Корень поиска` | Search root | Folder field |
| `Режим` | Mode | Search mode select |
| `Отпечатки` | Fingerprints | Default search mode |
| `Эмбеддинги + отпечатки` | Embeddings plus fingerprints | Second search mode |
| `Без спектра` | Skip the spectral check | Toggle |
| `Искать дубликаты` | Find duplicates | Start button |
| `Остановить` | Stop | Cancel button |
| `Отчёт и фильтры` | Report and filters | Section heading |
| `Отчётов пока нет — запустите поиск` | No reports yet, run a search | Empty report select |
| `Скачать XLSX отчёта` | Download the report as XLSX | Download button |
| `Уверенность` | Confidence | Filter |
| `любая` | any | Confidence filter default |
| `Отпечаток ≥` | Fingerprint at or above | Filter |
| `Только фейк-битрейт` | Suspected transcodes only | Filter |
| `Путь содержит` | Path contains | Filter |
| `Отметить кандидатов` | Mark the suggested copies | Marks candidates on the current page |
| `Снять всё` | Clear every mark | Clears the selection |
| `Назад` / `Вперёд` | Back / forward | Group pagination |
| `Ничего не помечено на удаление` | Nothing is marked for deletion | Idle footer |
| `Куда` | Destination | Deletion mode select |
| `В корзину` | To the recycle bin | Default deletion mode |
| `Безвозвратно` | Permanently | Second deletion mode |
| `Удалить помеченное` | Delete the marked copies | Footer delete button |
| `Пометьте копии на удаление` | Mark copies for deletion first | Delete button title when nothing is marked |

Per group and per copy:

| Russian | English meaning |
| --- | --- |
| `оставить` | keeper |
| `копия` | copy |
| `отпечаток <value>` | fingerprint score |
| `фейк-битрейт <n>` | suspected transcodes in the group |
| `По рекомендации` | Mark everything except the suggested keeper |
| `Снять` | Clear the marks in this group |
| `Прослушать копию` / `Пауза` | Play the copy / pause |
| `Пометить копию на удаление` / `Оставить эту копию` | Mark this copy / keep this copy |
| `Помечена на удаление` / `Удалить эту копию` | Marked for deletion / delete this copy |
| `Отчёт устарел: <reason>` | The report is stale for that reason |
| `Помечены все копии группы. Оставьте хотя бы одну — иначе удаление будет отклонено.` | Every copy in the group is marked. Keep at least one or the deletion is refused |

## Confirmation dialog

One dialog handles every destructive confirmation. It has a title, a message, and two buttons.

| Russian | English meaning |
| --- | --- |
| `Да` | Yes, the confirm button |
| `Нет` | No, the cancel button |
| `Подтвердить действие` | Confirm the action, title of `Да` |
| `Отменить действие` | Cancel the action, title of `Нет` |

There is no phrase field. The dialog never asks anyone to type a confirmation string.

The messages you will meet:

| Russian | English meaning |
| --- | --- |
| `Очистить базу?` | Clear the database? |
| `Удалить все данные из SQLite базы: треки, анализы, эмбеддинги и текущий сет? Аудиофайлы на диске останутся.` | Delete every row from the SQLite database, including tracks, analyses, embeddings, and the current set? The audio files stay on disk |
| `Сбросить <MODEL>?` | Reset that family? |
| `Сбросить результаты <MODEL>? Аудиофайлы не трогаем, остальные алгоритмы останутся.` | Reset that family's results? The audio files stay untouched and the other families remain |
| `Удалить результаты <profile>?` | Delete that profile's results? |
| `Будут удалены только рассчитанные score этого классификатора. Аудиофайлы и результаты других классификаторов останутся.` | Only that classifier's calculated scores go. Audio files and other classifiers remain |
| `Удалить трек из базы?` | Delete the track from the database? |
| `Будут удалены трек и все связанные данные SQLite. Аудиофайл <track> на диске останется.` | The track row and its related SQLite data go. The audio file stays on disk |
| `Удалить помеченные копии в корзину?` | Send the marked copies to the recycle bin? |
| `Удалить помеченные копии безвозвратно?` | Delete the marked copies permanently? |

## Log and status messages

The log dialog is titled `Лог` (log), with the subtitle
`События интерфейса, сканирования, анализа и записи жанров` (interface, scan, analysis, and genre
write events).

Status messages that name a blocker are worth recognizing:

| Russian | English meaning |
| --- | --- |
| `Выберите хотя бы одну стадию анализа` | Select at least one analysis stage |
| `Выберите папку staging перед запуском Staged Mode` | Choose a staging folder before starting Staged Mode |
| `Сначала выполните SONARA-анализ хотя бы одного трека` | Run SONARA on at least one track first |
| `Выберите seed-треки` | Select seed tracks |
| `Выберите от 1 до 5 уникальных seed-треков` | Select 1 to 5 unique seed tracks |
| `Все треки страницы уже в сете` | Every track on this page is already in the set |
| `Проверка БД завершена: <n> проверено · предупреждений <n> · ошибок <n>` | Database validation finished with that many checked, warnings, and errors |

## In-product help is also Russian

Hovering most controls shows a longer Russian explanation from the frontend help text. Those strings
carry ranges and defaults, so they are useful even without translation. Two of them disagree with
the code: the scan Workers help says `1-8` where the control accepts `1..16`, and the device and
inference-batch help lists MAEST, MERT, MuQ, and CLAP without MuQ-MuLan, which also uses the
selected device.

## Related pages

- [Troubleshooting](./troubleshooting.md)
- [Known limits](./known-limits.md)
- [UI controls reference](../reference/ui-controls.md)
