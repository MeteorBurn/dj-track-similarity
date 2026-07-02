# Features, embeddings, and tags

> Audience: Users comparing search tabs and metadata panels.
> Goal: Explain each evidence source and what it should be used for.
> Type: concept

The UI shows several kinds of information. They are stored together in SQLite, but they come from different sources.

## File tags

Scan and Refresh Tags use Mutagen to read a fixed metadata set: artist, title, album, genre, year, country, label, catalog number, track number, disc number, BPM, key, comment, ISRC, duration, audio format, and codec data when available.

These are source-file tags. They can be incomplete or inconsistent. The app stores a JSON-safe copy in SQLite.

## SONARA features

SONARA produces explainable audio features and derived working fields such as BPM, key, duration, and energy. SONARA features support the SONARA tab and help Smart Set Builder reason about rhythm, dynamics, timbre, tonal content, energy flow, and transition compatibility.

SONARA values are analysis results, not copied file tags.

## MAEST labels and embedding

MAEST stores genre-like labels and a MAEST audio embedding. The labels are used for display and optional standard genre tag writing. The embedding can be used as an audio-to-audio signal in SET and Hybrid preview.

Smart Set Builder may use the MAEST embedding, but it does not use MAEST genre labels as selection rules.

## MERT embedding

MERT stores an audio embedding. The MERT tab searches from selected seed tracks in this embedding space. SET, Hybrid preview, and Audio Dedup can also use stored MERT embeddings.

## CLAP audio embedding

CLAP analysis stores audio embeddings. The CLAP tab embeds a text prompt at search time and compares it to stored audio embeddings. SET, Hybrid, and Audio Dedup use stored CLAP audio embeddings as audio-to-audio signals, which are not the same as CLAP prompt scores.

## Classifier scores

Promoted Rhythm Lab classifiers write scores under a `classifier_key`. Scores are optional. Missing scores stay neutral in SET and Hybrid modifiers.

## Why separation matters

A file genre tag, a MAEST genre label, a CLAP text score, and an Audio Dedup content similarity value answer different questions. Use them together, but do not treat them as one shared scale.
