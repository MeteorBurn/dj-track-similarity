# Search by text with CLAP

> Audience: Users who think in descriptions rather than seed tracks.
> Goal: Use CLAP text prompts against stored CLAP audio embeddings.
> Type: how-to

## Before searching

Run CLAP analysis first. The UI shows a requirement message when stored CLAP embeddings are missing.

## Prompt style

Use concrete audio words: mood, density, instrumentation, rhythm, vocal presence, or mix role. Negative prompts can steer away from unwanted traits.

## Meaning

A high score means the prompt vector is close to the stored audio embedding. It is not proof that the track fits your exact context.

CLAP text-to-audio scores often sit below seed-based audio searches. In this library, useful text results can be around `0.35-0.55`; do not reuse a high MERT or audio-to-audio threshold without checking the result list. If `Avoid` is set, the shown score is contrast-style evidence: positive prompt match minus negative prompt match.
