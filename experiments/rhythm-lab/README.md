# Rhythm Lab

Temporary mini app for building a rhythm classifier without changing the main
application UI or mutating audio files.

The lab database lives at:

```text
experiments/rhythm-lab/data/rhythm_lab.sqlite
```

Generated SQLite files and model artifacts are ignored by git. Audio paths are
read from the source database and streamed from their original locations.

## Data Scope

The source database is expected at:

```text
C:\db\abstracted.sqlite
```

The lab set is built from:

- MAEST-sync candidates where `metadata_json.maest_syncopated_rhythm = true`
- an additional random sample of non-sync tracks for straight-rhythm labeling

The current intended seed set is:

- `4056` MAEST-sync candidates
- `944` random non-sync tracks
- `5000` lab tracks total

The source database is opened read-only. Audio files are not copied, moved,
retagged, or modified.

## Quick Start

Run commands from the repository root with the project virtual environment:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py import-subset --source C:\db\abstracted.sqlite
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py import-non-sync-sample --source C:\db\abstracted.sqlite --count 944
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py analyze-mert --device auto --batch-size 4
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py analyze-maest --device auto --batch-size 4
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py serve
```

Open:

```text
http://127.0.0.1:8777/
```

If analysis was already running before importing more tracks, run the analysis
command again later. Jobs select missing tracks when the job starts.

## Feature Extraction

`analyze-mert` uses the main project MERT job code and stores embeddings under:

```text
embedding_key = "mert"
```

`analyze-maest` stores MAEST embeddings under:

```text
embedding_key = "maest"
```

The same MAEST pass also refreshes:

- `maest_genres`
- `maest_model`
- `maest_syncopated_rhythm`

SONARA features are imported from the source database for v1 and are not
recomputed in the lab.

In the main project, MAEST is now also considered analyzed by the same trigger
as MERT and CLAP: a row in `embeddings` for the track with
`embedding_key = "maest"`. The genres are still saved as metadata.

## Labeling UI

Start the UI:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py serve
```

The UI includes:

- text search by path/title/artist
- syncopated rhythm filter: all, syncopated rhythm, no syncopated rhythm
- manual label filter: all, unlabeled, broken, straight, ambiguous
- pagination
- audio preview
- MAEST genres and feature availability

The `syncopated rhythm` badge is automatic and comes from
`maest_syncopated_rhythm`. The manual rhythm label is separate and is used for
training.

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
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py train
```

The training command benchmarks:

- `sonara`
- `mert`
- `maest`
- `combined`

The baseline is a scaled logistic regression model using `scikit-learn` and
`joblib`.

Artifacts and metrics are written to:

```text
experiments/rhythm-lab/artifacts/
```

Apply a trained model:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py predict experiments\rhythm-lab\artifacts\<model>.joblib
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py export-predictions
```

## Useful Checks

Count lab tracks and labels:

```powershell
@'
from pathlib import Path
import sqlite3
path = Path(r"E:\Projects\dj-track-similarity\experiments\rhythm-lab\data\rhythm_lab.sqlite")
conn = sqlite3.connect(path)
try:
    print("tracks=", conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
    print("sync_true=", conn.execute("SELECT COUNT(*) FROM tracks WHERE json_extract(metadata_json, '$.maest_syncopated_rhythm') = 1").fetchone()[0])
    print("non_sync=", conn.execute("SELECT COUNT(*) FROM tracks WHERE COALESCE(json_extract(metadata_json, '$.maest_syncopated_rhythm'), 0) != 1").fetchone()[0])
    print("labels=", conn.execute("SELECT label, COUNT(*) FROM rhythm_labels GROUP BY label ORDER BY label").fetchall())
finally:
    conn.close()
'@ | .\.venv\Scripts\python.exe -
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest experiments\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=
```
