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
and a Load database button. The picker opens only an existing SQLite file. The
selected source DB is opened read-only.

## Labeling UI

The UI includes:

- text search by path/title/artist
- source database picker and load control
- syncopated rhythm filter: all, syncopated rhythm, no syncopated rhythm
- manual label filter: all, unlabeled, broken, straight, ambiguous
- pagination
- audio preview from source paths
- MAEST genres and SONARA/MERT/MAEST feature availability from the source DB

Keyboard shortcuts on a focused row:

- `1` = `broken`
- `2` = `straight`
- `3` = `ambiguous`
- `0` = clear label

AIFF/AIF previews are transcoded to WAV on the fly for browser playback. This is
read-only streaming and does not rewrite or cache the source audio file.

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

Artifacts and metrics are written to:

```text
experiments/rhythm-lab/artifacts/
```

Apply a trained model:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py predict experiments\rhythm-lab\artifacts\<model>.joblib --source C:\db\abstracted.sqlite --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py export-predictions --labels experiments\rhythm-lab\data\rhythm_lab.sqlite
```

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
