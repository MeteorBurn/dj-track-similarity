# Search by text with CLAP or MuQ-MuLan

Use text search when you can hear an idea in your head but do not have a good reference track. A
prompt such as "broken drums with metallic synth hits" gives the app an audible direction. Metadata
filters serve a different purpose.

The result is a ranked shortlist to audition. It can reveal tracks with incomplete genre tags, but
it does not prove that every word in the prompt is present. Rewording the prompt changes the
question and often changes the useful part of the list.

Browser text search is rank-only. **Limit** controls how many rows are returned, scores remain in
descending order, and the browser does not apply a minimum-similarity threshold. API and CLI
thresholds are separate workflows.

The **TEXT** tab calls `/api/search/text`. Its **Model** control selects CLAP or MuQ-MuLan. The
selected adapter embeds text and compares that vector only against stored audio embeddings from the
same family. Results from either selection appear in the TEXT tab. Run the matching analysis before
using it. The browser keeps CLAP and MuQ-MuLan in separate score spaces rather than fusing their
results.

## CLI and direct API

The browser TEXT tab is the main interactive flow. The same search is available from the CLI:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, hazy pads" --model mulan --limit 20 --db .\data\library.sqlite
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

The strongest measured wording is a short tag line: genre, mood, instrument and tempo words, the
vocabulary both text towers were trained on. On the hand-labelled pools, tag banks beat the older
sentence banks on four concepts out of five, on both models, by `+0.04` to `+0.14` ROC-AUC, and
long scene descriptions ranked worst everywhere. The presets carry the winning form.

Two wording rules come out of the same benchmark:

- Keep words that describe a competing class out of the positive bank. A positive caption that
  mentioned "instrumental" dropped voice retrieval from `0.873` to `0.640`.
- Never write `no`, `not` or `without`. The text encoders do not model negation. Name the unwanted
  class in the negative bank instead.

## Presets

The preset picker groups 151 presets on 21 semantic spaces, ordered from rhythm to utility:
groove (swing and microtiming), rhythm (beat pattern), percussion, bass, synths, instruments,
organic (acoustic against synthetic), texture (surface processing), timbre (tone colour), space,
harmony, movement, density, complexity, mood, energy, tension, abstract, vocals, function (set
role), and style. Style is the deliberate outlier: a coarse genre shelf on top of the fine
perceptual spaces. Select several presets and their banks merge into one prompt bank. A "Breakbeat"
plus "Instrumental" selection covers both at once. Chips above the negative field show the
current selection. Both fields remain editable after a preset fills them.

Presets carry their own hard-negative weight, because one global value does not fit every concept.
A higher weight helps when the negatives name a real competing class. Presets whose negatives were
measured as harmful come with no negatives at all and a weight of zero. Presets that were measured
show their ROC-AUC for the selected model in the picker.

## Preset feedback and tuning

When at least one preset built the search, every result row grows two verdict buttons: relevant
("this is what the presets mean") and irrelevant. A verdict is stored per (track, preset, model)
in the `text_preset_feedback` table of the library database, beside `likes`; clicking the same
button again withdraws it. The verdicts credit the preset selection that ranked the list, not
whatever the picker holds at click time.

The accumulated verdicts are the reinforcement signal for `scripts/text_preset_tune.py`. Once a
preset collects enough verdicts of both kinds (five per class by default), the script scores the
current bank across the weight grid and every leave-one-out variant of its positive and negative
lines, on the frozen stored embeddings. The report puts a measured marginal value next to each
line: a positive gain on a "drop" variant means that line hurts the preset on your own verdicts.
The script is report-first and opens both databases read-only; applying a winning change means
editing `textPromptPresets.ts`, the same as any other bank change. Verdict pools are the
operator's own ears. Trained classifier outputs play no part in the text layer.

## Label reliability

Most labels have no hand-labelled examples, so their reliability is unknown. SONARA describes the
same library from a different direction, and comparing against it says whether a label points where
it claims to. `scripts/text_tag_crosscheck.py` ranks the library with each label and checks that
ranking against SONARA signal features.

This is a cross-check, not ground truth. A weak result can mean the label is weak, or that the
reference does not describe it.

Treat these figures as diagnostic cross-checks, not a prompt-bank reliability benchmark. A claim
that one bank is reliable or outperforms another requires a committed result table from
`scripts/text_prompt_benchmark.py`.

### What a reference can prove

References are not equal, so each one declares what it is worth.

An **orthogonal** reference measures a different kind of signal than the label names: spectral
shape, onset density, chord rate. Agreement there is evidence, and `ok` is reserved for it.

Two whole reference families were retired. MAEST genre heads used to serve as **echo** references,
but file genre tags are MAEST's own output, and track metadata and genres are ruled out as evidence
for the text layer, so every verdict they produced is withdrawn. SONARA vocal probability went the
same way earlier: its number does not reflect whether a track actually carries a voice.

### Results

Measured on the 45,109-track library, after retiring the genre-head and vocal-probability
references, 37 of the 117 labels keep an orthogonal SONARA reference.

| Verdict | MuQ-MuLan | CLAP |
| --- | --- | --- |
| `ok` | 11 | 18 |
| `weak` | 13 | 16 |
| `suspect` | 6 | 0 |
| `INVERTED` | 7 | 3 |

The two models are not interchangeable, and neither is better everywhere. The model that an axis
recommends now rests on hand-labelled pools where they exist: MuQ-MuLan carries rhythm
(`breakbeat` 0.949 against 0.853) and style (`minimal deep-tech` 0.928 against 0.781), while the
texture and energy recommendations rest on the SONARA cross-check, where CLAP leads.

The failures stay characteristic of each model. MuQ-MuLan inverts on labels naming an acoustic
instrument, `piano`, `strings and brass`, `nylon guitar`, `slap bass`, `saxophone` and `trumpet`:
it ranks programmed electronic tracks first for them. CLAP inverts on `jazz chords`, `clean` and
`glassy`, which is exactly why those three labels are pinned to MuQ-MuLan in the preset picker.

Voice labels are no longer cross-checked at all. Their old reference, SONARA vocal probability,
does not reflect whether a track actually carries a voice. A comparison against it measured the
reference rather than the label, and its verdicts were withdrawn. The one voice number that stands
is `vocal-led`, measured against hand labels by `scripts/text_prompt_benchmark.py`, not against
SONARA.

### Limits

Twenty one instrument labels share one reference, SONARA acousticness. It catches a label that
ranks the wrong way, but says nothing about whether a label finds a sitar rather than a piano: no
stored signal tells the two apart. The eleven voice labels had shared SONARA vocal probability the
same way, until that feature proved unreliable as a voice signal and was excluded from the text
cross-check entirely. The voice axis now has no reference and is checked by ear. Roughly eighteen
labels have a reference specific enough to test their own claim.

Promoted Rhythm Lab classifiers are deliberately not used as references. A classifier carries its
owner's own labelling, so certifying the text layer with it would test that layer on exactly the
task where a trained classifier already does better.

Three labels failed and were removed. `minor` and `major` scored at chance on both models: neither
text tower hears key mode, and SONARA already detects it. `machines` ranked acoustic tracks first,
because a library that is three quarters tech house offers no contrast for it.

## Negative prompt

The **Negative** field is a hard-negative bank. Each line is one unwanted audible class. When the
toggle is enabled, the search sends those lines as hard-negative queries for weighted contrast.

The current UI sends:

- `positive_queries` from the prompt bank,
- `negative_queries` from the negative bank when enabled,
- `negative_weight` when enabled negatives have a selected preset weight,
- `analysis_family` from the Model control,
- `limit` from **Limit**,
- `device` from the analysis device control.

There is no `query`, `preset`, or `adaptive_contrast` request field. Presets prepare the editable
prompt fields in the browser. Their keys are not part of the API request.

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

Text search reads stored embeddings and library rows. It does not modify source audio, tags,
analysis rows, or classifier scores.

## CLI text-search options

Options include:

- `--limit 1..500`
- `--min-similarity`
- `--model clap|mulan` (`clap` is the default)
- `--device auto|cpu|cuda` for the selected text embedding
- `--use-ann-index` for the selected family's persistent sidecar
- `--index-dir` for a custom sidecar directory

`--use-ann-index` has no exact-search fallback. A missing, stale, malformed, or unsupported sidecar
fails the command instead of quietly ranking against something else. Omit the flag to run the exact
search.
