# Search by text with CLAP

> Audience: Users who think in descriptions rather than seed tracks.
> Goal: Use CLAP text prompts against stored CLAP audio embeddings.
> Type: how-to

## Before searching

Run CLAP analysis first. The UI shows a requirement message when stored CLAP embeddings are missing.

## Prompt style

Use concrete audio words: mood, density, instrumentation, rhythm, vocal presence, or mix role. Profile presets fill the CLAP fields with a small prompt bank: each line is embedded separately, then the positive lines are pooled before scoring.

Keep prompt lines short and audio-centered. Prefer phrases such as `breakbeat.`, `This audio is a breakbeat track.`, or `An instrumental club track focused on drums, bass, rhythm, and production texture.` Avoid metadata, artist references, release years, and subjective claims.

The visible `Negative` field is a hard-negative bank, not a diffusion-style negative prompt. Write unwanted audible classes as positive statements, such as `This audio contains prominent singing vocals.` or `This audio is a straight four-on-the-floor house track.`

## Meaning

A high score means the prompt vector is close to the stored audio embedding. It is not proof that the track fits your exact context.

CLAP text-to-audio scores often sit below seed-based audio searches. In this library, useful text results can be around `0.35-0.55`. Do not reuse a high MERT or audio-to-audio threshold without checking the result list. If `Negative` is enabled, the shown score is contrast-style evidence: pooled positive prompt match minus `0.35 * max(hard-negative match)`.
