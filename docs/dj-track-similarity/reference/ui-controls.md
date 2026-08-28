# Browser controls reference

The interface is in Russian. Every control below is named by the Russian string the app
shows, with the English meaning after it. Technical tokens stay English on screen: model names,
`LAB`, `SONARA`, `SIMILARITY`, `PROMPT`, `CLASS`, mode names such as `Balanced` and `DJ transition`,
and field labels such as `Limit`, `Mode`, `Device`, and `BatchSize`. The complete label mapping lives
in the [UI language glossary](../help/ui-language.md).

The browser works with one library database. The database picker selects the library SQLite file.
The optional `*.evaluation.sqlite` companion is opened only by Evaluation workflows. There are no
separate Timeline or Representations database controls.

The workspace is a top bar plus three panels.

## Top bar

| Control | Label on screen | Behavior |
| --- | --- | --- |
| Title link | `DJ Track Similarity`, tooltip **Открыть HTML документацию** (open the HTML documentation) | Opens `/docs/` in a new window. Returns a "Documentation is not built" page when the docs site has never been built. |
| Theme toggle | Sun or Moon icon, **Переключить тему** (switch theme) | Switches light and dark. The choice persists in browser storage under `dj-track-similarity-theme`. |
| Log | Scroll icon, **Открыть лог** (open the log) | Opens the process box and the merged event log. The button picks up an error style when any job or activity event was an error. The log keeps at most 200 events per job. |
| Rhythm Lab | Flask icon, **Запустить Rhythm Lab** or **Открыть Rhythm Lab** (start or open Rhythm Lab) | Opens a blank tab, then redirects it to the launch URL from `POST /api/rhythm-lab/launch`. |
| Power | Power icon, **Остановить все серверы и закрыть вкладку** (stop all servers and close the tab) | Calls `POST /api/server/shutdown`, then asks the browser to close the tab. |
| Stop | Square icon, **Остановить текущий scan или анализ** (stop the current scan or analysis) | Cancels the active stage, checking scan first, then analysis, then the genre tag job. Disabled while nothing is running. |
| Process indicator | Spinner with the current stage name | Read-only status. The notice text beside it reports the last result. |

After the backend acknowledges a shutdown, the UI swaps to a final **Серверы остановлены** (servers
stopped) page and asks the browser to close the tab. If the browser blocks a script-driven tab close,
that page stays visible so you can close the tab yourself. Backend shutdown also attempts managed
Rhythm Lab cleanup before the main server exits.

## Panel 1, `1. База и анализ`

The database and analysis panel (`1. Database and analysis`).

| Control | Label on screen | Behavior |
| --- | --- | --- |
| Database path | read-only field, placeholder **Выберите SQLite базу** (select a SQLite database) | Shows the current selection. |
| Database picker | Database icon, **Выбрать SQLite базу** (select a SQLite database) | Opens the native picker through `POST /api/database/dialog`. An older or incomplete catalog is rejected instead of being migrated in place. |
| Import tracks | **Загрузить треки в базу** (load tracks into the database) | Opens the scan dialog described below. |
| Refresh tags | RefreshCcw icon, **Обновить теги** (refresh tags) | Re-reads file tags for stored rows with `workers: 8`. It does not rewrite source audio. |
| Save genres | Save icon, **Сохранить жанры** (save genres) | Starts the MAEST genre tag job. This is the one control that writes audio files. |
| Validate database | Shield icon, **Проверить базу** (check the database) | Starts a read-only validation job through `POST /api/database/validation/jobs`. Findings stream into the log. |
| Audio Dedup | CopyCheck icon, **Найти и разобрать дубликаты** (find and review duplicates) | Opens the duplicate review dialog. |
| Clear database | Trash icon, **Очистить базу** (clear the database) | Deletes catalog rows after a confirmation dialog. It does not delete source audio. |

Every button in that row except the picker stays disabled while a job runs, and most also require at
least one stored track.

### Analysis cards

Under the heading **Анализ** (analysis), with a note that one run handles the selected stages and
skips finished results. There are two cards, SONARA and **ML-модели** (ML models). Each model row
carries a checkbox, the model name, a short description, its current row count, and a
**Сбросить \<MODEL\>** (reset \<MODEL\>) trash button.

The model order is `SONARA`, `MAEST`, `MERT`, `MUQ`, `MULAN`, `CLAP`. There is no CLASSIFIERS
checkbox and no FULL button. The single **Analyze** button at the bottom of the panel runs the
checked models in the order SONARA then ML, which its tooltip states as
**Запустить отмеченные модели в порядке SONARA → ML**.

The ML checkboxes stay disabled until the library holds at least one SONARA row. Until then the
selection is limited to SONARA.

| Control | Card | Default | Range or meaning |
| --- | --- | --- | --- |
| `Mode` | SONARA | `Direct` | `Direct` reads source files. `Staged` copies them to a temporary folder first. |
| Staging folder | SONARA, Staged only | empty | Read-only field plus a folder picker. Staged Mode cannot start without it. |
| `BatchSize` | SONARA, Direct | `8` | `1..16` source paths per native batch |
| `Processes` | SONARA, Staged | `4` | `1..16` |
| `Threads` | SONARA, Staged | `4` | `1..64` Rayon threads per process |
| `BatchSize` | SONARA, Staged | `4` | `1..16` ready staging paths per native mini-batch |
| `StageSize` | SONARA, Staged | `32` | `1..512` files in the staging window |
| `Mode` | ML | `Direct` | `Direct` reads source files. `Staged` copies them first. |
| Staging folder | ML, Staged only | empty | A second, independent folder with its own picker |
| `Workers` | ML, Staged | `4` | `1..16` |
| `StageSize` | ML, Staged | `64` | `1..512` |
| `Device` | ML | `AUTO` | `AUTO`, `CPU`, or `CUDA` |
| `Track batch` | ML | `8` | `1..64` |
| `Inference batch` | ML | `16` | `1..128` |
| `Analyze limit` | panel footer | `0` | `0..100000`. A `0` means every track, applied separately to each stage. |

Both staging fields are read-only and change only through their pickers. Each card hides its folder
row while it is in Direct Mode. Mode, batch sizes, the BPM range, and the other Staged settings
persist in browser storage. Neither staging folder is stored, because it receives temporary copies of
your audio, so every session asks for it again.

The SONARA BPM range is set in the scan dialog rather than here. See
[SONARA BPM range](./analysis-families.md#sonara-bpm-range).

While a running job reports the `warmup` phase, the process box replaces per-track progress with a
warm-up view. That view has a progress bar over the selected model count, the current model name,
and its resolved device. The stage indicator names model warm-up until the phase becomes
`analyzing`, when the per-track box returns. See
[Model warm-up](./analysis-families.md#model-warm-up).

## Track import dialog

Each opening of **Загрузить треки в базу** starts a new modal dialog. It does not retain a previous
folder or settings.

The dialog offers 14 format badges, all selected by default: **AAC**, **AIF**, **AIFF**, **ALAC**,
**APE**, **FLAC**, **M4A**, **MP3**, **OGG**, **OPUS**, **WAV**, **WAVE**, **WMA**, and **WavPack**.

| Control | Default | Range or meaning |
| --- | ---: | --- |
| Scan limit | `0` | `0..100000`. A `0` scans every eligible track. |
| Duration range | `120..1200` seconds | Clear either field to drop that bound on its own. |
| Workers | `8` | `1..16` in this dialog. The API accepts `1..64`. |

### SONARA BPM range section

Headed **Диапазон BPM для анализа SONARA** (BPM range for SONARA analysis). It carries three preset
chips, a `BPM Min` field, a `BPM Max` field, and a hint line. The chip strip shows the active preset
range, or **Свой диапазон** (custom range) when the pair matches no preset.

Presets are Rekordbox `70-180`, VirtualDJ `80-240`, and Mixed In Key `79-192`. `BPM Min` accepts
`20` up to half the maximum. `BPM Max` accepts twice the minimum up to `400`.

Once the library holds SONARA rows, a lock icon appears beside the heading, every field in the
section is disabled, and the hint reads **База уже проанализирована этим диапазоном. Чтобы задать
другой, сбросьте анализ SONARA.** (the database is already analysed with this range, reset SONARA
analysis to choose another). Before that, the hint explains that the first SONARA analysis fixes the
range for the whole library and that the upper bound must be at least twice the lower one.

### Folder and start

The **Папка с треками** (track folder) section takes one root through a server-side picker,
**Выбрать папку на сервере** (choose a folder on the server). Scanning is recursive. The footer
button is **Старт** (start).

Scan reads exactly these tags through Mutagen: artist, title, album, genre, year, country, label,
track number, BPM, key, and comment.

The app first collects a list of paths that match the selected formats, then submits the raw paths
to the configured `ProcessPoolExecutor` in bounded batches of up to `64`. It keeps at most twice as
many metadata batches in flight as the configured worker count. As each batch finishes, the parent
scan coordinator consumes its results and writes eligible records to SQLite immediately instead of
waiting for metadata reads across the whole library. All SQLite writes stay on the parent job
thread. Worker processes only read metadata and apply the duration bound. There is no separate
duration pass.

Duration uses Mutagen metadata first and then a lightweight PyAV container-duration fallback that
does not decode audio frames. When a duration filter is active, files whose duration cannot be
determined are skipped. Scan limit caps tracks that meet the selected filters.
The final scan total includes only tracks accepted after the duration bounds and scan limit. The
scan status shows `skip N` for tracks rejected by those filters plus supported audio files excluded
by the selected format badges.

## Panel 2, `2. Библиотека и прослушивание`

The library and listening panel (`2. Library and listening`). A badge beside the heading shows the
total track count.

| Control | Label on screen | Behavior |
| --- | --- | --- |
| Search box | placeholder `path, title, artist, genre` | Filters the library server-side. |
| Search mode | `LIKE` and `FTS` | Chooses substring matching or the FTS5 index. |
| Page navigation | `Prev`, `Next`, page-number field, `current / total`, row range, filtered total | One `/api/tracks` request per page of up to `200` tracks. Type a page number and press Enter or leave the field. |
| Liked filter | Heart icon | Shows liked tracks only. Disabled when nothing is liked. |
| Syncopated preset | Waveform icon | Shows only tracks with the stored MAEST syncopated-rhythm flag. |
| Shuffle | Shuffle icon, **Включить случайный порядок воспроизведения на текущей странице** (shuffle playback order on the current page) | Reorders the loaded page in the browser. |
| Sort direction | ArrowDownUp icon, **Показать загруженные треки в обратном порядке** (show the loaded tracks in reverse order) | Reverses the loaded page in the browser. |
| Add visible tracks | Plus icon, **Добавить треки текущей страницы в сет** (add this page's tracks to the set) | Adds the current selection to the current set. |

Shuffle and sort direction act on the rows already loaded rather than on the server query. The
search box, the liked filter, the syncopated preset, and the classifier-score thresholds are
server-side filters.

All rows from the current page render in one scrollable list. There is no second row-window
paginator.

Each row carries an index, a play/pause button (`Preview` and `Pause preview`), the title, an inline
seek bar while selected, a like button (**Лайкнуть** or **Убрать лайк**), a tags button
(**Теги и жанры**, tags and genres), a `Seed` button, and a set toggle (**В сет** or
**Убрать из сета**, add to the set or remove from the set).

Preview streams `/media/{track_id}`. Metadata is fetched on demand from
`/api/tracks/{track_id}`. A liked-track write carries `catalog_uuid` and `track_uuid`.

Changing the database cancels or invalidates older library and search requests. Track rows are
deduplicated by `catalog_uuid` plus `track_uuid`.

## Panel 3, `3. Поиск и прослушивание`

The search and listening panel (`3. Search and listening`). A seed chip strip sits above a five-tab
strip. Use `ArrowLeft` and `ArrowRight` to move between tabs. `Home` and `End` jump to the first and
last tab.

The tabs render as `LAB`, `SONARA`, `SIMILARITY`, `PROMPT`, and `CLASS`, in that order. The internal
key for the PROMPT tab is still `text`.

### LAB

Reference Compare across six separate groups: CLAP, MERT, MuQ, MuQ-MuLan, MAEST, and SONARA. An
unavailable model keeps its group and shows a model-specific reason. Verdict writes include
`catalog_uuid` and `track_uuid`.

### SONARA

| Control | Default | Range or label |
| --- | ---: | --- |
| `Mixer` sliders (timbre, rhythm, dynamics, harmonic, tempo) | `1`, `1`, `0.8`, `0.8`, `0.35` | `0..5`, step `0.05` |
| `Modifiers` sliders (nine knobs) | `0` | `-1..1`, each with its own Off reset |
| `Reset` | none | **Сбросить SONARA mixer и modifiers** (reset the SONARA mixer and modifiers) |
| `Add Random Track` | none | **Добавить случайный SONARA-ready трек из базы в seed** (add a random SONARA-ready track from the database as a seed) |
| `Mode` | `Balanced` | `Balanced`, `Vibe`, `Sound`, `DJ transition`, `Custom mixer` |
| `Limit` | `10` | `1..500` |
| `SONARA search` | none | **Найти похожие треки через SONARA по выбранным seed-трекам** (find similar tracks with SONARA from the selected seeds) |

The mixer and the modifiers take effect in `Custom mixer` mode.

### SIMILARITY

| Control | Default | Range or behavior |
| --- | ---: | --- |
| `Add Random Track` | none | Adds one random track that already has an embedding in the selected family |
| `Model` | `MERT` | `MAEST`, `MERT`, `MuQ`, `MuQ-MuLan` |
| `Limit` | `10` | `1..500` |
| `Search` | none | Runs the seed search |

CLAP has no entry in this selector. It is available from `POST /api/search` and from LAB. An option
with zero current embeddings is disabled with a source-specific reason, and request failures stay
visible in the tab instead of being replaced by an empty successful result.

### PROMPT

| Control | Default | Behavior |
| --- | --- | --- |
| `Presets` picker | closed | 21 axes over 153 presets, **Выбрать пресеты по осям** (choose presets by axis). Selections show as chips, and one button clears them all. |
| Model-advice block | hidden | Appears when the selected presets carry a measurement. A **Переключить на \<model\>** (switch to \<model\>) button changes the model to the measured one. |
| `Prompt bank` | empty | Free text, one prompt per line. A counter shows how many non-empty lines go into the bank. |
| `Negatives` toggle | off | Turns the hard-negative bank on. Turning it off keeps the text and stops sending it. |
| Hard-negative field | empty | One competing class per line. Presets fill it themselves. |
| `Model` | `MuQ-MuLan` | `CLAP` or `MuQ-MuLan` |
| `Limit` | `10` | `1..500` |
| `Search` | none | Disabled while the prompt is empty or the selected family has no stored embeddings |

Opening the tab, and every later model change, fires a warmup request that loads the model weights
before a search waits on them. While that runs, a banner reads **\<model\> загружается** (\<model\>
is loading). A failed warmup shows **Прогреть \<model\> не удалось** (warming up \<model\> failed)
and the search loads the weights itself.

Result rows in this tab add a positive and a negative score chip, plus two feedback buttons: a
thumbs-up **По делу** (on point) and a thumbs-down **Мимо** (off target). Each writes one verdict per
selected preset, and clicking the same button again withdraws it.

### CLASS

The tab filters the library by stored classifier scores. A summary line reads
`available N · blocked N`. Each promoted profile shows a fact row with Status, Type, Models,
Features, Labels, Calibrated, Validation F1, and Promoted, a play button that resets and rescores
only that `classifier_key` from stored data, a delete button, and a `0..1` minimum-score slider that
stays disabled while the profile has scored no tracks. The main analysis panel does not run
classifier scoring.

### Results and the current set

Results carry a provenance header naming the search that produced them, then one row per hit with a
score meter and the same row actions as the library list.

**Сет и экспорт** (set and export) is a collapsed disclosure at the bottom of the panel. It holds a
name field, the current set paged `20` at a time with `Prev` and `Next`, an output directory field
with a picker (**Выбрать папку экспорта**, choose the export folder), and three buttons:
`Collection` (**Сохранить текущий сет в Rhythm Lab Collection**), `M3U`, and `CSV`. Each set row has
a tags button and a **Убрать из сета** (remove from the set) button.

## Audio Dedup review

**Найти и разобрать дубликаты** stays disabled while another job runs and while the library holds no
tracks. The dialog has three parts.

The search part starts one scan. It takes **Корень поиска** (search root) with a server-side folder
picker, a **Режим** (mode) select of **Отпечатки** (fingerprints) or **Эмбеддинги + отпечатки**
(embeddings plus fingerprints), and a **Без спектра** (skip spectral) toggle. The start button is
**Искать дубликаты** (find duplicates) and becomes **Остановить** (stop) while a scan runs, with a
progress bar over the processed count. The dialog sends only the root, the mode, and the spectral
toggle, so the preset stays at the server default `safe` and the source, weight, threshold,
stored-path, and group-limit options remain CLI-only. Job status polls every `1200` ms.

**Отчёт** (report) picks one report from the report directory, newest first, and downloads its XLSX
workbook when one exists. The filters are **Уверенность** (confidence, with **любая** for any),
**Отпечаток ≥** (fingerprint at least), **Только фейк-битрейт** (fake bitrate only), and
**Путь содержит** (path contains). **Отметить кандидатов** (mark candidates) selects the suggested
copies for every group on the page, and **Снять всё** (clear all) empties the selection. Groups page
`25` at a time, and the API caps a page at `200`.

The group list shows one card per duplicate group with a card for each copy, the suggested keeper
included. Each copy has a play button that reuses the app's single player through `/media/{track_id}`
and a toggle reading **Удалить эту копию** (delete this copy) or **Помечена на удаление** (marked for
deletion). Each group header has **По рекомендации** (follow the suggestion), which marks everything
except the suggested keeper, and **Снять** (clear), which clears that group. Every listed file is
rechecked against the live database and the disk, and a file that no longer matches its report row is
marked stale with a reason.

The footer counts the marked copies and their groups, offers **Куда** (destination) with
**В корзину** (recycle bin) or **Безвозвратно** (permanently), and ends with
**Удалить помеченное** (delete the marked copies). That button is enabled as soon as at least one
copy is marked and no dedup request is in flight. There is no confirmation-phrase field. Pressing it
opens a **Да / Нет** (yes / no) dialog naming the count, the size, and the destination. The client
puts the `APPLY DELETE` string the API requires into the request body itself. A group with every copy
marked is refused before the request is sent. For the deletion gates and the report semantics, see
[Audio Dedup](../tools-and-scripts/audio-dedup.md).

## Confirmation dialogs

Destructive actions open one shared dialog with a title, a message, and two buttons: **Нет** (no) and
**Да** (yes). No dialog in the app asks the user to type a phrase.

## Rhythm Lab from the browser

The top-bar Rhythm Lab action calls `/api/rhythm-lab/launch` and opens the returned local URL. The
current set can be saved as a Lab review collection. Standalone Rhythm Lab shows current, missing,
or stale state for SONARA, MERT, MAEST, CLAP, MuQ, and MuQ-MuLan. Its page sizes are `50`, `100`,
`200`, and `500`. For a binary profile, a configured training label appears immediately after
`TRAINED` with its display name, positive in green and negative in red. The training-recipe selector
supports explicit combinations of all six sources.

For analysis semantics, see [Analyze a library](../user-guide/analyze-library.md). For
source-file boundaries, see [Local-first safety](../concepts/local-first-safety.md).
