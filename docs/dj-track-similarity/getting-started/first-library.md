# Build your first library

A library is the app's private map of your music collection. It lets you search one catalog even when
the files are spread across folders and their tags are incomplete. Your audio stays in its original
location.

Control names on this page are given as the Russian string the browser shows, with the English
meaning in parentheses. The full mapping is in [UI language](../help/ui-language.md).

## What you get after a scan

- one browsable list of supported audio files,
- searchable artist, title, album, genre, path, and other available tags,
- stable track rows that later analysis can attach results to,
- scan counts that show what was added, updated, unchanged, or skipped.

Scanning alone does not give you sound-based search. It builds the catalog first. The next step,
[analysis](./first-analysis.md), adds the audio evidence behind similarity search, text search, LAB
comparison, Audio Dedup, and classifiers.

## How the catalog is stored

The selected library file stores track identity, paths, tags, analysis rows, embeddings, likes, and
classifier scores. Its one `library` row carries the `catalog_uuid` and selected scan roots.

`*.evaluation.sqlite` is an optional adjacent database for evaluation data. Resolving its path does
not create it. Normal startup refuses a legacy split layout instead of adapting it.

## Choose or create a database

In panel `1. База и анализ` (database and analysis), the read-only field at the top shows the current
SQLite path, with the placeholder `Выберите SQLite базу` (choose a SQLite database) when nothing is
selected. Press the database icon beside it, titled `Выбрать SQLite базу` (choose a SQLite database),
and pick the file. A new path creates the current library schema. An existing path loads only after
the runtime validates its `library` identity. Switching the database also clears old library and
search state, so a late response cannot leak rows from the previous catalog.

From the CLI, pass `--db`:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

## The import dialog

Press **Загрузить треки в базу** (load tracks into the database) in panel `1. База и анализ`. It
opens a dialog headed `Настройка параметров загрузки треков в базу` (import parameter settings) with
the subtitle `Форматы, длительность и диапазон BPM решают, что попадёт в базу.` (formats, duration,
and the BPM range decide what enters the database). The button stays disabled until a database is
selected.

The dialog holds its values only while it is open. Every new opening restores the defaults, except
for the SONARA BPM range, which belongs to the library.

### `Форматы файлов` (file formats)

Fourteen format chips, all selected at first. A counter beside the section title reads
`{selected} из 14` (of 14). Click a chip to exclude that format, and click it again to include it.

```text
AAC  AIF  AIFF  ALAC  APE  FLAC  M4A  MP3  OGG  OPUS  WAV  WAVE  WMA  WavPack
```

They map to these extensions:

```text
.aac .aif .aiff .alac .ape .flac .m4a .mp3 .ogg .opus .wav .wave .wma .wv
```

A supported audio file whose format chip is deselected is counted under `skip` in the activity
status rather than silently ignored.

### `Границы отбора` (selection bounds)

| Control | Initial value | Range or behavior |
| --- | ---: | --- |
| `Scan limit` | `0` | `0..100000`; `0` means every eligible track |
| `Min, сек` (minimum seconds) | `120` | positive integer; clearing the field disables only this bound |
| `Max, сек` (maximum seconds) | `1200` | positive integer; clearing the field disables only this bound |
| `Workers` | `8` | `1..16` metadata reader processes |

`Scan limit` counts tracks added to the database, not files visited. Its tooltip states that
scanning stops once that many new tracks have been added.

### `Диапазон BPM для анализа SONARA` (SONARA analysis BPM range)

The range SONARA folds estimated tempos into belongs to the library rather than to one run. Choose
it here, before the first SONARA analysis.

Three preset chips are offered. Selecting one fills both fields:

| Preset chip | Range |
| --- | ---: |
| `Rekordbox` | 70 to 180 |
| `VirtualDJ` | 80 to 240 |
| `Mixed In Key` | 79 to 192 |

Type your own pair into `BPM Min` and `BPM Max` when none of them fits. A pair matching no preset is
marked `Свой диапазон` (custom range) beside the section title. Both bounds accept `20` to `400`.

The upper bound must be at least twice the lower one, because SONARA folds octave-related tempo
estimates into the range. Editing one field pushes the other just far enough to keep that rule, so
the dialog cannot submit a pair the backend would reject.

Once the library holds SONARA rows, the section locks. A padlock icon appears beside the title, the
preset chips and both fields go read-only, and the hint changes from
`Выберите пресет или введите свой диапазон. Задаётся один раз: первый анализ SONARA закрепит его за всей базой. Верхняя граница должна быть минимум вдвое больше нижней.`
(choose a preset or enter your own range, set once, fixed by the first SONARA analysis, upper bound
at least twice the lower) to
`База уже проанализирована этим диапазоном. Чтобы задать другой, сбросьте анализ SONARA.`
(the database is already analyzed with this range, reset SONARA analysis to choose another).

An analysis job that requests a different range than the stored one is refused with the same
instruction. Choosing another range means resetting SONARA and reanalyzing. See
[Reanalyze SONARA data](../workflows/reanalyze-sonara-split-storage.md).

### `Папка с треками` (music folder)

The read-only path field shows `Папка не выбрана` (no folder selected) until you press the folder
icon, titled `Выбрать папку на сервере` (choose a folder on the server). The picker runs on the
machine hosting the backend. Scanning descends into subfolders.

### Starting the import

Press **Старт** (start) in the footer. The button stays disabled until a folder is chosen, at least
one format is selected, and the duration bounds are valid. Pressing it with something missing shows
`Выберите папку, хотя бы один формат и корректный диапазон длительности.` (choose a folder, at
least one format, and a valid duration range).

The dialog has no cancel button. Dismiss it with the `Закрыть` (close) icon in its header or with
`Escape`.

The dialog closes immediately and a centered `Подготавливаем список треков…` (preparing the track
list) toast appears. The main status reads `Сканирование директории` (scanning directory). After the
API returns the scan job, it changes to `Загрузка треков в базу` (loading tracks into the database)
and the normal scan-job status takes over with counts for added, updated, unchanged, skipped, and
failed. The browser refreshes the typed library summary when the job finishes.

## How the scan runs

The app first collects a list of paths that match the selected formats, then submits the raw paths
to the configured `ProcessPoolExecutor` in bounded batches of up to `64`. It keeps at most twice as
many metadata batches in flight as the configured worker count. As each batch finishes, the parent
scan coordinator consumes its results and writes eligible records to SQLite right away instead of
waiting for metadata reads across the whole library. All SQLite writes stay on the parent job
thread. Worker processes only read metadata and apply the duration bound. There is no separate
duration pass.

Duration comes from Mutagen metadata first, then from a lightweight PyAV container-duration fallback
that decodes no audio frames. Files with an unknown duration are skipped when a bound is active.

The directory walk is name-sorted and depth-first, it does not follow symlinked directories, and it
de-duplicates resolved paths. It skips AppleDouble-style files whose names start with `._`.

A file whose size or modification time changed between the metadata read and the write is failed
rather than written with stale values.

The equivalent CLI command is:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

The CLI scans with the full extension set and no bounds, which is also the only configuration that
marks previously seen files as missing. Both surfaces create a fresh library database when the
selected file does not exist. A legacy split database stays unchanged until you explicitly stop its
users and run `dj-sim migrate-database`.

## What scan reads

Scan reads exactly eleven tag fields through Mutagen, plus duration and technical file facts:

```text
artist  title  album  genre  year  country  label  track_number  bpm  key  comment
```

Each name resolves through several tag aliases, so `artist` also accepts `albumartist`, `TPE1`,
`TPE2`, `©ART`, and `aART`. Catalog number, disc number, and ISRC are not read and have no column.

When a tag cannot be read, scan still creates a minimal metadata row with the file stem as title.

## What scan writes

Scan writes library track and tag rows. It does not write audio tags. A track is updated when its
file size or modification time changes. An unchanged size and modification time pair deliberately
skips tag decoding, so a tag-only edit needs Refresh Tags.

The CLI prints added, updated, unchanged, and skipped counts.

## Refresh Tags

The backend can reread file tags for existing tracks without rerunning SONARA, MAEST, MERT, MuQ,
MuQ-MuLan, or CLAP. Press the circular-arrows icon titled `Обновить теги` (refresh tags) in panel
`1. База и анализ`. It uses eight workers and reports progress through the same activity surface as
scan. Stored paths and every analysis row stay untouched.

## Browse after scan

The library panel reads one server-backed page of up to `200` tracks at a time. Use `Prev`, `Next`,
or the page-number field to move between pages. Each page maps to one `/api/tracks` request with
`limit=200`. The final page can hold fewer rows. Every row from the current page renders in one
scrollable list.

The browser deduplicates each loaded result by `catalog_uuid` and `track_uuid`. Metadata opens from
the detail endpoint only when requested. Preview and liked-track changes use the same exact track
identity.
