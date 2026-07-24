# Search by text with CLAP

> Audience: Users who know the sound they want better than the seed track.
> Goal: Write useful CLAP prompts and read the score scale correctly.
> Type: guide

::: warning v7 frontend status
The React workflow below documents the deferred frontend. It has not been ported to the schema-v7
API, so these UI steps are not currently validated or available for v7. Use the backend CLI or API
alternative below.
:::

Use text search when you can hear an idea in your head but do not have a good reference track. A
prompt such as "broken drums with metallic synth hits" gives the app an audible direction. Metadata
filters serve a different purpose.

The result is a ranked shortlist to audition. It can reveal tracks with incomplete genre tags, but
it does not prove that every word in the prompt is present. Rewording the prompt changes the
question and often changes the useful part of the list.

The **CLAP** tab calls `/api/search/text`. It embeds text and compares the text vector against stored
CLAP audio embeddings. Run CLAP analysis before using it.

## Current v7 alternative

The CLI is available without the React tab:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 20 --db .\data\library.sqlite
```

API clients can use `POST /api/search/text`; see the current request contract in the
[API reference](../reference/api.md).

## Deferred frontend workflow

## When to choose another search

- Use MERT when one existing track already captures the direction.
- Use SONARA when you want explicit control over rhythm, timbre, dynamics, harmony, or tempo.
- Use library filters when the property is already reliable metadata, such as artist or label.

## Before searching

You need stored CLAP audio embeddings. In the UI, the CLAP search button is disabled when the library summary reports zero CLAP embeddings.

CLI example:

```powershell
dj-sim analyze --models clap --db .\data\library.sqlite
```

## Prompt style

Write prompts in English and describe audible traits, not metadata. Good prompts mention rhythm, drums, bass, texture, instruments, space, energy, vocal presence, and style.

Examples:

```text
dark rolling techno, low rumble, sparse vocal texture, hypnotic percussion
```

```text
broken electro rhythm, syncopated drums, dry bass, metallic synth hits
```

The UI treats each line as a separate positive prompt. It averages positive text embeddings before searching.

## Negative prompt

The **Negative** field is a hard-negative bank. Each line is one unwanted audible class. When the toggle is enabled, the search sends negative queries and adaptive contrast.

The current UI sends:

- `positive_queries` from the text field,
- `negative_queries` from the negative field when enabled,
- `adaptive_contrast: true`,
- the selected preset key,
- `device` from the analysis device control.

With negative prompts, the visible score is contrast evidence: positive prompt match minus part of the strongest negative match. It is not a probability.

## Score scale

CLAP text-to-audio scores are usually lower than seed-based audio-to-audio scores. Useful text matches may sit around `0.35..0.55`, depending on prompts and library content.

Do not compare CLAP text scores directly with:

- MERT seed-search similarity,
- SET scores,
- Hybrid audio-to-audio support,
- Audio Dedup `min_similarity`.

Those are different scoring surfaces.

## CLI text-search options

Options include:

- `--limit 1..500`
- `--min-similarity`
- `--device auto|cpu|cuda`
- `--use-ann-index` for the persistent CLAP sidecar
- `--index-dir` for a custom sidecar directory

When `--use-ann-index` is set and the sidecar is missing or stale, the command warns and falls back to exact search.
