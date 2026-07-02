# Search by text with CLAP

> Audience: Users who know the sound they want better than the seed track.
> Goal: Write useful CLAP prompts and read the score scale correctly.
> Type: guide

The **CLAP** tab calls `/api/search/text`. It embeds text and compares the text vector against stored CLAP audio embeddings. Run CLAP analysis before using it.

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

## CLI text search

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 20 --db .\data\library.sqlite
```

Options include:

- `--limit 1..500`
- `--min-similarity`
- `--device auto|cpu|cuda`
- `--use-ann-index` for the persistent CLAP sidecar
- `--index-dir` for a custom sidecar directory

When `--use-ann-index` is set and the sidecar is missing or stale, the command warns and falls back to exact search.
