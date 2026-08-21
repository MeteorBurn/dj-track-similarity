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

### What a reference can prove

References are not equal, so each one declares what it is worth.

An **orthogonal** reference measures a different kind of signal than the label names: spectral
shape, syncopation, chord rate, vocal probability. Agreement there is evidence, and `ok` is
reserved for it.

An **echo** reference is a MAEST head carrying the label's own genre name. Both the head and the
text encoders learned genre names from overlapping web tag conventions, so their errors correlate
and agreement shows a shared vocabulary rather than a working label. Echo results are capped at
`consistent` and never read as confirmation. Disagreement still counts: a label that ranks against
its own name is broken whatever the reference is.

This distinction inverts the obvious reading of the numbers. `jungle` reaches ROC-AUC `0.975`
against the head named "Jungle", while `breakbeat` reaches `0.785` against a rhythm feature, and
the second is the stronger result.

### Results

Measured on a 45,508 track library, 66 of the 107 labels have a reference.

| Verdict | MuQ-MuLan | CLAP |
| --- | --- | --- |
| `ok`, orthogonal reference | 17 | 21 |
| `consistent`, echo reference | 16 | 15 |
| `weak` | 19 | 23 |
| `suspect` | 9 | 1 |
| `INVERTED` | 5 | 6 |

The two models are not interchangeable, and neither is better everywhere. Measured by the share of
the reference in the first 100 rows, MuQ-MuLan leads on style, groove, voice and harmony, while
CLAP leads on instruments, texture, energy and low end. The largest gap is the instrument axis,
where CLAP reaches `0.719` against MuQ-MuLan's `0.454`.

That gap shows up as outright failures. MuQ-MuLan inverts on `trumpet`, `nylon guitar`,
`saxophone`, `slap bass` and `strings and brass`: it ranks programmed electronic tracks first for
labels naming an acoustic instrument. CLAP handles the same labels and inverts elsewhere, on
`spoken`, `chopped`, `clean` and `glassy`.

Voice labels behave differently again. Their global ROC-AUC sits near chance, yet `male lead` fills
71% of its top 100 with vocal tracks under CLAP and 66% under MuQ-MuLan, where the library rate is
13%. The label orders the first screen well and the rest of the library poorly, which is what a
shortlist needs, so the verdict weighs the top of the list alongside the whole ordering.

### Limits

Twenty one instrument labels share one reference, SONARA acousticness, and eleven voice labels share
SONARA vocal probability. Those references catch a label that ranks the wrong way. They say nothing
about whether a label finds a sitar rather than a piano: no stored signal tells the two apart.
Roughly eighteen labels have a reference specific enough to test their own claim.

Promoted Rhythm Lab classifiers are deliberately not used as references. A classifier carries its
owner's own labelling, so certifying the text layer with it would test that layer on exactly the
task where a trained classifier already does better.

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
