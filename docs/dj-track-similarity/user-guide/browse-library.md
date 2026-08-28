# Browse a large library without rendering everything

After a scan you have thousands of rows and one screen. This page covers finding tracks, reading
their metadata, previewing audio, and turning what you find into seeds or a temporary set.

Panel `2. Библиотека и прослушивание` (library and listening) is the middle column. Its heading
carries a badge reading `tracks` plus the library total. Control names below are given as the
Russian string with the English meaning in parentheses, and
[UI language](../help/ui-language.md) carries the full mapping.

## Direct API equivalent

The browser uses the same current endpoints shown here. For scripting, start the backend on `127.0.0.1`
and call them directly:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/library/summary'
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/tracks?limit=25'
```

Use `GET /api/tracks/{track_id}` for full metadata and `GET /media/{track_id}` for preview audio.
The current response shapes and filter query parameters are in the
[API reference](../reference/api.md).

## Loading behavior

The library panel uses fixed server-side pages of up to `200` tracks. `Prev`, `Next`, and the
page-number field request one `/api/tracks` page at a time. All returned rows render in one
scrollable list. There is no second row-window paginator.

The pagination group also shows three read-only status chips: the current page over the page count,
the track range on this page, and the filtered total in parentheses. Each reads `...` while a page
is loading.

Database changes and newer loads invalidate older responses. Duplicate rows are reconciled by
their stable `catalog_uuid` and `track_uuid` identity. A response whose catalog identity does not
match the selected database is rejected with
`Library response catalog identity does not match the selected database.`

## Search and filters

The search box carries the placeholder `path, title, artist, genre` and matches artist, title,
album, path, and MAEST genres. Beside it a two-button group selects the matching mode:

- `LIKE` runs a substring match, so it finds partial text inside a token.
- `FTS` runs a token search. It is faster on broad text queries and does not match arbitrary
  substrings inside one token.

To the right of the pagination group sit four controls, left to right:

1. A heart icon filters to liked tracks only. Its tooltip names the count, as in
   `Показать только лайкнутые треки. Доступно: 312.` (show liked tracks only, 312 available). It is
   disabled while no track is liked.
2. A waveform icon titled
   `Показать только треки с сохранённым MAEST-флагом syncopated rhythm` filters to tracks whose
   stored MAEST analysis carries the syncopated-rhythm flag.
3. A shuffle icon toggles random playback order.
4. An up/down arrow icon toggles the display order of the loaded rows.

Shuffle and sort direction act on the rows already loaded on the current page. Neither reorders the
server query or reaches other pages. Both are disabled while fewer than two rows are loaded.

Promoted classifiers add minimum-score filters to the same library query. They are configured in the
[CLASS tab](./class-tab.md).

The API caps each request at `1..500`. The UI keeps rows light and opens full metadata only on
demand.

## Maintenance actions in panel 1

Five icon buttons in panel `1. База и анализ` (database and analysis) act on the library you are
browsing:

| Icon | Title on screen | What it does |
| --- | --- | --- |
| Circular arrows | `Обновить теги` (refresh tags) | rereads Mutagen tags for existing tracks without touching paths or analysis rows |
| Save | `Сохранить жанры` (save genres) | writes stored MAEST genres into audio files, the one backend audio write |
| Shield with a check | `Проверить базу` (validate the database) | starts a read-only database validation job |
| Two overlapping squares | `Найти и разобрать дубликаты` (find and review duplicates) | opens the Audio Dedup reviewer |
| Trash | `Очистить базу` (clear the database) | deletes every SQLite row after a confirmation, leaving audio files in place |

`Проверить базу` is read-only. It opens the file read-only, streams findings into the log, and
reports a running notice such as
`Проверка БД завершена: 41235 проверено · предупреждений 3 · ошибок 0`
(validation finished, checked, warnings, errors). Only one validation job runs at a time. The same
check is available from the CLI as `dj-sim validate-database`, which exits with code 2 when it finds
errors.

All five buttons are disabled while the library is empty or a stage is running. `Сохранить жанры`
also needs at least one stored MAEST genre.

## Metadata dialog

Open track details with the tag icon on a row, titled `Теги и жанры` (tags and genres). The dialog
separates:

- MAEST genres, with a syncopated-rhythm indicator when the flag is stored,
- `Track Details`, with file name, path, and size,
- `Tags`, the Mutagen fields,
- `Data`, the technical audio facts,
- `SONARA features`, grouped into tempo, tonal, loudness, structure, spectral, timbral, perceptual, mood, aggression, and vocalness,
- `Classifier scores`,
- `Scan analyses details`, a collapsible block with scan, SONARA, embedding, and classifier timestamps.

Each SONARA feature value carries an inline `#` comment in a fixed description column. BPM and key
candidate lists use the full value width and omit that comment. A value that has not been computed
renders as `-`, and an empty group states so in Russian, such as
`SONARA features ещё не рассчитаны` (SONARA features not computed yet).

The header carries a copy button for the file path, a copy button for the file name, an
`Open containing folder` action, and a delete action titled `Удалить из базы` (delete from the
database). The delete action removes the track and its catalog-owned SQLite data after a
confirmation and leaves the audio file on disk.

Keep those sources separate when judging a track. A MAEST label and a file tag are not the same evidence.

## Preview

The `/media/{track_id}` endpoint streams the local file when the browser can play it. AIFF, FLAC,
DSD/DSF, WMA, APE, WV, M4B/M4R, TAK, TTA, and browser-unsafe WAV files are decoded and encoded in
process with TorchCodec and the configured shared FFmpeg libraries to a temporary WAV for streaming,
then the temporary file is deleted. The source audio file is not rewritten, and no `ffmpeg.exe`
process is started.

If the file is missing, preview returns an error instead of hiding the problem.

The row playing right now replaces its score or index area with a seek slider and a `M:SS / M:SS`
readout.

### Continuous playback on the loaded page

When a library preview finishes, the player starts the next visible track in the displayed order of
the currently loaded page. Playback stops after the last visible track. It does not advance to
another page.

With shuffle enabled, the next track is chosen at random from the current page. Shuffle never
selects the track that just finished.

## Likes

The like button writes a local SQLite row with `catalog_uuid` and `track_uuid`. It does not edit
audio tags. Its tooltip toggles between `Лайкнуть` (like) and `Убрать лайк` (remove the like).
Likes can be used for browsing and filtering.

## Seeds and the current set

From each visible result row you can:

- add the track as a seed with the magnifier icon titled `Seed`,
- add or remove the track from the current set with the plus or minus icon, titled `В сет` (into the
  set) and `Убрать из сета` (remove from the set),
- start or stop preview,
- open metadata,
- toggle liked state.

Seeds feed the `SIMILARITY`, `SONARA`, and `LAB` tabs. Selected seeds appear as removable chips
above the tab strip in panel `3. Поиск и прослушивание`. The current set is the temporary playlist
inside the collapsible `Сет и экспорт` block. It is not written to disk until you export it or save
it as a Rhythm Lab collection.

## Add visible tracks

The plus button at the right of the control group appends only the tracks already loaded on the
current library page to the current set, in the displayed order. Tracks already in the set are
skipped, and a run that adds nothing reports `Все треки страницы уже в сете` (every track on this
page is already in the set). It does not make a separate library or database request, load other
pages, validate track data, or recalculate analysis.
