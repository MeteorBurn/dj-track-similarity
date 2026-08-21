# Search by text with CLAP or MuQ-MuLan

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

The **Prompt bank** field takes one prompt per line. Each line is embedded on its own, and the bank
is averaged before the search runs. Several short prompts are more reliable than one long sentence:
in the benchmark a single caption scored anywhere between `0.955` and `0.495` ROC-AUC depending on
its wording, while a bank of four short prompts stayed stable.

Two wording rules come out of the same benchmark:

- Keep words that describe a competing class out of the positive bank. A positive caption that
  mentioned "instrumental" dropped voice retrieval from `0.873` to `0.640`.
- Never write `no`, `not` or `without`. The text encoders do not model negation. Name the unwanted
  class in the negative bank instead.

## Presets

The preset picker groups presets on axes: groove, low end, texture, voice, instruments, space,
energy, and style. Select several presets and their banks merge into one prompt bank. A "Breakbeat"
plus "Instrumental" selection covers both at once. Chips above the negative field show the
current selection. Both fields remain editable after a preset fills them.

Presets carry their own hard-negative weight, because one global value does not fit every concept.
A higher weight helps when the negatives name a real competing class. Presets whose negatives were
measured as harmful come with no negatives at all and a weight of zero. Presets that were measured
show their ROC-AUC for the selected model in the picker.

## Label reliability

Most labels have no hand-labelled examples, so their reliability is unknown. Other analysis layers
describe the same library from a different direction, and comparing against them says whether a
label points where it claims to. `scripts/text_tag_crosscheck.py` ranks the library with each label
and checks that ranking against SONARA features and MAEST genres.

This is a cross-check, not ground truth. A weak result can mean the label is weak, or that the
reference does not describe it.

Measured on a 45,508 track library with MuQ-MuLan, 46 of the labels have a reference. Genre labels
score highest: `jungle` reaches ROC-AUC `0.975` and fills 41% of its top 100 against a library rate
of `0.2%`. `disco`, `drum and bass` and `experimental` behave the same way. Rhythm labels also hold
up, with `breakbeat` at `0.785` against the MAEST syncopation flag.

Voice labels tell a different story. Their global ROC-AUC sits near chance, yet `male lead` fills
66% of its top 100 with vocal tracks where the library rate is 13%. The label orders the first
screen well and the rest of the library poorly, which is what a shortlist needs.

Three labels failed and were removed. `minor` and `major` scored at chance on both models: neither
text tower hears key mode, and SONARA already detects it. `machines` ranked acoustic tracks first,
because a library that is three quarters tech house offers no contrast for it.

## Negative prompt

The **Negative** field is a hard-negative bank. Each line is one unwanted audible class. When the
toggle is enabled, the search sends negative queries and adaptive contrast.

The current UI sends:

- `positive_queries` from the prompt bank,
- `negative_queries` from the negative bank when enabled,
- `adaptive_contrast: true`,
- `negative_weight` from the selected presets when they define one,
- the selected preset keys,
- `device` from the analysis device control.

With negative prompts, the visible score is contrast evidence: positive prompt match minus part of the strongest negative match. It is not a probability.

## Model loading and verification

The first text search after the server starts loads the selected family. That load verifies the
pinned checkpoint digest, copies the verified files into a private temporary directory, and
deserializes the weights. It takes roughly 40 seconds on a warm disk.

The loaded model then stays in memory and serves later searches in tens of milliseconds per prompt.
It is released after 10 idle minutes, which returns about `0.8` GB (CLAP) or `2.5` GB (MuQ-MuLan) of
device memory for analysis jobs. The next search after that reloads the model.

Because the model is reused, its pinned digest is verified once per server process instead of once
per search. Analysis jobs are unaffected: they still verify their own load.

MuQ-MuLan loads its XLM-R text encoder and tokenizer from a verified pinned snapshot as well. Both
were previously resolved from the ambient Hugging Face cache at load time and on the first prompt.

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
