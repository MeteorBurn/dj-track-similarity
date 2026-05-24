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

Generated artifacts and exports live under:

```text
experiments/rhythm-lab/artifacts/
```

These remain local generated data and should not be committed.

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

The UI now has two tabs:

- `Library`: the original searchable source-library labeling view.
- `Candidates`: a post-training review queue built from `rhythm_predictions`.

The Candidates tab defaults to unlabeled candidates with `P(broken) >= 0.3`.
Rows are ordered by broken probability descending and show:

- SONARA/MERT/MAEST availability
- current manual label
- `P(broken)` and `P(straight)`
- predicted label and feature set
- MAEST genres plus rhythm badges
- audio preview and the same manual labeling controls

Predictions are de-duplicated by `source_track_id`; the latest saved prediction
for a track is what the UI and CSV export show. This avoids duplicate candidates
after multiple train/predict iterations.

## Current Training State

As of the latest local run in this handoff:

- manual training labels: `500 broken`, `500 straight`
- review-only labels: `164 ambiguous`
- all 1,000 training labels were feature-complete for `combined`
- latest selected artifact:

```text
experiments\rhythm-lab\artifacts\rhythm-combined-20260524T124029Z.joblib
```

Latest `combined` metrics from the 1,000-label run:

- 5-fold CV broken recall mean: `0.944`
- 5-fold CV broken precision mean: `0.931`
- 5-fold CV macro F1 mean: `0.937`
- holdout threshold `P(broken) >= 0.3`: broken recall `0.984`, precision `0.885`
- holdout threshold `P(broken) >= 0.5`: broken recall `0.968`, precision `0.896`

Latest prediction coverage for the current source DB:

- predicted with `combined`: `11030`
- skipped for missing combined features: `29064`

The latest candidate export is:

```text
experiments\rhythm-lab\artifacts\broken-candidates.csv
```

It is sorted by `P(broken)` descending and contains one latest prediction per
source track ID.

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

Recommended current loop:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py train --source C:\db\abstracted.sqlite --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py predict experiments\rhythm-lab\artifacts\<selected-combined-model>.joblib --source C:\db\abstracted.sqlite --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py export-predictions --labels experiments\rhythm-lab\data\rhythm_lab.sqlite --output experiments\rhythm-lab\artifacts\broken-candidates.csv
```

Then review in the Candidates tab instead of opening the CSV manually.

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

## Future Improvement Ideas

- Add Candidates sort modes:
  - highest `P(broken)` for fast positive discovery
  - uncertain first for `P(broken)` near `0.5`
  - likely false positives where prediction is broken but genres/manual history
    suggest straight
- Add min/max probability filters so the user can target a band such as
  `0.35 <= P(broken) <= 0.65`.
- Add a label-audit queue for manual labels that strongly disagree with the
  latest model.
- Add a "latest artifact only" indicator and optional cleanup command for old
  prediction rows.
- Compare tuned logistic regression, calibrated linear SVM, and a small
  gradient-boosted tree model on the same CV splits.
- Report per-genre/per-folder precision and recall to find under-trained
  rhythm families.
- Add a lightweight run manifest recording label counts, source DB path,
  feature coverage, selected artifact, and metric summary for each training
  iteration.
- Once all roughly 40,000 source tracks have MERT and MAEST embeddings, rerun
  `combined` predictions for the full library and resume Candidates review from
  the updated queue.
