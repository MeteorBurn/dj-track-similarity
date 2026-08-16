# Search by text with CLAP or MuQ-MuLan

> Audience: Users who know the sound they want better than the seed track.
> Goal: Choose a text embedding family, write useful prompts, and read its score scale correctly.
> Type: guide

Use text search when you can hear an idea in your head but do not have a good reference track. A
prompt such as "broken drums with metallic synth hits" gives the app an audible direction. Metadata
filters serve a different purpose.

The result is a ranked shortlist to audition. It can reveal tracks with incomplete genre tags, but
it does not prove that every word in the prompt is present. Rewording the prompt changes the
question and often changes the useful part of the list.

The **TEXT** tab calls `/api/search/text`. Its **Model** control selects CLAP or MuQ-MuLan. The
selected adapter embeds text and compares that vector only against stored audio embeddings from the
same family. Results from either selection appear in the TEXT tab. Run the matching analysis before
using it.

## CLI and direct API

The browser TEXT tab is the main interactive flow. The same search is available from the CLI:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --model mulan --limit 20 --db .\data\library.sqlite
```

API clients can use `POST /api/search/text`; see the current request payload in the
[API reference](../reference/api.md).

## When to choose another search

- Use MERT, MuQ, or MuQ-MuLan seed search when one existing track already captures the direction.
- Use SONARA when you want explicit control over rhythm, timbre, dynamics, harmony, or tempo.
- Use library filters when the property is already reliable metadata, such as artist or label.

## Before searching

You need stored audio embeddings for the chosen family. In the UI, the search button is disabled
when the library summary reports zero CLAP or MuQ-MuLan embeddings for the selected model.

CLI example:

```powershell
dj-sim analyze --models mulan --db .\data\library.sqlite
```

## Prompt style

For CLAP, write prompts in English and describe audible traits, not metadata. The official MuQ-MuLan
model also accepts English and Chinese text. Good prompts mention rhythm, drums, bass, texture,
instruments, space, energy, vocal presence, and style.

Examples:

```text
dark rolling techno, low rumble, sparse vocal texture, hypnotic percussion
```

```text
broken electro rhythm, syncopated drums, dry bass, metallic synth hits
```

The UI treats each line as a separate positive prompt. It averages positive text embeddings before
searching, within the selected family.

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

Read text-to-audio scores within one selected family and one prompt set. Results also depend on the
library. They are not directly comparable to seed-based audio-to-audio scores or to a text result
from the other family.

Do not compare CLAP or MuQ-MuLan text scores directly with:

- MERT seed-search similarity,
- Audio Dedup `min_similarity`.

Those are different scoring surfaces.

## CLI text-search options

Options include:

- `--limit 1..500`
- `--min-similarity`
- `--model clap|mulan` (`clap` is the default)
- `--device auto|cpu|cuda` for the selected text embedding
- `--use-ann-index` for the selected family's persistent sidecar
- `--index-dir` for a custom sidecar directory

When `--use-ann-index` is set and the sidecar is missing or stale, the command warns and falls back to exact search.
