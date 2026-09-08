# Text Prompt Bank Reference

This reference describes the current balanced prompt-bank format for CLAP and
MuQ-MuLan, followed by CLAP scoring background.

## Model assumptions

Primary target configuration:

```text
repo: lukewys/laion_clap
checkpoint: music_audioset_epoch_15_esc_90.14.pt
architecture: HTSAT-base
enable_fusion: False
embedding dimension: 512
sample rate: 48 kHz
text max length: 77 tokens
nominal audio chunk: 10 seconds
```

## Why prompts behave differently from image generation prompts

CLAP does not execute the text as a command. It embeds text and audio into a shared vector space. Prompt text should therefore be treated as an anchor that names and describes audible characteristics.

Strong anchors are:

- short
- acoustic
- unambiguous
- similar to natural audio captions
- comparable across labels

Weak anchors are:

- long paragraphs
- artist-like references
- social metadata
- taste claims
- negative clauses with many `no/not/without` terms

## Balanced prompt forms

Use six positive lines for every label and every model: two label anchors, two
tag lists, and two descriptions, in that order. This is the user's curation
contract; superiority over a single prompt requires a retrieval comparison.

### Label anchors: lines 1-2

Name the target property directly. For MuQ-MuLan, a compact term and a short
`A {label} track.` template can both serve as anchors. For CLAP, frame both
anchors through the track, such as `The track has {label}.`. Use the precise
musical term rather than a broader synonym chosen only for variety.

### Tag lists: lines 3-4

Write two distinct lists of short, comma-separated musical or acoustic keywords,
usually one or two words per tag. Use established multiword terms such as
`drum breaks`; do not fill these rows with descriptive clauses. MuQ-MuLan receives
lowercase bare lists without a final period, such as
`breakbeat, syncopation, backbeat`. Each complete list remains one prompt;
commas do not create separate vectors.
CLAP keeps a short track frame, such as `This track has {tag}, {tag}, {tag}.`.
Select only tags describing the target axis and label.

### Short descriptions: lines 5-6

Describe the audible behavior in two short sentences. Preserve the label's
meaning without adding genre, mood, instrumentation, tempo or another condition
unless that condition defines the selected label. CLAP descriptions stay
track-centered; MuQ-MuLan descriptions can be more compact.

## Prompt length

Use several compact prompts rather than one long prompt.

Practical bands:

| Type | Recommended size |
|---|---:|
| label anchor | a short term or a short track template |
| tag list | 2–4 concise tags, with a short track frame for CLAP |
| short description | one concrete sentence |
| production upper bound | under ~50 text tokens |
| hard ceiling | 77 tokens |

## Prompt ensemble procedure

For each label:

1. Embed each of the six complete prompt lines.
2. L2-normalize every prompt embedding.
3. Average all six embeddings with equal weights.
4. L2-normalize the average.
5. Compare audio embeddings to label vectors via cosine similarity.

Each form contributes two vectors out of six. Keep that balance across labels
and models. The form names are a writing convention, not a text classifier,
special tokenizer input or an additional weighting mechanism.

## Handling negative concepts

Avoid treating negative prompt text as a reliable exclusion mechanism:

```text
no vocals, no pop, no rock, not commercial
```

Replace it with hard-negative classes:

```text
This audio contains prominent singing vocals.
This audio is speech or spoken word.
This audio is a vocal pop song.
This audio is rock music with electric guitars.
```

Then score with a margin:

```text
final = sim(audio, positive_label) - alpha * max(sim(audio, hard_negative_i))
```

Calibrate `alpha` per label rather than globally. Measured on this project's library, a
negative bank that names a real competing class keeps improving up to `alpha = 0.75-1.0`,
while an invented negative bank lowers ROC-AUC at every `alpha`, so such labels ship with
no negatives and `alpha = 0`. The server default of `0.5` applies only when a request
sends no weight of its own.

## Audio segmentation for full tracks

For `enable_fusion=False`, score explicit 10-second windows:

```text
window_seconds = 10
hop_seconds = 5
sample_rate = 48000
window_samples = 480000
hop_samples = 240000
```

Aggregate with:

- mean
- median
- top-k mean, e.g. top 20% windows
- max
- standard deviation

For club music, `median` and `top20_mean` are often more useful than a single whole-track score.

## Balanced bank examples

Each block is one six-line bank: anchors first, then tag lists, then descriptions.
Keep each line focused on the label; these examples are writing patterns, not
evidence that six prompts improve retrieval.

### Breakbeat: MuQ-MuLan

```text
Breakbeat rhythm.
A breakbeat track.
breakbeat, syncopation, backbeat
drum breaks, offbeat, percussion
The drums repeat a break with irregular kicks and snare backbeats.
The kick and snare interlock in a repeating broken pattern.
```

### Breakbeat: CLAP

```text
The track has a breakbeat drum pattern.
A track with a broken drum rhythm.
This track features breakbeat, syncopation, backbeats.
A track with drum breaks, offbeat accents, percussion.
This track features a broken rhythm with syncopated kick and snare hits.
The track repeats a drum break whose irregular kicks interlock with snare backbeats.
```

## Calibration checklist

Create a small validation set:

- 20–50 known positive tracks per target label if possible.
- 20–50 near-miss tracks per label.
- A few obvious negatives.
- Optional per-window annotations for intros/breakdowns/drops.

For each label:

1. Plot score distributions for positives and negatives.
2. Compare label-only vs template vs description vs ensemble.
3. Choose thresholds from distributions, not from vibes.
4. Keep examples of false positives and false negatives.
5. Rewrite prompts to separate confused labels.

## Common failure modes

### Prompt too literary

Problem:

```text
A transcendent journey through futuristic inner space with profound underground aesthetics.
```

Fix:

```text
A deep electronic track with sparse percussion, low bass, synthetic textures, and a hypnotic late-night atmosphere.
```

### Negative clauses dominate the prompt

Problem:

```text
A minimal track with no vocals, no rock, no pop, no bright melodies, no acoustic instruments.
```

Fix:

```text
A stripped-down instrumental minimal house track with dry percussion, subtle bassline, and sparse synthetic texture.
```

Then use hard negatives for vocals, rock, pop, and acoustic music.

### Label imbalance

Problem: one class has 1 short prompt, another has 8 detailed prompts.

Fix: standardize prompt count and type across labels.

### Whole-track randomness with non-fusion checkpoints

Problem: file-level embedding may represent a random or non-representative chunk.

Fix: score deterministic 10-second windows and aggregate.
