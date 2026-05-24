# Rhythm Lab Handoff

Last updated: 2026-05-24

## Goal

Build a practical rhythm classifier for the DJ library that separates:

- `broken`: syncopated or broken rhythm tracks the user wants treated as broken
- `straight`: straight four-on-the-floor rhythm
- `ambiguous`: useful for review, but excluded from training

The classifier is meant to refine the MAEST-sync candidate set first. Full
library false-negative discovery can be a later phase.

The key idea is not to trust MAEST genres alone. Genres are useful for seeding
and review, but the model should learn from available features:

- SONARA imported features
- MERT embeddings
- MAEST embeddings
- combined feature sets

## Current Lab State

Lab DB:

```text
experiments/rhythm-lab/data/rhythm_lab.sqlite
```

Source DB:

```text
C:\db\abstracted.sqlite
```

Current local counts checked on 2026-05-24:

- tracks: `5000`
- MERT embeddings: `4999`
- MAEST embeddings: `4999`
- labels:
  - `broken`: `200`
  - `straight`: `200`
  - `ambiguous`: `109`

The user manually selected 200 tracks they consider broken rhythm, and 200
tracks with straight rhythm. Treat those as the initial balanced labeled set.

## Important Semantics

`syncopated rhythm` is an automatic MAEST-genre-derived metadata flag:

```text
metadata_json.maest_syncopated_rhythm
```

Manual `label` is separate and stored in `rhythm_labels`. Training must use
manual labels only:

- train on `broken` and `straight`
- exclude `ambiguous`

The manual `broken` label means the user wants the track counted as broken
rhythm, even if MAEST genres would not clearly imply it.

## Main Project MAEST Change

The main project now stores MAEST embeddings during MAEST genre analysis.

MAEST is considered analyzed by the same trigger as MERT and CLAP:

```text
embeddings(track_id, embedding_key = "maest")
```

MAEST genres are still saved to metadata as before:

- `maest_genres`
- `maest_model`
- `maest_syncopated_rhythm`

Resetting MAEST in the main project must clear both metadata genres and
`embedding_key = "maest"` rows.

## Useful Commands

Start the lab UI:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py serve
```

Run missing MERT embeddings:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py analyze-mert --device auto --batch-size 4
```

Run missing MAEST embeddings and refresh MAEST genres:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py analyze-maest --device auto --batch-size 4
```

Train/evaluate baselines:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py train
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest experiments\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=
```

## Next Suggested Tasks

1. Run training on the current balanced 200/200 labeled set.
2. Compare `sonara`, `mert`, `maest`, and `combined` metrics.
3. Inspect confusion cases and low-confidence predictions.
4. Add an export/review queue for tracks where:
   - manual label disagrees with MAEST sync flag
   - model confidence is low
   - model predicts `straight` inside the MAEST-sync candidate set
5. After the candidate-set classifier is useful, sample non-sync tracks from the
   full library to search for false negatives.

## Cautions

- Do not mutate or retag audio files.
- Do not copy audio into the lab.
- Lab DB and artifacts are local generated data and should stay ignored by git.
- If more tracks are imported while an analysis job is already running, rerun
  the analysis command later; jobs select missing tracks only when they start.
- AIFF/AIF previews are streamed through ffmpeg as WAV for browser playback;
  this does not modify source files.
