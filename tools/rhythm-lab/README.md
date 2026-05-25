# Rhythm Lab

Rhythm Lab is an auxiliary classifier labeling and training UI for
`dj-track-similarity`. It runs separately from the main app, opens a main
project SQLite database read-only, and stores only lab labels, predictions, and
training checkpoints in its own writable SQLite file.

The first supported classifier profile is Break Energy. Its training labels are:

- `broken`: positive Break Energy class for syncopated, broken, break-heavy, or
  drum-break rhythm texture
- `straight`: negative/reference class for straight four-on-the-floor rhythm
- `ambiguous`: review-only label, excluded from fitting

## Storage Layout

Lab state:

```text
tools/rhythm-lab/data/rhythm_lab.sqlite
```

Training artifacts for Break Energy:

```text
tools/rhythm-lab/artifacts/break-energy/
```

Promoted runtime model used by the main app:

```text
models/classifiers/break-energy/model.joblib
models/classifiers/break-energy/model.json
```

The lab database uses classifier-scoped tables:

```text
classifier_labels
classifier_predictions
classifier_training_checkpoints
```

Break Energy rows use `classifier_key = "break_energy"`. This keeps the lab
ready for additional classifier profiles without mixing their labels or
artifacts.

## Quick Start

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Open:

```text
http://127.0.0.1:8777/
```

No source database is loaded at startup unless `--source` is provided. The UI
has a source database path field, file picker, and Load database button. The
selected source DB is opened read-only.

## Labeling UI

The UI includes:

- Library and Candidates tabs
- text search by path/title/artist
- source database picker and load control
- syncopated rhythm filter
- manual Break Energy label filter
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

## Training

After labeling enough examples:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py train --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

The training command benchmarks these feature sets:

- `sonara`
- `mert`
- `maest`
- `combined`

Artifacts and metrics are written to:

```text
tools/rhythm-lab/artifacts/break-energy/
```

Artifact names use the Break Energy classifier prefix, for example:

```text
break-energy-combined-20260525T010203Z.joblib
break-energy-combined-20260525T010203Z.metrics.json
```

Apply a trained model and export candidates:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py predict tools\rhythm-lab\artifacts\break-energy\<model>.joblib --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py export-predictions --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Promote the latest combined Break Energy model into the main project:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py promote-break-energy --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

This copies the latest `break-energy-combined-*.joblib` artifact to
`models/classifiers/break-energy/model.joblib` and writes local metadata to
`models/classifiers/break-energy/model.json`. Those promoted files are local
runtime artifacts and are ignored by git.

## Useful Checks

Count Break Energy labels:

```powershell
@'
from pathlib import Path
import sqlite3
path = Path(r"E:\Projects\dj-track-similarity\tools\rhythm-lab\data\rhythm_lab.sqlite")
conn = sqlite3.connect(path)
try:
    print(conn.execute("""
        SELECT label, COUNT(*)
        FROM classifier_labels
        WHERE classifier_key = 'break_energy'
        GROUP BY label
        ORDER BY label
    """).fetchall())
finally:
    conn.close()
'@ | .\.venv\Scripts\python.exe -
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=
```
