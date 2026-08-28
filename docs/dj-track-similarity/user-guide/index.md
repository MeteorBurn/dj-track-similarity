# User guide

The UI is a workbench for moving from a large local collection to a smaller list worth hearing. It
is a three-column workspace under one top bar.

| Panel | Heading on screen | What it holds |
| --- | --- | --- |
| Left | `1. База и анализ` | database selection, import, maintenance actions, analysis stages and settings |
| Middle | `2. Библиотека и прослушивание` | the paginated track list, filters, preview, seeds |
| Right | `3. Поиск и прослушивание` | the five search tabs and the current set |

Panel headings, button titles, tooltips, and notices are Russian. Tab labels, model names, and most
field labels are English. Every page in this section gives the Russian string with its English
meaning in parentheses, and [UI language](../help/ui-language.md) carries the full mapping.

## Start from what you know

| What you already have | Open | What you will get |
| --- | --- | --- |
| A track that points in the right direction | `SIMILARITY` or `SONARA` | Nearby candidates ranked around the seed |
| A sound you can describe in words | `PROMPT` | A text-matched listening shortlist |
| One reference and no idea which model hears it best | `LAB` | Six model columns for the same seed |
| A recurring personal judgment | `CLASS` and Rhythm Lab | A reusable score for filtering the library |
| Useful candidates from several searches | `Сет и экспорт` | An editable working list for preview and export |

You can move tracks between these surfaces without committing to a final playlist. Search results
and the current set remain local UI state until you explicitly add or export tracks.

## Pages

- [Browse library](./browse-library.md): pagination, search, metadata, preview, seeds, and set actions.
- [Analyze library](./analyze-library.md): stage selection, Direct and Staged modes, progress, cancellation, and reset.
- [Search with seed tracks](./search-with-seeds.md): the `SIMILARITY`, `SONARA`, and `LAB` tabs.
- [Text search](./text-search.md): the `PROMPT` tab, prompt banks, negatives, presets, and score scale.
- [CLASS tab](./class-tab.md): use a personal learned concept as a library filter.
- [Export playlists](./export-playlists.md): M3U, CSV, output folder, and Rhythm Lab collections.
- [Tags and audio writes](./tags-and-audio-writes.md): the exact workflows that can touch audio files.

## Work safely

Preview and exports are not commitments. Use the app to find candidates, then listen. Write
operations are separated from browsing and search on purpose, and
[Tags and audio writes](./tags-and-audio-writes.md) names every one of them.
