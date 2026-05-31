# Analysis Models

This page describes the models behind each analysis family: what each model is,
what it produces, and how the app uses and stores its output. Use it together
with [Analysis](analysis.md), which focuses on *which* pass to run
first, and [Search & Tags](search-and-tags.md), which covers how the
results are searched.

All model analysis is database-first: it reads audio and writes results to
SQLite only. It does not modify audio files. The one explicit audio-file write
path is MAEST genre tag saving, documented in
[Search & Tags](search-and-tags.md).

## Model Summary

| Model | Identifier / checkpoint | Output | Embedding key | Device | Needs |
| --- | --- | --- | --- | --- | --- |
| Sonara | `sonara.analyze_file` | Explainable playlist features | n/a | CPU | `sonara` |
| MAEST | `discogs-maest-30s-pw-129e-519l` (`maest-infer`) | Genre labels + embedding | `maest` | `auto`/`cpu`/`cuda` | `ml` |
| MERT | `m-a-p/MERT-v1-95M` | Audio-to-audio embedding | `mert` | `auto`/`cpu`/`cuda` | `ml` |
| CLAP | `music_audioset_epoch_15_esc_90.14.pt` (LAION) | Audio + text embeddings | `clap` | `auto`/`cpu`/`cuda` | `ml` |

Sonara features live in `metadata_json.sonara_features`. MERT, MAEST, and CLAP
vectors live in the `embeddings` table under their embedding key. See
[Database](database.md) for the full storage layout.

Device selection for MAEST, MERT, and CLAP follows one rule: `auto` picks CUDA
when PyTorch sees a GPU, otherwise CPU; explicit `cuda` errors if CUDA is
unavailable. These three families also use inference batching through
`--inference-batch-size`; decoded track batching is controlled separately with
`--track-batch-size`. The `ml` and `sonara` install groups are described in
[Install](install.md).

## Sonara

Sonara is the fast, explainable feature pass. The shared audio loader starts
with `sonara.analyze_file`, and the app stores a focused set of playlist
features in `metadata_json.sonara_features` plus the model name in
`metadata_json.sonara_model`.

It produces grouped, human-readable features: core rhythm/loudness/spectral
summaries, perceptual values (`energy`, `danceability`, `valence`,
`acousticness`), musical key with confidence, and tonal analysis. Sonara BPM and
key are analyzed values, not copied file tags, and the app keeps raw Sonara key
data without deriving Camelot notation.

How the app uses it:

- The SONARA search tab ranks tracks by these features with custom mixer weights
  and modifiers.
- Library-level fields such as analyzed BPM, key, energy, danceability, and
  loudness come from Sonara.
- Sonara features are one of the inputs for promoted classifier scoring.

Sonara runs on CPU and participates in the shared decoded-track batches
controlled by `track_batch_size`; it does not use a neural inference batch. Run
Sonara first if you are unsure where to start; it is the most transparent family
because the UI can show and mix its feature groups directly. For the full key
list, see [Analysis](analysis.md).

## MAEST

MAEST predicts genre labels and stores a MAEST embedding. The adapter uses
`maest-infer` with the `discogs-maest-30s-pw-129e-519l` model.

It analyzes up to three 30-second windows per track (around a 60-second offset,
near 38% of duration, and near 72% of duration). Impossible or duplicate windows
are clamped and deduplicated. Per-label activations are averaged across windows
to pick the top labels, and the MAEST embedding rows are averaged across the
same windows.

It writes to SQLite only:

- `metadata_json.maest_model`
- `metadata_json.maest_genres`
- `metadata_json.maest_syncopated_rhythm`
- an embedding under embedding key `maest`

How the app uses it:

- Generated genre labels feed the metadata dialog and the optional genre tag
  write workflow.
- `maest_syncopated_rhythm` drives the library `syncopated` preset.
- The MAEST embedding is an input for promoted classifier scoring.

MAEST analysis itself never modifies audio. Saving labels into standard genre
tags is a separate, explicit action covered in
[Search & Tags](search-and-tags.md).

## MERT

MERT builds audio-to-audio embeddings under embedding key `mert`. The default
model is:

```text
m-a-p/MERT-v1-95M
```

How the app uses it:

- The MERT search tab finds tracks close to selected seed tracks in MERT
  embedding space.
- MERT search uses only MERT vectors; it does not mix Sonara features or CLAP
  vectors.
- MERT embeddings are an input for promoted classifier scoring.

Results depend on existing MERT embeddings, so newly scanned tracks must be
analyzed before they appear in useful MERT results. Run MERT when seed-track
similarity matters more than explainable controls.

## CLAP

CLAP builds music-focused audio embeddings under embedding key `clap` and can
also embed text into the same space for text-to-audio search. The active
checkpoint is:

```text
lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt
```

How the app uses it:

- The CLAP text search tab can embed positive and negative prompt variants and
  rank CLAP audio vectors by adaptive contrast.
- The `dj-sim text-search` CLI command runs direct single-prompt CLAP search
  from the terminal.
- Text search requires CLAP audio embeddings produced by the same checkpoint.

Run CLAP when you want to search by mood, instrumentation, energy, or other
descriptive language. Clear, concrete prompts usually work better than a single
genre word. In the UI, prompt presets provide local Find/Avoid pairs and fill
the Text query and Avoid fields directly.

## Promoted Classifiers

Promoted classifiers are not audio-analysis models; they are local profiles
trained in Rhythm Lab that score tracks from stored SONARA, MERT, and MAEST
data. In the UI, `CLASSIFIERS` is part of the same selected-model analysis job:
tracks missing classifier scores become candidates. SONARA, MAEST, and MERT
must already exist for those tracks or be selected in the same run; otherwise
the job returns a clear error instead of silently auto-selecting models. CLAP is
not an input for promoted classifiers, but selected CLAP work for each decoded
track batch is still completed before classifier scoring runs for that batch.
Standalone classifier scoring still reads existing analysis only. See [Analysis](analysis.md) for scoring details
and [Rhythm Lab](rhythm-lab.md) for training and promotion.
