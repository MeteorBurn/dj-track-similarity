# Read similarity scores as suggestions

> Audience: Users interpreting search results.
> Goal: Explain scores without making them sound absolute.
> Type: explanation

Scores help sort candidates inside one search mode. They are not universal quality ratings, and they do not replace listening.

## Meaning

A score says that, under the selected feature or embedding space, a candidate is close to the seed or prompt. It does not prove the track is mix-ready.

Read scores as ranking hints: the top cluster is usually more important than the exact decimal value. A lower-scored track can still be the better DJ choice if it has the right intro, vocal spacing, groove, or energy.

## Why tabs differ

- SONARA scores come from measured feature groups.
- MERT scores come from MERT embeddings.
- CLAP text scores compare prompt embeddings with CLAP audio embeddings.
- Hybrid/SET combines sources and routing logic.

Scores are comparable within the same tab or mode because they came from the same scoring surface. They are not equivalent across tabs: `0.82` in CLAP text search does not mean the same thing as `0.82` in SONARA or a SET preview. Compare candidates within the list you asked for, then decide by ear.

CLAP also appears as a stored audio embedding in SET, Hybrid, and Audio Dedup. Those audio-to-audio CLAP similarities are not the same scale as CLAP text search scores.
