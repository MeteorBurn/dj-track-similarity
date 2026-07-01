# CLAP Prompting Reference

This reference is for LAION-CLAP prompt engineering with emphasis on music retrieval, zero-shot classification, and tagging.

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

## Recommended prompt families

### Label-only

Use when labels are already common genre or sound names:

```text
microhouse.
dub techno.
deep tech house.
experimental electronic music.
```

### Music template

Use for genre/style labels:

```text
This audio is a {label} track.
This audio is a {label} song.
A {label} track with {audible details}.
```

### Sound-event template

Use for non-music classes:

```text
This is an audio clip of {label}.
A sound recording of {label}.
The sound of {label}.
```

### Acoustic description

Use to disambiguate labels:

```text
A dub techno track with deep sub bass, chord stabs, tape delay, spacious reverb, and a steady four-on-the-floor beat.
```

## Prompt length

Use several compact prompts rather than one long prompt.

Practical bands:

| Type | Recommended size |
|---|---:|
| label-only | 1–4 words |
| template | 5–12 words |
| descriptive | 12–35 words |
| production upper bound | under ~50 text tokens |
| hard ceiling | 77 tokens |

## Prompt ensemble procedure

For each label:

1. Embed all prompts.
2. L2-normalize every prompt embedding.
3. Average embeddings.
4. L2-normalize the average.
5. Compare audio embeddings to label vectors via cosine similarity.

Use equal prompt counts for labels being compared.

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

Start with `alpha = 0.35`, then calibrate.

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

## Domain-specific prompt examples

### Microhouse / Romanian minimal

```text
microhouse.
This audio is a microhouse track.
This audio is a Romanian minimal house track.
A sparse microhouse track with dry drums, shuffled percussion, subtle bassline, and a hypnotic repetitive groove.
A Romanian minimal house track with micro-samples, tight percussion, and an afterhours club atmosphere.
```

### Dub techno

```text
dub techno.
This audio is a dub techno track.
This audio is a dub techno song.
A dub techno track with deep sub bass, chord stabs, tape delay, spacious reverb, and a steady four-on-the-floor beat.
A hypnotic electronic track with echoing chords, warm low-end, and a spacious dub-influenced atmosphere.
```

### Deep tech house

```text
deep tech house.
This audio is a deep tech house track.
This audio is a minimal tech house track.
A deep tech house track with a rolling bassline, tight drums, muted percussion, and a dark club groove.
A minimal house track with deep bass, precise percussion, and a restrained late-night atmosphere.
```

### Experimental electronics

```text
experimental electronic music.
This audio is an experimental electronic track.
An experimental electronic track with abstract textures, irregular rhythms, and unconventional sound design.
A leftfield electronic piece with glitchy percussion, synthetic textures, and an unconventional structure.
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
