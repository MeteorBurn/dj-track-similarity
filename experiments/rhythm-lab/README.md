# Rhythm Lab

Temporary mini app for training a rhythm classifier on the MAEST-sync subset.
It is intentionally separate from the main frontend and uses a reduced SQLite
database under `experiments/rhythm-lab/data/`.

The lab database uses the normal `LibraryDatabase` schema, plus lab-only tables
for source mapping, manual labels, and predictions. This lets the existing MERT
analysis job run unchanged on the subset. SONARA features are imported from the
source database. MAEST embeddings are extracted with the lab adapter and stored
as embedding key `maest`; the same MAEST pass also saves fresh top genre scores
back into lab metadata as `maest_genres`.

## Quick Start

From the repository root:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py import-subset --source C:\db\abstracted.sqlite
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py import-non-sync-sample --source C:\db\abstracted.sqlite --count 944
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py analyze-mert --device auto --batch-size 4
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py analyze-maest --device auto --batch-size 4
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py serve
```

Then open:

```text
http://127.0.0.1:8777/
```

## Labeling

Use the web app to assign:

- `broken`
- `straight`
- `ambiguous`

Only `broken` and `straight` are used for training.
`ambiguous` is retained for review and excluded from model fitting.

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

Artifacts and metrics are written to `experiments/rhythm-lab/artifacts/`.

Apply a trained model:

```powershell
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py predict experiments\rhythm-lab\artifacts\<model>.joblib
.\.venv\Scripts\python.exe experiments\rhythm-lab\rhythm_lab_cli.py export-predictions
```
