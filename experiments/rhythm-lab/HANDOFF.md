# Rhythm Lab Handoff

Last updated: 2026-05-24

## Goal

Build a practical rhythm classifier for the DJ library that separates:

- `broken`: syncopated or broken rhythm tracks the user wants treated as broken
- `straight`: straight four-on-the-floor rhythm
- `ambiguous`: useful for review, but excluded from training

Rhythm Lab is now a labeling/training layer over a main project database. It
does not scan audio and does not run MAEST/MERT/SONARA analysis. Analysis must be
done in the main project.

## Current Architecture

Source DB, read-only:

```text
C:\db\abstracted.sqlite
```

Labels DB, writable local lab state:

```text
experiments/rhythm-lab/data/rhythm_lab.sqlite
```

The source DB provides:

- `tracks`
- `metadata_json`
- MAEST genres and `maest_syncopated_rhythm`
- SONARA features
- MERT/MAEST embeddings
- audio paths for preview

The labels DB provides:

- `rhythm_labels`
- `rhythm_predictions`

Manual labels are keyed by:

```text
rhythm_labels.source_track_id = source.tracks.id
```

The labels DB also stores `path`, `size`, and `mtime` snapshots. Under the
current assumption that the source DB only grows and track IDs are not
recreated, this mapping is stable.

## Important Semantics

`syncopated rhythm` is an automatic MAEST-genre-derived metadata flag in the
source DB:

```text
metadata_json.maest_syncopated_rhythm
```

Manual `label` is separate and stored in the labels DB. Training must use manual
labels only:

- train on `broken` and `straight`
- exclude `ambiguous`

The manual `broken` label means the user wants the track counted as broken
rhythm, even if MAEST genres would not clearly imply it.

## UI

Start the lab UI:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py serve --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
```

The UI starts with no source DB loaded unless `--source` is provided explicitly.
Choose an existing source DB via the source database field, Browse button, and
Load database button. Browse only fills the path field; Load database validates
that the file already exists and has the main project schema, then opens it
read-only.

Track rows keep the compact Rhythm Lab layout:

- MAEST genres, the automatic `syncopated rhythm` badge, and the manual rhythm
  label badge share one row.
- Manual label badges are color-coded: `broken` red, `straight` blue,
  `ambiguous` violet.
- Starting one audio preview stops and rewinds any previously playing preview.

## Useful Commands

Train/evaluate baselines:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py train --source C:\db\abstracted.sqlite --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
```

Apply/export predictions:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py predict experiments\rhythm-lab\artifacts\<model>.joblib --source C:\db\abstracted.sqlite --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py export-predictions --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest experiments\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=
```

## Cautions

- Do not mutate or retag audio files.
- Do not write to the source database from Rhythm Lab.
- Do not copy audio into the lab.
- Labels DB and artifacts are local generated data and should stay ignored by git.
- If the main source DB is recreated from scratch and `tracks.id` values change,
  labels may need a recovery pass using stored path/size/mtime snapshots.
- AIFF/AIF previews are streamed through ffmpeg as WAV for browser playback;
  this does not modify source files.
