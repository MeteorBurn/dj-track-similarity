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

Newer SONARA analysis adds optional Camelot key, vocalness, mood, instrumentalness, loudness, beat-grid, structure, and silence fields. Treat these analysis estimates as inspectable evidence. Only fields wired into a scorer affect ranking.

Mood affinities and instrumentalness are shown as analysis data and retained for possible future workflows. They are not current similarity, SET, Hybrid, or classifier inputs. True peak and ReplayGain are also retained for possible loudness-management features rather than direct SONARA similarity. Loudness scalars can enter the `sonara2` classifier variant. The existing SONARA dynamics comparison uses momentary loudness maximum and loudness range. Vocalness is available through an explicit search modifier and the optional `sonara2vocal` variant.

Complete beat positions, onset positions, chord labels/events, tempo curves, energy curves, loudness curves, and downbeat arrays live in the separate `sonara_curves` table. The SONARA embedding and fingerprint are archived there as well. Small beat/onset lists can also remain in hot metadata, while longer ones keep only a compact descriptor there. The metadata dialog loads the lazy payload and summarizes it in the browser. Search and classifiers never load the out-of-band copy. Time signature, time-signature confidence, tempo variability, and embedding/fingerprint version fields stay in lightweight metadata for possible future use.

SONARA values are analysis results, not copied file tags. Tempo-aware workflows use current signed
SONARA tempo evidence first. Below `0.45` confidence, they also inspect ranked tempo candidates and
the Mutagen BPM tag. Beat-grid stability can weaken reliability, and unreliable evidence moves
toward a neutral score rather than creating similarity.

SONARA v0.2.4 also stores `bpm_confidence` beside raw BPM, tempo candidates, and Camelot key. The confidence value records how strongly SONARA supports its working BPM estimate. Saved provenance records the analysis schema and settings plus the installed package version when available, so results can be traced to the configuration that produced them.

UI, CLI, and API defaults request the full supported SONARA profile. Plain playlist mode or a smaller subset must be requested explicitly. A deterministic signature identifies the exact profile, so a legacy or mismatched SONARA row is queued for reanalysis automatically instead of requiring a manual reset.

The exact field and scoring boundaries are in the
[SONARA v0.2.4 project contract](../reference/sonara-v0-2-4-contract.md).

## MAEST labels and embedding

MAEST stores genre-like labels and a MAEST audio embedding. The labels are used for display and optional standard genre tag writing. The embedding can be used as an audio-to-audio signal in SET and Hybrid preview.

Smart Set Builder may use the MAEST embedding, but it does not use MAEST genre labels as selection rules.

## MERT embedding

MERT stores an audio embedding. The MERT tab searches from selected seed tracks in this embedding space. SET, Hybrid preview, and Audio Dedup can also use stored MERT embeddings.

## MuQ embedding

MuQ stores a separate audio embedding from 24 kHz `float32` audio. It is tracked as its own analysis family and can be reset independently. The current app stores MuQ embeddings for future workflows, but it does not use them in search, SET, Hybrid, Audio Dedup, or classifier scoring yet.

## CLAP audio embedding

CLAP analysis stores audio embeddings. The CLAP tab embeds a text prompt at search time and compares it to stored audio embeddings. SET, Hybrid, and Audio Dedup use stored CLAP audio embeddings as audio-to-audio signals, which are not the same as CLAP prompt scores.

## Classifier scores

Promoted Rhythm Lab classifiers write scores under a `classifier_key`. Scores are optional. Missing scores stay neutral in SET and Hybrid modifiers.

## Why separation matters

A file genre tag, a MAEST genre label, a CLAP text score, and an Audio Dedup content similarity value answer different questions. Use them together, but do not treat them as one shared scale.
