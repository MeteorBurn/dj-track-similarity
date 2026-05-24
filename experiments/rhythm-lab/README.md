# Rhythm Lab

Temporary mini app for manually labeling rhythm classes and training a small
classifier from an existing `dj-track-similarity` project database.

Rhythm Lab no longer scans or analyzes audio. All analysis is expected to happen
in the main project database. The lab opens that database read-only and stores
only user labels/predictions in its own writable SQLite file.

## Databases

Default source database:

```text
C:\db\abstracted.sqlite
```

Default labels database:

```text
experiments/rhythm-lab/data/rhythm_lab.sqlite
```

The source database must already exist and use the main project schema. Rhythm
Lab will not create it. The labels database is local lab state and may be
created by the lab.

Labels are keyed by the source database `tracks.id` value:

```text
rhythm_labels.source_track_id = source.tracks.id
```

The labels table also stores `path`, `size`, and `mtime` snapshots for future
diagnostics. With the current workflow where the source database only grows and
tracks are not deleted/recreated, `source_track_id` is stable enough.

## Quick Start

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py serve --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
```

Open:

```text
http://127.0.0.1:8777/
```

No source database is loaded at startup unless `--source` is provided
explicitly. The UI includes a source database path field, a file picker button,
and a Load database button. The picker opens only an existing SQLite file and
only fills the path field; the database is loaded only after pressing Load
database. The selected source DB is opened read-only.

## Labeling UI

The UI includes:

- Library and Candidates tabs
- text search by path/title/artist
- source database picker and load control
- syncopated rhythm filter: all, syncopated rhythm, no syncopated rhythm
- manual label filter: all, unlabeled, broken, straight, ambiguous
- pagination
- audio preview from source paths
- MAEST genres and SONARA/MERT/MAEST feature availability from the source DB

Manual rhythm label badges are color-coded in the track row:

- `broken`: red
- `straight`: blue
- `ambiguous`: violet

Keyboard shortcuts on a focused row:

- `1` = `broken`
- `2` = `straight`
- `3` = `ambiguous`
- `0` = clear label

AIFF/AIF previews are transcoded to WAV on the fly for browser playback. This is
read-only streaming and does not rewrite or cache the source audio file.
Starting a preview stops and rewinds the previously playing preview.

The Candidates tab reads saved `rhythm_predictions` from the labels DB. It is
intended for controlled post-training review:

- candidates can be ordered by highest `P(broken)`, highest `P(straight)`, or
  near-equal `P(broken)`/`P(straight)`
- each row shows SONARA/MERT/MAEST availability, current manual label,
  predicted probabilities, MAEST genres, rhythm badges, and audio preview
- labeling uses the same `Broken`, `Straight`, `Ambiguous`, and `Clear` actions
- `Refresh candidates` reruns the latest `rhythm-combined-*.joblib` model
  against the currently loaded source DB and removes older predictions for that
  feature set after the refresh succeeds
- `Train + refresh` trains new models only after at least 100 new `broken` and
  100 new `straight` labels have been added since the last training checkpoint,
  then refreshes candidates with the new latest combined model. If a combined
  model already exists before checkpoints were introduced, the current label
  counts become the baseline so older labels are not treated as newly added.
- After a successful `Train + refresh`, artifact cleanup keeps the latest 3
  `.joblib` files per feature set and the latest 10 `.metrics.json` files per
  feature set. The current checkpoint model is always protected from deletion.

Predictions are de-duplicated by source track ID for UI/CSV review. If several
model artifacts have predictions for the same track, the latest saved prediction
is used.

## Label Meanings

Use only the rhythm pattern, not the MAEST genre label alone.

- `broken`: syncopated or broken rhythm such as breaks, jungle, drum and bass,
  UK garage, electro, broken beat, halftime, juke, bassline
- `straight`: straight four-on-the-floor rhythm
- `ambiguous`: unclear, mixed, too hard to decide quickly, or not suitable for
  training

Only `broken` and `straight` are used for model training. `ambiguous` is kept for
review and excluded from fitting.

## Training

After labeling enough examples:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py train --source C:\db\abstracted.sqlite --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
```

The training command benchmarks:

- `sonara`
- `mert`
- `maest`
- `combined`

The baseline is a scaled logistic regression model using `scikit-learn` and
`joblib`. Features are read from the source DB. Labels are read from the labels
DB.

Training is tuned as a practical broken-rhythm discovery workflow, not as a
final automatic tagger. Metrics include:

- normal train/test classification report and confusion matrix
- 5-fold stratified cross-validation summary when enough labels are available
- broken-discovery threshold table for `P(broken)`
- top-N broken yield/recall table

Artifacts and metrics are written to:

```text
experiments/rhythm-lab/artifacts/
```

Apply a trained model:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py predict experiments\rhythm-lab\artifacts\<model>.joblib --source C:\db\abstracted.sqlite --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py export-predictions --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
```

The recommended loop is:

1. Label a balanced batch of confident `broken`, confident `straight`, and
   `ambiguous` cases when the decision is not quick.
2. Run `train` and compare `combined`, `maest`, `mert`, and `sonara` metrics.
3. Apply the best artifact with `predict`.
4. Use the Candidates tab to review new unlabeled candidates.
5. Repeat after another focused labeling batch.

The current strongest path is usually `combined`, but it only covers tracks that
have SONARA features plus both MERT and MAEST embeddings. Use `sonara` only as a
broader, lower-quality fallback while waiting for embeddings to finish.

## Future Improvement Ideas

- Add a Candidates sort mode for uncertain tracks near `P(broken) = 0.5`; these
  are often better training examples than more obvious `P(broken) = 1.0` rows.
- Add min/max `P(broken)` filters so review can target high-confidence broken,
  borderline cases, and likely false positives separately.
- Add model-artifact filtering and a visible "latest model" marker in the UI.
- Add an endpoint/command to clear older predictions after a new model is
  accepted, while keeping manual labels untouched.
- Compare regularization strengths for logistic regression and a calibrated
  linear SVM before trying heavier models.
- Add a small label-audit view for old labels where the current model strongly
  disagrees with the manual label.
- Track per-genre and per-folder candidate yield to find styles where the model
  is under-trained.
- Once all library tracks have MERT/MAEST embeddings, rerun `combined` over the
  full database and use Candidates as the main review queue.

## Useful Checks

Count labels:

```powershell
@'
from pathlib import Path
import sqlite3
path = Path(r"E:\Projects\dj-track-similarity\experiments\rhythm-lab\data\rhythm_lab.sqlite")
conn = sqlite3.connect(path)
try:
    print("labels=", conn.execute("SELECT label, COUNT(*) FROM rhythm_labels GROUP BY label ORDER BY label").fetchall())
finally:
    conn.close()
'@ | .\.venv\Scripts\python.exe -
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest experiments\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=
```
