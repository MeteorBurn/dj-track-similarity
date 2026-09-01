# Search by text in the PROMPT tab

Use text search when you can hear an idea in your head but do not have a good reference track. A
prompt such as "broken drums with metallic synth hits" gives the app an audible direction. Metadata
filters answer a different question.

The result is a ranked shortlist to audition. It can reveal tracks with incomplete genre tags, but
it does not prove that every word in the prompt is present. Rewording the prompt changes the
question and often changes the useful part of the list.

The tab renders as **PROMPT**, the fourth of the five tabs in panel 3, search and listening. Its
internal key is still `text`, so the API route is `/api/search/text`. Most of its controls are
English on screen while its tooltips are Russian. The full label mapping is in
[UI language](../help/ui-language.md).

Browser text search is rank-only. `Limit` controls how many rows are returned, scores remain in
descending order, and the browser applies no minimum-similarity threshold. API and CLI thresholds
are separate workflows.

The `Model` control selects `MuQ-MuLan` or `CLAP`, starting on `MuQ-MuLan`. The selected adapter
embeds text and compares that vector only against stored audio embeddings from the same family.
Results from either selection appear in the same tab. The browser keeps CLAP and MuQ-MuLan in
separate score spaces rather than fusing their results.

## CLI and direct API

The browser PROMPT tab is the main interactive flow. The same search is available from the CLI,
where the default model is `clap` rather than `mulan`:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, hazy pads" --model mulan --limit 20 --db .\data\library.sqlite
```

API clients can use `POST /api/search/text`; see the current request payload in the
[API reference](../reference/api.md).

## When to choose another search

- Use the `SIMILARITY` tab when one existing track already captures the direction.
- Use the `SONARA` tab when you want explicit control over rhythm, timbre, dynamics, harmony, or tempo.
- Use library filters when the property is already reliable metadata, such as artist or label.

## Before searching

You need stored audio embeddings for the chosen family. The search button is disabled when the
library summary reports zero embeddings for the selected model, and the tab shows
`Requires stored MuQ-MuLan embeddings. Run MuQ-MuLan analysis first.` The button is also disabled
while the prompt bank is empty, which the tooltip does not mention.

CLI example:

```powershell
dj-sim analyze --models mulan --db .\data\library.sqlite
```

## The model warms up when the tab opens

Opening the tab fires `POST /api/search/text/warmup` for the selected family, and changing the
`Model` select fires it again. The request loads the family and embeds the literal prompt `warmup`,
touching no library data. It runs only when the library already holds embeddings for that family,
and leaving the tab or switching model aborts an in-flight request.

While it runs, a status banner says the model is loading and that the first search will not wait for
the weights. A failed warmup instead says the warmup failed and that the search itself will load the
weights. Nothing renders once the model is ready.

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

The `Prompt bank` field takes one prompt per line, and a counter beside its label shows how many
non-empty lines will be sent. Each line is embedded on its own, and the bank is averaged into one
L2-normalized vector before the search runs. Several short prompts are more reliable than one long
sentence: in the benchmark a single caption scored anywhere between `0.955` and `0.495` ROC-AUC
depending on its wording, while a bank of four short prompts stayed stable.

The strongest measured wording is a short tag line: genre, mood, instrument and tempo words, the
vocabulary both text towers were trained on. On the hand-labelled pools, tag banks beat the older
sentence banks on four concepts out of five, on both models, by `+0.04` to `+0.14` ROC-AUC, and
long scene descriptions ranked worst everywhere. For genre concepts the effect goes further: banks
built from bare genre names and their sibling scenes rank better than caption wording, on both
models. The presets carry the winning forms.

Every measured wording form is committed in `scripts/text_prompt_benchmark_prompts.json`, so each
number here reproduces from the frozen spec. The spec also keeps the losers: the GTZAN-style
template "This audio is a `<genre>` song." was measured and lost on both models, so no production
bank uses it.

Two wording rules come out of the same benchmark:

- Keep words that describe a competing class out of the positive bank. A positive caption that
  mentioned "instrumental" dropped voice retrieval from `0.873` to `0.640`.
- Never write `no`, `not` or `without`. The text encoders do not model negation, so `no vocals`
  searches for vocals. Name the unwanted class in the `Negative` field instead. The in-product help
  on the prompt field states the same rule.

## Presets

The preset picker opens from the `Presets` button, which shows either **none selected** or
**{n} selected**. Inside, a header row of axis buttons filters the option list, and a counter reads
the selection against the 153 presets in the vocabulary.

The picker groups 153 presets on 21 axes, ordered the way a track gets described: `Rhythm`,
`Groove`, `Percussion`, `Bass`, `Synths`, `Instruments`, `Vocals`, `Harmony`, `Movement`, `Timbre`,
`Texture`, `Organic`, `Space`, `Density`, `Complexity`, `Energy`, `Tension`, `Mood`, `Abstract`,
`Function`, and `Genres`. Two labels differ from their internal keys: the `Vocals` axis is `voice`,
and the `Genres` axis is `style`.

`Genres` is the deliberate outlier, a coarse genre shelf on top of the fine perceptual axes. Its
banks are built from genre names rather than sound descriptions, because genre-tag wording measured
stronger than captions for genre concepts on both models. Each genre bank holds four lines. The
first is the bare genre tag, the second lists sibling genres, the third reaches for adjacent or
parent scenes plus a few supporting descriptors, and the last is the anchor caption
"A `<genre>` track."

Each axis carries one kind of label. `Genres` holds genres only: "Broken beat" and "Boom bap" name
drum patterns, so they live on the `Rhythm` axis instead. "Gallop" sits on `Rhythm` too, not on
`Groove`: a repeating triplet figure is a drum pattern rather than microtiming. Anchor sentences of
the form "A `<genre>` track." live only on the `Genres` axis. Banks on other axes, such as Acid 303,
Dubby / Tape, and Metallic / Industrial, open with a tag line describing the sound instead of a
genre sentence. The `Groove` axis names both poles of its claim: "Rigid / Quantized" and
"Laid-back / Loose" describe opposite microtiming extremes, and each carries the other as its hard
negative at weight `0.5`. The `Function` axis names set roles, so its beatless preset is labelled
"Interlude / Beatless" rather than a genre word.

Select several presets and their banks merge into one prompt bank. A "Breakbeat" plus
"Instrumental" selection covers both at once. Positive lines are de-duplicated in order, and chips
above the negative field show the current selection. Both text fields remain editable after a preset
fills them, but toggling any preset rewrites both fields from scratch, so hand edits are lost on the
next toggle.

Hovering a preset in the picker previews the lines it would add, split into `Positive` and
`Negative` columns for the selected model.

A preset can carry model-specific wording where a variant measured better. The picker fills the
bank for the selected model and falls back to the shared lines. Breakbeat has a MuQ-MuLan bank of
genre names (`0.975` against `0.949` for the shared lines), Minimal / Deep-tech has a CLAP bank
that differs only in capitalization (`0.851` against `0.781`), and Vocal-led has a CLAP bank of
"The sound of ..." captions, the form of CLAP's training captions (`0.927` against `0.900`).

Presets that were measured show their ROC-AUC for the selected model as a badge in the picker.
Unmeasured presets show `—` with a tooltip saying reliability is not measured because there are no
labelled examples for that label, and to check by ear. Five presets are measured on hand-labelled
pools:

| Preset | CLAP | MuQ-MuLan |
| --- | --- | --- |
| Breakbeat | 0.854 | 0.975 |
| Minimal / Deep-tech | 0.851 | 0.928 |
| Vocal-led | 0.927 | 0.906 |
| Organic / Acoustic | 0.820 | 0.833 |
| Experimental | 0.980 | 0.958 |

## The picker can switch the model for you

A preset can record which model measured best for it, either through its own pin or through its
axis. Three axes carry a pin, `Rhythm` and `Genres` to MuQ-MuLan and `Texture` to CLAP, and six
individual presets override their axis. Metallic / Industrial, Vocal-led, and Experimental point to
CLAP, while Clean / Hi-fi, Glassy, and Jazz chords point to MuQ-MuLan.

Every time you toggle a preset, the new selection is re-evaluated. When all pinned presets agree on
one model, the `Model` select changes by itself and both banks are recomposed for that model. When
they disagree, or when nothing in the selection is pinned, the current model stands.

An evidence block above the prompt field explains the current state in one of four Russian lines,
naming the model in use, the axes that drove the choice, the measured scores, and any selected
preset with no measurement at all. Picking a model by hand after an automatic switch adds a
**Switch to CLAP** or **Switch to MuQ-MuLan** button, which returns to the measured choice. Its
tooltip states why there is no third option: models cannot be mixed, because rank fusion was
measured and rejected for dragging the stronger model toward the weaker one.

## Negative prompts

The `Negative` field is a hard-negative bank. Each line is one unwanted audible class. A `Negatives`
toggle above it is on by default, and its state chip reads the line count and the weight, or
**disabled**. Turning it off keeps the text and stops sending it. The parked note then says
negatives are off and how many lines are saved, and adds that they return with the toggle.

The negative weight is displayed and not editable. It defaults to `0.5`, matching the backend
default. When presets are selected, the applied weight is the **minimum** weight among the presets
that contributed negatives. A preset whose negatives measured as harmful contributes none and
carries a weight of zero, which the picker preview states as weight 0, measured because negatives
only hurt that label. The API accepts `0` to `2`, so a scripted client has the range the browser
does not expose.

### How the contrast score is computed

With no negatives and a single positive line, the search is a plain cosine query against the family
matrix.

With a negative bank, the score is:

```text
score = positive - weight * mean(two highest negative cosines)
```

The positive term is the cosine against the L2-normalized mean of the L2-normalized positive lines.
The negative term is the **mean of the two highest** negative cosines, not the single strongest
match. Averaging the two closest negatives asks a second prompt to agree before a track is pushed
down, which one badly worded negative could otherwise decide alone. It was measured to beat the
maximum at every weight for both text models. A bank of one negative collapses back to that single
value.

Each result row carries the split: hovering the positive number shows that it is the match against
the positive prompt bank, and the negative number shows that it is the match against the nearest
negative. That second tooltip describes the single nearest negative while the code averages the two
highest.

The resulting contrast value can be negative and is not a probability.

## Preset feedback and tuning

When at least one preset built the search, every result row grows two verdict buttons: relevant
("this is what the presets mean") and irrelevant. A verdict is stored per `(track, preset, model)`
in the `text_preset_feedback` table of the library database, beside `likes`, through
`POST /api/search/text/feedback`. Clicking the same button again withdraws it. The verdicts credit
the preset selection that ranked the list, not whatever the picker holds at click time.

The accumulated verdicts are the reinforcement signal for `scripts/prompt_preset_tune.py`. Once a
preset collects enough verdicts of both kinds (five per class by default), the script scores the
current bank across the weight grid and every leave-one-out variant of its positive and negative
lines, on the frozen stored embeddings. The report puts a measured marginal value next to each
line: a positive gain on a "drop" variant means that line hurts the preset on your own verdicts.
The script is report-first and opens both databases read-only. Applying a winning change means
editing `textPromptPresets.ts`, the same as any other bank change. Verdict pools are the operator's
own ears. Trained classifier outputs play no part in the text layer.

## Label reliability

Most labels have no hand-labelled examples, so their reliability is unknown. SONARA describes the
same library from a different direction, and comparing against it says whether a label points where
it claims to. `scripts/text_tag_crosscheck.py` ranks the library with each label and checks that
ranking against SONARA signal features.

This is a cross-check rather than ground truth. A weak result can mean the label is weak, or that
the reference does not describe it.

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
references, 37 of the 153 labels keep an orthogonal SONARA reference.

| Verdict | MuQ-MuLan | CLAP |
| --- | --- | --- |
| `ok` | 11 | 18 |
| `weak` | 13 | 16 |
| `suspect` | 7 | 0 |
| `INVERTED` | 6 | 3 |

The two models are not interchangeable, and neither is better everywhere. The model that an axis
recommends now rests on hand-labelled pools where they exist: MuQ-MuLan carries rhythm
(`breakbeat` 0.975 against 0.854) and genres (`minimal deep-tech` 0.928 against 0.851), while the
texture recommendation rests on the SONARA cross-check, where CLAP leads.

The failures stay characteristic of each model. MuQ-MuLan inverts on labels naming an acoustic
instrument, `piano`, `strings and brass`, `nylon guitar`, `slap bass`, `saxophone` and `trumpet`:
it ranks programmed electronic tracks first for them. On `metallic` it no longer inverts since
the bank was reworded to open with a metallic-percussion tag line instead of a genre sentence,
but it stays near chance against SONARA spectral flatness (`0.436` to `0.450`), while the same
reword lifted CLAP from `0.593` to `0.675`. No other referenced label moved, and the label stays
pinned to CLAP. CLAP inverts on `jazz chords`, `clean` and `glassy`, which is exactly why those
three labels are pinned to MuQ-MuLan in the preset picker.

Voice labels are no longer cross-checked at all. Their old reference, SONARA vocal probability,
does not reflect whether a track actually carries a voice. A comparison against it measured the
reference rather than the label, and its verdicts were withdrawn. The one voice number that stands
is `vocal-led`, measured against hand labels by `scripts/text_prompt_benchmark.py`, not against
SONARA: its CLAP "The sound of ..." bank measures `0.927` against `0.906` for MuQ-MuLan, so the
label is pinned to CLAP.

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

## What the request carries

The PROMPT tab sends:

- `positive_queries` from the prompt bank,
- `negative_queries` from the negative bank when the toggle is on,
- `negative_weight`, only when enabled negatives exist and a preset selection set a weight,
- `analysis_family` from the `Model` control,
- `limit` from `Limit`,
- `device` from the analysis device control.

There is no `query`, `preset`, or `adaptive_contrast` request field. Presets prepare the editable
prompt fields in the browser, and their keys are not part of the search request. The contract
rejects unknown fields outright.

## Model loading and verification

The first text search after the server starts loads the selected family, unless the tab already
warmed it up. That load verifies the pinned checkpoint digest. It then copies the verified files
into a private temporary directory and deserializes the weights. The whole load takes roughly 40
seconds on a warm disk.

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
- Audio Dedup `min_similarity`,
- classifier probabilities from the `CLASS` tab.

Those are different scoring surfaces. A CLAP text score and a CLAP audio-to-audio score come from
the same stored table and still answer different questions, because one is `prompt · audio` and the
other is `audio · audio`.

Text search reads stored embeddings and library rows. Apart from the optional feedback verdicts, it
writes nothing. It does not modify source audio, tags, analysis rows, or classifier scores.

## CLI text-search options

Options include:

- `--limit 1..500`, default `50`
- `--min-similarity`
- `--model clap|mulan`, default `clap`
- `--device auto|cpu|cuda` for the selected text embedding
